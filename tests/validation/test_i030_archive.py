#!/usr/bin/env python3
"""Offline contracts for exact-byte I030 donor stability diagnostic evidence archive."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import re
import unittest

ROOT=Path(__file__).resolve().parents[2]
SCRIPT=ROOT/".github/program/i030_archive.py"
WORKFLOW=ROOT/".github/workflows/i030-evidence-archive.yml"
PROGRAM_ARCHIVE=ROOT/".github/workflows/program-iteration.yml"
CLOSURE=ROOT/(
    ".github/research/continuous-optimization/development-v4/"
    "i030-ns-upstream-donor-joint-residual-stability-decomposition-v1-result.json"
)

SPEC=importlib.util.spec_from_file_location("i030_archive",SCRIPT)
archive=importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(archive)


class I030ArchiveTests(unittest.TestCase):
    def test_closure_is_terminal_non_shipping_and_archive_bound(self):
        closure=json.loads(CLOSURE.read_text(encoding="utf-8"))
        expected=archive.validate_closure(closure)
        self.assertEqual(closure["status"],"CLOSED_DIAGNOSTIC_ONLY")
        self.assertEqual(len(expected),11)
        self.assertIn("SHA256SUMS",expected)
        self.assertEqual(
            closure["authoritative_execution"]["artifact_id"],
            archive.EXPECTED_ARTIFACT,
        )
        self.assertFalse(closure["fresh_authority"]["rerun_allowed"])
        self.assertEqual(
            closure["reviewed_decision"],
            "PRE_READY_DONOR_TRANSFER_FAILURE_ASSOCIATED_WITH_JOINT_SUMMARY_INCOHERENCE_AND_CONDITION_HETEROGENEITY_NOT_SIMPLE_POOL_DISPERSION_NO_CANDIDATE",
        )
        self.assertEqual(closure["pre_ready_speech_review"]["paired_cases"],72)
        self.assertEqual(closure["pre_ready_speech_review"]["gap_wins"],43)
        self.assertEqual(closure["pre_ready_speech_review"]["gap_losses"],29)
        self.assertFalse(
            closure["root_cause_review"]["simple_between_donor_pool_dispersion_supported"])
        self.assertTrue(
            closure["root_cause_review"]["joint_summary_algebra_incoherence_associated_with_pre_ready_failures"])
        self.assertFalse(
            closure["authority_boundary"]["reference_source_candidate_selected"])
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

    def test_publisher_is_push_only_and_uses_one_dedicated_writer(self):
        text=WORKFLOW.read_text(encoding="utf-8")
        expected="GH_WRITE_TOKEN: $"+"{{ secrets.RESEARCH_AUTOMATION_TOKEN }}"
        bindings=[
            line.strip()
            for line in text.splitlines()
            if line.strip().startswith("GH_WRITE_TOKEN:")
        ]
        self.assertEqual(bindings,[expected])
        self.assertEqual(
            set(re.findall(r"secrets\.([A-Za-z0-9_]+)",text)),
            {"RESEARCH_AUTOMATION_TOKEN"},
        )
        self.assertIn(
            "if: github.event_name == 'push' && github.ref == 'refs/heads/main'",
            text,
        )
        self.assertNotIn("\n  workflow_dispatch:\n",text)
        self.assertNotIn("\n  schedule:\n",text)
        self.assertIn("persist-credentials: false",text)
        self.assertNotIn("contents: write",text)
        self.assertNotIn("pull-requests: write",text)

    def test_program_archive_covers_finalizer_and_archive_root(self):
        text=PROGRAM_ARCHIVE.read_text(encoding="utf-8")
        for required in (
            ".github/program/i030_archive.py",
            ".github/workflows/i030-evidence-archive.yml",
            "tests/validation/test_i030_archive.py",
            "validation/research/evidence/i030-36654157293/**",
        ):
            self.assertEqual(
                text.count("'"+required+"'"),
                2,
                "Program Archive push/pull coverage drift: "+required,
            )

    def test_archive_branch_is_separate_from_research_execution(self):
        self.assertTrue(
            archive.ARCHIVE_BRANCH.startswith("automation/i030-evidence-")
        )
        self.assertEqual(archive.EXPECTED_RUN,36654157293)
        self.assertEqual(archive.EXPECTED_ARTIFACT,11072280283)
        self.assertNotIn("candidate",archive.ARCHIVE_BRANCH)


if __name__=="__main__":
    unittest.main()
