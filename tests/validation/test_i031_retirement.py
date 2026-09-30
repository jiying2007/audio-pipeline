#!/usr/bin/env python3
"""Retire consumed valid I031 joint-coherent aggregation diagnostic."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import unittest

ROOT=Path(__file__).resolve().parents[2]
LIVE=ROOT/".github/workflows/research-i031-ns-upstream-joint-coherent-donor-aggregation-v1.yml"
HISTORY=ROOT/"tests/validation/data/i031-consumed-workflow.yml"
CONTRACT=ROOT/(
    ".github/research/continuous-optimization/development-v4/"
    "i031-ns-upstream-joint-coherent-donor-aggregation-v1.json"
)
RESULT=ROOT/(
    ".github/research/continuous-optimization/development-v4/"
    "i031-ns-upstream-joint-coherent-donor-aggregation-v1-result.json"
)
EVIDENCE_ROOT=Path("validation/research/evidence/i031-36666717040")
HISTORY_BLOB="5dd1e167c00ab7fce868c74851e17035d08fb761"


def git_blob(data: bytes) -> str:
    return hashlib.sha1(b"blob "+str(len(data)).encode()+b"\0"+data).hexdigest()


class I031RetirementTests(unittest.TestCase):
    def test_consumed_workflow_is_immutable_data(self):
        self.assertEqual(git_blob(HISTORY.read_bytes()),HISTORY_BLOB)
        text=HISTORY.read_text(encoding="utf-8")
        self.assertIn("  workflow_dispatch:\n",text)
        self.assertIn("  diagnose:\n",text)
        self.assertIn("Enforce one-shot I031 diagnostic execution",text)
        self.assertIn(
            "Materialize fresh I031 donor and target public-development-v3 partitions",
            text,
        )
        self.assertIn(
            "Evaluate candidate-zero joint-coherent donor aggregation",
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
        self.assertIn("test_i031_retirement.py",text)

    def test_reviewed_joint_coherent_result_is_terminal(self):
        result=json.loads(RESULT.read_text(encoding="utf-8"))
        contract=json.loads(CONTRACT.read_text(encoding="utf-8"))
        self.assertEqual(result["status"],"CLOSED_DIAGNOSTIC_ONLY")
        self.assertEqual(
            result["decision"],
            "NS_UPSTREAM_JOINT_COHERENT_DONOR_AGGREGATION_DECOMPOSED_REVIEW_REQUIRED",
        )
        self.assertEqual(
            result["reviewed_decision"],
            "JOINT_COHERENCE_RESTORED_BUT_PRIMARY_GAP_ERROR_WORSENED_NO_OPERATOR_OR_REFERENCE_SOURCE_CANDIDATE",
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
        self.assertEqual(result["authoritative_execution"]["run_id"],36666717040)
        self.assertEqual(result["authoritative_execution"]["artifact_id"],11077390422)
        self.assertEqual(
            result["original_result_path"],str(EVIDENCE_ROOT/"result.json"))

    def test_joint_identity_restored_but_primary_gap_worsened(self):
        result=json.loads(RESULT.read_text(encoding="utf-8"))
        primary=result["primary_directional_review"]
        self.assertEqual(primary["paired_cases"],71)
        self.assertFalse(primary["supported"])
        self.assertLess(primary["median_gap_error_improvement"],0)
        self.assertLess(primary["gap_better_fraction"],0.5)
        self.assertGreater(
            primary["one_sided_sign_test_p"],
            primary["preregistered_maximum_p"],
        )
        self.assertLessEqual(
            primary["max_joint_coherent_algebraic_inconsistency"],1e-6)
        root=result["root_cause_review"]
        self.assertTrue(root["joint_algebraic_incoherence_is_real"])
        self.assertFalse(
            root["joint_algebraic_incoherence_is_sufficient_explanation"])
        self.assertFalse(root["observed_frame_coherent_operator_supported"])
        self.assertFalse(root["aggregation_only_search_should_continue"])

    def test_domain_slices_cannot_rescue_failed_primary(self):
        result=json.loads(RESULT.read_text(encoding="utf-8"))
        domains=result["domain_review"]
        self.assertGreater(domains["living"]["median_gap_error_improvement"],0)
        for domain in ("bus","field","cafeteria","kitchen"):
            self.assertLess(domains[domain]["median_gap_error_improvement"],0)
        self.assertFalse(
            result["authority_boundary"]["joint_aggregation_candidate_selected"])
        self.assertFalse(
            result["authority_boundary"]["reference_source_candidate_selected"])

    def test_non_authoritative_projection_is_not_a_second_operator_result(self):
        result=json.loads(RESULT.read_text(encoding="utf-8"))
        sanity=result["non_authoritative_sanity_check"]
        self.assertFalse(sanity["use_for_candidate_selection"])
        self.assertLess(
            sanity["pre_ready_speech_median_gap_error_improvement_approx"],0)
        limits=" ".join(result["verification_limits"])
        self.assertIn("non-authoritative projection sanity check",limits)

    def test_followup_moves_to_causal_noise_scale_observability(self):
        result=json.loads(RESULT.read_text(encoding="utf-8"))
        follow=result["proposed_followup_hypothesis"]
        self.assertEqual(
            follow["id"],
            "i032-ns-upstream-target-causal-noise-scale-observability-v1",
        )
        self.assertEqual(follow["authority"],"CANDIDATE_ZERO_DIAGNOSTIC_ONLY")
        rationale=follow["rationale"]
        self.assertIn("ns_noise_rms_dbfs",rationale)
        self.assertIn("median absolute error <=3 dB",rationale)
        self.assertIn("90th-percentile absolute error <=6 dB",rationale)
        prohibited=set(follow["prohibited"])
        self.assertIn(
            "search or evaluation of another aggregation operator",prohibited)
        self.assertIn("noise-scale normalization mapping selection",prohibited)
        self.assertIn("reference-source candidate selection",prohibited)
        self.assertTrue(all(
            value is False for value in result["authority_boundary"].values()
        ))


if __name__=="__main__":
    unittest.main()
