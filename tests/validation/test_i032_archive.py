#!/usr/bin/env python3
"""Offline contracts for exact-byte I032 causal noise-scale diagnostic evidence archive."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import re
import unittest

ROOT=Path(__file__).resolve().parents[2]
SCRIPT=ROOT/".github/program/i032_archive.py"
WORKFLOW=ROOT/".github/workflows/i032-evidence-archive.yml"
PROGRAM_ARCHIVE=ROOT/".github/workflows/program-iteration.yml"
CLOSURE=ROOT/(
    ".github/research/continuous-optimization/development-v4/"
    "i032-ns-upstream-target-causal-noise-scale-observability-v1-result.json"
)

SPEC=importlib.util.spec_from_file_location("i032_archive",SCRIPT)
archive=importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(archive)


class I032ArchiveTests(unittest.TestCase):
    def test_closure_is_terminal_observable_only_and_archive_bound(self):
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
            "TARGET_CAUSAL_NS_NOISE_SCALE_FIDELITY_SUPPORTED_NO_NORMALIZATION_OR_REFERENCE_SOURCE_CANDIDATE",
        )
        fidelity=closure["fidelity_review"]
        self.assertTrue(fidelity["supported"])
        self.assertLessEqual(fidelity["median_absolute_error_db"],3.0)
        self.assertLessEqual(fidelity["p90_absolute_error_db"],6.0)
        self.assertTrue(
            closure["root_cause_review"]["target_causal_noise_scale_observable_supported"])
        self.assertFalse(
            closure["root_cause_review"]["direct_absolute_normalization_mapping_supported"])
        self.assertFalse(
            closure["authority_boundary"]["noise_scale_normalization_selected"])
        self.assertFalse(
            closure["authority_boundary"]["source_patch_selected"])
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
        expected="GH_WRITE_TOKEN: $"+ "{{ secrets.RESEARCH_AUTOMATION_TOKEN }}"
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
            ".github/program/i032_archive.py",
            ".github/workflows/i032-evidence-archive.yml",
            "tests/validation/test_i032_archive.py",
            "validation/research/evidence/i032-36688937963/**",
        ):
            self.assertEqual(
                text.count("'"+required+"'"),
                2,
                "Program Archive push/pull coverage drift: "+required,
            )

    def test_archive_branch_is_separate_from_research_execution(self):
        self.assertTrue(
            archive.ARCHIVE_BRANCH.startswith("automation/i032-evidence-")
        )
        self.assertEqual(archive.EXPECTED_RUN,36688937963)
        self.assertEqual(archive.EXPECTED_ARTIFACT,11084259758)
        self.assertNotIn("candidate",archive.ARCHIVE_BRANCH)


if __name__=="__main__":
    unittest.main()
