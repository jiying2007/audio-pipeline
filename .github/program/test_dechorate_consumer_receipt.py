#!/usr/bin/env python3
"""Offline unit controls for exact production receipt routing, not acquisition.

Compile selected definitions from the adjacent production source rather than
copying their logic. Upstream run/artifact providers are explicit unit fixtures;
the existing complete V2 suite remains responsible for integrated source/Git
and transport validation. No live provider, credentials or DSP is used here.
"""
from __future__ import annotations

import argparse
import ast
import contextlib
import copy
import io
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock
import zipfile

SOURCE = Path(__file__).with_name("dechorate_governance_v2.py")


def production():
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"), filename=str(SOURCE))
    names = {"Denied", "PrivateBypassRefused", "need", "integer", "cli_integer", "consumer_receipt",
             "preflight", "envelope", "main"}
    definitions = [node for node in tree.body
                   if isinstance(node, (ast.FunctionDef, ast.ClassDef)) and node.name in names]
    assignments = [node for node in tree.body if isinstance(node, ast.Assign) and
                   any(isinstance(target, ast.Name) and target.id in ("IDENTITY", "FALSE_FLAGS")
                       for target in node.targets)]
    if {node.name for node in definitions} != names or len(definitions) != len(names):
        raise AssertionError("PRODUCTION_DEFINITION_INVENTORY_CHANGED")
    module = ast.Module(body=assignments + definitions, type_ignores=[])
    namespace = {"__name__": "offline_exact_production_definitions", "__doc__": "offline unit control",
                 "argparse": argparse, "Path": Path, "os": os, "sys": sys,
                 "json": json, "re": re, "subprocess": subprocess, "zipfile": zipfile}
    exec(compile(module, str(SOURCE), "exec"), namespace)
    return namespace


class ConsumerReceiptTests(unittest.TestCase):
    def setUp(self):
        self.module = production()
        self.api = mock.Mock(name="offline_provider_not_live")
        self.record = {"id": 7001, "run_attempt": 1}
        self.proof = {"id": 8001, "zip_sha256": "a" * 64}
        self.run = mock.Mock(return_value=self.record)
        self.fetch = mock.Mock()
        self.module.update(run_record=self.run, artifact=self.fetch)

    def receipt(self, attempt=1):
        return {"phase": "CHALLENGE" if attempt == 1 else "CONSUMER_SECOND",
                "scope": {"github_run_id": "7001", "github_run_attempt": str(attempt)}}

    def call(self, value, attempt=1):
        self.fetch.return_value = value, self.proof
        self.record["run_attempt"] = attempt
        return self.module["consumer_receipt"](self.api, 7001, attempt)

    def denied(self, value, reason, attempt=1):
        before = copy.deepcopy(value)
        self.run.reset_mock()
        self.fetch.reset_mock()
        with self.assertRaises(self.module["Denied"]) as caught:
            self.call(value, attempt)
        self.assertEqual(str(caught.exception), reason)
        self.assertEqual(value, before)
        self.run.assert_called_once_with(self.api, 7001, attempt)
        self.fetch.assert_called_once_with(self.api, self.record,
            f"dechorate-event-source-range-7001-{attempt}", "source-range.json")
        self.assertEqual(self.api.mock_calls, [])

    def test_rejected_without_scope_has_source_reason(self):
        self.denied({"phase": "REJECTED", "reason": "LIVE_PR_SOURCE_OR_EVENT_METADATA_DRIFT"},
                    "CONSUMER_SOURCE_REJECTED")

    def test_rejected_with_valid_scope_is_never_a_challenge(self):
        self.denied({**self.receipt(), "phase": "REJECTED"}, "CONSUMER_SOURCE_REJECTED")

    def test_rejected_with_malformed_scope_remains_source_rejection(self):
        for value in (None, [], 1, True, "unknown", {}):
            with self.subTest(scope=value):
                self.denied({"phase": "REJECTED", "scope": value}, "CONSUMER_SOURCE_REJECTED")

    def test_rejected_attempt_two_is_not_accepted(self):
        self.denied({**self.receipt(2), "phase": "REJECTED"}, "CONSUMER_SOURCE_REJECTED", 2)

    def test_missing_scope_is_not_attempt_drift(self):
        self.denied({"phase": "CHALLENGE"}, "CONSUMER_ARTIFACT_SCOPE_MISSING_OR_INVALID")

    def test_non_object_scope_is_a_named_schema_rejection(self):
        for value in (None, [], ["7001", "1"], 1, True, "7001", 1.0):
            with self.subTest(scope=value):
                self.denied({"phase": "CHALLENGE", "scope": value},
                            "CONSUMER_ARTIFACT_SCOPE_MISSING_OR_INVALID")

    def test_non_object_receipt_fails_closed(self):
        for value in (None, [], 1, True, "REJECTED"):
            with self.subTest(receipt=value):
                self.denied(value, "CONSUMER_ARTIFACT_SCHEMA_DRIFT")

    def test_valid_first_returns_original_objects(self):
        receipt = self.receipt()
        first, proof, record = self.call(receipt)
        self.assertIs(first, receipt)
        self.assertIs(proof, self.proof)
        self.assertIs(record, self.record)

    def test_valid_second_returns_original_objects(self):
        receipt = self.receipt(2)
        first, proof, record = self.call(receipt, 2)
        self.assertIs(first, receipt)
        self.assertIs(proof, self.proof)
        self.assertIs(record, self.record)

    def test_actual_run_mismatch_keeps_existing_reason(self):
        for value in ("7002", "07001", 7001, True, None, [], {}):
            receipt = self.receipt()
            receipt["scope"]["github_run_id"] = value
            self.denied(receipt, "CONSUMER_ARTIFACT_ATTEMPT_DRIFT")

    def test_actual_attempt_mismatch_keeps_existing_reason(self):
        for value in ("2", "01", 1, True, None, [], {}):
            receipt = self.receipt()
            receipt["scope"]["github_run_attempt"] = value
            self.denied(receipt, "CONSUMER_ARTIFACT_ATTEMPT_DRIFT")

    def test_object_scope_with_missing_tuple_keeps_existing_reason(self):
        for scope in ({}, {"github_run_id": "7001"}, {"github_run_attempt": "1"}):
            self.denied({"phase": "CHALLENGE", "scope": scope}, "CONSUMER_ARTIFACT_ATTEMPT_DRIFT")

    def test_run_validation_failure_prevents_artifact_access(self):
        failure = self.module["Denied"]("ACTUAL_RUN_IDENTITY_DRIFT")
        self.run.side_effect = failure
        with self.assertRaises(self.module["Denied"]) as caught:
            self.call(self.receipt())
        self.assertIs(caught.exception, failure)
        self.fetch.assert_not_called()

    def test_artifact_validation_failure_remains_unchanged(self):
        failure = self.module["Denied"]("ARTIFACT_INNER_SEAL_DRIFT")
        self.fetch.side_effect = failure
        with self.assertRaises(self.module["Denied"]) as caught:
            self.call(self.receipt())
        self.assertIs(caught.exception, failure)
        self.fetch.assert_called_once()

    def test_arbitrary_original_reason_is_never_reflected(self):
        self.denied({"phase": "REJECTED", "reason": "PRIVATE_SENTINEL\n" * 1000},
                    "CONSUMER_SOURCE_REJECTED")

    def setup_preflight(self):
        self.fetch.return_value = {"phase": "REJECTED"}, self.proof
        self.module.update(producer_environment=mock.Mock(return_value=(9001, "b" * 40)),
            local_source=mock.Mock(return_value={}),
            source=SimpleNamespace(same_repo=lambda unused: True, Git=lambda unused: object()),
            validate_challenge=mock.Mock(side_effect=AssertionError("challenge must not run")),
            target_snapshot=mock.Mock(side_effect=AssertionError("source request must not run")),
            first_job=mock.Mock(side_effect=AssertionError("job request must not run")),
            ROOT=Path.cwd())
        return {"action": "completed", "repository": {},
                "workflow_run": {**self.record, "repository": {}, "head_repository": {}}}

    def test_actual_preflight_stops_before_challenge_or_extra_metadata(self):
        event = self.setup_preflight()
        with self.assertRaises(self.module["Denied"]) as caught:
            self.module["preflight"](event, {}, object(), self.api)
        self.assertEqual(str(caught.exception), "CONSUMER_SOURCE_REJECTED")
        self.assertEqual(self.run.call_count, 2)
        self.fetch.assert_called_once()
        for name in ("validate_challenge", "target_snapshot", "first_job"):
            self.module[name].assert_not_called()
        self.assertEqual(self.api.mock_calls, [])

    def test_cli_writes_rejected_false_authority_envelope(self):
        event = self.setup_preflight()
        written = mock.Mock()
        self.module.update(API=lambda unused: self.api, parsed=lambda unused: event,
                           write_new=written)
        with tempfile.TemporaryDirectory() as tmp:
            event_path = Path(tmp) / "event.json"
            event_path.write_text("{}")
            argv = ["consumer-test", "preflight", "--event-file", str(event_path),
                    "--output", str(Path(tmp) / "result.json")]
            with mock.patch.object(sys, "argv", argv), contextlib.redirect_stdout(io.StringIO()) as output:
                self.assertEqual(self.module["main"](), 1)
        written.assert_called_once()
        result = written.call_args.args[1]
        self.assertEqual(result["phase"], "REJECTED")
        self.assertEqual(result["reason"], "CONSUMER_SOURCE_REJECTED")
        self.assertEqual(result["decision"], "ORIGINAL_RESEARCH_GUARDS_REQUIRED")
        self.assertNotIn("scope", result)
        for key in (*self.module["FALSE_FLAGS"], "source_range_qualified", "governance_post_qualified"):
            self.assertIs(result[key], False)
        self.assertEqual(json.loads(output.getvalue())["reason"], "CONSUMER_SOURCE_REJECTED")


if __name__ == "__main__":
    unittest.main(verbosity=2)
