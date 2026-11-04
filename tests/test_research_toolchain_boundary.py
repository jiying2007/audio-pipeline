#!/usr/bin/env python3
"""Offline research-toolchain source contract (Python 3.8 compatible)."""
from pathlib import Path
import os
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/verify-research-toolchain.sh"

class ResearchToolchainBoundary(unittest.TestCase):
    def test_research_script_is_not_a_publication_entry(self):
        self.assertTrue(SCRIPT.is_file())
        self.assertFalse((ROOT / "scripts/verify-shipping-toolchain.sh").exists())
        text = SCRIPT.read_text(encoding="utf-8")
        for old in ("shipping", "certification", "gh release", "product-certified",
                    "git tag", "product-lifecycle"):
            with self.subTest(token=old):
                self.assertNotIn(old, text.lower())
        for required in ("research_compiler", "research_sysroot", "CMAKE_C_COMPILER",
                         "CMAKE_SYSROOT", "CMAKE_C_FLAGS", 'cmake "$@"',
                         "RESEARCH_COMPILER_UNAVAILABLE"):
            with self.subTest(required=required):
                self.assertIn(required, text)
        syntax = subprocess.run(["sh", "-n", str(SCRIPT)],
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                universal_newlines=True, timeout=5)
        self.assertEqual(syntax.returncode, 0, syntax.stderr)

    def test_compiler_missing_fails_before_any_file_effect(self):
        with tempfile.TemporaryDirectory(prefix="research-cc-missing-") as tmp:
            run = subprocess.run(["sh", str(SCRIPT)], cwd=tmp,
                                 env={"PATH": os.environ.get("PATH", "/usr/bin:/bin")},
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                 universal_newlines=True, timeout=5)
            self.assertNotEqual(run.returncode, 0)
            self.assertEqual(list(Path(tmp).iterdir()), [])

if __name__ == "__main__":
    unittest.main()
