#!/usr/bin/env python3
"""Offline contracts for exact-byte invalid I036 evidence archive."""

from __future__ import annotations

import importlib.util,json
from pathlib import Path
import re
import unittest

ROOT=Path(__file__).resolve().parents[2]
SCRIPT=ROOT/".github/program/i036_archive.py"
WORKFLOW=ROOT/".github/workflows/i036-evidence-archive.yml"
PROGRAM_ARCHIVE=ROOT/".github/workflows/program-iteration.yml"
CLOSURE=ROOT/(
    ".github/research/continuous-optimization/development-v4/"
    "i036-ns-noise-estimate-aggregation-domain-decomposition-v1-result.json"
)

SPEC=importlib.util.spec_from_file_location("i036_archive",SCRIPT)
archive=importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(archive)


class I036ArchiveTests(unittest.TestCase):
    def test_closure_is_terminal_invalid_and_archive_bound(self):
        closure=json.loads(CLOSURE.read_text(encoding="utf-8"))
        expected=archive.validate_closure(closure)
        self.assertEqual(closure["status"],"CLOSED_INVALID_DIAGNOSTIC_ONLY")
        self.assertEqual(len(expected),11)
        self.assertEqual(
            expected["SHA256SUMS"],
            "e600fe5e84cfc295033fd9c87f7e65b2949c923104553bb7ed9087649ee336e6",
        )
        self.assertEqual(
            closure["authoritative_execution"]["artifact_id"],
            archive.EXPECTED_ARTIFACT,
        )
        self.assertEqual(
            closure["invalidity_review"]["invalid_reasons"],
            ["noise_rms_reconstruction"],
        )
        self.assertFalse(closure["fresh_authority"]["rerun_allowed"])
        self.assertFalse(
            closure["invalidity_review"]["post_hoc_gate_relaxation_authorized"])
        self.assertTrue(all(
            value is False for value in closure["authority_boundary"].values()
        ))

    def test_archive_is_ready_or_exactly_committed(self):
        closure=json.loads(CLOSURE.read_text(encoding="utf-8"))
        expected=archive.validate_closure(closure)
        status=archive.check_repository(expected)
        self.assertIn(
            status["status"],
            {
                "TRUSTED_INVALID_CLOSURE_READY_FOR_ARCHIVE",
                "DURABLE_INVALID_ARCHIVE_PRESENT_AND_VERIFIED",
            },
        )
        if status["status"]=="DURABLE_INVALID_ARCHIVE_PRESENT_AND_VERIFIED":
            self.assertEqual(status["members"],11)

    def test_publisher_is_push_only_and_ephemeral(self):
        text=WORKFLOW.read_text(encoding="utf-8")
        expected="GH_WRITE_TOKEN: $"+ "{{ github.token }}"
        bindings=[
            line.strip() for line in text.splitlines()
            if line.strip().startswith("GH_WRITE_TOKEN:")
        ]
        self.assertEqual(bindings,[expected])
        self.assertEqual(set(re.findall(r"secrets\.([A-Za-z0-9_]+)",text)),set())
        self.assertIn(
            "if: github.event_name == 'push' && github.ref == 'refs/heads/main'",
            text,
        )
        self.assertNotIn("\n  workflow_dispatch:\n",text)
        self.assertNotIn("\n  schedule:\n",text)
        self.assertIn("persist-credentials: false",text)
        self.assertNotIn("pull-requests: write",text)

    def test_program_archive_covers_finalizer_and_archive_root(self):
        text=PROGRAM_ARCHIVE.read_text(encoding="utf-8")
        for required in (
            ".github/program/i036_archive.py",
            ".github/workflows/i036-evidence-archive.yml",
            "tests/validation/test_i036_archive.py",
            "validation/research/evidence/i036-36803529573/**",
        ):
            self.assertEqual(
                text.count("'"+required+"'"),2,
                "Program Archive push/pull coverage drift: "+required,
            )

    def test_archive_branch_is_separate_from_research_execution(self):
        self.assertTrue(
            archive.ARCHIVE_BRANCH.startswith("automation/i036-evidence-")
        )
        self.assertEqual(archive.EXPECTED_RUN,36803529573)
        self.assertEqual(archive.EXPECTED_ARTIFACT,11137255580)
        self.assertNotIn("candidate",archive.ARCHIVE_BRANCH)


if __name__=="__main__":
    unittest.main()
