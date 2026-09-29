#!/usr/bin/env python3
"""Retire consumed invalid I027 diagnostic and bind readiness-coverage closure."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import unittest

ROOT=Path(__file__).resolve().parents[2]
LIVE=ROOT/".github/workflows/research-i027-ns-upstream-reference-ready-component-counterfactual-v1.yml"
HISTORY=ROOT/"tests/validation/data/i027-consumed-workflow.yml"
CONTRACT=ROOT/(
    ".github/research/continuous-optimization/development-v4/"
    "i027-ns-upstream-reference-ready-component-counterfactual-v1.json")
RESULT=ROOT/(
    ".github/research/continuous-optimization/development-v4/"
    "i027-ns-upstream-reference-ready-component-counterfactual-v1-result.json")
EVIDENCE_ROOT=Path("validation/research/evidence/i027-36570600341")
HISTORY_BLOB="ae95b8504d2a299ce1f15919f0fa3da3caf4567f"


def git_blob(data: bytes) -> str:
    return hashlib.sha1(
        b"blob "+str(len(data)).encode()+b"\0"+data
    ).hexdigest()


class I027RetirementTests(unittest.TestCase):
    def test_consumed_workflow_is_immutable_data(self):
        self.assertEqual(git_blob(HISTORY.read_bytes()),HISTORY_BLOB)
        text=HISTORY.read_text(encoding="utf-8")
        self.assertIn("  workflow_dispatch:\n",text)
        self.assertIn("  diagnose:\n",text)
        self.assertIn("Enforce one-shot I027 diagnostic execution",text)
        self.assertIn("Materialize fresh public-development-v3 partitions",text)
        self.assertIn(
            "Evaluate candidate-zero reference-ready component counterfactual",
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
        self.assertIn("test_i027_retirement.py",text)

    def test_speech_readiness_coverage_failure_is_terminal(self):
        result=json.loads(RESULT.read_text(encoding="utf-8"))
        contract=json.loads(CONTRACT.read_text(encoding="utf-8"))
        self.assertEqual(result["status"],"CLOSED_INVALID_DIAGNOSTIC_ONLY")
        self.assertEqual(result["decision"],"I027_INPUT_INVALID_REVIEW_REQUIRED")
        self.assertEqual(
            result["reviewed_decision"],
            "REFERENCE_READY_SPEECH_COVERAGE_GATE_FAILED_NO_COMPONENT_CONCLUSION_NO_CANDIDATE",
        )
        self.assertEqual(
            result["fresh_authority"]["seeds"],
            contract["fresh_diagnostic_authority"]["seeds"],
        )
        self.assertFalse(result["fresh_authority"]["rerun_allowed"])
        self.assertEqual(result["authoritative_execution"]["run_id"],36570600341)
        self.assertEqual(result["authoritative_execution"]["artifact_id"],11034169094)
        self.assertEqual(
            result["original_result_path"],
            str(EVIDENCE_ROOT/"result.json"),
        )
        invalid=result["invalidity_review"]
        self.assertEqual(
            invalid["invalid_reasons"],
            [
                "domain_eligible_fraction:cafeteria:speech",
                "global_eligible_fraction:speech",
            ],
        )
        self.assertEqual(invalid["target_cases"],168)
        self.assertEqual(invalid["target_cases_with_any_eligible_target"],168)
        self.assertAlmostEqual(
            invalid["global"]["speech"]["eligible_fraction"],
            0.7449760145209386,
        )
        self.assertFalse(invalid["global"]["speech"]["gate_passed"])
        self.assertAlmostEqual(
            invalid["cafeteria_speech"]["eligible_fraction"],
            0.5537084398976982,
        )
        self.assertFalse(invalid["cafeteria_speech"]["gate_passed"])
        self.assertTrue(
            invalid["secondary_scenario_snr_reverb_coverage_gates_passed"])
        self.assertTrue(invalid["denominator_correction_worked"])
        self.assertTrue(
            invalid["experiment_design_coverage_failure_not_shipping_failure"])

    def test_invalid_counterfactuals_cannot_rank_components(self):
        result=json.loads(RESULT.read_text(encoding="utf-8"))
        invalid=result["invalid_observations"]
        self.assertFalse(invalid["interpretation_allowed"])
        self.assertIn("must not be used to rank",invalid["reason"])
        limits="\n".join(result["verification_limits"])
        self.assertIn("non-authoritative",limits)
        self.assertIn("must not be relaxed",limits)
        self.assertFalse(result["authority_boundary"]["component_selected"])
        self.assertFalse(
            result["authority_boundary"]["component_ranked_for_shipping"])
        self.assertFalse(result["authority_boundary"]["mapping_selected"])
        self.assertFalse(result["authority_boundary"]["readiness_threshold_changed"])

    def test_shipping_mirror_is_exact_but_not_coverage_authority(self):
        result=json.loads(RESULT.read_text(encoding="utf-8"))
        mirror=result["shipping_mirror"]
        self.assertEqual(mirror["max_ns_upstream_gap_delta"],0)
        self.assertEqual(mirror["max_vad_probability_delta"],0)
        self.assertEqual(mirror["vad_active_mismatch_frames"],0)
        self.assertIn(
            "implementation identity only",
            "\n".join(result["verification_limits"]),
        )

    def test_followup_decomposes_readiness_without_counterfactual_rerun(self):
        result=json.loads(RESULT.read_text(encoding="utf-8"))
        follow=result["proposed_followup_hypothesis"]
        self.assertEqual(
            follow["id"],
            "i028-ns-upstream-reference-readiness-temporal-decomposition-v1",
        )
        self.assertEqual(follow["authority"],"CANDIDATE_ZERO_DIAGNOSTIC_ONLY")
        rationale=follow["rationale"]
        self.assertIn("do not run component counterfactuals",rationale)
        self.assertIn("first frame/time",rationale)
        prohibited=set(follow["prohibited"])
        self.assertIn("reuse of I027 seeds",prohibited)
        self.assertIn(
            "post-hoc lowering of the eight-frame readiness threshold",
            prohibited,
        )
        self.assertIn("component counterfactual ranking",prohibited)
        self.assertIn("candidate selection",prohibited)
        self.assertTrue(all(
            value is False for value in result["authority_boundary"].values()
        ))


if __name__=="__main__":
    unittest.main()
