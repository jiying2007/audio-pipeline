#!/usr/bin/env python3
"""Retire consumed valid I034 NS/VAD temporal-response diagnostic."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import unittest

ROOT=Path(__file__).resolve().parents[2]
LIVE=ROOT/".github/workflows/research-i034-ns-vad-noise-state-temporal-response-decomposition-v1.yml"
HISTORY=ROOT/"tests/validation/data/i034-consumed-workflow.yml"
CONTRACT=ROOT/(
    ".github/research/continuous-optimization/development-v4/"
    "i034-ns-vad-noise-state-temporal-response-decomposition-v1.json"
)
RESULT=ROOT/(
    ".github/research/continuous-optimization/development-v4/"
    "i034-ns-vad-noise-state-temporal-response-decomposition-v1-result.json"
)
EVIDENCE_ROOT=Path("validation/research/evidence/i034-36784701187")
HISTORY_BLOB="e4b5f6c1d8b9dbe735a7d8b7486ead2fa487cb0d"


def git_blob(data: bytes) -> str:
    return hashlib.sha1(b"blob "+str(len(data)).encode()+b"\0"+data).hexdigest()


class I034RetirementTests(unittest.TestCase):
    def test_consumed_workflow_is_immutable_data(self):
        self.assertEqual(git_blob(HISTORY.read_bytes()),HISTORY_BLOB)
        text=HISTORY.read_text(encoding="utf-8")
        self.assertIn("  workflow_dispatch:\n",text)
        self.assertIn("  diagnose:\n",text)
        self.assertIn("Enforce one-shot I034 diagnostic execution",text)
        self.assertIn(
            "Materialize fresh I034 target public-development-v3 partitions",
            text,
        )
        self.assertIn(
            "Evaluate candidate-zero NS/VAD temporal response decomposition",
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
        self.assertIn("test_i034_retirement.py",text)

    def test_reviewed_result_is_terminal_and_hash_bound(self):
        result=json.loads(RESULT.read_text(encoding="utf-8"))
        contract=json.loads(CONTRACT.read_text(encoding="utf-8"))
        self.assertEqual(result["status"],"CLOSED_DIAGNOSTIC_ONLY")
        self.assertEqual(
            result["decision"],
            "NS_VAD_NOISE_STATE_TEMPORAL_RESPONSE_DECOMPOSED_REVIEW_REQUIRED",
        )
        self.assertEqual(
            result["reviewed_decision"],
            "FIXED_HORIZON_TEMPORAL_CATCHUP_NOT_OBSERVED_PERSISTENT_NS_RESPONSE_AMPLITUDE_GAP_NO_LAG_ALPHA_MAPPING_CANDIDATE",
        )
        self.assertEqual(
            result["fresh_authority"]["target_seeds"],
            contract["fresh_diagnostic_authority"]["target_seeds"],
        )
        self.assertFalse(result["fresh_authority"]["rerun_allowed"])
        execution=result["authoritative_execution"]
        self.assertEqual(execution["run_id"],36784701187)
        self.assertEqual(execution["artifact_id"],11129761829)
        self.assertEqual(execution["evaluator_return_code"],0)
        self.assertTrue(execution["evaluator_result_valid"])
        self.assertTrue(execution["internal_sha256sums_verified"])
        self.assertEqual(len(execution["member_sha256"]),11)
        self.assertEqual(
            execution["member_sha256"]["SHA256SUMS"],
            "7e57af547a8d462cb3b8be011c805cc6fdf958df1cf81734b54c8558c464cd12",
        )
        self.assertEqual(
            result["original_result_path"],str(EVIDENCE_ROOT/"result.json"))

    def test_coverage_and_shipping_mirrors_are_valid(self):
        result=json.loads(RESULT.read_text(encoding="utf-8"))
        coverage=result["coverage_review"]
        self.assertEqual(coverage["target_cases"],252)
        self.assertGreaterEqual(coverage["causal_target_cases"],100)
        self.assertGreaterEqual(coverage["causal_anchor_cases"],35)
        self.assertGreaterEqual(coverage["causal_anchor_coverage"],0.25)
        self.assertEqual(
            coverage["fixed_horizon_coverage"],
            {"1":1,"2":1,"4":1,"8":1},
        )
        self.assertTrue(
            coverage["all_noise_domains_have_full_fixed_horizon_coverage"])
        self.assertEqual(result["shipping_mirror"]["max_ns_upstream_gap_delta"],0)
        self.assertEqual(result["shipping_mirror"]["max_vad_probability_delta"],0)
        self.assertEqual(result["shipping_mirror"]["vad_active_mismatch_frames"],0)

    def test_fixed_horizons_do_not_show_monotonic_catchup(self):
        result=json.loads(RESULT.read_text(encoding="utf-8"))
        review=result["temporal_response_review"]
        self.assertEqual(review["reference_horizons"],[1,2,4,8])
        global_review=review["global"]
        ratios=[
            global_review[str(h)]["median_abs_response_ratio_ns_over_local"]
            for h in (1,2,4,8)
        ]
        self.assertLess(max(ratios),0.25)
        errors=[
            global_review[str(h)]["median_absolute_alignment_error_db"]
            for h in (1,2,4,8)
        ]
        self.assertEqual(errors,review["median_alignment_error_progression_db"])
        self.assertGreater(errors[3],errors[2])
        self.assertFalse(review["monotonic_temporal_catchup_observed"])
        self.assertFalse(review["best_horizon_selected"])
        self.assertFalse(
            result["root_cause_review"]["lag_only_explanation_supported"])
        self.assertTrue(
            result["root_cause_review"]["persistent_response_amplitude_gap_observed"])

    def test_i035_followup_is_update_regime_decomposition_only(self):
        result=json.loads(RESULT.read_text(encoding="utf-8"))
        follow=result["proposed_followup_hypothesis"]
        self.assertEqual(
            follow["id"],
            "i035-ns-noise-tracker-update-regime-decomposition-v1",
        )
        self.assertEqual(follow["authority"],"CANDIDATE_ZERO_DIAGNOSTIC_ONLY")
        prohibited=set(follow["prohibited"])
        self.assertIn("tracker alpha tuning or search",prohibited)
        self.assertIn("tracker branch-threshold tuning",prohibited)
        self.assertIn("best-horizon or best-lag selection",prohibited)
        self.assertIn("VAD noise-state refresh source patch",prohibited)
        self.assertTrue(all(
            value is False for value in result["authority_boundary"].values()
        ))


if __name__=="__main__":
    unittest.main()
