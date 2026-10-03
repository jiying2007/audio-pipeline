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


def evaluate(contract: dict, aggregate: dict) -> dict:
    if contract.get("authority") != "CANDIDATE_ZERO_SINGLE_HYPOTHESIS_CONFIRMATION_ONLY":
        raise ValueError("confirmation authority drift")
    if int(contract.get("candidate_limit", -1)) != 0:
        raise ValueError("candidate budget drift")
    if int(contract.get("confirmation_limit", -1)) != 1:
        raise ValueError("confirmation budget drift")

    expected = [int(x) for x in contract["corpus"]["fresh_seeds"]]
    actual = [int(x) for x in aggregate["fresh_seeds"]]
    if actual != expected:
        raise ValueError(f"fresh seed drift: {actual} != {expected}")

    mechanical = aggregate["mechanical_validity"]
    required_mechanical = {
        "probe_output_bitwise_equivalent_all_seeds": True,
        "identity_valid_all_seeds": True,
        "normalized_reconstruction_valid_all_seeds": True,
        "actual_observed_recovery_matches_standard_aec_all_seeds": True,
        "evidence_accepted": True,
    }
    for key, expected_value in required_mechanical.items():
        if mechanical.get(key) is not expected_value:
            raise ValueError(f"mechanical validity failed: {key}")

    required_ms = int(contract["hypothesis"]["required_freeze_both_recovery_ms"])
    freeze_both = aggregate["counterfactual_summary"]["freeze_both"]
    recovery = {str(k): v for k, v in freeze_both["recovery_time_ms"].items()}
    per_seed = []
    for seed in expected:
        value = recovery.get(str(seed))
        confirmed = value == required_ms
        per_seed.append({
            "seed": seed,
            "freeze_both_recovery_ms": value,
            "confirmed_on_seed": confirmed,
        })

    confirmed_count = sum(item["confirmed_on_seed"] for item in per_seed)
    hypothesis_confirmed = (
        confirmed_count == int(contract["hypothesis"]["required_fresh_seed_count"])
        and confirmed_count == len(expected)
    )

    return {
        "schema_version": 1,
        "investigation_id": contract["id"],
        "authority": "candidate-zero-single-hypothesis-confirmation-only",
        "fresh_seeds": expected,
        "mechanical_validity": mechanical,
        "hypothesis": contract["hypothesis"]["statement"],
        "per_seed": per_seed,
        "confirmed_seed_count": confirmed_count,
        "total_seed_count": len(expected),
        "hypothesis_confirmed": hypothesis_confirmed,
        "outcome": "CONFIRMED" if hypothesis_confirmed else "REJECTED",
        "single_factor_freeze_q": aggregate["counterfactual_summary"]["freeze_q"],
        "single_factor_freeze_rho": aggregate["counterfactual_summary"]["freeze_rho"],
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
    aggregate = {
        "fresh_seeds": [1, 2],
        "mechanical_validity": {
            "probe_output_bitwise_equivalent_all_seeds": True,
            "identity_valid_all_seeds": True,
            "normalized_reconstruction_valid_all_seeds": True,
            "actual_observed_recovery_matches_standard_aec_all_seeds": True,
            "evidence_accepted": True,
        },
        "counterfactual_summary": {
            "freeze_both": {"recovery_time_ms": {"1": 50, "2": 50}},
            "freeze_q": {"recovery_time_ms": {"1": 100, "2": 100}},
            "freeze_rho": {"recovery_time_ms": {"1": 100, "2": 100}},
        },
    }
    assert evaluate(contract, aggregate)["outcome"] == "CONFIRMED"
    aggregate["counterfactual_summary"]["freeze_both"]["recovery_time_ms"]["2"] = 100
    assert evaluate(contract, aggregate)["outcome"] == "REJECTED"
    print("joint geometry confirmation self-test: OK")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--contract", type=Path)
    parser.add_argument("--aggregate", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    if args.contract is None or args.aggregate is None or args.output is None:
        parser.error("--contract, --aggregate and --output are required")
    result = evaluate(load(args.contract), load(args.aggregate))
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
