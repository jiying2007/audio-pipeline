#!/usr/bin/env python3
"""Retire consumed valid I038 matched-domain diagnostic with packaging defect."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import unittest

ROOT=Path(__file__).resolve().parents[2]
LIVE=ROOT/".github/workflows/research-i038-ns-post-ns-matched-domain-transfer-decomposition-v1.yml"
HISTORY=ROOT/"tests/validation/data/i038-consumed-workflow.yml"
CONTRACT=ROOT/(
    ".github/research/continuous-optimization/development-v4/"
    "i038-ns-post-ns-matched-domain-transfer-decomposition-v1.json"
)
RESULT=ROOT/(
    ".github/research/continuous-optimization/development-v4/"
    "i038-ns-post-ns-matched-domain-transfer-decomposition-v1-result.json"
)
EVIDENCE_ROOT=Path("validation/research/evidence/i038-36849477777")
HISTORY_BLOB="4e1466f1c5f7b171003ef8a617e82020335c2f8b"


def git_blob(data: bytes) -> str:
    return hashlib.sha1(b"blob "+str(len(data)).encode()+b"\0"+data).hexdigest()


class I038RetirementTests(unittest.TestCase):
    def test_consumed_workflow_is_immutable_data(self):
        self.assertEqual(git_blob(HISTORY.read_bytes()),HISTORY_BLOB)
        text=HISTORY.read_text(encoding="utf-8")
        self.assertIn("  workflow_dispatch:\n",text)
        self.assertIn("  diagnose:\n",text)
        self.assertIn("Enforce one-shot I038 diagnostic execution",text)
        self.assertIn(
            "Materialize fresh I038 target public-development-v3 partitions",text)
        self.assertIn(
            "Evaluate candidate-zero post-NS matched-domain transfer",text)
        self.assertIn("'aggregation_domain':r['aggregation_domain']",text)

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
        self.assertIn("test_i038_retirement.py",text)

    def test_reviewed_result_is_terminal_valid_and_hash_bound(self):
        result=json.loads(RESULT.read_text(encoding="utf-8"))
        contract=json.loads(CONTRACT.read_text(encoding="utf-8"))
        self.assertEqual(result["status"],"CLOSED_DIAGNOSTIC_ONLY")
        self.assertEqual(
            result["decision"],
            "NS_POST_NS_MATCHED_DOMAIN_TRANSFER_DECOMPOSED_REVIEW_REQUIRED",
        )
        self.assertEqual(
            result["fresh_authority"]["target_seeds"],
            contract["fresh_diagnostic_authority"]["target_seeds"],
        )
        self.assertFalse(result["fresh_authority"]["rerun_allowed"])
        execution=result["authoritative_execution"]
        self.assertEqual(execution["run_id"],36849477777)
        self.assertEqual(execution["run_attempt"],1)
        self.assertEqual(
            execution["head_sha"],
            "3142ebb7d7a872344a2360486aa97832f0c47a11",
        )
        self.assertEqual(execution["artifact_id"],11156030612)
        self.assertEqual(execution["evaluator_return_code"],0)
        self.assertTrue(execution["evaluator_result_valid"])
        self.assertEqual(len(execution["member_sha256"]),9)
        self.assertNotIn("summary.json",execution["member_sha256"])
        self.assertNotIn("SHA256SUMS",execution["member_sha256"])
        self.assertEqual(
            result["original_result_path"],str(EVIDENCE_ROOT/"result.json"))

    def test_packaging_failure_does_not_invalidate_research(self):
        result=json.loads(RESULT.read_text(encoding="utf-8"))
        packaging=result["artifact_packaging_review"]
        self.assertTrue(packaging["research_result_valid"])
        self.assertTrue(packaging["packaging_step_failed_after_evaluator_success"])
        self.assertEqual(
            packaging["missing_members"],["SHA256SUMS","summary.json"])
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
        self.assertLessEqual(
            mirror["max_post_ns_partition_energy_share_gap"],2e-5)
        coverage=result["coverage_review"]
        self.assertEqual(coverage["target_cases"],252)
        self.assertGreaterEqual(coverage["causal_target_cases"],100)
        self.assertGreaterEqual(coverage["causal_anchor_cases"],35)
        self.assertGreaterEqual(coverage["causal_anchor_coverage"],0.25)
        self.assertEqual(
            coverage["fixed_horizon_coverage"],
            {"1":1,"2":1,"4":1,"8":1},
        )

    def test_matched_domain_deficit_persists_without_selection(self):
        result=json.loads(RESULT.read_text(encoding="utf-8"))
        review=result["root_cause_review"]
        self.assertFalse(review["cross_domain_benchmark_artifact_explanation_supported"])
        self.assertTrue(review["matched_domain_response_deficit_persists"])
        self.assertTrue(review["tracker_response_magnitude_small_relative_to_post_ns"])
        horizons=result["fixed_horizon_matched_domain_review"]
        self.assertEqual(list(horizons),["1","2","4","8"])
        for item in horizons.values():
            self.assertGreater(item["median_all_matched_response_deficit_db"],0)
            self.assertGreater(item["median_speech_matched_response_deficit_db"],0)
            self.assertGreater(item["median_low_matched_response_deficit_db"],0)
            self.assertGreater(item["median_high_matched_response_deficit_db"],0)
            self.assertLess(item["median_all_tracker_to_post_ns_magnitude_ratio"],0.5)
            self.assertLess(item["median_speech_tracker_to_post_ns_magnitude_ratio"],0.5)
        self.assertTrue(all(
            value is False for value in result["authority_boundary"].values()
        ))

    def test_followup_is_suppression_transfer_diagnostic_only(self):
        result=json.loads(RESULT.read_text(encoding="utf-8"))
        follow=result["proposed_followup_hypothesis"]
        self.assertEqual(
            follow["id"],
            "i039-ns-suppression-transfer-path-decomposition-v1",
        )
        self.assertEqual(follow["authority"],"CANDIDATE_ZERO_DIAGNOSTIC_ONLY")
        prohibited=set(follow["prohibited"])
        self.assertIn("spectral-band or domain selection",prohibited)
        self.assertIn("estimator selection",prohibited)
        self.assertIn("normalization mapping selection",prohibited)
        self.assertIn("NS floor or suppression-gain tuning",prohibited)
        self.assertIn("source candidate execution",prohibited)


if __name__=="__main__":
    unittest.main()
