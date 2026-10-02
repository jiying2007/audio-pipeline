#!/usr/bin/env python3
"""Candidate-zero echo-path RES/NS recovery sign-variability observation."""

from __future__ import annotations

import argparse
import json
import statistics
import tempfile
from pathlib import Path

import aec_echo_path_ns_state_decomposition as ns_state
from aec_recovery_rebaseline_100w50s import analyze_case as analyze_recovery

PROFILES = ("prefix-res", "prefix-ns", "default")
SNAPSHOT_METRICS = (
    "noise_rms_dbfs",
    "speech_probability",
    "noise_estimate_mean_after",
    "noise_estimate_signed_delta_mean",
    "noise_estimate_abs_delta_mean",
    "noise_estimate_abs_update_fraction_of_previous_sum",
    "residual_gain_mean_after",
    "residual_gain_min_after",
    "residual_gain_max_after",
    "residual_gain_signed_delta_mean",
    "residual_gain_abs_delta_mean",
    "overlap_rms_after",
    "previous_rms_after",
    "residual_echo_gain",
    "erle_db",
)


def load_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path}: JSON object required")
    return value


def require_contract(contract: dict) -> None:
    if contract.get("authority") != "CANDIDATE_ZERO_SIGN_VARIABILITY_OBSERVATION_ONLY":
        raise ValueError("sign-variability authority drift")
    if contract.get("candidate_limit") != 0 or contract.get("confirmation_limit") != 0:
        raise ValueError("sign-variability candidate budget drift")
    if tuple(contract["corpus"]["profiles"]) != PROFILES:
        raise ValueError("sign-variability profile set/order drift")
    if contract["measurement"]["geometry_id"] != "100w-50s":
        raise ValueError("sign-variability recovery geometry drift")
    if contract["measurement"]["post_stride_ms"] != 50:
        raise ValueError("sign-variability stride drift")
    if contract["preregistered_rules"]["retain_all_sign_classes"] is not True:
        raise ValueError("sign-class retention disabled")
    if contract["preregistered_rules"]["no_state_family_ranking"] is not True:
        raise ValueError("state-family ranking enabled")
    if contract["preregistered_rules"]["no_root_cause_selection"] is not True:
        raise ValueError("root-cause selection enabled")


def classify_sign(
    res_recovery: dict,
    ns_recovery: dict,
) -> tuple[str, int | None]:
    if bool(res_recovery["censored"]) or bool(ns_recovery["censored"]):
        return "censored", None
    delta = int(ns_recovery["recovery_time_ms"]) - int(res_recovery["recovery_time_ms"])
    if delta >= 50:
        return "extension", delta
    if delta <= -50:
        return "contraction", delta
    if delta == 0:
        return "neutral", delta
    raise ValueError(f"unexpected 50 ms-grid delta: {delta}")


def snapshot(row: dict) -> dict:
    keys = (
        "frame",
        "noise_tracker_frame_after",
        "noise_tracker_frame_mod8_after",
        "frequency_res_active",
        "far_end_active",
        "double_talk_active",
        "aec_converged",
        "erle_valid",
        "estimated_delay_ms",
        "delay_error_samples",
    )
    out = {key: row[key] for key in keys}
    for name in SNAPSHOT_METRICS:
        out[name] = row[name]
    return out


def snapshot_at(
    rows: list[dict],
    frame: int,
) -> dict:
    if frame < 0 or frame >= len(rows):
        raise ValueError(f"snapshot frame out of range: {frame}")
    return snapshot(rows[frame])


def recovery_geometry_view(item: dict) -> dict:
    return {
        "recovery_time_ms": item["recovery_time_ms"],
        "censored": bool(item["censored"]),
        "pre_baseline_db": item["pre_baseline_db"],
        "recovery_limit_db": item["recovery_limit_db"],
        "previous_window_margin_db": item["previous_window_margin_db"],
        "recovery_start_margin_db": item["recovery_start_margin_db"],
        "recovery_hold_max_margin_db": item["recovery_hold_max_margin_db"],
    }


def analyze_seed(
    corpus_path: Path,
    report_path: Path,
    processor: Path,
    state_probe: Path,
    contract: dict,
    trace_output: Path,
) -> dict:
    require_contract(contract)
    corpus = load_json(corpus_path)
    report = load_json(report_path)
    expected_ids = {f"echo-path-change--{profile}" for profile in PROFILES}
    cases = {case["case_id"]: case for case in corpus["cases"]}
    if set(cases) != expected_ids:
        raise ValueError("sign-variability corpus case-set drift")
    report_cases = {case["case_id"]: case for case in report.get("cases", [])}
    if set(report_cases) != expected_ids:
        raise ValueError("sign-variability report case-set drift")
    if not all(bool(item.get("passed", False)) for item in report_cases.values()):
        raise ValueError("sign-variability canonical policy failure")

    res_case = cases["echo-path-change--prefix-res"]
    ns_case = cases["echo-path-change--prefix-ns"]
    full_case = cases["echo-path-change--default"]

    res_recovery = analyze_recovery(res_case, corpus_path, processor, contract)
    ns_recovery = analyze_recovery(ns_case, corpus_path, processor, contract)
    full_recovery = analyze_recovery(full_case, corpus_path, processor, contract)
    sign_class, delta = classify_sign(res_recovery, ns_recovery)

    with tempfile.TemporaryDirectory(prefix="ap-sign-variability-") as raw:
        root = Path(raw)
        reference = ns_state.standard_output(
            processor, corpus_path, ns_case, root / "reference"
        )
        observed, rows = ns_state.run_state_probe(
            state_probe, corpus_path, ns_case, root / "probe"
        )
    equivalent = reference == observed
    trace_output.parent.mkdir(parents=True, exist_ok=True)
    trace_output.write_text(
        "\n".join(json.dumps(row, sort_keys=True) for row in rows) + "\n",
        encoding="utf-8",
    )

    transition_frame = int(ns_case["control"]["echo_path_change_frame"])
    frame_ms = 10
    fixed_snapshots = {}
    for offset_ms in contract["state_probe"]["fixed_transition_relative_snapshots_ms"]:
        if int(offset_ms) % frame_ms != 0:
            raise ValueError("fixed snapshot offset is not frame-aligned")
        frame = transition_frame + int(offset_ms) // frame_ms
        fixed_snapshots[str(offset_ms)] = snapshot_at(rows, frame)

    boundary_snapshots = {}
    for label, recovery in (("res", res_recovery), ("ns", ns_recovery)):
        if recovery["recovery_time_ms"] is None:
            boundary_snapshots[label] = None
            continue
        recovery_ms = int(recovery["recovery_time_ms"])
        if recovery_ms % frame_ms != 0:
            raise ValueError("recovery boundary is not frame-aligned")
        frame = transition_frame + recovery_ms // frame_ms
        boundary_snapshots[label] = snapshot_at(rows, frame)

    return {
        "schema_version": 1,
        "investigation_id": contract["id"],
        "seed": int(corpus["generator"]["seed"]),
        "authority": "candidate-zero-sign-variability-observation-only",
        "probe_output_bitwise_equivalent": equivalent,
        "transition_frame": transition_frame,
        "sign_class": sign_class,
        "ns_minus_res_ms": delta,
        "recovery": {
            "RES": recovery_geometry_view(res_recovery),
            "NS": recovery_geometry_view(ns_recovery),
            "full": recovery_geometry_view(full_recovery),
        },
        "fixed_transition_relative_snapshots": fixed_snapshots,
        "ns_state_at_recovery_boundaries": boundary_snapshots,
        "candidate_authority": False,
        "root_cause_claim_authority": False,
    }


def scalar_summary(values: list[float]) -> dict:
    if not values:
        return {"count": 0}
    return {
        "count": len(values),
        "median": float(statistics.median(values)),
        "min": min(values),
        "max": max(values),
    }


def aggregate(items: list[dict], contract: dict) -> dict:
    require_contract(contract)
    expected = sorted(int(x) for x in contract["corpus"]["fresh_seeds"])
    by_seed = {int(item["seed"]): item for item in items}
    if sorted(by_seed) != expected:
        raise ValueError("sign-variability fresh-seed mismatch")
    equivalence = all(
        by_seed[seed]["probe_output_bitwise_equivalent"] for seed in expected
    )

    classes = ("extension", "neutral", "contraction", "censored")
    distribution = {
        key: [seed for seed in expected if by_seed[seed]["sign_class"] == key]
        for key in classes
    }

    fixed_time_by_class = {}
    for offset_ms in contract["state_probe"]["fixed_transition_relative_snapshots_ms"]:
        offset = str(offset_ms)
        fixed_time_by_class[offset] = {}
        for sign_class in classes:
            seeds = distribution[sign_class]
            summaries = {}
            for metric in SNAPSHOT_METRICS:
                values = [
                    float(
                        by_seed[seed]["fixed_transition_relative_snapshots"]
                        [offset][metric]
                    )
                    for seed in seeds
                ]
                summaries[metric] = scalar_summary(values)
            fixed_time_by_class[offset][sign_class] = {
                "seeds": seeds,
                "metrics": summaries,
            }

    return {
        "schema_version": 1,
        "investigation_id": contract["id"],
        "fresh_seeds": expected,
        "probe_output_bitwise_equivalent_all_seeds": equivalence,
        "sign_distribution": distribution,
        "extension_ms_by_seed": {
            str(seed): by_seed[seed]["ns_minus_res_ms"] for seed in expected
        },
        "recovery_geometry_by_seed": {
            str(seed): by_seed[seed]["recovery"] for seed in expected
        },
        "fixed_transition_relative_state_by_sign_class": fixed_time_by_class,
        "all_seed_receipts": [by_seed[seed] for seed in expected],
        "state_family_ranking": "NOT_AUTHORIZED",
        "root_cause_attribution": "NOT_AUTHORIZED",
        "candidate_authority": False,
        "s004_open": False,
    }


def self_test() -> None:
    extension, delta = classify_sign(
        {"censored": False, "recovery_time_ms": 150},
        {"censored": False, "recovery_time_ms": 200},
    )
    assert extension == "extension" and delta == 50
    contraction, delta = classify_sign(
        {"censored": False, "recovery_time_ms": 250},
        {"censored": False, "recovery_time_ms": 200},
    )
    assert contraction == "contraction" and delta == -50
    neutral, delta = classify_sign(
        {"censored": False, "recovery_time_ms": 200},
        {"censored": False, "recovery_time_ms": 200},
    )
    assert neutral == "neutral" and delta == 0
    censored, delta = classify_sign(
        {"censored": True, "recovery_time_ms": None},
        {"censored": False, "recovery_time_ms": 200},
    )
    assert censored == "censored" and delta is None
    print("echo-path recovery sign variability self-test: OK")


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("self-test")
    run_p = sub.add_parser("run")
    run_p.add_argument("--corpus", type=Path, required=True)
    run_p.add_argument("--report", type=Path, required=True)
    run_p.add_argument("--processor", type=Path, required=True)
    run_p.add_argument("--state-probe", type=Path, required=True)
    run_p.add_argument("--contract", type=Path, required=True)
    run_p.add_argument("--trace-output", type=Path, required=True)
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
        result = analyze_seed(
            args.corpus,
            args.report,
            args.processor,
            args.state_probe,
            contract,
            args.trace_output,
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
            "sign_class": result["sign_class"],
            "ns_minus_res_ms": result["ns_minus_res_ms"],
            "probe_output_bitwise_equivalent":
                result["probe_output_bitwise_equivalent"],
        }, sort_keys=True))
    else:
        print(json.dumps({
            "sign_distribution": result["sign_distribution"],
            "extension_ms_by_seed": result["extension_ms_by_seed"],
            "probe_output_bitwise_equivalent_all_seeds":
                result["probe_output_bitwise_equivalent_all_seeds"],
        }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
