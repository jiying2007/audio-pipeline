#!/usr/bin/env python3
"""Retire consumed I023 diagnostic execution and bind reviewed closure."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import unittest

ROOT=Path(__file__).resolve().parents[2]
LIVE=ROOT/".github/workflows/research-i023-vad-upstream-local-disagreement-risk-v1.yml"
HISTORY=ROOT/"tests/validation/data/i023-consumed-workflow.yml"
CONTRACT=ROOT/(
    ".github/research/continuous-optimization/development-v4/"
    "i023-vad-upstream-local-disagreement-risk-v1.json")
RESULT=ROOT/(
    ".github/research/continuous-optimization/development-v4/"
    "i023-vad-upstream-local-disagreement-risk-v1-result.json")
EVIDENCE_ROOT=Path("validation/research/evidence/i023-36441887773")
HISTORY_BLOB="fe54ec2fd617fc0a6ec3bdc30cc61ed75dd268cb"


def git_blob(data: bytes) -> str:
    return hashlib.sha1(
        b"blob "+str(len(data)).encode()+b"\0"+data
    ).hexdigest()


class I023RetirementTests(unittest.TestCase):
    def test_consumed_workflow_is_immutable_data(self):
        self.assertEqual(git_blob(HISTORY.read_bytes()),HISTORY_BLOB)
        text=HISTORY.read_text(encoding="utf-8")
        self.assertIn("  workflow_dispatch:\n",text)
        self.assertIn("  diagnose:\n",text)
        self.assertIn("Enforce one-shot I023 diagnostic execution",text)
        self.assertIn("Materialize fresh public-development-v3 partitions",text)
        self.assertIn("Evaluate candidate-zero disagreement risk",text)

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
        self.assertIn("test_i023_retirement.py",text)

    def test_reviewed_closure_rejects_direct_disagreement_trust(self):
        result=json.loads(RESULT.read_text(encoding="utf-8"))
        contract=json.loads(CONTRACT.read_text(encoding="utf-8"))
        self.assertEqual(result["status"],"CLOSED_DIAGNOSTIC_ONLY")
        self.assertEqual(
            result["reviewed_decision"],
            "UPSTREAM_LOCAL_DISAGREEMENT_NOISE_RISK_HIGH_NO_DIRECT_TRUST_CANDIDATE",
        )
        self.assertEqual(
            result["fresh_authority"]["seeds"],
            contract["fresh_diagnostic_authority"]["seeds"],
        )
        self.assertFalse(result["fresh_authority"]["rerun_allowed"])
        self.assertEqual(result["authoritative_execution"]["run_id"],36441887773)
        self.assertEqual(result["authoritative_execution"]["artifact_id"],10979618377)
        self.assertEqual(
            result["original_result_path"],
            str(EVIDENCE_ROOT/"result.json"),
        )
        summary=result["summary"]
        self.assertGreater(summary["low_local_fraction_of_false_negatives"],0.93)
        self.assertGreater(
            summary["disagreement_coverage_of_low_local_false_negatives"],0.61)
        self.assertLess(summary["disagreement_conditional_speech_precision"],0.48)
        self.assertGreater(summary["disagreement_noise_occupancy"],0.30)
        self.assertGreater(summary["disagreement_noise_active_fraction"],0.33)
        self.assertGreater(summary["disagreement_noise_pre_hangover_fraction"],0.36)
        self.assertLess(
            summary["disagreement_noise_refresh_fraction"]["weak"],0.016)
        self.assertEqual(
            summary["disagreement_noise_refresh_fraction"]["strong"],0)
        self.assertTrue(all(
            value is False
            for value in result["authority_boundary"].values()
        ))

    def test_verification_limits_prevent_overclaiming_tail_and_precision(self):
        result=json.loads(RESULT.read_text(encoding="utf-8"))
        limits="\n".join(result["verification_limits"])
        self.assertIn("not a calibrated product-environment positive predictive value",limits)
        self.assertIn("cannot be interpreted as causal hangover",limits)

    def test_followup_remains_candidate_zero_feature_separability(self):
        result=json.loads(RESULT.read_text(encoding="utf-8"))
        follow=result["proposed_followup_hypothesis"]
        self.assertEqual(
            follow["id"],"i024-vad-disagreement-feature-separability-v1")
        self.assertEqual(follow["authority"],"CANDIDATE_ZERO_DIAGNOSTIC_ONLY")
        prohibited=set(follow["prohibited"])
        self.assertIn("direct disagreement activation",prohibited)
        self.assertIn("direct disagreement refresh",prohibited)
        self.assertIn("source candidate selection",prohibited)


if __name__=="__main__":
    unittest.main()
