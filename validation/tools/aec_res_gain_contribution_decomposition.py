#!/usr/bin/env python3
"""Candidate-zero RES gain contribution decomposition.

This is analysis-only. It reconstructs the shipping scalar RES math and
compares actual smoothing with two preregistered counterfactual gain paths.
"""

from __future__ import annotations

import argparse
import copy
import json
import math
import statistics
import subprocess
import tempfile
from pathlib import Path

import build_aec_transition_corpus
import run_validation_engine as engine
import stage_interaction_run
from aec_recovery_rebaseline_100w50s import analyze_case as analyze_standard_recovery
from aec_recovery_window_geometry import measure_geometry

BASE_CASE = "echo-path-change"
PROFILES = ("prefix-aec", "prefix-res")
PATH_KEYS = ("mic_audio", "render_audio", "clean_near_audio", "echo_audio", "vad_labels")
FRAME_MS = 10


def load_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path}: JSON object required")
    return value


def require_contract(contract: dict) -> None:
    if contract.get("authority") != "CANDIDATE_ZERO_COUNTERFACTUAL_ANALYSIS_ONLY":
        raise ValueError("RES contribution authority drift")
    if contract.get("candidate_limit") != 0 or contract.get("confirmation_limit") != 0:
        raise ValueError("RES contribution candidate budget drift")
    if tuple(contract["corpus"]["profiles"]) != PROFILES:
        raise ValueError("RES contribution profile set/order drift")
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
            raise ValueError(f"RES contribution measurement drift: {key}")
    if contract["validity_gates"]["either_counterfactual_outcome_is_valid_evidence"] is not True:
        raise ValueError("counterfactual outcome authority drift")
    rules = contract["preregistered_rules"]
    for key in (
        "no_gain_or_alpha_search",
        "no_aec_mu_tap_or_stride_search",
        "no_recovery_threshold_search",
        "no_counterfactual_parameter_sweep",
        "no_candidate_selection",
        "no_root_cause_selection",
    ):
        if rules[key] is not True:
            raise ValueError(f"RES contribution rule drift: {key}")


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
    source_case = next(
        (case for case in base["cases"] if case["case_id"] == BASE_CASE),
        None,
    )
    if source_case is None:
        raise ValueError("echo-path case missing")

    cases = []
    for order, profile in enumerate(PROFILES):
        case = prefix_paths(source_case, "source")
        case["case_id"] = f"{BASE_CASE}--{profile}"
        case["scenario"] = f"res-gain-contribution::{source_case['scenario']}"
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
        "corpus_id": f"aec-res-gain-contribution-v1-seed-{seed}",
        "tier": "regression",
        "generator": {
            "name": "aec_res_gain_contribution_decomposition.py",
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
        raise ValueError("RES contribution trace empty")
    frames = [int(row["frame"]) for row in rows]
    if frames != list(range(len(rows))):
        raise ValueError("RES contribution trace frame sequence drift")
    return rows


def run_probe(
    probe: Path,
    corpus_path: Path,
    case: dict,
    work: Path,
) -> tuple[list[int], list[dict]]:
    work.mkdir(parents=True, exist_ok=True)
    mic = engine.resolve(corpus_path, case.get("mic_audio"))
    render = engine.resolve(corpus_path, case.get("render_audio"))
    if mic is None or render is None:
        raise ValueError("RES contribution probe requires mic and render")
    change_frame = case.get("control", {}).get("echo_path_change_frame")
    if change_frame is None:
        raise ValueError("echo-path change frame missing")
    out = work / "probe-out.pcm"
    trace = work / "gain-contribution.jsonl"
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


def echo_frame_energy(
    corpus_path: Path,
    case: dict,
    total_frames: int,
) -> list[float]:
    echo_path = engine.resolve(corpus_path, case.get("echo_audio"))
    if echo_path is None:
        raise ValueError("echo reference missing")
    rate = int(case["sample_rate_hz"])
    samples = [float(x) / 32768.0 for x in engine.read_audio_samples(echo_path, rate, 1)]
    frame_samples = rate // 100
    expected = total_frames * frame_samples
    if len(samples) < expected:
        samples.extend([0.0] * (expected - len(samples)))
    samples = samples[:expected]
    energies = []
    for frame in range(total_frames):
        chunk = samples[frame * frame_samples:(frame + 1) * frame_samples]
        energies.append(
            (1.0e-12 + sum(x * x for x in chunk)) / max(1, len(chunk))
        )
    return energies


def window_curve(
    numerator_frame_energy: list[float],
    echo_frame_energy_values: list[float],
    transition_frame: int,
    start_ms: int,
    end_ms: int,
    window_ms: int,
    stride_ms: int,
) -> list[dict]:
    if window_ms % FRAME_MS or stride_ms % FRAME_MS:
        raise ValueError("counterfactual geometry must align to 10 ms frames")
    window_frames = window_ms // FRAME_MS
    stride_frames = stride_ms // FRAME_MS
    start_frame = transition_frame + start_ms // FRAME_MS
    end_frame = transition_frame + end_ms // FRAME_MS
    if start_ms % FRAME_MS or end_ms % FRAME_MS:
        raise ValueError("counterfactual interval must align to 10 ms frames")
    rows = []
    frame = start_frame
    while frame + window_frames <= end_frame:
        if frame < 0 or frame + window_frames > len(numerator_frame_energy):
            raise ValueError("counterfactual window out of range")
        numerator = sum(numerator_frame_energy[frame:frame + window_frames])
        denominator = sum(echo_frame_energy_values[frame:frame + window_frames])
        value = 10.0 * math.log10(
            (numerator + 1.0e-18) / (denominator + 1.0e-18)
        )
        rows.append({
            "start_ms_relative": (frame - transition_frame) * FRAME_MS,
            "end_ms_relative": (frame - transition_frame) * FRAME_MS + window_ms,
            "residual_to_echo_power_db": value,
        })
        frame += stride_frames
    return rows


def measure_curve(
    frame_energy: list[float],
    echo_energy: list[float],
    transition_frame: int,
    contract: dict,
) -> dict:
    m = contract["measurement"]
    pre = window_curve(
        frame_energy,
        echo_energy,
        transition_frame,
        int(m["pre_baseline_ms"][0]),
        int(m["pre_baseline_ms"][1]),
        int(m["pre_baseline_window_ms"]),
        int(m["pre_baseline_window_ms"]),
    )
    baseline = float(statistics.median(
        row["residual_to_echo_power_db"] for row in pre
    ))
    limit = baseline + float(m["recovery_excess_db"])
    post = window_curve(
        frame_energy,
        echo_energy,
        transition_frame,
        int(m["search_ms"][0]),
        int(m["search_ms"][1]),
        int(m["post_window_ms"]),
        int(m["post_stride_ms"]),
    )
    measured = measure_geometry(
        post,
        baseline,
        limit,
        int(m["required_windows_for_300ms_coverage"]),
    )
    measured.update({
        "pre_baseline_db": baseline,
        "recovery_limit_db": limit,
        "post_windows": post,
    })
    return measured


def median_pre_gain(rows: list[dict], transition_frame: int, contract: dict) -> float:
    start_ms, end_ms = contract["measurement"]["pre_baseline_ms"]
    start = transition_frame + int(start_ms) // FRAME_MS
    end = transition_frame + int(end_ms) // FRAME_MS
    values = [float(row["gain_after"]) for row in rows[start:end]]
    if not values:
        raise ValueError("pre-transition gain reference window empty")
    return float(statistics.median(values))


def recovery_delta(a: int | None, b: int | None) -> int | None:
    if a is None or b is None:
        return None
    return int(b) - int(a)


def analyze_seed(
    corpus_path: Path,
    report_path: Path,
    processor: Path,
    probe: Path,
    contract: dict,
    trace_output: Path,
) -> dict:
    require_contract(contract)
    corpus = load_json(corpus_path)
    report = load_json(report_path)
    expected_ids = {f"{BASE_CASE}--{profile}" for profile in PROFILES}
    cases = {case["case_id"]: case for case in corpus["cases"]}
    if set(cases) != expected_ids:
        raise ValueError("RES contribution corpus case-set drift")
    report_cases = {case["case_id"]: case for case in report.get("cases", [])}
    if set(report_cases) != expected_ids:
        raise ValueError("RES contribution report case-set drift")
    if not all(bool(item.get("passed", False)) for item in report_cases.values()):
        raise ValueError("RES contribution canonical policy failure")

    aec_case = cases[f"{BASE_CASE}--prefix-aec"]
    res_case = cases[f"{BASE_CASE}--prefix-res"]
    aec_standard = analyze_standard_recovery(
        aec_case, corpus_path, processor, contract
    )
    res_standard = analyze_standard_recovery(
        res_case, corpus_path, processor, contract
    )

    with tempfile.TemporaryDirectory(prefix="ap-res-contribution-") as raw:
        root = Path(raw)
        reference = standard_output(
            processor, corpus_path, res_case, root / "reference"
        )
        observed, rows = run_probe(
            probe, corpus_path, res_case, root / "probe"
        )
    equivalent = reference == observed
    trace_output.parent.mkdir(parents=True, exist_ok=True)
    trace_output.write_text(
        "\n".join(json.dumps(row, sort_keys=True) for row in rows) + "\n",
        encoding="utf-8",
    )

    max_formula_error = max(float(row["gain_formula_abs_error"]) for row in rows)
    formula_limit = float(
        contract["probe"]["per_frame_formula_validation"]["max_abs_error"]
    )
    formula_valid = max_formula_error <= formula_limit

    transition_frame = int(res_case["control"]["echo_path_change_frame"])
    echo_energy = echo_frame_energy(corpus_path, res_case, len(rows))
    pre_res = [float(row["pre_res_energy"]) for row in rows]
    actual = [float(row["post_res_energy"]) for row in rows]
    target = [
        float(row["pre_res_energy"]) * float(row["target_gain"]) ** 2
        for row in rows
    ]
    pre_gain = median_pre_gain(rows, transition_frame, contract)
    frozen = [energy * pre_gain * pre_gain for energy in pre_res]

    actual_measured = measure_curve(
        actual, echo_energy, transition_frame, contract
    )
    target_measured = measure_curve(
        target, echo_energy, transition_frame, contract
    )
    frozen_measured = measure_curve(
        frozen, echo_energy, transition_frame, contract
    )
    aec_analytic = measure_curve(
        pre_res, echo_energy, transition_frame, contract
    )

    standard_aec_ms = aec_standard["recovery_time_ms"]
    standard_res_ms = res_standard["recovery_time_ms"]
    actual_ms = actual_measured["recovery_time_ms"]
    frozen_ms = frozen_measured["recovery_time_ms"]
    analytic_aec_ms = aec_analytic["recovery_time_ms"]

    return {
        "schema_version": 1,
        "investigation_id": contract["id"],
        "seed": int(corpus["generator"]["seed"]),
        "authority": "candidate-zero-res-gain-counterfactual-analysis-only",
        "probe_output_bitwise_equivalent": equivalent,
        "gain_formula_max_abs_error": max_formula_error,
        "gain_formula_valid": formula_valid,
        "pre_transition_gain_reference": pre_gain,
        "standard_recovery_ms": {
            "AEC": standard_aec_ms,
            "RES": standard_res_ms,
        },
        "analytic_recovery_ms": {
            "aec_pre_res_energy": analytic_aec_ms,
            "actual_smoothed": actual_ms,
            "instantaneous_target": target_measured["recovery_time_ms"],
            "frozen_pre_gain": frozen_ms,
        },
        "validity": {
            "analytic_actual_matches_standard_res":
                actual_ms == standard_res_ms,
            "analytic_aec_matches_standard_aec":
                analytic_aec_ms == standard_aec_ms,
            "frozen_pre_gain_matches_standard_aec":
                frozen_ms == standard_aec_ms,
        },
        "contribution_ms": {
            "standard_aec_to_res": recovery_delta(standard_aec_ms, standard_res_ms),
            "instantaneous_target_minus_aec":
                recovery_delta(standard_aec_ms, target_measured["recovery_time_ms"]),
            "actual_minus_instantaneous_target":
                recovery_delta(target_measured["recovery_time_ms"], actual_ms),
            "actual_minus_frozen_pre_gain":
                recovery_delta(frozen_ms, actual_ms),
        },
        "counterfactual_curves": {
            "actual_smoothed": actual_measured,
            "instantaneous_target": target_measured,
            "frozen_pre_gain": frozen_measured,
            "aec_pre_res_energy": aec_analytic,
        },
        "candidate_authority": False,
        "root_cause_claim_authority": False,
    }


def aggregate(items: list[dict], contract: dict) -> dict:
    require_contract(contract)
    expected = sorted(int(x) for x in contract["corpus"]["fresh_seeds"])
    by_seed = {int(item["seed"]): item for item in items}
    if sorted(by_seed) != expected:
        raise ValueError("RES contribution fresh-seed mismatch")

    all_equivalent = all(
        by_seed[seed]["probe_output_bitwise_equivalent"] for seed in expected
    )
    all_formula_valid = all(
        by_seed[seed]["gain_formula_valid"] for seed in expected
    )
    actual_matches = all(
        by_seed[seed]["validity"]["analytic_actual_matches_standard_res"]
        for seed in expected
    )
    analytic_aec_matches = all(
        by_seed[seed]["validity"]["analytic_aec_matches_standard_aec"]
        for seed in expected
    )
    frozen_matches = all(
        by_seed[seed]["validity"]["frozen_pre_gain_matches_standard_aec"]
        for seed in expected
    )
    accepted = (
        all_equivalent
        and all_formula_valid
        and actual_matches
        and analytic_aec_matches
        and frozen_matches
    )

    receipts = [
        {
            "seed": seed,
            "standard_recovery_ms": by_seed[seed]["standard_recovery_ms"],
            "analytic_recovery_ms": by_seed[seed]["analytic_recovery_ms"],
            "contribution_ms": by_seed[seed]["contribution_ms"],
            "pre_transition_gain_reference":
                by_seed[seed]["pre_transition_gain_reference"],
            "gain_formula_max_abs_error":
                by_seed[seed]["gain_formula_max_abs_error"],
        }
        for seed in expected
    ]

    return {
        "schema_version": 1,
        "investigation_id": contract["id"],
        "fresh_seeds": expected,
        "mechanical_validity": {
            "probe_output_bitwise_equivalent_all_seeds": all_equivalent,
            "gain_formula_valid_all_seeds": all_formula_valid,
            "analytic_actual_matches_standard_res_all_seeds": actual_matches,
            "analytic_aec_matches_standard_aec_all_seeds": analytic_aec_matches,
            "frozen_pre_gain_matches_standard_aec_all_seeds": frozen_matches,
            "evidence_accepted": accepted,
        },
        "receipts": receipts,
        "contribution_summary": {
            "standard_aec_to_res_ms": {
                str(seed): by_seed[seed]["contribution_ms"]["standard_aec_to_res"]
                for seed in expected
            },
            "instantaneous_target_minus_aec_ms": {
                str(seed):
                    by_seed[seed]["contribution_ms"]["instantaneous_target_minus_aec"]
                for seed in expected
            },
            "actual_minus_instantaneous_target_ms": {
                str(seed):
                    by_seed[seed]["contribution_ms"]["actual_minus_instantaneous_target"]
                for seed in expected
            },
        },
        "counterfactual_outcome_authority": "DESCRIPTIVE_ONLY",
        "root_cause_attribution": "NOT_AUTHORIZED",
        "candidate_authority": False,
        "s004_open": False,
    }


def self_test() -> None:
    contract = {
        "authority": "CANDIDATE_ZERO_COUNTERFACTUAL_ANALYSIS_ONLY",
        "candidate_limit": 0,
        "confirmation_limit": 0,
        "corpus": {"profiles": list(PROFILES)},
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
        "validity_gates": {
            "either_counterfactual_outcome_is_valid_evidence": True,
        },
        "preregistered_rules": {
            "no_gain_or_alpha_search": True,
            "no_aec_mu_tap_or_stride_search": True,
            "no_recovery_threshold_search": True,
            "no_counterfactual_parameter_sweep": True,
            "no_candidate_selection": True,
            "no_root_cause_selection": True,
        },
    }
    require_contract(contract)
    assert recovery_delta(100, 150) == 50
    assert recovery_delta(None, 150) is None
    print("RES gain contribution decomposition self-test: OK")


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
    run_p.add_argument("--probe", type=Path, required=True)
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
            args.probe,
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
            "standard_recovery_ms": result["standard_recovery_ms"],
            "analytic_recovery_ms": result["analytic_recovery_ms"],
            "contribution_ms": result["contribution_ms"],
            "formula_error": result["gain_formula_max_abs_error"],
            "validity": result["validity"],
            "probe_output_bitwise_equivalent":
                result["probe_output_bitwise_equivalent"],
        }, sort_keys=True))
    else:
        print(json.dumps({
            "mechanical_validity": result["mechanical_validity"],
            "contribution_summary": result["contribution_summary"],
        }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
