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
    ".github/workflows/i010-ns-vad-observation-domain.yml",
    ".github/workflows/p002-candidate-zero-audit.yml",
    ".github/workflows/p002-closure.yml",
}
EXPECTED_TASKS = {"I004", "I005", "I006", "I007", "I008", "I009", "I010", "P002"}
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
RETIREMENT_COLLECTION_KEYS = {
    "workflows",
    "research_workflows",
    "source_candidate_workflows",
    "selection_workflows",
    "source_candidate_rounds",
    "stage_lane_rounds",
    "historical_replay_workflows",
}
MANIFEST_KEYS = RETIREMENT_COLLECTION_KEYS | {
    "schema_version",
    "policy",
    "software_release",
    "release_source_sha",
    "reintroduction_allowed",
    "retained_reproducers",
    "authority_boundary",
}


def require(ok: bool, message: str) -> None:
    if not ok:
        raise ValueError(message)


def git(*args: str, check: bool = True) -> str:
    p = subprocess.run(["git", *args], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if check and p.returncode:
        raise RuntimeError((p.stderr or p.stdout).strip())
    return p.stdout.strip()


def validate_manifest(data: dict) -> None:
    require(set(data) == MANIFEST_KEYS,
            f"retirement manifest top-level fields drift: {sorted(set(data) ^ MANIFEST_KEYS)}")
    require({
        key for key, value in data.items() if isinstance(value, list)
    } == RETIREMENT_COLLECTION_KEYS,
            "retirement manifest collection categories drift")
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

    round_records = data.get("source_candidate_rounds", [])
    require(isinstance(round_records, list), "source_candidate_rounds must be a list")
    for r in round_records:
        require(set(r) == {
            "round_id", "workflows", "round_closure", "candidate_contracts",
            "candidate_closures", "reason"
        }, f"source-candidate round fields drift: {r.get('round_id')}")
        require(isinstance(r["round_id"], str) and r["round_id"],
                "source-candidate round id missing")
        workflows = r["workflows"]
        require(isinstance(workflows, list) and workflows,
                f"source-candidate round workflows missing: {r['round_id']}")
        stages = set()
        for item in workflows:
            require(set(item) == {"path", "blob_sha", "stage", "evidence"},
                    f"source-candidate round workflow fields drift: {r['round_id']}")
            path = str(item["path"])
            blob = str(item["blob_sha"])
            stage = item["stage"]
            evidence = item["evidence"]
            require(path.startswith(".github/workflows/"),
                    f"invalid source-candidate round workflow path: {path}")
            require(path not in seen_paths, f"duplicate retired workflow path: {path}")
            require(SHA_RE.fullmatch(blob) is not None,
                    f"invalid source-candidate round workflow blob SHA: {path}")
            require(blob not in seen_blobs, f"retired workflow blob SHA reused: {path}")
            require(isinstance(stage, str) and stage and stage not in stages,
                    f"invalid/duplicate source-candidate round stage: {stage}")
            require(isinstance(evidence, str) and evidence.startswith(".github/research/"),
                    f"source-candidate round evidence path invalid: {path}")
            stages.add(stage)
            seen_paths.add(path)
            seen_blobs.add(blob)
        require(stages == {
            "source-candidate-evaluation",
            "independent-source-confirmation",
            "vad-public-confirmation",
        }, f"unexpected source-candidate round stages: {r['round_id']}={sorted(stages)}")
        require(isinstance(r["round_closure"], str)
                and r["round_closure"].startswith(".github/research/"),
                f"invalid source-candidate round closure: {r['round_id']}")
        contracts = r["candidate_contracts"]
        require(isinstance(contracts, dict) and set(contracts) == {
            "vad-confidence-tiered-hold-v1",
            "agc-error-adaptive-release-v1",
        }, f"unexpected source-candidate contract set: {r['round_id']}")
        for candidate_id, evidence in contracts.items():
            require(isinstance(evidence, str) and evidence.startswith(".github/research/"),
                    f"invalid candidate contract path: {candidate_id}")
        closures = r["candidate_closures"]
        require(isinstance(closures, dict) and set(closures) == set(contracts),
                f"source-candidate contract/closure set mismatch: {r['round_id']}")
        for candidate_id, evidence in closures.items():
            require(isinstance(evidence, str) and evidence.startswith(".github/research/"),
                    f"invalid candidate closure path: {candidate_id}")
        require(isinstance(r["reason"], str) and r["reason"],
                f"missing source-candidate round reason: {r['round_id']}")

    stage_lane_records = data.get("stage_lane_rounds", [])
    require(isinstance(stage_lane_records, list), "stage_lane_rounds must be a list")
    for r in stage_lane_records:
        require(set(r) == {
            "round_id", "path", "blob_sha", "evidence", "lane_outcomes", "reason"
        }, f"stage-lane round fields drift: {r.get('round_id')}")
        round_id = r["round_id"]
        path = str(r["path"])
        blob = str(r["blob_sha"])
        evidence = r["evidence"]
        require(isinstance(round_id, str) and round_id,
                "stage-lane round id missing")
        require(path.startswith(".github/workflows/"),
                f"invalid stage-lane workflow path: {path}")
        require(path not in seen_paths, f"duplicate retired workflow path: {path}")
        require(SHA_RE.fullmatch(blob) is not None,
                f"invalid stage-lane workflow blob SHA: {path}")
        require(blob not in seen_blobs, f"retired workflow blob SHA reused: {path}")
        require(isinstance(evidence, str) and evidence.startswith(".github/research/"),
                f"stage-lane evidence path invalid: {path}")
        lane_outcomes = r["lane_outcomes"]
        require(isinstance(lane_outcomes, dict) and set(lane_outcomes) == {
            "bf", "ns", "vad", "agc"
        }, f"unexpected stage-lane outcome set: {round_id}")
        for lane_id, outcome in lane_outcomes.items():
            require(isinstance(outcome, str) and outcome.startswith(".github/research/"),
                    f"stage-lane outcome path invalid: {round_id}/{lane_id}")
        require(isinstance(r["reason"], str) and r["reason"],
                f"missing stage-lane retirement reason: {round_id}")
        seen_paths.add(path)
        seen_blobs.add(blob)

    historical_replay_records = data.get("historical_replay_workflows", [])
    require(isinstance(historical_replay_records, list),
            "historical_replay_workflows must be a list")
    for r in historical_replay_records:
        require(set(r) == {"path", "blob_sha", "replay_id", "evidence", "reason"},
                f"historical replay retirement fields drift: {r.get('path')}")
        path = str(r["path"])
        blob = str(r["blob_sha"])
        replay_id = r["replay_id"]
        evidence = r["evidence"]
        require(path.startswith(".github/workflows/"),
                f"invalid historical replay workflow path: {path}")
        require(path not in seen_paths, f"duplicate retired workflow path: {path}")
        require(SHA_RE.fullmatch(blob) is not None,
                f"invalid historical replay workflow blob SHA: {path}")
        require(blob not in seen_blobs, f"retired workflow blob SHA reused: {path}")
        require(isinstance(replay_id, str) and replay_id,
                f"historical replay id missing: {path}")
        require(isinstance(evidence, str) and evidence.startswith(".github/research/"),
                f"historical replay evidence path invalid: {path}")
        require(isinstance(r["reason"], str) and r["reason"],
                f"missing historical replay reason: {path}")
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

    source_candidate_round_checked = []
    for r in data.get("source_candidate_rounds", []):
        round_id = r["round_id"]
        evidence_by_stage = {}
        for item in r["workflows"]:
            path = root / item["path"]
            require(not path.exists(),
                    f"retired source-candidate round workflow was reintroduced: {item['path']}")
            evidence_path = root / item["evidence"]
            require(evidence_path.is_file(),
                    f"source-candidate round evidence missing: {item['evidence']}")
            evidence_by_stage[item["stage"]] = json.loads(
                evidence_path.read_text(encoding="utf-8")
            )
            require(git("cat-file", "-t", item["blob_sha"]) == "blob",
                    f"historical source-candidate round blob missing: {item['path']}")
            historical = git("cat-file", "blob", item["blob_sha"])
            on_block = extract_on_block(historical)
            require("pull_request:" in on_block and "workflow_dispatch:" in on_block,
                    f"retired source-candidate round workflow must preserve PR + manual lineage: {item['path']}")
            for forbidden in ("push:", "schedule:", "workflow_call:", "workflow_run:"):
                require(forbidden not in on_block,
                        f"retired source-candidate round workflow had forbidden trigger {forbidden}: {item['path']}")

        source_eval = evidence_by_stage["source-candidate-evaluation"]
        confirmation = evidence_by_stage["independent-source-confirmation"]
        public = evidence_by_stage["vad-public-confirmation"]

        require(source_eval.get("workflow") == "Research Stage Source Candidate Evaluation"
                and source_eval.get("event") == "workflow_dispatch"
                and source_eval.get("conclusion") == "success"
                and source_eval.get("requested_candidate") == "all",
                f"source-candidate evaluation evidence drift: {round_id}")
        source_candidates = source_eval.get("candidates") or {}
        vad_eval = source_candidates.get("vad") or {}
        agc_eval = source_candidates.get("agc") or {}
        require(vad_eval.get("candidate_id") == "vad-confidence-tiered-hold-v1"
                and vad_eval.get("decision") == "SOURCE_CANDIDATE_PASS"
                and vad_eval.get("independent_confirmation_required") is True,
                f"VAD source-candidate evaluation drift: {round_id}")
        require(agc_eval.get("candidate_id") == "agc-error-adaptive-release-v1"
                and agc_eval.get("decision") == "SOURCE_CANDIDATE_PASS"
                and agc_eval.get("independent_confirmation_required") is True,
                f"AGC source-candidate evaluation drift: {round_id}")
        for key in ("shipping", "automatic_main_mutation", "hil", "product_certification"):
            require((source_eval.get("authority") or {}).get(key) is False,
                    f"source-candidate evaluation regained {key}: {round_id}")

        require(confirmation.get("workflow") == "Research Stage Source Confirmation"
                and confirmation.get("event") == "workflow_dispatch"
                and confirmation.get("conclusion") == "success"
                and confirmation.get("requested_candidate") == "all",
                f"source confirmation evidence drift: {round_id}")
        require((confirmation.get("predecessor") or {}).get("source_candidate_run_id")
                == source_eval.get("run_id"),
                f"source confirmation predecessor drift: {round_id}")
        agc_confirm = confirmation.get("agc") or {}
        vad_confirm = confirmation.get("vad") or {}
        require(agc_confirm.get("candidate_id") == "agc-error-adaptive-release-v1"
                and agc_confirm.get("decision") == "SOURCE_CANDIDATE_REJECT"
                and agc_confirm.get("candidate_budget") == 0
                and agc_confirm.get("terminal_exact_candidate") is True
                and agc_confirm.get("next_gate") is None,
                f"AGC confirmation is not terminal: {round_id}")
        require(vad_confirm.get("candidate_id") == "vad-confidence-tiered-hold-v1"
                and vad_confirm.get("decision") == "SYNTHETIC_CONFIRMATION_PASS_PENDING_PUBLIC_LOCK"
                and vad_confirm.get("public_authority_consumed") is False
                and not vad_confirm.get("violations"),
                f"VAD synthetic confirmation drift: {round_id}")
        for key in ("shipping", "automatic_main_mutation", "hil",
                    "product_certification", "source_merge_authorized"):
            require((confirmation.get("authority") or {}).get(key) is False,
                    f"source confirmation regained {key}: {round_id}")

        require(public.get("workflow") == "Research Stage VAD Public Confirmation"
                and public.get("conclusion") == "success"
                and public.get("candidate_id") == "vad-confidence-tiered-hold-v1"
                and public.get("decision") == "SOURCE_CANDIDATE_REJECT",
                f"VAD public confirmation evidence drift: {round_id}")
        require((public.get("public_authority") or {}).get("consumed") is True
                and (public.get("public_authority") or {}).get("lock_rebind_passed") is True,
                f"VAD public authority was not consumed exactly: {round_id}")
        require(public.get("violations"),
                f"VAD public rejection lost gate evidence: {round_id}")
        for key in ("shipping", "hil", "product_certification",
                    "source_merge_authorized", "automatic_main_mutation"):
            require((public.get("authority") or {}).get(key) is False,
                    f"VAD public confirmation regained {key}: {round_id}")

        closure_path = root / r["round_closure"]
        require(closure_path.is_file(),
                f"source-candidate round closure missing: {r['round_closure']}")
        round_closure = json.loads(closure_path.read_text(encoding="utf-8"))
        require(round_closure.get("closure_id") == round_id
                and round_closure.get("status") == "CLOSED_NO_SURVIVING_SOURCE_CANDIDATE"
                and round_closure.get("surviving_source_candidates") == []
                and round_closure.get("source_merge_authorized") is False
                and round_closure.get("shipping_source_unchanged") is True,
                f"source-candidate round is not terminal: {round_id}")
        closed_candidates = round_closure.get("candidates") or {}
        vad_round = closed_candidates.get("vad-confidence-tiered-hold-v1") or {}
        agc_round = closed_candidates.get("agc-error-adaptive-release-v1") or {}
        require(vad_round.get("terminal") is True
                and vad_round.get("candidate_budget") == 0
                and vad_round.get("final_decision") == "SOURCE_CANDIDATE_REJECT"
                and vad_round.get("final_run_id") == public.get("run_id"),
                f"VAD round closure drift: {round_id}")
        require(agc_round.get("terminal") is True
                and agc_round.get("candidate_budget") == 0
                and agc_round.get("final_decision") == "SOURCE_CANDIDATE_REJECT"
                and agc_round.get("final_run_id") == confirmation.get("run_id"),
                f"AGC round closure drift: {round_id}")
        for key in ("shipping", "hil", "product_certification", "automatic_main_mutation"):
            require((round_closure.get("authority") or {}).get(key) is False,
                    f"source-candidate round regained {key}: {round_id}")

        contracts = {}
        for candidate_id, relative in r["candidate_contracts"].items():
            candidate_path = root / relative
            require(candidate_path.is_file(),
                    f"canonical candidate contract missing: {relative}")
            contracts[candidate_id] = json.loads(candidate_path.read_text(encoding="utf-8"))
        closures = {}
        for candidate_id, relative in r["candidate_closures"].items():
            candidate_path = root / relative
            require(candidate_path.is_file(),
                    f"candidate terminal closure missing: {relative}")
            closures[candidate_id] = json.loads(candidate_path.read_text(encoding="utf-8"))
        agc_contract = contracts["agc-error-adaptive-release-v1"]
        vad_contract = contracts["vad-confidence-tiered-hold-v1"]
        agc_closure = closures["agc-error-adaptive-release-v1"]
        vad_closure = closures["vad-confidence-tiered-hold-v1"]
        for candidate_id, candidate_contract in contracts.items():
            candidate_closure = closures[candidate_id]
            require(candidate_contract.get("candidate_id") == candidate_id
                    and candidate_contract.get("status") == "CLOSED_TERMINAL_SOURCE_CANDIDATE_REJECT"
                    and candidate_contract.get("terminal_candidate") is True
                    and candidate_contract.get("candidate_budget") == 0
                    and candidate_contract.get("confirmation_limit") == 0,
                    f"canonical candidate contract is not terminal: {candidate_id}")
            require(candidate_contract.get("closure_path") == r["candidate_closures"][candidate_id],
                    f"canonical candidate closure path drift: {candidate_id}")
            require(candidate_closure.get("candidate_id") == candidate_id
                    and candidate_closure.get("status") == "CLOSED_TERMINAL_SOURCE_CANDIDATE_REJECT"
                    and candidate_closure.get("terminal_candidate") is True
                    and candidate_closure.get("candidate_budget") == 0
                    and candidate_closure.get("decision") == "SOURCE_CANDIDATE_REJECT",
                    f"candidate closure is not terminal: {candidate_id}")
            for key in ("automatic_main_mutation", "shipping", "hil", "product_certification"):
                require((candidate_contract.get("promotion") or {}).get(key) is False,
                        f"canonical candidate regained {key}: {candidate_id}")
            for key in SOURCE_CANDIDATE_AUTHORITY_FALSE_KEYS:
                require((candidate_closure.get("output_authority") or {}).get(key) is False,
                        f"candidate closure regained {key}: {candidate_id}")

        agc_provenance = agc_closure.get("confirmation_provenance") or {}
        require(agc_provenance.get("run_id") == confirmation.get("run_id")
                and agc_provenance.get("artifact_id") == agc_confirm.get("artifact_id")
                and agc_provenance.get("artifact_digest") == agc_confirm.get("artifact_digest"),
                f"AGC terminal provenance drift: {round_id}")
        vad_predecessor = vad_closure.get("predecessor_evidence") or {}
        vad_public_provenance = vad_closure.get("public_confirmation_provenance") or {}
        require(vad_predecessor.get("source_candidate_run_id") == source_eval.get("run_id")
                and vad_predecessor.get("independent_synthetic_run_id") == confirmation.get("run_id"),
                f"VAD predecessor provenance drift: {round_id}")
        public_artifact = public.get("artifact") or {}
        require(vad_public_provenance.get("run_id") == public.get("run_id")
                and vad_public_provenance.get("artifact_id") == public_artifact.get("id")
                and vad_public_provenance.get("artifact_digest") == public_artifact.get("digest"),
                f"VAD public terminal provenance drift: {round_id}")

        agc_consumption = agc_contract.get("consumption") or {}
        vad_consumption = vad_contract.get("consumption") or {}
        require(agc_consumption.get("source_evaluation_run_id") == source_eval.get("run_id")
                and agc_consumption.get("source_evaluation_artifact_id") == agc_eval.get("artifact_id")
                and agc_consumption.get("source_evaluation_artifact_digest") == agc_eval.get("artifact_digest")
                and agc_consumption.get("independent_confirmation_run_id") == confirmation.get("run_id")
                and agc_consumption.get("independent_confirmation_artifact_id") == agc_confirm.get("artifact_id")
                and agc_consumption.get("independent_confirmation_artifact_digest") == agc_confirm.get("artifact_digest")
                and agc_consumption.get("fresh_source_evaluation_consumed") is True
                and agc_consumption.get("independent_confirmation_consumed") is True,
                f"AGC canonical consumption provenance drift: {round_id}")
        require(vad_consumption.get("source_evaluation_run_id") == source_eval.get("run_id")
                and vad_consumption.get("source_evaluation_artifact_id") == vad_eval.get("artifact_id")
                and vad_consumption.get("source_evaluation_artifact_digest") == vad_eval.get("artifact_digest")
                and vad_consumption.get("independent_synthetic_confirmation_run_id") == confirmation.get("run_id")
                and vad_consumption.get("independent_synthetic_artifact_id") == vad_confirm.get("artifact_id")
                and vad_consumption.get("independent_synthetic_artifact_digest") == vad_confirm.get("artifact_digest")
                and vad_consumption.get("public_confirmation_run_id") == public.get("run_id")
                and vad_consumption.get("public_confirmation_artifact_id") == public_artifact.get("id")
                and vad_consumption.get("public_confirmation_artifact_digest") == public_artifact.get("digest")
                and vad_consumption.get("fresh_source_evaluation_consumed") is True
                and vad_consumption.get("independent_confirmation_consumed") is True
                and vad_consumption.get("public_authority_consumed") is True,
                f"VAD canonical consumption provenance drift: {round_id}")

        source_candidate_round_checked.append({
            "round_id": round_id,
            "workflows": [item["path"] for item in r["workflows"]],
            "round_closure": r["round_closure"],
        })

    stage_lane_round_checked = []
    for r in data.get("stage_lane_rounds", []):
        round_id = r["round_id"]
        workflow_path = root / r["path"]
        require(not workflow_path.exists(),
                f"retired stage-lane workflow was reintroduced: {r['path']}")

        evidence_path = root / r["evidence"]
        require(evidence_path.is_file(),
                f"stage-lane run evidence missing: {r['evidence']}")
        evidence = json.loads(evidence_path.read_text(encoding="utf-8"))

        require(git("cat-file", "-t", r["blob_sha"]) == "blob",
                f"historical stage-lane workflow blob missing: {r['path']}")
        historical = git("cat-file", "blob", r["blob_sha"])
        on_block = extract_on_block(historical)
        require("pull_request:" in on_block and "workflow_dispatch:" in on_block,
                f"retired stage-lane workflow must preserve PR + manual lineage: {r['path']}")
        for forbidden in ("push:", "schedule:", "workflow_call:", "workflow_run:"):
            require(forbidden not in on_block,
                    f"retired stage-lane workflow had forbidden trigger {forbidden}: {r['path']}")

        require(evidence.get("program_id") == round_id
                and evidence.get("workflow") == "Research Stage Lane Optimization"
                and evidence.get("event") == "workflow_dispatch"
                and evidence.get("requested_lane") == "all"
                and evidence.get("status") == "SUCCESS",
                f"stage-lane run evidence drift: {round_id}")
        feedback = evidence.get("feedback_boundary") or {}
        require(feedback.get("development_selected") is True
                and feedback.get("validation_and_shadow_reject_only") is True
                and feedback.get("blind_used_for_selection") is False
                and feedback.get("product_external_used_for_selection") is False,
                f"stage-lane feedback boundary drift: {round_id}")
        require((evidence.get("composition") or {}).get("executable_ready") is False,
                f"stage-lane unexpectedly regained composition readiness: {round_id}")

        artifacts = evidence.get("artifacts") or {}
        decisions = evidence.get("decisions") or {}
        require(set(artifacts) == {"bf", "ns", "vad", "agc"}
                and set(decisions) == {"bf", "ns", "vad", "agc"},
                f"stage-lane evidence set drift: {round_id}")

        outcomes = {}
        for lane_id, relative in r["lane_outcomes"].items():
            outcome_path = root / relative
            require(outcome_path.is_file(),
                    f"stage-lane outcome missing: {round_id}/{lane_id} -> {relative}")
            outcomes[lane_id] = json.loads(outcome_path.read_text(encoding="utf-8"))

        bf = outcomes["bf"]
        bf_artifact = artifacts["bf"]
        bf_decision = decisions["bf"]
        bf_predecessor = bf.get("predecessor") or {}
        require(bf_decision.get("decision") == "FROZEN_STAGE_RESEARCH_CANDIDATE"
                and bf_decision.get("executable_binding") is False
                and bf_decision.get("next_gate") == "separate-source-candidate-review",
                f"BF stage-lane decision drift: {round_id}")
        require(bf.get("authority") == "DIAGNOSTIC_ONLY"
                and bf.get("candidate_budget") == 0
                and bf_predecessor.get("stage_lane_run") == evidence.get("run_id")
                and bf_predecessor.get("artifact_id") == bf_artifact.get("artifact_id")
                and bf_predecessor.get("artifact_digest") == bf_artifact.get("digest")
                and bf_predecessor.get("lane_decision") == bf_decision.get("decision")
                and bf_predecessor.get("emulator_variant")
                    == (bf_decision.get("selected") or {}).get("variant")
                and bf_predecessor.get("emulator_parameter")
                    == (bf_decision.get("selected") or {}).get("parameter"),
                f"BF stage-lane outcome was not consumed exactly: {round_id}")
        prohibited = set(bf.get("prohibited") or [])
        require("select a BF source candidate" in prohibited
                and "shipping/HIL/Product Certification promotion" in prohibited,
                f"BF stage-lane diagnostic boundary drift: {round_id}")

        ns = outcomes["ns"]
        ns_artifact = artifacts["ns"]
        ns_decision = decisions["ns"]
        ns_evidence = ns.get("evidence") or {}
        require(ns_decision.get("decision") == "REJECT_CANDIDATE"
                and ns_decision.get("executable_binding") is True
                and ns_decision.get("next_gate") is None,
                f"NS stage-lane decision drift: {round_id}")
        require(ns.get("status") == "CLOSED_KEEP_BASELINE_AFTER_REJECT"
                and ns.get("candidate_budget") == 0
                and ns_evidence.get("stage_lane_run") == evidence.get("run_id")
                and ns_evidence.get("artifact_id") == ns_artifact.get("artifact_id")
                and ns_evidence.get("artifact_digest") == ns_artifact.get("digest")
                and ns_evidence.get("decision") == ns_decision.get("decision")
                and (ns_evidence.get("effective_winner") or {}).get("algorithm")
                    == (ns_decision.get("effective_winner") or {}).get("algorithm")
                and (ns_evidence.get("effective_winner") or {}).get("ns_floor")
                    == ((ns_decision.get("effective_winner") or {}).get("tuning") or {}).get("ns_floor"),
                f"NS stage-lane closure drift: {round_id}")

        for lane_id in ("vad", "agc"):
            candidate = outcomes[lane_id]
            artifact = artifacts[lane_id]
            decision = decisions[lane_id]
            predecessor = candidate.get("predecessor") or {}
            require(decision.get("decision") == "FROZEN_STAGE_RESEARCH_CANDIDATE"
                    and decision.get("executable_binding") is False
                    and decision.get("next_gate") == "separate-source-candidate-review",
                    f"{lane_id.upper()} stage-lane decision drift: {round_id}")
            require(candidate.get("status") == "CLOSED_TERMINAL_SOURCE_CANDIDATE_REJECT"
                    and candidate.get("terminal_candidate") is True
                    and candidate.get("candidate_budget") == 0
                    and candidate.get("confirmation_limit") == 0
                    and predecessor.get("stage_lane_run") == evidence.get("run_id")
                    and predecessor.get("artifact_id") == artifact.get("artifact_id")
                    and predecessor.get("artifact_digest") == artifact.get("digest")
                    and predecessor.get("lane_decision") == decision.get("decision"),
                    f"{lane_id.upper()} stage-lane successor is not terminal: {round_id}")
            for key in ("automatic_main_mutation", "shipping", "hil", "product_certification"):
                require((candidate.get("promotion") or {}).get(key) is False,
                        f"{lane_id.upper()} stage-lane successor regained {key}: {round_id}")

        stage_lane_round_checked.append({
            "round_id": round_id,
            "path": r["path"],
            "evidence": r["evidence"],
            "lane_outcomes": r["lane_outcomes"],
        })

    historical_replay_checked = []
    for r in data.get("historical_replay_workflows", []):
        path = root / r["path"]
        require(not path.exists(),
                f"retired historical replay workflow was reintroduced: {r['path']}")
        evidence_path = root / r["evidence"]
        require(evidence_path.is_file(),
                f"historical replay evidence missing: {r['evidence']}")
        evidence = json.loads(evidence_path.read_text(encoding="utf-8"))

        require(evidence.get("replay_id") == r["replay_id"],
                f"historical replay identity drift: {r['path']}")
        require(evidence.get("authority") == "DIAGNOSTIC_REGRESSION_ONLY"
                and evidence.get("status") == "CONSUMED_HISTORICAL_BASELINE_EXPLANATION"
                and evidence.get("candidate_budget") == 0,
                f"historical replay is not consumed diagnostic evidence: {r['path']}")
        require(evidence.get("historical_workflow_blob_sha") == r["blob_sha"],
                f"historical replay blob identity drift: {r['path']}")

        replay = evidence.get("replay") or {}
        require(replay.get("conclusion") == "success"
                and isinstance(replay.get("run_id"), int)
                and isinstance(replay.get("artifact_id"), int)
                and isinstance(replay.get("artifact_digest"), str)
                and replay.get("artifact_digest", "").startswith("sha256:")
                and replay.get("head_sha") == (evidence.get("final_product_lineage") or {}).get("exact_shipping_head_sha"),
                f"historical replay execution provenance drift: {r['path']}")
        require(evidence.get("exact_base_sha")
                and evidence.get("exact_base_sha") != replay.get("head_sha"),
                f"historical replay lost distinct fixed-base identity: {r['path']}")

        finding = evidence.get("finding") or {}
        require(finding.get("hard_fault_isolation_needed") is True
                and finding.get("pure_energy_strong_bypass_safe") is False,
                f"historical replay finding drift: {r['path']}")

        product = evidence.get("final_product_lineage") or {}
        require(product.get("confirmation_conclusion") == "success"
                and product.get("shipped_release") == "v2.3.11"
                and isinstance(product.get("differential_confirmation_run_id"), int)
                and isinstance(product.get("differential_confirmation_artifact_id"), int)
                and isinstance(product.get("differential_confirmation_artifact_digest"), str)
                and product.get("differential_confirmation_artifact_digest", "").startswith("sha256:")
                and product.get("shipping_merge_commit"),
                f"historical replay final product lineage drift: {r['path']}")
        semantics = product.get("confirmation_semantics") or {}
        require(semantics.get("non_wind_byte_exact_vs_base") is True
                and semantics.get("hard_mode_coverage") == 0.88
                and semantics.get("healthy_channel_selection") == 1.0
                and semantics.get("stable_recovery_frames") == 28,
                f"historical replay final confirmation semantics drift: {r['path']}")

        authority = evidence.get("output_authority") or {}
        require(authority.get("research_diagnostic_only") is True,
                f"historical replay lost diagnostic-only authority: {r['path']}")
        for key in RESEARCH_AUTHORITY_FALSE_KEYS:
            require(authority.get(key) is False,
                    f"historical replay regained {key} authority: {r['path']}")

        require(git("cat-file", "-t", r["blob_sha"]) == "blob",
                f"historical replay workflow blob missing: {r['path']}")
        historical = git("cat-file", "blob", r["blob_sha"])
        base_match = re.search(
            r"(?m)^\s*BASE_SHA:\s*([0-9a-f]{40})\s*$", historical
        )
        require(base_match is not None
                and base_match.group(1) == evidence.get("exact_base_sha"),
                f"historical replay fixed-base binding drift: {r['path']}")
        on_block = extract_on_block(historical)
        require("pull_request:" in on_block and "workflow_dispatch:" in on_block,
                f"retired historical replay must preserve PR + manual lineage: {r['path']}")
        for forbidden in ("push:", "schedule:", "workflow_call:", "workflow_run:"):
            require(forbidden not in on_block,
                    f"retired historical replay had forbidden trigger {forbidden}: {r['path']}")

        historical_replay_checked.append({
            "path": r["path"],
            "blob_sha": r["blob_sha"],
            "replay_id": r["replay_id"],
            "evidence": r["evidence"],
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
        "retired_source_candidate_rounds": len(source_candidate_round_checked),
        "retired_stage_lane_rounds": len(stage_lane_round_checked),
        "retired_historical_replay_workflows": len(historical_replay_checked),
        "tasks": sorted(EXPECTED_TASKS),
        "research_investigations": sorted(item["investigation_id"] for item in research_checked),
        "source_candidates": sorted(item["candidate_id"] for item in source_candidate_checked),
        "selection_ids": sorted(item["selection_id"] for item in selection_checked),
        "source_candidate_rounds": sorted(item["round_id"] for item in source_candidate_round_checked),
        "stage_lane_rounds": sorted(item["round_id"] for item in stage_lane_round_checked),
        "historical_replays": sorted(item["replay_id"] for item in historical_replay_checked),
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
        "selection_workflows": [],
        "source_candidate_rounds": [],
        "stage_lane_rounds": [],
        "historical_replay_workflows": [],
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
    round_sample = json.loads(json.dumps(sample))
    round_sample["source_candidate_rounds"] = [{
        "round_id": "stage-source-candidate-round-v1",
        "workflows": [
            {
                "path": ".github/workflows/research-source-eval.yml",
                "blob_sha": "a" * 40,
                "stage": "source-candidate-evaluation",
                "evidence": ".github/research/source-eval-run.json",
            },
            {
                "path": ".github/workflows/research-source-confirm.yml",
                "blob_sha": "b" * 40,
                "stage": "independent-source-confirmation",
                "evidence": ".github/research/source-confirm-run.json",
            },
            {
                "path": ".github/workflows/research-public-confirm.yml",
                "blob_sha": "c" * 40,
                "stage": "vad-public-confirmation",
                "evidence": ".github/research/public-confirm-run.json",
            },
        ],
        "round_closure": ".github/research/source-round-closure.json",
        "candidate_contracts": {
            "vad-confidence-tiered-hold-v1": ".github/research/source-candidates/vad.json",
            "agc-error-adaptive-release-v1": ".github/research/source-candidates/agc.json",
        },
        "candidate_closures": {
            "vad-confidence-tiered-hold-v1": ".github/research/vad-closure.json",
            "agc-error-adaptive-release-v1": ".github/research/agc-closure.json",
        },
        "reason": "terminal source candidate round",
    }]
    validate_manifest(round_sample)
    stage_lane_sample = json.loads(json.dumps(sample))
    stage_lane_sample["stage_lane_rounds"] = [{
        "round_id": "bf-ns-vad-agc-stage-lanes-v1",
        "path": ".github/workflows/research-stage-lane-example.yml",
        "blob_sha": "9" * 40,
        "evidence": ".github/research/stage-lane-run.json",
        "lane_outcomes": {
            "bf": ".github/research/bf-outcome.json",
            "ns": ".github/research/ns-outcome.json",
            "vad": ".github/research/vad-outcome.json",
            "agc": ".github/research/agc-outcome.json",
        },
        "reason": "terminal four-lane research round",
    }]
    validate_manifest(stage_lane_sample)
    replay_sample = json.loads(json.dumps(sample))
    replay_sample["historical_replay_workflows"] = [{
        "path": ".github/workflows/research-historical-replay.yml",
        "blob_sha": "8" * 40,
        "replay_id": "historical-replay-v1",
        "evidence": ".github/research/historical-replay-v1.json",
        "reason": "consumed exact-base diagnostic replay",
    }]
    validate_manifest(replay_sample)
    assert "pull_request:" in extract_on_block("name: X\non:\n  pull_request:\npermissions:\n  contents: read\n")
    assert TASK_WORKFLOW_RE.fullmatch("i009-residual-echo-rescue-root-cause.yml")
    assert not TASK_WORKFLOW_RE.fullmatch("audio-quality-gates.yml")
    unknown = json.loads(json.dumps(sample))
    unknown["future_retirement_category"] = []
    try:
        validate_manifest(unknown)
    except ValueError as exc:
        assert "top-level fields drift" in str(exc)
    else:
        raise AssertionError("unknown retirement category was silently accepted")
    missing = json.loads(json.dumps(sample))
    missing.pop("historical_replay_workflows")
    try:
        validate_manifest(missing)
    except ValueError as exc:
        assert "top-level fields drift" in str(exc)
    else:
        raise AssertionError("missing retirement category was silently accepted")
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
