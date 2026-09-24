#!/usr/bin/env python3
from __future__ import annotations

import argparse
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

REQUIRED_CASES = {"stage-ns-stationary", "stage-ns-nonstationary"}


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON object required: {path}")
    return value


def resolve(corpus_path: Path, raw: str | None) -> Path | None:
    return engine.resolve(corpus_path, raw)


def run_case(probe: Path, corpus_path: Path, case: dict[str, Any]) -> dict[str, Any]:
    mic = resolve(corpus_path, case.get("mic_audio"))
    labels = resolve(corpus_path, case.get("vad_labels"))
    if mic is None or labels is None:
        raise ValueError(f"missing I011 calibrated local-SNR input: {case.get('case_id')}")
    if int(case.get("sample_rate_hz", 0)) != 16000 or int(case.get("mic_channels", 0)) != 1:
        raise ValueError(f"I011 calibrated local-SNR requires 16 kHz mono: {case.get('case_id')}")

    with tempfile.TemporaryDirectory(prefix="ap-vad-cal-snr-") as tmp:
        work = Path(tmp)
        _, staged_raw = engine.stage_audio(mic, 16000, 1, work, "mic.pcm")
        output = work / "result.json"
        subprocess.run(
            [str(probe), str(staged_raw), str(labels), str(output)],
            check=True,
        )
        row = load_json(output)
    row["case_id"] = str(case["case_id"])
    row["profile"] = str(case.get("processor_profile", ""))
    return row


def derived(row: dict[str, Any]) -> dict[str, float]:
    speech = int(row["speech_frames"])
    noise = int(row["noise_frames"])
    if speech <= 0 or noise <= 0:
        raise ValueError("I011 calibrated local-SNR did not exercise speech/noise labels")
    return {
        "shipping_recall": int(row["speech_shipping_active"]) / speech,
        "counterfactual_recall": int(row["speech_counter_active"]) / speech,
        "shipping_false_positive_rate": int(row["noise_shipping_active"]) / noise,
        "counterfactual_false_positive_rate": int(row["noise_counter_active"]) / noise,
    }


def aggregate_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    total: dict[str, int | float] = {
        "frames": 0,
        "speech_frames": 0,
        "noise_frames": 0,
        "mirror_probability_mismatch_frames": 0,
        "mirror_active_mismatch_frames": 0,
        "floor_probability_mismatch_frames": 0,
        "floor_active_mismatch_frames": 0,
        "behavior_probability_diff_frames": 0,
        "behavior_active_diff_frames": 0,
        "speech_shipping_active": 0,
        "speech_counter_active": 0,
        "noise_shipping_active": 0,
        "noise_counter_active": 0,
        "lost_speech_frames": 0,
        "gained_speech_frames": 0,
        "max_mirror_probability_delta": 0.0,
        "max_floor_probability_delta": 0.0,
        "max_floor_noise_reference_delta_db": 0.0,
        "max_floor_upstream_probability_delta": 0.0,
        "max_shipping_counter_probability_delta": 0.0,
    }
    integer_keys = {
        key for key, value in total.items() if isinstance(value, int)
    }
    maximum_keys = set(total) - integer_keys
    ratio_min = math.inf
    ratio_max = -math.inf
    scale_offsets: list[float] = []
    for row in rows:
        for key in integer_keys:
            total[key] = int(total[key]) + int(row[key])
        for key in maximum_keys:
            total[key] = max(float(total[key]), float(row[key]))
        ratio_min = min(ratio_min, float(row["min_counter_ratio_db"]))
        ratio_max = max(ratio_max, float(row["max_counter_ratio_db"]))
        scale_offsets.append(float(row["scale_offset_db"]))
    total["min_counter_ratio_db"] = ratio_min
    total["max_counter_ratio_db"] = ratio_max
    total["scale_offset_db"] = scale_offsets[0]
    total.update(derived(total))
    return total


def evaluate(probe: Path, contract_path: Path, corpora: list[Path],
             output: Path) -> dict[str, Any]:
    contract = load_json(contract_path)
    expected_seeds = [
        int(seed) for seed in contract["fresh_diagnostic_authority"]["seeds"]
    ]
    if len(corpora) != len(expected_seeds):
        raise ValueError("corpus count must match preregistered calibrated local-SNR seeds")
    if contract["budget"] != {
        "candidate_limit": 0,
        "confirmation_limit": 0,
        "diagnostic_execution_limit": 1,
    }:
        raise ValueError("calibrated local-SNR budget drift")
    fixed = contract["fixed_counterfactual"]
    if any(
        fixed[key] is not False
        for key in ("threshold_changes", "hold_changes", "blend_changes",
                    "shipping_source_mutation", "public_api_mutation")
    ):
        raise ValueError("fixed counterfactual semantics drift")

    partitions: list[dict[str, Any]] = []
    input_violations: list[dict[str, Any]] = []
    regression_violations: list[dict[str, Any]] = []
    actual_seeds: list[int] = []
    expected_offset = float(fixed["calibrated_noise_reference"]["scale_offset_db"])
    gates = contract["diagnostic_gates"]

    for corpus_path in corpora:
        corpus = load_json(corpus_path)
        seed = int(corpus.get("generator", {}).get("seed", -1))
        actual_seeds.append(seed)
        selected = {
            str(case.get("case_id")): case
            for case in corpus.get("cases", [])
            if case.get("processor_profile") == "ns-isolated"
            and case.get("vad_labels")
            and case.get("render_audio") is None
            and str(case.get("case_id")) in REQUIRED_CASES
        }
        if set(selected) != REQUIRED_CASES:
            raise ValueError(
                f"missing calibrated local-SNR required cases seed={seed}: "
                f"{sorted(REQUIRED_CASES - set(selected))}"
            )
        cases = [
            run_case(probe, corpus_path, selected[case_id])
            for case_id in sorted(REQUIRED_CASES)
        ]
        summary = aggregate_rows(cases)
        if abs(float(summary["scale_offset_db"]) - expected_offset) > 1.0e-5:
            input_violations.append({
                "seed": seed,
                "gate": "scale_offset_identity",
                "actual": summary["scale_offset_db"],
                "expected": expected_offset,
            })
        if int(summary["mirror_probability_mismatch_frames"]) != 0 or            int(summary["mirror_active_mismatch_frames"]) != 0 or            float(summary["max_mirror_probability_delta"]) > float(
               gates["mirror_probability_tolerance"]
           ):
            input_violations.append({
                "seed": seed,
                "gate": "shipping_mirror_identity",
                "probability_mismatch_frames":
                    summary["mirror_probability_mismatch_frames"],
                "active_mismatch_frames": summary["mirror_active_mismatch_frames"],
                "max_probability_delta": summary["max_mirror_probability_delta"],
            })
        if int(summary["floor_probability_mismatch_frames"]) != 0 or            int(summary["floor_active_mismatch_frames"]) != 0 or            float(summary["max_floor_probability_delta"]) > float(
               gates["floor_probability_tolerance"]
           ) or            float(summary["max_floor_noise_reference_delta_db"]) > float(
               gates["max_floor_noise_reference_delta_db"]
           ) or            float(summary["max_floor_upstream_probability_delta"]) > float(
               gates["max_floor_upstream_probability_delta"]
           ):
            input_violations.append({
                "seed": seed,
                "gate": "counterfactual_floor_invariance",
                "probability_mismatch_frames":
                    summary["floor_probability_mismatch_frames"],
                "active_mismatch_frames": summary["floor_active_mismatch_frames"],
                "max_probability_delta": summary["max_floor_probability_delta"],
                "max_noise_reference_delta_db":
                    summary["max_floor_noise_reference_delta_db"],
                "max_upstream_probability_delta":
                    summary["max_floor_upstream_probability_delta"],
            })
        if int(summary["behavior_probability_diff_frames"]) <= 0 and            int(summary["behavior_active_diff_frames"]) <= 0:
            input_violations.append({
                "seed": seed,
                "gate": "counterfactual_behavior_not_exercised",
            })

        recall_drop = (
            float(summary["shipping_recall"]) -
            float(summary["counterfactual_recall"])
        )
        fpr_rise = (
            float(summary["counterfactual_false_positive_rate"]) -
            float(summary["shipping_false_positive_rate"])
        )
        if recall_drop > float(gates["max_partition_recall_drop"]) + 1.0e-12:
            regression_violations.append({
                "seed": seed,
                "gate": "partition_recall_drop",
                "shipping": summary["shipping_recall"],
                "counterfactual": summary["counterfactual_recall"],
                "actual_drop": recall_drop,
                "allowed": gates["max_partition_recall_drop"],
            })
        if fpr_rise > float(gates["max_partition_false_positive_rate_rise"]) + 1.0e-12:
            regression_violations.append({
                "seed": seed,
                "gate": "partition_false_positive_rate_rise",
                "shipping": summary["shipping_false_positive_rate"],
                "counterfactual": summary["counterfactual_false_positive_rate"],
                "actual_rise": fpr_rise,
                "allowed": gates["max_partition_false_positive_rate_rise"],
            })
        partitions.append({
            "seed": seed,
            "corpus_id": corpus.get("corpus_id"),
            "summary": summary,
            "cases": [
                {**row, "derived": derived(row)}
                for row in cases
            ],
            "recall_drop": recall_drop,
            "false_positive_rate_rise": fpr_rise,
        })

    if actual_seeds != expected_seeds:
        raise ValueError(
            f"calibrated local-SNR seed drift: actual={actual_seeds} "
            f"expected={expected_seeds}"
        )

    aggregate = aggregate_rows([
        {
            **part["summary"],
        }
        for part in partitions
    ])

    if input_violations:
        decision = "CALIBRATED_LOCAL_SNR_INPUT_INVALID_REVIEW_REQUIRED"
    elif regression_violations:
        decision = "CALIBRATED_LOCAL_SNR_REGRESSION_REVIEW_REQUIRED"
    else:
        decision = "CALIBRATED_LOCAL_SNR_FEASIBLE_REVIEW_REQUIRED"

    result = {
        "schema_version": 1,
        "diagnostic_id": contract["diagnostic_id"],
        "authority": contract["authority"],
        "source_base_sha": contract["source_base_sha"],
        "decision": decision,
        "fresh_seeds": actual_seeds,
        "partitions": partitions,
        "aggregate": aggregate,
        "input_violations": input_violations,
        "regression_violations": regression_violations,
        "candidate_budget_consumed": 0,
        "confirmation_budget_consumed": 0,
        "candidate_selected": False,
        "thresholds_tuned": False,
        "shipping_source_changed": False,
        "interpretation_rule": (
            "This fixed counterfactual tests only whether the calibrated pre-suppression "
            "NS noise reference can replace the adaptive VAD local ratio source while all "
            "existing shipping VAD constants remain unchanged. It cannot select a source "
            "candidate, tune thresholds, consume confirmation, or authorize shipping/HIL/PQ."
        ),
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return result


def self_test() -> None:
    row = {
        "frames": 100,
        "speech_frames": 40,
        "noise_frames": 60,
        "mirror_probability_mismatch_frames": 0,
        "mirror_active_mismatch_frames": 0,
        "floor_probability_mismatch_frames": 0,
        "floor_active_mismatch_frames": 0,
        "behavior_probability_diff_frames": 10,
        "behavior_active_diff_frames": 4,
        "speech_shipping_active": 32,
        "speech_counter_active": 31,
        "noise_shipping_active": 12,
        "noise_counter_active": 11,
        "lost_speech_frames": 2,
        "gained_speech_frames": 1,
        "max_mirror_probability_delta": 0.0,
        "max_floor_probability_delta": 0.0,
        "max_floor_noise_reference_delta_db": 0.0,
        "max_floor_upstream_probability_delta": 0.0,
        "max_shipping_counter_probability_delta": 0.2,
        "scale_offset_db": 32.16113097315181,
        "min_counter_ratio_db": -2.0,
        "max_counter_ratio_db": 12.0,
    }
    d = derived(row)
    assert d["shipping_recall"] == 0.8
    assert d["counterfactual_recall"] == 0.775
    assert abs(d["shipping_false_positive_rate"] - 0.2) < 1e-12
    assert abs(d["counterfactual_false_positive_rate"] - 11 / 60) < 1e-12
    combined = aggregate_rows([row, row])
    assert combined["frames"] == 200
    assert combined["lost_speech_frames"] == 4
    assert combined["shipping_recall"] == 0.8
    print("calibrated local-SNR counterfactual evaluator self-test: OK")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--probe", type=Path)
    parser.add_argument("--contract", type=Path)
    parser.add_argument("--corpus", action="append", type=Path, default=[])
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    if args.self_test:
        self_test()
        return 0
    if not args.probe or not args.contract or not args.corpus or not args.output:
        parser.error("--probe, --contract, --corpus and --output are required")

    result = evaluate(
        args.probe.resolve(),
        args.contract.resolve(),
        [path.resolve() for path in args.corpus],
        args.output.resolve(),
    )
    print(json.dumps({
        "decision": result["decision"],
        "fresh_seeds": result["fresh_seeds"],
        "shipping_recall": result["aggregate"]["shipping_recall"],
        "counterfactual_recall": result["aggregate"]["counterfactual_recall"],
        "shipping_false_positive_rate":
            result["aggregate"]["shipping_false_positive_rate"],
        "counterfactual_false_positive_rate":
            result["aggregate"]["counterfactual_false_positive_rate"],
        "input_violations": len(result["input_violations"]),
        "regression_violations": len(result["regression_violations"]),
    }, sort_keys=True))
    return 2 if result["decision"] == (
        "CALIBRATED_LOCAL_SNR_INPUT_INVALID_REVIEW_REQUIRED"
    ) else 0


if __name__ == "__main__":
    raise SystemExit(main())
