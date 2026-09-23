#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import subprocess
from pathlib import Path
from typing import Any

FLOOR_EPS_DB = 1.0e-6


def classify(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        raise ValueError("no I011 probe rows")
    seeds = [int(row.get("seed", -1)) for row in rows]
    if len(seeds) != len(set(seeds)):
        raise ValueError("duplicate I011 seed")

    for row in rows:
        if int(row.get("total_frames", 0)) != 1280:
            raise ValueError("I011 probe frame count drift")
        if int(row.get("speech_frames", 0)) <= 0 or int(row.get("noise_frames", 0)) <= 0:
            raise ValueError("I011 probe labels were not exercised")
        for key in (
            "max_noise_reference_delta_db",
            "max_proxy_delta_db",
            "speech_proxy_mean_db",
            "noise_proxy_mean_db",
            "mean_gap_db",
            "speech_proxy_p10_db",
            "noise_proxy_p90_db",
            "tail_gap_db",
            "proxy_auc",
        ):
            value = float(row.get(key, float("nan")))
            if not math.isfinite(value):
                raise ValueError(f"I011 non-finite metric: {key}")

    max_noise_delta = max(float(row["max_noise_reference_delta_db"]) for row in rows)
    max_proxy_delta = max(float(row["max_proxy_delta_db"]) for row in rows)
    min_auc = min(float(row["proxy_auc"]) for row in rows)
    min_mean_gap = min(float(row["mean_gap_db"]) for row in rows)
    min_tail_gap = min(float(row["tail_gap_db"]) for row in rows)

    floor_invariant = max_noise_delta <= FLOOR_EPS_DB and max_proxy_delta <= FLOOR_EPS_DB
    directionally_separable = all(
        float(row["speech_proxy_mean_db"]) > float(row["noise_proxy_mean_db"])
        and float(row["proxy_auc"]) > 0.5
        for row in rows
    )

    if not floor_invariant:
        decision = "NOISE_REFERENCE_FLOOR_DEPENDENT_REVIEW_REQUIRED"
    elif directionally_separable:
        decision = "NOISE_REFERENCE_PROXY_SEPARABLE_REVIEW_REQUIRED"
    else:
        decision = "NOISE_REFERENCE_PROXY_NOT_SEPARABLE_REVIEW_REQUIRED"

    return {
        "schema_version": 1,
        "investigation_id": "vad-noise-reference-proxy-v1",
        "authority": "CANDIDATE_ZERO_DIAGNOSTIC_ONLY",
        "decision": decision,
        "seeds": seeds,
        "candidate_limit_consumed": 0,
        "confirmation_limit_consumed": 0,
        "shipping_source_changed": False,
        "summary": {
            "max_noise_reference_delta_db": max_noise_delta,
            "max_proxy_delta_db": max_proxy_delta,
            "min_proxy_auc": min_auc,
            "min_mean_gap_db": min_mean_gap,
            "min_tail_gap_db": min_tail_gap,
            "floor_invariant": floor_invariant,
            "directionally_separable": directionally_separable,
        },
        "rows": rows,
        "interpretation_rule": (
            "This is a threshold-free candidate-zero feature diagnostic. "
            "It may establish floor invariance and directional label separation only. "
            "It cannot select a source candidate, tune VAD thresholds, consume confirmation, "
            "reuse I010 locked authority, or authorize shipping/HIL/Product Certification."
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
            raise ValueError(f"I011 probe seed mismatch: {seed}")
        rows.append(row)
    return rows


def self_test() -> None:
    base = {
        "total_frames": 1280,
        "speech_frames": 500,
        "noise_frames": 780,
        "max_noise_reference_delta_db": 0.0,
        "max_proxy_delta_db": 0.0,
        "speech_proxy_mean_db": 9.0,
        "noise_proxy_mean_db": 3.0,
        "mean_gap_db": 6.0,
        "speech_proxy_p10_db": 4.0,
        "noise_proxy_p90_db": 6.0,
        "tail_gap_db": -2.0,
        "proxy_auc": 0.75,
    }
    rows = [{**base, "seed": seed} for seed in (1, 2, 3)]
    assert classify(rows)["decision"] == "NOISE_REFERENCE_PROXY_SEPARABLE_REVIEW_REQUIRED"

    dependent = [{**row, "max_proxy_delta_db": 0.1} for row in rows]
    assert classify(dependent)["decision"] == "NOISE_REFERENCE_FLOOR_DEPENDENT_REVIEW_REQUIRED"

    weak = [{**row, "speech_proxy_mean_db": 2.0, "mean_gap_db": -1.0,
             "proxy_auc": 0.49} for row in rows]
    assert classify(weak)["decision"] == "NOISE_REFERENCE_PROXY_NOT_SEPARABLE_REVIEW_REQUIRED"
    print("I011 VAD noise-reference proxy evaluator self-test: OK")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--probe", type=Path)
    parser.add_argument("--contract", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--seed", action="append", type=int, default=[])
    args = parser.parse_args()

    if args.self_test:
        self_test()
        return 0
    if not args.probe or not args.contract or not args.output or not args.seed:
        parser.error("--probe, --contract, --output and at least one --seed are required")

    contract = json.loads(args.contract.read_text(encoding="utf-8"))
    expected = [int(x) for x in contract["fresh_seeds"]]
    if args.seed != expected:
        raise SystemExit(f"I011 seed contract mismatch: actual={args.seed} expected={expected}")
    if contract.get("authority") != "CANDIDATE_ZERO_DIAGNOSTIC_ONLY":
        raise SystemExit("I011 authority drift")
    if contract.get("candidate_limit") != 0 or contract.get("confirmation_limit") != 0:
        raise SystemExit("I011 candidate/confirmation budget must stay zero")
    if contract.get("protocol", {}).get("parameter_search") is not False:
        raise SystemExit("I011 parameter search must stay disabled")
    if contract.get("protocol", {}).get("threshold_tuning") is not False:
        raise SystemExit("I011 threshold tuning must stay disabled")
    if contract.get("protocol", {}).get("candidate_emulation") is not False:
        raise SystemExit("I011 candidate emulation must stay disabled")

    rows = run_probe(args.probe.resolve(), args.seed)
    result = classify(rows)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "decision": result["decision"],
        "seeds": result["seeds"],
        "summary": result["summary"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
