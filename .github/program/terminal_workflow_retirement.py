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
WORKFLOW_DIR = Path(".github/workflows")
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
TASK_WORKFLOW_RE = re.compile(r"^(?P<task>[ip]\d{3})-.*\.ya?ml$", re.IGNORECASE)
EXPECTED_PATHS = {
    ".github/workflows/i004-ns-baseline-diagnostic.yml",
    ".github/workflows/i004-ns-burst-candidate-search.yml",
    ".github/workflows/i004-ns-root-cause-differential.yml",
    ".github/workflows/i005-vad-baseline.yml",
    ".github/workflows/i005-vad-source-admission.yml",
    ".github/workflows/i006-agc-baseline.yml",
    ".github/workflows/i006-agc-root-cause-differential.yml",
    ".github/workflows/i007-bf-health-baseline.yml",
    ".github/workflows/i007-bf-health-root-cause.yml",
    ".github/workflows/i007-closure.yml",
    ".github/workflows/i008-review-required.yml",
    ".github/workflows/i009-activity-doubletalk-baseline.yml",
    ".github/workflows/i009-echo-normalized-root-cause.yml",
    ".github/workflows/i009-residual-echo-rescue-root-cause.yml",
    ".github/workflows/i009-closure.yml",
    ".github/workflows/p002-candidate-zero-audit.yml",
    ".github/workflows/p002-closure.yml",
}
EXPECTED_TASKS = {"I004", "I005", "I006", "I007", "I008", "I009", "P002"}
FORBIDDEN_CONTINUOUS_TRIGGERS = ("workflow_call:", "workflow_run:", "schedule:", "push:")
RESEARCH_FORBIDDEN_TRIGGERS = ("workflow_call:", "workflow_run:", "schedule:", "workflow_dispatch:")
RESEARCH_AUTHORITY_FALSE_KEYS = (
    "candidate_selection",
    "tuning",
    "automatic_main_mutation",
    "shipping",
    "hil",
    "product_certification",
)
SOURCE_CANDIDATE_AUTHORITY_FALSE_KEYS = (
    "shipping_authority",
    "target_execution_authority",
    "hil_authority",
    "product_certification_authority",
    "source_merge_authority",
    "automatic_main_mutation",
)


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
    require(isinstance(records, list) and len(records) == len(EXPECTED_PATHS),
            f"expected exactly {len(EXPECTED_PATHS)} retired workflows")
    require({r.get("path") for r in records} == EXPECTED_PATHS, "retired workflow set drift")
    require({r.get("task_id") for r in records} == EXPECTED_TASKS, "terminal task set drift")
    require(len({r.get("blob_sha") for r in records}) == len(records), "retired workflow blob SHA reused")
    for r in records:
        require(set(r) == {"path", "blob_sha", "task_id", "terminal_evidence", "reason"},
                f"retirement record fields drift: {r.get('path')}")
        require(str(r["path"]).startswith(".github/workflows/"), f"invalid workflow path: {r['path']}")
        require(SHA_RE.fullmatch(str(r["blob_sha"])) is not None, f"invalid blob SHA: {r['path']}")
        require(isinstance(r["reason"], str) and r["reason"], f"missing reason: {r['path']}")

    research_records = data.get("research_workflows", [])
    require(isinstance(research_records, list), "research_workflows must be a list")
    seen_paths = {r["path"] for r in records}
    seen_blobs = {r["blob_sha"] for r in records}
    for r in research_records:
        require(set(r) == {"path", "blob_sha", "investigation_id", "evidence", "reason"},
                f"research retirement record fields drift: {r.get('path')}")
        path = str(r["path"])
        blob = str(r["blob_sha"])
        investigation = r["investigation_id"]
        evidence = r["evidence"]
        require(path.startswith(".github/workflows/"), f"invalid research workflow path: {path}")
        require(path not in seen_paths, f"duplicate retired workflow path: {path}")
        require(SHA_RE.fullmatch(blob) is not None, f"invalid research workflow blob SHA: {path}")
        require(blob not in seen_blobs, f"retired workflow blob SHA reused: {path}")
        require(isinstance(investigation, str) and investigation,
                f"research investigation id missing: {path}")
        require(isinstance(evidence, str) and evidence.startswith(".github/research/"),
                f"research evidence path invalid: {path}")
        require(isinstance(r["reason"], str) and r["reason"], f"missing research reason: {path}")
        seen_paths.add(path)
        seen_blobs.add(blob)

    source_candidate_records = data.get("source_candidate_workflows", [])
    require(isinstance(source_candidate_records, list),
            "source_candidate_workflows must be a list")
    for r in source_candidate_records:
        require(set(r) == {"path", "blob_sha", "candidate_id", "evidence", "reason"},
                f"source-candidate retirement record fields drift: {r.get('path')}")
        path = str(r["path"])
        blob = str(r["blob_sha"])
        candidate_id = r["candidate_id"]
        evidence = r["evidence"]
        require(path.startswith(".github/workflows/"),
                f"invalid source-candidate workflow path: {path}")
        require(path not in seen_paths, f"duplicate retired workflow path: {path}")
        require(SHA_RE.fullmatch(blob) is not None,
                f"invalid source-candidate workflow blob SHA: {path}")
        require(blob not in seen_blobs, f"retired workflow blob SHA reused: {path}")
        require(isinstance(candidate_id, str) and candidate_id,
                f"source-candidate id missing: {path}")
        require(isinstance(evidence, str) and evidence.startswith(".github/research/"),
                f"source-candidate evidence path invalid: {path}")
        require(isinstance(r["reason"], str) and r["reason"],
                f"missing source-candidate reason: {path}")
        seen_paths.add(path)
        seen_blobs.add(blob)

    selection_records = data.get("selection_workflows", [])
    require(isinstance(selection_records, list),
            "selection_workflows must be a list")
    for r in selection_records:
        require(set(r) == {
            "path", "blob_sha", "selection_id", "evidence",
            "successor", "terminal_evidence", "reason"
        }, f"selection retirement record fields drift: {r.get('path')}")
        path = str(r["path"])
        blob = str(r["blob_sha"])
        selection_id = r["selection_id"]
        require(path.startswith(".github/workflows/"),
                f"invalid selection workflow path: {path}")
        require(path not in seen_paths, f"duplicate retired workflow path: {path}")
        require(SHA_RE.fullmatch(blob) is not None,
                f"invalid selection workflow blob SHA: {path}")
        require(blob not in seen_blobs, f"retired workflow blob SHA reused: {path}")
        require(isinstance(selection_id, str) and selection_id,
                f"selection id missing: {path}")
        for key in ("evidence", "successor", "terminal_evidence"):
            value = r[key]
            require(isinstance(value, str) and value.startswith(".github/research/"),
                    f"selection {key} path invalid: {path}")
        require(isinstance(r["reason"], str) and r["reason"],
                f"missing selection reason: {path}")
        seen_paths.add(path)
        seen_blobs.add(blob)

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

    research_checked = []
    for r in data.get("research_workflows", []):
        path = root / r["path"]
        require(not path.exists(), f"retired research workflow was reintroduced: {r['path']}")
        evidence_path = root / r["evidence"]
        require(evidence_path.is_file(), f"research terminal evidence missing: {r['evidence']}")
        evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
        require(evidence.get("investigation_id") == r["investigation_id"],
                f"research investigation identity drift: {r['path']}")
        require(evidence.get("candidate_budget") == 0,
                f"retired research investigation regained candidate budget: {r['path']}")
        status = evidence.get("status")
        if status == "DIAGNOSTIC_ONLY":
            predecessor = evidence.get("predecessor") or {}
            require(predecessor.get("fresh_main_closed") is True,
                    f"research diagnostic is not fresh-main closed: {r['path']}")
        elif status == "CLOSED_DIAGNOSTIC_PLATEAU":
            closure = evidence.get("fresh_main_closure") or {}
            require(closure.get("fresh_main_closed") is True,
                    f"research plateau is not fresh-main closed: {r['path']}")
        else:
            raise ValueError(f"research workflow is not terminal diagnostic evidence: {r['path']}={status}")

        authority = evidence.get("output_authority") or {}
        require(authority.get("research_diagnostic_only") is True,
                f"retired research investigation lost diagnostic-only authority: {r['path']}")
        for key in RESEARCH_AUTHORITY_FALSE_KEYS:
            require(authority.get(key) is False,
                    f"retired research investigation regained {key} authority: {r['path']}")

        require(git("cat-file", "-t", r["blob_sha"]) == "blob",
                f"historical research workflow blob missing: {r['path']}")
        text = git("cat-file", "blob", r["blob_sha"])
        on_block = extract_on_block(text)
        require("pull_request:" in on_block and "push:" in on_block,
                f"retired research workflow must preserve PR + fresh-main push lineage: {r['path']}")
        require(not any(trigger in on_block for trigger in RESEARCH_FORBIDDEN_TRIGGERS),
                f"retired research workflow had reusable/scheduled/manual trigger: {r['path']}")
        research_checked.append({
            "path": r["path"],
            "blob_sha": r["blob_sha"],
            "investigation_id": r["investigation_id"],
            "evidence": r["evidence"],
        })

    source_candidate_checked = []
    for r in data.get("source_candidate_workflows", []):
        path = root / r["path"]
        require(not path.exists(),
                f"retired source-candidate workflow was reintroduced: {r['path']}")
        evidence_path = root / r["evidence"]
        require(evidence_path.is_file(),
                f"source-candidate terminal evidence missing: {r['evidence']}")
        evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
        require(evidence.get("candidate_id") == r["candidate_id"],
                f"source-candidate identity drift: {r['path']}")
        require(evidence.get("status") == "CLOSED_TERMINAL_SOURCE_CANDIDATE_REJECT",
                f"source-candidate is not terminally rejected: {r['path']}")
        require(evidence.get("terminal_candidate") is True,
                f"source-candidate lost terminal flag: {r['path']}")
        require(evidence.get("candidate_budget") == 0,
                f"source-candidate regained candidate budget: {r['path']}")
        require(evidence.get("confirmation_limit") == 0,
                f"source-candidate regained confirmation budget: {r['path']}")
        authority = evidence.get("output_authority") or {}
        for key in SOURCE_CANDIDATE_AUTHORITY_FALSE_KEYS:
            require(authority.get(key) is False,
                    f"source-candidate regained {key}: {r['path']}")

        require(git("cat-file", "-t", r["blob_sha"]) == "blob",
                f"historical source-candidate workflow blob missing: {r['path']}")
        text = git("cat-file", "blob", r["blob_sha"])
        on_block = extract_on_block(text)
        require("pull_request:" in on_block and "workflow_dispatch:" in on_block,
                f"retired source-candidate workflow must preserve PR + manual lineage: {r['path']}")
        for forbidden in ("push:", "schedule:", "workflow_call:", "workflow_run:"):
            require(forbidden not in on_block,
                    f"retired source-candidate workflow had forbidden trigger {forbidden}: {r['path']}")
        source_candidate_checked.append({
            "path": r["path"],
            "blob_sha": r["blob_sha"],
            "candidate_id": r["candidate_id"],
            "evidence": r["evidence"],
        })

    selection_checked = []
    for r in data.get("selection_workflows", []):
        path = root / r["path"]
        require(not path.exists(),
                f"retired selection workflow was reintroduced: {r['path']}")
        evidence_path = root / r["evidence"]
        successor_path = root / r["successor"]
        terminal_path = root / r["terminal_evidence"]
        for label, item in (
            ("selection evidence", evidence_path),
            ("selection successor", successor_path),
            ("selection terminal evidence", terminal_path),
        ):
            require(item.is_file(), f"{label} missing: {item.relative_to(root)}")

        evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
        successor = json.loads(successor_path.read_text(encoding="utf-8"))
        terminal = json.loads(terminal_path.read_text(encoding="utf-8"))
        selection_id = r["selection_id"]

        require(evidence.get("hypothesis_id") == selection_id,
                f"selection identity drift: {r['path']}")
        require(evidence.get("authority") == "development-selection-only",
                f"selection authority drift: {r['path']}")
        require(evidence.get("event") == "workflow_dispatch"
                and evidence.get("conclusion") == "success",
                f"selection evidence is not a completed manual run: {r['path']}")
        require(evidence.get("decision") == "FROZEN_STAGE_RESEARCH_CANDIDATE",
                f"selection did not freeze a downstream candidate: {r['path']}")
        feedback = evidence.get("feedback_boundary") or {}
        require(feedback.get("development_selected") is True
                and feedback.get("validation_and_shadow_reject_only") is True
                and feedback.get("consumed_public_authority_used") is False
                and feedback.get("old_confirmation_seeds_used") is False,
                f"selection feedback boundary drift: {r['path']}")
        promotion = evidence.get("promotion") or {}
        for key in (
            "source_merge_authorized", "shipping", "hil",
            "product_certification", "automatic_main_mutation"
        ):
            require(promotion.get(key) is False,
                    f"selection regained {key}: {r['path']}")

        predecessor = successor.get("predecessor") or {}
        artifact = evidence.get("artifact") or {}
        selected = evidence.get("selected") or {}
        require(successor.get("candidate_id") == selection_id,
                f"selection successor identity drift: {r['path']}")
        require(predecessor.get("lane_run_id") == evidence.get("run_id"),
                f"selection run was not consumed by successor: {r['path']}")
        require(predecessor.get("lane_artifact_id") == artifact.get("id")
                and predecessor.get("lane_artifact_digest") == artifact.get("digest"),
                f"selection artifact was not consumed exactly: {r['path']}")
        require(predecessor.get("variant_id") == selected.get("variant_id"),
                f"selected variant drifted in successor: {r['path']}")
        require(successor.get("status") == "CLOSED_TERMINAL_SOURCE_CANDIDATE_REJECT"
                and successor.get("terminal_candidate") is True
                and successor.get("candidate_budget") == 0
                and successor.get("confirmation_limit") == 0,
                f"selection successor is not terminal: {r['path']}")
        require(successor.get("closure_path") == r["terminal_evidence"],
                f"selection successor closure path drift: {r['path']}")

        terminal_predecessor = terminal.get("predecessor") or {}
        require(terminal.get("candidate_id") == selection_id,
                f"selection terminal identity drift: {r['path']}")
        require(terminal.get("status") == "CLOSED_TERMINAL_SOURCE_CANDIDATE_REJECT"
                and terminal.get("terminal_candidate") is True
                and terminal.get("candidate_budget") == 0
                and terminal.get("confirmation_limit") == 0,
                f"selection terminal evidence is not closed: {r['path']}")
        require(terminal_predecessor.get("lane_run_id") == evidence.get("run_id")
                and terminal_predecessor.get("lane_decision") == evidence.get("decision")
                and terminal_predecessor.get("selected_variant_id") == selected.get("variant_id"),
                f"selection terminal lineage drift: {r['path']}")

        require(git("cat-file", "-t", r["blob_sha"]) == "blob",
                f"historical selection workflow blob missing: {r['path']}")
        text = git("cat-file", "blob", r["blob_sha"])
        on_block = extract_on_block(text)
        require("pull_request:" in on_block and "workflow_dispatch:" in on_block,
                f"retired selection workflow must preserve PR + manual lineage: {r['path']}")
        for forbidden in ("push:", "schedule:", "workflow_call:", "workflow_run:"):
            require(forbidden not in on_block,
                    f"retired selection workflow had forbidden trigger {forbidden}: {r['path']}")
        selection_checked.append({
            "path": r["path"],
            "blob_sha": r["blob_sha"],
            "selection_id": selection_id,
            "evidence": r["evidence"],
            "successor": r["successor"],
            "terminal_evidence": r["terminal_evidence"],
        })

    # A terminal research task must not regain a standalone Actions entry under its task prefix.
    # Reproducers/contracts/results stay in the repository; only the consumed orchestration entry is retired.
    for pattern in ("*.yml", "*.yaml"):
        for path in sorted((root / WORKFLOW_DIR).glob(pattern)):
            match = TASK_WORKFLOW_RE.fullmatch(path.name)
            if not match:
                continue
            task_id = match.group("task").upper()
            task = tasks.get(task_id)
            if task and task.get("status") == "CLOSED":
                raise ValueError(f"live standalone workflow remains for CLOSED task {task_id}: {path.relative_to(root)}")

    return {
        "schema_version": 1,
        "result": "TERMINAL_WORKFLOW_RETIREMENT_PASS",
        "retired_workflows": len(checked),
        "retired_research_workflows": len(research_checked),
        "retired_source_candidate_workflows": len(source_candidate_checked),
        "retired_selection_workflows": len(selection_checked),
        "tasks": sorted(EXPECTED_TASKS),
        "research_investigations": sorted(item["investigation_id"] for item in research_checked),
        "source_candidates": sorted(item["candidate_id"] for item in source_candidate_checked),
        "selection_ids": sorted(item["selection_id"] for item in selection_checked),
        "software_release": data["software_release"],
        "release_source_sha": data["release_source_sha"],
        "product_qualification": "DEFERRED_BY_SCOPE",
        "checked": checked,
    }


def self_test() -> None:
    pairs = [
        (".github/workflows/i004-ns-baseline-diagnostic.yml", "I004"),
        (".github/workflows/i004-ns-burst-candidate-search.yml", "I004"),
        (".github/workflows/i004-ns-root-cause-differential.yml", "I004"),
        (".github/workflows/i005-vad-baseline.yml", "I005"),
        (".github/workflows/i005-vad-source-admission.yml", "I005"),
        (".github/workflows/i006-agc-baseline.yml", "I006"),
        (".github/workflows/i006-agc-root-cause-differential.yml", "I006"),
        (".github/workflows/i007-bf-health-baseline.yml", "I007"),
        (".github/workflows/i007-bf-health-root-cause.yml", "I007"),
        (".github/workflows/i007-closure.yml", "I007"),
        (".github/workflows/i008-review-required.yml", "I008"),
        (".github/workflows/i009-activity-doubletalk-baseline.yml", "I009"),
        (".github/workflows/i009-echo-normalized-root-cause.yml", "I009"),
        (".github/workflows/i009-residual-echo-rescue-root-cause.yml", "I009"),
        (".github/workflows/i009-closure.yml", "I009"),
        (".github/workflows/p002-candidate-zero-audit.yml", "P002"),
        (".github/workflows/p002-closure.yml", "P002"),
    ]
    sample = {
        "schema_version": 1,
        "policy": "retired-terminal-workflow-set",
        "software_release": "v2.3.13",
        "release_source_sha": "d70e18b12b899a67fa20adf3d281d10b901afbe8",
        "reintroduction_allowed": False,
        "retained_reproducers": True,
        "workflows": [
            {"path": p, "blob_sha": f"{index + 1:040x}", "task_id": t,
             "terminal_evidence": "x.json", "reason": "terminal"}
            for index, (p, t) in enumerate(pairs)
        ],
        "research_workflows": [],
        "source_candidate_workflows": [],
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
    research_sample = json.loads(json.dumps(sample))
    research_sample["research_workflows"] = [{
        "path": ".github/workflows/research-example.yml",
        "blob_sha": "f" * 40,
        "investigation_id": "research-example-v1",
        "evidence": ".github/research/example.json",
        "reason": "terminal research diagnostic",
    }]
    validate_manifest(research_sample)
    source_sample = json.loads(json.dumps(sample))
    source_sample["source_candidate_workflows"] = [{
        "path": ".github/workflows/research-source-candidate-example.yml",
        "blob_sha": "e" * 40,
        "candidate_id": "source-candidate-example-v1",
        "evidence": ".github/research/source-candidate-example-closure.json",
        "reason": "terminal source candidate",
    }]
    validate_manifest(source_sample)
    selection_sample = json.loads(json.dumps(sample))
    selection_sample["selection_workflows"] = [{
        "path": ".github/workflows/research-selection-example.yml",
        "blob_sha": "d" * 40,
        "selection_id": "selection-example-v1",
        "evidence": ".github/research/selection-example-run.json",
        "successor": ".github/research/source-candidates/selection-example-v1.json",
        "terminal_evidence": ".github/research/confirmations/selection-example-v1-closure.json",
        "reason": "consumed selection with terminal downstream candidate",
    }]
    validate_manifest(selection_sample)
    assert "pull_request:" in extract_on_block("name: X\non:\n  pull_request:\npermissions:\n  contents: read\n")
    assert TASK_WORKFLOW_RE.fullmatch("i009-residual-echo-rescue-root-cause.yml")
    assert not TASK_WORKFLOW_RE.fullmatch("audio-quality-gates.yml")
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
