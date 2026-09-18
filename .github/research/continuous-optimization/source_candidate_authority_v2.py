#!/usr/bin/env python3
"""Baseline-only qualification for future source-candidate authority pools.

The exact source-base executable qualifies a preregistered pool before any
candidate executes. Baseline-invalid pool entries are diagnostic only and cannot
reject, rank, tune, or rescue a candidate. This policy is forward-only:
terminal candidates are never reclassified or rescued by this tool.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "validation/tools"))
sys.path.insert(0, str(ROOT / "tests/validation"))
sys.path.insert(0, str(ROOT / ".github/research/continuous-optimization"))

import agc_dynamics_diagnostic as agc_diag
import run_validation_engine as engine
import stage_source_candidate_evaluate as source_eval

DEFAULT_POLICY = (
    ROOT / ".github/research/continuous-optimization/source-candidate-authority-v2.json"
)
SOURCE_SHA_RE = re.compile(r"^[0-9a-f]{40}$")


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
    if qualification.get("selected_identity_binding") != [
        "generator_seed", "corpus_id", "corpus_sha256"
    ]:
        raise ValueError("authority-v2 identity binding drifted")

    profiles = policy.get("qualification_profiles")
    if not isinstance(profiles, dict) or set(profiles) != {"vad-stage", "agc-dynamics"}:
        raise ValueError("authority-v2 qualification profiles must be VAD + AGC")
    expected_targets = {
        "vad-stage": ("ap_process_pcm", []),
        "agc-dynamics": (
            "agc_dynamics_probe",
            ["agc_target_dbfs", "limiter_dbfs"],
        ),
    }
    for name, (target, args) in expected_targets.items():
        spec = profiles.get(name)
        if not isinstance(spec, dict):
            raise ValueError(f"invalid qualification profile: {name}")
        if spec.get("baseline_executable_target") != target:
            raise ValueError(f"qualification profile target drift: {name}")
        if spec.get("baseline_args_required") != args:
            raise ValueError(f"qualification profile baseline args drift: {name}")
        if not isinstance(spec.get("absolute_gate_semantics"), str):
            raise ValueError(f"qualification profile semantics missing: {name}")

    evaluation = policy.get("candidate_evaluation", {})
    if evaluation.get("corpus_substitution_after_lock") is not False:
        raise ValueError("authority-v2 must forbid corpus substitution after lock")
    if evaluation.get("pool_reordering_after_qualification") is not False:
        raise ValueError("authority-v2 must forbid pool reordering after qualification")
    if evaluation.get("candidate_feedback_to_authority_selection") is not False:
        raise ValueError("candidate feedback may not affect authority selection")

    lock = policy.get("authority_lock", {})
    if lock.get("required_before_candidate_execution") is not True:
        raise ValueError("authority-v2 lock must be required before candidate execution")
    if lock.get("predeclared_lock_path_required") is not True:
        raise ValueError("authority-v2 lock path must be preregistered")
    if lock.get("lock_path_root") != (
        ".github/research/continuous-optimization/source-authority-locks"
    ):
        raise ValueError("authority-v2 lock root drifted")
    if lock.get("qualification_limit_per_candidate_identity") != 1:
        raise ValueError("authority-v2 qualification limit must remain one")
    if lock.get("qualification_replay_additional_authority") is not False:
        raise ValueError("qualification replay cannot add authority")
    required_lock_bindings = {
        "policy_sha256",
        "candidate_contract_sha256",
        "source_base_sha",
        "qualification_profile",
        "baseline_executable_target",
        "baseline_executable_sha256",
        "baseline_args",
        "generator_contract",
        "pool_order",
        "selected_authority",
    }
    if set(lock.get("lock_must_bind", [])) != required_lock_bindings:
        raise ValueError("authority-v2 lock binding set drifted")

    outcomes = policy.get("outcomes", {})
    if outcomes != {
        "qualified": "BASELINE_QUALIFIED_AUTHORITY_LOCK",
        "insufficient": "AUTHORITY_INCOMPLETE",
    }:
        raise ValueError("authority-v2 outcomes drifted")


def _validate_generator(generator: Any) -> dict[str, Any]:
    if not isinstance(generator, dict):
        raise ValueError("authority-v2 generator contract must be an object")
    path = generator.get("path")
    seconds = generator.get("seconds")
    extra_args = generator.get("extra_args", [])
    if not isinstance(path, str) or not path or Path(path).is_absolute() or ".." in Path(path).parts:
        raise ValueError("authority-v2 generator path must be repository-relative")
    if not isinstance(seconds, int) or seconds <= 0:
        raise ValueError("authority-v2 generator seconds must be positive integer")
    if not isinstance(extra_args, list) or any(not isinstance(x, str) for x in extra_args):
        raise ValueError("authority-v2 generator extra_args must be string list")
    return {"path": path, "seconds": seconds, "extra_args": extra_args}


def _validate_execution_workflow_path(candidate_id: str, raw: Any) -> str:
    if not isinstance(raw, str) or not raw:
        raise ValueError("authority-v2 execution_workflow is required")
    if not re.fullmatch(r"[A-Za-z0-9._-]+", candidate_id):
        raise ValueError("authority-v2 candidate_id must be workflow-path safe")
    expected = (
        ".github/workflows/research-source-candidate-v2-"
        f"{candidate_id}.yml"
    )
    if raw != expected:
        raise ValueError(
            f"authority-v2 execution workflow drift: {raw!r} != {expected!r}"
        )
    return raw


def _validate_lock_path(candidate_id: str, raw: Any, policy: dict[str, Any]) -> str:
    if not isinstance(raw, str) or not raw:
        raise ValueError("authority-v2 authority_lock_path is required")
    path = Path(raw)
    root = Path(policy["authority_lock"]["lock_path_root"])
    if path.is_absolute() or ".." in path.parts or path.suffix != ".json":
        raise ValueError("authority-v2 lock path must be safe repo-relative JSON")
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise ValueError("authority-v2 lock path must remain under canonical lock root") from exc
    if path.name != f"{candidate_id}.json":
        raise ValueError("authority-v2 lock filename must equal candidate_id.json")
    return path.as_posix()


def _validate_profile_binding(
    profile: str, v2: dict[str, Any], policy: dict[str, Any]
) -> tuple[str, dict[str, float]]:
    profiles = policy["qualification_profiles"]
    if profile not in profiles:
        raise ValueError(f"unsupported authority-v2 qualification_profile: {profile}")
    spec = profiles[profile]
    target = v2.get("baseline_executable_target")
    if target != spec["baseline_executable_target"]:
        raise ValueError(
            f"baseline executable target drift for {profile}: "
            f"{target!r} != {spec['baseline_executable_target']!r}"
        )

    args = v2.get("baseline_args", {})
    if not isinstance(args, dict):
        raise ValueError("authority-v2 baseline_args must be an object")
    required = spec["baseline_args_required"]
    if set(args) != set(required):
        raise ValueError(
            f"baseline args drift for {profile}: "
            f"actual={sorted(args)} expected={sorted(required)}"
        )
    normalized: dict[str, float] = {}
    for key in required:
        value = float(args[key])
        if not math.isfinite(value):
            raise ValueError(f"baseline arg must be finite: {key}")
        normalized[key] = value

    if profile == "agc-dynamics":
        target_dbfs = normalized["agc_target_dbfs"]
        limiter_dbfs = normalized["limiter_dbfs"]
        if not -60.0 <= target_dbfs <= -1.0:
            raise ValueError("agc_target_dbfs out of product bounds")
        if not -20.0 <= limiter_dbfs <= -0.1:
            raise ValueError("limiter_dbfs out of product bounds")
        if target_dbfs >= limiter_dbfs:
            raise ValueError("AGC target must remain below limiter")
    return str(target), normalized


def validate_candidate_contract(
    contract: dict[str, Any], policy: dict[str, Any], contract_path: Path
) -> dict[str, Any]:
    if contract.get("schema_version") != 2:
        raise ValueError("authority-v2 candidate contract schema_version must be 2")
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
    source_base_sha = contract.get("source_base_sha")
    if not isinstance(source_base_sha, str) or not SOURCE_SHA_RE.fullmatch(source_base_sha):
        raise ValueError("future authority-v2 candidate requires exact 40-hex source_base_sha")

    execution_workflow = _validate_execution_workflow_path(
        candidate_id, contract.get("execution_workflow")
    )

    evaluation = contract.get("fresh_candidate_evaluation", {})
    if not isinstance(evaluation, dict):
        raise ValueError("candidate contract requires fresh_candidate_evaluation")
    if evaluation.get("candidate_value_search") is not False:
        raise ValueError("candidate values must be frozen before authority qualification")

    v2 = contract.get("baseline_authority_qualification_v2")
    if not isinstance(v2, dict):
        raise ValueError("candidate contract missing baseline_authority_qualification_v2")
    if v2.get("policy_id") != policy["policy_id"]:
        raise ValueError("candidate authority-v2 policy binding drifted")
    profile = v2.get("qualification_profile")
    if not isinstance(profile, str):
        raise ValueError("candidate authority-v2 qualification_profile missing")
    baseline_target, baseline_args = _validate_profile_binding(profile, v2, policy)

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
    if v2.get("qualification_limit") != 1:
        raise ValueError("authority-v2 qualification_limit must remain one")
    authority_lock_path = _validate_lock_path(
        candidate_id, v2.get("authority_lock_path"), policy
    )
    generator = _validate_generator(v2.get("generator"))

    return {
        "candidate_id": candidate_id,
        "source_base_sha": source_base_sha,
        "execution_workflow": execution_workflow,
        "required_count": required_count,
        "pool_seeds": pool_seeds,
        "qualification_profile": profile,
        "baseline_executable_target": baseline_target,
        "baseline_args": baseline_args,
        "generator": generator,
        "qualification_limit": 1,
        "authority_lock_path": authority_lock_path,
        "contract_sha256": sha256_file(contract_path),
    }


def _corpus_identity(corpus_path: Path) -> dict[str, Any]:
    corpus = load_json(corpus_path)
    generator = corpus.get("generator", {})
    if not isinstance(generator, dict) or not isinstance(generator.get("seed"), int):
        raise ValueError(f"corpus generator seed missing: {corpus_path}")
    return {
        "generator_seed": int(generator["seed"]),
        "corpus_id": corpus.get("corpus_id"),
        "corpus_sha256": engine.sha256_file(corpus_path),
    }


def summarize_vad_baseline(
    baseline_executable: Path, corpus_path: Path, baseline_args: dict[str, float]
) -> dict[str, Any]:
    if baseline_args:
        raise ValueError("vad-stage baseline_args must remain empty")
    partition = source_eval.collect_vad_partition(baseline_executable, corpus_path)
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


def summarize_agc_baseline(
    baseline_executable: Path, corpus_path: Path, baseline_args: dict[str, float]
) -> dict[str, Any]:
    report = agc_diag.diagnose(
        baseline_executable,
        corpus_path,
        target_override=baseline_args["agc_target_dbfs"],
        limiter_override=baseline_args["limiter_dbfs"],
    )
    invalid_cases = [
        {
            "case_id": case["case_id"],
            "violations": case["violations"],
        }
        for case in report["cases"]
        if case["violations"]
    ]
    passed = sum(bool(case.get("passed")) for case in report["cases"])
    summary = {
        "cases": len(report["cases"]),
        "passed_cases": passed,
        "pass_rate": passed / max(1, len(report["cases"])),
        "effective_tuning": report["effective_tuning"],
    }
    return {
        "identity": _corpus_identity(corpus_path),
        "baseline_validation_result": report["validation_result"],
        "baseline_summary": summary,
        "absolute_case_gate_violations": invalid_cases,
        "baseline_valid": report["validation_result"] == "PASS" and not invalid_cases,
    }


def summarize_baseline_partition(
    qualification_profile: str,
    baseline_executable: Path,
    corpus_path: Path,
    baseline_args: dict[str, float],
) -> dict[str, Any]:
    if qualification_profile == "vad-stage":
        return summarize_vad_baseline(
            baseline_executable, corpus_path, baseline_args
        )
    if qualification_profile == "agc-dynamics":
        return summarize_agc_baseline(
            baseline_executable, corpus_path, baseline_args
        )
    raise ValueError(
        f"unsupported authority-v2 qualification_profile: {qualification_profile}"
    )


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
    baseline_executable: Path,
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
        summarize_baseline_partition(
            binding["qualification_profile"],
            baseline_executable,
            corpus,
            binding["baseline_args"],
        )
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
        "source_base_sha": binding["source_base_sha"],
        "qualification_profile": binding["qualification_profile"],
        "baseline_executable_target": binding["baseline_executable_target"],
        "baseline_executable_sha256": engine.sha256_file(baseline_executable),
        "baseline_args": binding["baseline_args"],
        "generator_contract": binding["generator"],
        "qualification_limit": binding["qualification_limit"],
        "expected_authority_lock_path": binding["authority_lock_path"],
        "qualification_replay_additional_authority": False,
        "decision": decision,
        "required_count": binding["required_count"],
        "pool_order": [item["identity"] for item in entries],
        "selected_authority": [item["identity"] for item in selected],
        "invalid_pool_entries": [
            {
                "identity": item["identity"],
                "status": "AUTHORITY_POOL_ENTRY_INVALID",
                "baseline_validation_result": item["baseline_validation_result"],
                "baseline_summary": item["baseline_summary"],
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



def _identity_tuple(identity: dict[str, Any]) -> tuple[int, str, str]:
    required = {"generator_seed", "corpus_id", "corpus_sha256"}
    if set(identity) != required:
        raise ValueError(f"authority identity fields drifted: {sorted(identity)}")
    seed = int(identity["generator_seed"])
    corpus_id = identity["corpus_id"]
    digest = identity["corpus_sha256"]
    if not isinstance(corpus_id, str) or not corpus_id:
        raise ValueError("authority identity corpus_id must be non-empty string")
    if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise ValueError("authority identity corpus_sha256 must be exact lowercase SHA-256")
    return seed, corpus_id, digest


def validate_authority_lock(
    lock: dict[str, Any],
    binding: dict[str, Any],
    policy: dict[str, Any],
    policy_path: Path,
) -> dict[str, Any]:
    if lock.get("schema_version") != 1:
        raise ValueError("authority lock schema_version must be 1")
    if lock.get("authority") != "baseline-only-source-candidate-authority-qualification":
        raise ValueError("unexpected authority lock authority")
    if lock.get("policy_id") != policy["policy_id"]:
        raise ValueError("authority lock policy_id drifted")
    if lock.get("policy_sha256") != sha256_file(policy_path):
        raise ValueError("authority lock policy bytes drifted")
    if lock.get("candidate_id") != binding["candidate_id"]:
        raise ValueError("authority lock candidate identity drifted")
    if lock.get("candidate_contract_sha256") != binding["contract_sha256"]:
        raise ValueError("authority lock candidate contract bytes drifted")
    if lock.get("source_base_sha") != binding["source_base_sha"]:
        raise ValueError("authority lock source-base drifted")
    if lock.get("qualification_profile") != binding["qualification_profile"]:
        raise ValueError("authority lock qualification profile drifted")
    if lock.get("baseline_executable_target") != binding["baseline_executable_target"]:
        raise ValueError("authority lock baseline target drifted")
    executable_sha = lock.get("baseline_executable_sha256")
    if not isinstance(executable_sha, str) or not re.fullmatch(r"[0-9a-f]{64}", executable_sha):
        raise ValueError("authority lock baseline executable SHA-256 invalid")
    if lock.get("baseline_args") != binding["baseline_args"]:
        raise ValueError("authority lock baseline args drifted")
    if lock.get("generator_contract") != binding["generator"]:
        raise ValueError("authority lock generator contract drifted")
    if lock.get("qualification_limit") != 1:
        raise ValueError("authority lock qualification limit drifted")
    if lock.get("expected_authority_lock_path") != binding["authority_lock_path"]:
        raise ValueError("authority lock expected path drifted")
    if lock.get("qualification_replay_additional_authority") is not False:
        raise ValueError("authority lock replay cannot add authority")
    if lock.get("decision") != "BASELINE_QUALIFIED_AUTHORITY_LOCK":
        raise ValueError("candidate execution requires qualified authority lock")
    if int(lock.get("required_count", 0)) != binding["required_count"]:
        raise ValueError("authority lock required_count drifted")

    pool = lock.get("pool_order")
    selected = lock.get("selected_authority")
    invalid = lock.get("invalid_pool_entries")
    if not isinstance(pool, list) or not isinstance(selected, list) or not isinstance(invalid, list):
        raise ValueError("authority lock pool/selection evidence must be arrays")
    pool_ids = [_identity_tuple(item) for item in pool]
    if [item[0] for item in pool_ids] != binding["pool_seeds"]:
        raise ValueError("authority lock pool seed order drifted")
    if len(pool_ids) != len(set(pool_ids)):
        raise ValueError("authority lock pool identities must be unique")

    selected_ids = [_identity_tuple(item) for item in selected]
    if len(selected_ids) != binding["required_count"]:
        raise ValueError("authority lock selected count drifted")
    if len(selected_ids) != len(set(selected_ids)):
        raise ValueError("authority lock selected identities must be unique")
    pool_position = {identity: index for index, identity in enumerate(pool_ids)}
    try:
        selected_positions = [pool_position[item] for item in selected_ids]
    except KeyError as exc:
        raise ValueError("selected authority identity missing from pool") from exc
    if selected_positions != sorted(selected_positions):
        raise ValueError("selected authority order must preserve preregistered pool order")

    invalid_ids = []
    for item in invalid:
        if not isinstance(item, dict) or item.get("status") != "AUTHORITY_POOL_ENTRY_INVALID":
            raise ValueError("invalid pool entry status drifted")
        identity = item.get("identity")
        if not isinstance(identity, dict):
            raise ValueError("invalid pool entry identity missing")
        invalid_ids.append(_identity_tuple(identity))
    if set(selected_ids) & set(invalid_ids):
        raise ValueError("selected authority cannot contain baseline-invalid pool entry")

    required_false = (
        "candidate_budget_consumed",
        "candidate_feedback_used",
        "retroactive_candidate_reclassification",
        "shipping_authority",
        "source_merge_authorized",
        "automatic_main_mutation",
    )
    for key in required_false:
        if lock.get(key) is not False:
            raise ValueError(f"authority lock boundary must remain false: {key}")
    if lock.get("candidate_execution_allowed") is not True:
        raise ValueError("qualified authority lock must explicitly allow candidate execution")

    return {
        "result": "PASS",
        "candidate_id": binding["candidate_id"],
        "qualification_profile": binding["qualification_profile"],
        "selected_seeds": [item[0] for item in selected_ids],
        "authority_lock_path": binding["authority_lock_path"],
    }



def _future_contract(
    policy: dict[str, Any],
    profile: str,
    target: str,
    baseline_args: dict[str, float],
) -> dict[str, Any]:
    return {
        "schema_version": 2,
        "candidate_id": f"future-{profile}-candidate-v2",
        "authority": "SOURCE_CANDIDATE_EVALUATION_ONLY",
        "candidate_budget": 1,
        "confirmation_limit": 0,
        "source_base_sha": "1" * 40,
        "execution_workflow": (
            ".github/workflows/research-source-candidate-v2-"
            f"future-{profile}-candidate-v2.yml"
        ),
        "fresh_candidate_evaluation": {"candidate_value_search": False},
        "baseline_authority_qualification_v2": {
            "policy_id": policy["policy_id"],
            "qualification_profile": profile,
            "baseline_executable_target": target,
            "baseline_args": baseline_args,
            "required_count": 2,
            "pool_seeds": [101, 102, 103],
            "generator": {
                "path": "validation/tools/build_stage_validation_corpus.py",
                "seconds": 4,
                "extra_args": [],
            },
            "qualification_limit": 1,
            "authority_lock_path": (
                ".github/research/continuous-optimization/source-authority-locks/"
                f"future-{profile}-candidate-v2.json"
            ),
            "selection_rule": policy["baseline_qualification"]["selection_rule"],
            "candidate_execution_before_lock": False,
        },
    }


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
            "baseline_summary": {"pass_rate": 1.0 if valid else 0.5},
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

    import tempfile
    with tempfile.TemporaryDirectory(prefix="ap-source-authority-v2-") as tmp:
        root = Path(tmp)

        vad = _future_contract(policy, "vad-stage", "ap_process_pcm", {})
        vad_path = root / "vad.json"
        vad_path.write_text(json.dumps(vad) + "\n", encoding="utf-8")
        vad_binding = validate_candidate_contract(vad, policy, vad_path)
        assert vad_binding["qualification_profile"] == "vad-stage"
        assert vad_binding["baseline_args"] == {}

        agc = _future_contract(
            policy,
            "agc-dynamics",
            "agc_dynamics_probe",
            {"agc_target_dbfs": -20.0, "limiter_dbfs": -2.0},
        )
        agc_path = root / "agc.json"
        agc_path.write_text(json.dumps(agc) + "\n", encoding="utf-8")
        agc_binding = validate_candidate_contract(agc, policy, agc_path)
        assert agc_binding["qualification_profile"] == "agc-dynamics"
        assert agc_binding["baseline_args"]["agc_target_dbfs"] == -20.0

        pool_ids = [
            {
                "generator_seed": seed,
                "corpus_id": f"pool-{seed}",
                "corpus_sha256": digest * 64,
            }
            for seed, digest in ((101, "1"), (102, "2"), (103, "3"))
        ]
        lock = {
            "schema_version": 1,
            "authority": "baseline-only-source-candidate-authority-qualification",
            "policy_id": policy["policy_id"],
            "policy_sha256": sha256_file(DEFAULT_POLICY),
            "candidate_id": vad_binding["candidate_id"],
            "candidate_contract_sha256": vad_binding["contract_sha256"],
            "source_base_sha": vad_binding["source_base_sha"],
            "qualification_profile": vad_binding["qualification_profile"],
            "baseline_executable_target": vad_binding["baseline_executable_target"],
            "baseline_executable_sha256": "a" * 64,
            "baseline_args": vad_binding["baseline_args"],
            "generator_contract": vad_binding["generator"],
            "qualification_limit": 1,
            "expected_authority_lock_path": vad_binding["authority_lock_path"],
            "qualification_replay_additional_authority": False,
            "decision": "BASELINE_QUALIFIED_AUTHORITY_LOCK",
            "required_count": vad_binding["required_count"],
            "pool_order": pool_ids,
            "selected_authority": pool_ids[:2],
            "invalid_pool_entries": [{
                "identity": pool_ids[2],
                "status": "AUTHORITY_POOL_ENTRY_INVALID",
                "baseline_validation_result": "FAIL",
                "baseline_summary": {"pass_rate": 0.5},
                "absolute_case_gate_violations": [{"case_id": "x"}],
            }],
            "candidate_execution_allowed": True,
            "candidate_budget_consumed": False,
            "candidate_feedback_used": False,
            "retroactive_candidate_reclassification": False,
            "shipping_authority": False,
            "source_merge_authorized": False,
            "automatic_main_mutation": False,
        }
        lock_result = validate_authority_lock(
            lock, vad_binding, policy, DEFAULT_POLICY
        )
        assert lock_result["selected_seeds"] == [101, 102]

        bad_lock = json.loads(json.dumps(lock))
        bad_lock["candidate_contract_sha256"] = "0" * 64
        try:
            validate_authority_lock(bad_lock, vad_binding, policy, DEFAULT_POLICY)
        except ValueError as exc:
            assert "contract bytes drifted" in str(exc)
        else:
            raise AssertionError("authority lock contract drift was accepted")

        bad_target = json.loads(json.dumps(vad))
        bad_target["baseline_authority_qualification_v2"][
            "baseline_executable_target"
        ] = "agc_dynamics_probe"
        bad_path = root / "bad-target.json"
        bad_path.write_text(json.dumps(bad_target) + "\n", encoding="utf-8")
        try:
            validate_candidate_contract(bad_target, policy, bad_path)
        except ValueError as exc:
            assert "target drift" in str(exc)
        else:
            raise AssertionError("profile/target mismatch was accepted")

        terminal = json.loads(json.dumps(vad))
        terminal["candidate_id"] = "vad-strong-origin-bounded-hysteresis-v1"
        terminal_path = root / "terminal.json"
        terminal_path.write_text(json.dumps(terminal) + "\n", encoding="utf-8")
        try:
            validate_candidate_contract(terminal, policy, terminal_path)
        except ValueError as exc:
            assert "terminal candidate" in str(exc)
        else:
            raise AssertionError("terminal candidate was allowed into authority-v2")

    print("source-candidate baseline-qualified authority v2 self-test: OK")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--validate-policy", action="store_true")
    parser.add_argument("--describe-contract", action="store_true")
    parser.add_argument("--validate-lock", action="store_true")
    parser.add_argument("--baseline-executable", type=Path)
    parser.add_argument("--pool-corpus", action="append", type=Path, default=[])
    parser.add_argument("--candidate-contract", type=Path)
    parser.add_argument("--authority-lock", type=Path)
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
            "qualification_profiles": sorted(policy["qualification_profiles"]),
        }, sort_keys=True))
        return 0
    if args.describe_contract:
        if args.candidate_contract is None:
            parser.error("--candidate-contract is required with --describe-contract")
        contract = load_json(args.candidate_contract)
        binding = validate_candidate_contract(
            contract, policy, args.candidate_contract.resolve()
        )
        print(json.dumps(binding, sort_keys=True))
        return 0
    if args.validate_lock:
        if args.candidate_contract is None or args.authority_lock is None:
            parser.error("--candidate-contract and --authority-lock are required with --validate-lock")
        contract = load_json(args.candidate_contract)
        binding = validate_candidate_contract(
            contract, policy, args.candidate_contract.resolve()
        )
        lock = load_json(args.authority_lock)
        try:
            actual_lock_path = args.authority_lock.resolve().relative_to(ROOT.resolve()).as_posix()
        except ValueError as exc:
            raise ValueError("authority lock must reside inside repository") from exc
        if actual_lock_path != binding["authority_lock_path"]:
            raise ValueError(
                f"authority lock path drift: {actual_lock_path} != {binding['authority_lock_path']}"
            )
        result = validate_authority_lock(lock, binding, policy, args.policy.resolve())
        result["authority_lock_sha256"] = sha256_file(args.authority_lock)
        print(json.dumps(result, sort_keys=True))
        return 0
    if args.baseline_executable is None or args.candidate_contract is None or args.output is None:
        parser.error(
            "baseline executable, candidate contract and output are required for qualification"
        )
    result = run(
        args.baseline_executable.resolve(),
        [path.resolve() for path in args.pool_corpus],
        args.candidate_contract.resolve(),
        args.policy.resolve(),
        args.output.resolve(),
    )
    print(json.dumps({
        "candidate_id": result["candidate_id"],
        "qualification_profile": result["qualification_profile"],
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
