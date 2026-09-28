#!/usr/bin/env python3
"""Lock the independently reviewed source-patch baseline-reference authority."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[2]
REVIEW=ROOT/(
    ".github/research/continuous-optimization/development-v4/"
    "source-patch-blind-baseline-reference-authority-v1.json")
QUALITY_REVIEW=ROOT/(
    ".github/research/continuous-optimization/development-v4/"
    "source-patch-blind-candidate-quality-scope-v1.json")
EVIDENCE_ROOT=ROOT/(
    "validation/research/evidence/"
    "i020-blind-baseline-invalid-36304120808-36324803945")
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
        self.assertNotIn("candidate_quality_mode",m["blind_contract"])
        self.assertTrue(m["blind_contract"]["require_candidate_absolute_pass"])
        review=json.loads(I020.read_text())
        self.assertEqual(review["decision"],"BLIND_BASELINE_INVALID_REVIEW_REQUIRED")
        self.assertFalse(review["terminal_candidate"])
        self.assertFalse(review["authority_boundary"]["requalification_authorized"])
        self.assertFalse(review["authority_boundary"]["policy_relaxation_authorized"])

    def test_future_candidate_quality_scope_is_evidence_bound_and_non_shipping(self):
        review=json.loads(QUALITY_REVIEW.read_text())
        self.assertEqual(review["status"],"CLOSED_DESIGN_REVIEW")
        self.assertFalse(
            review["authority_boundary"]["i020_requalification_authorized"])
        self.assertFalse(
            review["authority_boundary"]["i020_reclassification_authorized"])
        self.assertFalse(
            review["authority_boundary"]["policy_threshold_change_authorized"])
        self.assertFalse(
            review["authority_boundary"]["non_vad_regression_authorized"])
        self.assertEqual(
            review["future_contract"]["vad_impact_scoped_v1"]["allowed_patch_paths"],
            ["src/enhance/ap_vad.c"],
        )

        bv=json.loads((EVIDENCE_ROOT/"baseline-visible-report.json").read_text())
        cv=json.loads((EVIDENCE_ROOT/"candidate-visible-report.json").read_text())
        bb=json.loads((EVIDENCE_ROOT/"baseline-blind-report.json").read_text())
        cb=json.loads((EVIDENCE_ROOT/"candidate-blind-report.json").read_text())
        evidence=review["evidence"]
        self.assertEqual(
            bv["summary"]["median_near_si_sdr_improvement_db"],
            evidence["visible"]["baseline_median_near_si_sdr_improvement_db"],
        )
        self.assertEqual(
            cv["summary"]["median_near_si_sdr_improvement_db"],
            evidence["visible"]["candidate_median_near_si_sdr_improvement_db"],
        )
        self.assertEqual(
            bv["summary"]["median_output_render_corr_reduction"],
            cv["summary"]["median_output_render_corr_reduction"],
        )
        self.assertEqual(
            bb["summary"]["median_output_render_corr_reduction"],
            cb["summary"]["median_output_render_corr_reduction"],
        )
        self.assertEqual(
            cv["summary"]["min_vad_f1"],
            evidence["visible"]["candidate_min_vad_f1"],
        )
        self.assertEqual(
            cb["summary"]["min_vad_f1"],
            evidence["blind"]["candidate_min_vad_f1"],
        )
        self.assertLess(cv["summary"]["min_vad_f1"],0.80)
        self.assertLess(cb["summary"]["min_vad_f1"],0.80)

    def test_future_impact_scope_cannot_rescue_frozen_i020(self):
        spec=importlib.util.spec_from_file_location("source_patch_blind_i020",HELPER)
        module=importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)

        manifest=json.loads(MANIFEST.read_text())
        counterfactual=json.loads(json.dumps(manifest))
        blind=counterfactual["blind_contract"]
        blind["baseline_reference_mode"]="valid-report"
        blind["require_baseline_absolute_pass"]=False
        blind["candidate_quality_mode"]="vad-impact-scoped-v1"
        blind["require_candidate_absolute_pass"]=False

        bv=json.loads((EVIDENCE_ROOT/"baseline-visible-report.json").read_text())
        cv=json.loads((EVIDENCE_ROOT/"candidate-visible-report.json").read_text())
        bb=json.loads((EVIDENCE_ROOT/"baseline-blind-report.json").read_text())
        cb=json.loads((EVIDENCE_ROOT/"candidate-blind-report.json").read_text())
        identity={
            "authority":"non-shipping-source-patch-blind-qualification",
            "candidate_id":counterfactual["candidate_id"],
            "research_candidate_id":counterfactual["research_candidate_id"],
            "source_base_sha":counterfactual["source_base_sha"],
            "patch":counterfactual["patch"],
            "blind_contract":counterfactual["blind_contract"],
            "baseline_processor_sha256":bv["bindings"]["processor_sha256"],
            "candidate_processor_sha256":cv["bindings"]["processor_sha256"],
        }
        self.assertEqual(
            bb["bindings"]["processor_sha256"],
            identity["baseline_processor_sha256"],
        )
        self.assertEqual(
            cb["bindings"]["processor_sha256"],
            identity["candidate_processor_sha256"],
        )
        with tempfile.TemporaryDirectory() as tmp:
            result,rc=module.classify(
                counterfactual,identity,bv,cv,bb,cb,
                Path(tmp)/"counterfactual.json",
            )
        self.assertEqual(rc,1)
        self.assertEqual(result["decision"],"BLIND_REJECTED_NON_SHIPPING")
        self.assertEqual(
            result["failed_stage"],"impact-scoped-candidate-quality")
        self.assertTrue(result["terminal_candidate"])
        self.assertEqual(
            {item["metric"] for item in result["relative_vad_violations"]},
            {"min_vad_f1"},
        )
        frozen=json.loads(I020.read_text())
        self.assertEqual(
            frozen["decision"],"BLIND_BASELINE_INVALID_REVIEW_REQUIRED")
        self.assertFalse(frozen["terminal_candidate"])

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
        # The helper self-test covers legacy behavior, explicit valid-report,
        # future VAD impact scope, unrelated-metric drift rejection, and a
        # future self-described workflow/seed identity without touching I020.
        module.self_test()


if __name__=="__main__":
    unittest.main()
