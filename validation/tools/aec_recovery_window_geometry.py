#!/usr/bin/env python3
"""Decompose AEC recovery measurement geometry into stride and window effects.

Candidate-zero measurement only. All geometries share the exact same processor
output, pre-transition baseline, recovery limit, 300 ms hold, and search range.
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
GEOMETRY_IDS = ("100w-100s", "100w-50s", "50w-50s")


def load_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path}: JSON object required")
    return value


def require_contract(contract: dict) -> None:
    if contract.get("authority") != "CANDIDATE_ZERO_MEASUREMENT_ONLY":
        raise ValueError("geometry authority drift")
    if contract.get("candidate_limit") != 0 or contract.get("confirmation_limit") != 0:
        raise ValueError("geometry candidate budget drift")
    if tuple(contract["corpus"]["stage_profiles"]) != PROFILES:
        raise ValueError("geometry stage profile set/order drift")
    ids = tuple(item["id"] for item in contract["geometries"])
    if ids != GEOMETRY_IDS:
        raise ValueError("geometry set/order drift")
    expected = {
        "100w-100s": (100, 100, 3),
        "100w-50s": (100, 50, 5),
        "50w-50s": (50, 50, 6),
    }
    for item in contract["geometries"]:
        if (
            int(item["window_ms"]),
            int(item["stride_ms"]),
            int(item["required_windows_for_300ms_coverage"]),
        ) != expected[item["id"]]:
            raise ValueError(f"{item['id']}: geometry definition drift")
    if contract["fixed_baseline"]["window_ms"] != 100:
        raise ValueError("baseline window drift")
    if contract["fixed_baseline"]["pre_baseline_ms"] != [-1000, -200]:
        raise ValueError("baseline interval drift")
    shared = contract["shared_recovery"]
    if abs(float(shared["recovery_excess_db"]) - 3.01029995664) > 1e-12:
        raise ValueError("recovery limit drift")
    if int(shared["continuous_hold_ms"]) != 300:
        raise ValueError("hold duration drift")
    if shared["search_ms"] != [0, 2500]:
        raise ValueError("search interval drift")


def window_series(
    echo: list[int],
    output: list[int],
    transition_sample: int,
    output_delay_samples: int,
    start_ms: int,
    end_ms: int,
    window_ms: int,
    stride_ms: int,
) -> list[dict]:
    window_samples = RATE * window_ms // 1000
    stride_samples = RATE * stride_ms // 1000
    start_sample = transition_sample + start_ms * RATE // 1000
    end_sample = transition_sample + end_ms * RATE // 1000
    usable = (end_ms - start_ms) - window_ms
    if usable < 0 or usable % stride_ms != 0:
        raise ValueError("geometry does not tile requested interval exactly")
    expected = usable // stride_ms + 1
    rows: list[dict] = []
    offset = start_sample
    while offset + window_samples <= end_sample:
        value = power_ratio_db(
            echo,
            output,
            start_sample=offset,
            end_sample=offset + window_samples,
            output_delay_samples=output_delay_samples,
        )
        if value is None:
            raise ValueError("incomplete residual geometry window")
        relative_ms = (offset - transition_sample) * 1000 // RATE
        rows.append({
            "start_ms_relative": int(relative_ms),
            "end_ms_relative": int(relative_ms + window_ms),
            "residual_to_echo_power_db": float(value),
        })
        offset += stride_samples
    if len(rows) != expected:
        raise ValueError(f"geometry window count drift: {len(rows)} != {expected}")
    return rows


def measure_geometry(
    post: list[dict],
    baseline_db: float,
    recovery_limit_db: float,
    required_windows: int,
) -> dict:
    recovery_index = None
    for index in range(0, len(post) - required_windows + 1):
        candidate = post[index:index + required_windows]
        if all(
            row["residual_to_echo_power_db"] <= recovery_limit_db
            for row in candidate
        ):
            recovery_index = index
            break
    if recovery_index is None:
        return {
            "recovery_time_ms": None,
            "censored": True,
            "previous_window_margin_db": None,
            "recovery_start_margin_db": None,
            "recovery_hold_max_margin_db": None,
        }

    candidate = post[recovery_index:recovery_index + required_windows]
    previous = (
        post[recovery_index - 1]["residual_to_echo_power_db"] - recovery_limit_db
        if recovery_index > 0
        else None
    )
    return {
        "recovery_time_ms": int(candidate[0]["start_ms_relative"]),
        "censored": False,
        "previous_window_margin_db": previous,
        "recovery_start_margin_db":
            candidate[0]["residual_to_echo_power_db"] - recovery_limit_db,
        "recovery_hold_max_margin_db": max(
            row["residual_to_echo_power_db"] - recovery_limit_db
            for row in candidate
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
        prefix=f"ap-recovery-geometry-{case['case_id']}-"
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
        int(baseline_spec["window_ms"]),
    )
    baseline = float(statistics.median(
        row["residual_to_echo_power_db"] for row in pre
    ))
    shared = contract["shared_recovery"]
    recovery_limit = baseline + float(shared["recovery_excess_db"])

    geometries = {}
    for spec in contract["geometries"]:
        post = window_series(
            echo,
            output_list,
            transition_sample,
            output_delay_samples,
            int(shared["search_ms"][0]),
            int(shared["search_ms"][1]),
            int(spec["window_ms"]),
            int(spec["stride_ms"]),
        )
        measured = measure_geometry(
            post,
            baseline,
            recovery_limit,
            int(spec["required_windows_for_300ms_coverage"]),
        )
        measured.update({
            "window_ms": int(spec["window_ms"]),
            "stride_ms": int(spec["stride_ms"]),
            "required_windows_for_300ms_coverage":
                int(spec["required_windows_for_300ms_coverage"]),
            "recovery_limit_db": recovery_limit,
        })
        geometries[spec["id"]] = measured

    a = geometries["100w-100s"]["recovery_time_ms"]
    b = geometries["100w-50s"]["recovery_time_ms"]
    c = geometries["50w-50s"]["recovery_time_ms"]
    return {
        "case_id": case["case_id"],
        "base_case_id": dims["base_case_id"],
        "stage_profile": dims["stage_profile"],
        "stage_order": int(dims["stage_order"]),
        "stage_label": contract["corpus"]["stage_labels"][dims["stage_profile"]],
        "algorithmic_latency_ms": latency_ms,
        "shared_pre_baseline_db": baseline,
        "shared_recovery_limit_db": recovery_limit,
        "geometries": geometries,
        "stride_delta_ms_100w50s_minus_100w100s":
            None if a is None or b is None else int(b) - int(a),
        "integration_delta_ms_50w50s_minus_100w50s":
            None if b is None or c is None else int(c) - int(b),
        "same_output_for_all_geometries": True,
        "same_pre_baseline_for_all_geometries": True,
        "same_recovery_limit_for_all_geometries": True,
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
        raise ValueError("geometry corpus case-set drift")
    report_cases = {case["case_id"]: case for case in report.get("cases", [])}
    if set(report_cases) != expected_ids:
        raise ValueError("geometry canonical report case-set drift")
    if not all(bool(item.get("passed", False)) for item in report_cases.values()):
        raise ValueError("geometry canonical report policy failure")

    rows = [
        analyze_case(case, corpus_path, processor, contract)
        for case in corpus["cases"]
    ]
    rows.sort(key=lambda row: (row["base_case_id"], row["stage_order"]))
    for row in rows:
        if not (
            row["same_output_for_all_geometries"]
            and row["same_pre_baseline_for_all_geometries"]
            and row["same_recovery_limit_for_all_geometries"]
        ):
            raise ValueError("geometry isolation invariant failed")

    return {
        "schema_version": 1,
        "investigation_id": contract["id"],
        "seed": int(corpus["generator"]["seed"]),
        "authority": "candidate-zero-window-geometry-measurement-only",
        "observations": rows,
        "summary": {
            "observations": len(rows),
            "censored_by_geometry": {
                geometry: sum(
                    row["geometries"][geometry]["censored"] for row in rows
                )
                for geometry in GEOMETRY_IDS
            },
            "stride_changed_observations": sum(
                row["stride_delta_ms_100w50s_minus_100w100s"] not in (None, 0)
                for row in rows
            ),
            "integration_changed_observations": sum(
                row["integration_delta_ms_50w50s_minus_100w50s"] not in (None, 0)
                for row in rows
            ),
            "complete": True,
        },
        "candidate_authority": False,
        "measurement_artifact_verdict_authority": False,
    }


def range_or_none(observations: list[dict], geometry: str) -> int | None:
    values = [
        int(item["geometries"][geometry]["recovery_time_ms"])
        for item in observations
        if item["geometries"][geometry]["recovery_time_ms"] is not None
    ]
    if not values:
        return None
    return max(values) - min(values)


def aggregate(items: list[dict], contract: dict) -> dict:
    require_contract(contract)
    expected_seeds = sorted(int(x) for x in contract["corpus"]["fresh_seeds"])
    by_seed = {int(item["seed"]): item for item in items}
    if sorted(by_seed) != expected_seeds:
        raise ValueError("geometry fresh-seed mismatch")

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
                observations.append({"seed": seed, **row})

            ranges = {
                geometry: range_or_none(observations, geometry)
                for geometry in GEOMETRY_IDS
            }
            matrix.append({
                "base_case_id": base_case,
                "stage_profile": profile,
                "stage_label": contract["corpus"]["stage_labels"][profile],
                "observations": [
                    {
                        "seed": item["seed"],
                        "recovery_time_by_geometry": {
                            geometry:
                                item["geometries"][geometry]["recovery_time_ms"]
                            for geometry in GEOMETRY_IDS
                        },
                        "stride_delta_ms":
                            item["stride_delta_ms_100w50s_minus_100w100s"],
                        "integration_delta_ms":
                            item["integration_delta_ms_50w50s_minus_100w50s"],
                    }
                    for item in observations
                ],
                "cross_seed_range_ms": ranges,
                "range_stride_delta_ms":
                    None if ranges["100w-100s"] is None or ranges["100w-50s"] is None
                    else ranges["100w-50s"] - ranges["100w-100s"],
                "range_integration_delta_ms":
                    None if ranges["100w-50s"] is None or ranges["50w-50s"] is None
                    else ranges["50w-50s"] - ranges["100w-50s"],
            })

    return {
        "schema_version": 1,
        "investigation_id": contract["id"],
        "fresh_seeds": expected_seeds,
        "geometries": list(GEOMETRY_IDS),
        "matrix": matrix,
        "all_measurements_complete": True,
        "measurement_artifact_verdict": "NOT_AUTHORIZED",
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
        "geometries": [
            {"id": "100w-100s", "window_ms": 100, "stride_ms": 100,
             "required_windows_for_300ms_coverage": 3},
            {"id": "100w-50s", "window_ms": 100, "stride_ms": 50,
             "required_windows_for_300ms_coverage": 5},
            {"id": "50w-50s", "window_ms": 50, "stride_ms": 50,
             "required_windows_for_300ms_coverage": 6},
        ],
        "fixed_baseline": {"window_ms": 100, "pre_baseline_ms": [-1000, -200]},
        "shared_recovery": {
            "recovery_excess_db": 3.01029995664,
            "continuous_hold_ms": 300,
            "search_ms": [0, 2500],
        },
    }
    require_contract(contract)
    post = [
        {"start_ms_relative": i * 50, "residual_to_echo_power_db": v}
        for i, v in enumerate([4, 3, 2, 1, 0, -1, -2, -3])
    ]
    result = measure_geometry(post, 0.0, 3.01029995664, 5)
    assert result["recovery_time_ms"] == 50
    print("AEC recovery window geometry self-test: OK")


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
        result = run_seed(args.corpus, args.report, args.processor, contract)
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
        }, sort_keys=True))
    else:
        print(json.dumps({
            "all_measurements_complete": result["all_measurements_complete"],
            "ranges": {
                f"{row['base_case_id']}::{row['stage_label']}": {
                    **row["cross_seed_range_ms"],
                    "stride_range_delta": row["range_stride_delta_ms"],
                    "integration_range_delta": row["range_integration_delta_ms"],
                }
                for row in result["matrix"]
            },
        }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
