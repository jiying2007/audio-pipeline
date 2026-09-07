#!/usr/bin/env python3
"""Validate that one-shot terminal program workflows stay retired and auditable."""
from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path

MANIFEST = Path("docs/program/terminal-workflow-retirement.json")
PLAN = Path("docs/program/plan.json")
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
EXPECTED_PATHS = {
    ".github/workflows/i007-closure.yml",
    ".github/workflows/i008-review-required.yml",
    ".github/workflows/i009-closure.yml",
    ".github/workflows/p002-candidate-zero-audit.yml",
    ".github/workflows/p002-closure.yml",
}
EXPECTED_TASKS = {"I007", "I008", "I009", "P002"}
FORBIDDEN_CONTINUOUS_TRIGGERS = ("workflow_call:", "workflow_run:", "schedule:", "push:")


def require(ok: bool, message: str) -> None:
    if not ok:
        raise ValueError(message)


def git(*args: str, check: bool = True) -> str:
    p = subprocess.run(["git", *args], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if check and p.returncode:
        raise RuntimeError((p.stderr or p.stdout).strip())
    return p.stdout.strip()


def validate_manifest(data: dict) -> None:
    require(data.get("schema_version") == 1, "unsupported retirement schema")
    require(data.get("policy") == "retired-terminal-workflow-set", "unexpected retirement policy")
    require(data.get("software_release") == "v2.3.13", "software release drift")
    require(data.get("release_source_sha") == "d70e18b12b899a67fa20adf3d281d10b901afbe8",
            "release source drift")
    require(data.get("reintroduction_allowed") is False, "retired workflows must not be reintroduced")
    require(data.get("retained_reproducers") is True, "reproducer retention contract missing")
    records = data.get("workflows")
    require(isinstance(records, list) and len(records) == 5, "expected exactly five retired workflows")
    require({r.get("path") for r in records} == EXPECTED_PATHS, "retired workflow set drift")
    require({r.get("task_id") for r in records} == EXPECTED_TASKS, "terminal task set drift")
    for r in records:
        require(set(r) == {"path", "blob_sha", "task_id", "terminal_evidence", "reason"},
                f"retirement record fields drift: {r.get('path')}")
        require(SHA_RE.fullmatch(str(r["blob_sha"])) is not None, f"invalid blob SHA: {r['path']}")
        require(isinstance(r["reason"], str) and r["reason"], f"missing reason: {r['path']}")
    require(data.get("authority_boundary") == {
        "shipping_source_changed": False,
        "release_changed": False,
        "hardware_test_executed": False,
        "hardware_collection_performed": False,
        "product_qualification": "DEFERRED_BY_SCOPE",
        "dut_hil": "DEFERRED_BY_SCOPE",
    }, "retirement cannot gain release/hardware/PQ authority")


def extract_on_block(text: str) -> str:
    lines = text.splitlines()
    start = next((i for i, line in enumerate(lines) if line == "on:"), None)
    require(start is not None, "workflow has no on block")
    out = []
    for line in lines[start + 1:]:
        if line and not line.startswith((" ", "\t")):
            break
        out.append(line)
    return "\n".join(out)


def check(root: Path) -> dict:
    data = json.loads((root / MANIFEST).read_text(encoding="utf-8"))
    validate_manifest(data)
    plan = json.loads((root / PLAN).read_text(encoding="utf-8"))
    require(plan.get("phase") == "software-public-data", "program phase drift")
    require(plan.get("product_qualification") == "DEFERRED_BY_SCOPE", "PQ boundary drift")
    require(plan.get("hardware_collection") is False and plan.get("auto_promote") is False,
            "hardware/auto-promotion boundary drift")
    baseline = plan.get("baseline", {})
    require(baseline.get("software_release") == data["software_release"], "baseline release mismatch")
    require(baseline.get("source_sha") == data["release_source_sha"], "baseline source mismatch")
    tasks = {t["id"]: t for t in plan.get("tasks", [])}

    checked = []
    for r in data["workflows"]:
        path = root / r["path"]
        require(not path.exists(), f"retired workflow was reintroduced: {r['path']}")
        task = tasks.get(r["task_id"])
        require(task is not None, f"task missing: {r['task_id']}")
        require(task.get("status") == "CLOSED", f"task no longer terminal: {r['task_id']}")
        require(task.get("handler") is None, f"terminal task regained handler: {r['task_id']}")
        evidence = root / r["terminal_evidence"]
        require(evidence.is_file(), f"terminal evidence missing: {r['terminal_evidence']}")
        require(git("cat-file", "-t", r["blob_sha"]) == "blob", f"historical workflow blob missing: {r['path']}")
        text = git("cat-file", "blob", r["blob_sha"])
        on_block = extract_on_block(text)
        require("pull_request:" in on_block, f"retired workflow was not PR-scoped: {r['path']}")
        require(not any(trigger in on_block for trigger in FORBIDDEN_CONTINUOUS_TRIGGERS),
                f"retired workflow had a continuous/reusable trigger: {r['path']}")
        checked.append({"path": r["path"], "blob_sha": r["blob_sha"], "task_id": r["task_id"]})

    return {
        "schema_version": 1,
        "result": "TERMINAL_WORKFLOW_RETIREMENT_PASS",
        "retired_workflows": len(checked),
        "tasks": sorted(EXPECTED_TASKS),
        "software_release": data["software_release"],
        "release_source_sha": data["release_source_sha"],
        "product_qualification": "DEFERRED_BY_SCOPE",
        "checked": checked,
    }


def self_test() -> None:
    sample = {
        "schema_version": 1,
        "policy": "retired-terminal-workflow-set",
        "software_release": "v2.3.13",
        "release_source_sha": "d70e18b12b899a67fa20adf3d281d10b901afbe8",
        "reintroduction_allowed": False,
        "retained_reproducers": True,
        "workflows": [
            {"path": p, "blob_sha": "a" * 40, "task_id": t, "terminal_evidence": "x.json", "reason": "terminal"}
            for p, t in [
                (".github/workflows/i007-closure.yml", "I007"),
                (".github/workflows/i008-review-required.yml", "I008"),
                (".github/workflows/i009-closure.yml", "I009"),
                (".github/workflows/p002-candidate-zero-audit.yml", "P002"),
                (".github/workflows/p002-closure.yml", "P002"),
            ]
        ],
        "authority_boundary": {
            "shipping_source_changed": False,
            "release_changed": False,
            "hardware_test_executed": False,
            "hardware_collection_performed": False,
            "product_qualification": "DEFERRED_BY_SCOPE",
            "dut_hil": "DEFERRED_BY_SCOPE",
        },
    }
    validate_manifest(sample)
    assert "pull_request:" in extract_on_block("name: X\non:\n  pull_request:\npermissions:\n  contents: read\n")
    bad = json.loads(json.dumps(sample))
    bad["reintroduction_allowed"] = True
    try:
        validate_manifest(bad)
    except ValueError:
        pass
    else:
        raise AssertionError("unsafe retirement manifest accepted")
    print("terminal workflow retirement self-test: OK")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
    if args.check:
        print(json.dumps(check(Path.cwd()), indent=2, sort_keys=True))
    if not args.self_test and not args.check:
        parser.error("choose --self-test and/or --check")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
