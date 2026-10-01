#!/usr/bin/env python3
"""Retire consumed invalid I036 aggregation-domain diagnostic."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import unittest

ROOT=Path(__file__).resolve().parents[2]
LIVE=ROOT/".github/workflows/research-i036-ns-noise-estimate-aggregation-domain-decomposition-v1.yml"
HISTORY=ROOT/"tests/validation/data/i036-consumed-workflow.yml"
CONTRACT=ROOT/(
    ".github/research/continuous-optimization/development-v4/"
    "i036-ns-noise-estimate-aggregation-domain-decomposition-v1.json"
)
RESULT=ROOT/(
    ".github/research/continuous-optimization/development-v4/"
    "i036-ns-noise-estimate-aggregation-domain-decomposition-v1-result.json"
)
EVIDENCE_ROOT=Path("validation/research/evidence/i036-36803529573")
HISTORY_BLOB="0c2fac2067b6217f1cdc697018e9b87ad5dee371"


def git_blob(data: bytes) -> str:
    return hashlib.sha1(b"blob "+str(len(data)).encode()+b"\0"+data).hexdigest()


class I036RetirementTests(unittest.TestCase):
    def test_consumed_workflow_is_immutable_data(self):
        self.assertEqual(git_blob(HISTORY.read_bytes()),HISTORY_BLOB)
        text=HISTORY.read_text(encoding="utf-8")
        self.assertIn("  workflow_dispatch:\n",text)
        self.assertIn("  diagnose:\n",text)
        self.assertIn("Enforce one-shot I036 diagnostic execution",text)
        self.assertIn(
            "Materialize fresh I036 target public-development-v3 partitions",
            text,
        )
        self.assertIn(
            "Evaluate candidate-zero NS aggregation-domain decomposition",
            text,
        )
        self.assertIn("printf '%s\\n' \"$rc\"",text)
        self.assertIn("-printf '%f\\n'",text)

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
        self.assertIn("test_i036_retirement.py",text)

    def test_reviewed_result_is_terminal_invalid_and_hash_bound(self):
        result=json.loads(RESULT.read_text(encoding="utf-8"))
        contract=json.loads(CONTRACT.read_text(encoding="utf-8"))
        self.assertEqual(result["status"],"CLOSED_INVALID_DIAGNOSTIC_ONLY")
        self.assertEqual(result["decision"],"I036_INPUT_INVALID_REVIEW_REQUIRED")
        self.assertEqual(
            result["reviewed_decision"],
            "NUMERIC_RECONSTRUCTION_GATE_FAILED_FLOAT_REDUCTION_ORDER_NO_AGGREGATION_MECHANISM_VERDICT",
        )
        self.assertEqual(
            result["fresh_authority"]["target_seeds"],
            contract["fresh_diagnostic_authority"]["target_seeds"],
        )
        self.assertFalse(result["fresh_authority"]["rerun_allowed"])
        execution=result["authoritative_execution"]
        self.assertEqual(execution["run_id"],36803529573)
        self.assertEqual(execution["artifact_id"],11137255580)
        self.assertEqual(execution["evaluator_return_code"],2)
        self.assertFalse(execution["evaluator_input_valid"])
        self.assertTrue(execution["internal_sha256sums_verified"])
        self.assertEqual(len(execution["member_sha256"]),11)
        self.assertEqual(
            execution["member_sha256"]["SHA256SUMS"],
            "e600fe5e84cfc295033fd9c87f7e65b2949c923104553bb7ed9087649ee336e6",
        )
        self.assertEqual(
            result["original_result_path"],str(EVIDENCE_ROOT/"result.json"))

    def test_only_reconstruction_gate_failed(self):
        result=json.loads(RESULT.read_text(encoding="utf-8"))
        invalid=result["invalidity_review"]
        self.assertEqual(invalid["invalid_reasons"],["noise_rms_reconstruction"])
        self.assertEqual(
            invalid["preregistered_max_noise_rms_reconstruction_gap_db"],
            1e-05,
        )
        self.assertEqual(
            invalid["observed_max_noise_rms_reconstruction_gap_db"],
            1.52587891e-05,
        )
        self.assertGreater(
            invalid["observed_max_noise_rms_reconstruction_gap_db"],
            invalid["preregistered_max_noise_rms_reconstruction_gap_db"],
        )
        self.assertTrue(invalid["all_other_preregistered_validity_gates_passed"])
        self.assertFalse(invalid["post_hoc_gate_relaxation_authorized"])
        self.assertFalse(invalid["descriptive_result_promotion_authorized"])

        coverage=result["coverage_review"]
        self.assertEqual(coverage["target_cases"],252)
        self.assertGreaterEqual(coverage["causal_target_cases"],100)
        self.assertGreaterEqual(coverage["causal_anchor_cases"],35)
        self.assertGreaterEqual(coverage["causal_anchor_coverage"],0.25)
        self.assertEqual(
            coverage["fixed_horizon_coverage"],
            {"1":1,"2":1,"4":1,"8":1},
        )
        mirror=result["shipping_mirror"]
        self.assertEqual(mirror["max_ns_upstream_gap_delta"],0)
        self.assertEqual(mirror["max_vad_probability_delta"],0)
        self.assertEqual(mirror["vad_active_mismatch_frames"],0)

    def test_float_reduction_order_defect_is_not_reclassified_as_valid(self):
        result=json.loads(RESULT.read_text(encoding="utf-8"))
        review=result["instrumentation_review"]
        self.assertTrue(review["floating_reduction_order_changed"])
        self.assertEqual(
            review["retained_receipt_reconstruction_gap_values_db"],
            [0,3.81469727e-06,7.62939453e-06,1.14440918e-05],
        )
        self.assertEqual(review["full_frame_maximum_db"],1.52587891e-05)
        desc=result["descriptive_only_non_authoritative"]
        self.assertIn("debugging only",desc["note"])
        self.assertFalse(
            result["invalidity_review"]["descriptive_result_promotion_authorized"]
        )
        self.assertTrue(all(
            value is False for value in result["authority_boundary"].values()
        ))

    def test_i037_followup_is_exact_order_recovery_only(self):
        result=json.loads(RESULT.read_text(encoding="utf-8"))
        follow=result["proposed_followup_hypothesis"]
        self.assertEqual(
            follow["id"],
            "i037-ns-noise-estimate-aggregation-exact-order-recovery-v1",
        )
        self.assertEqual(follow["authority"],"CANDIDATE_ZERO_DIAGNOSTIC_ONLY")
        prohibited=set(follow["prohibited"])
        self.assertIn("reuse of I036 seeds",prohibited)
        self.assertIn(
            "post-hoc relaxation of the I036 reconstruction gate",prohibited)
        self.assertIn("spectral-band boundary search",prohibited)
        self.assertIn("estimator selection",prohibited)
        self.assertIn("tracker alpha tuning or search",prohibited)
        self.assertIn("best-horizon or best-lag selection",prohibited)


if __name__=="__main__":
    unittest.main()
