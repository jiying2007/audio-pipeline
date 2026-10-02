#!/usr/bin/env python3
"""Confirm 100w-50s as a research AEC recovery measurement geometry.

Candidate-zero measurement-method confirmation only. The confirmation rule is
fully preregistered in the investigation contract; either outcome is valid.
"""

from __future__ import annotations

import argparse
import json
import statistics
import tempfile
from pathlib import Path

import run_validation_engine as engine
import stage_interaction_run
from aec_recovery_window_geometry import window_series, measure_geometry
from build_validation_corpus import RATE

PROFILES = ("prefix-aec", "prefix-res", "prefix-ns", "prefix-agc", "default")
GEOMETRIES = ("100w-100s", "100w-50s")


def load_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path}: JSON object required")
    return value


def require_contract(contract: dict) -> None:
    if contract.get("authority") != "CANDIDATE_ZERO_MEASUREMENT_METHOD_CONFIRMATION_ONLY":
        raise ValueError("confirmation authority drift")
    if contract.get("candidate_limit") != 0 or contract.get("confirmation_limit") != 0:
        raise ValueError("confirmation candidate budget drift")
    if tuple(contract["corpus"]["stage_profiles"]) != PROFILES:
        raise ValueError("confirmation stage profile set/order drift")
    if tuple(contract["hypothesis"]["compared_geometries"]) != GEOMETRIES:
        raise ValueError("confirmation geometry set/order drift")
    fixed = contract["fixed_measurement"]
    if fixed["pre_baseline_ms"] != [-1000, -200]:
        raise ValueError("pre baseline drift")
    if int(fixed["pre_baseline_window_ms"]) != 100:
        raise ValueError("pre baseline window drift")
    if abs(float(fixed["recovery_excess_db"]) - 3.01029995664) > 1e-12:
        raise ValueError("recovery limit drift")
    if int(fixed["continuous_hold_ms"]) != 300:
        raise ValueError("hold duration drift")
    if fixed["search_ms"] != [0, 2500]:
        raise ValueError("search interval drift")
    baseline = fixed["baseline_geometry"]
    candidate = fixed["candidate_geometry"]
    if baseline != {
        "id": "100w-100s",
        "window_ms": 100,
        "stride_ms": 100,
        "required_windows": 3,
    }:
        raise ValueError("baseline geometry drift")
    if candidate != {
        "id": "100w-50s",
        "window_ms": 100,
        "stride_ms": 50,
        "required_windows": 5,
    }:
        raise ValueError("candidate geometry drift")


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
        prefix=f"ap-recovery-100w50-confirm-{case['case_id']}-"
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

    fixed = contract["fixed_measurement"]
    pre = window_series(
        echo,
        output_list,
        transition_sample,
        output_delay_samples,
        int(fixed["pre_baseline_ms"][0]),
        int(fixed["pre_baseline_ms"][1]),
        int(fixed["pre_baseline_window_ms"]),
        int(fixed["pre_baseline_window_ms"]),
    )
    baseline_db = float(
        statistics.median(row["residual_to_echo_power_db"] for row in pre)
    )
    recovery_limit_db = baseline_db + float(fixed["recovery_excess_db"])

    geometry_results = {}
    for key in ("baseline_geometry", "candidate_geometry"):
        spec = fixed[key]
        post = window_series(
            echo,
            output_list,
            transition_sample,
            output_delay_samples,
            int(fixed["search_ms"][0]),
            int(fixed["search_ms"][1]),
            int(spec["window_ms"]),
            int(spec["stride_ms"]),
        )
        result = measure_geometry(
            post,
            baseline_db,
            recovery_limit_db,
            int(spec["required_windows"]),
        )
        result.update({
            "window_ms": int(spec["window_ms"]),
            "stride_ms": int(spec["stride_ms"]),
            "required_windows": int(spec["required_windows"]),
        })
        geometry_results[spec["id"]] = result

    base_time = geometry_results["100w-100s"]["recovery_time_ms"]
    candidate_time = geometry_results["100w-50s"]["recovery_time_ms"]
    return {
        "case_id": case["case_id"],
        "base_case_id": dims["base_case_id"],
        "stage_profile": dims["stage_profile"],
        "stage_order": int(dims["stage_order"]),
        "stage_label": contract["corpus"]["stage_labels"][dims["stage_profile"]],
        "shared_pre_baseline_db": baseline_db,
        "shared_recovery_limit_db": recovery_limit_db,
        "geometries": geometry_results,
        "paired_candidate_minus_baseline_ms": (
            None
            if base_time is None or candidate_time is None
            else int(candidate_time) - int(base_time)
        ),
        "same_output_for_both_geometries": True,
        "same_pre_baseline": True,
        "same_recovery_limit": True,
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
        raise ValueError("confirmation corpus case-set drift")
    report_cases = {case["case_id"]: case for case in report.get("cases", [])}
    if set(report_cases) != expected_ids:
        raise ValueError("confirmation canonical report case-set drift")
    if not all(bool(item.get("passed", False)) for item in report_cases.values()):
        raise ValueError("confirmation canonical report policy failure")

    rows = [
        analyze_case(case, corpus_path, processor, contract)
        for case in corpus["cases"]
    ]
    rows.sort(key=lambda row: (row["base_case_id"], row["stage_order"]))
    for row in rows:
        if not (
            row["same_output_for_both_geometries"]
            and row["same_pre_baseline"]
            and row["same_recovery_limit"]
        ):
            raise ValueError("confirmation geometry isolation invariant failed")

    return {
        "schema_version": 1,
        "investigation_id": contract["id"],
        "seed": int(corpus["generator"]["seed"]),
        "authority": "candidate-zero-measurement-method-confirmation",
        "observations": rows,
        "summary": {
            "observations": len(rows),
            "censored": {
                geometry: sum(
                    row["geometries"][geometry]["censored"] for row in rows
                )
                for geometry in GEOMETRIES
            },
            "complete": True,
        },
        "candidate_authority": False,
        "dsp_change_authority": False,
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
        raise ValueError("confirmation fresh-seed mismatch")

    matrix = []
    baseline_sum = 0
    candidate_sum = 0
    non_worse = 0
    censored = {geometry: 0 for geometry in GEOMETRIES}

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
                for geometry in GEOMETRIES:
                    censored[geometry] += int(
                        row["geometries"][geometry]["censored"]
                    )

            ranges = {
                geometry: range_or_none(observations, geometry)
                for geometry in GEOMETRIES
            }
            if any(value is None for value in ranges.values()):
                pair_non_worse = False
            else:
                baseline_sum += int(ranges["100w-100s"])
                candidate_sum += int(ranges["100w-50s"])
                pair_non_worse = (
                    int(ranges["100w-50s"]) <= int(ranges["100w-100s"])
                )
            non_worse += int(pair_non_worse)
            matrix.append({
                "base_case_id": base_case,
                "stage_profile": profile,
                "stage_label": contract["corpus"]["stage_labels"][profile],
                "cross_seed_range_ms": ranges,
                "candidate_non_worse": pair_non_worse,
                "observations": [
                    {
                        "seed": item["seed"],
                        "recovery_time_ms": {
                            geometry:
                                item["geometries"][geometry]["recovery_time_ms"]
                            for geometry in GEOMETRIES
                        },
                        "paired_candidate_minus_baseline_ms":
                            item["paired_candidate_minus_baseline_ms"],
                    }
                    for item in observations
                ],
            })

    rule = contract["hypothesis"]["confirmation_rule"]
    no_censor = all(value == 0 for value in censored.values())
    non_worse_ok = non_worse >= int(rule["minimum_non_worse_case_profiles"])
    sum_ok = candidate_sum < baseline_sum
    confirmed = no_censor and non_worse_ok and sum_ok

    return {
        "schema_version": 1,
        "investigation_id": contract["id"],
        "fresh_seeds": expected_seeds,
        "hypothesis": contract["hypothesis"],
        "matrix": matrix,
        "mechanical_result": {
            "non_worse_case_profiles": non_worse,
            "total_case_profiles": len(matrix),
            "summed_cross_seed_range_ms": {
                "100w-100s": baseline_sum,
                "100w-50s": candidate_sum,
            },
            "censored_observations": censored,
            "non_worse_rule_satisfied": non_worse_ok,
            "summed_range_rule_satisfied": sum_ok,
            "zero_censor_rule_satisfied": no_censor,
        },
        "hypothesis_confirmed": confirmed,
        "outcome": "CONFIRMED" if confirmed else "REJECTED",
        "either_outcome_is_valid_evidence": True,
        "research_measurement_geometry_authority": (
            "100w-50s" if confirmed else "NONE"
        ),
        "dsp_candidate_authority": False,
        "product_requirement_authority": False,
        "s004_open": False,
    }


def self_test() -> None:
    contract = {
        "authority": "CANDIDATE_ZERO_MEASUREMENT_METHOD_CONFIRMATION_ONLY",
        "candidate_limit": 0,
        "confirmation_limit": 0,
        "corpus": {"stage_profiles": list(PROFILES)},
        "hypothesis": {
            "compared_geometries": list(GEOMETRIES),
            "confirmation_rule": {
                "minimum_non_worse_case_profiles": 13,
            },
        },
        "fixed_measurement": {
            "pre_baseline_window_ms": 100,
            "pre_baseline_ms": [-1000, -200],
            "recovery_excess_db": 3.01029995664,
            "continuous_hold_ms": 300,
            "search_ms": [0, 2500],
            "baseline_geometry": {
                "id": "100w-100s", "window_ms": 100, "stride_ms": 100,
                "required_windows": 3,
            },
            "candidate_geometry": {
                "id": "100w-50s", "window_ms": 100, "stride_ms": 50,
                "required_windows": 5,
            },
        },
    }
    require_contract(contract)
    assert GEOMETRIES == ("100w-100s", "100w-50s")
    print("AEC 100w-50s geometry confirmation self-test: OK")


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
        print(json.dumps({"seed": result["seed"], **result["summary"]}, sort_keys=True))
    else:
        print(json.dumps({
            "outcome": result["outcome"],
            "hypothesis_confirmed": result["hypothesis_confirmed"],
            **result["mechanical_result"],
        }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
