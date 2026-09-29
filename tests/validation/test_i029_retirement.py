#!/usr/bin/env python3
"""Retire consumed valid I029 donor-reference diagnostic and bind reviewed closure."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import unittest

ROOT=Path(__file__).resolve().parents[2]
LIVE=ROOT/".github/workflows/research-i029-ns-upstream-independent-donor-reference-feasibility-v1.yml"
HISTORY=ROOT/"tests/validation/data/i029-consumed-workflow.yml"
CONTRACT=ROOT/(
    ".github/research/continuous-optimization/development-v4/"
    "i029-ns-upstream-independent-donor-reference-feasibility-v1.json"
)
RESULT=ROOT/(
    ".github/research/continuous-optimization/development-v4/"
    "i029-ns-upstream-independent-donor-reference-feasibility-v1-result.json"
)
EVIDENCE_ROOT=Path("validation/research/evidence/i029-36595080698")
HISTORY_BLOB="578213c08fad113266de978e99893756065821eb"


def git_blob(data: bytes) -> str:
    return hashlib.sha1(b"blob "+str(len(data)).encode()+b"\0"+data).hexdigest()


class I029RetirementTests(unittest.TestCase):
    def test_consumed_workflow_is_immutable_data(self):
        self.assertEqual(git_blob(HISTORY.read_bytes()),HISTORY_BLOB)
        text=HISTORY.read_text(encoding="utf-8")
        self.assertIn("  workflow_dispatch:\n",text)
        self.assertIn("  diagnose:\n",text)
        self.assertIn("Enforce one-shot I029 diagnostic execution",text)
        self.assertIn(
            "Materialize fresh donor and target public-development-v3 partitions",
            text,
        )
        self.assertIn(
            "Evaluate candidate-zero independent donor reference feasibility",
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
        self.assertIn("test_i029_retirement.py",text)

    def test_primary_gap_direction_is_terminally_not_supported(self):
        result=json.loads(RESULT.read_text(encoding="utf-8"))
        contract=json.loads(CONTRACT.read_text(encoding="utf-8"))
        self.assertEqual(result["status"],"CLOSED_DIAGNOSTIC_ONLY")
        self.assertEqual(
            result["decision"],
            "NS_UPSTREAM_INDEPENDENT_DONOR_REFERENCE_FEASIBILITY_DECOMPOSED_REVIEW_REQUIRED",
        )
        self.assertEqual(
            result["reviewed_decision"],
            "MATCHED_DONOR_PRIMARY_GAP_DIRECTION_NOT_SUPPORTED_NO_REFERENCE_SOURCE_CANDIDATE",
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
        self.assertEqual(result["authoritative_execution"]["run_id"],36595080698)
        self.assertEqual(result["authoritative_execution"]["artifact_id"],11046820253)
        self.assertEqual(
            result["original_result_path"],str(EVIDENCE_ROOT/"result.json"))
        primary=result["primary_directional_review"]
        self.assertEqual(primary["paired_cases"],69)
        self.assertAlmostEqual(primary["one_sided_sign_test_p"],0.026644681908256817)
        self.assertEqual(primary["preregistered_maximum_p"],0.01)
        self.assertFalse(primary["supported"])
        self.assertGreater(primary["median_paired_improvement"],0)
        self.assertGreater(primary["matched_better_fraction"],0.5)

    def test_secondary_concentration_cannot_replace_primary(self):
        result=json.loads(RESULT.read_text(encoding="utf-8"))
        secondary=result["secondary_observations"]["concentration"]
        self.assertLess(secondary["one_sided_sign_test_p"],0.01)
        self.assertIn("cannot replace",secondary["interpretation"])
        limits="\n".join(result["verification_limits"])
        self.assertIn("must not be promoted",limits)
        self.assertFalse(
            result["authority_boundary"]["reference_source_candidate_selected"])
        self.assertFalse(result["authority_boundary"]["candidate_selected"])

    def test_domain_outputs_are_descriptive_and_heterogeneous(self):
        result=json.loads(RESULT.read_text(encoding="utf-8"))
        domains=result["secondary_observations"]["descriptive_domain_gap"]
        self.assertGreater(domains["living"]["median_paired_improvement"],0)
        self.assertLess(domains["living"]["one_sided_sign_test_p"],0.01)
        self.assertLess(domains["bus"]["median_paired_improvement"],0)
        self.assertLess(domains["field"]["median_paired_improvement"],0)
        limits="\n".join(result["verification_limits"])
        self.assertIn("descriptive outputs",limits)
        self.assertIn("fresh decomposition only",limits)

    def test_followup_is_joint_residual_stability_diagnostic_only(self):
        result=json.loads(RESULT.read_text(encoding="utf-8"))
        follow=result["proposed_followup_hypothesis"]
        self.assertEqual(
            follow["id"],
            "i030-ns-upstream-donor-joint-residual-stability-decomposition-v1",
        )
        self.assertEqual(follow["authority"],"CANDIDATE_ZERO_DIAGNOSTIC_ONLY")
        self.assertIn("joint",follow["rationale"])
        self.assertIn("stability",follow["rationale"])
        prohibited=set(follow["prohibited"])
        self.assertIn("post-hoc change of K",prohibited)
        self.assertIn("reference-source candidate selection",prohibited)
        self.assertIn("component counterfactual ranking",prohibited)
        self.assertTrue(all(
            value is False for value in result["authority_boundary"].values()
        ))


if __name__=="__main__":
    unittest.main()
