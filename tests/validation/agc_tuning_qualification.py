#!/usr/bin/env python3
"""Finalize generic AGC tuning with independent dynamic validation/shadow replay.

This tool does not search parameters or implement AGC metrics. It reuses the
existing AGC dynamics diagnostic as a second-stage qualification gate so a
candidate selected by canonical steady-state metrics cannot be promoted as an
ACOUSTIC_CANDIDATE when level-step/transient behavior regresses.
"""

from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path

import agc_dynamics_diagnostic as dynamics


def tuning_pair(raw: dict) -> tuple[float, float]:
    tuning = raw.get("tuning", raw)
    target = float(tuning["agc_target_dbfs"])
    limiter = float(tuning["limiter_dbfs"])
    if not -60.0 <= target <= -1.0:
        raise ValueError("agc_target_dbfs outside product bounds")
    if not -20.0 <= limiter <= -0.1:
        raise ValueError("limiter_dbfs outside product bounds")
    if target >= limiter:
        raise ValueError("agc_target_dbfs must be below limiter_dbfs")
    return target, limiter


def compact(report: dict) -> dict:
    level_step = next(
        (case for case in report.get("cases", []) if case.get("case_id") == "agc-level-step"),
        {},
    )
    steady_low = next(
        (case for case in report.get("cases", []) if case.get("case_id") == "agc-steady-low"),
        {},
    )
    steady_hot = next(
        (case for case in report.get("cases", []) if case.get("case_id") == "agc-steady-hot"),
        {},
    )
    return {
        "validation_result": report.get("validation_result"),
        "effective_tuning": report.get("effective_tuning"),
        "violations": report.get("violations", []),
        "steady_low_tail_output_rms_dbfs": steady_low.get("tail_output_rms_dbfs"),
        "steady_hot_tail_output_rms_dbfs": steady_hot.get("tail_output_rms_dbfs"),
        "low_to_hot_settle_frames": level_step.get("low_to_hot_settle_frames"),
        "hot_to_low_settle_frames": level_step.get("hot_to_low_settle_frames"),
        "level_step_gain_slew_p95_db": level_step.get("p95_abs_gain_step_db"),
    }


def qualify(iteration: dict, probe: Path, validation_corpus: Path,
            shadow_corpus: Path, output_dir: Path) -> dict:
    if iteration.get("authority") != "non-shipping-acoustic-iteration":
        raise ValueError("iteration authority is not eligible for AGC dynamic qualification")
    original = str(iteration.get("decision"))
    if original not in {"KEEP_BASELINE", "REJECT_CANDIDATE", "ACOUSTIC_CANDIDATE"}:
        raise ValueError(f"unknown iteration decision: {original}")

    baseline_target, baseline_limiter = tuning_pair(iteration["baseline"])
    selected_target, selected_limiter = tuning_pair(iteration["selected"])
    output_dir.mkdir(parents=True, exist_ok=True)

    reports: dict[str, dict[str, dict]] = {"validation": {}, "shadow": {}}
    corpora = {"validation": validation_corpus, "shadow": shadow_corpus}
    for partition, corpus in corpora.items():
        for role, target, limiter in (
            ("baseline", baseline_target, baseline_limiter),
            ("candidate", selected_target, selected_limiter),
        ):
            report = dynamics.diagnose(
                probe.resolve(), corpus.resolve(),
                target_override=target, limiter_override=limiter,
            )
            path = output_dir / f"{partition}-{role}.json"
            path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            reports[partition][role] = report

    baseline_pass = all(
        reports[partition]["baseline"]["validation_result"] == "PASS"
        for partition in reports
    )
    if not baseline_pass:
        raise RuntimeError("shipping baseline fails AGC dynamic validation/shadow qualification")

    candidate_pass = all(
        reports[partition]["candidate"]["validation_result"] == "PASS"
        for partition in reports
    )
    same_as_baseline = (
        abs(selected_target - baseline_target) <= 1.0e-12
        and abs(selected_limiter - baseline_limiter) <= 1.0e-12
    )
    if original == "KEEP_BASELINE" or same_as_baseline:
        final = "KEEP_BASELINE"
    elif original == "REJECT_CANDIDATE":
        final = "REJECT_CANDIDATE"
    else:
        final = "ACOUSTIC_CANDIDATE" if candidate_pass else "REJECT_CANDIDATE"

    result = {
        "schema_version": 1,
        "authority": "non-shipping-agc-dynamic-qualification",
        "original_decision": original,
        "decision": final,
        "baseline": {
            "agc_target_dbfs": baseline_target,
            "limiter_dbfs": baseline_limiter,
        },
        "selected": {
            "agc_target_dbfs": selected_target,
            "limiter_dbfs": selected_limiter,
        },
        "candidate_dynamic_pass": candidate_pass,
        "partitions": {
            partition: {
                role: compact(report)
                for role, report in roles.items()
            }
            for partition, roles in reports.items()
        },
        "promotion_boundary": (
            "dynamic validation/shadow qualification only; no shipping default mutation"
        ),
    }
    (output_dir / "agc-dynamic-qualification.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return result


def self_test() -> None:
    assert tuning_pair({"agc_target_dbfs": -20.0, "limiter_dbfs": -2.0}) == (-20.0, -2.0)
    for bad in (
        {"agc_target_dbfs": -0.5, "limiter_dbfs": -0.1},
        {"agc_target_dbfs": -2.0, "limiter_dbfs": -3.0},
    ):
        try:
            tuning_pair(bad)
        except ValueError:
            pass
        else:
            raise AssertionError("invalid AGC tuning must fail closed")
    report = {
        "validation_result": "PASS",
        "effective_tuning": {"agc_target_dbfs": -20.0, "limiter_dbfs": -2.0},
        "violations": [],
        "cases": [
            {"case_id": "agc-steady-low", "tail_output_rms_dbfs": -20.4},
            {"case_id": "agc-steady-hot", "tail_output_rms_dbfs": -20.1},
            {"case_id": "agc-level-step", "low_to_hot_settle_frames": 12,
             "hot_to_low_settle_frames": 80, "p95_abs_gain_step_db": 0.2},
        ],
    }
    summary = compact(report)
    assert summary["low_to_hot_settle_frames"] == 12
    assert summary["steady_low_tail_output_rms_dbfs"] == -20.4
    print("AGC dynamic tuning qualification self-test: OK")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--iteration-result", type=Path)
    parser.add_argument("--probe", type=Path)
    parser.add_argument("--validation-corpus", type=Path)
    parser.add_argument("--shadow-corpus", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    for name in ("iteration_result", "probe", "validation_corpus", "shadow_corpus", "output_dir"):
        if getattr(args, name) is None:
            parser.error(f"--{name.replace('_', '-')} is required")
    iteration = json.loads(args.iteration_result.read_text(encoding="utf-8"))
    result = qualify(
        iteration, args.probe, args.validation_corpus,
        args.shadow_corpus, args.output_dir,
    )
    print(json.dumps({
        "decision": result["decision"],
        "original_decision": result["original_decision"],
        "candidate_dynamic_pass": result["candidate_dynamic_pass"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
