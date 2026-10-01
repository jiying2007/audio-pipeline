#!/usr/bin/env python3
"""Retire consumed valid I039 suppression-transfer diagnostic."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import unittest

ROOT=Path(__file__).resolve().parents[2]
LIVE=ROOT/".github/workflows/research-i039-ns-suppression-transfer-path-decomposition-v1.yml"
HISTORY=ROOT/"tests/validation/data/i039-consumed-workflow.yml"
CONTRACT=ROOT/(
    ".github/research/continuous-optimization/development-v4/"
    "i039-ns-suppression-transfer-path-decomposition-v1.json"
)
RESULT=ROOT/(
    ".github/research/continuous-optimization/development-v4/"
    "i039-ns-suppression-transfer-path-decomposition-v1-result.json"
)
EVIDENCE_ROOT=Path("validation/research/evidence/i039-36861549133")
HISTORY_BLOB="a16bbb31e907eac85d7a8c92ca2f127dd373ae62"


def git_blob(data: bytes) -> str:
    return hashlib.sha1(b"blob "+str(len(data)).encode()+b"\0"+data).hexdigest()


class I039RetirementTests(unittest.TestCase):
    def test_consumed_workflow_is_immutable_data(self):
        self.assertEqual(git_blob(HISTORY.read_bytes()),HISTORY_BLOB)
        text=HISTORY.read_text(encoding="utf-8")
        self.assertIn("  workflow_dispatch:\n",text)
        self.assertIn("  diagnose:\n",text)
        self.assertIn("Enforce one-shot I039 diagnostic execution",text)
        self.assertIn(
            "Materialize fresh I039 target public-development-v3 partitions",text)
        self.assertIn(
            "Evaluate candidate-zero suppression-transfer path",text)
        self.assertIn(
            "'suppression_transfer_path':r['suppression_transfer_path']",text)
        self.assertIn("summary_rc=0",text)
        self.assertLess(
            text.index("while read -r file; do sha256sum"),
            text.index('if test "$summary_rc" -ne 0'),
        )

    def test_live_surface_is_contract_only(self):
        text=LIVE.read_text(encoding="utf-8")
        self.assertIn("\n  pull_request:\n",text)
        self.assertNotIn("\n  workflow_dispatch:\n",text)
        self.assertNotIn("\n  push:\n",text)
        self.assertNotIn("\n  schedule:\n",text)
        jobs=re.findall(
            r"(?m)^  ([A-Za-z_][A-Za-z0-9_-]*):\s*$",
            text[text.index("\njobs:")+1:],
        )
        self.assertEqual(jobs,["contract"])
        self.assertIn("test_i039_retirement.py",text)

    def test_reviewed_result_is_terminal_valid_and_hash_bound(self):
        result=json.loads(RESULT.read_text(encoding="utf-8"))
        contract=json.loads(CONTRACT.read_text(encoding="utf-8"))
        self.assertEqual(result["status"],"CLOSED_DIAGNOSTIC_ONLY")
        self.assertEqual(
            result["decision"],
            "NS_SUPPRESSION_TRANSFER_PATH_DECOMPOSED_REVIEW_REQUIRED",
        )
        self.assertEqual(
            result["fresh_authority"]["target_seeds"],
            contract["fresh_diagnostic_authority"]["target_seeds"],
        )
        self.assertFalse(result["fresh_authority"]["rerun_allowed"])
        execution=result["authoritative_execution"]
        self.assertEqual(execution["run_id"],36861549133)
        self.assertEqual(execution["run_attempt"],1)
        self.assertEqual(
            execution["head_sha"],
            "165688cbaabed8bc22c65ed5bbab33f83207ef0d",
        )
        self.assertEqual(execution["artifact_id"],11162786250)
        self.assertEqual(execution["evaluator_return_code"],0)
        self.assertTrue(execution["evaluator_result_valid"])
        self.assertEqual(len(execution["member_sha256"]),11)
        self.assertIn("summary.json",execution["member_sha256"])
        self.assertIn("SHA256SUMS",execution["member_sha256"])
        self.assertEqual(
            result["original_result_path"],str(EVIDENCE_ROOT/"result.json"))

    def test_packaging_is_complete_and_hash_bound(self):
        result=json.loads(RESULT.read_text(encoding="utf-8"))
        packaging=result["artifact_packaging_review"]
        self.assertTrue(packaging["research_result_valid"])
        self.assertTrue(packaging["packaging_completed"])
        self.assertEqual(packaging["original_artifact_member_count"],11)
        self.assertTrue(packaging["sha256_manifest_present"])
        self.assertTrue(packaging["sha256_manifest_verified"])
        self.assertTrue(packaging["summary_present"])
        self.assertFalse(packaging["synthetic_repair_authorized"])
        self.assertFalse(packaging["rerun_required"])
        self.assertTrue(packaging["evaluator_stderr_empty"])
        self.assertTrue(packaging["evaluate_exit_code_is_zero"])

    def test_all_preregistered_validity_gates_passed(self):
        result=json.loads(RESULT.read_text(encoding="utf-8"))
        mirror=result["shipping_mirror"]
        self.assertEqual(mirror["noise_rms_bitwise_mismatch_frames"],0)
        self.assertEqual(mirror["max_noise_rms_reconstruction_gap_db"],0)
        self.assertEqual(mirror["max_ns_upstream_gap_delta"],0)
        self.assertEqual(mirror["max_vad_probability_delta"],0)
        self.assertEqual(mirror["vad_active_mismatch_frames"],0)
        inv=result["transfer_invariants"]
        self.assertLessEqual(
            inv["max_post_ns_partition_energy_share_gap"],2e-5)
        self.assertLessEqual(
            inv["max_suppression_attenuation_identity_gap_db"],2e-5)
        self.assertLessEqual(
            inv["max_predicted_suppressed_power_excess_db"],2e-5)
        coverage=result["coverage_review"]
        self.assertEqual(coverage["target_cases"],252)
        self.assertGreaterEqual(coverage["causal_target_cases"],100)
        self.assertGreaterEqual(coverage["causal_anchor_cases"],35)
        self.assertGreaterEqual(coverage["causal_anchor_coverage"],0.25)
        self.assertEqual(
            coverage["fixed_horizon_coverage"],
            {"1":1,"2":1,"4":1,"8":1},
        )

    def test_suppression_is_partial_not_complete_explanation(self):
        result=json.loads(RESULT.read_text(encoding="utf-8"))
        review=result["root_cause_review"]
        self.assertTrue(
            review["instantaneous_suppression_partial_explanation_in_speech_domain_supported"])
        self.assertFalse(
            review["instantaneous_suppression_complete_explanation_supported"])
        self.assertTrue(review["all_domain_predicted_post_residual_persists"])
        self.assertTrue(review["speech_domain_predicted_post_residual_persists"])
        self.assertTrue(review["synthesis_or_overlap_add_transfer_not_yet_isolated"])
        horizons=result["fixed_horizon_suppression_transfer_review"]
        self.assertEqual(list(horizons),["1","2","4","8"])
        speech_improved=0
        all_improved=0
        for item in horizons.values():
            if (
                item["median_speech_predicted_vs_post_alignment_abs_error_db"]
                < item["median_speech_tracker_vs_post_alignment_abs_error_db"]
            ):
                speech_improved+=1
            if (
                item["median_all_predicted_vs_post_alignment_abs_error_db"]
                < item["median_all_tracker_vs_post_alignment_abs_error_db"]
            ):
                all_improved+=1
            self.assertGreater(
                item["median_speech_predicted_vs_post_alignment_abs_error_db"],4.0)
            self.assertGreater(
                item["median_all_predicted_vs_post_alignment_abs_error_db"],4.0)
        self.assertEqual(speech_improved,4)
        self.assertEqual(all_improved,1)
        self.assertTrue(all(
            value is False for value in result["authority_boundary"].values()
        ))

    def test_followup_is_synthesis_ola_diagnostic_only(self):
        result=json.loads(RESULT.read_text(encoding="utf-8"))
        follow=result["proposed_followup_hypothesis"]
        self.assertEqual(
            follow["id"],
            "i040-ns-synthesis-overlap-add-transfer-decomposition-v1",
        )
        self.assertEqual(follow["authority"],"CANDIDATE_ZERO_DIAGNOSTIC_ONLY")
        prohibited=set(follow["prohibited"])
        self.assertIn("spectral-band or domain selection",prohibited)
        self.assertIn("window or overlap-add selection/tuning",prohibited)
        self.assertIn("NS floor or suppression-gain tuning",prohibited)
        self.assertIn("source candidate execution",prohibited)


if __name__=="__main__":
    unittest.main()
