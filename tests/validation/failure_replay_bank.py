#!/usr/bin/env python3
"""Validate the durable system-robustness Failure Replay Bank.

The bank stores small, reviewable replay contracts and immutable provenance,
not generated PCM. CI regenerates the deterministic corpus from committed
generators and verifies current stage-attribution against every open entry.
"""

from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path


def load_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path}: expected JSON object")
    return value


def load_catalog(path: Path) -> tuple[dict, list[dict]]:
    catalog = load_json(path)
    if catalog.get("schema_version") != 1:
        raise ValueError("catalog schema_version must be 1")
    if catalog.get("authority") != (
        "diagnostic-regression-only-not-release-or-candidate-authority"
    ):
        raise ValueError("invalid replay bank authority")
    if catalog.get("s004_candidate_authority") is not False:
        raise ValueError("replay bank must not grant S004 authority")
    raw_entries = catalog.get("entries")
    if not isinstance(raw_entries, list) or not raw_entries:
        raise ValueError("catalog entries must be non-empty")

    entries: list[dict] = []
    for relative in raw_entries:
        if not isinstance(relative, str) or not relative.startswith("entries/"):
            raise ValueError(f"invalid catalog entry path: {relative!r}")
        entry = load_json(path.parent / relative)
        validate_entry_shape(entry, catalog)
        entries.append(entry)

    ids = [entry["failure_id"] for entry in entries]
    if len(set(ids)) != len(ids):
        raise ValueError("failure_id values must be unique")
    return catalog, entries


def validate_entry_shape(entry: dict, catalog: dict) -> None:
    required = {
        "schema_version",
        "failure_id",
        "lifecycle_status",
        "authority",
        "source_identity",
        "prior_evidence",
        "expected_replay",
        "regression_assertion",
        "s004_eligibility",
        "root_cause_claim_authority",
        "release_acceptance_authority",
    }
    missing = required - set(entry)
    if missing:
        raise ValueError(f"{entry.get('failure_id')}: missing {sorted(missing)}")
    if entry["schema_version"] != 1:
        raise ValueError("entry schema_version must be 1")
    if entry["authority"] != "replay-only":
        raise ValueError("entry authority must be replay-only")
    if entry["root_cause_claim_authority"] is not False:
        raise ValueError("entry must not claim root-cause authority")
    if entry["release_acceptance_authority"] is not False:
        raise ValueError("entry must not claim release authority")
    if entry["s004_eligibility"].get("eligible") is not False:
        raise ValueError("open replay entry must not grant S004 eligibility")
    if entry["lifecycle_status"] not in {"OPEN_DIAGNOSTIC", "FIXED_REGRESSION"}:
        raise ValueError("invalid lifecycle_status")

    seeds = entry["source_identity"].get("seeds")
    if not isinstance(seeds, list) or len(seeds) < 2 or len(set(seeds)) != len(seeds):
        raise ValueError("entry requires at least two unique replay seeds")

    prior = entry["prior_evidence"]
    authority = catalog["source_evidence"]
    for key in (
        "workflow_run_id",
        "artifact_id",
        "artifact_zip_sha256",
        "execution_head_sha",
        "merged_main_sha",
    ):
        if prior.get(key) != authority.get(key):
            raise ValueError(
                f"{entry['failure_id']}: prior_evidence.{key} does not match catalog"
            )


def parse_attribution_args(values: list[str]) -> dict[int, dict]:
    result: dict[int, dict] = {}
    for raw in values:
        if "=" not in raw:
            raise ValueError("--attribution requires SEED=PATH")
        seed_text, path_text = raw.split("=", 1)
        seed = int(seed_text)
        if seed in result:
            raise ValueError(f"duplicate attribution seed: {seed}")
        value = load_json(Path(path_text))
        if int(value.get("seed", -1)) != seed:
            raise ValueError(f"attribution seed mismatch: {seed}")
        result[seed] = value
    return result


def case_map(attribution: dict) -> dict[str, dict]:
    cases = attribution.get("cases")
    if not isinstance(cases, list):
        raise ValueError("attribution cases missing")
    return {str(item["base_case_id"]): item for item in cases}


def transition_map(case: dict) -> dict[str, dict]:
    return {
        str(item["stage_profile"]): item
        for item in case.get("transitions", [])
    }


def validate_open_entry(entry: dict, attributions: dict[int, dict]) -> list[str]:
    errors: list[str] = []
    expected = entry["expected_replay"]
    base_case_id = entry["source_identity"]["base_case_id"]
    expected_signatures = sorted(expected["signature_union"])
    expected_stage = expected["first_observable_stage"]
    expected_transitions = expected.get("stage_transitions", {})

    observed_stages: list[str | None] = []
    observed_signature_sets: list[tuple[str, ...]] = []

    for seed in entry["source_identity"]["seeds"]:
        attribution = attributions.get(int(seed))
        if attribution is None:
            errors.append(f"seed {seed}: attribution missing")
            continue
        case = case_map(attribution).get(base_case_id)
        if case is None:
            errors.append(f"seed {seed}: base case {base_case_id} missing")
            continue

        if bool(case.get("all_stage_policy_passed")) != bool(
            expected["release_policy_passed"]
        ):
            errors.append(f"seed {seed}: release-policy state changed")

        stage = case.get("first_observable_stage")
        signatures = sorted(case.get("signature_union", []))
        observed_stages.append(stage)
        observed_signature_sets.append(tuple(signatures))

        if stage != expected_stage:
            errors.append(
                f"seed {seed}: first stage {stage!r} != {expected_stage!r}"
            )
        if signatures != expected_signatures:
            errors.append(
                f"seed {seed}: signatures {signatures!r} != {expected_signatures!r}"
            )

        transitions = transition_map(case)
        for profile, transition_expected in expected_transitions.items():
            transition = transitions.get(profile)
            if transition is None:
                errors.append(f"seed {seed}: transition {profile} missing")
                continue
            new_signatures = sorted(transition.get("new_signatures", []))
            wanted = sorted(transition_expected.get("new_signatures", []))
            if new_signatures != wanted:
                errors.append(
                    f"seed {seed}: {profile} new signatures "
                    f"{new_signatures!r} != {wanted!r}"
                )

    if expected.get("cross_seed_first_stage_consistent"):
        if not observed_stages or len(set(observed_stages)) != 1:
            errors.append("cross-seed first-stage consistency lost")
    if expected.get("cross_seed_signature_set_consistent"):
        if not observed_signature_sets or len(set(observed_signature_sets)) != 1:
            errors.append("cross-seed signature consistency lost")
    return errors


def validate_fixed_entry(entry: dict, attributions: dict[int, dict]) -> list[str]:
    errors: list[str] = []
    assertion = entry["regression_assertion"].get("fixed_regression")
    if not isinstance(assertion, dict):
        return ["FIXED_REGRESSION entry requires fixed_regression assertion"]
    forbidden = set(assertion.get("forbidden_signature_ids", []))
    base_case_id = entry["source_identity"]["base_case_id"]
    for seed in entry["source_identity"]["seeds"]:
        attribution = attributions.get(int(seed))
        if attribution is None:
            errors.append(f"seed {seed}: attribution missing")
            continue
        case = case_map(attribution).get(base_case_id)
        if case is None:
            errors.append(f"seed {seed}: base case {base_case_id} missing")
            continue
        active = set(case.get("signature_union", []))
        recurring = sorted(active & forbidden)
        if recurring:
            errors.append(f"seed {seed}: fixed signatures recurred: {recurring}")
    return errors


def validate_bank(
    catalog: dict,
    entries: list[dict],
    attributions: dict[int, dict],
) -> dict:
    required_seeds = sorted({
        int(seed)
        for entry in entries
        for seed in entry["source_identity"]["seeds"]
    })
    missing_seeds = sorted(set(required_seeds) - set(attributions))
    if missing_seeds:
        raise ValueError(f"missing attribution seeds: {missing_seeds}")

    results: list[dict] = []
    errors: list[str] = []
    for entry in entries:
        if entry["lifecycle_status"] == "OPEN_DIAGNOSTIC":
            entry_errors = validate_open_entry(entry, attributions)
        else:
            entry_errors = validate_fixed_entry(entry, attributions)
        errors.extend(f"{entry['failure_id']}: {item}" for item in entry_errors)
        results.append({
            "failure_id": entry["failure_id"],
            "lifecycle_status": entry["lifecycle_status"],
            "status": "PASS" if not entry_errors else "FAIL",
            "errors": entry_errors,
            "s004_eligible": False,
        })

    return {
        "schema_version": 1,
        "bank_id": catalog["bank_id"],
        "authority": catalog["authority"],
        "status": "PASS" if not errors else "FAIL",
        "errors": errors,
        "seeds": required_seeds,
        "entries": results,
        "s004_candidate_authority": False,
        "release_acceptance_authority": False,
    }


def self_test() -> None:
    entry = {
        "schema_version": 1,
        "failure_id": "F1",
        "lifecycle_status": "OPEN_DIAGNOSTIC",
        "authority": "replay-only",
        "source_identity": {
            "source_family": "s001",
            "base_case_id": "case-a",
            "generator": "g.py",
            "stage_interaction_generator": "s.py",
            "seeds": [1, 2],
        },
        "prior_evidence": {
            "workflow_run_id": 1,
            "artifact_id": 2,
            "artifact_zip_sha256": "a" * 64,
            "execution_head_sha": "b" * 40,
            "merged_main_sha": "c" * 40,
        },
        "expected_replay": {
            "release_policy_passed": True,
            "first_observable_stage": "NS",
            "signature_union": ["sig-a"],
            "stage_transitions": {
                "prefix-ns": {"new_signatures": ["sig-a"]},
            },
            "cross_seed_first_stage_consistent": True,
            "cross_seed_signature_set_consistent": True,
        },
        "regression_assertion": {
            "open_diagnostic": "reproduce",
            "fixed_regression": None,
        },
        "s004_eligibility": {"eligible": False, "satisfied": [], "missing": ["x"]},
        "root_cause_claim_authority": False,
        "release_acceptance_authority": False,
    }
    catalog = {
        "schema_version": 1,
        "bank_id": "test",
        "authority": "diagnostic-regression-only-not-release-or-candidate-authority",
        "source_evidence": {
            **entry["prior_evidence"],
            "phase": "S003",
            "artifact_name": "a",
            "artifact_zip_bytes": 1,
            "evidence_retention_note": "test",
        },
        "entries": ["entries/f1.json"],
        "lifecycle": {},
        "s004_candidate_authority": False,
    }
    with tempfile.TemporaryDirectory(prefix="ap-failure-bank-") as raw:
        root = Path(raw)
        (root / "entries").mkdir()
        (root / "catalog.json").write_text(
            json.dumps(catalog), encoding="utf-8"
        )
        (root / "entries/f1.json").write_text(
            json.dumps(entry), encoding="utf-8"
        )
        loaded_catalog, entries = load_catalog(root / "catalog.json")
        attribution = {
            "seed": 1,
            "cases": [{
                "base_case_id": "case-a",
                "first_observable_stage": "NS",
                "signature_union": ["sig-a"],
                "all_stage_policy_passed": True,
                "transitions": [{
                    "stage_profile": "prefix-ns",
                    "new_signatures": ["sig-a"],
                }],
            }],
        }
        attributions = {1: attribution, 2: {**attribution, "seed": 2}}
        result = validate_bank(loaded_catalog, entries, attributions)
        assert result["status"] == "PASS"

        attributions[2] = {
            **attributions[2],
            "cases": [{
                **attributions[2]["cases"][0],
                "first_observable_stage": "AGC",
            }],
        }
        result = validate_bank(loaded_catalog, entries, attributions)
        assert result["status"] == "FAIL"
    print("failure replay bank self-test: OK")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--catalog", type=Path)
    parser.add_argument("--attribution", action="append", default=[])
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    if args.self_test:
        self_test()
        return 0
    if args.catalog is None or not args.attribution or args.output is None:
        parser.error("--catalog, --attribution and --output are required")

    catalog, entries = load_catalog(args.catalog)
    attributions = parse_attribution_args(args.attribution)
    result = validate_bank(catalog, entries, attributions)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps({
        "status": result["status"],
        "entries": len(result["entries"]),
        "seeds": result["seeds"],
        "s004_candidate_authority": result["s004_candidate_authority"],
    }, sort_keys=True))
    return 0 if result["status"] == "PASS" else 3


if __name__ == "__main__":
    raise SystemExit(main())
