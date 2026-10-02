#!/usr/bin/env python3
"""Candidate-zero echo-path AEC/RES/NS recovery-source observation."""

from __future__ import annotations

import argparse
import copy
import json
import statistics
import subprocess
import tempfile
from pathlib import Path

import build_aec_transition_corpus
import run_validation_engine as engine
import stage_interaction_run
from aec_recovery_rebaseline_100w50s import analyze_case as analyze_recovery

BASE_CASE = "echo-path-change"
PROFILES = ("prefix-aec", "prefix-res", "prefix-ns", "default")
PATH_KEYS = ("mic_audio", "render_audio", "clean_near_audio", "echo_audio", "vad_labels")
STATE_METRICS = (
    "res_gain",
    "res_gain_delta_from_previous_frame",
    "residual_echo_gain",
    "erle_db",
    "estimated_delay_ms",
    "delay_error_samples",
    "input_rms_dbfs",
    "output_rms_dbfs",
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
        raise ValueError("RES-side recovery stride drift")
    if contract["preregistered_rules"]["no_res_gain_threshold_fitting"] is not True:
        raise ValueError("RES gain threshold fitting enabled")
    if contract["preregistered_rules"]["no_root_cause_selection"] is not True:
        raise ValueError("root-cause selection enabled")
    if contract["preregistered_rules"]["no_state_family_ranking"] is not True:
        raise ValueError("state-family ranking enabled")


def prefix_paths(case: dict, prefix: str) -> dict:
    out = copy.deepcopy(case)
    for key in PATH_KEYS:
        value = out.get(key)
        if value:
            out[key] = f"{prefix}/{value}"
    return out


def build_corpus(output: Path, seed: int, seconds: float) -> dict:
    output.mkdir(parents=True, exist_ok=True)
    source_root = output / "source"
    base = build_aec_transition_corpus.build(source_root, seed, seconds)
    by_id = {case["case_id"]: case for case in base["cases"]}
    if BASE_CASE not in by_id:
        raise ValueError("echo-path case missing")
    source_case = by_id[BASE_CASE]
    cases = []
    for order, profile in enumerate(PROFILES):
        case = prefix_paths(source_case, "source")
        case["case_id"] = f"{BASE_CASE}--{profile}"
        case["scenario"] = f"res-side-recovery::{source_case['scenario']}"
        case["processor_profile"] = profile
        case["expected"] = {}
        dims = dict(case.get("dimensions", {}))
        dims.update({
            "base_case_id": BASE_CASE,
            "stage_profile": profile,
            "stage_order": order,
            "source_family": "deterministic-aec-transition-v1",
        })
        case["dimensions"] = dims
        cases.append(case)
    corpus = {
        "schema_version": 1,
        "corpus_id": f"aec-echo-res-side-v1-seed-{seed}",
        "tier": "regression",
        "generator": {
            "name": "aec_echo_path_res_side_recovery.py",
            "version": 1,
            "seed": seed,
            "seconds": seconds,
        },
        "sources": ["deterministic-aec-transition-v1"],
        "sealed_data": True,
        "candidate_limit": 0,
        "confirmation_limit": 0,
        "promotion_allowed": False,
        "shipping_change_allowed": False,
        "cases": cases,
    }
    (output / "corpus.json").write_text(
        json.dumps(corpus, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return corpus


def read_jsonl(path: Path) -> list[dict]:
    rows = [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if not rows:
        raise ValueError("RES state trace empty")
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


def snapshot(row: dict) -> dict:
    keys = (
        "frame",
        "far_end_active",
        "double_talk_active",
        "aec_converged",
        "erle_valid",
    )
    out = {key: row[key] for key in keys}
    for name in STATE_METRICS:
        out[name] = row[name]
    return out


def snapshot_at(rows: list[dict], frame: int) -> dict:
    if frame < 0 or frame >= len(rows):
        raise ValueError(f"RES snapshot frame out of range: {frame}")
    return snapshot(rows[frame])


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
    expected_ids = {f"{BASE_CASE}--{profile}" for profile in PROFILES}
    cases = {case["case_id"]: case for case in corpus["cases"]}
    if set(cases) != expected_ids:
        raise ValueError("RES-side corpus case-set drift")
    report_cases = {case["case_id"]: case for case in report.get("cases", [])}
    if set(report_cases) != expected_ids:
        raise ValueError("RES-side report case-set drift")
    if not all(bool(item.get("passed", False)) for item in report_cases.values()):
        raise ValueError("RES-side canonical policy failure")

    recovery = {}
    for profile in PROFILES:
        recovery[profile] = analyze_recovery(
            cases[f"{BASE_CASE}--{profile}"],
            corpus_path,
            processor,
            contract,
        )

    res_case = cases[f"{BASE_CASE}--prefix-res"]
    with tempfile.TemporaryDirectory(prefix="ap-res-side-equivalence-") as raw:
        root = Path(raw)
        reference = standard_output(
            processor, corpus_path, res_case, root / "reference"
        )
        observed, rows = run_res_probe(
            res_probe, corpus_path, res_case, root / "probe"
        )
    equivalent = reference == observed
    trace_output.parent.mkdir(parents=True, exist_ok=True)
    trace_output.write_text(
        "\n".join(json.dumps(row, sort_keys=True) for row in rows) + "\n",
        encoding="utf-8",
    )

    transition_frame = int(res_case["control"]["echo_path_change_frame"])
    fixed = {}
    for offset_ms in contract["res_probe"]["fixed_transition_relative_snapshots_ms"]:
        if int(offset_ms) % 10 != 0:
            raise ValueError("RES fixed snapshot offset not frame-aligned")
        fixed[str(offset_ms)] = snapshot_at(
            rows, transition_frame + int(offset_ms) // 10
        )

    boundary_snapshots = {}
    for label, profile in (
        ("AEC", "prefix-aec"),
        ("RES", "prefix-res"),
        ("NS", "prefix-ns"),
    ):
        item = recovery[profile]
        if item["recovery_time_ms"] is None:
            boundary_snapshots[label] = None
        else:
            ms = int(item["recovery_time_ms"])
            if ms % 10 != 0:
                raise ValueError("recovery boundary not frame-aligned")
            boundary_snapshots[label] = snapshot_at(
                rows, transition_frame + ms // 10
            )

    def delta(left: str, right: str) -> int | None:
        a = recovery[left]["recovery_time_ms"]
        b = recovery[right]["recovery_time_ms"]
        if a is None or b is None:
            return None
        return int(b) - int(a)

    return {
        "schema_version": 1,
        "investigation_id": contract["id"],
        "seed": int(corpus["generator"]["seed"]),
        "authority": "candidate-zero-res-side-observation-only",
        "probe_output_bitwise_equivalent": equivalent,
        "transition_frame": transition_frame,
        "recovery": {
            "AEC": recovery_view(recovery["prefix-aec"]),
            "RES": recovery_view(recovery["prefix-res"]),
            "NS": recovery_view(recovery["prefix-ns"]),
            "full": recovery_view(recovery["default"]),
        },
        "aec_to_res_ms": delta("prefix-aec", "prefix-res"),
        "res_to_ns_ms": delta("prefix-res", "prefix-ns"),
        "fixed_transition_relative_res_state": fixed,
        "res_state_at_recovery_boundaries": boundary_snapshots,
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
    equivalent = all(
        by_seed[seed]["probe_output_bitwise_equivalent"] for seed in expected
    )

    fixed_summary = {}
    for offset_ms in contract["res_probe"]["fixed_transition_relative_snapshots_ms"]:
        offset = str(offset_ms)
        fixed_summary[offset] = {
            metric: scalar_summary([
                float(by_seed[seed]["fixed_transition_relative_res_state"][offset][metric])
                for seed in expected
            ])
            for metric in STATE_METRICS
        }

    recovery_by_seed = {
        str(seed): {
            "AEC": by_seed[seed]["recovery"]["AEC"],
            "RES": by_seed[seed]["recovery"]["RES"],
            "NS": by_seed[seed]["recovery"]["NS"],
            "full": by_seed[seed]["recovery"]["full"],
            "aec_to_res_ms": by_seed[seed]["aec_to_res_ms"],
            "res_to_ns_ms": by_seed[seed]["res_to_ns_ms"],
        }
        for seed in expected
    }

    return {
        "schema_version": 1,
        "investigation_id": contract["id"],
        "fresh_seeds": expected,
        "probe_output_bitwise_equivalent_all_seeds": equivalent,
        "recovery_by_seed": recovery_by_seed,
        "fixed_transition_relative_res_state_summary": fixed_summary,
        "all_seed_receipts": [by_seed[seed] for seed in expected],
        "state_family_ranking": "NOT_AUTHORIZED",
        "root_cause_attribution": "NOT_AUTHORIZED",
        "candidate_authority": False,
        "s004_open": False,
    }


def self_test() -> None:
    assert PROFILES == ("prefix-aec", "prefix-res", "prefix-ns", "default")
    assert scalar_summary([1.0, 2.0, 3.0]) == {
        "count": 3, "median": 2.0, "min": 1.0, "max": 3.0
    }
    print("echo-path RES-side recovery variability self-test: OK")


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("self-test")
    build_p = sub.add_parser("build")
    build_p.add_argument("--output", type=Path, required=True)
    build_p.add_argument("--seed", type=int, required=True)
    build_p.add_argument("--seconds", type=float, default=6.0)
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
    if args.command == "build":
        corpus = build_corpus(args.output, args.seed, args.seconds)
        print(json.dumps({
            "seed": args.seed,
            "cases": len(corpus["cases"]),
            "corpus": str(args.output / "corpus.json"),
        }, sort_keys=True))
        return 0

    contract = load_json(args.contract)
    if args.command == "run":
        result = analyze_seed(
            args.corpus,
            args.report,
            args.processor,
            args.res_probe,
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
            "aec_to_res_ms": result["aec_to_res_ms"],
            "res_to_ns_ms": result["res_to_ns_ms"],
            "recovery_ms": {
                key: value["recovery_time_ms"]
                for key, value in result["recovery"].items()
            },
            "probe_output_bitwise_equivalent":
                result["probe_output_bitwise_equivalent"],
        }, sort_keys=True))
    else:
        print(json.dumps({
            "probe_output_bitwise_equivalent_all_seeds":
                result["probe_output_bitwise_equivalent_all_seeds"],
            "recovery_by_seed": result["recovery_by_seed"],
        }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
