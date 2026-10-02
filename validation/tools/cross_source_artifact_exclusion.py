#!/usr/bin/env python3
"""Aggregate S003 dEchorate cross-source and artifact-exclusion evidence."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

ROOM_RE = re.compile(r"^(capture-clipping|mic-gain-delay-mismatch)-room([0-9]{6})$")


def signature_ids(stage: dict) -> set[str]:
    return {item["id"] for item in stage.get("diagnostic_signatures", [])}


def load_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path}: JSON object required")
    return value


def analyze_one(attribution: dict, contract: dict) -> dict:
    seed = int(attribution["seed"])
    expected_by_failure = {
        spec["base_failure"]: {
            "durable_failure_id": failure_id,
            "expected_first_observable_stage": spec["expected_first_observable_stage"],
            "expected_signature_union": set(spec["expected_signature_union"]),
        }
        for failure_id, spec in contract["expected_durable_signatures"].items()
    }
    rows: list[dict] = []
    seen_rooms: dict[str, set[str]] = {key: set() for key in expected_by_failure}

    for case in attribution["cases"]:
        match = ROOM_RE.fullmatch(case["base_case_id"])
        if not match:
            raise ValueError(f"unexpected base_case_id: {case['base_case_id']}")
        failure_kind, room = match.groups()
        if failure_kind not in expected_by_failure:
            raise ValueError(f"unexpected failure kind: {failure_kind}")
        if room in seen_rooms[failure_kind]:
            raise ValueError(f"duplicate room/failure: {failure_kind}/{room}")
        seen_rooms[failure_kind].add(room)

        expected = expected_by_failure[failure_kind]
        stages = case["stages"]
        by_stage = {item["stage"]: item for item in stages}
        raw = signature_ids(by_stage["raw"])
        final = signature_ids(by_stage["final"])
        union = set(case["signature_union"])
        pre_final_union: set[str] = set()
        for stage in stages:
            if stage["stage"] != "final":
                pre_final_union.update(signature_ids(stage))

        exact_reproduction = (
            case["first_observable_stage"] == expected["expected_first_observable_stage"]
            and union == expected["expected_signature_union"]
        )
        measurement_domain_artifact_excluded = not bool(
            raw & expected["expected_signature_union"]
        )
        downstream_transfer_artifact_excluded = (
            case["first_observable_stage"] not in {None, "final"}
            and expected["expected_signature_union"] <= pre_final_union
        )
        rows.append({
            "durable_failure_id": expected["durable_failure_id"],
            "failure_kind": failure_kind,
            "room": room,
            "first_observable_stage": case["first_observable_stage"],
            "signature_union": sorted(union),
            "raw_signatures": sorted(raw),
            "final_signatures": sorted(final),
            "pre_final_signature_union": sorted(pre_final_union),
            "exact_cross_source_reproduction": exact_reproduction,
            "measurement_domain_artifact_excluded": measurement_domain_artifact_excluded,
            "downstream_transfer_artifact_excluded": downstream_transfer_artifact_excluded,
        })

    required_rooms = int(contract["public_source"]["expected_room_count"])
    for failure_kind, rooms in seen_rooms.items():
        if len(rooms) != required_rooms:
            raise ValueError(
                f"{failure_kind}: expected {required_rooms} rooms, got {len(rooms)}"
            )

    threshold = int(
        contract["preregistered_evidence_rules"]["minimum_exact_rooms_per_seed"]
    )
    failures: dict[str, dict] = {}
    for failure_kind, expected in expected_by_failure.items():
        subset = [row for row in rows if row["failure_kind"] == failure_kind]
        exact = sum(row["exact_cross_source_reproduction"] for row in subset)
        measurement = sum(
            row["measurement_domain_artifact_excluded"] for row in subset
        )
        transfer = sum(
            row["downstream_transfer_artifact_excluded"] for row in subset
        )
        failures[expected["durable_failure_id"]] = {
            "failure_kind": failure_kind,
            "rooms": len(subset),
            "minimum_required_rooms": threshold,
            "exact_cross_source_reproduction_rooms": exact,
            "measurement_domain_artifact_excluded_rooms": measurement,
            "downstream_transfer_artifact_excluded_rooms": transfer,
            "cross_source_repetition_satisfied": exact >= threshold,
            "measurement_domain_artifact_exclusion_satisfied": measurement >= threshold,
            "downstream_transfer_artifact_exclusion_satisfied": transfer >= threshold,
        }

    return {"seed": seed, "failures": failures, "rooms": rows}


def aggregate(attributions: list[dict], contract: dict) -> dict:
    expected_seeds = sorted(int(x) for x in contract["fresh_seeds"])
    by_seed = {int(item["seed"]): item for item in attributions}
    if sorted(by_seed) != expected_seeds:
        raise ValueError(f"fresh seed mismatch: {sorted(by_seed)} != {expected_seeds}")

    per_seed = [analyze_one(by_seed[seed], contract) for seed in expected_seeds]
    failure_ids = sorted(contract["expected_durable_signatures"])
    decisions: dict[str, dict] = {}
    for failure_id in failure_ids:
        observations = [
            item["failures"][failure_id] for item in per_seed
        ]
        cross = all(x["cross_source_repetition_satisfied"] for x in observations)
        measurement = all(
            x["measurement_domain_artifact_exclusion_satisfied"] for x in observations
        )
        transfer = all(
            x["downstream_transfer_artifact_exclusion_satisfied"] for x in observations
        )
        decisions[failure_id] = {
            "cross_source_repetition_satisfied": cross,
            "measurement_domain_artifact_exclusion_satisfied": measurement,
            "downstream_transfer_artifact_exclusion_satisfied": transfer,
            "all_three_s003_evidence_conditions_satisfied": (
                cross and measurement and transfer
            ),
            "per_seed": [
                {
                    "seed": item["seed"],
                    **item["failures"][failure_id],
                }
                for item in per_seed
            ],
            "s004_candidate_authority": False,
            "remaining_s004_precondition": "bounded_candidate_resource_fit",
        }

    return {
        "schema_version": 1,
        "investigation_id": contract["id"],
        "authority": contract["authority"],
        "source_family": "dechorate-measured-rir",
        "fresh_seeds": expected_seeds,
        "decisions": decisions,
        "per_seed": per_seed,
        "candidate_authority": False,
        "shipping_change_authority": False,
        "root_cause_claim_authority": False,
        "note": (
            "A satisfied S003 evidence condition advances evidence only. "
            "It never creates or selects a candidate."
        ),
    }


def self_test() -> None:
    assert signature_ids({"diagnostic_signatures": [{"id": "x"}]}) == {"x"}
    assert ROOM_RE.fullmatch("capture-clipping-room000000")
    assert ROOM_RE.fullmatch("mic-gain-delay-mismatch-room020002")
    assert not ROOM_RE.fullmatch("other-room000000")
    print("cross-source artifact-exclusion evaluator self-test: OK")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--contract", type=Path)
    parser.add_argument("--attribution", type=Path, action="append")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    if args.contract is None or not args.attribution or args.output is None:
        parser.error("--contract, --attribution and --output are required")
    contract = load_json(args.contract)
    attributions = [load_json(path) for path in args.attribution]
    result = aggregate(attributions, contract)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps({
        failure_id: {
            "cross_source": decision["cross_source_repetition_satisfied"],
            "measurement_excluded": decision[
                "measurement_domain_artifact_exclusion_satisfied"
            ],
            "transfer_excluded": decision[
                "downstream_transfer_artifact_exclusion_satisfied"
            ],
        }
        for failure_id, decision in result["decisions"].items()
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
