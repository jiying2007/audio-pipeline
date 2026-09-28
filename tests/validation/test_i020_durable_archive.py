#!/usr/bin/env python3
"""Offline contract tests for the copy-only I020 durable evidence archive."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / ".github/program/i020_durable_archive.py"
WORKFLOW = ROOT / ".github/workflows/i020-durable-evidence-archive.yml"
PROGRAM_ARCHIVE = ROOT / ".github/workflows/program-iteration.yml"
MANIFEST = ROOT / ".github/research/continuous-optimization/development-v4/i020-blind-baseline-invalid-durable-evidence-v1.json"
REVIEW = ROOT / ".github/research/continuous-optimization/development-v4/i020-vad-weak-start-requires-blend-v1-blind-review.json"

SPEC = importlib.util.spec_from_file_location("i020_durable_archive", SCRIPT)
archive = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(archive)


class I020DurableArchiveTests(unittest.TestCase):
    def test_frozen_manifest_and_review_remain_copy_only(self):
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        review = json.loads(REVIEW.read_text(encoding="utf-8"))
        archive.validate_frozen(manifest, review)
        self.assertEqual(manifest["archive_root"], archive.EXPECTED_ROOT)
        self.assertEqual(manifest["status"], "FROZEN_ARCHIVE_MANIFEST")
        self.assertFalse(review["terminal_candidate"])
        self.assertTrue(manifest["authority_boundary"]["archive_copy_only"])
        self.assertFalse(review["authority_boundary"]["requalification_authorized"])
        self.assertFalse(review["authority_boundary"]["source_merge_authorized"])
        self.assertFalse(review["authority_boundary"]["shipping_authority"])

    def test_archive_is_manifest_only_or_exactly_verified(self):
        status = archive.check_repository()
        self.assertIn(
            status["status"],
            {"FROZEN_MANIFEST_READY_FOR_COPY", "DURABLE_ARCHIVE_PRESENT_AND_VERIFIED"},
        )
        if status["status"] == "DURABLE_ARCHIVE_PRESENT_AND_VERIFIED":
            self.assertEqual(status["members"], 11)

    def test_publisher_uses_only_dedicated_research_writer(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        expected = "GH_WRITE_TOKEN: $" + "{{ secrets.RESEARCH_AUTOMATION_TOKEN }}"
        bindings = [
            line.strip() for line in text.splitlines()
            if line.strip().startswith("GH_WRITE_TOKEN:")
        ]
        self.assertEqual(bindings, [expected])
        self.assertEqual(
            set(re.findall(r"secrets\.([A-Za-z0-9_]+)", text)),
            {"RESEARCH_AUTOMATION_TOKEN"},
        )
        self.assertNotIn("GH_WRITE_TOKEN: $" + "{{ github.token }}", text)
        self.assertIn("if: github.event_name != 'pull_request'", text)
        self.assertIn("persist-credentials: false", text)

    def test_program_archive_covers_finalizer_and_durable_evidence(self):
        text = PROGRAM_ARCHIVE.read_text(encoding="utf-8")
        for required in (
            ".github/program/i020_durable_archive.py",
            ".github/workflows/i020-durable-evidence-archive.yml",
            "tests/validation/test_i020_durable_archive.py",
            "validation/research/evidence/i020-blind-baseline-invalid-36304120808-36324803945/**",
        ):
            self.assertEqual(
                text.count("'" + required + "'"),
                2,
                "Program Archive push/pull coverage drift: " + required,
            )

    def test_archive_branch_is_separate_from_shipping_candidate(self):
        self.assertTrue(archive.ARCHIVE_BRANCH.startswith("automation/i020-durable-evidence-"))
        self.assertNotIn("source-patch", archive.ARCHIVE_BRANCH)
        self.assertEqual(archive.EXPECTED_SOURCE_RUN, 36304120808)
        self.assertEqual(archive.EXPECTED_RESUME_RUN, 36324803945)


if __name__ == "__main__":
    unittest.main()
