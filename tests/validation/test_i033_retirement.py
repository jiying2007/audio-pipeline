#!/usr/bin/env python3
"""Retire consumed valid I033 causal NS/VAD noise-delta diagnostic."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import unittest

ROOT=Path(__file__).resolve().parents[2]
LIVE=ROOT/".github/workflows/research-i033-ns-vad-causal-noise-delta-alignment-v1.yml"
HISTORY=ROOT/"tests/validation/data/i033-consumed-workflow.yml"
CONTRACT=ROOT/(
    ".github/research/continuous-optimization/development-v4/"
    "i033-ns-vad-causal-noise-delta-alignment-v1.json"
)
RESULT=ROOT/(
    ".github/research/continuous-optimization/development-v4/"
    "i033-ns-vad-causal-noise-delta-alignment-v1-result.json"
)
EVIDENCE_ROOT=Path("validation/research/evidence/i033-36719045384")
HISTORY_BLOB="1cfd40654740c0cfb5fc7ff3a30c52986da52bfa"


def git_blob(data: bytes) -> str:
    return hashlib.sha1(b"blob "+str(len(data)).encode()+b"\0"+data).hexdigest()


class I033RetirementTests(unittest.TestCase):
    def test_consumed_workflow_is_immutable_data(self):
        self.assertEqual(git_blob(HISTORY.read_bytes()),HISTORY_BLOB)
        text=HISTORY.read_text(encoding="utf-8")
        self.assertIn("  workflow_dispatch:\n",text)
        self.assertIn("  diagnose:\n",text)
        self.assertIn("Enforce one-shot I033 diagnostic execution",text)
        self.assertIn(
            "Materialize fresh I033 target public-development-v3 partitions",
            text,
        )
        self.assertIn(
            "Evaluate candidate-zero NS/VAD causal noise-delta alignment",
            text,
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
        self.assertIn("test_i033_retirement.py",text)

    def test_reviewed_negative_result_is_terminal(self):
        result=json.loads(RESULT.read_text(encoding="utf-8"))
        contract=json.loads(CONTRACT.read_text(encoding="utf-8"))
        self.assertEqual(result["status"],"CLOSED_DIAGNOSTIC_ONLY")
        self.assertEqual(
            result["decision"],
            "NS_VAD_CAUSAL_NOISE_DELTA_ALIGNMENT_DECOMPOSED_REVIEW_REQUIRED",
        )
        self.assertEqual(
            result["reviewed_decision"],
            "RELATIVE_NS_TO_POST_NS_NOISE_DELTA_ALIGNMENT_NOT_SUPPORTED_NO_REFRESH_MAPPING_OR_SOURCE_CANDIDATE",
        )
        self.assertEqual(
            result["fresh_authority"]["target_seeds"],
            contract["fresh_diagnostic_authority"]["target_seeds"],
        )
        self.assertFalse(result["fresh_authority"]["rerun_allowed"])
        self.assertEqual(result["authoritative_execution"]["run_id"],36719045384)
        self.assertEqual(result["authoritative_execution"]["artifact_id"],11099050975)
        self.assertTrue(result["authoritative_execution"]["evaluator_result_valid"])
        self.assertEqual(result["authoritative_execution"]["evaluator_return_code"],0)
        self.assertEqual(
            result["original_result_path"],str(EVIDENCE_ROOT/"result.json"))

    def test_preregistered_relative_delta_hypothesis_is_rejected(self):
        result=json.loads(RESULT.read_text(encoding="utf-8"))
        review=result["delta_alignment_review"]
        self.assertEqual(review["cases"],39)
        self.assertFalse(review["supported"])
        self.assertGreater(
            review["median_absolute_delta_error_db"],
            review["preregistered_maximum_median_absolute_delta_error_db"],
        )
        self.assertGreater(
            review["p90_absolute_delta_error_db"],
            review["preregistered_maximum_p90_absolute_delta_error_db"],
        )
        self.assertFalse(result["root_cause_review"]["relative_delta_alignment_supported"])
        self.assertFalse(result["authority_boundary"]["vad_noise_state_refresh_selected"])
        self.assertFalse(result["authority_boundary"]["mapping_selected"])

    def test_coverage_and_shipping_mirrors_remain_valid(self):
        result=json.loads(RESULT.read_text(encoding="utf-8"))
        coverage=result["coverage_review"]
        self.assertEqual(coverage["target_cases"],252)
        self.assertGreaterEqual(coverage["causal_target_cases"],100)
        self.assertGreaterEqual(coverage["causal_anchor_cases"],35)
        self.assertGreaterEqual(coverage["causal_anchor_coverage"],0.25)
        self.assertGreaterEqual(coverage["post_target_benchmark_coverage"],0.8)
        self.assertEqual(result["shipping_mirror"]["max_ns_upstream_gap_delta"],0)
        self.assertEqual(result["shipping_mirror"]["max_vad_probability_delta"],0)
        self.assertEqual(result["shipping_mirror"]["vad_active_mismatch_frames"],0)

    def test_packaging_failure_is_recorded_without_research_rerun(self):
        result=json.loads(RESULT.read_text(encoding="utf-8"))
        packaging=result["artifact_packaging_review"]
        self.assertTrue(packaging["research_result_valid"])
        self.assertTrue(packaging["packaging_step_failed_after_evaluator_success"])
        self.assertTrue(packaging["sha256sums_member_empty"])
        self.assertTrue(packaging["summary_json_has_literal_backslash_n_suffix"])
        self.assertTrue(packaging["evaluate_exit_code_bytes_represent_literal_zero_backslash_n"])
        self.assertTrue(packaging["build_info_has_literal_backslash_n_suffix"])
        self.assertTrue(packaging["evaluator_stderr_empty"])
        self.assertFalse(packaging["rerun_required"])
        self.assertEqual(
            result["authoritative_execution"]["member_sha256"]["SHA256SUMS"],
            "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        )

    def test_dynamic_followup_remains_diagnostic_only(self):
        result=json.loads(RESULT.read_text(encoding="utf-8"))
        dynamic=result["descriptive_dynamic_review"]
        self.assertLess(dynamic["median_absolute_causal_ns_delta_db"],1.0)
        self.assertGreater(dynamic["median_absolute_future_local_delta_db"],6.0)
        self.assertEqual(
            dynamic["authority"],
            "post-hoc descriptive only; cannot select a lag, smoothing constant, refresh rule, mapping or candidate",
        )
        follow=result["proposed_followup_hypothesis"]
        self.assertEqual(
            follow["id"],
            "i034-ns-vad-noise-state-temporal-response-decomposition-v1",
        )
        self.assertEqual(follow["authority"],"CANDIDATE_ZERO_DIAGNOSTIC_ONLY")
        prohibited=set(follow["prohibited"])
        self.assertIn("best-lag or best-horizon selection",prohibited)
        self.assertIn("tracker alpha tuning",prohibited)
        self.assertIn("VAD noise-state refresh source patch",prohibited)
        self.assertTrue(all(
            value is False for value in result["authority_boundary"].values()
        ))


if __name__=="__main__":
    unittest.main()
