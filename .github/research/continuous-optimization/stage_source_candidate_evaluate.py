#!/usr/bin/env python3
"""Evaluate frozen VAD/AGC source candidates on fresh predeclared development data."""
from __future__ import annotations

import argparse
import json
import math
import sys
import tempfile
from pathlib import Path
from statistics import median
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "validation/tools"))
sys.path.insert(0, str(ROOT / "tests/validation"))
sys.path.insert(0, str(ROOT / ".github/research/continuous-optimization"))

import run_validation_engine as engine
import stage_profile_support
import agc_dynamics_diagnostic as agc_diag
import agc_stage_lane_v1 as agc_lane

STAGE_INVOKE = stage_profile_support.build_invoke(engine)

VAD_LOCAL_THRESHOLD = 0.45
VAD_NS_THRESHOLD = 0.35


def vad_expected_policy(probabilities: list[float], profile: str) -> list[int]:
    threshold = VAD_NS_THRESHOLD if profile == "ns-isolated" else VAD_LOCAL_THRESHOLD
    hold = 0
    out: list[int] = []
    for raw in probabilities:
        probability = float(raw)
        if not math.isfinite(probability):
            probability = 0.0
        if probability >= 0.70:
            hold = 10
        elif probability >= 0.50:
            hold = 8
        elif probability > threshold:
            hold = max(hold, 6)
        elif hold:
            hold -= 1
        out.append(1 if hold > 0 else 0)
    return out


def vad_allowed_expected(case: dict[str, Any]) -> dict[str, float]:
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


def collect_vad_case(processor: Path, corpus_path: Path, case: dict[str, Any]) -> dict[str, Any]:
    profile = str(case.get("processor_profile", "default"))
    if profile not in {"vad-isolated", "ns-isolated"} or not case.get("vad_labels"):
        raise ValueError(f"invalid VAD source-candidate case: {case.get('case_id')}")
    labels_path = engine.resolve(corpus_path, case["vad_labels"])
    if labels_path is None:
        raise ValueError("VAD labels required")
    labels = engine.load_labels(labels_path)
    with tempfile.TemporaryDirectory(prefix="ap-vad-source-candidate-") as temporary:
        _, trace, _ = STAGE_INVOKE(processor, case, corpus_path, Path(temporary))
    count = min(len(labels), len(trace))
    if count <= 0:
        raise ValueError(f"empty VAD trace: {case['case_id']}")
    return {
        "case_id": case["case_id"],
        "profile": profile,
        "labels": labels[:count],
        "probabilities": [float(row.get("vad_probability", 0.0)) for row in trace[:count]],
        "active": [int(row.get("vad_active", 0)) for row in trace[:count]],
        "expected": vad_allowed_expected(case),
    }


def collect_vad_partition(processor: Path, corpus_path: Path) -> dict[str, Any]:
    corpus = json.loads(corpus_path.read_text(encoding="utf-8"))
    cases = [
        collect_vad_case(processor, corpus_path, case)
        for case in corpus.get("cases", [])
        if case.get("processor_profile") in {"vad-isolated", "ns-isolated"}
        and case.get("vad_labels")
    ]
    profiles = {case["profile"] for case in cases}
    if profiles != {"vad-isolated", "ns-isolated"}:
        raise ValueError(f"candidate evaluation requires both VAD profiles: {sorted(profiles)}")
    return {
        "seed": corpus.get("generator", {}).get("seed"),
        "corpus_id": corpus.get("corpus_id"),
        "cases": cases,
    }


def vad_case_metrics(case: dict[str, Any]) -> dict[str, float | None]:
    stats = engine.vad_stats(case["labels"], [{"vad_active": value} for value in case["active"]])
    return {
        "vad_f1": stats["f1"],
        "vad_precision": stats["precision"],
        "vad_recall": stats["recall"],
        "vad_false_positive_rate": stats["false_positive_rate"],
        "vad_false_negative_rate": stats["false_negative_rate"],
    }


def vad_partition_summary(partition: dict[str, Any]) -> dict[str, Any]:
    rows = []
    positive: set[str] = set()
    for case in partition["cases"]:
        if any(case["labels"]):
            positive.add(case["case_id"])
        metrics = vad_case_metrics(case)
        violations = engine.threshold_violations(metrics, case["expected"])
        rows.append({
            "case_id": case["case_id"],
            "profile": case["profile"],
            "metrics": metrics,
            "violations": violations,
            "passed": not violations,
        })
    recalls = [float(row["metrics"]["vad_recall"]) for row in rows if row["case_id"] in positive]
    f1s = [float(row["metrics"]["vad_f1"]) for row in rows if row["case_id"] in positive]
    fprs = [float(row["metrics"]["vad_false_positive_rate"]) for row in rows]
    return {
        "validation_result": "PASS" if all(row["passed"] for row in rows) else "FAIL",
        "summary": {
            "pass_rate": sum(row["passed"] for row in rows) / max(1, len(rows)),
            "min_vad_recall": min(recalls),
            "min_vad_f1": min(f1s),
            "max_vad_false_positive_rate": max(fprs),
        },
        "cases": rows,
    }


def evaluate_vad(base_processor: Path, candidate_processor: Path,
                 corpora: list[Path], output: Path) -> dict[str, Any]:
    if len(corpora) != 3:
        raise ValueError("VAD source-candidate evaluation requires exactly three fresh corpora")
    partitions = []
    total_changed = 0
    total_probability_mismatch = 0
    total_policy_mismatch = 0
    for corpus in corpora:
        base = collect_vad_partition(base_processor, corpus)
        candidate = collect_vad_partition(candidate_processor, corpus)
        if [x["case_id"] for x in base["cases"]] != [x["case_id"] for x in candidate["cases"]]:
            raise ValueError("VAD base/candidate case identity mismatch")
        case_checks = []
        for b, c in zip(base["cases"], candidate["cases"]):
            if b["profile"] != c["profile"] or b["labels"] != c["labels"]:
                raise ValueError("VAD base/candidate case binding drift")
            if len(b["probabilities"]) != len(c["probabilities"]):
                raise ValueError("VAD probability trace length drift")
            prob_mismatch = sum(
                abs(x - y) > 1.0e-7
                for x, y in zip(b["probabilities"], c["probabilities"])
            )
            expected = vad_expected_policy(c["probabilities"], c["profile"])
            policy_mismatch = sum(x != y for x, y in zip(expected, c["active"]))
            changed = sum(x != y for x, y in zip(b["active"], c["active"]))
            total_probability_mismatch += prob_mismatch
            total_policy_mismatch += policy_mismatch
            total_changed += changed
            case_checks.append({
                "case_id": c["case_id"],
                "probability_mismatches": prob_mismatch,
                "policy_mismatches": policy_mismatch,
                "changed_active_frames_vs_base": changed,
            })
        base_summary = vad_partition_summary(base)
        cand_summary = vad_partition_summary(candidate)
        regression = []
        checks = (
            ("min_vad_recall", "drop", 0.03),
            ("min_vad_f1", "drop", 0.03),
            ("max_vad_false_positive_rate", "rise", 0.03),
        )
        for metric, kind, allowed in checks:
            b = float(base_summary["summary"][metric])
            c = float(cand_summary["summary"][metric])
            value = b - c if kind == "drop" else c - b
            if value > allowed + 1.0e-12:
                regression.append({
                    "metric": metric, "regression": value, "allowed": allowed,
                    "baseline": b, "candidate": c,
                })
        partitions.append({
            "seed": candidate["seed"],
            "base": base_summary["summary"],
            "candidate": cand_summary["summary"],
            "candidate_validation_result": cand_summary["validation_result"],
            "regression_violations": regression,
            "case_checks": case_checks,
        })
    violations = []
    if total_probability_mismatch:
        violations.append({"gate": "probability_generation_drift", "count": total_probability_mismatch})
    if total_policy_mismatch:
        violations.append({"gate": "candidate_policy_conformance", "count": total_policy_mismatch})
    if total_changed <= 0:
        violations.append({"gate": "candidate_behavior_not_exercised"})
    for partition in partitions:
        if partition["candidate_validation_result"] != "PASS":
            violations.append({"gate": "candidate_case_gates", "seed": partition["seed"]})
        if partition["regression_violations"]:
            violations.append({
                "gate": "candidate_regression",
                "seed": partition["seed"],
                "violations": partition["regression_violations"],
            })
    result = {
        "schema_version": 1,
        "authority": "source-candidate-evaluation-only",
        "candidate_id": "vad-confidence-tiered-hold-v1",
        "decision": "SOURCE_CANDIDATE_PASS" if not violations else "SOURCE_CANDIDATE_REJECT",
        "fresh_seeds": [item["seed"] for item in partitions],
        "total_changed_active_frames_vs_base": total_changed,
        "total_probability_mismatches": total_probability_mismatch,
        "total_policy_mismatches": total_policy_mismatch,
        "partitions": partitions,
        "violations": violations,
        "shipping_authority": False,
        "automatic_main_mutation": False,
        "independent_confirmation_required_after_pass": True,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result


def agc_case_by_id(report: dict[str, Any], case_id: str) -> dict[str, Any]:
    return next(case for case in report["cases"] if case["case_id"] == case_id)


def evaluate_agc(base_probe: Path, candidate_probe: Path,
                 corpora: list[Path], output: Path) -> dict[str, Any]:
    if len(corpora) != 3:
        raise ValueError("AGC source-candidate evaluation requires exactly three fresh corpora")
    partitions = []
    conformance_gain_max = 0.0
    conformance_rms_max = 0.0
    conformance_peak_max = 0.0
    improvements = []
    violations = []
    for corpus in corpora:
        baseline = agc_diag.diagnose(base_probe, corpus, -20.0, -2.0)
        candidate = agc_diag.diagnose(candidate_probe, corpus, -20.0, -2.0)
        if baseline["validation_result"] != "PASS":
            raise ValueError(f"AGC shipping baseline failed fresh corpus: {corpus}")
        if candidate["validation_result"] != "PASS":
            violations.append({"gate": "candidate_dynamic_gates", "corpus": str(corpus)})

        base_step = agc_case_by_id(baseline, "agc-level-step")
        cand_step = agc_case_by_id(candidate, "agc-level-step")
        base_hot_to_low = float(base_step["hot_to_low_settle_frames"])
        cand_hot_to_low = float(cand_step["hot_to_low_settle_frames"])
        improvement = base_hot_to_low - cand_hot_to_low
        improvements.append(improvement)
        low_to_hot_regression = (
            float(cand_step["low_to_hot_settle_frames"])
            - float(base_step["low_to_hot_settle_frames"])
        )
        slew_regression = (
            float(cand_step["p95_abs_gain_step_db"])
            - float(base_step["p95_abs_gain_step_db"])
        )
        peak_regression = max(
            float(case_c["max_output_peak_dbfs"]) - float(case_b["max_output_peak_dbfs"])
            for case_b, case_c in zip(baseline["cases"], candidate["cases"])
        )
        if low_to_hot_regression > 5.0:
            violations.append({
                "gate": "low_to_hot_regression",
                "corpus": str(corpus),
                "actual": low_to_hot_regression,
                "allowed": 5.0,
            })
        if slew_regression > 0.15:
            violations.append({
                "gate": "slew_regression",
                "corpus": str(corpus),
                "actual": slew_regression,
                "allowed": 0.15,
            })
        if peak_regression > 0.20:
            violations.append({
                "gate": "peak_regression",
                "corpus": str(corpus),
                "actual": peak_regression,
                "allowed": 0.20,
            })

        corpus_json = json.loads(corpus.read_text(encoding="utf-8"))
        case_conformance = []
        for case in corpus_json["cases"]:
            if case.get("processor_profile") != "agc-isolated":
                continue
            pcm = engine.resolve(corpus, case["mic_audio"])
            if pcm is None:
                raise ValueError("AGC mic audio missing")
            actual = agc_diag.run_probe(candidate_probe, pcm, -20.0, -2.0)
            samples = agc_lane.read_pcm(pcm)
            expected = agc_lane.simulate(
                samples, -20.0, -2.0, "error-adaptive-release", 0.05
            )
            if len(actual) != len(expected):
                raise ValueError("AGC emulator/source trace length mismatch")
            gain_delta = max(
                abs(float(a["gain_db"]) - float(e["gain_db"]))
                for a, e in zip(actual, expected)
            )
            rms_delta = max(
                abs(float(a["output_rms_dbfs"]) - float(e["output_rms_dbfs"]))
                for a, e in zip(actual, expected)
            )
            peak_delta = max(
                abs(float(a["output_peak_dbfs"]) - float(e["output_peak_dbfs"]))
                for a, e in zip(actual, expected)
            )
            conformance_gain_max = max(conformance_gain_max, gain_delta)
            conformance_rms_max = max(conformance_rms_max, rms_delta)
            conformance_peak_max = max(conformance_peak_max, peak_delta)
            case_conformance.append({
                "case_id": case["case_id"],
                "max_gain_db_delta": gain_delta,
                "max_output_rms_db_delta": rms_delta,
                "max_output_peak_db_delta": peak_delta,
            })

        partitions.append({
            "corpus": str(corpus),
            "baseline_validation_result": baseline["validation_result"],
            "candidate_validation_result": candidate["validation_result"],
            "hot_to_low_improvement_frames": improvement,
            "low_to_hot_regression_frames": low_to_hot_regression,
            "slew_regression_db": slew_regression,
            "peak_regression_db": peak_regression,
            "candidate_emulator_conformance": case_conformance,
        })

    median_improvement = median(improvements)
    if median_improvement < 20.0:
        violations.append({
            "gate": "median_hot_to_low_improvement_frames",
            "actual": median_improvement,
            "expected_min": 20.0,
        })
    for metric, value in (
        ("max_gain_db_delta", conformance_gain_max),
        ("max_output_rms_db_delta", conformance_rms_max),
        ("max_output_peak_db_delta", conformance_peak_max),
    ):
        if value > 0.03:
            violations.append({
                "gate": "candidate_emulator_conformance",
                "metric": metric,
                "actual": value,
                "expected_max": 0.03,
            })
    result = {
        "schema_version": 1,
        "authority": "source-candidate-evaluation-only",
        "candidate_id": "agc-error-adaptive-release-v1",
        "decision": "SOURCE_CANDIDATE_PASS" if not violations else "SOURCE_CANDIDATE_REJECT",
        "fresh_corpora": [str(path) for path in corpora],
        "median_hot_to_low_improvement_frames": median_improvement,
        "emulator_conformance": {
            "max_gain_db_delta": conformance_gain_max,
            "max_output_rms_db_delta": conformance_rms_max,
            "max_output_peak_db_delta": conformance_peak_max,
        },
        "partitions": partitions,
        "violations": violations,
        "shipping_authority": False,
        "automatic_main_mutation": False,
        "independent_confirmation_required_after_pass": True,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result


def self_test() -> None:
    probabilities = [0.1, 0.8] + [0.1] * 12
    trace = vad_expected_policy(probabilities, "vad-isolated")
    assert trace[1] == 1 and trace[10] == 1 and trace[11] == 0
    ns_trace = vad_expected_policy([0.1, 0.4] + [0.1] * 8, "ns-isolated")
    assert ns_trace[1] == 1
    assert len(ns_trace) == 10
    print("stage source candidate evaluator self-test: OK")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--candidate", choices=("vad", "agc"))
    parser.add_argument("--base-processor", type=Path)
    parser.add_argument("--candidate-processor", type=Path)
    parser.add_argument("--base-probe", type=Path)
    parser.add_argument("--candidate-probe", type=Path)
    parser.add_argument("--corpus", action="append", type=Path, default=[])
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    if args.candidate is None or args.output is None:
        parser.error("--candidate and --output are required")
    corpora = [path.resolve() for path in args.corpus]
    if args.candidate == "vad":
        if args.base_processor is None or args.candidate_processor is None:
            parser.error("VAD requires --base-processor and --candidate-processor")
        result = evaluate_vad(
            args.base_processor.resolve(), args.candidate_processor.resolve(),
            corpora, args.output.resolve(),
        )
    else:
        if args.base_probe is None or args.candidate_probe is None:
            parser.error("AGC requires --base-probe and --candidate-probe")
        result = evaluate_agc(
            args.base_probe.resolve(), args.candidate_probe.resolve(),
            corpora, args.output.resolve(),
        )
    print(json.dumps({
        "candidate_id": result["candidate_id"],
        "decision": result["decision"],
        "violations": len(result["violations"]),
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
