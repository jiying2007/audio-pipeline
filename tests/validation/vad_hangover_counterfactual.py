#!/usr/bin/env python3
"""Bounded research-only VAD hangover counterfactual.

Keep shipping probability generation, thresholds and NS fusion unchanged. Select a
shared hangover length only on deterministic development seed 1307, replay on
2307/3307, then let the frozen AMI external-timing microset independently accept
or reject the synthetic candidate. This tool never mutates shipping defaults.
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
import vad_operating_point_selector as selector
import ami_vad_microset_eval as ami_eval
import discover_ami_vad_microset as discovery

stage_profile_support.install(engine)

LOCAL_THRESHOLD = 0.45
NS_THRESHOLD = 0.35
BASELINE_HANGOVER = 8
HANGOVER_CANDIDATES = (2, 4, 6, 8)
MIN_DEV_SCORE = 0.25
MAX_RECALL_DROP = 0.03
MAX_F1_DROP = 0.02
MAX_FPR_RISE = 0.01
MIN_HOLDOUT_SCORE = 0.0
AMI_MIN_FPR_IMPROVEMENT = 0.005
AMI_MAX_RECALL_DROP = 0.03
AMI_MAX_F1_DROP = 0.02
AMI_W2_MIN_FPR_IMPROVEMENT = 0.005
AMI_WINDOW_MAX_RECALL_DROP = 0.05
AMI_WINDOW_MAX_F1_DROP = 0.03
AMI_WINDOW_MAX_FPR_RISE = 0.01


def decision_trace(probabilities: list[float], threshold: float, hangover_frames: int) -> list[dict[str, int]]:
    if not math.isfinite(threshold) or not 0.0 < threshold < 1.0:
        raise ValueError("threshold must be finite and in (0, 1)")
    if hangover_frames < 1 or hangover_frames > 32:
        raise ValueError("hangover_frames must be in 1..32")
    hangover = 0
    trace: list[dict[str, int]] = []
    for raw in probabilities:
        probability = float(raw)
        if not math.isfinite(probability):
            probability = 0.0
        if probability > threshold:
            hangover = hangover_frames
        elif hangover:
            hangover -= 1
        trace.append({"vad_active": 1 if hangover > 0 else 0})
    return trace


def threshold_for(profile: str) -> float:
    return NS_THRESHOLD if profile == "ns-isolated" else LOCAL_THRESHOLD


def case_metrics(case: dict[str, Any], hangover_frames: int) -> dict[str, float | None]:
    stats = engine.vad_stats(
        case["labels"],
        decision_trace(case["probabilities"], threshold_for(case["processor_profile"]), hangover_frames),
    )
    return {
        "vad_f1": stats["f1"],
        "vad_precision": stats["precision"],
        "vad_recall": stats["recall"],
        "vad_false_positive_rate": stats["false_positive_rate"],
        "vad_false_negative_rate": stats["false_negative_rate"],
    }


def evaluate_synthetic(partition: dict[str, Any], hangover_frames: int) -> dict[str, Any]:
    results = []
    positive_case_ids = {case["case_id"] for case in partition["cases"] if any(case["labels"])}
    for case in partition["cases"]:
        metrics = case_metrics(case, hangover_frames)
        violations = engine.threshold_violations(metrics, case["expected"])
        results.append({
            "case_id": case["case_id"],
            "scenario": case["scenario"],
            "processor_profile": case["processor_profile"],
            "threshold": threshold_for(case["processor_profile"]),
            "hangover_frames": hangover_frames,
            "metrics": metrics,
            "violations": violations,
            "passed": not violations,
        })
    recalls = [
        float(item["metrics"]["vad_recall"])
        for item in results
        if item["case_id"] in positive_case_ids and item["metrics"]["vad_recall"] is not None
    ]
    f1_values = [
        float(item["metrics"]["vad_f1"])
        for item in results
        if item["case_id"] in positive_case_ids and item["metrics"]["vad_f1"] is not None
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
        "hangover_frames": hangover_frames,
        "validation_result": "PASS" if all(item["passed"] for item in results) else "FAIL",
        "summary": summary,
        "cases": results,
    }


def metric(report: dict[str, Any], name: str) -> float:
    value = report["summary"].get(name)
    if value is None:
        raise ValueError(f"missing aggregate metric: {name}")
    return float(value)


def synthetic_score(baseline: dict[str, Any], candidate: dict[str, Any]) -> float:
    recall_delta = metric(candidate, "min_vad_recall") - metric(baseline, "min_vad_recall")
    f1_delta = metric(candidate, "min_vad_f1") - metric(baseline, "min_vad_f1")
    fpr_improvement = metric(baseline, "max_vad_false_positive_rate") - metric(candidate, "max_vad_false_positive_rate")
    return (
        1.0 * recall_delta / 0.02
        + 1.0 * f1_delta / 0.02
        + 1.75 * fpr_improvement / 0.02
    )


def synthetic_regressions(baseline: dict[str, Any], candidate: dict[str, Any]) -> list[dict[str, Any]]:
    violations: list[dict[str, Any]] = []
    if candidate["validation_result"] != "PASS":
        violations.append({"gate": "candidate_case_gates", "actual": candidate["validation_result"]})
    checks = (
        ("min_vad_recall", metric(baseline, "min_vad_recall") - metric(candidate, "min_vad_recall"), MAX_RECALL_DROP),
        ("min_vad_f1", metric(baseline, "min_vad_f1") - metric(candidate, "min_vad_f1"), MAX_F1_DROP),
        ("max_vad_false_positive_rate", metric(candidate, "max_vad_false_positive_rate") - metric(baseline, "max_vad_false_positive_rate"), MAX_FPR_RISE),
    )
    for name, regression, allowed in checks:
        if regression > allowed + 1.0e-12:
            violations.append({
                "gate": "aggregate_regression",
                "metric": name,
                "regression": regression,
                "allowed": allowed,
            })
    return violations


def select_development(development: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    baseline = evaluate_synthetic(development, BASELINE_HANGOVER)
    ranking = []
    for hangover in HANGOVER_CANDIDATES:
        report = evaluate_synthetic(development, hangover)
        violations = synthetic_regressions(baseline, report)
        ranking.append({
            "candidate_id": f"hangover={hangover}",
            "hangover_frames": hangover,
            "score": synthetic_score(baseline, report),
            "validation_result": report["validation_result"],
            "summary": report["summary"],
            "regression_violations": violations,
        })
    eligible = [
        item for item in ranking
        if item["hangover_frames"] != BASELINE_HANGOVER
        and item["validation_result"] == "PASS"
        and not item["regression_violations"]
        and float(item["score"]) >= MIN_DEV_SCORE
    ]
    eligible.sort(key=lambda item: (
        -float(item["score"]),
        abs(int(item["hangover_frames"]) - BASELINE_HANGOVER),
    ))
    selected = eligible[0] if eligible else next(item for item in ranking if item["hangover_frames"] == BASELINE_HANGOVER)
    ranking.sort(key=lambda item: (-float(item["score"]), abs(int(item["hangover_frames"]) - BASELINE_HANGOVER)))
    return selected, ranking


def partition_identity(partition: dict[str, Any]) -> dict[str, Any]:
    return {key: partition[key] for key in ("corpus_id", "generator_seed", "corpus_sha256")}


def collect_ami(processor: Path, lock_path: Path) -> dict[str, Any]:
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    ami_eval.validate_lock(lock)
    intervals, _ = ami_eval.load_annotations(lock)
    audio_url = discovery.hf_resolve_url(str(lock["audio"]["path"]))
    windows = []
    with tempfile.TemporaryDirectory(prefix="ap-ami-hangover-") as temporary:
        root = Path(temporary)
        corpus_path = root / "corpus.json"
        corpus_path.write_text('{"schema_version":1,"cases":[]}\n', encoding="utf-8")
        for window in lock["windows"]:
            pcm = ami_eval.request_exact_range(audio_url, int(window["start_byte"]), int(window["end_byte"]))
            digest = ami_eval.sha256_bytes(pcm)
            if digest != window["sha256"]:
                raise ValueError(f"AMI window hash drifted: {window['window_id']}")
            pcm_path = root / f"{window['window_id']}.pcm"
            pcm_path.write_bytes(pcm)
            labels = ami_eval.labels_for_window(intervals, float(window["start_s"]), float(window["end_s"]))
            case = {
                "case_id": window["window_id"],
                "scenario": "ami-external-timing-real-speech",
                "sample_rate_hz": 16000,
                "mic_channels": 1,
                "mic_audio": pcm_path.name,
                "render_audio": None,
                "processor_profile": "ns-isolated",
                "control": {},
            }
            with tempfile.TemporaryDirectory(prefix="ap-ami-hangover-run-") as work:
                _, trace, _ = engine.invoke(processor, case, corpus_path, Path(work))
            probabilities = [float(row.get("vad_probability", 0.0)) for row in trace]
            count = min(len(labels), len(probabilities))
            if count < 1900:
                raise ValueError(f"insufficient AMI trace frames: {window['window_id']} count={count}")
            windows.append({
                "window_id": window["window_id"],
                "activity_fraction": sum(labels[:count]) / count,
                "audio_sha256": digest,
                "labels": labels[:count],
                "probabilities": probabilities[:count],
            })
    return {
        "meeting": lock["dataset"]["meeting"],
        "license": lock["dataset"]["license"],
        "transport_revision": lock["transport_mirror"]["revision"],
        "lock_sha256": engine.sha256_file(lock_path),
        "windows": windows,
    }


def ami_report(ami: dict[str, Any], hangover_frames: int) -> dict[str, Any]:
    window_reports = []
    aggregate_labels: list[int] = []
    aggregate_trace: list[dict[str, int]] = []
    for window in ami["windows"]:
        trace = decision_trace(window["probabilities"], NS_THRESHOLD, hangover_frames)
        stats = engine.vad_stats(window["labels"], trace)
        aggregate_labels.extend(window["labels"])
        aggregate_trace.extend(trace)
        window_reports.append({
            "window_id": window["window_id"],
            "activity_fraction": window["activity_fraction"],
            "metrics": stats,
        })
    return {
        "hangover_frames": hangover_frames,
        "aggregate": engine.vad_stats(aggregate_labels, aggregate_trace),
        "windows": window_reports,
    }


def stat(report: dict[str, Any], name: str) -> float:
    value = report["aggregate"].get(name)
    if value is None:
        raise ValueError(f"missing AMI metric: {name}")
    return float(value)


def ami_score(baseline: dict[str, Any], candidate: dict[str, Any]) -> float:
    recall_delta = stat(candidate, "recall") - stat(baseline, "recall")
    f1_delta = stat(candidate, "f1") - stat(baseline, "f1")
    fpr_improvement = stat(baseline, "false_positive_rate") - stat(candidate, "false_positive_rate")
    return 0.75 * recall_delta + 1.0 * f1_delta + 2.0 * fpr_improvement


def ami_regressions(baseline: dict[str, Any], candidate: dict[str, Any]) -> list[dict[str, Any]]:
    violations: list[dict[str, Any]] = []
    fpr_improvement = stat(baseline, "false_positive_rate") - stat(candidate, "false_positive_rate")
    recall_drop = stat(baseline, "recall") - stat(candidate, "recall")
    f1_drop = stat(baseline, "f1") - stat(candidate, "f1")
    if fpr_improvement < AMI_MIN_FPR_IMPROVEMENT - 1.0e-12:
        violations.append({"gate": "ami_aggregate_fpr_improvement", "actual": fpr_improvement, "required": AMI_MIN_FPR_IMPROVEMENT})
    if recall_drop > AMI_MAX_RECALL_DROP + 1.0e-12:
        violations.append({"gate": "ami_aggregate_recall_drop", "actual": recall_drop, "allowed": AMI_MAX_RECALL_DROP})
    if f1_drop > AMI_MAX_F1_DROP + 1.0e-12:
        violations.append({"gate": "ami_aggregate_f1_drop", "actual": f1_drop, "allowed": AMI_MAX_F1_DROP})

    baseline_by_id = {item["window_id"]: item for item in baseline["windows"]}
    for item in candidate["windows"]:
        base = baseline_by_id[item["window_id"]]["metrics"]
        cand = item["metrics"]
        recall_drop_window = float(base["recall"]) - float(cand["recall"])
        f1_drop_window = float(base["f1"]) - float(cand["f1"])
        fpr_rise_window = float(cand["false_positive_rate"]) - float(base["false_positive_rate"])
        if recall_drop_window > AMI_WINDOW_MAX_RECALL_DROP + 1.0e-12:
            violations.append({"gate": "ami_window_recall_drop", "window_id": item["window_id"], "actual": recall_drop_window, "allowed": AMI_WINDOW_MAX_RECALL_DROP})
        if f1_drop_window > AMI_WINDOW_MAX_F1_DROP + 1.0e-12:
            violations.append({"gate": "ami_window_f1_drop", "window_id": item["window_id"], "actual": f1_drop_window, "allowed": AMI_WINDOW_MAX_F1_DROP})
        if fpr_rise_window > AMI_WINDOW_MAX_FPR_RISE + 1.0e-12:
            violations.append({"gate": "ami_window_fpr_rise", "window_id": item["window_id"], "actual": fpr_rise_window, "allowed": AMI_WINDOW_MAX_FPR_RISE})
        if item["window_id"] == "ES2003a-w2":
            improvement = float(base["false_positive_rate"]) - float(cand["false_positive_rate"])
            if improvement < AMI_W2_MIN_FPR_IMPROVEMENT - 1.0e-12:
                violations.append({"gate": "ami_low_activity_fpr_improvement", "window_id": item["window_id"], "actual": improvement, "required": AMI_W2_MIN_FPR_IMPROVEMENT})
    return violations


def run(processor: Path, development_path: Path, validation_path: Path, shadow_path: Path,
        ami_lock: Path, output: Path) -> dict[str, Any]:
    development = selector.collect_partition(processor, development_path)
    validation = selector.collect_partition(processor, validation_path)
    shadow = selector.collect_partition(processor, shadow_path)
    seeds = [development["generator_seed"], validation["generator_seed"], shadow["generator_seed"]]
    if None in seeds or len(set(seeds)) != 3:
        raise ValueError("development/validation/shadow must use three distinct seeds")

    selected, ranking = select_development(development)
    baseline_dev = evaluate_synthetic(development, BASELINE_HANGOVER)
    candidate_dev = evaluate_synthetic(development, int(selected["hangover_frames"]))
    val_baseline = evaluate_synthetic(validation, BASELINE_HANGOVER)
    val_candidate = evaluate_synthetic(validation, int(selected["hangover_frames"]))
    shadow_baseline = evaluate_synthetic(shadow, BASELINE_HANGOVER)
    shadow_candidate = evaluate_synthetic(shadow, int(selected["hangover_frames"]))
    val_violations = synthetic_regressions(val_baseline, val_candidate)
    shadow_violations = synthetic_regressions(shadow_baseline, shadow_candidate)
    val_score = synthetic_score(val_baseline, val_candidate)
    shadow_score = synthetic_score(shadow_baseline, shadow_candidate)

    ami = collect_ami(processor, ami_lock)
    ami_baseline = ami_report(ami, BASELINE_HANGOVER)
    ami_candidate = ami_report(ami, int(selected["hangover_frames"]))
    ami_violations = ami_regressions(ami_baseline, ami_candidate) if int(selected["hangover_frames"]) != BASELINE_HANGOVER else []
    real_score = ami_score(ami_baseline, ami_candidate)

    if int(selected["hangover_frames"]) == BASELINE_HANGOVER:
        decision = "KEEP_BASELINE"
    elif val_violations or shadow_violations or val_score < MIN_HOLDOUT_SCORE or shadow_score < MIN_HOLDOUT_SCORE or ami_violations:
        decision = "REJECT_CANDIDATE"
    else:
        decision = "RESEARCH_CANDIDATE"

    result = {
        "schema_version": 1,
        "authority": "non-shipping-vad-hangover-counterfactual",
        "decision": decision,
        "scope": {
            "shared_hangover_only": True,
            "local_threshold": LOCAL_THRESHOLD,
            "ns_threshold": NS_THRESHOLD,
            "probability_generation_unchanged": True,
            "noise_adaptation_unchanged": True,
            "ns_fusion_unchanged": True,
            "shipping_source_unchanged": True,
        },
        "baseline": {"hangover_frames": BASELINE_HANGOVER},
        "selected": selected,
        "development": {
            "identity": partition_identity(development),
            "baseline": baseline_dev,
            "candidate": candidate_dev,
            "ranking": ranking,
        },
        "validation": {
            "identity": partition_identity(validation),
            "baseline": val_baseline,
            "candidate": val_candidate,
            "score": val_score,
            "regression_violations": val_violations,
        },
        "shadow": {
            "identity": partition_identity(shadow),
            "baseline": shadow_baseline,
            "candidate": shadow_candidate,
            "score": shadow_score,
            "regression_violations": shadow_violations,
        },
        "ami_holdout": {
            "identity": {
                "meeting": ami["meeting"],
                "license": ami["license"],
                "transport_revision": ami["transport_revision"],
                "lock_sha256": ami["lock_sha256"],
            },
            "baseline": ami_baseline,
            "candidate": ami_candidate,
            "score": real_score,
            "regression_violations": ami_violations,
            "authority": "research-external-timing-holdout",
        },
        "promotion_boundary": (
            "research selector only; any shipping hangover change requires a separate release-bearing source PR, "
            "canonical/hosted-real/target/HIL qualification, and stronger real SAD authority"
        ),
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result


def self_test() -> None:
    probabilities = [0.1, 0.8] + [0.1] * 10
    active2 = [row["vad_active"] for row in decision_trace(probabilities, 0.35, 2)]
    active8 = [row["vad_active"] for row in decision_trace(probabilities, 0.35, 8)]
    assert sum(active2) == 2
    assert sum(active8) == 8
    assert HANGOVER_CANDIDATES[-1] == BASELINE_HANGOVER
    assert LOCAL_THRESHOLD == 0.45 and NS_THRESHOLD == 0.35
    print("VAD hangover counterfactual self-test: OK")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--processor", type=Path)
    parser.add_argument("--development-corpus", type=Path)
    parser.add_argument("--validation-corpus", type=Path)
    parser.add_argument("--shadow-corpus", type=Path)
    parser.add_argument("--ami-lock", type=Path, default=Path("tests/validation/data/ami_vad_microset.lock.json"))
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
        args.ami_lock.resolve(),
        args.output.resolve(),
    )
    print(json.dumps({
        "decision": result["decision"],
        "selected": result["selected"],
        "validation_score": result["validation"]["score"],
        "shadow_score": result["shadow"]["score"],
        "ami_score": result["ami_holdout"]["score"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
