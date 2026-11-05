#!/usr/bin/env python3
"""Audit protected research-main GitHub controls, not publication authority."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
from pathlib import Path
from typing import Optional

API_VERSION = "2026-03-10"
GITHUB_ACTIONS_APP_ID = 15368


def _ref_included(ruleset: dict) -> bool:
    conditions = ruleset.get("conditions")
    if not isinstance(conditions, dict):
        return False
    ref_name = conditions.get("ref_name")
    if not isinstance(ref_name, dict):
        return False
    includes = ref_name.get("include")
    excludes = ref_name.get("exclude")
    return (
        isinstance(includes, list)
        and all(type(item) is str for item in includes)
        and any(item in ("refs/heads/main", "~DEFAULT_BRANCH") for item in includes)
        and type(excludes) is list
        and excludes == []
    )


def _rule(ruleset: dict, kind: str) -> dict:
    for item in ruleset.get("rules", []) or []:
        if isinstance(item, dict) and item.get("type") == kind:
            return item
    return {}


def _main_enforced(rule: dict) -> bool:
    if rule.get("target") != "branch" or rule.get("enforcement") != "active":
        return False
    if not _ref_included(rule):
        return False
    if type(rule.get("bypass_actors")) is not list or rule["bypass_actors"] != []:
        return False
    present = {r.get("type") for r in rule.get("rules", []) or [] if isinstance(r, dict)}
    if not {"deletion", "non_fast_forward", "pull_request", "required_status_checks"} <= present:
        return False
    pull = _rule(rule, "pull_request").get("parameters", {})
    if (
        not isinstance(pull, dict)
        or pull.get("allowed_merge_methods") != ["squash"]
        or pull.get("required_review_thread_resolution") is not True
    ):
        return False
    checks = _rule(rule, "required_status_checks").get("parameters", {})
    if not isinstance(checks, dict):
        return False
    if checks.get("strict_required_status_checks_policy") is not True:
        return False
    items = checks.get("required_status_checks")
    return isinstance(items, list) and any(
        isinstance(item, dict)
        and item.get("context") == "summary"
        and item.get("integration_id") == GITHUB_ACTIONS_APP_ID
        for item in items
    )


def audit(rulesets: list, repository: Optional[dict]) -> dict:
    main_enforced = any(
        _main_enforced(item) for item in rulesets if isinstance(item, dict)
    )
    delete_on_merge = bool(
        isinstance(repository, dict) and repository.get("delete_branch_on_merge") is True
    )
    findings = []
    if not main_enforced:
        findings.append("protected research main requires strict PR/squash/summary/no-bypass rules")
    if not delete_on_merge:
        findings.append("repository delete_branch_on_merge must be enabled")
    return {
        "schema_version": 2,
        "scope": "technical-research-main-only",
        "result": "PASS" if not findings else "FAIL",
        "main_ruleset_enforced": main_enforced,
        "delete_branch_on_merge_enabled": delete_on_merge,
        "findings": findings,
    }


def _gh_json(args: list, *, token: Optional[str] = None) -> object:
    command = [
        "gh", "api", "-H", "Accept: application/vnd.github+json",
        "-H", "X-GitHub-Api-Version: " + API_VERSION, *args,
    ]
    env = os.environ.copy()
    if token is not None:
        env["GH_TOKEN"] = token
    process = subprocess.run(
        command, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        check=False, env=env,
    )
    if process.returncode:
        raise RuntimeError(
            "GitHub API read failed; repository/branch protection was not verified: "
            + process.stderr.strip()
        )
    return json.loads(process.stdout)


def fetch_live(repository: str, *, repository_metadata_token: Optional[str] = None):
    summaries = _gh_json(["repos/{}/rulesets".format(repository)])
    if not isinstance(summaries, list):
        raise RuntimeError("repository ruleset list is not an array")
    details = []
    for item in summaries:
        if not isinstance(item, dict) or type(item.get("id")) is not int:
            continue
        detail = _gh_json(["repos/{}/rulesets/{}".format(repository, item["id"])])
        if isinstance(detail, dict):
            details.append(detail)
    repository_info = _gh_json(
        ["repos/{}".format(repository)], token=repository_metadata_token
    )
    if not isinstance(repository_info, dict):
        raise RuntimeError("repository metadata is not an object")
    return details, repository_info


def self_test() -> None:
    import copy

    main = {
        "target": "branch", "enforcement": "active", "bypass_actors": [],
        "conditions": {"ref_name": {"include": ["refs/heads/main"], "exclude": []}},
        "rules": [
            {"type": "deletion"},
            {"type": "non_fast_forward"},
            {"type": "pull_request", "parameters": {
                "allowed_merge_methods": ["squash"],
                "required_review_thread_resolution": True,
            }},
            {"type": "required_status_checks", "parameters": {
                "strict_required_status_checks_policy": True,
                "required_status_checks": [
                    {"context": "summary", "integration_id": GITHUB_ACTIONS_APP_ID}
                ],
            }},
        ],
    }
    repo = {"delete_branch_on_merge": True}
    assert audit([main], repo)["result"] == "PASS"
    assert audit([main, {"target": "tag", "enforcement": "active"}], repo)["result"] == "PASS"
    for variant in (
        {"delete_branch_on_merge": False},
        {"delete_branch_on_merge": "true"},
        {},
    ):
        assert audit([main], variant)["result"] == "FAIL"
    assert audit([], repo)["result"] == "FAIL"
    for field, replacements in (
        ("bypass_actors", [None, False, {}, [{"actor_type": "RepositoryRole", "actor_id": 5}]]),
        ("enforcement", ["evaluate", "disabled", None]),
        ("target", ["tag", None]),
    ):
        for value in replacements:
            bad = copy.deepcopy(main)
            bad[field] = value
            assert audit([bad], repo)["result"] == "FAIL", (field, value)
    for ref in ([], ["refs/heads/*"], ["refs/tags/v*"], ["refs/heads/main", None]):
        bad = copy.deepcopy(main)
        bad["conditions"]["ref_name"]["include"] = ref
        assert audit([bad], repo)["result"] == "FAIL", ref
    for exclusion in (None, ["refs/heads/main"], ["~DEFAULT_BRANCH"]):
        bad = copy.deepcopy(main)
        bad["conditions"]["ref_name"]["exclude"] = exclusion
        assert audit([bad], repo)["result"] == "FAIL", exclusion
    for kind in ("deletion", "non_fast_forward", "pull_request", "required_status_checks"):
        bad = copy.deepcopy(main)
        bad["rules"] = [item for item in bad["rules"] if item["type"] != kind]
        assert audit([bad], repo)["result"] == "FAIL", kind
    bad = copy.deepcopy(main)
    bad["rules"][2]["parameters"]["allowed_merge_methods"] = ["merge", "squash"]
    assert audit([bad], repo)["result"] == "FAIL"
    bad = copy.deepcopy(main)
    bad["rules"][3]["parameters"]["strict_required_status_checks_policy"] = False
    assert audit([bad], repo)["result"] == "FAIL"
    bad = copy.deepcopy(main)
    bad["rules"][3]["parameters"]["required_status_checks"][0]["integration_id"] = 0
    assert audit([bad], repo)["result"] == "FAIL"
    bad = copy.deepcopy(main)
    bad["conditions"]["ref_name"]["include"] = ["~DEFAULT_BRANCH"]
    assert audit([bad], repo)["result"] == "PASS"
    print("research main governance self-test: OK")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--repository", default=os.environ.get("GITHUB_REPOSITORY"))
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    if not args.repository or args.output is None:
        parser.error("--repository and --output are required")
    rulesets, repository = fetch_live(
        args.repository,
        repository_metadata_token=os.environ.get("REPOSITORY_METADATA_TOKEN"),
    )
    result = audit(rulesets, repository)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n",
                           encoding="utf-8")
    print(json.dumps(result, sort_keys=True))
    return 0 if result["result"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
