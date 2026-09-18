#!/usr/bin/env python3
"""Baseline-only qualification for future source-candidate authority pools.

This policy exists to prevent a fresh partition that the exact shipping baseline
itself fails from being misattributed as a candidate defect. It is forward-only:
terminal candidates are never reclassified or rescued by this tool.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "validation/tools"))
sys.path.insert(0, str(ROOT / "tests/validation"))
sys.path.insert(0, str(ROOT / ".github/research/continuous-optimization"))

import run_validation_engine as engine
import stage_source_candidate_evaluate as source_eval

DEFAULT_POLICY = (
    ROOT / ".github/research/continuous-optimization/source-candidate-authority-v2.json"
)


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON object required: {path}")
    return value


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_policy(policy: dict[str, Any]) -> None:
    if policy.get("schema_version") != 1:
        raise ValueError("authority-v2 schema_version must be 1")
    if policy.get("policy_id") != "source-candidate-baseline-qualified-authority-v2":
        raise ValueError("unexpected authority-v2 policy_id")
    if policy.get("authority") != "FUTURE_SOURCE_CANDIDATE_EVALUATION_POLICY_ONLY":
        raise ValueError("unexpected authority-v2 authority")
    scope = policy.get("scope", {})
    if scope.get("retroactive_reclassification_allowed") is not False:
        raise ValueError("authority-v2 must forbid retroactive reclassification")
    if scope.get("retroactive_rescue_allowed") is not False:
        raise ValueError("authority-v2 must forbid retroactive rescue")
    closed = scope.get("closed_candidates", [])
    required_closed = {
        "vad-confidence-tiered-hold-v1",
        "agc-error-adaptive-release-v1",
        "vad-strong-origin-bounded-hysteresis-v1",
    }
    if not required_closed.issubset(set(closed)):
        raise ValueError("authority-v2 must preserve known terminal candidate closures")

    prerequisites = policy.get("prerequisites", {})
    for key in (
        "candidate_identity_frozen_before_qualification",
        "candidate_values_frozen_before_qualification",
        "authority_pool_order_preregistered",
        "authority_pool_seed_and_generator_contract_preregistered",
    ):
        if prerequisites.get(key) is not True:
            raise ValueError(f"authority-v2 prerequisite must be true: {key}")
    if prerequisites.get("candidate_value_search") is not False:
        raise ValueError("authority-v2 forbids candidate value search during qualification")
    if prerequisites.get("candidate_execution_before_authority_lock") is not False:
        raise ValueError("candidate execution must be forbidden before authority lock")

    qualification = policy.get("baseline_qualification", {})
    if qualification.get("candidate_processor_forbidden") is not True:
        raise ValueError("baseline qualification must forbid candidate execution")
    if qualification.get("selection_rule") != (
        "select the first N baseline-valid partitions in the preregistered pool order"
    ):
        raise ValueError("authority-v2 selection rule drifted")
    if qualification.get("invalid_pool_entry_candidate_effect") != (
        "cannot reject, rank, tune, or rescue a candidate"
    ):
        raise ValueError("baseline-invalid authority role drifted")
    if qualification.get("candidate_budget_consumed_on_authority_incomplete") is not False:
        raise ValueError("authority incomplete cannot consume candidate budget")
    required_identity = qualification.get("selected_identity_binding")
    if required_identity != ["generator_seed", "corpus_id", "corpus_sha256"]:
        raise ValueError("authority-v2 identity binding drifted")

    evaluation = policy.get("candidate_evaluation", {})
    if evaluation.get("corpus_substitution_after_lock") is not False:
        raise ValueError("authority-v2 must forbid corpus substitution after lock")
    if evaluation.get("pool_reordering_after_qualification") is not False:
        raise ValueError("authority-v2 must forbid pool reordering after qualification")
    if evaluation.get("candidate_feedback_to_authority_selection") is not False:
        raise ValueError("candidate feedback may not affect authority selection")

    outcomes = policy.get("outcomes", {})
    if outcomes != {
        "qualified": "BASELINE_QUALIFIED_AUTHORITY_LOCK",
        "insufficient": "AUTHORITY_INCOMPLETE",
    }:
        raise ValueError("authority-v2 outcomes drifted")


def validate_candidate_contract(
    contract: dict[str, Any], policy: dict[str, Any], contract_path: Path
) -> dict[str, Any]:
    candidate_id = contract.get("candidate_id")
    if not isinstance(candidate_id, str) or not candidate_id:
        raise ValueError("candidate contract requires candidate_id")
    if candidate_id in set(policy["scope"]["closed_candidates"]):
        raise ValueError(
            f"authority-v2 cannot be used to re-evaluate terminal candidate: {candidate_id}"
        )
    if contract.get("authority") != "SOURCE_CANDIDATE_EVALUATION_ONLY":
        raise ValueError("candidate contract must remain source-candidate-evaluation-only")
    if int(contract.get("candidate_budget", -1)) != 1:
        raise ValueError("future authority-v2 candidate must begin with candidate_budget=1")

    evaluation = contract.get("fresh_candidate_evaluation", {})
    if evaluation.get("candidate_value_search") is not False:
        raise ValueError("candidate values must be frozen before authority qualification")

    v2 = contract.get("baseline_authority_qualification_v2")
    if not isinstance(v2, dict):
        raise ValueError("candidate contract missing baseline_authority_qualification_v2")
    if v2.get("policy_id") != policy["policy_id"]:
        raise ValueError("candidate authority-v2 policy binding drifted")
    required_count = int(v2.get("required_count", 0))
    pool_seeds = v2.get("pool_seeds")
    if required_count <= 0:
        raise ValueError("authority-v2 required_count must be positive")
    if not isinstance(pool_seeds, list) or len(pool_seeds) < required_count:
        raise ValueError("authority-v2 pool must be at least required_count")
    if any(not isinstance(seed, int) for seed in pool_seeds):
        raise ValueError("authority-v2 pool seeds must be integers")
    if len(pool_seeds) != len(set(pool_seeds)):
        raise ValueError("authority-v2 pool seeds must be unique")
    if v2.get("selection_rule") != policy["baseline_qualification"]["selection_rule"]:
        raise ValueError("candidate authority-v2 selection rule drifted")
    if v2.get("candidate_execution_before_lock") is not False:
        raise ValueError("candidate execution before authority lock must be false")

    return {
        "candidate_id": candidate_id,
        "required_count": required_count,
        "pool_seeds": pool_seeds,
        "contract_sha256": sha256_file(contract_path),
    }


def summarize_baseline_partition(
    baseline_processor: Path, corpus_path: Path
) -> dict[str, Any]:
    partition = source_eval.collect_vad_partition(baseline_processor, corpus_path)
    report = source_eval.vad_partition_summary(partition)
    invalid_cases = [
        {
            "case_id": row["case_id"],
            "profile": row["profile"],
            "violations": row["violations"],
        }
        for row in report["cases"]
        if row["violations"]
    ]
    return {
        "identity": {
            "generator_seed": int(partition["seed"]),
            "corpus_id": partition["corpus_id"],
            "corpus_sha256": engine.sha256_file(corpus_path),
        },
        "baseline_validation_result": report["validation_result"],
        "baseline_summary": report["summary"],
        "absolute_case_gate_violations": invalid_cases,
        "baseline_valid": report["validation_result"] == "PASS" and not invalid_cases,
    }


def select_authority(
    entries: list[dict[str, Any]], required_count: int
) -> tuple[str, list[dict[str, Any]], list[dict[str, Any]]]:
    if required_count <= 0:
        raise ValueError("required_count must be positive")
    seeds = [int(item["identity"]["generator_seed"]) for item in entries]
    hashes = [str(item["identity"]["corpus_sha256"]) for item in entries]
    if len(seeds) != len(set(seeds)):
        raise ValueError("authority pool contains duplicate generator seeds")
    if len(hashes) != len(set(hashes)):
        raise ValueError("authority pool contains duplicate corpus hashes")

    selected: list[dict[str, Any]] = []
    invalid: list[dict[str, Any]] = []
    for item in entries:
        if item.get("baseline_valid") is True:
            if len(selected) < required_count:
                selected.append(item)
        else:
            invalid.append(item)

    decision = (
        "BASELINE_QUALIFIED_AUTHORITY_LOCK"
        if len(selected) == required_count
        else "AUTHORITY_INCOMPLETE"
    )
    return decision, selected, invalid


def run(
    baseline_processor: Path,
    pool_corpora: list[Path],
    candidate_contract_path: Path,
    policy_path: Path,
    output_path: Path,
) -> dict[str, Any]:
    policy = load_json(policy_path)
    validate_policy(policy)
    contract = load_json(candidate_contract_path)
    binding = validate_candidate_contract(contract, policy, candidate_contract_path)

    if len(pool_corpora) != len(binding["pool_seeds"]):
        raise ValueError("authority pool corpus count does not match preregistered pool")
    entries = [
        summarize_baseline_partition(baseline_processor, corpus)
        for corpus in pool_corpora
    ]
    observed_seeds = [item["identity"]["generator_seed"] for item in entries]
    if observed_seeds != binding["pool_seeds"]:
        raise ValueError(
            f"authority pool order/seed drift: {observed_seeds} != {binding['pool_seeds']}"
        )

    decision, selected, invalid = select_authority(entries, binding["required_count"])
    result = {
        "schema_version": 1,
        "authority": "baseline-only-source-candidate-authority-qualification",
        "policy_id": policy["policy_id"],
        "policy_sha256": sha256_file(policy_path),
        "candidate_id": binding["candidate_id"],
        "candidate_contract_sha256": binding["contract_sha256"],
        "decision": decision,
        "required_count": binding["required_count"],
        "pool_order": [item["identity"] for item in entries],
        "selected_authority": [item["identity"] for item in selected],
        "invalid_pool_entries": [
            {
                "identity": item["identity"],
                "status": "AUTHORITY_POOL_ENTRY_INVALID",
                "baseline_validation_result": item["baseline_validation_result"],
                "absolute_case_gate_violations": item["absolute_case_gate_violations"],
            }
            for item in invalid
        ],
        "candidate_execution_allowed": decision == "BASELINE_QUALIFIED_AUTHORITY_LOCK",
        "candidate_budget_consumed": False,
        "candidate_feedback_used": False,
        "retroactive_candidate_reclassification": False,
        "shipping_authority": False,
        "source_merge_authorized": False,
        "automatic_main_mutation": False,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return result


def self_test() -> None:
    policy = load_json(DEFAULT_POLICY)
    validate_policy(policy)

    def entry(seed: int, digest: str, valid: bool) -> dict[str, Any]:
        return {
            "identity": {
                "generator_seed": seed,
                "corpus_id": f"c-{seed}",
                "corpus_sha256": digest * 64,
            },
            "baseline_validation_result": "PASS" if valid else "FAIL",
            "absolute_case_gate_violations": [] if valid else [{"case_id": "x"}],
            "baseline_valid": valid,
        }

    pool = [
        entry(1, "a", False),
        entry(2, "b", True),
        entry(3, "c", False),
        entry(4, "d", True),
        entry(5, "e", True),
    ]
    decision, selected, invalid = select_authority(pool, 3)
    assert decision == "BASELINE_QUALIFIED_AUTHORITY_LOCK"
    assert [x["identity"]["generator_seed"] for x in selected] == [2, 4, 5]
    assert [x["identity"]["generator_seed"] for x in invalid] == [1, 3]

    decision2, selected2, invalid2 = select_authority(pool, 4)
    assert decision2 == "AUTHORITY_INCOMPLETE"
    assert [x["identity"]["generator_seed"] for x in selected2] == [2, 4, 5]
    assert len(invalid2) == 2

    try:
        select_authority([entry(1, "a", True), entry(1, "b", True)], 1)
    except ValueError as exc:
        assert "duplicate generator seeds" in str(exc)
    else:
        raise AssertionError("duplicate seed authority pool was accepted")

    terminal = {
        "candidate_id": "vad-strong-origin-bounded-hysteresis-v1",
        "authority": "SOURCE_CANDIDATE_EVALUATION_ONLY",
        "candidate_budget": 1,
        "fresh_candidate_evaluation": {"candidate_value_search": False},
        "baseline_authority_qualification_v2": {
            "policy_id": policy["policy_id"],
            "required_count": 1,
            "pool_seeds": [1],
            "selection_rule": policy["baseline_qualification"]["selection_rule"],
            "candidate_execution_before_lock": False,
        },
    }
    import tempfile
    with tempfile.TemporaryDirectory(prefix="ap-source-authority-v2-") as tmp:
        path = Path(tmp) / "candidate.json"
        path.write_text(json.dumps(terminal) + "\n", encoding="utf-8")
        try:
            validate_candidate_contract(terminal, policy, path)
        except ValueError as exc:
            assert "terminal candidate" in str(exc)
        else:
            raise AssertionError("terminal candidate was allowed into authority-v2")

    print("source-candidate baseline-qualified authority v2 self-test: OK")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--validate-policy", action="store_true")
    parser.add_argument("--baseline-processor", type=Path)
    parser.add_argument("--pool-corpus", action="append", type=Path, default=[])
    parser.add_argument("--candidate-contract", type=Path)
    parser.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    if args.self_test:
        self_test()
        return 0
    policy = load_json(args.policy)
    validate_policy(policy)
    if args.validate_policy:
        print(json.dumps({
            "result": "PASS",
            "policy_id": policy["policy_id"],
            "policy_sha256": sha256_file(args.policy),
        }, sort_keys=True))
        return 0
    if args.baseline_processor is None or args.candidate_contract is None or args.output is None:
        parser.error(
            "baseline processor, candidate contract and output are required for qualification"
        )
    result = run(
        args.baseline_processor.resolve(),
        [path.resolve() for path in args.pool_corpus],
        args.candidate_contract.resolve(),
        args.policy.resolve(),
        args.output.resolve(),
    )
    print(json.dumps({
        "candidate_id": result["candidate_id"],
        "decision": result["decision"],
        "selected_seeds": [
            item["generator_seed"] for item in result["selected_authority"]
        ],
        "invalid_pool_entries": len(result["invalid_pool_entries"]),
        "candidate_execution_allowed": result["candidate_execution_allowed"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
