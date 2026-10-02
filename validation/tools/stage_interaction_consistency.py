#!/usr/bin/env python3
"""Compare S003 first-observable-stage evidence across fresh deterministic seeds."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def build(items: list[dict]) -> dict:
    if len(items) < 2:
        raise ValueError("at least two attribution reports are required")
    by_seed = {int(item["seed"]): item for item in items}
    if len(by_seed) != len(items):
        raise ValueError("attribution seeds must be unique")

    case_sets = [set(x["base_case_id"] for x in item["cases"]) for item in items]
    if any(case_set != case_sets[0] for case_set in case_sets[1:]):
        raise ValueError("attribution reports must contain identical base cases")

    rows: list[dict] = []
    for base_case_id in sorted(case_sets[0]):
        observations = []
        for seed, item in sorted(by_seed.items()):
            case = next(x for x in item["cases"] if x["base_case_id"] == base_case_id)
            observations.append({
                "seed": seed,
                "first_observable_stage": case["first_observable_stage"],
                "signature_union": case["signature_union"],
                "all_stage_policy_passed": case["all_stage_policy_passed"],
            })
        stages = {x["first_observable_stage"] for x in observations}
        signatures = {tuple(x["signature_union"]) for x in observations}
        repeated_stage = len(stages) == 1 and None not in stages
        rows.append({
            "base_case_id": base_case_id,
            "observations": observations,
            "first_observable_stage_consistent": len(stages) == 1,
            "signature_set_consistent": len(signatures) == 1,
            "repeated_non_null_stage": repeated_stage,
            "s004_stage_consistency_precondition": repeated_stage and len(signatures) == 1,
        })

    return {
        "schema_version": 1,
        "authority": "candidate-zero-consistency-evidence-only",
        "seeds": sorted(by_seed),
        "cases": rows,
        "summary": {
            "case_count": len(rows),
            "consistent_first_stage_count": sum(
                x["first_observable_stage_consistent"] for x in rows
            ),
            "repeated_non_null_stage_count": sum(
                x["repeated_non_null_stage"] for x in rows
            ),
            "s004_stage_consistency_precondition_count": sum(
                x["s004_stage_consistency_precondition"] for x in rows
            ),
        },
        "s004_candidate_authority": False,
        "note": (
            "Stage consistency alone is insufficient: cross-source repetition, "
            "artifact exclusion and resource fit are still required."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--attribution", type=Path, action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    items = [
        json.loads(path.read_text(encoding="utf-8"))
        for path in args.attribution
    ]
    result = build(items)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(result["summary"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
