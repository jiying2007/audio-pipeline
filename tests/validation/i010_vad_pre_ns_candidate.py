#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import math
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "validation" / "tools"))

import run_validation_engine as engine  # type: ignore

CANDIDATE_ID = "vad-pre-ns-local-observation-v1"
PROB_EPS = 1.0e-7
DEFAULT_NS_FLOOR = 0.12
STRESS_NS_FLOOR = 0.05
ALLOWED_EXPECTED = {
    "min_vad_f1",
    "min_vad_precision",
    "min_vad_recall",
    "max_vad_false_positive_rate",
    "max_vad_false_negative_rate",
}


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def resolve(corpus_path: Path, raw: str | None) -> Path | None:
    return engine.resolve(corpus_path, raw)


def allowed_expected(case: dict[str, Any]) -> dict[str, float]:
    return {
        key: float(value)
        for key, value in case.get("expected", {}).items()
        if key in ALLOWED_EXPECTED
    }


def run_case(processor: Path, corpus_path: Path, case: dict[str, Any],
             work: Path, ns_floor: float | None = None) -> dict[str, Any]:
    profile = str(case.get("processor_profile", "default"))
    if profile not in {"vad-isolated", "ns-isolated"}:
        raise ValueError(f"unsupported I010 VAD case profile: {profile}")
    if case.get("render_audio") is not None:
        raise ValueError("I010 VAD candidate cases must remain capture-only")
    mic_path = resolve(corpus_path, case.get("mic_audio"))
    labels_path = resolve(corpus_path, case.get("vad_labels"))
    if mic_path is None or labels_path is None:
        raise ValueError(f"missing mic/labels: {case.get('case_id')}")
    rate = int(case["sample_rate_hz"])
    channels = int(case["mic_channels"])
    staged, staged_raw = engine.stage_audio(
        mic_path, rate, channels, work, "mic.pcm"
    )
    output_path = work / "out.pcm"
    metrics_path = work / "metrics.jsonl"
    command = [
        str(processor),
        "--sample-rate", str(rate),
        "--mic-channels", str(channels),
        "--metrics-jsonl", str(metrics_path),
        "--capture-profile", profile,
    ]
    if ns_floor is not None:
        if profile != "ns-isolated":
            raise ValueError("NS floor stress is only valid for ns-isolated cases")
        command.extend(["--ns-floor", repr(float(ns_floor))])
    command.extend(["--capture-only", str(staged_raw), str(output_path)])
    subprocess.run(command, check=True)
    labels = engine.load_labels(labels_path)
    trace: list[dict[str, Any]] = []
    for number, line in enumerate(
        metrics_path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"invalid metrics JSONL {metrics_path}:{number}: {exc.msg}"
            ) from exc
        trace.append(row)
    count = min(len(labels), len(trace))
    if count <= 0:
        raise ValueError(f"empty VAD trace: {case['case_id']}")
    output = output_path.read_bytes()
    return {
        "case_id": case["case_id"],
        "profile": profile,
        "labels": labels[:count],
        "probabilities": [
            float(row.get("vad_probability", 0.0)) for row in trace[:count]
        ],
        "active": [int(row.get("vad_active", 0)) for row in trace[:count]],
        "expected": allowed_expected(case),
        "output_sha256": hashlib.sha256(output).hexdigest(),
        "staged_input_sha256": hashlib.sha256(staged_raw.read_bytes()).hexdigest(),
        "staged_samples": len(staged),
    }


def vad_metrics(row: dict[str, Any]) -> dict[str, float]:
    stats = engine.vad_stats(
        row["labels"],
        [{"vad_active": value} for value in row["active"]],
    )
    return {
        "vad_f1": float(stats["f1"]),
        "vad_precision": float(stats["precision"]),
        "vad_recall": float(stats["recall"]),
        "vad_false_positive_rate": float(stats["false_positive_rate"]),
        "vad_false_negative_rate": float(stats["false_negative_rate"]),
    }


def trace_diff(a: dict[str, Any], b: dict[str, Any]) -> dict[str, int | float]:
    if a["case_id"] != b["case_id"] or a["profile"] != b["profile"]:
        raise ValueError("trace identity mismatch")
    if a["labels"] != b["labels"]:
        raise ValueError("trace label mismatch")
    if len(a["probabilities"]) != len(b["probabilities"]):
        raise ValueError("trace length mismatch")
    prob = [
        abs(float(x) - float(y))
        for x, y in zip(a["probabilities"], b["probabilities"])
    ]
    return {
        "probability_mismatch_frames": sum(value > PROB_EPS for value in prob),
        "max_probability_delta": max(prob, default=0.0),
        "active_mismatch_frames": sum(
            int(x) != int(y) for x, y in zip(a["active"], b["active"])
        ),
    }


def partition_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    case_rows = []
    recalls: list[float] = []
    f1s: list[float] = []
    fprs: list[float] = []
    for row in rows:
        metrics = vad_metrics(row)
        violations = engine.threshold_violations(metrics, row["expected"])
        if any(row["labels"]):
            recalls.append(metrics["vad_recall"])
            f1s.append(metrics["vad_f1"])
        fprs.append(metrics["vad_false_positive_rate"])
        case_rows.append({
            "case_id": row["case_id"],
            "profile": row["profile"],
            "metrics": metrics,
            "violations": violations,
            "passed": not violations,
        })
    return {
        "validation_result": "PASS" if all(x["passed"] for x in case_rows) else "FAIL",
        "summary": {
            "pass_rate": sum(bool(x["passed"]) for x in case_rows) / max(1, len(case_rows)),
            "min_vad_recall": min(recalls),
            "min_vad_f1": min(f1s),
            "max_vad_false_positive_rate": max(fprs),
        },
        "cases": case_rows,
    }


def compare_summary(base: dict[str, Any], candidate: dict[str, Any]) -> list[dict[str, Any]]:
    checks = (
        ("min_vad_recall", "drop", 0.03),
        ("min_vad_f1", "drop", 0.03),
        ("max_vad_false_positive_rate", "rise", 0.03),
    )
    violations = []
    for metric, kind, allowed in checks:
        b = float(base["summary"][metric])
        c = float(candidate["summary"][metric])
        regression = b - c if kind == "drop" else c - b
        if regression > allowed + 1.0e-12:
            violations.append({
                "gate": "candidate_regression",
                "metric": metric,
                "baseline": b,
                "candidate": c,
                "regression": regression,
                "allowed": allowed,
            })
    return violations


def evaluate(base_processor: Path, candidate_processor: Path,
             corpora: list[Path], output: Path) -> dict[str, Any]:
    if len(corpora) != 3:
        raise ValueError("I010 source candidate requires exactly three locked corpora")

    partitions = []
    violations: list[dict[str, Any]] = []
    baseline_floor_sensitivity_frames = 0
    candidate_floor_sensitivity_frames = 0
    candidate_changed_frames = 0
    vad_isolated_identity_mismatches = 0
    audio_output_mismatches = 0

    for corpus_path in corpora:
        corpus = json.loads(corpus_path.read_text(encoding="utf-8"))
        cases = [
            case for case in corpus.get("cases", [])
            if case.get("processor_profile") in {"vad-isolated", "ns-isolated"}
            and case.get("vad_labels")
        ]
        profiles = {str(case["processor_profile"]) for case in cases}
        if profiles != {"vad-isolated", "ns-isolated"}:
            raise ValueError(f"locked corpus missing VAD profiles: {corpus_path}")

        base_rows = []
        candidate_rows = []
        checks = []
        for index, case in enumerate(cases):
            with tempfile.TemporaryDirectory(prefix=f"ap-i010-base-{index}-") as tmp:
                base_default = run_case(
                    base_processor, corpus_path, case, Path(tmp), None
                )
            with tempfile.TemporaryDirectory(prefix=f"ap-i010-cand-{index}-") as tmp:
                cand_default = run_case(
                    candidate_processor, corpus_path, case, Path(tmp), None
                )

            base_rows.append(base_default)
            candidate_rows.append(cand_default)
            base_candidate = trace_diff(base_default, cand_default)
            candidate_changed_frames += (
                int(base_candidate["probability_mismatch_frames"]) +
                int(base_candidate["active_mismatch_frames"])
            )
            if base_default["output_sha256"] != cand_default["output_sha256"]:
                audio_output_mismatches += 1

            row = {
                "case_id": case["case_id"],
                "profile": case["processor_profile"],
                "base_vs_candidate": base_candidate,
                "base_output_sha256": base_default["output_sha256"],
                "candidate_output_sha256": cand_default["output_sha256"],
            }

            if case["processor_profile"] == "vad-isolated":
                mismatch = (
                    int(base_candidate["probability_mismatch_frames"]) +
                    int(base_candidate["active_mismatch_frames"])
                )
                vad_isolated_identity_mismatches += mismatch
            else:
                with tempfile.TemporaryDirectory(prefix=f"ap-i010-base-stress-{index}-") as tmp:
                    base_stress = run_case(
                        base_processor, corpus_path, case, Path(tmp), STRESS_NS_FLOOR
                    )
                with tempfile.TemporaryDirectory(prefix=f"ap-i010-cand-stress-{index}-") as tmp:
                    cand_stress = run_case(
                        candidate_processor, corpus_path, case, Path(tmp), STRESS_NS_FLOOR
                    )
                base_floor = trace_diff(base_default, base_stress)
                cand_floor = trace_diff(cand_default, cand_stress)
                baseline_floor_sensitivity_frames += (
                    int(base_floor["probability_mismatch_frames"]) +
                    int(base_floor["active_mismatch_frames"])
                )
                candidate_floor_sensitivity_frames += (
                    int(cand_floor["probability_mismatch_frames"]) +
                    int(cand_floor["active_mismatch_frames"])
                )
                row["baseline_floor_sensitivity"] = base_floor
                row["candidate_floor_sensitivity"] = cand_floor
            checks.append(row)

        base_summary = partition_summary(base_rows)
        candidate_summary = partition_summary(candidate_rows)
        regression = compare_summary(base_summary, candidate_summary)
        seed = int(corpus.get("generator", {}).get("seed"))
        if base_summary["validation_result"] != "PASS":
            violations.append({
                "gate": "locked_baseline_not_valid",
                "seed": seed,
            })
        if candidate_summary["validation_result"] != "PASS":
            violations.append({
                "gate": "candidate_absolute_case_gates",
                "seed": seed,
                "cases": [
                    row for row in candidate_summary["cases"]
                    if row["violations"]
                ],
            })
        for item in regression:
            violations.append({"seed": seed, **item})
        partitions.append({
            "seed": seed,
            "corpus_id": corpus.get("corpus_id"),
            "corpus_sha256": sha256_file(corpus_path),
            "baseline": base_summary,
            "candidate": candidate_summary,
            "regression_violations": regression,
            "trace_checks": checks,
        })

    if vad_isolated_identity_mismatches:
        violations.append({
            "gate": "vad_isolated_identity_drift",
            "mismatch_frames": vad_isolated_identity_mismatches,
        })
    if audio_output_mismatches:
        violations.append({
            "gate": "audio_output_changed",
            "cases": audio_output_mismatches,
        })
    if baseline_floor_sensitivity_frames <= 0:
        violations.append({"gate": "baseline_floor_sensitivity_not_exercised"})
    if candidate_floor_sensitivity_frames > 0:
        violations.append({
            "gate": "candidate_floor_invariance",
            "mismatch_frames": candidate_floor_sensitivity_frames,
        })
    if candidate_changed_frames <= 0:
        violations.append({"gate": "candidate_behavior_not_exercised"})

    result = {
        "schema_version": 1,
        "authority": "source-candidate-evaluation-only",
        "candidate_id": CANDIDATE_ID,
        "decision": "SOURCE_CANDIDATE_PASS" if not violations else "SOURCE_CANDIDATE_REJECT",
        "default_ns_floor": DEFAULT_NS_FLOOR,
        "diagnostic_stress_ns_floor": STRESS_NS_FLOOR,
        "locked_seeds": [row["seed"] for row in partitions],
        "baseline_floor_sensitivity_frames": baseline_floor_sensitivity_frames,
        "candidate_floor_sensitivity_frames": candidate_floor_sensitivity_frames,
        "candidate_changed_frames_vs_base": candidate_changed_frames,
        "vad_isolated_identity_mismatches": vad_isolated_identity_mismatches,
        "audio_output_mismatches": audio_output_mismatches,
        "partitions": partitions,
        "violations": violations,
        "candidate_budget_consumed": True,
        "shipping_authority": False,
        "source_merge_authorized": False,
        "automatic_main_mutation": False,
        "independent_confirmation_required_after_pass": True,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result


def self_test() -> None:
    base = {"summary": {
        "min_vad_recall": 0.8,
        "min_vad_f1": 0.7,
        "max_vad_false_positive_rate": 0.2,
    }}
    good = {"summary": {
        "min_vad_recall": 0.79,
        "min_vad_f1": 0.69,
        "max_vad_false_positive_rate": 0.21,
    }}
    bad = {"summary": {
        "min_vad_recall": 0.75,
        "min_vad_f1": 0.69,
        "max_vad_false_positive_rate": 0.21,
    }}
    assert not compare_summary(base, good)
    assert compare_summary(base, bad)[0]["metric"] == "min_vad_recall"
    a = {
        "case_id": "x", "profile": "ns-isolated",
        "labels": [0, 1], "probabilities": [0.1, 0.5], "active": [0, 1],
    }
    b = {
        "case_id": "x", "profile": "ns-isolated",
        "labels": [0, 1], "probabilities": [0.1, 0.5], "active": [0, 1],
    }
    assert trace_diff(a, b)["active_mismatch_frames"] == 0
    b["probabilities"][1] = 0.6
    assert trace_diff(a, b)["probability_mismatch_frames"] == 1
    print("I010 pre-NS VAD source-candidate evaluator self-test: OK")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--base-processor", type=Path)
    parser.add_argument("--candidate-processor", type=Path)
    parser.add_argument("--corpus", action="append", type=Path, default=[])
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    if not args.base_processor or not args.candidate_processor or not args.output:
        parser.error("--base-processor, --candidate-processor and --output are required")
    result = evaluate(
        args.base_processor.resolve(),
        args.candidate_processor.resolve(),
        [path.resolve() for path in args.corpus],
        args.output.resolve(),
    )
    print(json.dumps({
        "candidate_id": result["candidate_id"],
        "decision": result["decision"],
        "violations": len(result["violations"]),
        "baseline_floor_sensitivity_frames": result["baseline_floor_sensitivity_frames"],
        "candidate_floor_sensitivity_frames": result["candidate_floor_sensitivity_frames"],
        "candidate_changed_frames_vs_base": result["candidate_changed_frames_vs_base"],
    }, sort_keys=True))
    return 0 if result["decision"] == "SOURCE_CANDIDATE_PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
