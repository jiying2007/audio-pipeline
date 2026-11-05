#!/usr/bin/env python3
"""Research-only boundary for retired product certifiers (Python 3.8+).

Source-only / offline: no product certificate, hardware action or Release I/O.
"""
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
RETIRED_GENERATORS = (
    "tools/ap_certify.py",
    "tools/certification_provenance.py",
)
HISTORICAL_AUDITORS = (
    "certification/validate_record.py",
    "certification/validate_archive_receipt.py",
)


class ResearchCertificationCodeBoundary(unittest.TestCase):
    def test_no_product_certificate_generation_entrypoint(self):
        for rel in RETIRED_GENERATORS:
            with self.subTest(path=rel):
                self.assertFalse((ROOT / rel).exists(),
                                 "retired commercial collector must remain absent")
        self.assertTrue((ROOT / "tools/target_evidence.py").is_file(),
                        "independent research target measurements must remain")

    def test_historical_audit_explicit_only(self):
        for rel in HISTORICAL_AUDITORS:
            with self.subTest(path=rel):
                path = ROOT / rel
                self.assertTrue(path.is_file(), "preserve offline historic replay")
                process = subprocess.run(
                    [sys.executable, str(path)],
                    cwd=str(ROOT),
                    capture_output=True, text=True,
                )
                self.assertNotEqual(process.returncode, 0)
                self.assertIn("--historical-replay-only", process.stderr)
                self.assertIn("no current research/product authority", process.stderr)

    def test_archived_audit_self_tests_remain_reproducible(self):
        for rel in HISTORICAL_AUDITORS:
            with self.subTest(path=rel):
                process = subprocess.run(
                    [sys.executable, str(ROOT / rel), "--self-test"],
                    cwd=str(ROOT), capture_output=True, text=True,
                )
                self.assertEqual(process.returncode, 0, process.stderr)


if __name__ == "__main__":
    unittest.main()
