#!/usr/bin/env python3
"""Audit the GitHub controls that make the repository release path non-bypassable."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
from pathlib import Path


def _ref_included(ruleset: dict, ref: str, default_branch: bool = False) -> bool:
    ref_name = ruleset.get("conditions", {}).get("ref_name", {})
    includes = ref_name.get("include", []) or []
    excludes = ref_name.get("exclude", []) or []
    wanted = {ref}
    if default_branch:
        wanted.add("~DEFAULT_BRANCH")
    if not any(item in wanted for item in includes):
        return False
    if ref in excludes or (default_branch and "~DEFAULT_BRANCH" in excludes):
        return False
    return True


def _rule(ruleset: dict, kind: str) -> dict | None:
    for rule in ruleset.get("rules", []) or []:
        if rule.get("type") == kind:
            return rule
    return None


def audit(rulesets: list[dict], immutable: dict | None) -> dict:
    active = [r for r in rulesets if r.get("enforcement") == "active"]
    main_candidates = [
        r for r in active
        if r.get("target") == "branch" and _ref_included(r, "refs/heads/main", True)
    ]
    tag_candidates = [
        r for r in active
        if r.get("target") == "tag"
        and any(
            item in {"refs/tags/v*", "refs/tags/v**"}
            for item in r.get("conditions", {}).get("ref_name", {}).get("include", []) or []
        )
    ]

    findings: list[str] = []
    if not main_candidates:
        findings.append("no active branch ruleset targets main")
    if not tag_candidates:
        findings.append("no active tag ruleset targets refs/tags/v*")

    def main_ok(ruleset: dict) -> bool:
        required = {"pull_request", "required_status_checks", "deletion", "non_fast_forward"}
        present = {rule.get("type") for rule in ruleset.get("rules", []) or []}
        if not required.issubset(present):
            return False
        status = _rule(ruleset, "required_status_checks") or {}
        params = status.get("parameters", {})
        contexts = {
            item.get("context")
            for item in params.get("required_status_checks", []) or []
            if isinstance(item, dict)
        }
        if "summary" not in contexts or params.get("strict_required_status_checks_policy") is not True:
            return False
        if ruleset.get("bypass_actors"):
            return False
        return True

    def tag_ok(ruleset: dict) -> bool:
        present = {rule.get("type") for rule in ruleset.get("rules", []) or []}
        return {"deletion", "non_fast_forward"}.issubset(present) and not ruleset.get("bypass_actors")

    main_enforced = any(main_ok(r) for r in main_candidates)
    tags_enforced = any(tag_ok(r) for r in tag_candidates)
    if main_candidates and not main_enforced:
        findings.append(
            "main ruleset must require PRs, strict summary status, deletion protection, "
            "non-fast-forward protection and no bypass actors"
        )
    if tag_candidates and not tags_enforced:
        findings.append("v* tag ruleset must protect deletion/force-update and have no bypass actors")

    immutable_enabled = bool(immutable and immutable.get("enabled") is True)
    if not immutable_enabled:
        findings.append("immutable releases are not enabled")

    return {
        "schema_version": 1,
        "result": "PASS" if not findings else "FAIL",
        "main_ruleset_enforced": main_enforced,
        "version_tag_ruleset_enforced": tags_enforced,
        "immutable_releases_enabled": immutable_enabled,
        "findings": findings,
    }


def _gh_json(args: list[str]) -> object:
    command = ["gh", "api", *args]
    return json.loads(subprocess.check_output(command, text=True))


def fetch_live(repository: str) -> tuple[list[dict], dict | None]:
    summaries = _gh_json([f"repos/{repository}/rulesets"])
    if not isinstance(summaries, list):
        raise RuntimeError("GitHub rulesets response is not an array")
    details: list[dict] = []
    for item in summaries:
        if not isinstance(item, dict) or "id" not in item:
            continue
        detail = _gh_json([f"repos/{repository}/rulesets/{item['id']}"])
        if isinstance(detail, dict):
            details.append(detail)
    try:
        immutable = _gh_json([f"repos/{repository}/immutable-releases"])
    except subprocess.CalledProcessError:
        immutable = None
    return details, immutable if isinstance(immutable, dict) else None


def self_test() -> None:
    main = {
        "target": "branch",
        "enforcement": "active",
        "bypass_actors": [],
        "conditions": {"ref_name": {"include": ["~DEFAULT_BRANCH"], "exclude": []}},
        "rules": [
            {"type": "pull_request", "parameters": {"allowed_merge_methods": ["squash"]}},
            {
                "type": "required_status_checks",
                "parameters": {
                    "strict_required_status_checks_policy": True,
                    "required_status_checks": [{"context": "summary"}],
                },
            },
            {"type": "deletion"},
            {"type": "non_fast_forward"},
        ],
    }
    tags = {
        "target": "tag",
        "enforcement": "active",
        "bypass_actors": [],
        "conditions": {"ref_name": {"include": ["refs/tags/v*"], "exclude": []}},
        "rules": [{"type": "deletion"}, {"type": "non_fast_forward"}],
    }
    assert audit([main, tags], {"enabled": True})["result"] == "PASS"
    main["bypass_actors"] = [{"actor_type": "RepositoryRole", "actor_id": 5}]
    failed = audit([main, tags], {"enabled": False})
    assert failed["result"] == "FAIL"
    assert not failed["main_ruleset_enforced"]
    print("github governance self-test: OK")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--repository", default=os.environ.get("GITHUB_REPOSITORY"))
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    if not args.repository or not args.output:
        parser.error("--repository and --output are required")
    rulesets, immutable = fetch_live(args.repository)
    result = audit(rulesets, immutable)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, sort_keys=True))
    return 0 if result["result"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
