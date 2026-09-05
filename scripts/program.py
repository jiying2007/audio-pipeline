#!/usr/bin/env python3
"""Validate the committed software/public-data program and run registered work.

This orchestrator is not an acoustic evaluator, optimizer, promotion authority,
or product-certification substitute. Registered handlers are typed and bounded;
a successful execution still requires evidence review and never auto-promotes.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import re
import signal
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLAN = "docs/program/plan.json"
STATES = {"PLANNED", "READY", "ACTIVE", "REVIEW_REQUIRED", "CLOSED", "DEFERRED"}
LANES = {"governance", "measurement", "engineering", "acoustic", "external"}
I003_CANDIDATES = [
    "earliest-qualified",
    "incumbent-qualified",
    "causal-cluster-leading-edge",
]
HANDLERS = {
    "aec-motion-model-qualification": {
        "lane": "measurement",
        "path": "tests/validation/aec_motion_model_qualification.py",
        "contract": "docs/program/iterations/I002.json",
        "iteration_id": "I002",
        "decision": "NOT_AN_ACOUSTIC_CANDIDATE",
    },
    "promotion-governance": {
        "lane": "governance",
        "path": ".github/program/promotion_governance.py",
        "contract": "docs/program/iterations/P001.json",
        "iteration_id": "P001",
        "decision": "GOVERNANCE_READY_NO_ACOUSTIC_CANDIDATE",
    },
    "aec-sync-selector-search": {
        "lane": "acoustic",
        "path": "tests/validation/aec_sync_selector_search.py",
        "contract": "docs/program/iterations/I003.json",
        "iteration_id": "I003",
        "decision": "BOUNDED_SELECTOR_SEARCH_REVIEW_REQUIRED",
    },
}


def require(ok: bool, message: str) -> None:
    if not ok:
        raise ValueError(message)


def keys(value: dict, expected: set[str]) -> None:
    require(isinstance(value, dict) and set(value) == expected, "unknown/missing fields")


def sha(value: str) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{40}", value) is not None


def repo_file(root: Path, value: str) -> Path:
    require(isinstance(value, str) and bool(value), "empty path")
    path = root / value
    require(not Path(value).is_absolute() and ".." not in Path(value).parts,
            "path must stay in repository")
    require(path.resolve().is_relative_to(root.resolve()) and path.is_file(),
            f"missing/escaping file: {value}")
    return path


def validate_contract(task: dict, contract: dict, spec: dict) -> None:
    require(task["lane"] == spec["lane"], "handler lane mismatch")
    require(task["contract"] == spec["contract"] and
            contract["iteration_id"] == spec["iteration_id"] == task["id"],
            "handler/contract identity")
    require(sha(contract["base_sha"]), "contract base SHA")
    require(contract["promotion_allowed"] is False and contract["confirmation_limit"] == 0,
            "registered task cannot acquire promotion/confirmation authority")
    require(type(contract["run_timeout_seconds"]) is int and 1 <= contract["run_timeout_seconds"] <= 900,
            "timeout budget")

    if task["lane"] == "measurement":
        require(contract["candidate_limit"] == 0, "measurement task candidate authority")
        require(contract["data_role"] == "development", "measurement task data role")
        require(len(contract["seeds"]) == 3 and len(set(contract["seeds"])) == 3 and
                all(type(seed) is int and 0 <= seed < 2 ** 32 for seed in contract["seeds"]), "seed budget")
        require(task["id"] == "I002" and contract["phase"] == "measurement-migration" and
                contract["canonical_generator"] == "validation/tools/build_aec_motion_corpus.py" and
                contract["generator_version"] == 2, "I002 measurement migration contract")
    elif task["lane"] == "governance":
        require(contract["candidate_limit"] == 0, "governance task candidate authority")
        require(task["id"] == "P001" and contract["phase"] == "governance-qualification" and
                contract["root_cause_id"] == "promotion-governance" and
                contract["policy"] == "docs/program/promotion-policy.json",
                "P001 governance contract")
    elif task["lane"] == "acoustic":
        require(task["id"] == "I003" and contract["phase"] == "candidate-selection" and
                contract["root_cause_id"] == "aec-motion-continuous-tracking",
                "I003 acoustic selection contract")
        require(contract["candidate_limit"] == 3 and contract["confirmation_limit"] == 0,
                "I003 bounded candidate/confirmation budget")
        require(contract["policy"] == "docs/program/promotion-policy.json" and
                contract["canonical_generator"] == "validation/tools/build_aec_motion_corpus.py" and
                contract["generator_version"] == 2 and contract["seconds"] == 4.0,
                "I003 generator/policy contract")
        require(contract["development_seeds"] == [4107, 4207] and
                contract["validation_seeds"] == [9107, 9207], "I003 frozen observed seed partitions")
        require(contract["selector_candidates"] == I003_CANDIDATES, "I003 frozen candidate set")
        require(contract["budget_before"] == {
                    "search_rounds_consumed": 1,
                    "candidate_variants_consumed": 9,
                    "confirmation_sets_consumed": 0,
                } and contract["budget_after_this_run"] == {
                    "search_rounds_consumed": 2,
                    "candidate_variants_consumed": 12,
                    "confirmation_sets_consumed": 0,
                }, "I003 inherited budget transition")
        require(contract["confirmation_source_group"] is None,
                "I003 selection cannot consume confirmation")
    else:
        raise ValueError("registered handler lane is not approved in this phase")


def validate(plan: dict, root: Path | None = None) -> None:
    keys(plan, {"schema_version", "phase", "product_qualification", "hardware_collection",
                "auto_promote", "max_parallel_candidates", "baseline", "data_roles", "tasks"})
    require(type(plan["schema_version"]) is int and plan["schema_version"] == 1, "schema")
    require(plan["phase"] == "software-public-data", "unapproved phase")
    require(plan["product_qualification"] == "DEFERRED_BY_SCOPE", "qualification boundary")
    require(plan["hardware_collection"] is False and plan["auto_promote"] is False,
            "hardware and automatic promotion are forbidden in this phase")
    require(type(plan["max_parallel_candidates"]) is int and plan["max_parallel_candidates"] == 1,
            "only one acoustic candidate at a time")
    baseline = plan["baseline"]
    keys(baseline, {"source_sha", "verify_url", "software_release", "release_url", "note"})
    require(sha(baseline["source_sha"]), "baseline must be an exact SHA")
    require(isinstance(baseline["verify_url"], str) and "/actions/runs/" in baseline["verify_url"],
            "baseline Verify URL")
    require(re.fullmatch(r"v\d+\.\d+\.\d+", baseline["software_release"]) is not None,
            "baseline release SemVer")
    require(isinstance(baseline["release_url"], str) and baseline["release_url"].endswith(
        "/releases/tag/" + baseline["software_release"]), "baseline release URL")

    require(isinstance(plan["data_roles"], list), "data_roles must be a list")
    seen_paths = set()
    for data in plan["data_roles"]:
        keys(data, {"path", "role", "exposed"})
        require(data["path"] not in seen_paths, "duplicate data authority")
        seen_paths.add(data["path"])
        require(type(data["exposed"]) is bool, "exposure must be explicit")
        require(data["role"] in {"development", "validation", "shadow", "regression",
                                 "hosted-regression", "confirmation", "promotion"}, "data role")
        require(not (data["exposed"] and data["role"] in {"confirmation", "promotion"}),
                "exposed data cannot be independent")
        if root is not None:
            repo_file(root, data["path"])

    tasks = plan["tasks"]
    require(isinstance(tasks, list) and tasks, "tasks must be nonempty")
    ids = [task["id"] for task in tasks]
    require(len(ids) == len(set(ids)), "duplicate task")
    by_id = {task["id"]: task for task in tasks}
    for task in tasks:
        keys(task, {"id", "priority", "status", "lane", "title", "depends_on", "handler",
                    "contract", "exit", "evidence"})
        require(re.fullmatch(r"[A-Z][0-9]{3}", task["id"]) is not None, "task ID")
        require(type(task["priority"]) is int and task["priority"] >= 0, "priority")
        require(task["status"] in STATES and task["lane"] in LANES, "task state/lane")
        require(bool(task["title"]) and bool(task["exit"]), "task requires title/exit")
        require(isinstance(task["depends_on"], list) and
                len(task["depends_on"]) == len(set(task["depends_on"])), "dependencies")
        require(all(dep in by_id and dep != task["id"] for dep in task["depends_on"]), "unknown dependency")
        require(isinstance(task["evidence"], list), "evidence list")
        if task["status"] == "CLOSED":
            require(bool(task["evidence"]), "CLOSED requires reviewed evidence pointers")
        for evidence in task["evidence"]:
            keys(evidence, {"source_sha", "url", "meaning"})
            require(sha(evidence["source_sha"]), "evidence exact SHA")
            require(isinstance(evidence["url"], str) and evidence["url"].startswith(
                "https://github.com/jiying2007/audio-pipeline/"), "evidence URL")
            require(bool(evidence["meaning"]), "evidence meaning")
        if task["lane"] == "external":
            require(task["status"] == "DEFERRED" and task["handler"] is None,
                    "product capture/qualification is deferred")
        if task["handler"] is not None:
            require(task["handler"] in HANDLERS, "unregistered handler")
            spec = HANDLERS[task["handler"]]
            require(task["status"] in {"READY", "ACTIVE", "REVIEW_REQUIRED"},
                    "handler on terminal/planned task")
            require(task["contract"] == spec["contract"], "handler contract path")
            if root is not None:
                repo_file(root, spec["path"])
                contract = json.loads(repo_file(root, task["contract"]).read_text())
                validate_contract(task, contract, spec)

    visiting, visited = set(), set()
    def walk(task_id: str) -> None:
        require(task_id not in visiting, "dependency cycle")
        if task_id in visited:
            return
        visiting.add(task_id)
        for dep in by_id[task_id]["depends_on"]:
            walk(dep)
        visiting.remove(task_id)
        visited.add(task_id)
    for task_id in ids:
        walk(task_id)


def next_task(plan: dict) -> dict | None:
    by_id = {task["id"]: task for task in plan["tasks"]}
    ready = [task for task in plan["tasks"] if task["status"] == "READY" and
             all(by_id[dep]["status"] == "CLOSED" for dep in task["depends_on"])]
    return min(ready, key=lambda task: (task["priority"], task["id"])) if ready else None


def view(plan: dict) -> dict:
    current = next_task(plan)
    return {"schema_version": 1, "phase": plan["phase"],
            "product_qualification": plan["product_qualification"],
            "authority": "committed-plan-index-not-execution-proof",
            "next_task": current["id"] if current else None,
            "automation_status": ("READY" if current["handler"] in HANDLERS else "BLOCKED_IMPLEMENTATION")
            if current else "NO_READY_TASK",
            "tasks": [{"id": item["id"], "status": item["status"], "title": item["title"]}
                      for item in plan["tasks"]]}


def self_test() -> None:
    plan = json.loads((ROOT / PLAN).read_text())
    validate(plan)
    by_id = {task["id"]: task for task in plan["tasks"]}
    i002, p001, i003 = by_id["I002"], by_id["P001"], by_id["I003"]
    require(i002["status"] == "CLOSED" and i002["handler"] is None and bool(i002["evidence"]),
            "I002 must remain reviewed and closed")
    require(p001["status"] == "CLOSED" and p001["handler"] is None and bool(p001["evidence"]),
            "P001 must remain reviewed and closed")

    if i003["status"] == "PLANNED":
        require(i003["handler"] is None and i003["contract"] is None,
                "planned I003 cannot have executable authority")
        require(next_task(plan) is None, "planned I003 cannot be next")
    elif i003["status"] == "READY":
        require(i003["handler"] == "aec-sync-selector-search" and
                i003["contract"] == "docs/program/iterations/I003.json",
                "I003 registered handler/contract")
        require(next_task(plan) is not None and next_task(plan)["id"] == "I003",
                "READY I003 must be next")
        require(view(plan)["automation_status"] == "READY", "I003 automation readiness")
    elif i003["status"] == "REVIEW_REQUIRED":
        require(i003["handler"] is None and bool(i003["evidence"]),
                "review-required I003 must be frozen and evidence-backed")
        require(next_task(plan) is None, "review-required I003 must not rerun automatically")
    elif i003["status"] == "CLOSED":
        require(i003["handler"] is None and bool(i003["evidence"]),
                "closed I003 must be terminal and evidence-backed")
        result = json.loads((ROOT / "docs/program/iterations/I003-confirmation-result.json").read_text())
        require(result["schema_version"] == 1 and result["iteration_id"] == "I003" and
                result["root_cause_id"] == "aec-motion-continuous-tracking" and
                result["result"] == "CLOSED_KEEP_BASELINE" and
                result["decision"] == "REJECT_CANDIDATE",
                "I003 CLOSED requires reviewed rejection result")
        require(result["candidate_version_not_released"] == "2.3.13" and
                result["authority_boundary"]["software_candidate_promoted"] is False and
                result["authority_boundary"]["release_created"] is False and
                result["authority_boundary"]["product_qualification"] == "DEFERRED_BY_SCOPE",
                "I003 rejection must preserve release/product boundary")
        confirmation = result["confirmation"]
        require(confirmation["workflow_run_id"] == 33976714064 and
                confirmation["artifact_id"] == 9972539010 and
                confirmation["budget_consumed"] == 1 and
                confirmation["source_group_next_role"] == "regression-retired" and
                confirmation["candidate_search_performed"] is False and
                confirmation["threshold_tuning_performed"] is False,
                "I003 rejection requires fixed-candidate confirmation evidence")
        require(result["aggregate"]["strict_improvement"] is False,
                "I003 rejection requires no independent strict improvement")
        policy = json.loads((ROOT / "docs/program/promotion-policy.json").read_text())
        budget = next(item for item in policy["research_budgets"]
                      if item["root_cause_id"] == "aec-motion-continuous-tracking")
        require(budget["confirmation_sets"] == {"limit": 2, "consumed": 1},
                "I003 CLOSED must preserve consumed confirmation budget")
        retired = next(item for item in policy["source_groups"]
                       if item["id"] == "aec-motion-geometry-v2-i003-confirmation-1-retired")
        require(retired["current_role"] == "regression" and
                "confirmation" in retired["prohibited_roles"] and
                "promotion" in retired["prohibited_roles"],
                "I003 CLOSED must retire confirmation source group")
        require(next_task(plan) is None, "closed I003 must not rerun automatically")
    else:
        raise AssertionError("I003 must be PLANNED, READY, REVIEW_REQUIRED or evidence-backed CLOSED")

    mutations = [
        lambda p: p.update(auto_promote=True),
        lambda p: p.update(hardware_collection=True),
        lambda p: p.update(product_qualification="PASS"),
        lambda p: p.update(unknown=True),
        lambda p: p["baseline"].update(source_sha="main"),
        lambda p: p["data_roles"][0].update(role="confirmation"),
        lambda p: p["tasks"][0].update(status="CLOSED", evidence=[]),
        lambda p: next(t for t in p["tasks"] if t["id"] == "I003").update(handler="shell"),
        lambda p: next(t for t in p["tasks"] if t["id"] == "I003").update(depends_on=["UNKNOWN"]),
        lambda p: p["tasks"][-1].update(status="READY"),
        lambda p: p["tasks"][0].update(depends_on=["I003"]),
    ]
    for mutate in mutations:
        bad = copy.deepcopy(plan)
        mutate(bad)
        try:
            validate(bad)
        except (ValueError, KeyError, TypeError, StopIteration):
            continue
        raise AssertionError("negative program case was accepted")

    blocked = copy.deepcopy(plan)
    by_id_blocked = {task["id"]: task for task in blocked["tasks"]}
    by_id_blocked["I003"].update(status="READY", handler=None, contract=None)
    require(view(blocked)["automation_status"] == "BLOCKED_IMPLEMENTATION",
            "missing I003 handler must block")
    by_id_blocked["I003"].update(depends_on=["I004"])
    require(next_task(blocked) is None, "unfinished dependency must block")
    print("program self-test: I002/P001 closed + bounded/evidence-backed I003 lifecycle and negative contracts OK")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", nargs="?", choices=["check", "next", "run"], default="check")
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0

    plan_path = ROOT / PLAN
    plan = json.loads(plan_path.read_text())
    validate(plan, ROOT)
    result = view(plan)
    result["plan_sha256"] = hashlib.sha256(plan_path.read_bytes()).hexdigest()
    if args.command == "run":
        require(args.output is not None, "run requires --output")
        output = args.output.resolve()
        require(not output.exists() or (output.is_dir() and not any(output.iterdir())), "output must be empty")
        output.mkdir(parents=True, exist_ok=True)
        (output / "plan-progress.json").write_text(json.dumps(result, indent=2) + "\n")
        task = next_task(plan)
        if task is None:
            print(json.dumps(result))
            return 0
        if task["handler"] not in HANDLERS:
            print(json.dumps(result))
            return 2
        spec = HANDLERS[task["handler"]]
        contract = json.loads((ROOT / task["contract"]).read_text())
        validate_contract(task, contract, spec)
        command = [sys.executable, str(ROOT / spec["path"]), "--contract", str(ROOT / task["contract"]),
                   "--output", str(output / "research")]
        result["execution_status"] = "FAILED"
        try:
            with (output / "execution.log").open("w") as log:
                process = subprocess.Popen(command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT,
                                           start_new_session=True)
                try:
                    code = process.wait(timeout=contract["run_timeout_seconds"])
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait()
                    raise
            result["execution_status"] = "COMPLETED" if code == 0 else "FAILED"
            result["returncode"] = code
        except subprocess.TimeoutExpired:
            result["execution_status"] = "TIMEOUT"
            result["returncode"] = 124
        finally:
            result["task_decision"] = spec["decision"]
            result["candidate_decision"] = spec["decision"]
            result["progress_transition"] = "REVIEW_REQUIRED_NOT_AUTOMATICALLY_CLOSED"
            (output / "execution-result.json").write_text(json.dumps(result, indent=2) + "\n")
        print(json.dumps(result))
        return result["returncode"]
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, KeyError, TypeError, OSError) as exc:
        print(f"program: {exc}", file=sys.stderr)
        raise SystemExit(1)
