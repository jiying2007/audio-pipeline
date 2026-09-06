#!/usr/bin/env python3
import subprocess
from pathlib import Path

BASE = "0f3a2ec707631b836fe5e0aafaea44543cd36e85"

def base_text(path: str) -> str:
    return subprocess.check_output(["git", "show", f"{BASE}:{path}"], text=True)

plan = Path("docs/program/plan.json")
s = base_text("docs/program/plan.json")
old = '''    {
      "id": "P002", "priority": 90, "status": "PLANNED", "lane": "governance",
      "title": "Release identity conflict and archival/GC in-flight safety audit",
      "depends_on": ["P000"], "handler": null, "contract": null,
      "exit": "Reject tag/asset identity conflicts; preserve exact replay evidence; no deletion on SHA drift or active dependency",
      "evidence": []
    },
'''
new = '''    {
      "id": "P002", "priority": 90, "status": "CLOSED", "lane": "governance",
      "title": "Release identity conflict and archival/GC in-flight safety audit",
      "depends_on": ["P000"], "handler": null, "contract": "docs/program/iterations/P002-closure.json",
      "exit": "Candidate-zero reproduced all three governance gaps; the single bounded fix closed existing-release identity, GC active-dependency and terminal-trigger gaps; exact-main Verify and existing v2.3.12 Release identity preflight both pass without release/tag/GC mutation",
      "evidence": [
        {"source_sha": "9100fd7adee6939082f0f95a867325a7e1a49b78", "url": "https://github.com/jiying2007/audio-pipeline/actions/runs/34041186187", "meaning": "P002 candidate-zero audit artifact 9991709188/digest 0fb55ac3... independently verified 6/6 hashes and reproduced all three frozen governance gaps without destructive mutation."},
        {"source_sha": "2e8ac905ec8417a60c45c4015d7ff96f37f12ff6", "url": "https://github.com/jiying2007/audio-pipeline/actions/runs/34043470402", "meaning": "The only bounded P002 governance fix passed live immutable v2.3.12 identity preflight, GC active-dependency regression fixtures and terminal-trigger scoping before merge; candidate budget 1/1, confirmation 0."},
        {"source_sha": "0f3a2ec707631b836fe5e0aafaea44543cd36e85", "url": "https://github.com/jiying2007/audio-pipeline/actions/runs/34043737389", "meaning": "Post-merge exact-main Verify #600 completed success on the P002 fix SHA; Hosted Real Audio/AEC also pass on the same main."},
        {"source_sha": "0f3a2ec707631b836fe5e0aafaea44543cd36e85", "url": "https://github.com/jiying2007/audio-pipeline/actions/runs/34043955335", "meaning": "Post-Verify Release #591 executed the existing-release identity step and returned EXISTING_RELEASE_IDENTITY_PASS for immutable v2.3.12: 8 assets, 7 checksums, tag/manifest source d82cb6d... and ancestor relation to current main; build/tag/publish remained skipped."}
      ]
    },
'''
assert s.count(old) == 1, s.count(old)
plan.write_text(s.replace(old, new))

program = Path("scripts/program.py")
p = base_text("scripts/program.py")
marker = "\ndef validate(plan: dict, root: Path | None = None) -> None:\n"
validator = r'''
def validate_p002_closed(plan: dict, root: Path) -> None:
    by_id = {task["id"]: task for task in plan["tasks"]}
    p002 = by_id["P002"]
    if p002["status"] != "CLOSED":
        return
    require(p002["handler"] is None and
            p002["contract"] == "docs/program/iterations/P002-closure.json" and
            len(p002["evidence"]) == 4,
            "P002 CLOSED must be terminal and evidence-backed")
    c = json.loads(repo_file(root, p002["contract"]).read_text())
    require(c["schema_version"] == 1 and c["iteration_id"] == "P002" and
            c["state"] == "CLOSED_GOVERNANCE_GAPS_FIXED" and
            c["lane"] == "governance" and
            c["closed_from_main_sha"] == "0f3a2ec707631b836fe5e0aafaea44543cd36e85" and
            c["root_cause_id"] == "release-identity-gc-active-dependency-terminal-trigger-safety",
            "P002 closure identity")
    require(c["shipping_baseline"] == {
                "release": "v2.3.12",
                "source_sha": plan["baseline"]["source_sha"],
                "unchanged": True,
            } and plan["baseline"]["software_release"] == "v2.3.12",
            "P002 closure must preserve immutable shipping baseline")
    audit = c["candidate_zero_audit"]
    require(audit["pr"] == 124 and
            audit["merge_main_sha"] == "699c1f604611b5018ab3cb7a712ed1a8942cedcb" and
            audit["audit_head_sha"] == "9100fd7adee6939082f0f95a867325a7e1a49b78" and
            audit["run_id"] == 34041186187 and audit["artifact_id"] == 9991709188 and
            audit["artifact_digest"] == "sha256:0fb55ac3e6d116826c46fa9a1b5171cc3acd74aed5b6467e36c6a0c959d46e65" and
            audit["internal_sha256s_verified"] == 6 and
            audit["decision"] == "GOVERNANCE_GAPS_REVIEW_REQUIRED" and
            audit["reproduced_gaps"] == [
                "existing-release-identity", "gc-active-dependency", "terminal-closure-trigger-scope"] and
            audit["real_release_or_tag_mutation"] is False and audit["real_branch_deletion"] is False,
            "P002 candidate-zero evidence")
    fix = c["bounded_governance_fix"]
    require(fix["candidate_limit"] == fix["candidate_limit_consumed"] == 1 and
            fix["confirmation_limit_consumed"] == 0 and fix["pr"] == 125 and
            fix["head_sha"] == "2e8ac905ec8417a60c45c4015d7ff96f37f12ff6" and
            fix["merge_main_sha"] == "0f3a2ec707631b836fe5e0aafaea44543cd36e85" and
            fix["dedicated_run_id"] == 34043470402 and fix["dedicated_run_conclusion"] == "success" and
            fix["fixes"] == {
                "existing_release_identity_preflight": True,
                "gc_active_dependency_block": True,
                "terminal_closure_trigger_scope": True,
            } and fix["shipping_source_changed"] is False and fix["semver_changed"] is False and
            fix["release_created_or_modified"] is False and fix["real_branch_deleted"] is False,
            "P002 bounded governance fix")
    post = c["post_merge_verification"]
    require(post == {
                "main_sha": "0f3a2ec707631b836fe5e0aafaea44543cd36e85",
                "verify_run_id": 34043737389,
                "verify_run_number": 600,
                "verify_conclusion": "success",
                "hosted_real_audio_run_id": 34043737228,
                "hosted_real_audio_conclusion": "success",
                "hosted_real_aec_run_id": 34043737310,
                "hosted_real_aec_conclusion": "success",
                "historical_terminal_closure_misfires_observed": 0,
            }, "P002 post-merge verification")
    release = c["existing_release_identity_proof"]
    require(release == {
                "release_run_id": 34043955335,
                "release_run_number": 591,
                "release_conclusion": "success",
                "identity_step": "Verify existing immutable release identity",
                "identity_step_conclusion": "success",
                "validator_result": "EXISTING_RELEASE_IDENTITY_PASS",
                "tag": "v2.3.12",
                "release_source_sha": "d82cb6d2be76497d1d66dd16da00924411207046",
                "verified_main_sha": "0f3a2ec707631b836fe5e0aafaea44543cd36e85",
                "release_source_is_ancestor": True,
                "immutable": True,
                "asset_count": 8,
                "checksummed_assets": 7,
                "manifest_payload_assets": 6,
                "release_build_publish_steps_skipped": True,
                "new_release_or_tag_created": False,
            }, "P002 existing release identity proof")
    require(c["closure_decision"] == {
                "status": "CLOSED",
                "governance_gaps_fixed": True,
                "additional_p002_candidate_authorized": False,
                "confirmation_consumed": 0,
                "destructive_gc_executed": False,
                "release_created": False,
                "semver_changed": False,
                "shipping_baseline_changed": False,
            }, "P002 closure decision")
    i008 = by_id["I008"]
    require(i008["status"] == "REVIEW_REQUIRED" and i008["handler"] is None and
            i008["contract"] == "docs/program/iterations/I008-review-required.json" and
            len(i008["evidence"]) == 2 and
            c["handoff"]["I008"] == {
                "status": "REVIEW_REQUIRED",
                "authority": "verified-release-bearing-comparator-fix-carry-only",
                "may_bypass_semver_policy": False,
                "may_claim_product_qualification": False,
                "future_real_patch_release_must_reverify_required_summary": True,
            }, "P002 closure must leave I008 REVIEW_REQUIRED")
    require(c["authority_boundary"] == {
                "shipping_source_changed": False,
                "software_candidate_promoted": False,
                "release_created": False,
                "product_qualification": "DEFERRED_BY_SCOPE",
                "hardware_collection": False,
                "dut_hil": "DEFERRED_BY_SCOPE",
            }, "P002 authority boundary")

'''
assert p.count(marker) == 1, p.count(marker)
p = p.replace(marker, "\n" + validator + "def validate(plan: dict, root: Path | None = None) -> None:\n")
old_calls = '''        validate_i009_closed(plan, root)\n        validate_i008_review_required(plan, root)\n'''
new_calls = '''        validate_i009_closed(plan, root)\n        validate_i008_review_required(plan, root)\n        validate_p002_closed(plan, root)\n'''
assert p.count(old_calls) == 1, p.count(old_calls)
p = p.replace(old_calls, new_calls)
old_self = '''    by_id = {task["id"]: task for task in plan["tasks"]}\n    i002, p001, i003, i004, i005, i006 = (by_id["I002"], by_id["P001"], by_id["I003"],\n                                           by_id["I004"], by_id["I005"], by_id["I006"])\n    i008 = by_id["I008"]\n'''
new_self = '''    by_id = {task["id"]: task for task in plan["tasks"]}\n    i002, p001, i003, i004, i005, i006 = (by_id["I002"], by_id["P001"], by_id["I003"],\n                                           by_id["I004"], by_id["I005"], by_id["I006"])\n    i008 = by_id["I008"]\n    p002 = by_id["P002"]\n'''
assert p.count(old_self) == 1, p.count(old_self)
p = p.replace(old_self, new_self)
anchor = '''    if i003["status"] == "PLANNED":\n'''
p002_self = '''    if p002["status"] == "PLANNED":\n        require(p002["handler"] is None and p002["contract"] is None and not p002["evidence"],\n                "planned P002 cannot have terminal/executable authority")\n    elif p002["status"] == "CLOSED":\n        require(p002["handler"] is None and\n                p002["contract"] == "docs/program/iterations/P002-closure.json" and\n                len(p002["evidence"]) == 4,\n                "closed P002 must be terminal and evidence-backed")\n    else:\n        raise AssertionError("P002 must be PLANNED or evidence-backed CLOSED")\n\n'''
assert p.count(anchor) == 1, p.count(anchor)
p = p.replace(anchor, p002_self + anchor)
mut_anchor = '''        lambda p: next(t for t in p["tasks"] if t["id"] == "I006").update(status="CLOSED", evidence=[]),\n'''
mut_new = mut_anchor + '''        lambda p: next(t for t in p["tasks"] if t["id"] == "P002").update(status="CLOSED", evidence=[]),\n'''
assert p.count(mut_anchor) == 1, p.count(mut_anchor)
p = p.replace(mut_anchor, mut_new)
old_msg = "program self-test: I002/P001/I003/I004/I005/I006/I008 evidence-backed lifecycles + negative contracts OK"
new_msg = "program self-test: I002/P001/I003/I004/I005/I006/I008/P002 evidence-backed lifecycles + negative contracts OK"
assert p.count(old_msg) == 1, p.count(old_msg)
p = p.replace(old_msg, new_msg)
program.write_text(p)
