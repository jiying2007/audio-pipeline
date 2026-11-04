#!/usr/bin/env python3
"""Default research verification must never depend on shipping approval.

Runs offline under Python 3.8+; intentionally checks only active required
entrypoints. Historic standalone release/certification documents are not
source of truth for research eligibility and are retired separately.
"""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class ResearchCIBoundaryTests(unittest.TestCase):
    def test_required_verify_has_no_product_release_authority(self):
        text = (ROOT / ".github/workflows/verify.yml").read_text(encoding="utf-8")
        for obsolete in (
            "certification/", "product-certification.yml", "shipping_approved",
            "REPOSITORY_GOVERNANCE_TOKEN", "tools/ap_certify.py",
            "tools/certification_provenance.py",
        ):
            with self.subTest(obsolete=obsolete):
                self.assertNotIn(obsolete, text)
        self.assertIn("name: Verify", text)
        self.assertIn("sh .github/scripts/verify-docs-gate.sh", text)
        self.assertIn("python3 scripts/ci_failure.py --self-test", text)
        self.assertIn("python3 tools/acoustic_upgrade_decision.py --self-test", text)

    def test_no_active_commercial_publication_entrypoints(self):
        for legacy in (
            ".github/workflows/release.yml",
            ".github/workflows/post-release-qualification-summary.yml",
            ".github/workflows/product-certification.yml",
        ):
            with self.subTest(legacy=legacy):
                self.assertFalse((ROOT / legacy).exists(),
                                 "commercial publication workflow must be retired")

    def test_doc_gate_keeps_source_science_and_excludes_release_approval(self):
        text = (ROOT / ".github/scripts/verify-docs-gate.sh").read_text(encoding="utf-8")
        self.assertIn("python3 tests/test_research_ci_boundary.py", text)
        for required in (
            "tests/validation/frontend_evolution/test_contracts.py",
            "scripts/ci_impact.py --self-test",
            "tests/validation/test_immutable_whitespace.py",
            "tests/validation/frontend_evolution/test_device_capture.py",
        ):
            with self.subTest(required=required):
                self.assertIn(required, text)
        for release_only in (
            "scripts/prepare_release.py --self-test",
            "scripts/release_manifest.py --self-test",
            "scripts/post_release_status.py --self-test",
            ".github/program/test_product_soak_observed_duration.py",
        ):
            with self.subTest(release_only=release_only):
                self.assertNotIn(release_only, text)


if __name__ == "__main__":
    unittest.main()
