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


def validate_i004_closed(plan: dict, root: Path) -> None:
    by_id = {task["id"]: task for task in plan["tasks"]}
    i004 = by_id["I004"]
    if i004["status"] != "CLOSED":
        return
    require(i004["handler"] is None and bool(i004["evidence"]),
            "I004 CLOSED must be terminal and evidence-backed")
    closure = json.loads(repo_file(root, "docs/program/iterations/I004-closure.json").read_text())
    result = json.loads(repo_file(
        root, "docs/program/iterations/I004-burst-candidate-search-result.json").read_text())

    require(closure["schema_version"] == 1 and closure["iteration_id"] == "I004" and
            closure["state"] == "CLOSED_KEEP_BASELINE" and closure["lane"] == "acoustic" and
            closure["root_cause_id"] == "ema-burst-start-stop-speech-protection",
            "I004 CLOSED requires reviewed closure identity")
    require(closure["closed_on_main_sha"] == "5d5fed094b5a51af2f503d1556e8f6fbce82af07",
            "I004 closure must bind reviewed #99 main SHA")
    shipping = closure["shipping_baseline"]
    require(shipping["release"] == plan["baseline"]["software_release"] == "v2.3.12" and
            shipping["source_sha"] == plan["baseline"]["source_sha"] and
            shipping["unchanged"] is True,
            "I004 closure must keep immutable shipping baseline")

    require(result["schema_version"] == 1 and result["iteration_id"] == "I004" and
            result["root_cause_id"] == "ema-burst-start-stop-speech-protection" and
            result["decision"] == "KEEP_BASELINE_NO_ELIGIBLE_CANDIDATE" and
            result["winner"] is None and result["promotion_allowed"] is False,
            "I004 CLOSED requires reviewed KEEP_BASELINE result")
    require(result["candidate_budget"] == {"limit": 2, "consumed": 2, "remaining": 0} and
            result["confirmation_budget_consumed"] == 0,
            "I004 CLOSED requires exhausted bounded candidates and zero confirmation")
    execution = result["authoritative_execution"]
    require(execution["workflow_run_id"] == 34004833190 and
            execution["artifact_id"] == 9980617637 and
            execution["artifact_digest"] ==
            "sha256:669cedca1f19564d67b3079f471d3bfe4c03f02cef8bfbc658a60d455da6416a" and
            execution["internal_sha256s_verified"] == 1399,
            "I004 CLOSED requires independently verified bounded-search evidence")
    require(len(result["candidates"]) == 2 and
            all(candidate["eligible"] is False for candidate in result["candidates"]),
            "I004 CLOSED requires both frozen candidates to be ineligible")
    require(result["reviewed_conclusion"]["do_not_add_third_candidate"] is True and
            result["reviewed_conclusion"][
                "do_not_use_confirmation_to_rescue_failed_development_candidates"] is True and
            result["reviewed_conclusion"][
                "future_I004_source_candidate_requires_new_root_cause_budget_decision"] is True,
            "I004 CLOSED must seal exhausted search authority")
    require(result["authority_boundary"] == {
                "shipping_source_changed": False,
                "software_candidate_promoted": False,
                "release_created": False,
                "product_qualification": "DEFERRED_BY_SCOPE",
            }, "I004 closure must preserve release/product boundary")

    bounded = closure["evidence_chain"]["bounded_source_search"]
    require(bounded["effective_run_id"] == execution["workflow_run_id"] and
            bounded["artifact_id"] == execution["artifact_id"] and
            bounded["artifact_digest"] == execution["artifact_digest"] and
            bounded["internal_sha256s_verified"] == execution["internal_sha256s_verified"] and
            bounded["candidate_limit"] == 2 and bounded["candidates_consumed"] == 2 and
            bounded["confirmation_consumed"] == 0 and
            bounded["decision"] == result["decision"] and bounded["winner"] is None,
            "I004 closure/result evidence mismatch")
    decision = closure["closure_decision"]
    require(decision["keep_baseline"] is True and decision["merge_shipping_candidate"] is False and
            decision["create_release"] is False and
            decision["consume_confirmation_to_rescue_failed_candidates"] is False and
            decision["allow_third_candidate"] is False and
            decision["future_I004_candidate_requires_new_root_cause_budget_decision"] is True,
            "I004 closure decision must be terminal KEEP_BASELINE")
    handoff = closure["handoff"]["I005"]
    require(handoff["status"] == "PLANNED" and
            handoff["authority"] == "already-observed-regression-root-cause-context-only" and
            handoff["may_be_independent_confirmation"] is False and
            handoff["may_be_candidate_selection_data"] is False,
            "I004 closure handoff must remain non-executable and non-independent")
    require(by_id["I005"]["status"] in {"PLANNED", "CLOSED"},
            "I004 closure cannot directly place I005 in an executable state")
    require(closure["authority_boundary"] == {
                "product_qualification": "DEFERRED_BY_SCOPE",
                "hardware_collection": False,
                "dut_hil": "DEFERRED_BY_SCOPE",
            }, "I004 CLOSED cannot claim product qualification")


def validate_i006_review_required(plan: dict, root: Path) -> None:
    by_id = {task["id"]: task for task in plan["tasks"]}
    i006 = by_id["I006"]
    if i006["status"] != "REVIEW_REQUIRED":
        return
    require(i006["handler"] is None and
            i006["contract"] == "docs/program/iterations/I006-baseline.json" and
            bool(i006["evidence"]),
            "I006 REVIEW_REQUIRED must be frozen, evidence-backed and non-executable")
    review = json.loads(repo_file(root, "docs/program/iterations/I006-review.json").read_text())
    result = json.loads(repo_file(root, "docs/program/iterations/I006-baseline-result.json").read_text())
    require(review["schema_version"] == 1 and review["iteration_id"] == "I006" and
            review["phase"] == "reviewed-baseline-gap" and
            review["state"] == "REVIEW_REQUIRED" and
            review["decision"] == "MEASURED_GAP_REVIEW_REQUIRED" and
            review["measurement_main_sha"] == "f48559f55791cc72a69befdd79472d908c93803d",
            "I006 REVIEW_REQUIRED requires reviewed baseline-gap identity")
    execution = review["authoritative_execution"]
    require(execution["workflow_run_id"] == 34011652196 and
            execution["artifact_id"] == 9982646065 and
            execution["artifact_digest"] ==
            "sha256:f175dc88aef99181d7e1fd8568ffc015ba5fc00065b5d36e2f787c38a6188b6f" and
            execution["internal_sha256s_verified"] == 341 and
            execution["measurement_revision"] == 3 and
            execution["cases_complete"] == 18 and
            execution["precondition_failures"] == 0,
            "I006 REVIEW_REQUIRED requires exact revision-3 evidence")
    authority = review["authority"]
    require(authority["candidate_limit_consumed"] == 0 and
            authority["confirmation_limit_consumed"] == 0 and
            authority["shipping_candidate_authorized"] is False and
            authority["root_cause_differential_authorized"] is True and
            authority["parameter_search_authorized"] is False and
            authority["promotion_allowed"] is False and
            authority["release_allowed"] is False,
            "I006 REVIEW_REQUIRED cannot acquire candidate/promotion authority")
    retirement = review["development_source_retirement"]
    require(retirement["seeds"] == [16107, 26107, 36107] and
            retirement["next_role"] == "regression" and
            retirement["future_independent_confirmation"] is False and
            retirement["promotion_authority"] is False,
            "I006 Development source must retire to regression")
    require(result["schema_version"] == 1 and result["iteration_id"] == "I006" and
            result["measurement_revision"] == 3 and
            result["decision"] == "MEASURED_GAP_REVIEW_REQUIRED" and
            result["candidate_decision"] == "NOT_AN_ACOUSTIC_CANDIDATE" and
            result["candidate_limit_consumed"] == 0 and
            result["confirmation_limit_consumed"] == 0 and
            result["promotion_allowed"] is False,
            "I006 review/result authority mismatch")
    authoritative = result["authoritative_execution"]
    require(authoritative["workflow_run_id"] == execution["workflow_run_id"] and
            authoritative["artifact_id"] == execution["artifact_id"] and
            authoritative["artifact_digest"] == execution["artifact_digest"] and
            authoritative["internal_sha256s_verified"] == execution["internal_sha256s_verified"] and
            authoritative["cases"] == 18 and authoritative["precondition_failures"] == 0,
            "I006 review/result evidence mismatch")
    require(result["reviewed_findings"]["pure_far_end"]["passed"] == 6 and
            result["reviewed_findings"]["near_far_speech_preservation"]["passed"] == 6 and
            result["reviewed_findings"]["noise_floor"]["passed"] == 0 and
            result["reviewed_findings"]["double_talk_activity"]["passed"] == 1,
            "I006 reviewed finding partition drift")
    require(result["reviewed_next_action"]["state"] == "REVIEW_REQUIRED" and
            result["reviewed_next_action"]["allow_agc_target_or_limiter_search"] is False and
            result["reviewed_next_action"]["allow_attack_release_search"] is False and
            result["reviewed_next_action"]["allow_confirmation"] is False,
            "I006 review may authorize root-cause differential only")
    require(result["shipping_boundary"] == {
                "shipping_source_changed": False,
                "software_candidate_promoted": False,
                "release_created": False,
                "software_release": "v2.3.12",
            } and result["product_qualification"] == "DEFERRED_BY_SCOPE",
            "I006 review must preserve shipping/product boundary")
    i007 = by_id["I007"]
    require(i007["status"] == "PLANNED" and i007["handler"] is None and
            i007["contract"] is None and not i007["evidence"],
            "I006 REVIEW_REQUIRED must not auto-activate I007")


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
    if root is not None:
        validate_i004_closed(plan, root)
        validate_i006_review_required(plan, root)


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
    validate(plan, ROOT)
    by_id = {task["id"]: task for task in plan["tasks"]}
    i002, p001, i003, i004, i005, i006 = (by_id["I002"], by_id["P001"], by_id["I003"],
                                           by_id["I004"], by_id["I005"], by_id["I006"])
    require(i002["status"] == "CLOSED" and i002["handler"] is None and bool(i002["evidence"]),
            "I002 must remain reviewed and closed")
    require(p001["status"] == "CLOSED" and p001["handler"] is None and bool(p001["evidence"]),
            "P001 must remain reviewed and closed")
    require(i004["status"] == "CLOSED" and i004["handler"] is None and bool(i004["evidence"]),
            "I004 must remain reviewed CLOSED_KEEP_BASELINE")
    if i005["status"] == "PLANNED":
        require(i005["handler"] is None and i005["contract"] is None and not i005["evidence"],
                "planned I005 cannot have executable/review authority")
    elif i005["status"] == "CLOSED":
        require(i005["handler"] is None and
                i005["contract"] == "docs/program/iterations/I005-baseline.json" and
                bool(i005["evidence"]),
                "closed I005 must be evidence-backed and non-executable")
        if i006["status"] == "PLANNED":
            require(i006["handler"] is None and i006["contract"] is None and not i006["evidence"],
                    "planned I006 cannot have executable/review authority")
        elif i006["status"] == "REVIEW_REQUIRED":
            require(i006["handler"] is None and
                    i006["contract"] == "docs/program/iterations/I006-baseline.json" and
                    bool(i006["evidence"]),
                    "review-required I006 must be evidence-backed and non-executable")
        else:
            raise AssertionError("I005 closure allows only PLANNED or independently reviewed I006")
        require(next_task(plan) is None and view(plan)["automation_status"] == "NO_READY_TASK",
                "I005 closure/I006 review cannot create an automatic next task")
    else:
        raise AssertionError("I005 must be PLANNED or evidence-backed CLOSED")

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
        lambda p: next(t for t in p["tasks"] if t["id"] == "I005").update(status="CLOSED", evidence=[]),
        lambda p: next(t for t in p["tasks"] if t["id"] == "I006").update(status="REVIEW_REQUIRED", evidence=[]),
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
    by_id_blocked["I004"].update(status="REVIEW_REQUIRED")
    by_id_blocked["I003"].update(depends_on=["I004"])
    require(next_task(blocked) is None, "explicit unfinished dependency must block")
    print("program self-test: I002/P001/I003/I004/I005/I006 evidence-backed lifecycles + negative contracts OK")


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
