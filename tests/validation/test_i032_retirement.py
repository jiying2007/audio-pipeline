#!/usr/bin/env python3
"""Retire consumed valid I032 target causal noise-scale diagnostic."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import unittest

ROOT=Path(__file__).resolve().parents[2]
LIVE=ROOT/".github/workflows/research-i032-ns-upstream-target-causal-noise-scale-observability-v1.yml"
HISTORY=ROOT/"tests/validation/data/i032-consumed-workflow.yml"
CONTRACT=ROOT/(
    ".github/research/continuous-optimization/development-v4/"
    "i032-ns-upstream-target-causal-noise-scale-observability-v1.json"
)
RESULT=ROOT/(
    ".github/research/continuous-optimization/development-v4/"
    "i032-ns-upstream-target-causal-noise-scale-observability-v1-result.json"
)
EVIDENCE_ROOT=Path("validation/research/evidence/i032-36688937963")
HISTORY_BLOB="227cc9b1fa129125ff16add0923ff30ec0120acc"


def git_blob(data: bytes) -> str:
    return hashlib.sha1(b"blob "+str(len(data)).encode()+b"\0"+data).hexdigest()


class I032RetirementTests(unittest.TestCase):
    def test_consumed_workflow_is_immutable_data(self):
        self.assertEqual(git_blob(HISTORY.read_bytes()),HISTORY_BLOB)
        text=HISTORY.read_text(encoding="utf-8")
        self.assertIn("  workflow_dispatch:\n",text)
        self.assertIn("  diagnose:\n",text)
        self.assertIn("Enforce one-shot I032 diagnostic execution",text)
        self.assertIn(
            "Materialize fresh I032 donor and target public-development-v3 partitions",
            text,
        )
        self.assertIn(
            "Evaluate candidate-zero target causal noise-scale observability",
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
        self.assertIn("test_i032_retirement.py",text)

    def test_reviewed_observability_result_is_terminal(self):
        result=json.loads(RESULT.read_text(encoding="utf-8"))
        contract=json.loads(CONTRACT.read_text(encoding="utf-8"))
        self.assertEqual(result["status"],"CLOSED_DIAGNOSTIC_ONLY")
        self.assertEqual(
            result["decision"],
            "NS_UPSTREAM_TARGET_CAUSAL_NOISE_SCALE_OBSERVABILITY_DECOMPOSED_REVIEW_REQUIRED",
        )
        self.assertEqual(
            result["reviewed_decision"],
            "TARGET_CAUSAL_NS_NOISE_SCALE_FIDELITY_SUPPORTED_NO_NORMALIZATION_OR_REFERENCE_SOURCE_CANDIDATE",
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
        self.assertEqual(result["authoritative_execution"]["run_id"],36688937963)
        self.assertEqual(result["authoritative_execution"]["artifact_id"],11084259758)
        self.assertEqual(
            result["original_result_path"],str(EVIDENCE_ROOT/"result.json"))

    def test_global_fidelity_supports_observable_not_mapping(self):
        result=json.loads(RESULT.read_text(encoding="utf-8"))
        fidelity=result["fidelity_review"]
        self.assertEqual(fidelity["cases"],72)
        self.assertTrue(fidelity["supported"])
        self.assertLessEqual(
            fidelity["median_absolute_error_db"],
            fidelity["preregistered_maximum_median_absolute_error_db"],
        )
        self.assertLessEqual(
            fidelity["p90_absolute_error_db"],
            fidelity["preregistered_maximum_p90_absolute_error_db"],
        )
        self.assertTrue(
            result["root_cause_review"]["target_causal_noise_scale_observable_supported"])
        self.assertFalse(
            result["root_cause_review"]["direct_absolute_normalization_mapping_supported"])
        self.assertFalse(result["authority_boundary"]["noise_scale_normalization_selected"])
        self.assertFalse(result["authority_boundary"]["source_patch_selected"])

    def test_condition_bias_requires_relative_state_followup(self):
        result=json.loads(RESULT.read_text(encoding="utf-8"))
        domains=result["fidelity_review"]["by_noise_domain"]
        self.assertGreater(domains["living"]["median_signed_error_db"],1.5)
        self.assertGreater(domains["kitchen"]["median_signed_error_db"],1.5)
        self.assertLess(abs(domains["office"]["median_signed_error_db"]),0.25)
        self.assertGreater(domains["kitchen"]["p90_absolute_error_db"],6.0)
        self.assertTrue(
            result["root_cause_review"]["absolute_scale_bias_condition_dependent"])

    def test_descriptive_transfer_association_is_monotonic_but_non_authoritative(self):
        result=json.loads(RESULT.read_text(encoding="utf-8"))
        review=result["descriptive_transfer_review"]
        self.assertGreater(
            review["spearman_noise_scale_mismatch_vs_gap_transfer_error"],0)
        quartiles=review["mismatch_quartiles"]
        errors=[
            quartiles[key]["median_frozen_donor_gap_transfer_error"]
            for key in ("q1","q2","q3","q4")
        ]
        self.assertEqual(errors,sorted(errors))
        self.assertEqual(review["authority"],
                         "descriptive only; cannot select a mapping or candidate")

    def test_followup_is_relative_noise_delta_alignment_only(self):
        result=json.loads(RESULT.read_text(encoding="utf-8"))
        follow=result["proposed_followup_hypothesis"]
        self.assertEqual(
            follow["id"],
            "i033-ns-vad-causal-noise-delta-alignment-v1",
        )
        self.assertEqual(follow["authority"],"CANDIDATE_ZERO_DIAGNOSTIC_ONLY")
        rationale=follow["rationale"]
        self.assertIn("last prior reference as a causal anchor",rationale)
        self.assertIn("median absolute delta error <=3 dB",rationale)
        self.assertIn("nearest-rank p90 <=6 dB",rationale)
        prohibited=set(follow["prohibited"])
        self.assertIn("absolute-value normalization mapping selection",prohibited)
        self.assertIn("VAD noise-state refresh source patch",prohibited)
        self.assertIn("threshold tuning",prohibited)
        self.assertTrue(all(
            value is False for value in result["authority_boundary"].values()
        ))


if __name__=="__main__":
    unittest.main()
