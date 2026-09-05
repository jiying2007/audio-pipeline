#!/usr/bin/env python3
"""Validate the committed software/public-data program and run registered work.

This orchestrator is not an acoustic evaluator, optimizer, promotion authority,
or product-certification substitute. A successful registered execution only
means the task ran to completion and still requires evidence review.
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
HANDLERS = {
    "aec-motion-model-qualification": {
        "path": "tests/validation/aec_motion_model_qualification.py",
        "contract": "docs/program/iterations/I002.json",
        "iteration_id": "I002",
        "decision": "NOT_AN_ACOUSTIC_CANDIDATE",
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
    require(task["lane"] == "measurement", "registered handlers are measurement-only in this phase")
    require(task["contract"] == spec["contract"] and contract["iteration_id"] == spec["iteration_id"] == task["id"],
            "handler/contract identity")
    require(sha(contract["base_sha"]), "contract base SHA")
    require(contract["data_role"] == "development" and contract["promotion_allowed"] is False and
            contract["candidate_limit"] == 0 and contract["confirmation_limit"] == 0,
            "measurement task cannot acquire candidate/confirmation authority")
    require(type(contract["run_timeout_seconds"]) is int and 1 <= contract["run_timeout_seconds"] <= 900,
            "timeout budget")
    require(len(contract["seeds"]) == 3 and len(set(contract["seeds"])) == 3 and
            all(type(seed) is int and 0 <= seed < 2 ** 32 for seed in contract["seeds"]), "seed budget")
    if task["id"] == "I002":
        require(contract["phase"] == "measurement-migration" and
                contract["canonical_generator"] == "validation/tools/build_aec_motion_corpus.py" and
                contract["generator_version"] == 2, "I002 measurement migration contract")


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
    require(sha(plan["baseline"]["source_sha"]), "baseline must be an exact SHA")
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
            require(task["status"] in {"READY", "ACTIVE", "REVIEW_REQUIRED"}, "handler on terminal/planned task")
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
    task = next_task(plan)
    return {"schema_version": 1, "phase": plan["phase"],
            "product_qualification": plan["product_qualification"],
            "authority": "committed-plan-index-not-execution-proof",
            "next_task": task["id"] if task else None,
            "automation_status": ("READY" if task["handler"] in HANDLERS else "BLOCKED_IMPLEMENTATION")
            if task else "NO_READY_TASK",
            "tasks": [{"id": task["id"], "status": task["status"], "title": task["title"]}
                      for task in plan["tasks"]]}


def self_test() -> None:
    plan = json.loads((ROOT / PLAN).read_text())
    validate(plan)
    require(next_task(plan) is not None and next_task(plan)["id"] == "I002", "I002 must be next reviewed task")
    require(view(plan)["automation_status"] == "READY", "I002 handler must be registered")
    mutations = [
        lambda p: p.update(auto_promote=True),
        lambda p: p.update(hardware_collection=True),
        lambda p: p.update(product_qualification="PASS"),
        lambda p: p.update(unknown=True),
        lambda p: p["baseline"].update(source_sha="main"),
        lambda p: p["data_roles"][0].update(role="confirmation"),
        lambda p: p["tasks"][0].update(status="CLOSED", evidence=[]),
        lambda p: p["tasks"][2].update(handler="shell"),
        lambda p: p["tasks"][2].update(depends_on=["UNKNOWN"]),
        lambda p: p["tasks"][-1].update(status="READY"),
        lambda p: p["tasks"][0].update(depends_on=["P001"]),
    ]
    for mutate in mutations:
        bad = copy.deepcopy(plan)
        mutate(bad)
        try:
            validate(bad)
        except (ValueError, KeyError, TypeError):
            continue
        raise AssertionError("negative program case was accepted")
    blocked = copy.deepcopy(plan)
    for task in blocked["tasks"]:
        if task["status"] == "READY":
            task["status"] = "PLANNED"
            task["handler"] = None
            task["contract"] = None
    blocked["tasks"][4].update(status="READY", handler=None, contract=None)
    require(view(blocked)["automation_status"] == "BLOCKED_IMPLEMENTATION", "missing handler must block")
    blocked["tasks"][4]["depends_on"] = ["I002"]
    require(next_task(blocked) is None, "unfinished dependency must block")
    print("program self-test: I002 readiness plus positive/negative governance contracts OK")


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
