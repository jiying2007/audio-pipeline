#!/usr/bin/env python3
"""Regression cases for the actual impact-aware Verify summary contract."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.ci_failure import aggregate, validation  # noqa: E402


class SummaryContractTests(unittest.TestCase):
    def setUp(self):
        self.results = {
            "impact": "success", "fast": "success", "hosted_real": "success",
            "lab": "success", "ci": "success", "quality": "success",
            "audio": "success", "resource": "success", "codeql": "success",
        }
        self.selected = {name: "true" for name in
                         ("lab", "ci", "quality", "audio", "resource", "codeql")}
        self.docs_only = "false"

    def classify(self):
        return aggregate(self.results, docs_only=self.docs_only, selected=self.selected)

    def assert_rejected(self, out, domain, category=None):
        self.assertFalse(out["passed"])
        self.assertNotEqual(out["category"], "NONE")
        self.assertIn(domain, out["failed_domains"])
        self.assertTrue(any(item["domain"] == domain for item in out["violations"]))
        if category:
            self.assertEqual(out["category"], category)

    def test_complete_main_matrix_passes(self):
        out = self.classify()
        self.assertTrue(out["passed"])
        self.assertEqual(out["category"], "NONE")
        self.assertEqual(out["failed_domains"], [])
        self.assertEqual(out["expected_results"], self.results)

    def test_hosted_real_only_failure_is_visible(self):
        self.results["hosted_real"] = "failure"
        self.assert_rejected(self.classify(), "hosted_real", "DSP_QUALITY_REGRESSION")

    def test_required_quality_skip_is_visible(self):
        self.results["quality"] = "skipped"
        out = self.classify()
        self.assert_rejected(out, "quality", "EVIDENCE_INVALID")
        self.assertEqual(out["expected_results"]["quality"], "success")

    def test_every_required_domain_failure_and_cancellation_rejects(self):
        for name in self.results:
            for result in ("failure", "cancelled", "skipped"):
                with self.subTest(domain=name, result=result):
                    self.results[name] = result
                    self.assert_rejected(self.classify(), name)
                    self.results[name] = "success"

    def test_docs_only_intentional_skips_pass(self):
        self.docs_only = "true"
        self.results["hosted_real"] = "skipped"
        for name in self.selected:
            self.selected[name] = "false"
            self.results[name] = "skipped"
        self.assertTrue(self.classify()["passed"])

    def test_non_docs_selected_subset_passes(self):
        for name in ("lab", "resource", "codeql"):
            self.selected[name] = "false"
            self.results[name] = "skipped"
        self.assertTrue(self.classify()["passed"])

    def test_unselected_job_must_actually_be_skipped(self):
        self.selected["quality"] = "false"
        for result in ("success", "failure", "cancelled"):
            with self.subTest(result=result):
                self.results["quality"] = result
                self.assert_rejected(self.classify(), "quality", "EVIDENCE_INVALID")

    def test_docs_only_hosted_execution_rejects(self):
        self.docs_only = "true"
        self.assert_rejected(self.classify(), "hosted_real", "EVIDENCE_INVALID")

    def test_invalid_docs_selection_rejects(self):
        for value in ("", "False", "0", "success"):
            with self.subTest(value=value):
                self.docs_only = value
                self.assert_rejected(self.classify(), "impact", "EVIDENCE_INVALID")

    def test_missing_or_malformed_domain_selection_rejects(self):
        for name in tuple(self.selected):
            for value in (None, "", "False", "0"):
                with self.subTest(domain=name, value=value):
                    if value is None:
                        del self.selected[name]
                    else:
                        self.selected[name] = value
                    self.assert_rejected(self.classify(), "impact", "EVIDENCE_INVALID")
                    self.selected[name] = "true"

    def test_missing_or_unknown_result_rejects(self):
        for name in tuple(self.results):
            for value in (None, "", "neutral", "SUCCESS"):
                with self.subTest(domain=name, value=value):
                    if value is None:
                        del self.results[name]
                    else:
                        self.results[name] = value
                    self.assert_rejected(self.classify(), name, "EVIDENCE_INVALID")
                    self.results[name] = "success"

    def cli(self, output, *, enforce=True):
        command = [sys.executable, str(ROOT / "scripts/ci_failure.py"),
                   "--output", str(output), "aggregate", "--docs-only", self.docs_only]
        if enforce:
            command.append("--enforce")
        for name, value in self.results.items():
            command.extend(["--" + name.replace("_", "-"), value])
        for name, value in self.selected.items():
            command.extend(["--expect-" + name, value])
        return subprocess.run(command, text=True, capture_output=True, check=False)

    def test_cli_failure_writes_same_receipt_before_nonzero_exit(self):
        self.results["hosted_real"] = "failure"
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "nested/summary.json"
            completed = self.cli(output)
            self.assertEqual(completed.returncode, 1, completed.stderr)
            saved = json.loads(output.read_text())
            self.assertEqual(saved, json.loads(completed.stdout))
            self.assertEqual(saved, self.classify())
            self.assert_rejected(saved, "hosted_real")

    def test_cli_success_and_diagnostic_mode(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "summary.json"
            self.assertEqual(self.cli(output).returncode, 0)
            self.assertTrue(json.loads(output.read_text())["passed"])
            self.results["quality"] = "skipped"
            self.assertEqual(self.cli(output, enforce=False).returncode, 0)
            self.assertFalse(json.loads(output.read_text())["passed"])
            self.assertEqual(self.cli(output).returncode, 1)

    def test_cli_omitted_inputs_create_failure_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "summary.json"
            completed = subprocess.run(
                [sys.executable, str(ROOT / "scripts/ci_failure.py"), "--output", str(output),
                 "aggregate", "--enforce"], text=True, capture_output=True, check=False)
            self.assertEqual(completed.returncode, 1, completed.stderr)
            self.assert_rejected(json.loads(output.read_text()), "impact", "EVIDENCE_INVALID")

    def test_validation_reporting_is_unchanged(self):
        with tempfile.TemporaryDirectory() as directory:
            report = Path(directory) / "report.json"
            report.write_text(json.dumps({"cases": [{"passed": False, "case_id": "dt-0",
                                                     "scenario": "double-talk"}]}))
            out = validation(report)
            self.assertEqual(out["category"], "DSP_QUALITY_REGRESSION")
            self.assertEqual(out["test"], "dt-0")
            self.assertEqual(out["failed_cases"], 1)


if __name__ == "__main__":
    unittest.main()
