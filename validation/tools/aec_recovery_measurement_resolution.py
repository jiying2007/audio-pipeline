#!/usr/bin/env python3
"""Paired 100 ms / 50 ms AEC recovery measurement on identical outputs.

Only post-transition measurement resolution changes. DSP, audio, baseline,
recovery limit and continuous hold are identical between paired measurements.
"""

from __future__ import annotations

import argparse
import json
import statistics
import tempfile
from pathlib import Path

import run_validation_engine as engine
import stage_interaction_run
from aec_metric_safe_evidence import power_ratio_db
from build_validation_corpus import RATE

PROFILES = ("prefix-aec", "prefix-res", "prefix-ns", "prefix-agc", "default")


def load_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path}: JSON object required")
    return value


def require_contract(contract: dict) -> None:
    if contract.get("authority") != "CANDIDATE_ZERO_MEASUREMENT_ONLY":
        raise ValueError("resolution authority drift")
    if contract.get("candidate_limit") != 0 or contract.get("confirmation_limit") != 0:
        raise ValueError("resolution candidate budget drift")
    if tuple(contract["corpus"]["stage_profiles"]) != PROFILES:
        raise ValueError("resolution stage profile set/order drift")
    if contract["fixed_baseline"]["window_ms"] != 100:
        raise ValueError("baseline window drift")
    if contract["fixed_baseline"]["pre_baseline_ms"] != [-1000, -200]:
        raise ValueError("baseline interval drift")
    for name, expected_window, expected_hold in (
        ("100ms", 100, 3),
        ("50ms", 50, 6),
    ):
        item = contract["paired_measurements"][name]
        if int(item["post_window_ms"]) != expected_window:
            raise ValueError(f"{name}: post window drift")
        if int(item["continuous_hold_ms"]) != 300:
            raise ValueError(f"{name}: hold duration drift")
        if int(item["required_consecutive_windows"]) != expected_hold:
            raise ValueError(f"{name}: consecutive-window drift")
        if item["search_ms"] != [0, 2500]:
            raise ValueError(f"{name}: search interval drift")
        if abs(float(item["recovery_excess_db"]) - 3.01029995664) > 1.0e-12:
            raise ValueError(f"{name}: recovery threshold drift")


def window_series(
    echo: list[int],
    output: list[int],
    transition_sample: int,
    output_delay_samples: int,
    start_ms: int,
    end_ms: int,
    window_ms: int,
) -> list[dict]:
    window_samples = RATE * window_ms // 1000
    start_sample = transition_sample + start_ms * RATE // 1000
    end_sample = transition_sample + end_ms * RATE // 1000
    expected = (end_ms - start_ms) // window_ms
    rows = []
    for offset in range(start_sample, end_sample, window_samples):
        value = power_ratio_db(
            echo,
            output,
            start_sample=offset,
            end_sample=offset + window_samples,
            output_delay_samples=output_delay_samples,
        )
        if value is None:
            raise ValueError("incomplete residual measurement window")
        relative_ms = (offset - transition_sample) * 1000 // RATE
        rows.append({
            "start_ms_relative": int(relative_ms),
            "end_ms_relative": int(relative_ms + window_ms),
            "residual_to_echo_power_db": float(value),
        })
    if len(rows) != expected:
        raise ValueError(f"window count drift: {len(rows)} != {expected}")
    return rows


def measure_grid(
    post: list[dict],
    baseline_db: float,
    spec: dict,
) -> dict:
    limit = baseline_db + float(spec["recovery_excess_db"])
    hold = int(spec["required_consecutive_windows"])
    recovery_index = None
    for index in range(0, len(post) - hold + 1):
        candidate = post[index:index + hold]
        if all(row["residual_to_echo_power_db"] <= limit for row in candidate):
            recovery_index = index
            break

    if recovery_index is None:
        return {
            "recovery_time_ms": None,
            "censored": True,
            "recovery_limit_db": limit,
            "previous_window_margin_db": None,
            "recovery_start_margin_db": None,
            "recovery_hold_max_margin_db": None,
        }

    candidate = post[recovery_index:recovery_index + hold]
    previous = (
        post[recovery_index - 1]["residual_to_echo_power_db"] - limit
        if recovery_index > 0 else None
    )
    return {
        "recovery_time_ms": int(candidate[0]["start_ms_relative"]),
        "censored": False,
        "recovery_limit_db": limit,
        "previous_window_margin_db": previous,
        "recovery_start_margin_db":
            candidate[0]["residual_to_echo_power_db"] - limit,
        "recovery_hold_max_margin_db": max(
            row["residual_to_echo_power_db"] - limit for row in candidate
        ),
    }


def analyze_case(
    case: dict,
    corpus_path: Path,
    processor: Path,
    contract: dict,
) -> dict:
    dims = case["dimensions"]
    frame = int(dims.get("frame", -1))
    if frame < 0:
        raise ValueError(f"{case['case_id']}: transition frame missing")
    transition_sample = frame * (RATE // 100)

    echo_path = engine.resolve(corpus_path, case.get("echo_audio"))
    if echo_path is None:
        raise ValueError(f"{case['case_id']}: echo reference missing")
    echo = [int(x) for x in engine.read_audio_samples(echo_path, RATE, 1)]

    with tempfile.TemporaryDirectory(
        prefix=f"ap-recovery-resolution-{case['case_id']}-"
    ) as raw:
        output, trace, _inputs = stage_interaction_run.invoke(
            processor, case, corpus_path, Path(raw)
        )
    if not trace:
        raise ValueError(f"{case['case_id']}: processor trace missing")
    latency_ms = int(trace[0].get("algorithmic_latency_ms", -1))
    if latency_ms < 0:
        raise ValueError(f"{case['case_id']}: invalid latency")
    output_delay_samples = latency_ms * RATE // 1000
    output_list = [int(x) for x in output]

    baseline_spec = contract["fixed_baseline"]
    pre = window_series(
        echo,
        output_list,
        transition_sample,
        output_delay_samples,
        int(baseline_spec["pre_baseline_ms"][0]),
        int(baseline_spec["pre_baseline_ms"][1]),
        int(baseline_spec["window_ms"]),
    )
    baseline = float(statistics.median(
        row["residual_to_echo_power_db"] for row in pre
    ))

    measurements = {}
    for name in ("100ms", "50ms"):
        spec = contract["paired_measurements"][name]
        post = window_series(
            echo,
            output_list,
            transition_sample,
            output_delay_samples,
            int(spec["search_ms"][0]),
            int(spec["search_ms"][1]),
            int(spec["post_window_ms"]),
        )
        measurements[name] = measure_grid(post, baseline, spec)

    a = measurements["100ms"]["recovery_time_ms"]
    b = measurements["50ms"]["recovery_time_ms"]
    paired_delta = None if a is None or b is None else int(b) - int(a)

    return {
        "case_id": case["case_id"],
        "base_case_id": dims["base_case_id"],
        "stage_profile": dims["stage_profile"],
        "stage_order": int(dims["stage_order"]),
        "stage_label": contract["corpus"]["stage_labels"][dims["stage_profile"]],
        "algorithmic_latency_ms": latency_ms,
        "shared_pre_baseline_db": baseline,
        "measurements": measurements,
        "paired_recovery_delta_ms_50_minus_100": paired_delta,
        "same_output_for_both_grids": True,
        "same_baseline_for_both_grids": True,
        "same_recovery_limit_for_both_grids": (
            abs(
                measurements["100ms"]["recovery_limit_db"]
                - measurements["50ms"]["recovery_limit_db"]
            ) < 1.0e-12
        ),
    }


def run_seed(
    corpus_path: Path,
    report_path: Path,
    processor: Path,
    contract: dict,
) -> dict:
    require_contract(contract)
    corpus = load_json(corpus_path)
    report = load_json(report_path)
    expected_ids = {
        f"{base}--{profile}"
        for base in contract["corpus"]["target_cases"]
        for profile in PROFILES
    }
    if {case["case_id"] for case in corpus["cases"]} != expected_ids:
        raise ValueError("resolution corpus case-set drift")
    report_cases = {case["case_id"]: case for case in report.get("cases", [])}
    if set(report_cases) != expected_ids:
        raise ValueError("resolution canonical report case-set drift")
    if not all(bool(item.get("passed", False)) for item in report_cases.values()):
        raise ValueError("resolution canonical report policy failure")

    rows = [
        analyze_case(case, corpus_path, processor, contract)
        for case in corpus["cases"]
    ]
    rows.sort(key=lambda row: (row["base_case_id"], row["stage_order"]))
    if not all(row["same_output_for_both_grids"] for row in rows):
        raise ValueError("paired grids did not share output")
    if not all(row["same_baseline_for_both_grids"] for row in rows):
        raise ValueError("paired grids did not share baseline")
    if not all(row["same_recovery_limit_for_both_grids"] for row in rows):
        raise ValueError("paired grids did not share recovery limit")

    return {
        "schema_version": 1,
        "investigation_id": contract["id"],
        "seed": int(corpus["generator"]["seed"]),
        "authority": "candidate-zero-paired-resolution-measurement-only",
        "observations": rows,
        "summary": {
            "observations": len(rows),
            "censored_100ms": sum(
                row["measurements"]["100ms"]["censored"] for row in rows
            ),
            "censored_50ms": sum(
                row["measurements"]["50ms"]["censored"] for row in rows
            ),
            "paired_time_changed": sum(
                row["paired_recovery_delta_ms_50_minus_100"] not in (None, 0)
                for row in rows
            ),
            "complete": True,
        },
        "candidate_authority": False,
        "measurement_artifact_verdict_authority": False,
    }


def aggregate(items: list[dict], contract: dict) -> dict:
    require_contract(contract)
    expected_seeds = sorted(int(x) for x in contract["corpus"]["fresh_seeds"])
    by_seed = {int(item["seed"]): item for item in items}
    if sorted(by_seed) != expected_seeds:
        raise ValueError("resolution fresh-seed mismatch")

    matrix = []
    for base_case in contract["corpus"]["target_cases"]:
        for profile in PROFILES:
            observations = []
            for seed in expected_seeds:
                row = next(
                    item for item in by_seed[seed]["observations"]
                    if item["base_case_id"] == base_case
                    and item["stage_profile"] == profile
                )
                observations.append({
                    "seed": seed,
                    "recovery_time_100ms":
                        row["measurements"]["100ms"]["recovery_time_ms"],
                    "recovery_time_50ms":
                        row["measurements"]["50ms"]["recovery_time_ms"],
                    "censored_100ms":
                        row["measurements"]["100ms"]["censored"],
                    "censored_50ms":
                        row["measurements"]["50ms"]["censored"],
                    "paired_delta_ms_50_minus_100":
                        row["paired_recovery_delta_ms_50_minus_100"],
                })

            def range_or_none(key: str) -> int | None:
                values = [
                    int(item[key])
                    for item in observations
                    if item[key] is not None
                ]
                if not values:
                    return None
                return max(values) - min(values)

            range100 = range_or_none("recovery_time_100ms")
            range50 = range_or_none("recovery_time_50ms")
            matrix.append({
                "base_case_id": base_case,
                "stage_profile": profile,
                "stage_label": contract["corpus"]["stage_labels"][profile],
                "observations": observations,
                "cross_seed_range_100ms": range100,
                "cross_seed_range_50ms": range50,
                "range_delta_ms_50_minus_100":
                    None if range100 is None or range50 is None
                    else range50 - range100,
                "any_paired_time_change": any(
                    item["paired_delta_ms_50_minus_100"] not in (None, 0)
                    for item in observations
                ),
            })

    return {
        "schema_version": 1,
        "investigation_id": contract["id"],
        "fresh_seeds": expected_seeds,
        "matrix": matrix,
        "all_measurements_complete": True,
        "measurement_resolution_verdict": "NOT_AUTHORIZED",
        "performance_threshold_defined": False,
        "candidate_authority": False,
        "s004_open": False,
    }


def self_test() -> None:
    contract = {
        "authority": "CANDIDATE_ZERO_MEASUREMENT_ONLY",
        "candidate_limit": 0,
        "confirmation_limit": 0,
        "corpus": {"stage_profiles": list(PROFILES)},
        "fixed_baseline": {
            "window_ms": 100,
            "pre_baseline_ms": [-1000, -200],
        },
        "paired_measurements": {
            "100ms": {
                "post_window_ms": 100,
                "recovery_excess_db": 3.01029995664,
                "continuous_hold_ms": 300,
                "required_consecutive_windows": 3,
                "search_ms": [0, 2500],
            },
            "50ms": {
                "post_window_ms": 50,
                "recovery_excess_db": 3.01029995664,
                "continuous_hold_ms": 300,
                "required_consecutive_windows": 6,
                "search_ms": [0, 2500],
            },
        },
    }
    require_contract(contract)
    post = [
        {"start_ms_relative": i * 50, "residual_to_echo_power_db": value}
        for i, value in enumerate([5, 4, 2, 1, 0, -1, -2, -3])
    ]
    result = measure_grid(
        post,
        0.0,
        contract["paired_measurements"]["50ms"],
    )
    assert result["recovery_time_ms"] == 100
    print("AEC recovery measurement resolution self-test: OK")


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("self-test")
    run_p = sub.add_parser("run")
    run_p.add_argument("--corpus", type=Path, required=True)
    run_p.add_argument("--report", type=Path, required=True)
    run_p.add_argument("--processor", type=Path, required=True)
    run_p.add_argument("--contract", type=Path, required=True)
    run_p.add_argument("--output", type=Path, required=True)
    agg_p = sub.add_parser("aggregate")
    agg_p.add_argument("--contract", type=Path, required=True)
    agg_p.add_argument("--input", type=Path, action="append", required=True)
    agg_p.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    if args.command == "self-test":
        self_test()
        return 0

    contract = load_json(args.contract)
    if args.command == "run":
        result = run_seed(
            args.corpus, args.report, args.processor, contract
        )
    else:
        result = aggregate(
            [load_json(path) for path in args.input],
            contract,
        )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    if args.command == "run":
        print(json.dumps({
            "seed": result["seed"],
            **result["summary"],
            "paired_deltas_ms": {
                f"{row['base_case_id']}::{row['stage_label']}":
                    row["paired_recovery_delta_ms_50_minus_100"]
                for row in result["observations"]
            },
        }, sort_keys=True))
    else:
        print(json.dumps({
            "all_measurements_complete": result["all_measurements_complete"],
            "ranges": {
                f"{row['base_case_id']}::{row['stage_label']}": {
                    "100ms": row["cross_seed_range_100ms"],
                    "50ms": row["cross_seed_range_50ms"],
                    "delta": row["range_delta_ms_50_minus_100"],
                    "any_paired_change": row["any_paired_time_change"],
                }
                for row in result["matrix"]
            },
        }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
