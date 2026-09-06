#!/usr/bin/env python3
from pathlib import Path

plan = Path('docs/program/plan.json')
s = plan.read_text()
old = '''    {
      "id": "I008", "priority": 80, "status": "PLANNED", "lane": "engineering",
      "title": "Runtime/API/reset, bounded diagnostics/replay, resampler and composition resource audit",
      "depends_on": ["P000"], "handler": null, "contract": null,
      "exit": "TSan/realtime/SDK/ABI; FULL LOW TINY RAW custom; paired host CPU/RAM/ROM; no unproven DUT claims",
      "evidence": []
    },
'''
new = '''    {
      "id": "I008", "priority": 80, "status": "REVIEW_REQUIRED", "lane": "engineering",
      "title": "Runtime/API/reset, bounded diagnostics/replay, resampler and composition resource audit",
      "depends_on": ["P000"], "handler": null, "contract": "docs/program/iterations/I008-review-required.json",
      "exit": "Engineering matrix passes and the resampler paired-perf measurement bug is root-caused with a verified fix, but the fix is release-bearing and must not merge without an authorized future SemVer change; v2.3.12 remains shipping",
      "evidence": [
        {"source_sha": "665f766c0519bd3d58b8381deae2381f30dcce97", "url": "https://github.com/jiying2007/audio-pipeline/actions/runs/34038886087", "meaning": "I008 candidate-zero engineering audit: runtime/API/reset, SDK/ABI, TSan, diagnostics/replay, resampler functional contracts, FULL/LOW/TINY/RAW resources, ARM/QEMU and ordinary-user lab all pass. Artifacts 9991073229/9991049048/9991080810 were independently digest-verified, but review rejects the automated ADEQUATE decision because same-source resampler perf compared BANDLIMITED base against FAST head."},
        {"source_sha": "03a3bd9a85bb15e1a783ed78f4d2efc0b4bb966a", "url": "https://github.com/jiying2007/audio-pipeline/actions/runs/34039351719", "meaning": "Bounded comparator repair proves FAST-vs-FAST AP-cache-equivalent measurements: artifact 9991183617/digest b6c82e12... independently verified 2/2; all eight deltas collapse to about -0.21%..+0.17% with max |median delta| 0.000826 us. PR #122 remains unmerged because required Verify 34039351916 correctly enforces the release-bearing SemVer policy."}
      ]
    },
'''
assert s.count(old) == 1, s.count(old)
plan.write_text(s.replace(old, new))

program = Path('scripts/program.py')
p = program.read_text()
marker = '\ndef validate(plan: dict, root: Path | None = None) -> None:\n'
validator = r'''
def validate_i008_review_required(plan: dict, root: Path) -> None:
    by_id = {task["id"]: task for task in plan["tasks"]}
    i008 = by_id["I008"]
    if i008["status"] != "REVIEW_REQUIRED":
        return
    require(i008["handler"] is None and
            i008["contract"] == "docs/program/iterations/I008-review-required.json" and
            len(i008["evidence"]) == 2,
            "I008 REVIEW_REQUIRED must be frozen, evidence-backed and bound to reviewed result")
    c = json.loads(repo_file(root, i008["contract"]).read_text())
    require(c["schema_version"] == 1 and c["iteration_id"] == "I008" and
            c["state"] == "REVIEW_REQUIRED_RELEASE_BEARING_FIX" and
            c["lane"] == "engineering" and
            c["reviewed_from_main_sha"] == "54fd0cdb5ff7197748fa52d07e0cb83e465a6b57",
            "I008 review identity")
    require(c["shipping_baseline"] == {
                "release": "v2.3.12",
                "source_sha": plan["baseline"]["source_sha"],
                "unchanged": True,
            } and plan["baseline"]["software_release"] == "v2.3.12",
            "I008 review must keep shipping baseline")
    a = c["candidate_zero_audit"]
    require(a["pr"] == 121 and a["pr_closed"] is True and a["pr_merged"] is False and
            a["head_sha"] == "665f766c0519bd3d58b8381deae2381f30dcce97" and
            a["run_id"] == 34038886087 and a["run_conclusion"] == "success" and
            a["automated_decision"] == "ENGINEERING_BASELINE_ADEQUATE" and
            a["reviewed_decision"] == "ENGINEERING_GAP_REVIEW_REQUIRED",
            "I008 candidate-zero reviewed decision")
    eng = a["engineering_artifact"]
    require(eng["artifact_id"] == 9991073229 and
            eng["artifact_digest"] == "sha256:3f1f3b33f989cf617b0e9a58076d5b0ff89e84a03f1673ee2398ef2fc11af26c" and
            eng["independent_zip_sha256_verified"] is True and
            eng["internal_sha256s_verified"] == 20 and eng["job_status"] == "success",
            "I008 engineering artifact")
    arm = a["arm_qemu_artifact"]
    require(arm["artifact_id"] == 9991049048 and
            arm["artifact_digest"] == "sha256:e8294b5084577ea123f8a2c0f91bd360b1589338049900fe85bc2cf6c9fd0821" and
            arm["independent_zip_sha256_verified"] is True and
            arm["internal_sha256s_verified"] == 4 and arm["job_status"] == "success",
            "I008 ARM/QEMU artifact")
    lab = a["ordinary_user_lab_artifact"]
    require(lab["artifact_id"] == 9991080810 and
            lab["artifact_digest"] == "sha256:ece2a5fe18c34c514b6aea770fff48be25283c8520dae265c17167caf1bca7c5" and
            lab["independent_zip_sha256_verified"] is True and
            lab["source_revision"] == a["head_sha"] and
            all(lab[key] == "PASS" for key in
                ["audio_validation", "audio_target", "audio_builder", "certification_archive"]) and
            lab["idempotent"] is True and lab["system_path_writes"] is False,
            "I008 ordinary-user lab artifact")
    require(a["resource_metrics"] == {
                "pipeline_state_bytes": {"full": 78192, "low": 47024, "tiny": 25408, "raw": 1064},
                "runtime_state_bytes": {"full": 32752, "tiny": 5168},
                "consumer_elf_bytes": {"full": 3704, "voice": 3588, "raw": 3384},
                "cortex_a32_pipeline_rom_bytes": {"full": 34348, "tiny": 34120},
            }, "I008 resource metrics")
    bad = a["invalid_resampler_perf_evidence"]
    require(bad["base_project_default"] == "BANDLIMITED" and
            bad["head_explicit_mode"] == "FAST" and bad["same_product_source"] is True and
            bad["paired_delta_pct"] == [-89.435081, -83.860893, -82.778193, -82.698791,
                                        -78.901963, -72.245599, -89.976952, -83.725744] and
            bad["authority_after_review"] == "measurement-attribution-lineage-only",
            "I008 invalid comparator evidence attribution")
    r = c["root_cause"]
    require(r["id"] == "resampler-perf-base-head-backend-asymmetry" and
            r["file"] == "scripts/compare-resampler-perf.sh" and
            r["base_config_missing"] == "-DAP_RESAMPLER_MODE=FAST" and
            r["head_config_present"] == "-DAP_RESAMPLER_MODE=FAST" and
            r["cmake_default"] == "BANDLIMITED" and
            r["other_paired_comparators_have_symmetric_common_flags"] is True and
            r["shipping_dsp_defect"] is False,
            "I008 comparator root cause")
    f = c["verified_fix"]
    require(f["pr"] == 122 and f["pr_closed"] is True and f["pr_merged"] is False and
            f["head_sha"] == "03a3bd9a85bb15e1a783ed78f4d2efc0b4bb966a" and
            f["dedicated_run_id"] == 34039351719 and f["dedicated_run_conclusion"] == "success" and
            f["artifact_id"] == 9991183617 and
            f["artifact_digest"] == "sha256:b6c82e12e6e27529861e95cc3c1c29751d88d7d2d22522595c188524d1884ebd" and
            f["independent_zip_sha256_verified"] is True and f["internal_sha256s_verified"] == 2 and
            f["behavior_equivalent_ap_cache_required"] is True and
            f["base_mode"] == f["head_mode"] == "FAST" and
            f["repetitions"] == 7 and f["frames"] == 100000 and
            f["paired_delta_pct"] == [0.068688, -0.009317, -0.014095, 0.165614,
                                      -0.139386, -0.005558, -0.205423, 0.016036] and
            f["abs_delta_us"] == [0.000001, 0.000499, -0.000754, 0.000777,
                                   0.000391, 0.000650, -0.000361, -0.000826] and
            f["max_abs_delta_us"] == 0.000826 and
            f["former_72_to_90_percent_artifact_disappeared"] is True and
            f["hosted_real_audio_conclusion"] == f["hosted_real_aec_conclusion"] ==
            f["program_conclusion"] == "success",
            "I008 verified comparator fix evidence")
    b = c["release_policy_block"]
    require(b["verify_run_id"] == 34039351916 and b["verify_conclusion"] == "failure" and
            b["failed_job"] == "impact" and b["failed_step"] == "Select conservative CI impact" and
            b["policy_file"] == "scripts/ci_impact.py" and
            b["policy"] == "release-bearing change must advance SemVer" and
            b["base_version"] == b["head_version"] == "2.3.12" and
            b["release_bearing_path"] == "scripts/compare-resampler-perf.sh" and
            b["policy_preserved"] is True and
            b["comparator_whitelisted_release_neutral"] is False and
            b["fake_semver_bump_used"] is False,
            "I008 release-bearing policy block")
    d = c["review_decision"]
    require(d == {
                "status": "REVIEW_REQUIRED",
                "engineering_baseline_capabilities_passed": True,
                "performance_evidence_bug_root_caused": True,
                "fix_implementation_verified": True,
                "fix_authorized_to_merge_without_semver": False,
                "shipping_baseline_changed": False,
                "release_created": False,
                "candidate_limit_consumed": 0,
                "confirmation_limit_consumed": 0,
            }, "I008 reviewed decision")
    require(c["handoff"]["P002"]["authority"] ==
            "release-identity-and-ci-governance-context-only" and
            c["handoff"]["P002"]["may_bypass_semver_policy"] is False and
            c["authority_boundary"] == {
                "shipping_source_changed": False,
                "software_candidate_promoted": False,
                "release_created": False,
                "product_qualification": "DEFERRED_BY_SCOPE",
                "hardware_collection": False,
                "dut_hil": "DEFERRED_BY_SCOPE",
            }, "I008 authority boundary")

'''
assert p.count(marker) == 1, p.count(marker)
p = p.replace(marker, '\n' + validator + 'def validate(plan: dict, root: Path | None = None) -> None:\n')
old_calls = '''        validate_i006_closed(plan, root)
        validate_i009_closed(plan, root)
'''
new_calls = '''        validate_i006_closed(plan, root)
        validate_i009_closed(plan, root)
        validate_i008_review_required(plan, root)
'''
assert p.count(old_calls) == 1, p.count(old_calls)
p = p.replace(old_calls, new_calls)
old_self = '''    i002, p001, i003, i004, i005, i006 = (by_id["I002"], by_id["P001"], by_id["I003"],
                                           by_id["I004"], by_id["I005"], by_id["I006"])
'''
new_self = old_self + '''    i008 = by_id["I008"]
'''
assert p.count(old_self) == 1, p.count(old_self)
p = p.replace(old_self, new_self)
self_marker = '''    if i003["status"] == "PLANNED":
'''
self_block = '''    if i008["status"] == "PLANNED":
        require(i008["handler"] is None and i008["contract"] is None and not i008["evidence"],
                "planned I008 cannot have review/executable authority")
    elif i008["status"] == "REVIEW_REQUIRED":
        require(i008["handler"] is None and
                i008["contract"] == "docs/program/iterations/I008-review-required.json" and
                len(i008["evidence"]) == 2,
                "review-required I008 must be frozen, evidence-backed and non-executable")
    else:
        raise AssertionError("I008 must be PLANNED or evidence-backed REVIEW_REQUIRED in this phase")

'''
assert p.count(self_marker) == 1, p.count(self_marker)
p = p.replace(self_marker, self_block + self_marker)
p = p.replace(
    'program self-test: I002/P001/I003/I004/I005/I006 evidence-backed lifecycles + negative contracts OK',
    'program self-test: I002/P001/I003/I004/I005/I006/I008 evidence-backed lifecycles + negative contracts OK')
program.write_text(p)
