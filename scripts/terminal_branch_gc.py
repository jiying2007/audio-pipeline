#!/usr/bin/env python3
"""Fail-closed garbage collection for terminal non-main software branches.

A branch may be deleted only when its live SHA is exactly pinned, it has no
open PR, the software/public-data program is terminal, and its terminal state
is preserved by at least one independently checkable mechanism:
- its exact commit is already in main history;
- its exact head was the head of a PR merged to main;
- its exact SHA is cited by committed program/research evidence; or
- every path changed by its branch-only delta is already identical on main.

This tool never grants HIL, acoustic, certification, or Product Qualification
authority.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
from pathlib import Path
from urllib.parse import quote

SCHEMA_VERSION = 1
CONFIRMATION = "DELETE_TERMINAL_REFS"
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
DEFAULT_CONTRACT = Path("docs/program/terminal-branch-gc.json")
AUTHORITATIVE_EVIDENCE = (
    Path("docs/program/plan.json"),
    Path(".github/research/evidence-index.json"),
)


def require(ok: bool, message: str) -> None:
    if not ok:
        raise ValueError(message)


def run(command: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=check
    )


def git(*args: str, check: bool = True) -> str:
    proc = run(["git", *args], check=check)
    return proc.stdout.strip()


def gh_json(endpoint: str, *extra: str) -> object:
    proc = run(["gh", "api", endpoint, *extra])
    return json.loads(proc.stdout or "null")


def validate_contract(data: dict) -> None:
    require(data.get("schema_version") == SCHEMA_VERSION, "unsupported terminal GC schema")
    require(data.get("policy") == "terminal-non-main-ref-gc", "unexpected terminal GC policy")
    require(data.get("mutation_on_pull_request") is False, "PR mutation must remain disabled")
    require(data.get("mutation_on_workflow_dispatch") is False, "manual mutation must remain disabled")
    require(data.get("mutation_on_main_push") is True, "main-push mutation contract missing")
    for key in (
        "require_exact_live_sha",
        "require_no_open_pull_request",
        "require_preserved_terminal_evidence",
        "require_software_program_terminal",
    ):
        require(data.get(key) is True, f"{key} must remain fail-closed")
    require(data.get("unlisted_branch_deletion_allowed") is False, "unlisted deletion forbidden")

    prefixes = data.get("allowed_prefixes")
    require(isinstance(prefixes, list) and prefixes, "allowed_prefixes must be non-empty")
    require(all(isinstance(item, str) and item.endswith("/") for item in prefixes),
            "invalid allowed prefix")

    records = data.get("branches")
    require(isinstance(records, list) and records, "branches must be a non-empty list")
    seen: set[str] = set()
    for index, record in enumerate(records):
        require(set(record) == {"name", "expected_sha"}, f"record {index} fields drift")
        branch = record["name"]
        sha = record["expected_sha"]
        require(isinstance(branch, str) and branch and branch != "main",
                f"invalid branch at record {index}")
        require(any(branch.startswith(prefix) for prefix in prefixes),
                f"branch outside allowed prefixes: {branch}")
        require(branch not in seen, f"duplicate branch: {branch}")
        seen.add(branch)
        require(isinstance(sha, str) and SHA_RE.fullmatch(sha) is not None,
                f"invalid expected SHA: {branch}")

    authority = data.get("authority_boundary")
    require(authority == {
        "hardware_test_executed": False,
        "hardware_collection_performed": False,
        "shipping_source_changed": False,
        "release_changed": False,
        "product_qualification": "DEFERRED_BY_SCOPE",
        "dut_hil": "DEFERRED_BY_SCOPE",
    }, "terminal branch GC cannot gain product/hardware authority")


def validate_program_terminal(root: Path) -> dict:
    plan = json.loads((root / "docs/program/plan.json").read_text(encoding="utf-8"))
    require(plan.get("schema_version") == 1, "program schema drift")
    require(plan.get("phase") == "software-public-data", "program phase drift")
    require(plan.get("product_qualification") == "DEFERRED_BY_SCOPE", "PQ boundary drift")
    require(plan.get("hardware_collection") is False, "hardware collection must remain disabled")
    require(plan.get("auto_promote") is False, "auto promotion must remain disabled")

    tasks = plan.get("tasks")
    require(isinstance(tasks, list) and tasks, "program tasks missing")
    e001 = None
    for task in tasks:
        if task.get("id") == "E001":
            e001 = task
            continue
        require(task.get("status") == "CLOSED",
                f"software task is not terminal: {task.get('id')}={task.get('status')}")
    require(e001 is not None, "E001 task missing")
    require(e001.get("status") == "DEFERRED" and e001.get("lane") == "external",
            "E001 must remain external/deferred")
    require(e001.get("handler") is None, "E001 must not become software executable")
    return {
        "phase": plan["phase"],
        "product_qualification": plan["product_qualification"],
        "hardware_collection": plan["hardware_collection"],
        "software_tasks_terminal": True,
        "e001": "DEFERRED",
    }


def branch_sha(repository: str, branch: str) -> str | None:
    endpoint = f"repos/{repository}/git/ref/heads/{quote(branch, safe='/')}"
    proc = run(["gh", "api", endpoint], check=False)
    if proc.returncode:
        if "404" in proc.stderr or "Not Found" in proc.stderr:
            return None
        raise RuntimeError((proc.stderr or proc.stdout).strip())
    return str(json.loads(proc.stdout)["object"]["sha"])


def open_pr_numbers(repository: str, branch: str) -> list[int]:
    owner = repository.split("/", 1)[0]
    payload = gh_json(
        f"repos/{repository}/pulls",
        "-X", "GET", "-f", "state=open", "-f", f"head={owner}:{branch}", "-f", "per_page=100",
    )
    require(isinstance(payload, list), "unexpected open PR response")
    return [int(item["number"]) for item in payload]


def merged_pr_numbers(repository: str, branch: str, sha: str) -> list[int]:
    payload = gh_json(f"repos/{repository}/commits/{sha}/pulls")
    require(isinstance(payload, list), "unexpected commit PR response")
    result = []
    for pr in payload:
        if (
            pr.get("merged_at")
            and pr.get("base", {}).get("ref") == "main"
            and pr.get("head", {}).get("ref") == branch
            and str(pr.get("head", {}).get("sha", "")).lower() == sha
        ):
            result.append(int(pr["number"]))
    return result


def authoritative_evidence_hits(root: Path, sha: str) -> list[str]:
    candidates: list[Path] = list(AUTHORITATIVE_EVIDENCE)
    iteration_root = root / "docs/program/iterations"
    if iteration_root.is_dir():
        candidates.extend(path.relative_to(root) for path in iteration_root.rglob("*.json"))
    hits = []
    for relative in candidates:
        path = root / relative
        if path.is_file() and sha in path.read_text(encoding="utf-8", errors="replace"):
            hits.append(str(relative))
    return sorted(set(hits))


def object_id(revision: str, path: str) -> str | None:
    proc = run(["git", "rev-parse", f"{revision}:{path}"], check=False)
    return proc.stdout.strip() if proc.returncode == 0 else None


def delta_subsumed_by_main(branch_sha_value: str, main_sha: str) -> tuple[bool, list[str]]:
    base = git("merge-base", branch_sha_value, main_sha)
    changed_raw = git("diff", "--name-only", f"{base}..{branch_sha_value}")
    changed = [line for line in changed_raw.splitlines() if line]
    if not changed:
        return True, []
    mismatched = [
        path for path in changed
        if object_id(branch_sha_value, path) != object_id(main_sha, path)
    ]
    return not mismatched, mismatched


def delete_branch(repository: str, branch: str) -> None:
    endpoint = f"repos/{repository}/git/refs/heads/{quote(branch, safe='/')}"
    proc = run(["gh", "api", "--method", "DELETE", endpoint], check=False)
    if proc.returncode:
        raise RuntimeError((proc.stderr or proc.stdout).strip())


def evaluate(root: Path, contract: dict, repository: str, main_sha: str, *, apply: bool) -> dict:
    validate_contract(contract)
    program = validate_program_terminal(root)
    require(SHA_RE.fullmatch(main_sha) is not None, "main_sha must be exact 40-hex")
    require(git("cat-file", "-t", main_sha) == "commit", "main_sha must resolve to a commit")

    actions: list[dict] = []
    deletable: list[tuple[dict, str]] = []
    for record in contract["branches"]:
        branch = record["name"]
        expected = record["expected_sha"]
        current = branch_sha(repository, branch)
        item: dict = {
            "branch": branch,
            "expected_head_sha": expected,
            "current_head_sha": current,
        }
        if current is None:
            item["action"] = "ALREADY_DELETED"
            item["preservation"] = "NOT_REQUIRED_REF_ABSENT"
            actions.append(item)
            continue
        if current.lower() != expected:
            item["action"] = "BLOCK_SHA_DRIFT"
            actions.append(item)
            continue

        prs = open_pr_numbers(repository, branch)
        if prs:
            item["action"] = "BLOCK_OPEN_PR"
            item["open_prs"] = prs
            actions.append(item)
            continue

        preserved = False
        if run(["git", "merge-base", "--is-ancestor", expected, main_sha], check=False).returncode == 0:
            item["preservation"] = "MAIN_HISTORY"
            preserved = True
        else:
            merged = merged_pr_numbers(repository, branch, expected)
            if merged:
                item["preservation"] = "MERGED_PR"
                item["merged_prs"] = merged
                preserved = True
            else:
                hits = authoritative_evidence_hits(root, expected)
                if hits:
                    item["preservation"] = "COMMITTED_EXACT_SHA_EVIDENCE"
                    item["evidence_files"] = hits
                    preserved = True
                else:
                    subsumed, mismatched = delta_subsumed_by_main(expected, main_sha)
                    if subsumed:
                        item["preservation"] = "BRANCH_DELTA_SUBSUMED_BY_MAIN"
                        preserved = True
                    else:
                        item["action"] = "BLOCK_UNPRESERVED_TERMINAL_REF"
                        item["mismatched_paths"] = mismatched[:20]
        if preserved:
            item["action"] = "DELETE_DRY_RUN"
            deletable.append((item, branch))
        actions.append(item)

    blocked = [item for item in actions if item["action"].startswith("BLOCK_")]
    if apply and not blocked:
        for item, branch in deletable:
            delete_branch(repository, branch)
            if branch_sha(repository, branch) is not None:
                raise RuntimeError(f"branch deletion did not take effect: {branch}")
            item["action"] = "DELETED"
    elif apply and blocked:
        for item, _branch in deletable:
            item["action"] = "ABORT_BLOCKED"

    return {
        "schema_version": 1,
        "repository": repository,
        "main_sha": main_sha,
        "mode": "apply" if apply else "dry-run",
        "program": program,
        "actions": actions,
        "blocked": len(blocked),
        "deletions": sum(item["action"] == "DELETED" for item in actions),
        "deletable": sum(item["action"] == "DELETE_DRY_RUN" for item in actions),
        "already_deleted": sum(item["action"] == "ALREADY_DELETED" for item in actions),
        "authority": contract["authority_boundary"],
    }


def self_test() -> None:
    sample = {
        "schema_version": 1,
        "policy": "terminal-non-main-ref-gc",
        "baseline_main_sha": "1" * 40,
        "mutation_on_pull_request": False,
        "mutation_on_workflow_dispatch": False,
        "mutation_on_main_push": True,
        "require_exact_live_sha": True,
        "require_no_open_pull_request": True,
        "require_preserved_terminal_evidence": True,
        "require_software_program_terminal": True,
        "unlisted_branch_deletion_allowed": False,
        "allowed_prefixes": ["governance/"],
        "branches": [{"name": "governance/example", "expected_sha": "a" * 40}],
        "authority_boundary": {
            "hardware_test_executed": False,
            "hardware_collection_performed": False,
            "shipping_source_changed": False,
            "release_changed": False,
            "product_qualification": "DEFERRED_BY_SCOPE",
            "dut_hil": "DEFERRED_BY_SCOPE",
        },
    }
    validate_contract(sample)
    for mutation in (
        lambda d: d.update(mutation_on_pull_request=True),
        lambda d: d["branches"][0].update(expected_sha="bad"),
        lambda d: d["branches"][0].update(name="main"),
        lambda d: d.update(unlisted_branch_deletion_allowed=True),
    ):
        clone = json.loads(json.dumps(sample))
        mutation(clone)
        try:
            validate_contract(clone)
        except ValueError:
            pass
        else:
            raise AssertionError("unsafe terminal branch GC contract accepted")
    print("terminal branch GC self-test: OK")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT)
    parser.add_argument("--repository")
    parser.add_argument("--main-sha")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirmation", default="")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        self_test()
        return 0
    if not args.repository or not args.main_sha:
        parser.error("--repository and --main-sha are required")
    if args.apply:
        if args.confirmation != CONFIRMATION:
            raise SystemExit(f"apply requires --confirmation {CONFIRMATION}")
        if os.getenv("GITHUB_EVENT_NAME") != "push" or os.getenv("GITHUB_REF") != "refs/heads/main":
            raise SystemExit("terminal ref mutation is allowed only on a main push")

    root = Path.cwd()
    contract = json.loads(args.contract.read_text(encoding="utf-8"))
    result = evaluate(root, contract, args.repository, args.main_sha.lower(), apply=args.apply)
    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 1 if result["blocked"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
