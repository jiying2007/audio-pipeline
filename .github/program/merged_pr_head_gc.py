#!/usr/bin/env python3
"""Delete only the exact same-repository head ref of the PR that produced main.

The candidate branch is never supplied by a caller. It is derived from GitHub's
commit->PR association for the exact main commit. The exact main commit must map
to exactly one merged PR targeting main. If that PR comes from this repository,
the live branch ref must still equal GitHub's recorded PR head SHA and have no
open PR before deletion. External/fork PR heads are explicitly non-mutating.

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
    exact_names = contract.get("allowed_exact_names", [])
    require(isinstance(exact_names, list), "allowed_exact_names must be a list")
    require(all(isinstance(item, str) and item and item != "main" for item in exact_names),
            "invalid exact branch exception")
    require(len(set(exact_names)) == len(exact_names), "duplicate exact branch exception")
    require(all(not any(item.startswith(prefix) for prefix in prefixes) for item in exact_names),
            "exact branch exceptions must remain outside allowed prefixes")
    records = contract.get("branches")
    require(isinstance(records, list) and records, "branches must be a non-empty list")
    record_names = set()
    for index, record in enumerate(records):
        require(set(record) == {"name", "expected_sha"}, f"record {index} fields drift")
        branch = record["name"]
        sha = record["expected_sha"]
        require(isinstance(branch, str) and branch and branch != "main",
                f"invalid branch at record {index}")
        require(branch not in record_names, f"duplicate branch: {branch}")
        record_names.add(branch)
        require(isinstance(sha, str) and SHA_RE.fullmatch(sha) is not None,
                f"invalid expected SHA: {branch}")
    require(set(exact_names).issubset(record_names),
            "exact branch exception missing pinned branch record")


def merged_head_policy(contract: dict, branch: str, head_sha: str) -> str:
    prefix_allowed = any(branch.startswith(prefix) for prefix in contract["allowed_prefixes"])
    exact_names = set(contract.get("allowed_exact_names", []))
    static_records = {
        record["name"]: str(record["expected_sha"]).lower()
        for record in contract["branches"]
    }
    exact_allowed = branch in exact_names
    require(prefix_allowed or exact_allowed,
            f"merged PR head outside allowed prefixes and exact exceptions: {branch}")
    if exact_allowed:
        require(static_records.get(branch) == head_sha,
                f"merged PR exact-name SHA drift: branch={branch} "
                f"pinned={static_records.get(branch)} expected={head_sha}")
        return "EXACT_NAME_AND_SHA"
    require(branch not in static_records,
            "current prefix-allowed merged PR head must not duplicate the static terminal-ref set")
    return "ALLOWED_PREFIX"


def select_merged_pr(payload: object, main_sha: str) -> dict:
    """Resolve the unique merged PR that produced the exact main commit."""
    require(isinstance(payload, list), "unexpected commit PR response")
    matches = []
    for pr in payload:
        if not isinstance(pr, dict):
            continue
        if (
            pr.get("merged_at")
            and pr.get("base", {}).get("ref") == "main"
            and str(pr.get("merge_commit_sha", "")).lower() == main_sha
        ):
            matches.append(pr)
    require(len(matches) == 1,
            f"exact main commit must map to exactly one merged PR targeting main; matches={len(matches)}")
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
    pr = select_merged_pr(payload, main_sha)
    head = pr.get("head", {}) if isinstance(pr.get("head"), dict) else {}
    head_repo = head.get("repo", {}) if isinstance(head.get("repo"), dict) else {}
    head_repo_full_name = str(head_repo.get("full_name") or "")
    branch = str(head.get("ref") or "")
    head_sha = str(head.get("sha") or "").lower()

    # Never mutate a fork or any repository other than the current repository.
    if head_repo_full_name != repository:
        return {
            "schema_version": 1,
            "mode": "apply",
            "repository": repository,
            "main_sha": main_sha,
            "pull_request": int(pr["number"]),
            "branch": branch or None,
            "expected_head_sha": head_sha or None,
            "head_repository": head_repo_full_name or None,
            "action": "SKIP_EXTERNAL_HEAD_REPOSITORY",
            "derivation": "exact-main-commit-to-unique-merged-pr-external-head-no-mutation",
            "authority": authority,
        }

    require(branch and branch != "main", "merged PR head branch is invalid")
    require(SHA_RE.fullmatch(head_sha) is not None, "merged PR head SHA is invalid")
    admission = merged_head_policy(contract, branch, head_sha)
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
        "head_repository": head_repo_full_name,
        "action": action,
        "admission": admission,
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
        "allowed_exact_names": ["docs/special"],
        "branches": [
            {"name": "governance/older", "expected_sha": "a" * 40},
            {"name": "docs/special", "expected_sha": "2" * 40},
        ],
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
    assert select_merged_pr(good, main_sha)["number"] == 7
    assert merged_head_policy(contract, "governance/current", "2" * 40) == "ALLOWED_PREFIX"
    assert merged_head_policy(contract, "docs/special", "2" * 40) == "EXACT_NAME_AND_SHA"
    for branch, sha in (("docs/special", "3" * 40), ("docs/unlisted", "2" * 40)):
        try:
            merged_head_policy(contract, branch, sha)
        except ValueError:
            pass
        else:
            raise AssertionError(f"unsafe merged-head admission accepted: {branch}")
    external = [{**good[0], "head": {**good[0]["head"], "repo": {"full_name": "fork/r"}}}]
    assert select_merged_pr(external, main_sha)["number"] == 7
    for bad in (
        [{**good[0], "merge_commit_sha": "3" * 40}],
        [{**good[0], "base": {"ref": "other"}}],
        good + [{**good[0], "number": 8}],
    ):
        try:
            select_merged_pr(bad, main_sha)
        except ValueError:
            pass
        else:
            raise AssertionError("ambiguous or non-main merged PR selection accepted")
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
