#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import Any


def classify(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        raise ValueError("no I010 probe rows")
    seeds = [int(row["seed"]) for row in rows]
    if len(set(seeds)) != len(seeds):
        raise ValueError("duplicate I010 seed")
    if any(int(row.get("total_frames", 0)) <= 0 for row in rows):
        raise ValueError("I010 probe did not execute frames")

    upstream_dependency = any(
        int(row.get("upstream_mismatch_frames", 0)) > 0 or
        float(row.get("max_upstream_probability_delta", 0.0)) > 1.0e-7
        for row in rows
    )
    cross_mismatch = any(
        int(row.get("low_cross_mismatch_frames", 0)) > 0 or
        int(row.get("base_cross_mismatch_frames", 0)) > 0
        for row in rows
    )
    waveform_exercised = all(
        int(row.get("waveform_changed_frames", 0)) > 0 and
        float(row.get("max_post_agc_rms_delta", 0.0)) > 1.0e-8
        for row in rows
    )
    vad_diverged = any(
        int(row.get("vad_probability_diff_frames", 0)) > 0 or
        int(row.get("vad_active_diff_frames", 0)) > 0
        for row in rows
    )

    if upstream_dependency:
        decision = "UPSTREAM_PROBABILITY_FLOOR_DEPENDENCE_REVIEW_REQUIRED"
    elif cross_mismatch or not waveform_exercised:
        decision = "INPUT_INVALID_REVIEW_REQUIRED"
    elif vad_diverged:
        decision = "LOCAL_WAVEFORM_COUPLING_CONFIRMED_REVIEW_REQUIRED"
    else:
        decision = "NO_OBSERVED_LOCAL_COUPLING_REVIEW_REQUIRED"

    return {
        "schema_version": 1,
        "iteration_id": "I010",
        "authority": "CANDIDATE_ZERO_ROOT_CAUSE_ONLY",
        "decision": decision,
        "seeds": seeds,
        "candidate_limit_consumed": 0,
        "confirmation_limit_consumed": 0,
        "shipping_source_changed": False,
        "summary": {
            "max_upstream_probability_delta": max(
                float(row["max_upstream_probability_delta"]) for row in rows
            ),
            "upstream_mismatch_frames": sum(
                int(row["upstream_mismatch_frames"]) for row in rows
            ),
            "max_post_agc_rms_delta": max(
                float(row["max_post_agc_rms_delta"]) for row in rows
            ),
            "waveform_changed_frames": sum(
                int(row["waveform_changed_frames"]) for row in rows
            ),
            "max_vad_probability_delta": max(
                float(row["max_vad_probability_delta"]) for row in rows
            ),
            "vad_probability_diff_frames": sum(
                int(row["vad_probability_diff_frames"]) for row in rows
            ),
            "vad_active_diff_frames": sum(
                int(row["vad_active_diff_frames"]) for row in rows
            ),
            "low_cross_mismatch_frames": sum(
                int(row["low_cross_mismatch_frames"]) for row in rows
            ),
            "base_cross_mismatch_frames": sum(
                int(row["base_cross_mismatch_frames"]) for row in rows
            ),
            "noise_active_base": sum(int(row["noise_active_base"]) for row in rows),
            "noise_active_low": sum(int(row["noise_active_low"]) for row in rows),
            "speech_active_base": sum(int(row["speech_active_base"]) for row in rows),
            "speech_active_low": sum(int(row["speech_active_low"]) for row in rows),
        },
        "rows": rows,
        "interpretation_rule": (
            "This diagnostic may attribute NS-floor/VAD observation-domain coupling only. "
            "It cannot select candidate values, modify thresholds, consume confirmation, "
            "or authorize shipping/HIL/Product Certification."
        ),
    }


def run_probe(probe: Path, seeds: list[int]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for seed in seeds:
        proc = subprocess.run(
            [str(probe), str(seed)],
            check=True,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        row = json.loads(proc.stdout)
        if int(row.get("seed", -1)) != seed:
            raise ValueError(f"probe seed mismatch: {seed}")
        rows.append(row)
    return rows


def self_test() -> None:
    base = {
        "total_frames": 100,
        "max_upstream_probability_delta": 0.0,
        "upstream_mismatch_frames": 0,
        "max_post_agc_rms_delta": 0.01,
        "waveform_changed_frames": 50,
        "max_vad_probability_delta": 0.02,
        "vad_probability_diff_frames": 10,
        "vad_active_diff_frames": 2,
        "low_cross_mismatch_frames": 0,
        "base_cross_mismatch_frames": 0,
        "noise_active_base": 10,
        "noise_active_low": 12,
        "speech_active_base": 20,
        "speech_active_low": 20,
    }
    rows = [{**base, "seed": seed} for seed in (1, 2, 3)]
    assert classify(rows)["decision"] == "LOCAL_WAVEFORM_COUPLING_CONFIRMED_REVIEW_REQUIRED"
    upstream = [{**row, "upstream_mismatch_frames": 1} for row in rows]
    assert classify(upstream)["decision"] == "UPSTREAM_PROBABILITY_FLOOR_DEPENDENCE_REVIEW_REQUIRED"
    invalid = [{**row, "low_cross_mismatch_frames": 1} for row in rows]
    assert classify(invalid)["decision"] == "INPUT_INVALID_REVIEW_REQUIRED"
    no_div = [{
        **row,
        "vad_probability_diff_frames": 0,
        "vad_active_diff_frames": 0,
        "max_vad_probability_delta": 0.0,
    } for row in rows]
    assert classify(no_div)["decision"] == "NO_OBSERVED_LOCAL_COUPLING_REVIEW_REQUIRED"
    print("I010 ns-vad observation-domain evaluator self-test: OK")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--probe", type=Path)
    parser.add_argument("--contract", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--seed", action="append", type=int, default=[])
    parser.add_argument("--enforce-input-valid", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        self_test()
        return 0
    if not args.probe or not args.contract or not args.output or not args.seed:
        parser.error("--probe, --contract, --output and at least one --seed are required")

    contract = json.loads(args.contract.read_text(encoding="utf-8"))
    expected = [int(x) for x in contract["fresh_seeds"]]
    if args.seed != expected:
        raise SystemExit(f"seed contract mismatch: actual={args.seed} expected={expected}")
    if contract.get("candidate_limit") != 0 or contract.get("confirmation_limit") != 0:
        raise SystemExit("I010 authority drift: candidate/confirmation budget must stay zero")

    rows = run_probe(args.probe.resolve(), args.seed)
    result = classify(rows)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "decision": result["decision"],
        "summary": result["summary"],
        "seeds": result["seeds"],
    }, sort_keys=True))

    if args.enforce_input_valid and result["decision"] == "INPUT_INVALID_REVIEW_REQUIRED":
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
