#!/usr/bin/env python3
"""Retire consumed valid I030 donor-stability diagnostic and bind reviewed closure."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import unittest

ROOT=Path(__file__).resolve().parents[2]
LIVE=ROOT/".github/workflows/research-i030-ns-upstream-donor-joint-residual-stability-decomposition-v1.yml"
HISTORY=ROOT/"tests/validation/data/i030-consumed-workflow.yml"
CONTRACT=ROOT/(
    ".github/research/continuous-optimization/development-v4/"
    "i030-ns-upstream-donor-joint-residual-stability-decomposition-v1.json"
)
RESULT=ROOT/(
    ".github/research/continuous-optimization/development-v4/"
    "i030-ns-upstream-donor-joint-residual-stability-decomposition-v1-result.json"
)
EVIDENCE_ROOT=Path("validation/research/evidence/i030-36654157293")
HISTORY_BLOB="5ccd71d7aa295b29d72951ef21f7cd9551669ba9"


def git_blob(data: bytes) -> str:
    return hashlib.sha1(b"blob "+str(len(data)).encode()+b"\0"+data).hexdigest()


class I030RetirementTests(unittest.TestCase):
    def test_consumed_workflow_is_immutable_data(self):
        self.assertEqual(git_blob(HISTORY.read_bytes()),HISTORY_BLOB)
        text=HISTORY.read_text(encoding="utf-8")
        self.assertIn("  workflow_dispatch:\n",text)
        self.assertIn("  diagnose:\n",text)
        self.assertIn("Enforce one-shot I030 diagnostic execution",text)
        self.assertIn(
            "Materialize fresh I030 donor and target public-development-v3 partitions",
            text,
        )
        self.assertIn(
            "Evaluate candidate-zero donor joint-residual stability decomposition",
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
        self.assertIn("test_i030_retirement.py",text)

    def test_reviewed_stability_decomposition_is_terminal(self):
        result=json.loads(RESULT.read_text(encoding="utf-8"))
        contract=json.loads(CONTRACT.read_text(encoding="utf-8"))
        self.assertEqual(result["status"],"CLOSED_DIAGNOSTIC_ONLY")
        self.assertEqual(
            result["decision"],
            "NS_UPSTREAM_DONOR_JOINT_RESIDUAL_STABILITY_DECOMPOSED_REVIEW_REQUIRED",
        )
        self.assertEqual(
            result["reviewed_decision"],
            "PRE_READY_DONOR_TRANSFER_FAILURE_ASSOCIATED_WITH_JOINT_SUMMARY_INCOHERENCE_AND_CONDITION_HETEROGENEITY_NOT_SIMPLE_POOL_DISPERSION_NO_CANDIDATE",
        )
        self.assertEqual(
            result["fresh_authority"]["donor_seeds"],
            contract["fresh_diagnostic_authority"]["donor_seeds"],
        )
        self.assertEqual(
            result["fresh_authority"]["target_seeds"],
            contract["fresh_diagnostic_authority"]["target_seeds"],
        )
        self.assertFalse(result["fresh_authority"]["rerun_allowed"])
        self.assertEqual(result["authoritative_execution"]["run_id"],36654157293)
        self.assertEqual(result["authoritative_execution"]["artifact_id"],11072280283)
        self.assertEqual(
            result["original_result_path"],str(EVIDENCE_ROOT/"result.json"))

    def test_failure_not_explained_by_simple_between_donor_dispersion(self):
        result=json.loads(RESULT.read_text(encoding="utf-8"))
        root=result["root_cause_review"]
        self.assertFalse(root["simple_between_donor_pool_dispersion_supported"])
        self.assertTrue(
            root["within_donor_and_target_variability_associated_with_failure"])
        self.assertTrue(
            root["joint_summary_algebra_incoherence_associated_with_pre_ready_failures"])
        pre=result["pre_ready_speech_review"]
        better=pre["matched_better"]
        worse=pre["matched_worse"]
        self.assertEqual(pre["paired_cases"],72)
        self.assertEqual(pre["gap_wins"],43)
        self.assertEqual(pre["gap_losses"],29)
        self.assertGreater(
            worse["median_within_donor_gap_mad"],
            better["median_within_donor_gap_mad"],
        )
        self.assertGreater(
            worse["median_target_gap_mad"],
            better["median_target_gap_mad"],
        )
        self.assertGreater(
            worse["median_gap_alignment_error"],
            better["median_gap_alignment_error"],
        )
        self.assertGreater(
            worse["median_abs_matched_summary_algebra_inconsistency"],
            better["median_abs_matched_summary_algebra_inconsistency"],
        )
        self.assertAlmostEqual(
            worse["median_between_donor_gap_mad"],
            0.03278665249999996,
        )
        self.assertAlmostEqual(
            better["median_between_donor_gap_mad"],
            0.02944809199999998,
        )

    def test_condition_heterogeneity_is_preserved_without_domain_selection(self):
        result=json.loads(RESULT.read_text(encoding="utf-8"))
        domains=result["domain_review"]
        self.assertEqual(domains["bus"]["gap_losses"],14)
        self.assertEqual(domains["bus"]["gap_wins"],4)
        self.assertLess(domains["bus"]["median_gap_improvement"],0)
        self.assertLess(domains["field"]["median_gap_improvement"],0)
        self.assertGreater(domains["living"]["median_gap_improvement"],0)
        self.assertGreater(domains["cafeteria"]["median_gap_improvement"],0)
        root=result["root_cause_review"]
        self.assertTrue(root["bus_adverse_transfer_reproduced"])
        self.assertFalse(root["field_adverse_transfer_reproduced_strongly"])
        self.assertFalse(result["authority_boundary"]["candidate_selected"])
        self.assertFalse(
            result["authority_boundary"]["reference_source_candidate_selected"])

    def test_followup_is_single_joint_coherent_operator_diagnostic(self):
        result=json.loads(RESULT.read_text(encoding="utf-8"))
        follow=result["proposed_followup_hypothesis"]
        self.assertEqual(
            follow["id"],
            "i031-ns-upstream-joint-coherent-donor-aggregation-v1",
        )
        self.assertEqual(follow["authority"],"CANDIDATE_ZERO_DIAGNOSTIC_ONLY")
        rationale=follow["rationale"]
        self.assertIn("single observed joint frame",rationale)
        self.assertIn("minimum unweighted L1 distance",rationale)
        prohibited=set(follow["prohibited"])
        self.assertIn("search across multiple joint aggregation operators",prohibited)
        self.assertIn("reference-source candidate selection",prohibited)
        self.assertIn("component counterfactual ranking",prohibited)
        self.assertTrue(all(
            value is False for value in result["authority_boundary"].values()
        ))


if __name__=="__main__":
    unittest.main()
