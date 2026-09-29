#!/usr/bin/env python3
"""Offline contracts for the exact-byte I028 temporal diagnostic evidence archive."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / ".github/program/i028_archive.py"
WORKFLOW = ROOT / ".github/workflows/i028-evidence-archive.yml"
PROGRAM_ARCHIVE = ROOT / ".github/workflows/program-iteration.yml"
CLOSURE = ROOT / (
    ".github/research/continuous-optimization/development-v4/"
    "i028-ns-upstream-reference-readiness-temporal-decomposition-v1-result.json"
)

SPEC = importlib.util.spec_from_file_location("i028_archive", SCRIPT)
archive = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(archive)


class I028ArchiveTests(unittest.TestCase):
    def test_closure_is_terminal_non_shipping_and_archive_bound(self):
        closure = json.loads(CLOSURE.read_text(encoding="utf-8"))
        expected = archive.validate_closure(closure)
        self.assertEqual(closure["status"], "CLOSED_DIAGNOSTIC_ONLY")
        self.assertEqual(len(expected), 11)
        self.assertIn("SHA256SUMS", expected)
        self.assertEqual(
            closure["authoritative_execution"]["artifact_id"],
            archive.EXPECTED_ARTIFACT,
        )
        self.assertFalse(closure["fresh_authority"]["rerun_allowed"])
        self.assertEqual(
            closure["decision"],
            "NS_UPSTREAM_REFERENCE_READINESS_TEMPORAL_DECOMPOSED_REVIEW_REQUIRED",
        )
        self.assertEqual(
            closure["reviewed_decision"],
            "PRE_READY_SPEECH_DRIVEN_BY_EARLY_TARGET_AND_DELAYED_INITIAL_REFERENCE_ARRIVAL_CAFETERIA_AMPLIFIED_NO_CANDIDATE",
        )
        self.assertTrue(
            closure["target_accounting"]["all_raw_targets_represented_exactly_once"]
        )
        self.assertEqual(closure["target_accounting"]["raw_target_count"],17046)
        self.assertTrue(
            all(value is False for value in closure["authority_boundary"].values())
        )

    def test_archive_is_ready_or_exactly_committed(self):
        closure = json.loads(CLOSURE.read_text(encoding="utf-8"))
        expected = archive.validate_closure(closure)
        status = archive.check_repository(expected)
        self.assertIn(
            status["status"],
            {
                "TRUSTED_CLOSURE_READY_FOR_ARCHIVE",
                "DURABLE_ARCHIVE_PRESENT_AND_VERIFIED",
            },
        )
        if status["status"] == "DURABLE_ARCHIVE_PRESENT_AND_VERIFIED":
            self.assertEqual(status["members"], 11)

    def test_publisher_is_push_only_and_uses_one_dedicated_writer(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        expected = "GH_WRITE_TOKEN: $" + "{{ secrets.RESEARCH_AUTOMATION_TOKEN }}"
        bindings = [
            line.strip()
            for line in text.splitlines()
            if line.strip().startswith("GH_WRITE_TOKEN:")
        ]
        self.assertEqual(bindings, [expected])
        self.assertEqual(
            set(re.findall(r"secrets\.([A-Za-z0-9_]+)", text)),
            {"RESEARCH_AUTOMATION_TOKEN"},
        )
        self.assertIn(
            "if: github.event_name == 'push' && github.ref == 'refs/heads/main'",
            text,
        )
        self.assertNotIn("\n  workflow_dispatch:\n", text)
        self.assertNotIn("\n  schedule:\n", text)
        self.assertIn("persist-credentials: false", text)
        self.assertNotIn("contents: write", text)
        self.assertNotIn("pull-requests: write", text)

    def test_program_archive_covers_finalizer_and_archive_root(self):
        text = PROGRAM_ARCHIVE.read_text(encoding="utf-8")
        for required in (
            ".github/program/i028_archive.py",
            ".github/workflows/i028-evidence-archive.yml",
            "tests/validation/test_i028_archive.py",
            "validation/research/evidence/i028-36579696633/**",
        ):
            self.assertEqual(
                text.count("'" + required + "'"),
                2,
                "Program Archive push/pull coverage drift: " + required,
            )

    def test_archive_branch_is_separate_from_research_execution(self):
        self.assertTrue(
            archive.ARCHIVE_BRANCH.startswith("automation/i028-evidence-")
        )
        self.assertEqual(archive.EXPECTED_RUN, 36579696633)
        self.assertEqual(archive.EXPECTED_ARTIFACT, 11038379441)
        self.assertNotIn("candidate", archive.ARCHIVE_BRANCH)


if __name__ == "__main__":
    unittest.main()
