#!/usr/bin/env python3
"""Fail-closed source-only research audio quality gate contract, Python 3.8+."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/audio-quality-gates.yml"


def check_workflow(source):
    required = (
        "  workflow_call:",
        "  bandlimited-boundary:",
        "ap_resampler_tests|ap_contract_tests|ap_drift_res_tests",
        "  validation-smoke:",
        "validation/tools/authority.py --self-test",
        "validation/tools/dataset_lock.py validate",
        "validation/tools/run_validation.py --self-test",
        "  diagnostics-replay:",
        "ap_runtime_tests",
    )
    for item in required:
        if item not in source:
            raise AssertionError("scientific quality gate missing: " + item)
    forbidden = (
        "certification/validate_record.py",
        "certification/validate_archive_receipt.py",
        "certification/policies/",
        "Verify certification evidence validator",
        "gh release create",
        "gh release download",
        "shipping_approved",
    )
    for item in forbidden:
        if item in source:
            raise AssertionError("obsolete product certification authority: " + item)


class AudioResearchQualityBoundary(unittest.TestCase):
    def test_active_audio_workflow(self):
        check_workflow(WORKFLOW.read_text(encoding="utf-8"))

    def test_negative_product_certification_mutations(self):
        original = WORKFLOW.read_text(encoding="utf-8")
        for mutation in (
            "      - run: python3 certification/validate_record.py --self-test\n",
            "      - run: python3 certification/validate_archive_receipt.py --self-test\n",
            "      - run: gh release create v1.0.0 build/sdk\n",
            "      - run: echo shipping_approved=true\n",
        ):
            with self.subTest(mutation=mutation.strip()):
                with self.assertRaises(AssertionError):
                    check_workflow(original + mutation)

    def test_acoustic_gates_cannot_be_removed_to_make_pass(self):
        original = WORKFLOW.read_text(encoding="utf-8")
        for required in ("ap_resampler_tests|ap_contract_tests|ap_drift_res_tests",
                         "validation/tools/dataset_lock.py validate",
                         "ap_runtime_tests"):
            with self.subTest(required=required):
                with self.assertRaises(AssertionError):
                    check_workflow(original.replace(required, "REMOVED"))


if __name__ == "__main__":
    unittest.main()
