#!/usr/bin/env python3
"""Research-only strong/weak VAD hangover refresh selector.

Keep product probability generation, local/NS decision thresholds, NS fusion, noise
adaptation and the strong 8-frame hold unchanged. Only test whether marginal
admissions should refresh a shorter hold. Candidate selection is development-only;
validation, shadow and frozen AMI data can reject but never select.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

import run_validation_engine as engine
import stage_profile_support
import vad_operating_point_selector as selector
import vad_hangover_counterfactual as fixed

stage_profile_support.install(engine)

LOCAL_THRESHOLD = 0.45
NS_THRESHOLD = 0.35
STRONG_HOLD = 8
STRONG_THRESHOLDS = (0.50, 0.55, 0.60)
WEAK_HOLDS = (4, 6)
MIN_DEV_SCORE = 0.25
MIN_HOLDOUT_SCORE = 0.0


def _probability(raw: float) -> float:
    value = float(raw)
    return value if math.isfinite(value) else 0.0


def baseline_trace(probabilities: list[float], decision_threshold: float) -> list[dict[str, int]]:
    if not 0.0 < decision_threshold < 1.0:
        raise ValueError("decision_threshold must be in (0,1)")
    hangover = 0
    trace: list[dict[str, int]] = []
    for raw in probabilities:
        probability = _probability(raw)
        if probability > decision_threshold:
            hangover = STRONG_HOLD
        elif hangover:
            hangover -= 1
        trace.append({"vad_active": 1 if hangover > 0 else 0})
    return trace


def policy_trace(probabilities: list[float], decision_threshold: float,
                 strong_threshold: float, weak_hold: int) -> list[dict[str, int]]:
    if not 0.0 < decision_threshold < strong_threshold < 1.0:
        raise ValueError("strong threshold must be above decision threshold and below 1")
    if weak_hold < 1 or weak_hold >= STRONG_HOLD:
        raise ValueError("weak hold must be shorter than strong hold")
    hangover = 0
    trace: list[dict[str, int]] = []
    for raw in probabilities:
        probability = _probability(raw)
        if probability > decision_threshold:
            if probability >= strong_threshold:
                hangover = STRONG_HOLD
            elif hangover < weak_hold:
                # Marginal evidence may extend a short tail, but must never truncate
                # a longer tail established by earlier strong evidence.
                hangover = weak_hold
        elif hangover:
            hangover -= 1
        trace.append({"vad_active": 1 if hangover > 0 else 0})
    return trace


def threshold_for(profile: str) -> float:
    return NS_THRESHOLD if profile == "ns-isolated" else LOCAL_THRESHOLD


def _stats(case: dict[str, Any], trace: list[dict[str, int]]) -> dict[str, float | None]:
    stats = engine.vad_stats(case["labels"], trace)
    return {
        "vad_f1": stats["f1"],
        "vad_precision": stats["precision"],
        "vad_recall": stats["recall"],
        "vad_false_positive_rate": stats["false_positive_rate"],
        "vad_false_negative_rate": stats["false_negative_rate"],
    }


def evaluate_synthetic(partition: dict[str, Any], strong_threshold: float | None,
                       weak_hold: int | None) -> dict[str, Any]:
    baseline = strong_threshold is None or weak_hold is None
    results = []
    positive_case_ids = {case["case_id"] for case in partition["cases"] if any(case["labels"])}
    for case in partition["cases"]:
        decision_threshold = threshold_for(case["processor_profile"])
        if baseline:
            trace = baseline_trace(case["probabilities"], decision_threshold)
        else:
            trace = policy_trace(case["probabilities"], decision_threshold, float(strong_threshold), int(weak_hold))
        metrics = _stats(case, trace)
        violations = engine.threshold_violations(metrics, case["expected"])
        results.append({
            "case_id": case["case_id"],
            "scenario": case["scenario"],
            "processor_profile": case["processor_profile"],
            "metrics": metrics,
            "violations": violations,
            "passed": not violations,
        })
    recalls = [float(item["metrics"]["vad_recall"]) for item in results
               if item["case_id"] in positive_case_ids and item["metrics"]["vad_recall"] is not None]
    f1_values = [float(item["metrics"]["vad_f1"]) for item in results
                 if item["case_id"] in positive_case_ids and item["metrics"]["vad_f1"] is not None]
    fpr_values = [float(item["metrics"]["vad_false_positive_rate"]) for item in results
                  if item["metrics"]["vad_false_positive_rate"] is not None]
    summary = {
        "cases": len(results),
        "passed_cases": sum(item["passed"] for item in results),
        "pass_rate": sum(item["passed"] for item in results) / max(1, len(results)),
        "min_vad_recall": min(recalls) if recalls else None,
        "min_vad_f1": min(f1_values) if f1_values else None,
        "max_vad_false_positive_rate": max(fpr_values) if fpr_values else None,
    }
    return {
        "strong_threshold": strong_threshold,
        "weak_hold": weak_hold,
        "validation_result": "PASS" if all(item["passed"] for item in results) else "FAIL",
        "summary": summary,
        "cases": results,
    }


def metric(report: dict[str, Any], name: str) -> float:
    value = report["summary"].get(name)
    if value is None:
        raise ValueError(f"missing aggregate metric: {name}")
    return float(value)


def score_synthetic(baseline: dict[str, Any], candidate: dict[str, Any]) -> float:
    recall_delta = metric(candidate, "min_vad_recall") - metric(baseline, "min_vad_recall")
    f1_delta = metric(candidate, "min_vad_f1") - metric(baseline, "min_vad_f1")
    fpr_improvement = metric(baseline, "max_vad_false_positive_rate") - metric(candidate, "max_vad_false_positive_rate")
    return recall_delta / 0.02 + f1_delta / 0.02 + 1.75 * fpr_improvement / 0.02


def synthetic_regressions(baseline: dict[str, Any], candidate: dict[str, Any]) -> list[dict[str, Any]]:
    # Reuse the predeclared fixed-hangover anti-regression contract from #82.
    return fixed.synthetic_regressions(baseline, candidate)


def candidate_id(strong_threshold: float, weak_hold: int) -> str:
    return f"strong={strong_threshold:.2f},weak={weak_hold}"


def candidate_space() -> list[tuple[float, int]]:
    return [(strong, weak) for strong in STRONG_THRESHOLDS for weak in WEAK_HOLDS]


def select_development(development: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    baseline = evaluate_synthetic(development, None, None)
    ranking = []
    for strong_threshold, weak_hold in candidate_space():
        report = evaluate_synthetic(development, strong_threshold, weak_hold)
        regressions = synthetic_regressions(baseline, report)
        ranking.append({
            "candidate_id": candidate_id(strong_threshold, weak_hold),
            "strong_threshold": strong_threshold,
            "weak_hold": weak_hold,
            "score": score_synthetic(baseline, report),
            "validation_result": report["validation_result"],
            "summary": report["summary"],
            "regression_violations": regressions,
            "failed_cases": [item["case_id"] for item in report["cases"] if not item["passed"]],
        })
    eligible = [item for item in ranking
                if item["validation_result"] == "PASS"
                and not item["regression_violations"]
                and float(item["score"]) >= MIN_DEV_SCORE]
    eligible.sort(key=lambda item: (-float(item["score"]), -int(item["weak_hold"]), float(item["strong_threshold"])))
    if eligible:
        selected = eligible[0]
    else:
        selected = {
            "candidate_id": "baseline",
            "strong_threshold": None,
            "weak_hold": 8,
            "score": 0.0,
            "validation_result": baseline["validation_result"],
            "summary": baseline["summary"],
            "regression_violations": [],
            "failed_cases": [],
        }
    ranking.sort(key=lambda item: (-float(item["score"]), item["candidate_id"]))
    return selected, ranking


def ami_report(ami: dict[str, Any], strong_threshold: float | None,
               weak_hold: int | None) -> dict[str, Any]:
    baseline = strong_threshold is None or weak_hold is None
    windows = []
    all_labels: list[int] = []
    all_trace: list[dict[str, int]] = []
    for window in ami["windows"]:
        if baseline:
            trace = baseline_trace(window["probabilities"], NS_THRESHOLD)
        else:
            trace = policy_trace(window["probabilities"], NS_THRESHOLD, float(strong_threshold), int(weak_hold))
        stats = engine.vad_stats(window["labels"], trace)
        all_labels.extend(window["labels"])
        all_trace.extend(trace)
        windows.append({
            "window_id": window["window_id"],
            "activity_fraction": window["activity_fraction"],
            "metrics": stats,
        })
    return {
        "strong_threshold": strong_threshold,
        "weak_hold": weak_hold,
        "aggregate": engine.vad_stats(all_labels, all_trace),
        "windows": windows,
    }


def partition_identity(partition: dict[str, Any]) -> dict[str, Any]:
    return {key: partition[key] for key in ("corpus_id", "generator_seed", "corpus_sha256")}


def point_for_synthetic(partition: dict[str, Any], baseline: dict[str, Any],
                        strong_threshold: float, weak_hold: int) -> dict[str, Any]:
    report = evaluate_synthetic(partition, strong_threshold, weak_hold)
    return {
        "candidate_id": candidate_id(strong_threshold, weak_hold),
        "strong_threshold": strong_threshold,
        "weak_hold": weak_hold,
        "score": score_synthetic(baseline, report),
        "validation_result": report["validation_result"],
        "summary": report["summary"],
        "regression_violations": synthetic_regressions(baseline, report),
        "failed_cases": [item["case_id"] for item in report["cases"] if not item["passed"]],
    }


def point_for_ami(ami: dict[str, Any], baseline: dict[str, Any],
                  strong_threshold: float, weak_hold: int) -> dict[str, Any]:
    report = ami_report(ami, strong_threshold, weak_hold)
    return {
        "candidate_id": candidate_id(strong_threshold, weak_hold),
        "strong_threshold": strong_threshold,
        "weak_hold": weak_hold,
        "score": fixed.ami_score(baseline, report),
        "report": report,
        "regression_violations": fixed.ami_regressions(baseline, report),
    }


def run(processor: Path, development_path: Path, validation_path: Path,
        shadow_path: Path, ami_lock: Path, output: Path) -> dict[str, Any]:
    development = selector.collect_partition(processor, development_path)
    validation = selector.collect_partition(processor, validation_path)
    shadow = selector.collect_partition(processor, shadow_path)
    seeds = [development["generator_seed"], validation["generator_seed"], shadow["generator_seed"]]
    if seeds != [1307, 2307, 3307]:
        raise ValueError(f"unexpected selector partition seeds: {seeds}")
    if len({development["corpus_sha256"], validation["corpus_sha256"], shadow["corpus_sha256"]}) != 3:
        raise ValueError("synthetic partitions must have distinct corpus hashes")

    selected, development_ranking = select_development(development)
    dev_baseline = evaluate_synthetic(development, None, None)
    val_baseline = evaluate_synthetic(validation, None, None)
    shadow_baseline = evaluate_synthetic(shadow, None, None)
    ami = fixed.collect_ami(processor, ami_lock)
    ami_baseline = ami_report(ami, None, None)

    matrix = {
        "development": development_ranking,
        "validation": [point_for_synthetic(validation, val_baseline, s, w) for s, w in candidate_space()],
        "shadow": [point_for_synthetic(shadow, shadow_baseline, s, w) for s, w in candidate_space()],
        "ami": [point_for_ami(ami, ami_baseline, s, w) for s, w in candidate_space()],
    }

    if selected["candidate_id"] == "baseline":
        decision = "KEEP_BASELINE"
        selected_dev = dev_baseline
        val_candidate = val_baseline
        shadow_candidate = shadow_baseline
        ami_candidate = ami_baseline
        val_regressions: list[dict[str, Any]] = []
        shadow_regressions: list[dict[str, Any]] = []
        ami_regressions: list[dict[str, Any]] = []
        val_score = shadow_score = ami_score = 0.0
    else:
        strong = float(selected["strong_threshold"])
        weak = int(selected["weak_hold"])
        selected_dev = evaluate_synthetic(development, strong, weak)
        val_candidate = evaluate_synthetic(validation, strong, weak)
        shadow_candidate = evaluate_synthetic(shadow, strong, weak)
        ami_candidate = ami_report(ami, strong, weak)
        val_regressions = synthetic_regressions(val_baseline, val_candidate)
        shadow_regressions = synthetic_regressions(shadow_baseline, shadow_candidate)
        ami_regressions = fixed.ami_regressions(ami_baseline, ami_candidate)
        val_score = score_synthetic(val_baseline, val_candidate)
        shadow_score = score_synthetic(shadow_baseline, shadow_candidate)
        ami_score = fixed.ami_score(ami_baseline, ami_candidate)
        if (not val_regressions and not shadow_regressions and not ami_regressions
                and val_score >= MIN_HOLDOUT_SCORE and shadow_score >= MIN_HOLDOUT_SCORE
                and ami_score >= MIN_HOLDOUT_SCORE):
            decision = "RESEARCH_CANDIDATE"
        else:
            decision = "REJECT_CANDIDATE"

    result = {
        "schema_version": 1,
        "authority": "non-shipping-vad-strong-weak-refresh",
        "decision": decision,
        "baseline": {
            "local_threshold": LOCAL_THRESHOLD,
            "ns_threshold": NS_THRESHOLD,
            "refresh_hold": STRONG_HOLD,
        },
        "search_space": {
            "strong_thresholds": list(STRONG_THRESHOLDS),
            "weak_holds": list(WEAK_HOLDS),
            "candidate_count": len(candidate_space()),
        },
        "selected": selected,
        "development": {
            "identity": partition_identity(development),
            "baseline": dev_baseline,
            "candidate": selected_dev,
        },
        "validation": {
            "identity": partition_identity(validation),
            "baseline": val_baseline,
            "candidate": val_candidate,
            "score": val_score,
            "regression_violations": val_regressions,
        },
        "shadow": {
            "identity": partition_identity(shadow),
            "baseline": shadow_baseline,
            "candidate": shadow_candidate,
            "score": shadow_score,
            "regression_violations": shadow_regressions,
        },
        "ami_holdout": {
            "authority": "research-external-timing-holdout",
            "identity": {
                "meeting": ami["meeting"],
                "license": ami["license"],
                "transport_revision": ami["transport_revision"],
                "lock_sha256": ami["lock_sha256"],
            },
            "baseline": ami_baseline,
            "candidate": ami_candidate,
            "score": ami_score,
            "regression_violations": ami_regressions,
        },
        "response_matrix": matrix,
        "scope": {
            "shipping_source_unchanged": True,
            "probability_generation_unchanged": True,
            "noise_adaptation_unchanged": True,
            "ns_fusion_unchanged": True,
            "strong_hold_fixed": STRONG_HOLD,
            "weak_evidence_never_truncates_existing_strong_hold": True,
            "candidate_selection_partition": "development-seed-1307-only",
            "holdouts_cannot_select": True,
        },
        "promotion_required": [
            "separate release-bearing source change for any shipping refresh-policy modification",
            "exact-source canonical plus hosted-real qualification",
            "target CPU/RSS/latency and HIL evidence before product promotion",
        ],
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result


def self_test() -> None:
    probabilities = [0.10, 0.58, 0.10, 0.40, 0.10, 0.10, 0.10, 0.10, 0.10]
    baseline = baseline_trace(probabilities, 0.35)
    candidate = policy_trace(probabilities, 0.35, 0.55, 4)
    assert baseline[1]["vad_active"] == 1 and candidate[1]["vad_active"] == 1
    # Strong evidence establishes 8 frames and later weak evidence must not shorten it.
    assert sum(row["vad_active"] for row in candidate) == sum(row["vad_active"] for row in baseline)

    weak_only = policy_trace([0.10, 0.40] + [0.10] * 8, 0.35, 0.55, 4)
    assert sum(row["vad_active"] for row in weak_only) == 4
    assert len(candidate_space()) == 6
    assert candidate_id(0.55, 6) == "strong=0.55,weak=6"
    print("VAD strong/weak refresh self-test: OK")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--processor", type=Path)
    parser.add_argument("--development-corpus", type=Path)
    parser.add_argument("--validation-corpus", type=Path)
    parser.add_argument("--shadow-corpus", type=Path)
    parser.add_argument("--ami-lock", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    required = (args.processor, args.development_corpus, args.validation_corpus,
                args.shadow_corpus, args.ami_lock, args.output)
    if any(item is None for item in required):
        parser.error("processor, three corpora, AMI lock and output are required")
    result = run(args.processor, args.development_corpus, args.validation_corpus,
                 args.shadow_corpus, args.ami_lock, args.output)
    selected = result["selected"]
    print(json.dumps({
        "decision": result["decision"],
        "selected": selected["candidate_id"],
        "development_score": selected["score"],
        "validation_score": result["validation"]["score"],
        "shadow_score": result["shadow"]["score"],
        "ami_score": result["ami_holdout"]["score"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
