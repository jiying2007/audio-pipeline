#!/usr/bin/env python3
"""Decompose AEC recovery variability using residual and stage telemetry evidence.

Candidate-zero observation only. This tool does not rank causes, fit thresholds,
or recommend parameter changes.
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
import tempfile
from pathlib import Path

import run_validation_engine as engine
import stage_interaction_run
from aec_transition_recovery_latency import WINDOW_MS, window_series
from build_validation_corpus import RATE

PROFILES = ("prefix-aec", "prefix-res", "prefix-ns", "prefix-agc", "default")
BOOLEAN_FIELDS = (
    "aec_converged",
    "erle_valid",
    "far_end_active",
    "double_talk_active",
)


def load_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path}: JSON object required")
    return value


def require_contract(contract: dict) -> None:
    if contract.get("authority") != "CANDIDATE_ZERO_OBSERVATION_ONLY":
        raise ValueError("variability authority drift")
    if contract.get("candidate_limit") != 0 or contract.get("confirmation_limit") != 0:
        raise ValueError("variability candidate budget drift")
    if tuple(contract["corpus"]["stage_profiles"]) != PROFILES:
        raise ValueError("stage profile set/order drift")
    measurement = contract["recovery_measurement"]
    if int(measurement["window_ms"]) != WINDOW_MS:
        raise ValueError("recovery window size drift")
    if measurement["pre_baseline_ms"] != [-1000, -200]:
        raise ValueError("pre baseline drift")
    if measurement["search_ms"] != [0, 2500]:
        raise ValueError("search interval drift")
    if int(measurement["continuous_hold_ms"]) != 300:
        raise ValueError("hold duration drift")


def percentile(values: list[float], quantile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = quantile * (len(ordered) - 1)
    lo = int(math.floor(position))
    hi = int(math.ceil(position))
    if lo == hi:
        return ordered[lo]
    frac = position - lo
    return ordered[lo] * (1.0 - frac) + ordered[hi] * frac


def telemetry_slice(
    trace: list[dict],
    transition_frame: int,
    start_ms: int,
    end_ms: int,
) -> list[dict]:
    frame_ms = 10
    start = transition_frame + start_ms // frame_ms
    end = transition_frame + end_ms // frame_ms
    start = max(0, start)
    end = min(len(trace), end)
    if end <= start:
        raise ValueError("telemetry window is empty")
    rows = trace[start:end]
    expected = (end_ms - start_ms) // frame_ms
    if len(rows) != expected:
        raise ValueError(
            f"telemetry window incomplete: {len(rows)} != {expected}"
        )
    return rows


def summarize_telemetry(rows: list[dict]) -> dict:
    out: dict[str, float | int | None] = {"frames": len(rows)}
    for field in BOOLEAN_FIELDS:
        out[f"{field}_fraction"] = (
            sum(1 if int(row.get(field, 0)) else 0 for row in rows) / len(rows)
        )

    valid_erle = [
        float(row["erle_db"])
        for row in rows
        if int(row.get("erle_valid", 0)) and row.get("erle_db") is not None
    ]
    out["erle_db_median_valid"] = (
        float(statistics.median(valid_erle)) if valid_erle else None
    )
    out["erle_db_p10_valid"] = percentile(valid_erle, 0.10)
    out["erle_db_p90_valid"] = percentile(valid_erle, 0.90)

    delays = [float(row.get("estimated_delay_ms", 0)) for row in rows]
    errors = [float(row.get("delay_error_samples", 0)) for row in rows]
    abs_errors = [abs(value) for value in errors]
    out["estimated_delay_ms_median"] = float(statistics.median(delays))
    out["estimated_delay_ms_range"] = max(delays) - min(delays)
    out["delay_error_samples_median"] = float(statistics.median(errors))
    out["delay_error_samples_abs_median"] = float(statistics.median(abs_errors))
    out["delay_error_samples_abs_p90"] = percentile(abs_errors, 0.90)
    out["delay_error_samples_abs_max"] = max(abs_errors)
    return out


def recovery_evidence(
    echo: list[int],
    output: list[int],
    transition_sample: int,
    output_delay_samples: int,
    contract: dict,
) -> dict:
    measurement = contract["recovery_measurement"]
    pre = window_series(
        echo,
        output,
        transition_sample,
        output_delay_samples,
        int(measurement["pre_baseline_ms"][0]),
        int(measurement["pre_baseline_ms"][1]),
    )
    post = window_series(
        echo,
        output,
        transition_sample,
        output_delay_samples,
        int(measurement["search_ms"][0]),
        int(measurement["search_ms"][1]),
    )
    baseline = float(
        statistics.median(row["residual_to_echo_power_db"] for row in pre)
    )
    limit = baseline + float(measurement["recovery_excess_db"])
    hold_windows = int(measurement["continuous_hold_ms"]) // WINDOW_MS

    recovery_index = None
    for index in range(0, len(post) - hold_windows + 1):
        candidate = post[index:index + hold_windows]
        if all(row["residual_to_echo_power_db"] <= limit for row in candidate):
            recovery_index = index
            break

    if recovery_index is None:
        recovery_time = None
        boundary = {
            "previous_window_margin_db": None,
            "recovery_start_margin_db": None,
            "recovery_hold_max_margin_db": None,
        }
    else:
        recovery_time = int(post[recovery_index]["start_ms_relative"])
        previous = (
            post[recovery_index - 1]["residual_to_echo_power_db"] - limit
            if recovery_index > 0
            else None
        )
        hold = post[recovery_index:recovery_index + hold_windows]
        boundary = {
            "previous_window_margin_db": previous,
            "recovery_start_margin_db":
                hold[0]["residual_to_echo_power_db"] - limit,
            "recovery_hold_max_margin_db": max(
                row["residual_to_echo_power_db"] - limit for row in hold
            ),
        }

    excess = [row["residual_to_echo_power_db"] - baseline for row in post]
    first_1000 = [
        value
        for row, value in zip(post, excess)
        if 0 <= int(row["start_ms_relative"]) < 1000
    ]
    late = [
        value
        for row, value in zip(post, excess)
        if 2000 <= int(row["start_ms_relative"]) < 2500
    ]
    if len(first_1000) != 10 or len(late) != 5:
        raise ValueError("recovery window coverage drift")

    return {
        "pre_baseline_db": baseline,
        "recovery_limit_db": limit,
        "recovery_time_ms": recovery_time,
        "censored": recovery_time is None,
        "peak_excess_db_in_first_1000ms": max(first_1000),
        "positive_excess_area_db_ms_0_2500": sum(
            max(0.0, value) * WINDOW_MS for value in excess
        ),
        "late_window_excess_db_2000_2500": float(statistics.median(late)),
        "recovery_boundary_margin_db": boundary,
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
        prefix=f"ap-recovery-variability-{case['case_id']}-"
    ) as raw:
        output, trace, _inputs = stage_interaction_run.invoke(
            processor, case, corpus_path, Path(raw)
        )
    if not trace:
        raise ValueError(f"{case['case_id']}: telemetry trace missing")
    latency_ms = int(trace[0].get("algorithmic_latency_ms", -1))
    if latency_ms < 0:
        raise ValueError(f"{case['case_id']}: invalid algorithmic latency")
    output_delay_samples = latency_ms * RATE // 1000

    windows = {}
    for name, (start_ms, end_ms) in contract["telemetry_windows"].items():
        rows = telemetry_slice(trace, frame, int(start_ms), int(end_ms))
        windows[name] = summarize_telemetry(rows)

    recovery = recovery_evidence(
        echo,
        [int(x) for x in output],
        transition_sample,
        output_delay_samples,
        contract,
    )

    return {
        "case_id": case["case_id"],
        "base_case_id": dims["base_case_id"],
        "stage_profile": dims["stage_profile"],
        "stage_order": int(dims["stage_order"]),
        "stage_label": contract["corpus"]["stage_labels"][dims["stage_profile"]],
        "algorithmic_latency_ms": latency_ms,
        "recovery": recovery,
        "telemetry_windows": windows,
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
        raise ValueError("variability corpus case-set drift")
    report_cases = {case["case_id"]: case for case in report.get("cases", [])}
    if set(report_cases) != expected_ids:
        raise ValueError("variability canonical report case-set drift")
    if not all(bool(item.get("passed", False)) for item in report_cases.values()):
        raise ValueError("variability canonical policy failure")

    rows = [
        analyze_case(case, corpus_path, processor, contract)
        for case in corpus["cases"]
    ]
    rows.sort(key=lambda row: (row["base_case_id"], row["stage_order"]))
    seed = int(corpus["generator"]["seed"])
    return {
        "schema_version": 1,
        "investigation_id": contract["id"],
        "seed": seed,
        "authority": "candidate-zero-recovery-variability-observation-only",
        "observations": rows,
        "summary": {
            "cases": len(rows),
            "censored": sum(row["recovery"]["censored"] for row in rows),
            "complete": True,
        },
        "candidate_authority": False,
        "causal_stage_authority": False,
    }


def numeric_delta(slow: dict, fast: dict) -> dict:
    keys = sorted(set(slow) & set(fast))
    out = {}
    for key in keys:
        a = slow[key]
        b = fast[key]
        if (
            isinstance(a, (int, float))
            and not isinstance(a, bool)
            and isinstance(b, (int, float))
            and not isinstance(b, bool)
        ):
            out[key] = float(a) - float(b)
    return out


def aggregate(items: list[dict], contract: dict) -> dict:
    require_contract(contract)
    expected_seeds = sorted(int(x) for x in contract["corpus"]["fresh_seeds"])
    by_seed = {int(item["seed"]): item for item in items}
    if sorted(by_seed) != expected_seeds:
        raise ValueError("variability fresh-seed mismatch")

    matrix = []
    for base_case in contract["corpus"]["target_cases"]:
        for profile in PROFILES:
            observations = []
            for seed in expected_seeds:
                row = next(
                    item
                    for item in by_seed[seed]["observations"]
                    if item["base_case_id"] == base_case
                    and item["stage_profile"] == profile
                )
                observations.append({"seed": seed, **row})
            non_censored = [
                item for item in observations
                if not item["recovery"]["censored"]
            ]
            times = [
                int(item["recovery"]["recovery_time_ms"])
                for item in non_censored
            ]
            if times:
                min_time = min(times)
                max_time = max(times)
                fastest = min(
                    (item for item in non_censored
                     if int(item["recovery"]["recovery_time_ms"]) == min_time),
                    key=lambda item: item["seed"],
                )
                slowest = min(
                    (item for item in non_censored
                     if int(item["recovery"]["recovery_time_ms"]) == max_time),
                    key=lambda item: item["seed"],
                )
                telemetry_delta = {
                    window: numeric_delta(
                        slowest["telemetry_windows"][window],
                        fastest["telemetry_windows"][window],
                    )
                    for window in contract["telemetry_windows"]
                }
                boundary_delta = numeric_delta(
                    slowest["recovery"]["recovery_boundary_margin_db"],
                    fastest["recovery"]["recovery_boundary_margin_db"],
                )
                recovery_range = max_time - min_time
            else:
                fastest = slowest = None
                telemetry_delta = {}
                boundary_delta = {}
                recovery_range = None

            matrix.append({
                "base_case_id": base_case,
                "stage_profile": profile,
                "stage_label": contract["corpus"]["stage_labels"][profile],
                "observations": observations,
                "cross_seed_recovery_range_ms": recovery_range,
                "fastest_seed": None if fastest is None else fastest["seed"],
                "slowest_seed": None if slowest is None else slowest["seed"],
                "fastest_vs_slowest_telemetry_delta_slow_minus_fast":
                    telemetry_delta,
                "fastest_vs_slowest_boundary_margin_delta_slow_minus_fast":
                    boundary_delta,
            })

    return {
        "schema_version": 1,
        "investigation_id": contract["id"],
        "fresh_seeds": expected_seeds,
        "matrix": matrix,
        "all_measurements_complete": True,
        "causal_attribution": "NOT_AUTHORIZED",
        "performance_threshold_defined": False,
        "candidate_authority": False,
        "s004_open": False,
    }


def self_test() -> None:
    contract = {
        "authority": "CANDIDATE_ZERO_OBSERVATION_ONLY",
        "candidate_limit": 0,
        "confirmation_limit": 0,
        "corpus": {"stage_profiles": list(PROFILES)},
        "recovery_measurement": {
            "window_ms": 100,
            "pre_baseline_ms": [-1000, -200],
            "search_ms": [0, 2500],
            "continuous_hold_ms": 300,
        },
    }
    require_contract(contract)
    delta = numeric_delta(
        {"x": 3.0, "y": 2, "b": True},
        {"x": 1.0, "y": 1, "b": False},
    )
    assert delta == {"x": 2.0, "y": 1.0}
    print("AEC recovery variability decomposition self-test: OK")


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
            "recovery_ms": {
                f"{row['base_case_id']}::{row['stage_label']}":
                    row["recovery"]["recovery_time_ms"]
                for row in result["observations"]
            },
        }, sort_keys=True))
    else:
        print(json.dumps({
            "all_measurements_complete": result["all_measurements_complete"],
            "recovery_ranges_ms": {
                f"{row['base_case_id']}::{row['stage_label']}":
                    row["cross_seed_recovery_range_ms"]
                for row in result["matrix"]
            },
        }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
