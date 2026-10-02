#!/usr/bin/env python3
"""Measure AEC transition recovery across diagnostic stage prefixes."""

from __future__ import annotations

import argparse
import json
import statistics
import tempfile
from pathlib import Path

import run_validation_engine as engine
import stage_interaction_run
from aec_transition_recovery_latency import WINDOW_MS, window_series
from build_validation_corpus import RATE

PROFILES = (
    "prefix-aec",
    "prefix-res",
    "prefix-ns",
    "prefix-agc",
    "default",
)


def load_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path}: JSON object required")
    return value


def require_contract(contract: dict) -> None:
    if contract.get("authority") != "CANDIDATE_ZERO_STAGE_MEASUREMENT_ONLY":
        raise ValueError("stage recovery authority drift")
    if contract.get("candidate_limit") != 0 or contract.get("confirmation_limit") != 0:
        raise ValueError("stage recovery budget drift")
    if tuple(contract["corpus"]["stage_profiles"]) != PROFILES:
        raise ValueError("stage profile set/order drift")
    measurement = contract["measurement"]
    if int(measurement["window_ms"]) != WINDOW_MS:
        raise ValueError("window size drift")
    if measurement["pre_baseline_ms"] != [-1000, -200]:
        raise ValueError("pre baseline drift")
    if measurement["search_ms"] != [0, 2500]:
        raise ValueError("search interval drift")
    if int(measurement["continuous_hold_ms"]) != 300:
        raise ValueError("hold duration drift")


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

    with tempfile.TemporaryDirectory(prefix=f"ap-stage-recovery-{case['case_id']}-") as raw:
        output, trace, _inputs = stage_interaction_run.invoke(
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

    baseline = float(statistics.median(
        row["residual_to_echo_power_db"] for row in pre
    ))
    excess_limit = float(measurement["recovery_excess_db"])
    recovery_limit = baseline + excess_limit
    hold_windows = int(measurement["continuous_hold_ms"]) // WINDOW_MS

    recovery_time_ms = None
    for index in range(0, len(post) - hold_windows + 1):
        candidate = post[index:index + hold_windows]
        if all(
            row["residual_to_echo_power_db"] <= recovery_limit
            for row in candidate
        ):
            recovery_time_ms = int(candidate[0]["start_ms_relative"])
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

    dims = case["dimensions"]
    return {
        "case_id": case["case_id"],
        "base_case_id": dims["base_case_id"],
        "stage_profile": dims["stage_profile"],
        "stage_order": int(dims["stage_order"]),
        "stage_label": contract["corpus"]["stage_labels"][dims["stage_profile"]],
        "algorithmic_latency_ms": latency_ms,
        "pre_baseline_db": baseline,
        "recovery_limit_db": recovery_limit,
        "recovery_time_ms": recovery_time_ms,
        "censored": recovery_time_ms is None,
        "peak_excess_db_in_first_1000ms": max(first_1000),
        "positive_excess_area_db_ms_0_2500": sum(
            max(0.0, value) * WINDOW_MS for value in excess
        ),
        "late_window_excess_db_2000_2500": float(statistics.median(late)),
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

    target = set(contract["corpus"]["target_cases"])
    expected_ids = {
        f"{base}--{profile}"
        for base in target
        for profile in PROFILES
    }
    actual_ids = {case["case_id"] for case in corpus["cases"]}
    if actual_ids != expected_ids:
        raise ValueError("stage-recovery corpus case-set drift")

    report_cases = {case["case_id"]: case for case in report.get("cases", [])}
    if set(report_cases) != expected_ids:
        raise ValueError("canonical stage report case-set drift")
    if not all(bool(item.get("passed", False)) for item in report_cases.values()):
        raise ValueError("canonical stage report contains policy failure")

    rows = [
        analyze_case(case, corpus_path, processor, contract)
        for case in corpus["cases"]
    ]
    rows.sort(key=lambda row: (row["base_case_id"], row["stage_order"]))

    grouped: dict[str, list[dict]] = {}
    for row in rows:
        grouped.setdefault(row["base_case_id"], []).append(row)

    cases_out = []
    for base_case_id in contract["corpus"]["target_cases"]:
        stage_rows = grouped[base_case_id]
        profiles = tuple(row["stage_profile"] for row in stage_rows)
        if profiles != PROFILES:
            raise ValueError(f"{base_case_id}: stage profile order drift")
        aec = stage_rows[0]
        for row in stage_rows:
            if aec["censored"] or row["censored"]:
                row["delta_vs_prefix_aec_ms"] = None
            else:
                row["delta_vs_prefix_aec_ms"] = (
                    int(row["recovery_time_ms"]) - int(aec["recovery_time_ms"])
                )
        cases_out.append({
            "base_case_id": base_case_id,
            "stages": stage_rows,
            "all_profiles_measured": True,
            "any_censored": any(row["censored"] for row in stage_rows),
        })

    seed = int(corpus["generator"]["seed"])
    return {
        "schema_version": 1,
        "investigation_id": contract["id"],
        "seed": seed,
        "authority": "candidate-zero-stage-recovery-measurement-only",
        "cases": cases_out,
        "summary": {
            "base_cases": len(cases_out),
            "stage_profiles_per_case": len(PROFILES),
            "all_measurements_complete": True,
            "censored_observations": sum(
                row["censored"]
                for case in cases_out
                for row in case["stages"]
            ),
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

    cases = []
    for base_case_id in contract["corpus"]["target_cases"]:
        profiles = []
        for profile in PROFILES:
            observations = []
            for seed in expected_seeds:
                case = next(
                    x for x in by_seed[seed]["cases"]
                    if x["base_case_id"] == base_case_id
                )
                stage = next(
                    x for x in case["stages"]
                    if x["stage_profile"] == profile
                )
                observations.append({
                    "seed": seed,
                    "recovery_time_ms": stage["recovery_time_ms"],
                    "censored": stage["censored"],
                    "delta_vs_prefix_aec_ms": stage["delta_vs_prefix_aec_ms"],
                    "peak_excess_db_in_first_1000ms":
                        stage["peak_excess_db_in_first_1000ms"],
                    "positive_excess_area_db_ms_0_2500":
                        stage["positive_excess_area_db_ms_0_2500"],
                    "late_window_excess_db_2000_2500":
                        stage["late_window_excess_db_2000_2500"],
                })
            profiles.append({
                "stage_profile": profile,
                "stage_label": contract["corpus"]["stage_labels"][profile],
                "observations": observations,
                "all_recovery_observed": all(
                    not obs["censored"] for obs in observations
                ),
            })
        cases.append({
            "base_case_id": base_case_id,
            "profiles": profiles,
        })

    return {
        "schema_version": 1,
        "investigation_id": contract["id"],
        "fresh_seeds": expected_seeds,
        "stage_profiles": list(PROFILES),
        "cases": cases,
        "all_measurements_complete": True,
        "stage_recovery_performance_threshold_defined": False,
        "algorithm_performance_verdict": "NOT_AUTHORIZED",
        "candidate_authority": False,
        "s004_open": False,
    }


def self_test() -> None:
    contract = {
        "authority": "CANDIDATE_ZERO_STAGE_MEASUREMENT_ONLY",
        "candidate_limit": 0,
        "confirmation_limit": 0,
        "corpus": {"stage_profiles": list(PROFILES)},
        "measurement": {
            "window_ms": 100,
            "pre_baseline_ms": [-1000, -200],
            "search_ms": [0, 2500],
            "continuous_hold_ms": 300,
        },
    }
    require_contract(contract)
    assert PROFILES[0] == "prefix-aec"
    assert PROFILES[-1] == "default"
    print("AEC stage recovery decomposition self-test: OK")


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
            args.corpus,
            args.report,
            args.processor,
            contract,
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
                case["base_case_id"]: {
                    stage["stage_label"]: stage["recovery_time_ms"]
                    for stage in case["stages"]
                }
                for case in result["cases"]
            },
        }, sort_keys=True))
    else:
        print(json.dumps({
            "all_measurements_complete": result["all_measurements_complete"],
            "cases": {
                case["base_case_id"]: {
                    profile["stage_label"]: [
                        obs["recovery_time_ms"]
                        for obs in profile["observations"]
                    ]
                    for profile in case["profiles"]
                }
                for case in result["cases"]
            },
        }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
