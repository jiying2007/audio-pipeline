#!/usr/bin/env python3
"""Rebaseline AEC transition recovery using confirmed 100w-50s research geometry.

Candidate-zero only. Retention requires a non-zero adjacent-stage recovery delta
with the same direction on every fresh seed.
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
LABELS = ("AEC", "RES", "NS", "AGC", "full")
BOUNDARIES = (("AEC", "RES"), ("RES", "NS"), ("NS", "AGC"), ("AGC", "full"))


def load_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path}: JSON object required")
    return value


def require_contract(contract: dict) -> None:
    if contract.get("authority") != "CANDIDATE_ZERO_REBASELINE_ONLY":
        raise ValueError("rebaseline authority drift")
    if contract.get("candidate_limit") != 0 or contract.get("confirmation_limit") != 0:
        raise ValueError("rebaseline candidate budget drift")
    if tuple(contract["corpus"]["stage_profiles"]) != PROFILES:
        raise ValueError("rebaseline stage profile set/order drift")
    labels = tuple(contract["corpus"]["stage_labels"][profile] for profile in PROFILES)
    if labels != LABELS:
        raise ValueError("rebaseline stage labels drift")
    if tuple(tuple(x) for x in contract["adjacent_boundaries"]) != BOUNDARIES:
        raise ValueError("rebaseline boundary set drift")
    m = contract["measurement"]
    expected = {
        "geometry_id": "100w-50s",
        "post_window_ms": 100,
        "post_stride_ms": 50,
        "pre_baseline_window_ms": 100,
        "pre_baseline_ms": [-1000, -200],
        "recovery_excess_db": 3.01029995664,
        "continuous_hold_ms": 300,
        "required_windows_for_300ms_coverage": 5,
        "search_ms": [0, 2500],
    }
    for key, value in expected.items():
        if m[key] != value:
            raise ValueError(f"rebaseline measurement drift: {key}")


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

    with tempfile.TemporaryDirectory(prefix=f"ap-rebaseline-{case['case_id']}-") as raw:
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

    m = contract["measurement"]
    pre = window_series(
        echo,
        output_list,
        transition_sample,
        output_delay_samples,
        int(m["pre_baseline_ms"][0]),
        int(m["pre_baseline_ms"][1]),
        int(m["pre_baseline_window_ms"]),
        int(m["pre_baseline_window_ms"]),
    )
    baseline = float(statistics.median(
        row["residual_to_echo_power_db"] for row in pre
    ))
    recovery_limit = baseline + float(m["recovery_excess_db"])
    post = window_series(
        echo,
        output_list,
        transition_sample,
        output_delay_samples,
        int(m["search_ms"][0]),
        int(m["search_ms"][1]),
        int(m["post_window_ms"]),
        int(m["post_stride_ms"]),
    )
    measured = measure_geometry(
        post,
        baseline,
        recovery_limit,
        int(m["required_windows_for_300ms_coverage"]),
    )
    return {
        "case_id": case["case_id"],
        "base_case_id": dims["base_case_id"],
        "stage_profile": dims["stage_profile"],
        "stage_order": int(dims["stage_order"]),
        "stage_label": contract["corpus"]["stage_labels"][dims["stage_profile"]],
        "algorithmic_latency_ms": latency_ms,
        "pre_baseline_db": baseline,
        "recovery_limit_db": recovery_limit,
        "recovery_time_ms": measured["recovery_time_ms"],
        "censored": measured["censored"],
        "previous_window_margin_db": measured["previous_window_margin_db"],
        "recovery_start_margin_db": measured["recovery_start_margin_db"],
        "recovery_hold_max_margin_db": measured["recovery_hold_max_margin_db"],
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
        raise ValueError("rebaseline corpus case-set drift")
    report_cases = {case["case_id"]: case for case in report.get("cases", [])}
    if set(report_cases) != expected_ids:
        raise ValueError("rebaseline canonical report case-set drift")
    if not all(bool(item.get("passed", False)) for item in report_cases.values()):
        raise ValueError("rebaseline canonical report policy failure")

    rows = [
        analyze_case(case, corpus_path, processor, contract)
        for case in corpus["cases"]
    ]
    rows.sort(key=lambda row: (row["base_case_id"], row["stage_order"]))

    cases_out = []
    for base_case in contract["corpus"]["target_cases"]:
        stages = [row for row in rows if row["base_case_id"] == base_case]
        if tuple(row["stage_label"] for row in stages) != LABELS:
            raise ValueError(f"{base_case}: stage label order drift")
        by_label = {row["stage_label"]: row for row in stages}
        deltas = []
        for left, right in BOUNDARIES:
            a = by_label[left]
            b = by_label[right]
            delta = (
                None
                if a["censored"] or b["censored"]
                else int(b["recovery_time_ms"]) - int(a["recovery_time_ms"])
            )
            deltas.append({
                "from_stage": left,
                "to_stage": right,
                "delta_ms": delta,
                "from_recovery_time_ms": a["recovery_time_ms"],
                "to_recovery_time_ms": b["recovery_time_ms"],
            })
        cases_out.append({
            "base_case_id": base_case,
            "stages": stages,
            "adjacent_stage_deltas": deltas,
        })

    return {
        "schema_version": 1,
        "investigation_id": contract["id"],
        "seed": int(corpus["generator"]["seed"]),
        "authority": "candidate-zero-100w50s-rebaseline-only",
        "geometry_id": "100w-50s",
        "cases": cases_out,
        "summary": {
            "base_cases": len(cases_out),
            "stage_observations": len(rows),
            "censored_observations": sum(row["censored"] for row in rows),
            "complete": True,
        },
        "candidate_authority": False,
        "causal_stage_authority": False,
    }


def classify_boundary(deltas: list[int | None], minimum: int) -> str:
    if any(value is None for value in deltas):
        return "variable"
    values = [int(x) for x in deltas]
    if all(value >= minimum for value in values):
        return "repeatable_extension"
    if all(value <= -minimum for value in values):
        return "repeatable_contraction"
    if all(value == 0 for value in values):
        return "stable_zero"
    return "variable"


def aggregate(items: list[dict], contract: dict) -> dict:
    require_contract(contract)
    expected_seeds = sorted(int(x) for x in contract["corpus"]["fresh_seeds"])
    by_seed = {int(item["seed"]): item for item in items}
    if sorted(by_seed) != expected_seeds:
        raise ValueError("rebaseline fresh-seed mismatch")
    minimum = int(contract["retention_rule"]["minimum_nonzero_delta_ms"])

    matrix = []
    retained = []
    for base_case in contract["corpus"]["target_cases"]:
        for left, right in BOUNDARIES:
            observations = []
            for seed in expected_seeds:
                case = next(
                    x for x in by_seed[seed]["cases"]
                    if x["base_case_id"] == base_case
                )
                delta = next(
                    x for x in case["adjacent_stage_deltas"]
                    if x["from_stage"] == left and x["to_stage"] == right
                )
                observations.append({"seed": seed, **delta})
            deltas = [item["delta_ms"] for item in observations]
            classification = classify_boundary(deltas, minimum)
            row = {
                "base_case_id": base_case,
                "from_stage": left,
                "to_stage": right,
                "observations": observations,
                "classification": classification,
                "retained_nonzero_phenomenon": classification in {
                    "repeatable_extension",
                    "repeatable_contraction",
                },
            }
            matrix.append(row)
            if row["retained_nonzero_phenomenon"]:
                retained.append({
                    "base_case_id": base_case,
                    "from_stage": left,
                    "to_stage": right,
                    "classification": classification,
                    "delta_ms": deltas,
                })

    full_ranges = {}
    for base_case in contract["corpus"]["target_cases"]:
        values = []
        for seed in expected_seeds:
            case = next(
                x for x in by_seed[seed]["cases"]
                if x["base_case_id"] == base_case
            )
            full = next(x for x in case["stages"] if x["stage_label"] == "full")
            if full["recovery_time_ms"] is not None:
                values.append(int(full["recovery_time_ms"]))
        full_ranges[base_case] = None if not values else max(values) - min(values)

    return {
        "schema_version": 1,
        "investigation_id": contract["id"],
        "fresh_seeds": expected_seeds,
        "geometry_id": "100w-50s",
        "boundary_matrix": matrix,
        "retained_nonzero_phenomena": retained,
        "retained_nonzero_phenomenon_count": len(retained),
        "full_pipeline_cross_seed_range_ms": full_ranges,
        "all_measurements_complete": True,
        "candidate_authority": False,
        "causal_attribution": "NOT_AUTHORIZED",
        "s004_open": False,
    }


def self_test() -> None:
    contract = {
        "authority": "CANDIDATE_ZERO_REBASELINE_ONLY",
        "candidate_limit": 0,
        "confirmation_limit": 0,
        "corpus": {
            "stage_profiles": list(PROFILES),
            "stage_labels": dict(zip(PROFILES, LABELS)),
        },
        "adjacent_boundaries": [list(x) for x in BOUNDARIES],
        "measurement": {
            "geometry_id": "100w-50s",
            "post_window_ms": 100,
            "post_stride_ms": 50,
            "pre_baseline_window_ms": 100,
            "pre_baseline_ms": [-1000, -200],
            "recovery_excess_db": 3.01029995664,
            "continuous_hold_ms": 300,
            "required_windows_for_300ms_coverage": 5,
            "search_ms": [0, 2500],
        },
    }
    require_contract(contract)
    assert classify_boundary([50, 100, 50, 50], 50) == "repeatable_extension"
    assert classify_boundary([-50, -100, -50, -50], 50) == "repeatable_contraction"
    assert classify_boundary([0, 0, 0, 0], 50) == "stable_zero"
    assert classify_boundary([0, 50, 0, 50], 50) == "variable"
    print("AEC 100w-50s rebaseline self-test: OK")


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
            "recovery_ms": {
                f"{case['base_case_id']}::{stage['stage_label']}":
                    stage["recovery_time_ms"]
                for case in result["cases"]
                for stage in case["stages"]
            },
        }, sort_keys=True))
    else:
        print(json.dumps({
            "retained_nonzero_phenomenon_count":
                result["retained_nonzero_phenomenon_count"],
            "retained_nonzero_phenomena": result["retained_nonzero_phenomena"],
            "full_pipeline_cross_seed_range_ms":
                result["full_pipeline_cross_seed_range_ms"],
        }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
