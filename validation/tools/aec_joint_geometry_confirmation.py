#!/usr/bin/env python3
"""Evaluate the preregistered S003 joint q/rho fresh confirmation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def load(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path}: object required")
    return value


def evaluate(contract: dict, receipts: list[dict]) -> dict:
    if contract.get("authority") != "CANDIDATE_ZERO_SINGLE_HYPOTHESIS_CONFIRMATION_ONLY":
        raise ValueError("confirmation authority drift")
    if int(contract.get("candidate_limit", -1)) != 0:
        raise ValueError("candidate budget drift")
    if int(contract.get("confirmation_limit", -1)) != 1:
        raise ValueError("confirmation budget drift")

    expected = [int(x) for x in contract["corpus"]["fresh_seeds"]]
    by_seed = {int(item["seed"]): item for item in receipts}
    if sorted(by_seed) != sorted(expected) or len(by_seed) != len(receipts):
        raise ValueError(f"fresh receipt set drift: {sorted(by_seed)} != {sorted(expected)}")

    required_ms = int(contract["hypothesis"]["required_freeze_both_recovery_ms"])
    per_seed = []
    freeze_q = {}
    freeze_rho = {}
    max_identity = 0.0
    max_normalized = 0.0
    for seed in expected:
        item = by_seed[seed]
        checks = {
            "probe_output_bitwise_equivalent": bool(item["probe_output_bitwise_equivalent"]),
            "identity_valid": bool(item["identity_valid"]),
            "normalized_reconstruction_valid": bool(item["normalized_reconstruction_valid"]),
            "actual_observed_recovery_matches_standard_aec":
                bool(item["actual_observed_recovery_matches_standard_aec"]),
        }
        if not all(checks.values()):
            raise ValueError(f"mechanical validity failed on seed {seed}: {checks}")
        max_identity = max(max_identity, float(item["identity_max_relative_error"]))
        max_normalized = max(max_normalized, float(item["normalized_max_relative_error"]))

        both = item["driver_receipts"]["freeze_both"]["recovery_time_ms"]
        confirmed = both == required_ms
        per_seed.append({
            "seed": seed,
            "standard_aec_recovery_ms": item["standard_aec_recovery_ms"],
            "freeze_both_recovery_ms": both,
            "confirmed_on_seed": confirmed,
        })
        freeze_q[str(seed)] = item["driver_receipts"]["freeze_q"]
        freeze_rho[str(seed)] = item["driver_receipts"]["freeze_rho"]

    confirmed_count = sum(item["confirmed_on_seed"] for item in per_seed)
    required_count = int(contract["hypothesis"]["required_fresh_seed_count"])
    hypothesis_confirmed = confirmed_count == required_count == len(expected)

    return {
        "schema_version": 1,
        "investigation_id": contract["id"],
        "authority": "candidate-zero-single-hypothesis-confirmation-only",
        "fresh_seeds": expected,
        "mechanical_validity": {
            "probe_output_bitwise_equivalent_all_seeds": True,
            "identity_valid_all_seeds": True,
            "normalized_reconstruction_valid_all_seeds": True,
            "actual_observed_recovery_matches_standard_aec_all_seeds": True,
            "max_identity_relative_error": max_identity,
            "max_normalized_relative_error": max_normalized,
            "evidence_accepted": True,
        },
        "hypothesis": contract["hypothesis"]["statement"],
        "per_seed": per_seed,
        "confirmed_seed_count": confirmed_count,
        "total_seed_count": len(expected),
        "hypothesis_confirmed": hypothesis_confirmed,
        "outcome": "CONFIRMED" if hypothesis_confirmed else "REJECTED",
        "single_factor_freeze_q_by_seed": freeze_q,
        "single_factor_freeze_rho_by_seed": freeze_rho,
        "single_factor_interpretation": "DESCRIPTIVE_ONLY",
        "candidate_authority": False,
        "root_cause_claim_authority": False,
        "s004_open": False,
    }


def self_test() -> None:
    contract = {
        "id": "test",
        "authority": "CANDIDATE_ZERO_SINGLE_HYPOTHESIS_CONFIRMATION_ONLY",
        "candidate_limit": 0,
        "confirmation_limit": 1,
        "corpus": {"fresh_seeds": [1, 2]},
        "hypothesis": {
            "statement": "x",
            "required_freeze_both_recovery_ms": 50,
            "required_fresh_seed_count": 2,
        },
    }
    def receipt(seed: int, both: int) -> dict:
        return {
            "seed": seed,
            "probe_output_bitwise_equivalent": True,
            "identity_valid": True,
            "normalized_reconstruction_valid": True,
            "actual_observed_recovery_matches_standard_aec": True,
            "identity_max_relative_error": 1e-15,
            "normalized_max_relative_error": 1e-15,
            "standard_aec_recovery_ms": 100,
            "driver_receipts": {
                "freeze_both": {"recovery_time_ms": both, "recovery_shift_vs_actual_ms": both - 100},
                "freeze_q": {"recovery_time_ms": 100, "recovery_shift_vs_actual_ms": 0},
                "freeze_rho": {"recovery_time_ms": 100, "recovery_shift_vs_actual_ms": 0},
            },
        }
    assert evaluate(contract, [receipt(1, 50), receipt(2, 50)])["outcome"] == "CONFIRMED"
    assert evaluate(contract, [receipt(1, 50), receipt(2, 100)])["outcome"] == "REJECTED"
    print("joint geometry confirmation self-test: OK")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--contract", type=Path)
    parser.add_argument("--receipt", type=Path, action="append")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    if args.contract is None or not args.receipt or args.output is None:
        parser.error("--contract, --receipt and --output are required")
    result = evaluate(load(args.contract), [load(path) for path in args.receipt])
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "outcome": result["outcome"],
        "confirmed_seed_count": result["confirmed_seed_count"],
        "total_seed_count": result["total_seed_count"],
        "per_seed": result["per_seed"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
