#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASE_SHA = "1e4d13598f7cc497c8ebd7415bf4343acb587a89"


def require(ok: bool, message: str) -> None:
    if not ok:
        raise AssertionError(message)


def audit_release_identity() -> dict:
    text = (ROOT / ".github/workflows/release.yml").read_text()
    require("- name: Check existing release" in text, "existing release branch missing")
    skip_count = text.count("if: steps.existing.outputs.release != 'true'")
    require(skip_count >= 8, f"expected release-producing steps to be skipped, got {skip_count}")
    has_existing_identity_gate = (
        "existing release identity" in text.lower()
        or "steps.existing.outputs.release == 'true'" in text
    )
    return {
        "scope": "existing-release-identity",
        "existing_release_short_circuit_present": True,
        "release_producing_steps_skipped_when_existing": skip_count,
        "existing_release_identity_gate_present": has_existing_identity_gate,
        "counterexample": {
            "existing_tag": "vX.Y.Z",
            "intended_source_sha": "a" * 40,
            "existing_tag_peel_sha": "b" * 40,
            "existing_assets": ["wrong-asset.bin"],
            "current_control_flow": "existing=true -> release-producing/identity-building steps skipped",
        },
        "protected": has_existing_identity_gate,
    }


def load_registry_module():
    path = ROOT / "scripts/research_registry.py"
    spec = importlib.util.spec_from_file_location("research_registry", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def audit_gc_active_dependency() -> dict:
    rr = load_registry_module()
    sha = "c" * 40
    data = {
        "schema_version": 1,
        "records": [{
            "branch": "research/p002-active-dependency-fixture",
            "head_sha": sha,
            "status": "REJECTED",
            "evidence": ["sealed:fixture"],
            "gc_eligible": True,
            "auto_gc": True,
        }],
    }
    rr.validate_registry(data)
    original_branch_sha, original_open_prs = rr.branch_sha, rr.open_prs
    try:
        rr.branch_sha = lambda repository, branch: sha
        rr.open_prs = lambda repository, branch: []
        dry = rr.plan(data, "owner/repo", apply=False)
        require(dry["actions"][0]["action"] == "DELETE_DRY_RUN", dry)

        rr.branch_sha = lambda repository, branch: "d" * 40
        drift = rr.plan(data, "owner/repo", apply=False)
        require(drift["actions"][0]["action"] == "BLOCK_SHA_DRIFT", drift)

        rr.branch_sha = lambda repository, branch: sha
        rr.open_prs = lambda repository, branch: [{"number": 77}]
        open_pr = rr.plan(data, "owner/repo", apply=False)
        require(open_pr["actions"][0]["action"] == "BLOCK_OPEN_PR", open_pr)
    finally:
        rr.branch_sha, rr.open_prs = original_branch_sha, original_open_prs

    # The current API has no active-dependency input/check. Model a dependency
    # outside the function and prove the branch remains DELETE_DRY_RUN.
    active_dependency = {
        "type": "program-evidence",
        "head_sha": sha,
        "still_required": True,
    }
    return {
        "scope": "gc-active-dependency",
        "sha_drift_protection": "BLOCK_SHA_DRIFT",
        "open_pr_protection": "BLOCK_OPEN_PR",
        "active_dependency_fixture": active_dependency,
        "action_with_exact_sha_no_open_pr": dry["actions"][0]["action"],
        "active_dependency_gate_present": False,
        "protected": False,
    }


def audit_terminal_triggers() -> dict:
    details = []
    all_protected = True
    for name in ("i007-closure.yml", "i009-closure.yml"):
        text = (ROOT / ".github/workflows" / name).read_text()
        shared_paths = [p for p in ("docs/program/plan.json", "scripts/program.py") if p in text]
        hardcoded_base = "PROGRAM_BASE:" in text
        exact_delta = 'git diff --name-only "$PROGRAM_BASE"...HEAD' in text
        mis_triggerable = bool(shared_paths and hardcoded_base and exact_delta)
        all_protected &= not mis_triggerable
        details.append({
            "workflow": name,
            "shared_program_trigger_paths": shared_paths,
            "hardcoded_program_base": hardcoded_base,
            "historical_exact_delta": exact_delta,
            "later_program_pr_can_retrigger_terminal_gate": mis_triggerable,
        })
    return {
        "scope": "terminal-closure-trigger-scope",
        "workflows": details,
        "protected": all_protected,
    }


def main() -> int:
    contract = json.loads((ROOT / "docs/program/iterations/P002-candidate-zero-audit.json").read_text())
    require(contract["base_sha"] == BASE_SHA, "P002 exact base drift")
    require(contract["candidate_limit"] == 0 and contract["confirmation_limit"] == 0, "candidate authority")
    require(contract["destructive_gc_allowed"] is False and contract["release_allowed"] is False, "destructive authority")

    findings = [audit_release_identity(), audit_gc_active_dependency(), audit_terminal_triggers()]
    gaps = [item["scope"] for item in findings if not item["protected"]]
    decision = "GOVERNANCE_GAPS_REVIEW_REQUIRED" if gaps else "GOVERNANCE_BASELINE_ADEQUATE"
    result = {
        "schema_version": 1,
        "iteration_id": "P002",
        "base_sha": BASE_SHA,
        "decision": decision,
        "gaps": gaps,
        "findings": findings,
        "candidate_limit_consumed": 0,
        "confirmation_limit_consumed": 0,
        "destructive_actions_executed": 0,
        "authority_boundary": contract["authority_boundary"],
    }
    out = Path("/tmp/p002-candidate-zero")
    out.mkdir(parents=True, exist_ok=True)
    (out / "result.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    import hashlib
    digest = hashlib.sha256((out / "result.json").read_bytes()).hexdigest()
    (out / "SHA256SUMS").write_text(f"{digest}  result.json\n")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
