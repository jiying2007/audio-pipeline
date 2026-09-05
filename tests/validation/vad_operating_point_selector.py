#!/usr/bin/env python3
"""Bounded, non-shipping VAD decision operating-point selector.

The selector replays existing VAD probability traces, changes only the final
decision threshold, applies the product's 8-frame hangover exactly, and reuses
canonical vad_stats()/threshold_violations() for all scoring/gates. Probability
generation, noise adaptation, NS fusion, guards and hangover length are not tuned.
"""

from __future__ import annotations

import argparse
import json
import math
import tempfile
from pathlib import Path
from typing import Any

import run_validation_engine as engine
import stage_profile_support

stage_profile_support.install(engine)

BASELINE_LOCAL = 0.45
BASELINE_NS = 0.35
LOCAL_THRESHOLDS = (0.40, 0.42, 0.45, 0.48, 0.50)
NS_THRESHOLDS = (0.30, 0.32, 0.35, 0.38, 0.40)
HANGOVER_FRAMES = 8
MIN_IMPROVEMENT_SCORE = 0.50
MAX_RECALL_REGRESSION = 0.03
MAX_F1_REGRESSION = 0.03
MAX_FPR_REGRESSION = 0.03


def decision_trace(probabilities: list[float], threshold: float) -> list[dict[str, int]]:
    if not math.isfinite(threshold) or not 0.0 < threshold < 1.0:
        raise ValueError("threshold must be finite and in (0, 1)")
    hangover = 0
    trace: list[dict[str, int]] = []
    for probability in probabilities:
        value = float(probability)
        if not math.isfinite(value):
            value = 0.0
        if value > threshold:
            hangover = HANGOVER_FRAMES
        elif hangover:
            hangover -= 1
        trace.append({"vad_active": 1 if hangover > 0 else 0})
    return trace


def vad_expected(case: dict[str, Any]) -> dict[str, float]:
    allowed = {
        "min_vad_f1",
        "min_vad_precision",
        "min_vad_recall",
        "max_vad_false_positive_rate",
        "max_vad_false_negative_rate",
    }
    return {
        key: float(value)
        for key, value in case.get("expected", {}).items()
        if key in allowed
    }


def collect_case(processor: Path, corpus_path: Path, case: dict[str, Any]) -> dict[str, Any]:
    profile = case.get("processor_profile", "default")
    if profile not in {"vad-isolated", "ns-isolated"}:
        raise ValueError(f"unsupported selector profile: {profile}")
    labels_path = engine.resolve(corpus_path, case.get("vad_labels"))
    if labels_path is None:
        raise ValueError(f"VAD labels required: {case['case_id']}")
    labels = engine.load_labels(labels_path)
    with tempfile.TemporaryDirectory(prefix="ap-vad-selector-") as temporary:
        _, trace, _ = engine.invoke(processor, case, corpus_path, Path(temporary))
    probabilities = [float(row.get("vad_probability", 0.0)) for row in trace]
    count = min(len(labels), len(probabilities))
    if count == 0:
        raise ValueError(f"empty VAD evidence: {case['case_id']}")
    return {
        "case_id": case["case_id"],
        "scenario": case["scenario"],
        "processor_profile": profile,
        "labels": labels[:count],
        "probabilities": probabilities[:count],
        "expected": vad_expected(case),
    }


def collect_partition(processor: Path, corpus_path: Path) -> dict[str, Any]:
    corpus = json.loads(corpus_path.read_text(encoding="utf-8"))
    cases = []
    for case in corpus.get("cases", []):
        if case.get("processor_profile") not in {"vad-isolated", "ns-isolated"}:
            continue
        if case.get("vad_labels"):
            cases.append(collect_case(processor, corpus_path, case))
    profiles = {case["processor_profile"] for case in cases}
    if profiles != {"vad-isolated", "ns-isolated"}:
        raise ValueError(f"selector requires both VAD profiles: {sorted(profiles)}")
    return {
        "corpus_id": corpus.get("corpus_id"),
        "generator_seed": corpus.get("generator", {}).get("seed"),
        "corpus_sha256": engine.sha256_file(corpus_path),
        "cases": cases,
    }


def case_metrics(case: dict[str, Any], threshold: float) -> dict[str, float | None]:
    stats = engine.vad_stats(
        case["labels"],
        decision_trace(case["probabilities"], threshold),
    )
    return {
        "vad_f1": stats["f1"],
        "vad_precision": stats["precision"],
        "vad_recall": stats["recall"],
        "vad_false_positive_rate": stats["false_positive_rate"],
        "vad_false_negative_rate": stats["false_negative_rate"],
    }


def threshold_for(profile: str, local_threshold: float, ns_threshold: float) -> float:
    return ns_threshold if profile == "ns-isolated" else local_threshold


def evaluate(partition: dict[str, Any], local_threshold: float, ns_threshold: float) -> dict[str, Any]:
    results = []
    positive_case_ids = {
        case["case_id"] for case in partition["cases"] if any(case["labels"])
    }
    for case in partition["cases"]:
        threshold = threshold_for(case["processor_profile"], local_threshold, ns_threshold)
        metrics = case_metrics(case, threshold)
        violations = engine.threshold_violations(metrics, case["expected"])
        results.append({
            "case_id": case["case_id"],
            "scenario": case["scenario"],
            "processor_profile": case["processor_profile"],
            "threshold": threshold,
            "metrics": metrics,
            "violations": violations,
            "passed": not violations,
        })
    recalls = [
        float(item["metrics"]["vad_recall"])
        for item in results
        if item["case_id"] in positive_case_ids
        and item["metrics"]["vad_recall"] is not None
    ]
    f1_values = [
        float(item["metrics"]["vad_f1"])
        for item in results
        if item["case_id"] in positive_case_ids
        and item["metrics"]["vad_f1"] is not None
    ]
    fpr_values = [
        float(item["metrics"]["vad_false_positive_rate"])
        for item in results
        if item["metrics"]["vad_false_positive_rate"] is not None
    ]
    summary = {
        "cases": len(results),
        "passed_cases": sum(item["passed"] for item in results),
        "pass_rate": sum(item["passed"] for item in results) / max(1, len(results)),
        "min_vad_recall": min(recalls) if recalls else None,
        "min_vad_f1": min(f1_values) if f1_values else None,
        "max_vad_false_positive_rate": max(fpr_values) if fpr_values else None,
    }
    return {
        "local_threshold": local_threshold,
        "ns_threshold": ns_threshold,
        "validation_result": "PASS" if all(item["passed"] for item in results) else "FAIL",
        "summary": summary,
        "cases": results,
    }


def metric(report: dict[str, Any], name: str) -> float:
    value = report["summary"].get(name)
    if value is None:
        raise ValueError(f"missing aggregate metric: {name}")
    return float(value)


def regression_violations(baseline: dict[str, Any], candidate: dict[str, Any]) -> list[dict[str, Any]]:
    violations: list[dict[str, Any]] = []
    if candidate["validation_result"] != "PASS":
        violations.append({"gate": "candidate_case_gates", "actual": candidate["validation_result"]})
    checks = (
        ("min_vad_recall", "max_drop", MAX_RECALL_REGRESSION),
        ("min_vad_f1", "max_drop", MAX_F1_REGRESSION),
        ("max_vad_false_positive_rate", "max_rise", MAX_FPR_REGRESSION),
    )
    for name, kind, allowed in checks:
        base = metric(baseline, name)
        cand = metric(candidate, name)
        regression = (base - cand) if kind == "max_drop" else (cand - base)
        if regression > allowed + 1.0e-12:
            violations.append({
                "gate": "aggregate_regression",
                "metric": name,
                "baseline": base,
                "candidate": cand,
                "regression": regression,
                "allowed": allowed,
            })
    return violations


def score(baseline: dict[str, Any], candidate: dict[str, Any]) -> float:
    recall_delta = metric(candidate, "min_vad_recall") - metric(baseline, "min_vad_recall")
    f1_delta = metric(candidate, "min_vad_f1") - metric(baseline, "min_vad_f1")
    fpr_improvement = (
        metric(baseline, "max_vad_false_positive_rate")
        - metric(candidate, "max_vad_false_positive_rate")
    )
    return (
        2.0 * recall_delta / 0.02
        + 1.0 * f1_delta / 0.02
        + 1.5 * fpr_improvement / 0.02
    )


def candidate_id(local_threshold: float, ns_threshold: float) -> str:
    return f"local={local_threshold:.2f},ns={ns_threshold:.2f}"


def select(development: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    baseline = evaluate(development, BASELINE_LOCAL, BASELINE_NS)
    ranking = []
    for local_threshold in LOCAL_THRESHOLDS:
        for ns_threshold in NS_THRESHOLDS:
            report = evaluate(development, local_threshold, ns_threshold)
            violations = regression_violations(baseline, report)
            ranking.append({
                "candidate_id": candidate_id(local_threshold, ns_threshold),
                "local_threshold": local_threshold,
                "ns_threshold": ns_threshold,
                "score": score(baseline, report),
                "validation_result": report["validation_result"],
                "summary": report["summary"],
                "regression_violations": violations,
            })

    baseline_id = candidate_id(BASELINE_LOCAL, BASELINE_NS)
    eligible = [
        item for item in ranking
        if not item["regression_violations"]
        and item["validation_result"] == "PASS"
        and item["score"] >= MIN_IMPROVEMENT_SCORE
    ]
    eligible.sort(key=lambda item: (
        -float(item["score"]),
        abs(float(item["local_threshold"]) - BASELINE_LOCAL)
        + abs(float(item["ns_threshold"]) - BASELINE_NS),
        item["candidate_id"],
    ))
    selected = eligible[0] if eligible else next(
        item for item in ranking if item["candidate_id"] == baseline_id
    )
    ranking.sort(key=lambda item: (-float(item["score"]), item["candidate_id"]))
    return selected, ranking


def partition_identity(partition: dict[str, Any]) -> dict[str, Any]:
    return {
        key: partition[key]
        for key in ("corpus_id", "generator_seed", "corpus_sha256")
    }


def run(processor: Path, development_path: Path, validation_path: Path,
        shadow_path: Path, output: Path) -> dict[str, Any]:
    development = collect_partition(processor, development_path)
    validation = collect_partition(processor, validation_path)
    shadow = collect_partition(processor, shadow_path)
    seeds = [development["generator_seed"], validation["generator_seed"], shadow["generator_seed"]]
    if None in seeds or len(set(seeds)) != 3:
        raise ValueError("development/validation/shadow must use three distinct generator seeds")
    hashes = [development["corpus_sha256"], validation["corpus_sha256"], shadow["corpus_sha256"]]
    if len(set(hashes)) != 3:
        raise ValueError("development/validation/shadow corpus hashes must be distinct")

    selected, ranking = select(development)
    baseline_dev = evaluate(development, BASELINE_LOCAL, BASELINE_NS)
    selected_dev = evaluate(development, selected["local_threshold"], selected["ns_threshold"])
    val_baseline = evaluate(validation, BASELINE_LOCAL, BASELINE_NS)
    val_candidate = evaluate(validation, selected["local_threshold"], selected["ns_threshold"])
    shadow_baseline = evaluate(shadow, BASELINE_LOCAL, BASELINE_NS)
    shadow_candidate = evaluate(shadow, selected["local_threshold"], selected["ns_threshold"])
    val_violations = regression_violations(val_baseline, val_candidate)
    shadow_violations = regression_violations(shadow_baseline, shadow_candidate)

    baseline_id = candidate_id(BASELINE_LOCAL, BASELINE_NS)
    if selected["candidate_id"] == baseline_id:
        decision = "KEEP_BASELINE"
    elif not val_violations and not shadow_violations:
        decision = "RESEARCH_CANDIDATE"
    else:
        decision = "REJECT_CANDIDATE"

    result = {
        "schema_version": 1,
        "authority": "non-shipping-vad-operating-point-selection",
        "decision": decision,
        "baseline": {
            "local_threshold": BASELINE_LOCAL,
            "ns_threshold": BASELINE_NS,
        },
        "selected": selected,
        "development": {
            "identity": partition_identity(development),
            "baseline": baseline_dev,
            "candidate": selected_dev,
            "ranking": ranking,
        },
        "validation": {
            "identity": partition_identity(validation),
            "baseline": val_baseline,
            "candidate": val_candidate,
            "regression_violations": val_violations,
        },
        "shadow": {
            "identity": partition_identity(shadow),
            "baseline": shadow_baseline,
            "candidate": shadow_candidate,
            "regression_violations": shadow_violations,
        },
        "scope": {
            "decision_only": True,
            "hangover_frames": HANGOVER_FRAMES,
            "probability_generation_unchanged": True,
            "noise_adaptation_unchanged": True,
            "ns_fusion_unchanged": True,
        },
        "promotion_required": [
            "separate release-bearing source change for any shipping threshold modification",
            "full canonical regression plus hosted real-audio/AEC replay on the exact source candidate",
            "target CPU/RSS/latency evidence and HIL before product promotion",
        ],
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result


def self_test() -> None:
    probabilities = [0.1, 0.8, 0.1] + [0.1] * 9
    trace = decision_trace(probabilities, 0.5)
    active = [row["vad_active"] for row in trace]
    assert active[0] == 0 and active[1] == 1
    assert sum(active[1:9]) == 8
    assert active[9] == 0

    labels = [0, 0, 1, 1, 1, 0, 0]
    candidate = decision_trace([0.1, 0.2, 0.8, 0.7, 0.6, 0.1, 0.1], 0.5)
    stats = engine.vad_stats(labels, candidate)
    assert stats["recall"] == 1.0
    assert candidate_id(BASELINE_LOCAL, BASELINE_NS) == "local=0.45,ns=0.35"
    assert len(LOCAL_THRESHOLDS) * len(NS_THRESHOLDS) == 25
    print("VAD operating-point selector self-test: OK")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--processor", type=Path)
    parser.add_argument("--development-corpus", type=Path)
    parser.add_argument("--validation-corpus", type=Path)
    parser.add_argument("--shadow-corpus", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    for name in ("processor", "development_corpus", "validation_corpus", "shadow_corpus", "output"):
        if getattr(args, name) is None:
            parser.error(f"--{name.replace('_', '-')} is required")
    result = run(
        args.processor.resolve(),
        args.development_corpus.resolve(),
        args.validation_corpus.resolve(),
        args.shadow_corpus.resolve(),
        args.output.resolve(),
    )
    print(json.dumps({
        "decision": result["decision"],
        "selected": result["selected"]["candidate_id"],
        "score": result["selected"]["score"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
