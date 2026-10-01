#!/usr/bin/env python3
"""Retire consumed valid I040 synthesis/overlap-add diagnostic."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import unittest

ROOT=Path(__file__).resolve().parents[2]
LIVE=ROOT/".github/workflows/research-i040-ns-synthesis-overlap-add-transfer-decomposition-v1.yml"
HISTORY=ROOT/"tests/validation/data/i040-consumed-workflow.yml"
CONTRACT=ROOT/(
    ".github/research/continuous-optimization/development-v4/"
    "i040-ns-synthesis-overlap-add-transfer-decomposition-v1.json"
)
RESULT=ROOT/(
    ".github/research/continuous-optimization/development-v4/"
    "i040-ns-synthesis-overlap-add-transfer-decomposition-v1-result.json"
)
EVIDENCE_ROOT=Path("validation/research/evidence/i040-36935646688")
HISTORY_BLOB="19bf48267ff4c121a73f468cbb9056c132a3e18a"


def git_blob(data: bytes) -> str:
    return hashlib.sha1(b"blob "+str(len(data)).encode()+b"\0"+data).hexdigest()


class I040RetirementTests(unittest.TestCase):
    def test_consumed_workflow_is_immutable_data(self):
        self.assertEqual(git_blob(HISTORY.read_bytes()),HISTORY_BLOB)
        text=HISTORY.read_text(encoding="utf-8")
        self.assertIn("  workflow_dispatch:\n",text)
        self.assertIn("  diagnose:\n",text)
        self.assertIn("Enforce one-shot I040 diagnostic execution",text)
        self.assertIn(
            "Materialize fresh I040 target public-development-v3 partitions",text)
        self.assertIn(
            "Evaluate candidate-zero synthesis-overlap-add transfer",text)
        self.assertIn(
            "'synthesis_overlap_add_transfer':r['synthesis_overlap_add_transfer']",
            text,
        )
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
        self.assertIn("test_i040_retirement.py",text)

    def test_reviewed_result_is_terminal_valid_and_hash_bound(self):
        result=json.loads(RESULT.read_text(encoding="utf-8"))
        contract=json.loads(CONTRACT.read_text(encoding="utf-8"))
        self.assertEqual(result["status"],"CLOSED_DIAGNOSTIC_ONLY")
        self.assertEqual(
            result["decision"],
            "NS_SYNTHESIS_OVERLAP_ADD_TRANSFER_DECOMPOSED_REVIEW_REQUIRED",
        )
        self.assertEqual(
            result["fresh_authority"]["target_seeds"],
            contract["fresh_diagnostic_authority"]["target_seeds"],
        )
        self.assertFalse(result["fresh_authority"]["rerun_allowed"])
        self.assertTrue(result["research_line_terminal"])
        self.assertIsNone(result["proposed_followup_hypothesis"])
        execution=result["authoritative_execution"]
        self.assertEqual(execution["run_id"],36935646688)
        self.assertEqual(execution["run_attempt"],1)
        self.assertEqual(
            execution["head_sha"],
            "e61ca2d76438ad017ea6cb01c50696f8cf468b81",
        )
        self.assertEqual(execution["artifact_id"],11198846570)
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
        self.assertTrue(packaging["evaluator_stderr_empty"])
        self.assertTrue(packaging["evaluate_exit_code_is_zero"])
        self.assertFalse(packaging["synthetic_repair_authorized"])
        self.assertFalse(packaging["rerun_required"])

    def test_all_preregistered_validity_gates_passed(self):
        result=json.loads(RESULT.read_text(encoding="utf-8"))
        mirror=result["shipping_mirror"]
        self.assertEqual(mirror["noise_rms_bitwise_mismatch_frames"],0)
        self.assertEqual(mirror["max_noise_rms_reconstruction_gap_db"],0)
        self.assertEqual(mirror["max_ns_upstream_gap_delta"],0)
        self.assertEqual(mirror["max_vad_probability_delta"],0)
        self.assertEqual(mirror["vad_active_mismatch_frames"],0)
        inv=result["transfer_invariants"]
        self.assertLessEqual(inv["max_post_ns_partition_energy_share_gap"],2e-5)
        self.assertLessEqual(
            inv["max_predicted_post_ns_partition_energy_share_gap"],2e-5)
        self.assertLessEqual(
            inv["max_suppression_attenuation_identity_gap_db"],2e-5)
        self.assertLessEqual(
            inv["max_predicted_suppressed_power_excess_db"],2e-5)
        self.assertEqual(inv["max_synthesis_output_abs_sample_delta"],0)
        self.assertEqual(inv["max_synthesis_output_rmse"],0)
        coverage=result["coverage_review"]
        self.assertEqual(coverage["target_cases"],252)
        self.assertGreaterEqual(coverage["causal_target_cases"],100)
        self.assertGreaterEqual(coverage["causal_anchor_cases"],35)
        self.assertGreaterEqual(coverage["causal_anchor_coverage"],0.25)
        self.assertEqual(
            coverage["fixed_horizon_coverage"],
            {"1":1,"2":1,"4":1,"8":1},
        )

    def test_synthesis_ola_completely_explains_residual(self):
        result=json.loads(RESULT.read_text(encoding="utf-8"))
        review=result["root_cause_review"]
        self.assertTrue(review["synthesis_overlap_add_exact_time_domain_mirror_supported"])
        self.assertTrue(
            review["synthesis_overlap_add_complete_residual_explanation_supported"])
        self.assertFalse(review["all_domain_synthesized_post_residual_persists"])
        self.assertFalse(review["low_domain_synthesized_post_residual_persists"])
        self.assertFalse(review["speech_domain_synthesized_post_residual_persists"])
        self.assertFalse(review["high_domain_synthesized_post_residual_persists"])
        horizons=result["fixed_horizon_synthesis_transfer_review"]
        self.assertEqual(list(horizons),["1","2","4","8"])
        for item in horizons.values():
            self.assertEqual(
                item["median_all_synthesized_vs_post_alignment_abs_error_db"],0)
            self.assertEqual(
                item["median_speech_synthesized_vs_post_alignment_abs_error_db"],0)
            self.assertEqual(
                item["median_low_synthesized_vs_post_alignment_abs_error_db"],0)
            self.assertEqual(
                item["median_high_synthesized_vs_post_alignment_abs_error_db"],0)
            self.assertEqual(
                item["p90_all_synthesized_vs_post_alignment_abs_error_db"],0)
            self.assertEqual(
                item["p90_speech_synthesized_vs_post_alignment_abs_error_db"],0)
            self.assertEqual(
                item["all_synthesized_post_direction_agreement_fraction"],1)
            self.assertEqual(
                item["speech_synthesized_post_direction_agreement_fraction"],1)
        self.assertTrue(all(
            value is False for value in result["authority_boundary"].values()
        ))


if __name__=="__main__":
    unittest.main()
