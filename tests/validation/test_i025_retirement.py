#!/usr/bin/env python3
"""Retire consumed I025 diagnostic execution and bind reviewed upstream-source closure."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import unittest

ROOT=Path(__file__).resolve().parents[2]
LIVE=ROOT/".github/workflows/research-i025-ns-upstream-disagreement-noise-source-decomposition-v1.yml"
HISTORY=ROOT/"tests/validation/data/i025-consumed-workflow.yml"
CONTRACT=ROOT/(
    ".github/research/continuous-optimization/development-v4/"
    "i025-ns-upstream-disagreement-noise-source-decomposition-v1.json")
RESULT=ROOT/(
    ".github/research/continuous-optimization/development-v4/"
    "i025-ns-upstream-disagreement-noise-source-decomposition-v1-result.json")
EVIDENCE_ROOT=Path("validation/research/evidence/i025-36516678401")
HISTORY_BLOB="36a2633d747b33b5ae78b4fd3c14ebd64b3428f8"


def git_blob(data: bytes) -> str:
    return hashlib.sha1(
        b"blob "+str(len(data)).encode()+b"\0"+data
    ).hexdigest()


class I025RetirementTests(unittest.TestCase):
    def test_consumed_workflow_is_immutable_data(self):
        self.assertEqual(git_blob(HISTORY.read_bytes()),HISTORY_BLOB)
        text=HISTORY.read_text(encoding="utf-8")
        self.assertIn("  workflow_dispatch:\n",text)
        self.assertIn("  diagnose:\n",text)
        self.assertIn("Enforce one-shot I025 diagnostic execution",text)
        self.assertIn("Materialize fresh public-development-v3 partitions",text)
        self.assertIn("Evaluate candidate-zero upstream source decomposition",text)

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
        self.assertIn("test_i025_retirement.py",text)

    def test_reviewed_closure_rejects_slow_update_self_lock(self):
        result=json.loads(RESULT.read_text(encoding="utf-8"))
        contract=json.loads(CONTRACT.read_text(encoding="utf-8"))
        self.assertEqual(result["status"],"CLOSED_DIAGNOSTIC_ONLY")
        self.assertEqual(
            result["reviewed_decision"],
            "FALSE_HIGH_NOISE_ASSOCIATED_WITH_SPARSE_POSTERIOR_GAP_SLOW_UPDATE_LOCK_NOT_SUPPORTED_NO_CANDIDATE",
        )
        self.assertEqual(
            result["fresh_authority"]["seeds"],
            contract["fresh_diagnostic_authority"]["seeds"],
        )
        self.assertFalse(result["fresh_authority"]["rerun_allowed"])
        self.assertEqual(result["authoritative_execution"]["run_id"],36516678401)
        self.assertEqual(result["authoritative_execution"]["artifact_id"],11011413710)
        self.assertEqual(
            result["original_result_path"],
            str(EVIDENCE_ROOT/"result.json"),
        )
        self.assertFalse(
            result["hypothesis_review"]["native_slow_update_self_lock_supported"])
        self.assertTrue(
            result["hypothesis_review"]["sparse_posterior_gap_association_supported"])
        self.assertAlmostEqual(
            result["noise_source_review"]["slow_update_bin_fraction"][
                "noise_disagreement_median"],
            0.139534891,
        )
        self.assertAlmostEqual(
            result["noise_source_review"]["slow_update_bin_fraction"][
                "noise_reference_median"],
            0.241860464,
        )
        self.assertLess(
            result["noise_source_review"]["mean_post_ratio"][
                "noise_disagreement_median"],
            result["noise_source_review"]["mean_post_ratio"][
                "noise_reference_median"],
        )
        self.assertTrue(all(
            value is False for value in result["authority_boundary"].values()
        ))

    def test_sparse_posterior_gap_is_reviewed_without_component_selection(self):
        result=json.loads(RESULT.read_text(encoding="utf-8"))
        gap=result["noise_source_review"]["gap_to_concentration"]
        sparse=result["noise_source_review"]["positive_bin_fraction"]
        self.assertGreater(gap["separability_auc"],0.75)
        self.assertGreater(gap["cross_domain_floor"],0.72)
        self.assertLess(
            sparse["noise_disagreement_median"],
            sparse["noise_reference_median"],
        )
        definition=result["definition_conditioned_metrics"]
        self.assertIn("Tautological",definition["disagreement_run_length"]["note"])
        self.assertIn("population selection",definition["upstream_high_run_length"]["note"])

    def test_i014_synergy_is_preserved_and_followup_is_causal_only(self):
        result=json.loads(RESULT.read_text(encoding="utf-8"))
        limits="\n".join(result["verification_limits"])
        self.assertIn("I014 remains authoritative",limits)
        self.assertIn("does not authorize removal or reweighting",limits)
        follow=result["proposed_followup_hypothesis"]
        self.assertEqual(
            follow["id"],"i026-ns-upstream-matched-component-counterfactual-v1")
        self.assertEqual(
            follow["authority"],"CANDIDATE_ZERO_CAUSAL_DIAGNOSTIC_ONLY")
        prohibited=set(follow["prohibited"])
        self.assertIn("component reweighting",prohibited)
        self.assertIn("shipping source changes",prohibited)
        self.assertIn("candidate selection",prohibited)


if __name__=="__main__":
    unittest.main()
