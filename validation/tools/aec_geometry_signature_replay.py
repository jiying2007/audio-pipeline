#!/usr/bin/env python3
"""Validate the durable supplemental AEC geometry replay signature."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def load_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path}: JSON object required")
    return value


def require_contract(contract: dict) -> None:
    if contract.get("schema_version") != 1:
        raise ValueError("replay schema_version must be 1")
    if contract.get("authority") != "supplemental-replay-only":
        raise ValueError("replay authority drift")
    if contract.get("lifecycle_status") not in {"OPEN_DIAGNOSTIC", "FIXED_REGRESSION"}:
        raise ValueError("invalid replay lifecycle")
    seeds = contract.get("source_identity", {}).get("seeds")
    if not isinstance(seeds, list) or len(seeds) < 2 or len(set(seeds)) != len(seeds):
        raise ValueError("replay requires at least two unique seeds")
    boundary = contract["authority_boundary"]
    for key in (
        "release_acceptance_authority",
        "candidate_authority",
        "s004_candidate_authority",
        "may_change_dsp_parameters",
        "may_change_recovery_threshold",
        "may_reopen_internal_mechanism_search",
    ):
        if boundary.get(key) is not False:
            raise ValueError(f"replay authority boundary drift: {key}")


def validate_receipts(contract: dict, receipts: list[dict]) -> dict:
    require_contract(contract)
    expected_seeds = sorted(int(x) for x in contract["source_identity"]["seeds"])
    by_seed = {int(item["seed"]): item for item in receipts}
    if sorted(by_seed) != expected_seeds:
        raise ValueError(f"replay seed mismatch: {sorted(by_seed)} != {expected_seeds}")

    expected = contract["expected_replay"]
    errors: list[str] = []
    per_seed = []

    for seed in expected_seeds:
        receipt = by_seed[seed]
        residual = receipt["residual_geometry"]
        scale = receipt["scale_geometry"]
        standard_expected = int(expected["standard_aec_recovery_ms"][str(seed)])
        freeze_expected = int(expected["freeze_geometry_recovery_ms"][str(seed)])

        seed_errors: list[str] = []
        if int(residual["standard_aec_recovery_ms"]) != standard_expected:
            seed_errors.append(
                f"standard recovery {residual['standard_aec_recovery_ms']} != {standard_expected}"
            )
        if bool(residual["probe_output_bitwise_equivalent"]) != bool(
            expected["probe_output_bitwise_equivalent"]
        ):
            seed_errors.append("probe output equivalence changed")
        if bool(residual["identity_valid"]) != bool(expected["identity_valid"]):
            seed_errors.append("AEC subtraction identity validity changed")
        if bool(residual["actual_observed_recovery_matches_standard_aec"]) != bool(
            expected["actual_observed_recovery_matches_standard_aec"]
        ):
            seed_errors.append("observed recovery no longer matches canonical AEC")

        freeze = scale["counterfactuals"]["freeze_geometry"]
        if bool(freeze["physically_admissible"]) != bool(
            expected["freeze_geometry_physically_admissible"]
        ):
            seed_errors.append("freeze-G physical admissibility changed")
        if freeze["recovery_time_ms"] is None or int(freeze["recovery_time_ms"]) != freeze_expected:
            seed_errors.append(
                f"freeze-G recovery {freeze['recovery_time_ms']} != {freeze_expected}"
            )

        errors.extend(f"seed {seed}: {item}" for item in seed_errors)
        per_seed.append({
            "seed": seed,
            "status": "PASS" if not seed_errors else "FAIL",
            "standard_aec_recovery_ms": residual["standard_aec_recovery_ms"],
            "freeze_geometry_recovery_ms": freeze["recovery_time_ms"],
            "freeze_geometry_physically_admissible": freeze["physically_admissible"],
            "probe_output_bitwise_equivalent": residual["probe_output_bitwise_equivalent"],
            "identity_valid": residual["identity_valid"],
            "errors": seed_errors,
        })

    status = "PASS" if not errors else "FAIL"
    return {
        "schema_version": 1,
        "replay_id": contract["replay_id"],
        "lifecycle_status": contract["lifecycle_status"],
        "authority": contract["authority"],
        "status": status,
        "errors": errors,
        "seeds": expected_seeds,
        "per_seed": per_seed,
        "first_observable_stage": contract["mechanism_lineage"]["first_observable_stage"],
        "mechanism_coordinate": contract["mechanism_lineage"]["mechanism_coordinate"],
        "release_acceptance_authority": False,
        "candidate_authority": False,
        "s004_candidate_authority": False,
    }


def self_test() -> None:
    contract = {
        "schema_version": 1,
        "replay_id": "R",
        "lifecycle_status": "OPEN_DIAGNOSTIC",
        "authority": "supplemental-replay-only",
        "source_identity": {"seeds": [1, 2]},
        "mechanism_lineage": {"first_observable_stage": "AEC", "mechanism_coordinate": "G=R/M"},
        "expected_replay": {
            "standard_aec_recovery_ms": {"1": 100, "2": 150},
            "freeze_geometry_recovery_ms": {"1": 0, "2": 0},
            "freeze_geometry_physically_admissible": True,
            "probe_output_bitwise_equivalent": True,
            "identity_valid": True,
            "actual_observed_recovery_matches_standard_aec": True,
        },
        "authority_boundary": {
            "release_acceptance_authority": False,
            "candidate_authority": False,
            "s004_candidate_authority": False,
            "may_change_dsp_parameters": False,
            "may_change_recovery_threshold": False,
            "may_reopen_internal_mechanism_search": False,
        },
    }
    def receipt(seed: int, recovery: int) -> dict:
        return {
            "seed": seed,
            "residual_geometry": {
                "standard_aec_recovery_ms": recovery,
                "probe_output_bitwise_equivalent": True,
                "identity_valid": True,
                "actual_observed_recovery_matches_standard_aec": True,
            },
            "scale_geometry": {
                "counterfactuals": {
                    "freeze_geometry": {
                        "physically_admissible": True,
                        "recovery_time_ms": 0,
                    }
                }
            },
        }
    assert validate_receipts(contract, [receipt(1, 100), receipt(2, 150)])["status"] == "PASS"
    broken = receipt(2, 100)
    assert validate_receipts(contract, [receipt(1, 100), broken])["status"] == "FAIL"
    print("AEC geometry supplemental replay self-test: OK")


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
        parser.error("--contract --receipt --output required")

    contract = load_json(args.contract)
    receipts = [load_json(path) for path in args.receipt]
    result = validate_receipts(contract, receipts)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps({
        "replay_id": result["replay_id"],
        "status": result["status"],
        "seeds": result["seeds"],
        "first_observable_stage": result["first_observable_stage"],
        "mechanism_coordinate": result["mechanism_coordinate"],
    }, sort_keys=True))
    return 0 if result["status"] == "PASS" else 3


if __name__ == "__main__":
    raise SystemExit(main())
