#!/usr/bin/env python3
"""Retire consumed I022 diagnostic execution and bind reviewed closure."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import unittest

ROOT=Path(__file__).resolve().parents[2]
LIVE=ROOT/".github/workflows/research-i022-vad-low-local-evidence-disagreement-decomposition-v1.yml"
HISTORY=ROOT/"tests/validation/data/i022-consumed-workflow.yml"
CONTRACT=ROOT/(
    ".github/research/continuous-optimization/development-v4/"
    "i022-vad-low-local-evidence-disagreement-decomposition-v1.json")
RESULT=ROOT/(
    ".github/research/continuous-optimization/development-v4/"
    "i022-vad-low-local-evidence-disagreement-decomposition-v1-result.json")
EVIDENCE_ROOT=Path("validation/research/evidence/i022-36432159733")
HISTORY_BLOB="1850a5f8c659ebbf9efac57579235adcccffe219"


def git_blob(data: bytes) -> str:
    return hashlib.sha1(
        b"blob "+str(len(data)).encode()+b"\0"+data
    ).hexdigest()


class I022RetirementTests(unittest.TestCase):
    def test_consumed_workflow_is_immutable_data(self):
        self.assertEqual(git_blob(HISTORY.read_bytes()),HISTORY_BLOB)
        text=HISTORY.read_text(encoding="utf-8")
        self.assertIn("  workflow_dispatch:\n",text)
        self.assertIn("  diagnose:\n",text)
        self.assertIn("Enforce one-shot I022 diagnostic execution",text)
        self.assertIn("Materialize fresh public-development-v3 partitions",text)
        self.assertIn("Evaluate candidate-zero low-local disagreement",text)

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
        self.assertIn("test_i022_retirement.py",text)

    def test_reviewed_closure_is_non_shipping_and_archive_bound(self):
        result=json.loads(RESULT.read_text(encoding="utf-8"))
        contract=json.loads(CONTRACT.read_text(encoding="utf-8"))
        self.assertEqual(result["status"],"CLOSED_DIAGNOSTIC_ONLY")
        self.assertEqual(
            result["reviewed_decision"],
            "LOW_LOCAL_FN_MOSTLY_REFERENCE_FAIL_UPSTREAM_DISAGREEMENT_COMMON_NO_CANDIDATE",
        )
        self.assertEqual(
            result["fresh_authority"]["seeds"],
            contract["fresh_diagnostic_authority"]["seeds"],
        )
        self.assertFalse(result["fresh_authority"]["rerun_allowed"])
        self.assertEqual(result["authoritative_execution"]["run_id"],36432159733)
        self.assertEqual(result["authoritative_execution"]["artifact_id"],10973704995)
        self.assertEqual(
            result["original_result_path"],
            str(EVIDENCE_ROOT/"result.json"),
        )
        self.assertGreater(
            result["summary"]["low_local_fraction_of_false_negatives"],0.93)
        self.assertGreater(
            result["summary"]["upstream_high_fraction_of_low_local"],0.59)
        self.assertLess(
            result["summary"]["reference_pass_fraction_of_applicable_low_local"],0.16)
        self.assertGreater(
            result["summary"]["low_local_matrix"]["upstream_high_reference_fail"]["fraction"],
            0.51,
        )
        self.assertTrue(all(
            value is False
            for value in result["authority_boundary"].values()
        ))

    def test_followup_remains_candidate_zero(self):
        result=json.loads(RESULT.read_text(encoding="utf-8"))
        follow=result["proposed_followup_hypothesis"]
        self.assertEqual(
            follow["id"],"i023-vad-upstream-local-disagreement-risk-v1")
        self.assertEqual(follow["authority"],"CANDIDATE_ZERO_DIAGNOSTIC_ONLY")
        prohibited=set(follow["prohibited"])
        self.assertIn("local guard threshold tuning",prohibited)
        self.assertIn("upstream guard threshold tuning",prohibited)
        self.assertIn("source candidate selection",prohibited)


if __name__=="__main__":
    unittest.main()
