#!/usr/bin/env python3
"""Aggregate S003 severe-near-reference subsignature transfer on SLR31."""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path

BASE_RE = re.compile(
    r"^(capture-clipping|mic-gain-delay-mismatch)-(u[0-9]{2})$"
)
SIGNATURE = "severe-near-reference-degradation"


def load_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path}: JSON object required")
    return value


def analyze(attribution: dict, minimum: int, total: int) -> dict:
    by_kind: dict[str, list[dict]] = {
        "capture-clipping": [],
        "mic-gain-delay-mismatch": [],
    }
    for case in attribution.get("cases", []):
        match = BASE_RE.fullmatch(str(case.get("base_case_id", "")))
        if match is None:
            raise ValueError(f"unexpected base case: {case.get('base_case_id')}")
        kind, utterance = match.groups()
        union = set(case.get("signature_union", []))
        by_kind[kind].append({
            "utterance_id": utterance,
            "subsignature_present": SIGNATURE in union,
            "signature_union": sorted(union),
            "first_observable_stage": case.get("first_observable_stage"),
        })

    result: dict[str, dict] = {}
    for kind, rows in by_kind.items():
        if len(rows) != total:
            raise ValueError(f"{kind}: expected {total} utterances, got {len(rows)}")
        if len({row["utterance_id"] for row in rows}) != total:
            raise ValueError(f"{kind}: duplicate utterance ids")
        count = sum(row["subsignature_present"] for row in rows)
        stages = Counter(
            str(row["first_observable_stage"])
            for row in rows
            if row["subsignature_present"]
        )
        result[kind] = {
            "utterances": total,
            "minimum_required": minimum,
            "subsignature_reproduced_utterances": count,
            "subsignature_repetition_satisfied": count >= minimum,
            "first_observable_stage_distribution": dict(sorted(stages.items())),
            "rows": sorted(rows, key=lambda row: row["utterance_id"]),
        }
    return {
        "seed": int(attribution["seed"]),
        "failure_families": result,
    }


def aggregate(contract: dict, attributions: list[dict]) -> dict:
    seeds = sorted(int(x) for x in contract["fresh_seeds"])
    by_seed = {int(item["seed"]): item for item in attributions}
    if sorted(by_seed) != seeds:
        raise ValueError(f"seed mismatch: {sorted(by_seed)} != {seeds}")
    rules = contract["preregistered_evidence_rules"]
    minimum = int(rules["minimum_reproduced_utterances_per_seed"])
    total = int(rules["required_total_utterances_per_seed"])
    per_seed = [analyze(by_seed[seed], minimum, total) for seed in seeds]

    failures: dict[str, dict] = {}
    mapping = {
        "FR-S003-CAPTURE-CLIPPING-V1": "capture-clipping",
        "FR-S003-MIC-GAIN-DELAY-MISMATCH-V1": "mic-gain-delay-mismatch",
    }
    for failure_id, kind in mapping.items():
        observations = [
            {
                "seed": item["seed"],
                **item["failure_families"][kind],
            }
            for item in per_seed
        ]
        repeated = all(
            item["subsignature_repetition_satisfied"] for item in observations
        )
        failures[failure_id] = {
            "failure_kind": kind,
            "required_subsignature": SIGNATURE,
            "second_public_family_repetition_satisfied": repeated,
            "per_seed": observations,
            "candidate_authority": False,
        }

    any_repeated = any(
        item["second_public_family_repetition_satisfied"]
        for item in failures.values()
    )
    return {
        "schema_version": 1,
        "investigation_id": contract["id"],
        "authority": contract["authority"],
        "source_family": "openslr-slr31-clean-speech",
        "fresh_seeds": seeds,
        "required_subsignature": SIGNATURE,
        "failures": failures,
        "second_public_dataset_family_counted": any_repeated,
        "multiple_public_dataset_repetition_blocker_satisfied": any_repeated,
        "public_dataset_family_count_if_satisfied": 2 if any_repeated else 1,
        "s004_candidate_authority": False,
        "remaining_s004_blockers": [
            "measurement_domain_artifact_exclusion",
            "downstream_transfer_artifact_exclusion",
            "bounded_candidate_resource_fit",
        ],
        "note": (
            "This result may satisfy only the multiple-public-dataset repetition "
            "blocker for the stable severe subsignature. It does not open S004."
        ),
    }


def self_test() -> None:
    assert BASE_RE.fullmatch("capture-clipping-u00")
    assert BASE_RE.fullmatch("mic-gain-delay-mismatch-u07")
    assert not BASE_RE.fullmatch("capture-clipping-room000000")
    print("SLR31 subsignature transfer evaluator self-test: OK")


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
    result = aggregate(
        load_json(args.contract),
        [load_json(path) for path in args.attribution],
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps({
        failure_id: {
            "repeated": item["second_public_family_repetition_satisfied"],
            "counts": [
                obs["subsignature_reproduced_utterances"]
                for obs in item["per_seed"]
            ],
        }
        for failure_id, item in result["failures"].items()
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
