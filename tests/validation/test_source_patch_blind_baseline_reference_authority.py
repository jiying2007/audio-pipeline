#!/usr/bin/env python3
"""Lock the independently reviewed source-patch baseline-reference authority."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[2]
REVIEW=ROOT/(
    ".github/research/continuous-optimization/development-v4/"
    "source-patch-blind-baseline-reference-authority-v1.json")
I020=ROOT/(
    ".github/research/continuous-optimization/development-v4/"
    "i020-vad-weak-start-requires-blend-v1-blind-review.json")
MANIFEST=ROOT/(
    ".github/research/continuous-optimization/code-candidates/"
    "i020-vad-weak-start-requires-blend-v1.json")
HELPER=ROOT/(
    ".github/research/continuous-optimization/research_code_candidate_blind.py")


class BaselineReferenceAuthorityTests(unittest.TestCase):
    def test_review_is_closed_and_non_shipping(self):
        r=json.loads(REVIEW.read_text())
        self.assertEqual(r["status"],"CLOSED_DESIGN_REVIEW")
        self.assertFalse(r["authority_boundary"]["i020_requalification_authorized"])
        self.assertFalse(r["authority_boundary"]["policy_threshold_change_authorized"])
        self.assertFalse(r["authority_boundary"]["candidate_threshold_change_authorized"])
        self.assertFalse(r["authority_boundary"]["shipping_authority"])
        self.assertFalse(r["authority_boundary"]["hil_authority"])
        self.assertFalse(r["authority_boundary"]["product_certification_authority"])

    def test_i020_frozen_contract_remains_legacy_absolute_pass(self):
        m=json.loads(MANIFEST.read_text())
        self.assertTrue(m["blind_contract"]["require_baseline_absolute_pass"])
        self.assertNotIn("baseline_reference_mode",m["blind_contract"])
        review=json.loads(I020.read_text())
        self.assertEqual(review["decision"],"BLIND_BASELINE_INVALID_REVIEW_REQUIRED")
        self.assertFalse(review["terminal_candidate"])
        self.assertFalse(review["authority_boundary"]["requalification_authorized"])
        self.assertFalse(review["authority_boundary"]["policy_relaxation_authorized"])

    def test_canonical_policy_authority_is_not_shipping_authority(self):
        authority=json.loads((ROOT/"validation/authority.json").read_text())
        self.assertFalse(
            authority["corpus_tiers"]["validation-grade"]["shipping_authority"])
        self.assertFalse(
            authority["corpus_tiers"]["validation-grade-blind"]["shipping_authority"])
        self.assertTrue(
            authority["terminal_authority"]["product-certified"]["shipping_authority"])

    def test_helper_defaults_legacy_and_supports_explicit_future_mode(self):
        spec=importlib.util.spec_from_file_location("source_patch_blind",HELPER)
        module=importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)
        # The helper's own self-test exercises both legacy absolute-pass and
        # future explicit valid-report semantics without touching I020 evidence.
        module.self_test()


if __name__=="__main__":
    unittest.main()
