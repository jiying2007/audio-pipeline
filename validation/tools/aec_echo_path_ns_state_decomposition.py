#!/usr/bin/env python3
"""Candidate-zero echo-path NS internal-state decomposition.

The state probe is test-only and must be bitwise output-equivalent to the
standard stage-prefix processor. State traces are descriptive only.
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
import subprocess
import tempfile
from pathlib import Path

import run_validation_engine as engine
import stage_interaction_run
from aec_recovery_rebaseline_100w50s import analyze_case as analyze_recovery

PROFILES = ("prefix-res", "prefix-ns", "default")
STATE_METRICS = (
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
    if contract.get("authority") != "CANDIDATE_ZERO_INTERNAL_STATE_OBSERVATION_ONLY":
        raise ValueError("NS state authority drift")
    if contract.get("candidate_limit") != 0 or contract.get("confirmation_limit") != 0:
        raise ValueError("NS state candidate budget drift")
    if tuple(contract["corpus"]["profiles"]) != PROFILES:
        raise ValueError("NS state profile set/order drift")
    if contract["measurement"]["geometry_id"] != "100w-50s":
        raise ValueError("NS state recovery geometry drift")
    if contract["state_windows"]["frame_duration_ms"] != 10:
        raise ValueError("NS state frame duration drift")
    if contract["preregistered_rules"]["no_state_threshold_fitting"] is not True:
        raise ValueError("state threshold fitting enabled")
    if contract["preregistered_rules"]["no_state_family_ranking"] is not True:
        raise ValueError("state family ranking enabled")


def read_jsonl(path: Path) -> list[dict]:
    rows = [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if not rows:
        raise ValueError("NS state trace is empty")
    frames = [int(row["frame"]) for row in rows]
    if frames != list(range(len(rows))):
        raise ValueError("NS state trace frame sequence drift")
    return rows


def run_state_probe(
    probe: Path,
    corpus_path: Path,
    case: dict,
    work: Path,
) -> tuple[list[int], list[dict]]:
    work.mkdir(parents=True, exist_ok=True)
    mic = engine.resolve(corpus_path, case.get("mic_audio"))
    render = engine.resolve(corpus_path, case.get("render_audio"))
    if mic is None or render is None:
        raise ValueError("NS state probe requires mic and render")
    control = case.get("control", {})
    change_frame = control.get("echo_path_change_frame")
    if change_frame is None:
        raise ValueError("echo-path change frame missing")
    out = work / "state-probe-out.pcm"
    trace = work / "ns-state.jsonl"
    command = [
        str(probe),
        "--sample-rate", str(int(case["sample_rate_hz"])),
        "--mic-channels", str(int(case["mic_channels"])),
        "--state-jsonl", str(trace),
        "--echo-path-change-frame", str(int(change_frame)),
        str(mic), str(render), str(out),
    ]
    subprocess.run(command, check=True)
    return [int(x) for x in engine.read_raw_array(out)], read_jsonl(trace)


def standard_output(
    processor: Path,
    corpus_path: Path,
    case: dict,
    work: Path,
) -> list[int]:
    work.mkdir(parents=True, exist_ok=True)
    output, _trace, _inputs = stage_interaction_run.invoke(
        processor, case, corpus_path, work
    )
    return [int(x) for x in output]


def row_at(rows: list[dict], frame: int) -> dict:
    if frame < 0 or frame >= len(rows):
        raise ValueError(f"state snapshot frame out of range: {frame}")
    return rows[frame]


def numeric_summary(rows: list[dict]) -> dict:
    if not rows:
        return {"frames": 0}
    out: dict[str, object] = {"frames": len(rows)}
    for name in STATE_METRICS:
        values = [float(row[name]) for row in rows]
        if not all(math.isfinite(value) for value in values):
            raise ValueError(f"non-finite state metric: {name}")
        out[name] = {
            "first": values[0],
            "last": values[-1],
            "delta_last_minus_first": values[-1] - values[0],
            "median": float(statistics.median(values)),
            "min": min(values),
            "max": max(values),
        }
    out["frequency_res_active_fraction"] = (
        sum(int(row["frequency_res_active"]) for row in rows) / len(rows)
    )
    out["far_end_active_fraction"] = (
        sum(int(row["far_end_active"]) for row in rows) / len(rows)
    )
    out["double_talk_active_fraction"] = (
        sum(int(row["double_talk_active"]) for row in rows) / len(rows)
    )
    return out


def boundary_snapshot(row: dict) -> dict:
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
    for name in STATE_METRICS:
        out[name] = row[name]
    return out


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
        raise ValueError("NS state corpus case-set drift")
    report_cases = {case["case_id"]: case for case in report.get("cases", [])}
    if set(report_cases) != expected_ids:
        raise ValueError("NS state canonical report case-set drift")
    if not all(bool(item.get("passed", False)) for item in report_cases.values()):
        raise ValueError("NS state canonical policy failure")

    res_case = cases["echo-path-change--prefix-res"]
    ns_case = cases["echo-path-change--prefix-ns"]
    res_recovery = analyze_recovery(res_case, corpus_path, processor, contract)
    ns_recovery = analyze_recovery(ns_case, corpus_path, processor, contract)

    with tempfile.TemporaryDirectory(prefix="ap-ns-state-equivalence-") as raw:
        root = Path(raw)
        reference = standard_output(processor, corpus_path, ns_case, root / "reference")
        observed, rows = run_state_probe(state_probe, corpus_path, ns_case, root / "probe")
    equivalent = reference == observed
    trace_output.parent.mkdir(parents=True, exist_ok=True)
    trace_output.write_text(
        "\n".join(json.dumps(row, sort_keys=True) for row in rows) + "\n",
        encoding="utf-8",
    )

    res_time = res_recovery["recovery_time_ms"]
    ns_time = ns_recovery["recovery_time_ms"]
    res_censored = bool(res_recovery["censored"])
    ns_censored = bool(ns_recovery["censored"])
    delta = (
        None
        if res_censored or ns_censored
        else int(ns_time) - int(res_time)
    )
    applicable = delta is not None and delta >= 50

    transition_frame = int(ns_case["control"]["echo_path_change_frame"])
    frame_ms = int(contract["state_windows"]["frame_duration_ms"])
    pre_start_ms, pre_end_ms = contract["state_windows"]["pre_transition_ms"]
    pre_start = transition_frame + int(pre_start_ms) // frame_ms
    pre_end = transition_frame + int(pre_end_ms) // frame_ms

    receipt = {
        "schema_version": 1,
        "investigation_id": contract["id"],
        "seed": int(corpus["generator"]["seed"]),
        "authority": "candidate-zero-internal-state-observation-only",
        "probe_output_bitwise_equivalent": equivalent,
        "transition_frame": transition_frame,
        "res_recovery": res_recovery,
        "ns_recovery": ns_recovery,
        "ns_minus_res_ms": delta,
        "state_decomposition_applicable": applicable,
        "pre_transition_summary": numeric_summary(rows[pre_start:pre_end]),
        "transition_snapshot": boundary_snapshot(row_at(rows, transition_frame)),
        "candidate_authority": False,
        "root_cause_claim_authority": False,
    }

    if applicable:
        if int(res_time) % frame_ms != 0 or int(ns_time) % frame_ms != 0:
            raise ValueError("recovery boundary is not frame-aligned")
        res_frame = transition_frame + int(res_time) // frame_ms
        ns_frame = transition_frame + int(ns_time) // frame_ms
        post_end = min(
            len(rows),
            ns_frame + int(contract["state_windows"]["post_ns_recovery_ms"][1]) // frame_ms,
        )
        receipt.update({
            "res_recovery_frame": res_frame,
            "ns_recovery_frame": ns_frame,
            "res_recovery_snapshot": boundary_snapshot(row_at(rows, res_frame)),
            "ns_recovery_snapshot": boundary_snapshot(row_at(rows, ns_frame)),
            "extension_summary": numeric_summary(rows[res_frame:ns_frame]),
            "post_ns_recovery_summary": numeric_summary(rows[ns_frame:post_end]),
        })
    else:
        receipt["non_applicability_reason"] = (
            "fresh RES-to-NS extension did not reproduce at >=50 ms"
        )

    return receipt


def aggregate(items: list[dict], contract: dict) -> dict:
    require_contract(contract)
    expected = sorted(int(x) for x in contract["corpus"]["fresh_seeds"])
    by_seed = {int(item["seed"]): item for item in items}
    if sorted(by_seed) != expected:
        raise ValueError("NS state fresh-seed mismatch")

    applicable = [by_seed[seed] for seed in expected if by_seed[seed]["state_decomposition_applicable"]]
    equivalence = all(by_seed[seed]["probe_output_bitwise_equivalent"] for seed in expected)
    metric_deltas: dict[str, list[dict]] = {}
    for name in STATE_METRICS:
        values = []
        for item in applicable:
            left = float(item["res_recovery_snapshot"][name])
            right = float(item["ns_recovery_snapshot"][name])
            values.append({
                "seed": item["seed"],
                "res_boundary": left,
                "ns_boundary": right,
                "ns_minus_res": right - left,
            })
        metric_deltas[name] = values

    tracker_phase = [
        {
            "seed": item["seed"],
            "res_mod8": int(item["res_recovery_snapshot"]["noise_tracker_frame_mod8_after"]),
            "ns_mod8": int(item["ns_recovery_snapshot"]["noise_tracker_frame_mod8_after"]),
            "extension_ms": int(item["ns_minus_res_ms"]),
        }
        for item in applicable
    ]

    return {
        "schema_version": 1,
        "investigation_id": contract["id"],
        "fresh_seeds": expected,
        "probe_output_bitwise_equivalent_all_seeds": equivalence,
        "applicable_seed_count": len(applicable),
        "non_applicable_seeds": [
            seed for seed in expected if not by_seed[seed]["state_decomposition_applicable"]
        ],
        "extension_ms_by_seed": {
            str(seed): by_seed[seed]["ns_minus_res_ms"] for seed in expected
        },
        "boundary_state_deltas": metric_deltas,
        "tracker_phase_at_recovery_boundaries": tracker_phase,
        "full_trace_retained": True,
        "state_family_ranking": "NOT_AUTHORIZED",
        "root_cause_attribution": "NOT_AUTHORIZED",
        "candidate_authority": False,
        "s004_open": False,
    }


def self_test() -> None:
    rows = [
        {
            name: float(index + 1)
            for name in STATE_METRICS
        } | {
            "frequency_res_active": 1,
            "far_end_active": 1,
            "double_talk_active": 0,
        }
        for index in range(3)
    ]
    summary = numeric_summary(rows)
    assert summary["frames"] == 3
    assert summary["noise_rms_dbfs"]["delta_last_minus_first"] == 2.0
    print("echo-path NS state decomposition self-test: OK")


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
            args.corpus, args.report, args.processor, args.state_probe,
            contract, args.trace_output,
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
            "probe_output_bitwise_equivalent": result["probe_output_bitwise_equivalent"],
            "ns_minus_res_ms": result["ns_minus_res_ms"],
            "state_decomposition_applicable": result["state_decomposition_applicable"],
        }, sort_keys=True))
    else:
        print(json.dumps({
            "probe_output_bitwise_equivalent_all_seeds":
                result["probe_output_bitwise_equivalent_all_seeds"],
            "applicable_seed_count": result["applicable_seed_count"],
            "extension_ms_by_seed": result["extension_ms_by_seed"],
        }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
