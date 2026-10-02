#!/usr/bin/env python3
"""Candidate-zero echo-path RES-side recovery variability observation."""

from __future__ import annotations

import argparse
import json
import statistics
import subprocess
import tempfile
from pathlib import Path

import run_validation_engine as engine
import stage_interaction_run
from aec_recovery_rebaseline_100w50s import analyze_case as analyze_recovery

PROFILES = ("prefix-res", "prefix-ns", "default")
SNAPSHOT_METRICS = (
    "erle_db",
    "res_gain_before",
    "res_gain_after",
    "res_gain_delta",
    "post_res_rms",
    "pre_res_rms_recovered",
    "echo_estimate_rms",
)


def load_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path}: JSON object required")
    return value


def require_contract(contract: dict) -> None:
    if contract.get("authority") != "CANDIDATE_ZERO_RES_SIDE_OBSERVATION_ONLY":
        raise ValueError("RES-side authority drift")
    if contract.get("candidate_limit") != 0 or contract.get("confirmation_limit") != 0:
        raise ValueError("RES-side candidate budget drift")
    if tuple(contract["corpus"]["profiles"]) != PROFILES:
        raise ValueError("RES-side profile set/order drift")
    if contract["measurement"]["geometry_id"] != "100w-50s":
        raise ValueError("RES-side recovery geometry drift")
    if contract["measurement"]["post_stride_ms"] != 50:
        raise ValueError("RES-side stride drift")
    rules = contract["preregistered_rules"]
    for key in (
        "retain_all_sign_classes",
        "non_positive_sign_is_valid_evidence",
        "no_sign_bucket_selection_for_candidate",
        "no_res_state_threshold_fitting",
        "no_state_family_ranking",
        "no_root_cause_selection",
        "no_recovery_threshold_search",
        "no_res_parameter_search",
        "no_aec_parameter_search",
        "no_ns_parameter_search",
    ):
        if rules[key] is not True:
            raise ValueError(f"RES-side rule drift: {key}")


def read_jsonl(path: Path) -> list[dict]:
    rows = [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if not rows:
        raise ValueError("RES state trace is empty")
    frames = [int(row["frame"]) for row in rows]
    if frames != list(range(len(rows))):
        raise ValueError("RES state trace frame sequence drift")
    return rows


def run_res_probe(
    probe: Path,
    corpus_path: Path,
    case: dict,
    work: Path,
) -> tuple[list[int], list[dict]]:
    work.mkdir(parents=True, exist_ok=True)
    mic = engine.resolve(corpus_path, case.get("mic_audio"))
    render = engine.resolve(corpus_path, case.get("render_audio"))
    if mic is None or render is None:
        raise ValueError("RES state probe requires mic and render")
    change_frame = case.get("control", {}).get("echo_path_change_frame")
    if change_frame is None:
        raise ValueError("echo-path change frame missing")
    out = work / "res-probe-out.pcm"
    trace = work / "res-state.jsonl"
    subprocess.run(
        [
            str(probe),
            "--sample-rate", str(int(case["sample_rate_hz"])),
            "--mic-channels", str(int(case["mic_channels"])),
            "--state-jsonl", str(trace),
            "--echo-path-change-frame", str(int(change_frame)),
            str(mic), str(render), str(out),
        ],
        check=True,
    )
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


def classify_sign(res_recovery: dict, ns_recovery: dict) -> tuple[str, int | None]:
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


def recovery_view(item: dict) -> dict:
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
    res_probe: Path,
    contract: dict,
    trace_output: Path,
) -> dict:
    require_contract(contract)
    corpus = load_json(corpus_path)
    report = load_json(report_path)
    expected_ids = {f"echo-path-change--{profile}" for profile in PROFILES}
    cases = {case["case_id"]: case for case in corpus["cases"]}
    if set(cases) != expected_ids:
        raise ValueError("RES-side corpus case-set drift")
    report_cases = {case["case_id"]: case for case in report.get("cases", [])}
    if set(report_cases) != expected_ids:
        raise ValueError("RES-side report case-set drift")
    if not all(bool(item.get("passed", False)) for item in report_cases.values()):
        raise ValueError("RES-side canonical policy failure")

    res_case = cases["echo-path-change--prefix-res"]
    ns_case = cases["echo-path-change--prefix-ns"]
    full_case = cases["echo-path-change--default"]
    res_recovery = analyze_recovery(res_case, corpus_path, processor, contract)
    ns_recovery = analyze_recovery(ns_case, corpus_path, processor, contract)
    full_recovery = analyze_recovery(full_case, corpus_path, processor, contract)
    sign_class, delta = classify_sign(res_recovery, ns_recovery)

    with tempfile.TemporaryDirectory(prefix="ap-res-side-") as raw:
        root = Path(raw)
        reference = standard_output(processor, corpus_path, res_case, root / "reference")
        observed, rows = run_res_probe(res_probe, corpus_path, res_case, root / "probe")
    equivalent = reference == observed
    trace_output.parent.mkdir(parents=True, exist_ok=True)
    trace_output.write_text(
        "\n".join(json.dumps(row, sort_keys=True) for row in rows) + "\n",
        encoding="utf-8",
    )

    transition_frame = int(res_case["control"]["echo_path_change_frame"])
    frame_ms = 10
    fixed_snapshots = {}
    for offset_ms in contract["res_probe"]["fixed_transition_relative_snapshots_ms"]:
        frame = transition_frame + int(offset_ms) // frame_ms
        if int(offset_ms) % frame_ms != 0 or frame < 0 or frame >= len(rows):
            raise ValueError(f"invalid fixed snapshot offset: {offset_ms}")
        fixed_snapshots[str(offset_ms)] = snapshot(rows[frame])

    res_boundary = None
    if res_recovery["recovery_time_ms"] is not None:
        recovery_ms = int(res_recovery["recovery_time_ms"])
        if recovery_ms % frame_ms != 0:
            raise ValueError("RES recovery boundary not frame-aligned")
        frame = transition_frame + recovery_ms // frame_ms
        res_boundary = snapshot(rows[frame])

    return {
        "schema_version": 1,
        "investigation_id": contract["id"],
        "seed": int(corpus["generator"]["seed"]),
        "authority": "candidate-zero-res-side-observation-only",
        "probe_output_bitwise_equivalent": equivalent,
        "transition_frame": transition_frame,
        "sign_class": sign_class,
        "ns_minus_res_ms": delta,
        "recovery": {
            "RES": recovery_view(res_recovery),
            "NS": recovery_view(ns_recovery),
            "full": recovery_view(full_recovery),
        },
        "fixed_transition_relative_snapshots": fixed_snapshots,
        "res_state_at_res_recovery_boundary": res_boundary,
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
        raise ValueError("RES-side fresh-seed mismatch")
    equivalence = all(
        by_seed[seed]["probe_output_bitwise_equivalent"] for seed in expected
    )

    classes = ("extension", "neutral", "contraction", "censored")
    distribution = {
        key: [seed for seed in expected if by_seed[seed]["sign_class"] == key]
        for key in classes
    }

    fixed_by_class = {}
    for offset_ms in contract["res_probe"]["fixed_transition_relative_snapshots_ms"]:
        offset = str(offset_ms)
        fixed_by_class[offset] = {}
        for sign_class in classes:
            seeds = distribution[sign_class]
            metrics = {}
            for metric in SNAPSHOT_METRICS:
                values = [
                    float(by_seed[seed]["fixed_transition_relative_snapshots"][offset][metric])
                    for seed in seeds
                ]
                metrics[metric] = scalar_summary(values)
            fixed_by_class[offset][sign_class] = {
                "seeds": seeds,
                "metrics": metrics,
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
        "fixed_transition_relative_res_state_by_sign_class": fixed_by_class,
        "all_seed_receipts": [by_seed[seed] for seed in expected],
        "state_family_ranking": "NOT_AUTHORIZED",
        "root_cause_attribution": "NOT_AUTHORIZED",
        "candidate_authority": False,
        "s004_open": False,
    }


def self_test() -> None:
    assert classify_sign(
        {"censored": False, "recovery_time_ms": 150},
        {"censored": False, "recovery_time_ms": 200},
    ) == ("extension", 50)
    assert classify_sign(
        {"censored": False, "recovery_time_ms": 250},
        {"censored": False, "recovery_time_ms": 250},
    ) == ("neutral", 0)
    assert classify_sign(
        {"censored": False, "recovery_time_ms": 300},
        {"censored": False, "recovery_time_ms": 250},
    ) == ("contraction", -50)
    print("echo-path RES-side variability self-test: OK")


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("self-test")
    run_p = sub.add_parser("run")
    run_p.add_argument("--corpus", type=Path, required=True)
    run_p.add_argument("--report", type=Path, required=True)
    run_p.add_argument("--processor", type=Path, required=True)
    run_p.add_argument("--res-probe", type=Path, required=True)
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
            args.corpus, args.report, args.processor, args.res_probe,
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
