#!/usr/bin/env python3
"""Delete only the exact head ref of the PR that produced the current main commit.

This is a narrow companion to terminal_branch_gc.py. It exists because this
repository does not enable GitHub's delete_branch_on_merge setting. The derived
ref is never supplied by a caller: it must come from GitHub's commit->PR
association for the exact main commit, must be a merged same-repository PR to
main, must have merge_commit_sha equal to that main commit, and the live ref
must still equal the recorded PR head SHA.

No hardware, HIL, acoustic, release, certification or Product Qualification
authority is granted by this cleanup.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
from pathlib import Path
from urllib.parse import quote

SHA_RE = re.compile(r"^[0-9a-f]{40}$")
DEFAULT_CONTRACT = Path("docs/program/terminal-branch-gc.json")


def require(ok: bool, message: str) -> None:
    if not ok:
        raise ValueError(message)


def run(command: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=check)


def gh_json(endpoint: str, *extra: str) -> object:
    proc = run(["gh", "api", endpoint, *extra])
    return json.loads(proc.stdout or "null")


def validate_contract(contract: dict) -> None:
    require(contract.get("schema_version") == 1, "unsupported terminal GC schema")
    require(contract.get("policy") == "terminal-non-main-ref-gc", "unexpected GC policy")
    require(contract.get("unlisted_branch_deletion_allowed") is False,
            "arbitrary unlisted deletion must remain forbidden")
    require(contract.get("delete_current_merged_pr_head_on_main_push") is True,
            "merged PR head self-GC must be explicit")
    require(contract.get("merged_pr_head_same_repository_only") is True,
            "merged PR head self-GC must stay same-repository only")
    require(contract.get("merged_pr_head_exact_main_commit_required") is True,
            "merged PR head self-GC must bind the exact main commit")
    require(contract.get("merged_pr_head_no_open_pr_required") is True,
            "merged PR head self-GC must reject open PRs")
    prefixes = contract.get("allowed_prefixes")
    require(isinstance(prefixes, list) and prefixes, "allowed prefixes missing")
    require(all(isinstance(item, str) and item.endswith("/") for item in prefixes),
            "invalid allowed prefix")


def select_merged_pr(payload: object, repository: str, main_sha: str) -> dict:
    require(isinstance(payload, list), "unexpected commit PR response")
    matches = []
    for pr in payload:
        if not isinstance(pr, dict):
            continue
        if (
            pr.get("merged_at")
            and pr.get("base", {}).get("ref") == "main"
            and str(pr.get("merge_commit_sha", "")).lower() == main_sha
            and pr.get("head", {}).get("repo", {}).get("full_name") == repository
        ):
            matches.append(pr)
    require(len(matches) == 1,
            f"exact main commit must map to exactly one merged same-repo PR; matches={len(matches)}")
    return matches[0]


def branch_sha(repository: str, branch: str) -> str | None:
    endpoint = f"repos/{repository}/git/ref/heads/{quote(branch, safe='/')}"
    proc = run(["gh", "api", endpoint], check=False)
    if proc.returncode:
        if "404" in proc.stderr or "Not Found" in proc.stderr:
            return None
        raise RuntimeError((proc.stderr or proc.stdout).strip())
    return str(json.loads(proc.stdout)["object"]["sha"]).lower()


def open_pr_numbers(repository: str, branch: str) -> list[int]:
    owner = repository.split("/", 1)[0]
    payload = gh_json(
        f"repos/{repository}/pulls",
        "-X", "GET", "-f", "state=open", "-f", f"head={owner}:{branch}", "-f", "per_page=100",
    )
    require(isinstance(payload, list), "unexpected open PR response")
    return [int(item["number"]) for item in payload]


def delete_branch(repository: str, branch: str) -> None:
    endpoint = f"repos/{repository}/git/refs/heads/{quote(branch, safe='/')}"
    proc = run(["gh", "api", "--method", "DELETE", endpoint], check=False)
    if proc.returncode:
        raise RuntimeError((proc.stderr or proc.stdout).strip())


def evaluate(contract: dict, repository: str, main_sha: str, *, apply: bool) -> dict:
    validate_contract(contract)
    require(SHA_RE.fullmatch(main_sha) is not None, "main_sha must be exact 40-hex")
    authority = contract["authority_boundary"]
    if not apply:
        return {
            "schema_version": 1,
            "mode": "deferred-until-main-push",
            "repository": repository,
            "main_sha": main_sha,
            "action": "NO_MUTATION_ON_PULL_REQUEST_OR_MANUAL_DISPATCH",
            "authority": authority,
        }

    payload = gh_json(f"repos/{repository}/commits/{main_sha}/pulls")
    pr = select_merged_pr(payload, repository, main_sha)
    branch = str(pr.get("head", {}).get("ref") or "")
    head_sha = str(pr.get("head", {}).get("sha") or "").lower()
    require(branch and branch != "main", "merged PR head branch is invalid")
    require(SHA_RE.fullmatch(head_sha) is not None, "merged PR head SHA is invalid")
    require(any(branch.startswith(prefix) for prefix in contract["allowed_prefixes"]),
            f"merged PR head outside allowed prefixes: {branch}")

    static_names = {record["name"] for record in contract["branches"]}
    require(branch not in static_names,
            "current merged PR head must not duplicate the static terminal-ref set")
    open_prs = open_pr_numbers(repository, branch)
    require(not open_prs, f"merged PR head unexpectedly has an open PR: {open_prs}")

    current = branch_sha(repository, branch)
    if current is None:
        action = "ALREADY_DELETED"
    else:
        require(current == head_sha,
                f"merged PR head SHA drift: branch={branch} live={current} expected={head_sha}")
        delete_branch(repository, branch)
        require(branch_sha(repository, branch) is None,
                f"merged PR head deletion did not take effect: {branch}")
        action = "DELETED"

    return {
        "schema_version": 1,
        "mode": "apply",
        "repository": repository,
        "main_sha": main_sha,
        "pull_request": int(pr["number"]),
        "branch": branch,
        "expected_head_sha": head_sha,
        "action": action,
        "derivation": "exact-main-commit-to-unique-merged-same-repository-pr",
        "authority": authority,
    }


def self_test() -> None:
    contract = {
        "schema_version": 1,
        "policy": "terminal-non-main-ref-gc",
        "unlisted_branch_deletion_allowed": False,
        "delete_current_merged_pr_head_on_main_push": True,
        "merged_pr_head_same_repository_only": True,
        "merged_pr_head_exact_main_commit_required": True,
        "merged_pr_head_no_open_pr_required": True,
        "allowed_prefixes": ["governance/"],
        "branches": [{"name": "governance/older", "expected_sha": "a" * 40}],
        "authority_boundary": {
            "hardware_test_executed": False,
            "hardware_collection_performed": False,
            "shipping_source_changed": False,
            "release_changed": False,
            "product_qualification": "DEFERRED_BY_SCOPE",
            "dut_hil": "DEFERRED_BY_SCOPE",
        },
    }
    validate_contract(contract)
    main_sha = "1" * 40
    good = [{
        "number": 7,
        "merged_at": "2026-01-01T00:00:00Z",
        "merge_commit_sha": main_sha,
        "base": {"ref": "main"},
        "head": {"ref": "governance/current", "sha": "2" * 40,
                 "repo": {"full_name": "o/r"}},
    }]
    assert select_merged_pr(good, "o/r", main_sha)["number"] == 7
    for bad in (
        [{**good[0], "merge_commit_sha": "3" * 40}],
        [{**good[0], "head": {**good[0]["head"], "repo": {"full_name": "other/r"}}}],
        good + [{**good[0], "number": 8}],
    ):
        try:
            select_merged_pr(bad, "o/r", main_sha)
        except ValueError:
            pass
        else:
            raise AssertionError("unsafe merged PR head selection accepted")
    print("merged PR head GC self-test: OK")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--main-sha", required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    if args.apply and (os.getenv("GITHUB_EVENT_NAME") != "push" or os.getenv("GITHUB_REF") != "refs/heads/main"):
        raise SystemExit("merged PR head mutation is allowed only on a main push")
    contract = json.loads(args.contract.read_text(encoding="utf-8"))
    result = evaluate(contract, args.repository, args.main_sha.lower(), apply=args.apply)
    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
