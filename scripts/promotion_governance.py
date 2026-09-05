#!/usr/bin/env python3
"""Validate promotion/data/budget governance without creating acoustic authority."""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = Path("docs/program/promotion-policy.json")
PLAN_PATH = Path("docs/program/plan.json")
TUNING_WORKFLOW = Path(".github/workflows/aec-motion-tuning.yml")
TUNING_REPLAY = Path("validation/tools/tuning_replay.py")

ALLOWED_P001_PATHS = {
    "docs/program/promotion-policy.json",
    "docs/program/iterations/P001.json",
    "docs/program/iterations/P001-result.json",
    "docs/program/plan.json",
    "docs/program/PROCESS.md",
    "scripts/program.py",
    "scripts/promotion_governance.py",
    ".github/workflows/program-iteration.yml",
    ".github/workflows/aec-motion-tuning.yml",
    "validation/tools/tuning_replay.py",
}
FORBIDDEN_PREFIXES = (
    "src/",
    "include/",
    "validation/policies/",
    "validation/datasets.lock.json",
    "validation/hosted_real.datasets.lock.json",
    "validation/hosted_aec.datasets.lock.json",
    "ci/resource-baseline.json",
    "certification/",
)
FORBIDDEN_EXACT = {"CMakeLists.txt", "CHANGELOG.md"}


def require(ok: bool, message: str) -> None:
    if not ok:
        raise ValueError(message)


def exact_sha(value: object) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{40}", value) is not None


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    require(isinstance(value, dict), f"JSON object required: {path}")
    return value


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")


def validate_policy(policy: dict) -> None:
    required = {
        "schema_version", "phase", "baseline", "principles", "source_groups",
        "candidate_gate_plan", "confirmation_policy", "research_budgets",
    }
    require(set(policy) == required, "promotion policy keys")
    require(policy["schema_version"] == 1 and policy["phase"] == "software-public-data", "policy identity")

    baseline = policy["baseline"]
    require(set(baseline) == {"source_sha", "verify_run_id", "release", "release_id"}, "baseline keys")
    require(exact_sha(baseline["source_sha"]), "baseline exact SHA")
    require(type(baseline["verify_run_id"]) is int and baseline["verify_run_id"] > 0, "verify run id")
    require(re.fullmatch(r"v\d+\.\d+\.\d+", baseline["release"]) is not None, "release SemVer")
    require(type(baseline["release_id"]) is int and baseline["release_id"] > 0, "release id")

    principles = policy["principles"]
    expected_principles = {
        "auto_promote": False,
        "product_qualification": "DEFERRED_BY_SCOPE",
        "measurement_change_can_trigger_acoustic_search": False,
        "repeated_execution_is_new_independent_evidence": False,
        "failed_attempts_must_be_retained": True,
        "budget_is_inherited_by_root_cause": True,
    }
    require(principles == expected_principles, "phase principles")

    groups = policy["source_groups"]
    require(isinstance(groups, list) and groups, "source groups")
    ids: set[str] = set()
    identities: set[str] = set()
    valid_roles = {"development", "validation", "shadow", "regression", "hosted-regression", "confirmation", "promotion"}
    for group in groups:
        require(set(group) == {
            "id", "identity", "kind", "current_role", "observed_before_future_selection",
            "allowed_roles", "prohibited_roles",
        }, "source group keys")
        require(isinstance(group["id"], str) and group["id"] and group["id"] not in ids, "source group id")
        require(isinstance(group["identity"], str) and group["identity"] and group["identity"] not in identities,
                "source group identity")
        ids.add(group["id"])
        identities.add(group["identity"])
        require(group["current_role"] in valid_roles, "source group current role")
        require(type(group["observed_before_future_selection"]) is bool, "source exposure boolean")
        allowed = group["allowed_roles"]
        prohibited = group["prohibited_roles"]
        require(isinstance(allowed, list) and allowed and len(allowed) == len(set(allowed)), "allowed roles")
        require(isinstance(prohibited, list) and len(prohibited) == len(set(prohibited)), "prohibited roles")
        require(set(allowed) <= valid_roles and set(prohibited) <= valid_roles, "unknown source role")
        require(not (set(allowed) & set(prohibited)), "source role both allowed and prohibited")
        if group["observed_before_future_selection"]:
            require("confirmation" not in allowed and "promotion" not in allowed,
                    "observed source cannot regain independent authority")
            require({"confirmation", "promotion"} <= set(prohibited),
                    "observed source must explicitly prohibit independent authority")

    gate_plan = policy["candidate_gate_plan"]
    require(set(gate_plan) == {
        "ordered_gates", "required_before_candidate_freeze", "required_before_merge",
        "required_after_merge_for_release_bearing_change", "gate_success", "skipped_is_success",
        "old_sha_is_success", "missing_gate_is_success",
    }, "gate plan keys")
    ordered = gate_plan["ordered_gates"]
    require(isinstance(ordered, list) and len(ordered) == len(set(ordered)) and len(ordered) >= 8,
            "ordered gate plan")
    for key in ("required_before_candidate_freeze", "required_before_merge",
                "required_after_merge_for_release_bearing_change"):
        value = gate_plan[key]
        require(isinstance(value, list) and len(value) == len(set(value)) and set(value) <= set(ordered), key)
    require(gate_plan["required_before_candidate_freeze"] == ordered[:3], "candidate freeze ordering")
    require(gate_plan["skipped_is_success"] is False and gate_plan["old_sha_is_success"] is False and
            gate_plan["missing_gate_is_success"] is False, "fail-closed gate semantics")

    confirmation = policy["confirmation_policy"]
    required_confirmation = {
        "selection_must_be_frozen_before_source_group_consumption": True,
        "source_group_must_not_have_been_observed_before_selection": True,
        "confirmation_cannot_search_or_rank_candidates": True,
        "failed_confirmation_retires_source_group_to_regression": True,
        "passed_confirmation_retires_source_group_to_regression_after_use": True,
        "publicly_cataloged_source_may_be_confirmation_if_unconsumed_before_freeze": True,
    }
    require(confirmation == required_confirmation, "confirmation policy")

    budgets = policy["research_budgets"]
    require(isinstance(budgets, list) and budgets, "research budgets")
    roots: set[str] = set()
    for budget in budgets:
        require(set(budget) == {
            "root_cause_id", "search_rounds", "candidate_variants", "confirmation_sets", "inherited_evidence"
        }, "budget keys")
        root = budget["root_cause_id"]
        require(isinstance(root, str) and root and root not in roots, "budget root cause")
        roots.add(root)
        for key in ("search_rounds", "candidate_variants", "confirmation_sets"):
            item = budget[key]
            require(set(item) == {"limit", "consumed"}, "budget counter keys")
            require(type(item["limit"]) is int and type(item["consumed"]) is int and
                    0 <= item["consumed"] <= item["limit"], "budget counter bounds")
        require(isinstance(budget["inherited_evidence"], list) and budget["inherited_evidence"],
                "budget inherited evidence")


def validate_gate_evidence(policy: dict, record: dict, stage: str = "before_merge") -> None:
    require(set(record) == {"expected_sha", "declared_attempt_count", "attempts"}, "gate evidence keys")
    require(exact_sha(record["expected_sha"]), "gate expected SHA")
    attempts = record["attempts"]
    require(isinstance(attempts, list) and attempts, "gate attempts")
    require(type(record["declared_attempt_count"]) is int and record["declared_attempt_count"] == len(attempts),
            "concealed or missing attempt history")
    attempt_ids = [item["attempt_id"] for item in attempts]
    require(len(attempt_ids) == len(set(attempt_ids)), "duplicate attempt id")
    required_map = {
        "before_freeze": policy["candidate_gate_plan"]["required_before_candidate_freeze"],
        "before_merge": policy["candidate_gate_plan"]["required_before_merge"],
        "after_merge_release": policy["candidate_gate_plan"]["required_after_merge_for_release_bearing_change"],
    }
    require(stage in required_map, "gate evidence stage")
    required_gates = required_map[stage]
    latest = attempts[-1]
    require(set(latest) == {"attempt_id", "result", "gates"}, "attempt keys")
    require(latest["result"] in {"PASS", "FAIL", "BLOCKED"}, "attempt result")
    gates = latest["gates"]
    require(isinstance(gates, dict), "gate map")
    for gate in required_gates:
        require(gate in gates, f"missing required gate: {gate}")
        value = gates[gate]
        require(set(value) == {"sha", "status", "conclusion"}, "gate result keys")
        require(value["sha"] == record["expected_sha"], f"old/wrong SHA gate: {gate}")
        require(value["status"] == "completed" and value["conclusion"] == "success",
                f"gate not successful: {gate}")
    require(latest["result"] == "PASS", "latest attempt must explicitly PASS")


def validate_budget_transition(previous: dict, current: dict) -> None:
    require(previous["root_cause_id"] == current["root_cause_id"], "budget root cause changed")
    for key in ("search_rounds", "candidate_variants", "confirmation_sets"):
        before, after = previous[key], current[key]
        require(after["limit"] >= before["limit"], f"budget limit silently reduced: {key}")
        require(after["consumed"] >= before["consumed"], f"budget consumption reset: {key}")
        require(after["consumed"] <= after["limit"], f"budget exceeded: {key}")


def pull_request_paths(workflow_text: str) -> list[str]:
    lines = workflow_text.splitlines()
    try:
        pull = next(i for i, line in enumerate(lines) if line.strip() == "pull_request:")
        paths = next(i for i in range(pull + 1, len(lines)) if lines[i].strip() == "paths:")
    except StopIteration as exc:
        raise ValueError("AEC tuning pull_request paths missing") from exc
    out: list[str] = []
    base_indent = len(lines[paths]) - len(lines[paths].lstrip())
    for line in lines[paths + 1:]:
        indent = len(line) - len(line.lstrip())
        stripped = line.strip()
        if stripped and indent <= base_indent:
            break
        if stripped.startswith("- "):
            out.append(stripped[2:].strip().strip("'\""))
    return out


def validate_tuning_workflow(workflow_text: str, replay_text: str) -> None:
    paths = pull_request_paths(workflow_text)
    require("validation/tools/build_aec_motion_corpus.py" not in paths and
            "validation/tools/build_aec_motion_bundle.py" not in paths,
            "measurement generator changes must not auto-trigger acoustic search")
    require("validation/tools/aec_motion_tuning.py" in paths and
            ".github/workflows/aec-motion-tuning.yml" in paths,
            "actual tuning changes must still trigger tuning verification")
    lower = workflow_text.lower()
    for forbidden in ("unseen motion", "fresh call", "independent multi-seed"):
        require(forbidden not in lower, f"repeated fixed data mislabeled as independent: {forbidden}")
    require("regression/replay" in lower, "fixed tuning partitions must declare regression/replay authority")
    require("non-shipping-regression-replay" in replay_text,
            "tuning replay authority must not claim independence for repeated fixed corpora")
    require("non-shipping-independent-replay" not in replay_text,
            "legacy independent replay authority remains")


def changed_paths(base_sha: str) -> list[str]:
    raw = subprocess.check_output(["git", "diff", "--name-only", f"{base_sha}..HEAD"], cwd=ROOT, text=True)
    return [line for line in raw.splitlines() if line]


def validate_scope(paths: list[str]) -> None:
    require(paths, "P001 must change governance")
    unknown = sorted(set(paths) - ALLOWED_P001_PATHS)
    require(not unknown, "unexpected P001 path(s): " + ", ".join(unknown))
    for path in paths:
        require(path not in FORBIDDEN_EXACT and not any(path == prefix or path.startswith(prefix) for prefix in FORBIDDEN_PREFIXES),
                f"shipping/acoustic authority changed in P001: {path}")


def validate_contract(contract: dict) -> None:
    required = {
        "schema_version", "iteration_id", "root_cause_id", "phase", "base_sha", "policy",
        "candidate_limit", "confirmation_limit", "promotion_allowed", "run_timeout_seconds",
        "acceptance", "next_on_success", "next_on_failure",
    }
    require(set(contract) == required, "P001 contract keys")
    require(contract["schema_version"] == 1 and contract["iteration_id"] == "P001" and
            contract["root_cause_id"] == "promotion-governance" and contract["phase"] == "governance-qualification",
            "P001 contract identity")
    require(exact_sha(contract["base_sha"]), "P001 base SHA")
    require(contract["policy"] == str(POLICY_PATH), "P001 policy path")
    require(contract["candidate_limit"] == 0 and contract["confirmation_limit"] == 0 and
            contract["promotion_allowed"] is False, "P001 cannot acquire acoustic authority")
    require(type(contract["run_timeout_seconds"]) is int and 1 <= contract["run_timeout_seconds"] <= 120,
            "P001 timeout")
    require(isinstance(contract["acceptance"], list) and len(contract["acceptance"]) >= 10, "P001 acceptance")


def self_test() -> None:
    policy = load_json(ROOT / POLICY_PATH)
    validate_policy(policy)

    sha = policy["baseline"]["source_sha"]
    gates = {
        name: {"sha": sha, "status": "completed", "conclusion": "success"}
        for name in policy["candidate_gate_plan"]["required_before_merge"]
    }
    record = {
        "expected_sha": sha,
        "declared_attempt_count": 2,
        "attempts": [
            {"attempt_id": "attempt-1", "result": "FAIL", "gates": {"base-identity": gates["base-identity"]}},
            {"attempt_id": "attempt-2", "result": "PASS", "gates": gates},
        ],
    }
    validate_gate_evidence(policy, record)

    mutations = []
    def leaked_source(p: dict) -> None:
        p["source_groups"][0]["allowed_roles"].append("confirmation")
        p["source_groups"][0]["prohibited_roles"].remove("confirmation")
    mutations.append(leaked_source)
    mutations.append(lambda p: p["candidate_gate_plan"].update(missing_gate_is_success=True))
    mutations.append(lambda p: p["principles"].update(auto_promote=True))
    for mutate in mutations:
        bad = copy.deepcopy(policy)
        mutate(bad)
        try:
            validate_policy(bad)
        except ValueError:
            pass
        else:
            raise AssertionError("bad promotion policy accepted")

    bad_cases = []
    missing = copy.deepcopy(record)
    del missing["attempts"][-1]["gates"][policy["candidate_gate_plan"]["required_before_merge"][-1]]
    bad_cases.append(missing)
    old_sha = copy.deepcopy(record)
    old_sha["attempts"][-1]["gates"]["base-identity"]["sha"] = "0" * 40
    bad_cases.append(old_sha)
    skipped = copy.deepcopy(record)
    skipped["attempts"][-1]["gates"]["shadow-protection"].update(status="completed", conclusion="skipped")
    bad_cases.append(skipped)
    concealed = copy.deepcopy(record)
    concealed["attempts"] = concealed["attempts"][1:]
    bad_cases.append(concealed)
    for bad in bad_cases:
        try:
            validate_gate_evidence(policy, bad)
        except ValueError:
            pass
        else:
            raise AssertionError("bad gate evidence accepted")

    previous = copy.deepcopy(policy["research_budgets"][0])
    current = copy.deepcopy(previous)
    current["search_rounds"]["consumed"] += 1
    validate_budget_transition(previous, current)
    reset = copy.deepcopy(current)
    reset["candidate_variants"]["consumed"] = 0
    try:
        validate_budget_transition(previous, reset)
    except ValueError:
        pass
    else:
        raise AssertionError("budget reset accepted")

    good_workflow = """on:\n  pull_request:\n    paths:\n      - 'validation/tools/aec_motion_tuning.py'\n      - '.github/workflows/aec-motion-tuning.yml'\n  schedule:\n    - cron: '0 0 * * *'\n# regression/replay\n"""
    validate_tuning_workflow(good_workflow, "authority = 'non-shipping-regression-replay'")
    bad_workflow = good_workflow.replace("      - 'validation/tools/aec_motion_tuning.py'\n",
                                         "      - 'validation/tools/build_aec_motion_corpus.py'\n      - 'validation/tools/aec_motion_tuning.py'\n")
    try:
        validate_tuning_workflow(bad_workflow, "authority = 'non-shipping-regression-replay'")
    except ValueError:
        pass
    else:
        raise AssertionError("measurement-only tuning trigger accepted")
    print("P001 promotion governance self-test: source/gate/history/budget/trigger negative contracts OK")


def run(contract_path: Path, output: Path) -> int:
    contract = load_json(contract_path)
    validate_contract(contract)
    policy = load_json(ROOT / contract["policy"])
    validate_policy(policy)
    require(policy["baseline"]["source_sha"] == contract["base_sha"], "policy/contract baseline mismatch")
    require(not output.exists() or (output.is_dir() and not any(output.iterdir())), "output must be empty")
    output.mkdir(parents=True, exist_ok=True)

    resolved = subprocess.check_output(["git", "rev-parse", contract["base_sha"] + "^{commit}"], cwd=ROOT, text=True).strip()
    require(resolved == contract["base_sha"], "P001 base commit unavailable")
    head_sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    paths = changed_paths(contract["base_sha"])
    validate_scope(paths)

    plan = load_json(ROOT / PLAN_PATH)
    require(plan["baseline"]["source_sha"] == contract["base_sha"] and
            plan["baseline"]["software_release"] == policy["baseline"]["release"],
            "program baseline not advanced to P001 authority")
    by_id = {task["id"]: task for task in plan["tasks"]}
    require(by_id["I002"]["status"] == "CLOSED", "I002 must be closed before P001")
    require(by_id["P001"]["status"] in {"READY", "ACTIVE", "REVIEW_REQUIRED"} and
            by_id["P001"]["handler"] == "promotion-governance", "P001 program registration")
    require(by_id["I003"]["status"] == "PLANNED", "I003 must not auto-activate during P001")

    workflow_text = (ROOT / TUNING_WORKFLOW).read_text(encoding="utf-8")
    replay_text = (ROOT / TUNING_REPLAY).read_text(encoding="utf-8")
    validate_tuning_workflow(workflow_text, replay_text)

    result = {
        "schema_version": 1,
        "iteration_id": "P001",
        "execution_result": "COMPLETE",
        "decision": "GOVERNANCE_READY_NO_ACOUSTIC_CANDIDATE",
        "authority": "governance-only",
        "base_sha": contract["base_sha"],
        "head_sha": head_sha,
        "product_qualification": "DEFERRED_BY_SCOPE",
        "candidate_limit": 0,
        "confirmation_limit": 0,
        "changed_paths": paths,
        "bindings": {
            "contract_sha256": digest(contract_path),
            "policy_sha256": digest(ROOT / contract["policy"]),
            "plan_sha256": digest(ROOT / PLAN_PATH),
            "program_sha256": digest(ROOT / "scripts/program.py"),
            "tuning_workflow_sha256": digest(ROOT / TUNING_WORKFLOW),
            "tuning_replay_sha256": digest(ROOT / TUNING_REPLAY),
        },
        "checks": {
            "known_observed_sources_locked_to_regression": True,
            "gate_plan_fail_closed": True,
            "attempt_history_retained": True,
            "budget_inheritance_enforced": True,
            "measurement_pr_tuning_trigger_disabled": True,
            "repeated_fixed_data_labeled_regression_replay": True,
            "i003_still_planned": True,
        },
    }
    write_json(output / "governance-result.json", result)
    print(json.dumps({"iteration_id": "P001", "result": "COMPLETE",
                      "decision": result["decision"], "head_sha": head_sha}, sort_keys=True))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--contract", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    if args.contract is None or args.output is None:
        parser.error("--contract and --output are required")
    try:
        return run(args.contract.resolve(), args.output.resolve())
    except (ValueError, OSError, subprocess.SubprocessError, KeyError, TypeError) as exc:
        print(f"P001 governance: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
