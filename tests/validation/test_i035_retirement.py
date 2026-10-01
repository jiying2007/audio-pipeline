#!/usr/bin/env python3
"""Retire consumed valid I035 NS noise-tracker update-regime diagnostic."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import unittest

ROOT=Path(__file__).resolve().parents[2]
LIVE=ROOT/".github/workflows/research-i035-ns-noise-tracker-update-regime-decomposition-v1.yml"
HISTORY=ROOT/"tests/validation/data/i035-consumed-workflow.yml"
CONTRACT=ROOT/(
    ".github/research/continuous-optimization/development-v4/"
    "i035-ns-noise-tracker-update-regime-decomposition-v1.json"
)
RESULT=ROOT/(
    ".github/research/continuous-optimization/development-v4/"
    "i035-ns-noise-tracker-update-regime-decomposition-v1-result.json"
)
EVIDENCE_ROOT=Path("validation/research/evidence/i035-36795467909")
HISTORY_BLOB="8bb16c0f1c38e12da804e319d5887e71d2c6b49e"


def git_blob(data: bytes) -> str:
    return hashlib.sha1(b"blob "+str(len(data)).encode()+b"\0"+data).hexdigest()


class I035RetirementTests(unittest.TestCase):
    def test_consumed_workflow_is_immutable_data(self):
        self.assertEqual(git_blob(HISTORY.read_bytes()),HISTORY_BLOB)
        text=HISTORY.read_text(encoding="utf-8")
        self.assertIn("  workflow_dispatch:\n",text)
        self.assertIn("  diagnose:\n",text)
        self.assertIn("Enforce one-shot I035 diagnostic execution",text)
        self.assertIn(
            "Materialize fresh I035 target public-development-v3 partitions",
            text,
        )
        self.assertIn(
            "Evaluate candidate-zero NS tracker update-regime decomposition",
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
        self.assertIn("test_i035_retirement.py",text)

    def test_reviewed_result_is_terminal_and_hash_bound(self):
        result=json.loads(RESULT.read_text(encoding="utf-8"))
        contract=json.loads(CONTRACT.read_text(encoding="utf-8"))
        self.assertEqual(result["status"],"CLOSED_DIAGNOSTIC_ONLY")
        self.assertEqual(
            result["decision"],
            "NS_NOISE_TRACKER_UPDATE_REGIME_DECOMPOSED_REVIEW_REQUIRED",
        )
        self.assertEqual(
            result["reviewed_decision"],
            "FAST_UPDATE_DOMINATES_NOISE_ESTIMATE_MOVEMENT_RESPONSE_DEFICIT_PERSISTS_NO_ALPHA_THRESHOLD_OR_LAG_CANDIDATE",
        )
        self.assertEqual(
            result["fresh_authority"]["target_seeds"],
            contract["fresh_diagnostic_authority"]["target_seeds"],
        )
        self.assertFalse(result["fresh_authority"]["rerun_allowed"])
        execution=result["authoritative_execution"]
        self.assertEqual(execution["run_id"],36795467909)
        self.assertEqual(execution["artifact_id"],11133847821)
        self.assertEqual(execution["evaluator_return_code"],0)
        self.assertTrue(execution["evaluator_result_valid"])
        self.assertTrue(execution["internal_sha256sums_verified"])
        self.assertEqual(len(execution["member_sha256"]),11)
        self.assertEqual(
            execution["member_sha256"]["SHA256SUMS"],
            "8043e8ca01183076d9891d43a7df0732e3c6de40f5f1b236bec827c16cc99c4e",
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
        self.assertEqual(result["shipping_mirror"]["max_ns_upstream_gap_delta"],0)
        self.assertEqual(result["shipping_mirror"]["max_vad_probability_delta"],0)
        self.assertEqual(result["shipping_mirror"]["vad_active_mismatch_frames"],0)

    def test_fast_update_dominates_but_deficit_persists(self):
        result=json.loads(RESULT.read_text(encoding="utf-8"))
        review=result["fixed_horizon_regime_review"]
        for horizon in ("1","2","4","8"):
            row=review[horizon]
            self.assertGreater(row["median_fast_update_bin_fraction"],0.90)
            self.assertGreater(
                row["median_fast_update_abs_contribution_fraction"],0.99)
            self.assertGreater(row["median_response_deficit_db"],2.0)
            self.assertLess(
                row["spearman_slow_update_bin_fraction_vs_response_deficit"],0.0)
        self.assertFalse(
            result["root_cause_review"]
            ["simple_slow_update_gating_explanation_supported"])
        self.assertTrue(
            result["root_cause_review"]["fast_update_opportunity_dominant"])
        self.assertTrue(
            result["root_cause_review"]
            ["response_deficit_persists_with_fast_update_opportunity"])

    def test_i036_followup_is_aggregation_domain_decomposition_only(self):
        result=json.loads(RESULT.read_text(encoding="utf-8"))
        follow=result["proposed_followup_hypothesis"]
        self.assertEqual(
            follow["id"],
            "i036-ns-noise-estimate-aggregation-domain-decomposition-v1",
        )
        self.assertEqual(follow["authority"],"CANDIDATE_ZERO_DIAGNOSTIC_ONLY")
        prohibited=set(follow["prohibited"])
        self.assertIn("spectral-band boundary search",prohibited)
        self.assertIn("tracker alpha tuning or search",prohibited)
        self.assertIn("tracker branch-threshold tuning",prohibited)
        self.assertIn("best-horizon or best-lag selection",prohibited)
        self.assertIn("VAD noise-state refresh source patch",prohibited)
        self.assertTrue(all(
            value is False for value in result["authority_boundary"].values()
        ))


if __name__=="__main__":
    unittest.main()
