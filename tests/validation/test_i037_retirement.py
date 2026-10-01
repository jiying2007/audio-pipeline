#!/usr/bin/env python3
"""Retire consumed valid I037 exact-order aggregation diagnostic."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import unittest

ROOT=Path(__file__).resolve().parents[2]
LIVE=ROOT/".github/workflows/research-i037-ns-noise-estimate-aggregation-exact-order-recovery-v1.yml"
HISTORY=ROOT/"tests/validation/data/i037-consumed-workflow.yml"
CONTRACT=ROOT/(
    ".github/research/continuous-optimization/development-v4/"
    "i037-ns-noise-estimate-aggregation-exact-order-recovery-v1.json"
)
RESULT=ROOT/(
    ".github/research/continuous-optimization/development-v4/"
    "i037-ns-noise-estimate-aggregation-exact-order-recovery-v1-result.json"
)
EVIDENCE_ROOT=Path("validation/research/evidence/i037-36824635292")
HISTORY_BLOB="495a3b8e0538e6aa8ba2bbc8ac3c8047eca4feb2"


def git_blob(data: bytes) -> str:
    return hashlib.sha1(b"blob "+str(len(data)).encode()+b"\0"+data).hexdigest()


class I037RetirementTests(unittest.TestCase):
    def test_consumed_workflow_is_immutable_data(self):
        self.assertEqual(git_blob(HISTORY.read_bytes()),HISTORY_BLOB)
        text=HISTORY.read_text(encoding="utf-8")
        self.assertIn("  workflow_dispatch:\n",text)
        self.assertIn("  diagnose:\n",text)
        self.assertIn("Enforce one-shot I037 diagnostic execution",text)
        self.assertIn(
            "Materialize fresh I037 target public-development-v3 partitions",text)
        self.assertIn(
            "Evaluate candidate-zero exact-order aggregation recovery",text)

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
        self.assertIn("test_i037_retirement.py",text)

    def test_reviewed_result_is_terminal_valid_and_hash_bound(self):
        result=json.loads(RESULT.read_text(encoding="utf-8"))
        contract=json.loads(CONTRACT.read_text(encoding="utf-8"))
        self.assertEqual(result["status"],"CLOSED_DIAGNOSTIC_ONLY")
        self.assertEqual(
            result["decision"],
            "NS_NOISE_ESTIMATE_AGGREGATION_EXACT_ORDER_RECOVERED_REVIEW_REQUIRED",
        )
        self.assertEqual(
            result["fresh_authority"]["target_seeds"],
            contract["fresh_diagnostic_authority"]["target_seeds"],
        )
        self.assertFalse(result["fresh_authority"]["rerun_allowed"])
        execution=result["authoritative_execution"]
        self.assertEqual(execution["run_id"],36824635292)
        self.assertEqual(execution["run_attempt"],1)
        self.assertEqual(
            execution["head_sha"],
            "4204ae2fa9bff472ec2f70e42b6710b6e088bc74",
        )
        self.assertEqual(execution["artifact_id"],11144499769)
        self.assertEqual(execution["evaluator_return_code"],0)
        self.assertTrue(execution["evaluator_result_valid"])
        self.assertTrue(execution["internal_sha256sums_verified"])
        self.assertEqual(len(execution["member_sha256"]),11)
        self.assertEqual(
            execution["member_sha256"]["SHA256SUMS"],
            "29177958e610747e4d1606e0110e94146bbed4abdb9ae2634984c16cb0c39248",
        )
        self.assertEqual(
            result["original_result_path"],str(EVIDENCE_ROOT/"result.json"))

    def test_exact_order_recovery_is_bitwise_and_gate_valid(self):
        result=json.loads(RESULT.read_text(encoding="utf-8"))
        mirror=result["shipping_mirror"]
        self.assertEqual(mirror["noise_rms_bitwise_mismatch_frames"],0)
        self.assertEqual(mirror["max_noise_rms_reconstruction_gap_db"],0)
        self.assertEqual(mirror["max_ns_upstream_gap_delta"],0)
        self.assertEqual(mirror["max_vad_probability_delta"],0)
        self.assertEqual(mirror["vad_active_mismatch_frames"],0)
        coverage=result["coverage_review"]
        self.assertEqual(coverage["target_cases"],252)
        self.assertGreaterEqual(coverage["causal_target_cases"],100)
        self.assertGreaterEqual(coverage["causal_anchor_cases"],35)
        self.assertGreaterEqual(coverage["causal_anchor_coverage"],0.25)
        self.assertEqual(
            coverage["fixed_horizon_coverage"],
            {"1":1,"2":1,"4":1,"8":1},
        )

    def test_review_does_not_select_fixed_speech_band(self):
        result=json.loads(RESULT.read_text(encoding="utf-8"))
        review=result["root_cause_review"]
        self.assertTrue(review["exact_order_reconstruction_recovered"])
        self.assertTrue(review["i036_float_reduction_order_defect_confirmed"])
        self.assertFalse(
            review["simple_all_bin_aggregation_dilution_explanation_supported"])
        self.assertFalse(
            review["fixed_speech_band_consistently_improves_alignment"])
        self.assertTrue(review["speech_band_response_deficit_persists"])
        horizons=result["aggregation_review"]["fixed_horizons"]
        self.assertEqual(list(horizons),["1","2","4","8"])
        self.assertTrue(all(
            item["median_speech_vs_all_alignment_improvement_db"] < 0
            for item in horizons.values()
        ))
        self.assertTrue(all(
            item["speech_alignment_better_fraction"] < 0.5
            for item in horizons.values()
        ))
        self.assertTrue(all(
            item["median_speech_response_deficit_db"] > 0
            for item in horizons.values()
        ))
        self.assertTrue(all(
            value is False for value in result["authority_boundary"].values()
        ))

    def test_followup_is_matched_domain_diagnostic_only(self):
        result=json.loads(RESULT.read_text(encoding="utf-8"))
        follow=result["proposed_followup_hypothesis"]
        self.assertEqual(
            follow["id"],
            "i038-ns-post-ns-matched-domain-transfer-decomposition-v1",
        )
        self.assertEqual(follow["authority"],"CANDIDATE_ZERO_DIAGNOSTIC_ONLY")
        prohibited=set(follow["prohibited"])
        self.assertIn("spectral-band boundary search",prohibited)
        self.assertIn("estimator selection",prohibited)
        self.assertIn("normalization mapping selection",prohibited)
        self.assertIn("source candidate execution",prohibited)


if __name__=="__main__":
    unittest.main()
