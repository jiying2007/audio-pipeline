#!/usr/bin/env python3
"""Offline contracts for exact-byte I037 diagnostic evidence archive."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import re
import unittest

ROOT=Path(__file__).resolve().parents[2]
SCRIPT=ROOT/".github/program/i037_archive.py"
WORKFLOW=ROOT/".github/workflows/i037-evidence-archive.yml"
PROGRAM_ARCHIVE=ROOT/".github/workflows/program-iteration.yml"
CLOSURE=ROOT/(
    ".github/research/continuous-optimization/development-v4/"
    "i037-ns-noise-estimate-aggregation-exact-order-recovery-v1-result.json"
)

SPEC=importlib.util.spec_from_file_location("i037_archive",SCRIPT)
archive=importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(archive)


class I037ArchiveTests(unittest.TestCase):
    def test_closure_is_terminal_and_archive_bound(self):
        closure=json.loads(CLOSURE.read_text(encoding="utf-8"))
        expected=archive.validate_closure(closure)
        self.assertEqual(closure["status"],"CLOSED_DIAGNOSTIC_ONLY")
        self.assertEqual(len(expected),11)
        self.assertEqual(
            expected["SHA256SUMS"],
            "29177958e610747e4d1606e0110e94146bbed4abdb9ae2634984c16cb0c39248",
        )
        self.assertEqual(
            closure["authoritative_execution"]["artifact_id"],
            archive.EXPECTED_ARTIFACT,
        )
        self.assertTrue(
            closure["authoritative_execution"]["internal_sha256sums_verified"])
        self.assertFalse(closure["fresh_authority"]["rerun_allowed"])
        self.assertTrue(
            closure["root_cause_review"]["exact_order_reconstruction_recovered"])
        self.assertFalse(
            closure["root_cause_review"]
            ["simple_all_bin_aggregation_dilution_explanation_supported"])
        self.assertFalse(
            closure["root_cause_review"]
            ["fixed_speech_band_consistently_improves_alignment"])
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
                "TRUSTED_CLOSURE_READY_FOR_ARCHIVE",
                "DURABLE_ARCHIVE_PRESENT_AND_VERIFIED",
            },
        )
        if status["status"]=="DURABLE_ARCHIVE_PRESENT_AND_VERIFIED":
            self.assertEqual(status["members"],11)

    def test_publisher_is_push_only_and_uses_ephemeral_branch_writer(self):
        text=WORKFLOW.read_text(encoding="utf-8")
        expected="GH_WRITE_TOKEN: $"+ "{{ github.token }}"
        bindings=[
            line.strip()
            for line in text.splitlines()
            if line.strip().startswith("GH_WRITE_TOKEN:")
        ]
        self.assertEqual(bindings,[expected])
        self.assertEqual(
            set(re.findall(r"secrets\.([A-Za-z0-9_]+)",text)),
            set(),
        )
        self.assertIn(
            "if: github.event_name == 'push' && github.ref == 'refs/heads/main'",
            text,
        )
        self.assertNotIn("\n  workflow_dispatch:\n",text)
        self.assertNotIn("\n  schedule:\n",text)
        self.assertIn("persist-credentials: false",text)
        publish=text[text.index("\n  publish:"):]
        self.assertIn("      contents: write",publish)
        self.assertNotIn("pull-requests: write",publish)

    def test_program_archive_covers_finalizer_and_archive_root(self):
        text=PROGRAM_ARCHIVE.read_text(encoding="utf-8")
        for required in (
            ".github/program/i037_archive.py",
            ".github/workflows/i037-evidence-archive.yml",
            "tests/validation/test_i037_archive.py",
            "validation/research/evidence/i037-36824635292/**",
        ):
            self.assertEqual(
                text.count("'"+required+"'"),
                2,
                "Program Archive push/pull coverage drift: "+required,
            )

    def test_archive_branch_is_separate_from_research_execution(self):
        self.assertTrue(
            archive.ARCHIVE_BRANCH.startswith("automation/i037-evidence-")
        )
        self.assertEqual(archive.EXPECTED_RUN,36824635292)
        self.assertEqual(archive.EXPECTED_ARTIFACT,11144499769)
        self.assertNotIn("candidate",archive.ARCHIVE_BRANCH)


if __name__=="__main__":
    unittest.main()
