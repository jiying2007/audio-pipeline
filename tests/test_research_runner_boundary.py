#!/usr/bin/env python3
"""Prevent resurrection of product-certification runner control planes.

All checks are offline/source-only. Neither a runner nor a DUT is contacted.
"""
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]


def guard(workflow, preflight):
    if "  archive:" in workflow or "certification-archive" in workflow:
        raise ValueError("historical archive runner job reintroduced")
    if "shipping_" in workflow or "--shipping-" in workflow:
        raise ValueError("shipping toolchain inputs reintroduced")
    if "  repository_dispatch:" in workflow or "  schedule:" in workflow:
        raise ValueError("scientific runner readiness must remain manual")
    if "  workflow_dispatch:" not in workflow or "source_sha:" not in workflow:
        raise ValueError("exact-source manual preflight missing")
    if "options: [audio-validation, audio-builder, audio-target]" not in workflow:
        raise ValueError("research runner roles changed")
    for required in ("--target-cc", "--target-sysroot", "--target-toolchain-root",
                     "runs-on: [self-hosted, linux, audio-target]",
                     "runs-on: [self-hosted, linux, audio-validation]",
                     "runs-on: [self-hosted, linux, audio-builder]"):
        if required not in workflow:
            raise ValueError("research runner contract missing: " + required)
    if '"certification-archive",' in preflight or "--archive-command" in preflight:
        raise ValueError("obsolete archive CLI revived")
    for required in ("--target-cc", "--target-sysroot", "--target-toolchain-root",
                     "audio-validation", "audio-builder", "audio-target",
                     "source-revision", "NOT_READY"):
        if required not in preflight:
            raise ValueError("research runner verifier drift: " + required)


class RunnerResearchBoundary(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workflow = (ROOT / ".github/workflows/trusted-runner-readiness.yml").read_text(encoding="utf-8")
        cls.preflight = (ROOT / "tools/runner_preflight.py").read_text(encoding="utf-8")

    def test_real_workflow_is_source_bound_without_product_roles(self):
        guard(self.workflow, self.preflight)
        for name in ('docs/TRUSTED_RUNNERS.md', 'docs/TRUSTED_RUNNERS.zh-CN.md'):
            page = (ROOT / name).read_text(encoding='utf-8')
            self.assertIn('Research Runner Readiness', page)
            self.assertIn('HIL_ENABLED', page)

    def test_preflight_self_test_is_still_fail_closed(self):
        completed = subprocess.run(
            [sys.executable, "-B", str(ROOT / "tools/runner_preflight.py"), "--self-test"],
            capture_output=True, text=True, check=False, timeout=20,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn('self-hosted runner preflight self-test: OK', completed.stdout)

    def test_reject_hidden_product_runner_reintroduction(self):
        for mutation in (
            self.workflow.replace("  workflow_dispatch:",
                                  "  schedule:\n    - cron: '0 0 * * *'\n  workflow_dispatch:", 1),
            self.workflow.replace("  workflow_dispatch:",
                                  "  repository_dispatch:\n    types: [release]\n  workflow_dispatch:", 1),
            self.workflow.replace("  workflow_dispatch:",
                                  "  archive:\n    runs-on: [self-hosted, linux, certification-archive]\n  workflow_dispatch:", 1),
            self.workflow.replace("--target-cc", "--shipping-cc", 1),
        ):
            with self.subTest(change=mutation[:90]), self.assertRaises(ValueError):
                guard(mutation, self.preflight)
        self.assertRaises(ValueError, guard, self.workflow, self.preflight + "\n--archive-command\n")


if __name__ == "__main__":
    unittest.main()
