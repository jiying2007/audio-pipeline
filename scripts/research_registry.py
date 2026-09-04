#!/usr/bin/env python3
"""Validate research lifecycle evidence and safely garbage-collect terminal branches."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import tempfile
from pathlib import Path
from urllib.parse import quote

SCHEMA_VERSION = 1
STATUSES = {"ACTIVE", "ACCEPTED", "REJECTED", "SUPERSEDED", "ABANDONED", "UNCLASSIFIED"}
TERMINAL_STATUSES = {"ACCEPTED", "REJECTED", "SUPERSEDED", "ABANDONED"}
GC_PREFIXES = ("research/", "validation/", "feat/", "opt/")
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
CONFIRMATION = "DELETE_GC_ELIGIBLE_REFS"


def load_registry(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    validate_registry(data)
    return data


def validate_registry(data: dict) -> None:
    if data.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(f"research registry schema_version must be {SCHEMA_VERSION}")
    records = data.get("records")
    if not isinstance(records, list):
        raise ValueError("research registry records must be a list")
    branches: set[str] = set()
    for index, record in enumerate(records):
        if not isinstance(record, dict):
            raise ValueError(f"record {index} must be an object")
        branch = record.get("branch")
        status = record.get("status")
        if not isinstance(branch, str) or not branch or branch == "main":
            raise ValueError(f"record {index} has invalid branch")
        if branch in branches:
            raise ValueError(f"duplicate research branch: {branch}")
        branches.add(branch)
        if not branch.startswith(GC_PREFIXES):
            raise ValueError(f"branch outside lifecycle prefixes: {branch}")
        if status not in STATUSES:
            raise ValueError(f"invalid lifecycle status for {branch}: {status}")
        head_sha = record.get("head_sha")
        if head_sha is not None and not SHA_RE.fullmatch(str(head_sha)):
            raise ValueError(f"invalid head_sha for {branch}")
        evidence = record.get("evidence", [])
        if not isinstance(evidence, list) or any(not isinstance(item, str) or not item for item in evidence):
            raise ValueError(f"invalid evidence list for {branch}")
        gc_eligible = bool(record.get("gc_eligible", False))
        auto_gc = bool(record.get("auto_gc", False))
        if gc_eligible:
            if status not in TERMINAL_STATUSES:
                raise ValueError(f"non-terminal branch marked gc_eligible: {branch}")
            if not head_sha:
                raise ValueError(f"gc_eligible branch must pin head_sha: {branch}")
            if not evidence:
                raise ValueError(f"gc_eligible branch must have sealed evidence: {branch}")
        if auto_gc and not gc_eligible:
            raise ValueError(f"auto_gc requires gc_eligible: {branch}")


def gh_json(endpoint: str, *extra: str) -> object:
    command = ["gh", "api", endpoint, *extra]
    completed = subprocess.run(command, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip()
        raise RuntimeError(f"gh api failed for {endpoint}: {detail}")
    return json.loads(completed.stdout or "null")


def branch_sha(repository: str, branch: str) -> str | None:
    endpoint = f"repos/{repository}/git/ref/heads/{quote(branch, safe='/')}"
    completed = subprocess.run(["gh", "api", endpoint], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if completed.returncode != 0:
        if "HTTP 404" in completed.stderr or "Not Found" in completed.stderr:
            return None
        raise RuntimeError((completed.stderr or completed.stdout).strip())
    payload = json.loads(completed.stdout)
    return str(payload["object"]["sha"])


def open_prs(repository: str, branch: str) -> list[dict]:
    owner = repository.split("/", 1)[0]
    payload = gh_json(
        f"repos/{repository}/pulls",
        "-X", "GET", "-f", "state=open", "-f", f"head={owner}:{branch}",
    )
    if not isinstance(payload, list):
        raise RuntimeError("unexpected pull request response")
    return payload


def delete_branch(repository: str, branch: str) -> None:
    endpoint = f"repos/{repository}/git/refs/heads/{quote(branch, safe='/')}"
    completed = subprocess.run(
        ["gh", "api", "--method", "DELETE", endpoint],
        text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    if completed.returncode != 0:
        raise RuntimeError((completed.stderr or completed.stdout).strip())


def plan(data: dict, repository: str, *, auto_only: bool = False, apply: bool = False) -> dict:
    actions: list[dict] = []
    deletable: list[tuple[dict, str]] = []
    for record in data["records"]:
        if not record.get("gc_eligible"):
            continue
        if auto_only and not record.get("auto_gc"):
            continue
        branch = record["branch"]
        expected = record["head_sha"]
        current = branch_sha(repository, branch)
        item = {"branch": branch, "expected_head_sha": expected, "current_head_sha": current}
        if current is None:
            item["action"] = "ALREADY_DELETED"
        elif current != expected:
            item["action"] = "BLOCK_SHA_DRIFT"
        else:
            prs = open_prs(repository, branch)
            if prs:
                item["action"] = "BLOCK_OPEN_PR"
                item["open_prs"] = [int(pr["number"]) for pr in prs]
            else:
                item["action"] = "DELETE_DRY_RUN"
                deletable.append((item, branch))
        actions.append(item)
    blocked = [item for item in actions if item["action"].startswith("BLOCK_")]
    if apply and not blocked:
        for item, branch in deletable:
            delete_branch(repository, branch)
            item["action"] = "DELETED"
    elif apply and blocked:
        for item, _branch in deletable:
            item["action"] = "ABORT_BLOCKED"
    return {
        "schema_version": 1,
        "repository": repository,
        "mode": "apply" if apply else "dry-run",
        "auto_only": auto_only,
        "actions": actions,
        "blocked": len(blocked),
        "deletions": sum(item["action"] == "DELETED" for item in actions),
    }


def self_test() -> None:
    good = {
        "schema_version": 1,
        "records": [
            {"branch": "research/example-v1", "head_sha": "a" * 40, "status": "REJECTED",
             "evidence": ["run:1"], "gc_eligible": True, "auto_gc": True},
            {"branch": "research/active-v2", "head_sha": None, "status": "UNCLASSIFIED",
             "evidence": [], "gc_eligible": False, "auto_gc": False},
        ],
    }
    validate_registry(good)
    for mutation in (
        lambda d: d["records"].append(dict(d["records"][0])),
        lambda d: d["records"][0].update(status="ACTIVE"),
        lambda d: d["records"][0].update(head_sha="bad"),
        lambda d: d["records"][1].update(auto_gc=True),
    ):
        clone = json.loads(json.dumps(good))
        mutation(clone)
        try:
            validate_registry(clone)
        except ValueError:
            pass
        else:
            raise AssertionError("invalid research registry mutation was accepted")
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "registry.json"
        path.write_text(json.dumps(good), encoding="utf-8")
        assert load_registry(path)["schema_version"] == 1
    print("research registry self-test: OK")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--registry", type=Path, default=Path(".github/research/evidence-index.json"))
    parser.add_argument("--repository")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--auto-only", action="store_true")
    parser.add_argument("--confirmation", default="")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    data = load_registry(args.registry)
    if not args.repository:
        parser.error("--repository is required unless --self-test is used")
    if args.apply and args.confirmation != CONFIRMATION:
        raise SystemExit(f"apply requires --confirmation {CONFIRMATION}")
    result = plan(data, args.repository, auto_only=args.auto_only, apply=args.apply)
    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 1 if result["blocked"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
