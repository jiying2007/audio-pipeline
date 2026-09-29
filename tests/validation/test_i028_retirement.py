#!/usr/bin/env python3
"""Retire consumed valid I028 temporal-readiness diagnostic and bind reviewed closure."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import unittest

ROOT=Path(__file__).resolve().parents[2]
LIVE=ROOT/".github/workflows/research-i028-ns-upstream-reference-readiness-temporal-decomposition-v1.yml"
HISTORY=ROOT/"tests/validation/data/i028-consumed-workflow.yml"
CONTRACT=ROOT/(
    ".github/research/continuous-optimization/development-v4/"
    "i028-ns-upstream-reference-readiness-temporal-decomposition-v1.json"
)
RESULT=ROOT/(
    ".github/research/continuous-optimization/development-v4/"
    "i028-ns-upstream-reference-readiness-temporal-decomposition-v1-result.json"
)
EVIDENCE_ROOT=Path("validation/research/evidence/i028-36579696633")
HISTORY_BLOB="b1281dd4e6e71dd0cdf6952c741bde7cf1d558d0"


def git_blob(data: bytes) -> str:
    return hashlib.sha1(b"blob "+str(len(data)).encode()+b"\0"+data).hexdigest()


class I028RetirementTests(unittest.TestCase):
    def test_consumed_workflow_is_immutable_data(self):
        self.assertEqual(git_blob(HISTORY.read_bytes()),HISTORY_BLOB)
        text=HISTORY.read_text(encoding="utf-8")
        self.assertIn("  workflow_dispatch:\n",text)
        self.assertIn("  diagnose:\n",text)
        self.assertIn("Enforce one-shot I028 diagnostic execution",text)
        self.assertIn("Materialize fresh public-development-v3 partitions",text)
        self.assertIn(
            "Evaluate candidate-zero reference-readiness temporal decomposition",
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
        self.assertIn("test_i028_retirement.py",text)

    def test_valid_temporal_decomposition_is_terminal(self):
        result=json.loads(RESULT.read_text(encoding="utf-8"))
        contract=json.loads(CONTRACT.read_text(encoding="utf-8"))
        self.assertEqual(result["status"],"CLOSED_DIAGNOSTIC_ONLY")
        self.assertEqual(
            result["decision"],
            "NS_UPSTREAM_REFERENCE_READINESS_TEMPORAL_DECOMPOSED_REVIEW_REQUIRED",
        )
        self.assertEqual(
            result["reviewed_decision"],
            "PRE_READY_SPEECH_DRIVEN_BY_EARLY_TARGET_AND_DELAYED_INITIAL_REFERENCE_ARRIVAL_CAFETERIA_AMPLIFIED_NO_CANDIDATE",
        )
        self.assertEqual(
            result["fresh_authority"]["seeds"],
            contract["fresh_diagnostic_authority"]["seeds"],
        )
        self.assertFalse(result["fresh_authority"]["rerun_allowed"])
        self.assertEqual(result["authoritative_execution"]["run_id"],36579696633)
        self.assertEqual(result["authoritative_execution"]["artifact_id"],11038379441)
        self.assertEqual(
            result["original_result_path"],
            str(EVIDENCE_ROOT/"result.json"),
        )
        accounting=result["target_accounting"]
        self.assertEqual(accounting["raw_target_count"],17046)
        self.assertEqual(accounting["target_receipt_count"],17046)
        self.assertTrue(accounting["all_raw_targets_represented_exactly_once"])
        self.assertEqual(accounting["target_cases"],168)

    def test_temporal_ordering_not_threshold_tuning_is_reviewed(self):
        result=json.loads(RESULT.read_text(encoding="utf-8"))
        global_review=result["global_readiness_review"]
        self.assertEqual(global_review["cases_first_target_before_ready"],139)
        self.assertEqual(
            global_review["cases_first_target_before_first_reference"],98)
        self.assertAlmostEqual(
            global_review["first_target_before_ready_case_fraction"],
            0.8273809523809523,
        )
        self.assertEqual(global_review["median_first_target_frame_index"],4)
        self.assertEqual(global_review["median_first_reference_frame_index"],10)
        self.assertEqual(global_review["median_first_ready_frame_index"],43)
        self.assertEqual(global_review["median_ready_minus_first_target_frames"],36)
        self.assertAlmostEqual(
            global_review["pre_ready_fraction"]["speech"],
            0.3636682242990654,
        )
        self.assertAlmostEqual(
            global_review["pre_ready_fraction"]["noise"],
            0.1292717416921989,
        )
        hypothesis=result["hypothesis_review"]
        self.assertTrue(hypothesis["early_target_timing_supported"])
        self.assertTrue(hypothesis["delayed_initial_reference_arrival_supported"])
        self.assertFalse(
            hypothesis["uniform_steady_state_reference_scarcity_supported"])
        self.assertFalse(result["authority_boundary"]["readiness_threshold_changed"])

    def test_cafeteria_amplifies_initial_reference_delay(self):
        result=json.loads(RESULT.read_text(encoding="utf-8"))
        cafe=result["cafeteria_readiness_review"]
        self.assertAlmostEqual(
            cafe["pre_ready_fraction"]["speech"],0.5445920303605313)
        self.assertEqual(cafe["cases_first_target_before_ready"],15)
        self.assertEqual(cafe["cases_first_target_before_first_reference"],12)
        self.assertEqual(cafe["median_first_target_frame_index"],5)
        self.assertEqual(cafe["median_first_reference_frame_index"],24)
        self.assertEqual(cafe["median_first_ready_frame_index"],44)
        self.assertEqual(
            cafe["median_pre_ready_speech_prior_reference_count"],0)
        self.assertEqual(cafe["pre_ready_speech_zero_prior_reference_targets"],289)
        self.assertAlmostEqual(
            cafe["pre_ready_speech_zero_prior_reference_fraction"],
            0.5034843205574913,
        )
        self.assertEqual(cafe["median_reference_interarrival_frames"],1)
        self.assertEqual(cafe["median_reference_frames_total_per_target_case"],56)

    def test_followup_is_donor_feasibility_without_component_counterfactual(self):
        result=json.loads(RESULT.read_text(encoding="utf-8"))
        follow=result["proposed_followup_hypothesis"]
        self.assertEqual(
            follow["id"],
            "i029-ns-upstream-independent-donor-reference-feasibility-v1",
        )
        self.assertEqual(follow["authority"],"CANDIDATE_ZERO_DIAGNOSTIC_ONLY")
        self.assertIn("independent",follow["rationale"])
        self.assertIn("retrospective agreement benchmark",follow["rationale"])
        prohibited=set(follow["prohibited"])
        self.assertIn("same-target future-frame reference leakage",prohibited)
        self.assertIn("component counterfactual ranking",prohibited)
        self.assertIn("reference source candidate selection",prohibited)
        self.assertTrue(all(
            value is False for value in result["authority_boundary"].values()
        ))


if __name__=="__main__":
    unittest.main()
