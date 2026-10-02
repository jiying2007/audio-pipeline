#!/usr/bin/env python3
"""Measure candidate-zero AEC transition recovery latency.

The operational recovery definition is preregistered in the investigation
contract. Censored recovery is valid evidence and never makes this tool fail.
"""

from __future__ import annotations

import argparse
import json
import statistics
import tempfile
from pathlib import Path

import run_validation_engine as engine
from aec_metric_safe_evidence import power_ratio_db
from build_validation_corpus import RATE

WINDOW_MS = 100


def load_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path}: JSON object required")
    return value


def require_contract(contract: dict) -> None:
    if contract.get("authority") != "CANDIDATE_ZERO_MEASUREMENT_ONLY":
        raise ValueError("recovery authority drift")
    if contract.get("candidate_limit") != 0 or contract.get("confirmation_limit") != 0:
        raise ValueError("recovery candidate budget drift")
    measurement = contract["measurement"]
    if int(measurement["window_ms"]) != WINDOW_MS:
        raise ValueError("window size drift")
    if measurement["pre_baseline_ms"] != [-1000, -200]:
        raise ValueError("pre-baseline interval drift")
    if measurement["search_ms"] != [0, 2500]:
        raise ValueError("search interval drift")
    if int(measurement["continuous_hold_ms"]) != 300:
        raise ValueError("hold duration drift")


def window_series(
    echo: list[int],
    output: list[int],
    transition_sample: int,
    output_delay_samples: int,
    start_ms: int,
    end_ms: int,
) -> list[dict]:
    window_samples = RATE * WINDOW_MS // 1000
    start_sample = transition_sample + start_ms * RATE // 1000
    end_sample = transition_sample + end_ms * RATE // 1000
    expected = (end_ms - start_ms) // WINDOW_MS
    rows: list[dict] = []
    for offset in range(start_sample, end_sample, window_samples):
        value = power_ratio_db(
            echo,
            output,
            start_sample=offset,
            end_sample=offset + window_samples,
            output_delay_samples=output_delay_samples,
        )
        if value is None:
            raise ValueError("incomplete residual window")
        rel_ms = (offset - transition_sample) * 1000 // RATE
        rows.append({
            "start_ms_relative": int(rel_ms),
            "end_ms_relative": int(rel_ms + WINDOW_MS),
            "residual_to_echo_power_db": float(value),
        })
    if len(rows) != expected:
        raise ValueError(f"window count drift: {len(rows)} != {expected}")
    return rows


def analyze_case(
    case: dict,
    corpus_path: Path,
    processor: Path,
    contract: dict,
) -> dict:
    frame = int(case.get("dimensions", {}).get("frame", -1))
    if frame < 0:
        raise ValueError(f"{case['case_id']}: transition frame missing")
    transition_sample = frame * (RATE // 100)

    echo_path = engine.resolve(corpus_path, case.get("echo_audio"))
    if echo_path is None:
        raise ValueError(f"{case['case_id']}: echo reference missing")
    echo = [int(x) for x in engine.read_audio_samples(echo_path, RATE, 1)]

    with tempfile.TemporaryDirectory(prefix=f"ap-recovery-{case['case_id']}-") as raw:
        output, trace, _inputs = engine.invoke(
            processor, case, corpus_path, Path(raw)
        )
    if not trace:
        raise ValueError(f"{case['case_id']}: processor trace missing")
    latency_ms = int(trace[0].get("algorithmic_latency_ms", -1))
    if latency_ms < 0:
        raise ValueError(f"{case['case_id']}: invalid algorithmic latency")
    output_delay_samples = latency_ms * RATE // 1000
    output_list = [int(x) for x in output]

    measurement = contract["measurement"]
    pre = window_series(
        echo,
        output_list,
        transition_sample,
        output_delay_samples,
        int(measurement["pre_baseline_ms"][0]),
        int(measurement["pre_baseline_ms"][1]),
    )
    post = window_series(
        echo,
        output_list,
        transition_sample,
        output_delay_samples,
        int(measurement["search_ms"][0]),
        int(measurement["search_ms"][1]),
    )

    pre_values = [row["residual_to_echo_power_db"] for row in pre]
    baseline = float(statistics.median(pre_values))
    excess_limit = float(measurement["recovery_excess_db"])
    recovery_limit = baseline + excess_limit
    hold_windows = int(measurement["continuous_hold_ms"]) // WINDOW_MS
    if hold_windows < 1:
        raise ValueError("invalid hold window count")

    recovery_time_ms = None
    recovery_run = None
    for index in range(0, len(post) - hold_windows + 1):
        candidate = post[index:index + hold_windows]
        if all(
            row["residual_to_echo_power_db"] <= recovery_limit
            for row in candidate
        ):
            recovery_time_ms = int(candidate[0]["start_ms_relative"])
            recovery_run = candidate
            break

    excess = [
        row["residual_to_echo_power_db"] - baseline for row in post
    ]
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
        raise ValueError("derived recovery window coverage drift")

    return {
        "case_id": case["case_id"],
        "family": case.get("dimensions", {}).get("family"),
        "transition": case.get("dimensions", {}).get("transition"),
        "transition_frame": frame,
        "algorithmic_latency_ms": latency_ms,
        "pre_baseline_db": baseline,
        "recovery_limit_db": recovery_limit,
        "recovery_excess_db": excess_limit,
        "recovery_time_ms": recovery_time_ms,
        "censored": recovery_time_ms is None,
        "hold_windows": hold_windows,
        "peak_excess_db_in_first_1000ms": max(first_1000),
        "positive_excess_area_db_ms_0_2500": sum(
            max(0.0, value) * WINDOW_MS for value in excess
        ),
        "late_window_excess_db_2000_2500": float(statistics.median(late)),
        "pre_windows": pre,
        "post_windows": post,
        "recovery_run": recovery_run,
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
    target = list(contract["corpus"]["target_cases"])
    cases = {case["case_id"]: case for case in corpus["cases"]}
    if not all(case_id in cases for case_id in target):
        raise ValueError("target transition case missing")

    report_cases = {case["case_id"]: case for case in report.get("cases", [])}
    for case_id in target:
        if case_id not in report_cases:
            raise ValueError(f"canonical report missing {case_id}")

    rows = [
        analyze_case(cases[case_id], corpus_path, processor, contract)
        for case_id in target
    ]
    seed = int(corpus["generator"]["seed"])
    return {
        "schema_version": 1,
        "investigation_id": contract["id"],
        "seed": seed,
        "authority": "candidate-zero-recovery-measurement-only",
        "cases": rows,
        "summary": {
            "target_cases": len(rows),
            "recovery_observed_cases": sum(not row["censored"] for row in rows),
            "censored_cases": sum(row["censored"] for row in rows),
            "measurements_complete": True,
        },
        "candidate_authority": False,
        "algorithm_performance_verdict_authority": False,
    }


def aggregate(items: list[dict], contract: dict) -> dict:
    require_contract(contract)
    expected_seeds = sorted(int(x) for x in contract["corpus"]["fresh_seeds"])
    by_seed = {int(item["seed"]): item for item in items}
    if sorted(by_seed) != expected_seeds:
        raise ValueError("fresh seed mismatch")
    target = list(contract["corpus"]["target_cases"])

    cases = []
    for case_id in target:
        observations = []
        for seed in expected_seeds:
            case = next(
                (row for row in by_seed[seed]["cases"] if row["case_id"] == case_id),
                None,
            )
            if case is None:
                raise ValueError(f"{case_id}: seed {seed} missing")
            observations.append({
                "seed": seed,
                "recovery_time_ms": case["recovery_time_ms"],
                "censored": case["censored"],
                "pre_baseline_db": case["pre_baseline_db"],
                "recovery_limit_db": case["recovery_limit_db"],
                "peak_excess_db_in_first_1000ms":
                    case["peak_excess_db_in_first_1000ms"],
                "positive_excess_area_db_ms_0_2500":
                    case["positive_excess_area_db_ms_0_2500"],
                "late_window_excess_db_2000_2500":
                    case["late_window_excess_db_2000_2500"],
            })
        cases.append({
            "case_id": case_id,
            "observations": observations,
            "all_recovery_observed": all(not row["censored"] for row in observations),
            "any_censored": any(row["censored"] for row in observations),
        })

    return {
        "schema_version": 1,
        "investigation_id": contract["id"],
        "fresh_seeds": expected_seeds,
        "measurement_definition": contract["measurement"],
        "cases": cases,
        "all_measurements_complete": True,
        "performance_threshold_defined": False,
        "algorithm_performance_verdict": "NOT_AUTHORIZED",
        "candidate_authority": False,
        "s004_open": False,
    }


def self_test() -> None:
    contract = {
        "authority": "CANDIDATE_ZERO_MEASUREMENT_ONLY",
        "candidate_limit": 0,
        "confirmation_limit": 0,
        "measurement": {
            "window_ms": 100,
            "pre_baseline_ms": [-1000, -200],
            "search_ms": [0, 2500],
            "continuous_hold_ms": 300,
        },
    }
    require_contract(contract)
    values = [-40.0, -39.0, -38.0]
    baseline = statistics.median(values)
    assert baseline == -39.0
    assert abs(10.0 ** (3.01029995664 / 10.0) - 2.0) < 1.0e-9
    print("AEC transition recovery latency self-test: OK")


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
                row["case_id"]: row["recovery_time_ms"]
                for row in result["cases"]
            },
        }, sort_keys=True))
    else:
        print(json.dumps({
            "all_measurements_complete": result["all_measurements_complete"],
            "cases": {
                item["case_id"]: [
                    {
                        "seed": obs["seed"],
                        "recovery_time_ms": obs["recovery_time_ms"],
                        "censored": obs["censored"],
                    }
                    for obs in item["observations"]
                ]
                for item in result["cases"]
            },
        }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
