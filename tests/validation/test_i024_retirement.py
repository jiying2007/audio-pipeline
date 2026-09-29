#!/usr/bin/env python3
"""Retire consumed I024 diagnostic execution and bind reviewed state-only closure."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import unittest

ROOT=Path(__file__).resolve().parents[2]
LIVE=ROOT/".github/workflows/research-i024-vad-disagreement-feature-separability-v1.yml"
HISTORY=ROOT/"tests/validation/data/i024-consumed-workflow.yml"
CONTRACT=ROOT/(
    ".github/research/continuous-optimization/development-v4/"
    "i024-vad-disagreement-feature-separability-v1.json")
RESULT=ROOT/(
    ".github/research/continuous-optimization/development-v4/"
    "i024-vad-disagreement-feature-separability-v1-result.json")
EVIDENCE_ROOT=Path("validation/research/evidence/i024-36499446662")
HISTORY_BLOB="04da1ea70e2ef254d176e5e06ab657de39429dee"


def git_blob(data: bytes) -> str:
    return hashlib.sha1(
        b"blob "+str(len(data)).encode()+b"\0"+data
    ).hexdigest()


class I024RetirementTests(unittest.TestCase):
    def test_consumed_workflow_is_immutable_data(self):
        self.assertEqual(git_blob(HISTORY.read_bytes()),HISTORY_BLOB)
        text=HISTORY.read_text(encoding="utf-8")
        self.assertIn("  workflow_dispatch:\n",text)
        self.assertIn("  diagnose:\n",text)
        self.assertIn("Enforce one-shot I024 diagnostic execution",text)
        self.assertIn("Materialize fresh public-development-v3 partitions",text)
        self.assertIn("Evaluate candidate-zero feature separability",text)

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
        self.assertIn("test_i024_retirement.py",text)

    def test_reviewed_closure_ends_state_only_candidate_path(self):
        result=json.loads(RESULT.read_text(encoding="utf-8"))
        contract=json.loads(CONTRACT.read_text(encoding="utf-8"))
        self.assertEqual(result["status"],"CLOSED_DIAGNOSTIC_ONLY")
        self.assertEqual(
            result["reviewed_decision"],
            "STATE_ONLY_DISAGREEMENT_FEATURE_SEPARABILITY_INSUFFICIENT_MOVE_UPSTREAM_NO_CANDIDATE",
        )
        self.assertEqual(
            result["fresh_authority"]["seeds"],
            contract["fresh_diagnostic_authority"]["seeds"],
        )
        self.assertFalse(result["fresh_authority"]["rerun_allowed"])
        self.assertEqual(result["authoritative_execution"]["run_id"],36499446662)
        self.assertEqual(result["authoritative_execution"]["artifact_id"],11005581022)
        self.assertEqual(
            result["original_result_path"],
            str(EVIDENCE_ROOT/"result.json"),
        )
        summary=result["summary"]
        self.assertAlmostEqual(
            summary["maximum_global_separability_over_preregistered_numeric_features"],
            0.6904523119741257,
        )
        self.assertAlmostEqual(
            summary["maximum_cross_domain_floor_over_preregistered_numeric_features"],
            0.6246670896601734,
        )
        self.assertAlmostEqual(
            summary["noise_update_kind_total_variation_distance"],
            0.029037914698111872,
        )
        self.assertEqual(
            summary["best_global_numeric_feature"]["feature"],
            "ratio_db",
        )
        self.assertEqual(
            summary["strongest_cross_domain_floor_feature"]["feature"],
            "shipping_probability",
        )
        self.assertTrue(all(
            value is False for value in result["authority_boundary"].values()
        ))

    def test_verification_limits_prevent_multivariate_overclaim(self):
        result=json.loads(RESULT.read_text(encoding="utf-8"))
        limits="\n".join(result["verification_limits"])
        self.assertIn("does not establish that every possible multivariate classifier",limits)
        self.assertIn("does not invalidate prior I014 evidence",limits)
        self.assertIn("not a selected feature, threshold, model or shipping rule",limits)

    def test_followup_moves_root_cause_upstream_without_candidate_authority(self):
        result=json.loads(RESULT.read_text(encoding="utf-8"))
        follow=result["proposed_followup_hypothesis"]
        self.assertEqual(
            follow["id"],"i025-ns-upstream-disagreement-noise-source-decomposition-v1")
        self.assertEqual(follow["authority"],"CANDIDATE_ZERO_DIAGNOSTIC_ONLY")
        prohibited=set(follow["prohibited"])
        self.assertIn("state-only feature candidate selection",prohibited)
        self.assertIn("multivariate model fitting",prohibited)
        self.assertIn("upstream component reweighting",prohibited)
        self.assertIn("source candidate selection",prohibited)


if __name__=="__main__":
    unittest.main()
