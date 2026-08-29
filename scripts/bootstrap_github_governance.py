#!/usr/bin/env python3
"""Idempotently install the repository governance required by v1.6 releases."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
from pathlib import Path

API_VERSION = "2026-03-10"
GITHUB_ACTIONS_APP_ID = 15368
MAIN_RULESET_NAME = "audio-pipeline-main"
TAG_RULESET_NAME = "audio-pipeline-version-tags"


def main_ruleset() -> dict:
    return {
        "name": MAIN_RULESET_NAME,
        "target": "branch",
        "enforcement": "active",
        "bypass_actors": [],
        "conditions": {
            "ref_name": {"include": ["refs/heads/main"], "exclude": []}
        },
        "rules": [
            {"type": "deletion"},
            {"type": "non_fast_forward"},
            {
                "type": "pull_request",
                "parameters": {
                    "required_approving_review_count": 0,
                    "dismiss_stale_reviews_on_push": False,
                    "require_code_owner_review": False,
                    "require_last_push_approval": False,
                    "required_review_thread_resolution": True,
                    "allowed_merge_methods": ["squash"],
                },
            },
            {
                "type": "required_status_checks",
                "parameters": {
                    "do_not_enforce_on_create": False,
                    "strict_required_status_checks_policy": True,
                    "required_status_checks": [
                        {
                            "context": "summary",
                            "integration_id": GITHUB_ACTIONS_APP_ID,
                        }
                    ],
                },
            },
        ],
    }


def tag_ruleset() -> dict:
    return {
        "name": TAG_RULESET_NAME,
        "target": "tag",
        "enforcement": "active",
        "bypass_actors": [],
        "conditions": {
            "ref_name": {"include": ["refs/tags/v*"], "exclude": []}
        },
        "rules": [
            {"type": "deletion"},
            {"type": "non_fast_forward"},
        ],
    }


def _command(args: list[str], payload: dict | None = None) -> str:
    command = [
        "gh", "api",
        "-H", "Accept: application/vnd.github+json",
        "-H", f"X-GitHub-Api-Version: {API_VERSION}",
        *args,
    ]
    result = subprocess.run(
        command,
        input=(json.dumps(payload) if payload is not None else None),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"GitHub API command failed ({result.returncode}): {' '.join(command)}\n"
            f"{result.stderr.strip()}"
        )
    return result.stdout


def _json(args: list[str], payload: dict | None = None) -> object:
    text = _command(args, payload).strip()
    return json.loads(text) if text else None


def choose_existing(summaries: list[dict], name: str, target: str) -> dict | None:
    matches = [
        item for item in summaries
        if item.get("name") == name and item.get("target") == target
    ]
    if len(matches) > 1:
        raise ValueError(f"multiple rulesets match {name!r}/{target!r}")
    return matches[0] if matches else None


def upsert_ruleset(repository: str, summaries: list[dict], desired: dict) -> tuple[str, int]:
    existing = choose_existing(summaries, desired["name"], desired["target"])
    if existing is None:
        response = _json(
            ["-X", "POST", f"repos/{repository}/rulesets", "--input", "-"], desired
        )
        action = "created"
    else:
        response = _json(
            ["-X", "PUT", f"repos/{repository}/rulesets/{existing['id']}", "--input", "-"],
            desired,
        )
        action = "updated"
    if not isinstance(response, dict) or not isinstance(response.get("id"), int):
        raise RuntimeError(f"unexpected ruleset response for {desired['name']}")
    return action, int(response["id"])


def apply(repository: str) -> dict:
    summaries = _json([f"repos/{repository}/rulesets"])
    if not isinstance(summaries, list):
        raise RuntimeError("repository ruleset list is not an array")

    main_action, main_id = upsert_ruleset(repository, summaries, main_ruleset())
    # Refresh after the first create so a second invocation remains unambiguous.
    summaries = _json([f"repos/{repository}/rulesets"])
    if not isinstance(summaries, list):
        raise RuntimeError("repository ruleset list is not an array")
    tag_action, tag_id = upsert_ruleset(repository, summaries, tag_ruleset())

    _command(["-X", "PUT", f"repos/{repository}/immutable-releases"])
    return {
        "schema_version": 1,
        "repository": repository,
        "main_ruleset": {"action": main_action, "id": main_id},
        "tag_ruleset": {"action": tag_action, "id": tag_id},
        "immutable_releases": "enabled",
    }


def self_test() -> None:
    main = main_ruleset()
    assert main["target"] == "branch"
    assert main["bypass_actors"] == []
    pr = next(rule for rule in main["rules"] if rule["type"] == "pull_request")
    assert pr["parameters"]["allowed_merge_methods"] == ["squash"]
    status = next(rule for rule in main["rules"] if rule["type"] == "required_status_checks")
    check = status["parameters"]["required_status_checks"][0]
    assert check == {"context": "summary", "integration_id": GITHUB_ACTIONS_APP_ID}
    assert status["parameters"]["strict_required_status_checks_policy"] is True
    tags = tag_ruleset()
    assert tags["conditions"]["ref_name"]["include"] == ["refs/tags/v*"]
    assert {rule["type"] for rule in tags["rules"]} == {"deletion", "non_fast_forward"}
    sample = [{"id": 1, "name": MAIN_RULESET_NAME, "target": "branch"}]
    assert choose_existing(sample, MAIN_RULESET_NAME, "branch")["id"] == 1
    assert choose_existing(sample, TAG_RULESET_NAME, "tag") is None
    try:
        choose_existing(sample + sample, MAIN_RULESET_NAME, "branch")
    except ValueError:
        pass
    else:
        raise AssertionError("duplicate ruleset self-test did not fail")
    print("github governance bootstrap self-test: OK")


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
    result = apply(args.repository)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
