#!/usr/bin/env python3
"""Nineteen registered metadata controls; no build, target or DSP execution."""
from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import signal
import sys
import time
import unittest
from unittest import mock

HERE = Path(__file__).resolve().parent


def load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


original = load("frozen_b3_deadline_metadata", "fe09_b3_f0_qualification.py")
repaired = load("repaired_b3_deadline_metadata", "fe09_b3_f0_deadline_r1_qualification.py")


def job() -> dict:
    return {"status": "OBSERVED_ACTUAL_JOB_START", "run_id": 71,
            "run_attempt": 1, "timeout_minutes": 15,
            "archive_reserve_seconds": 60,
            "started_at_epoch": 1000.0, "deadline_epoch": 1900.0}


def construct(module=repaired, *, origin=100.0, epoch=1200.0,
              ci=False, observed=None, path="synthetic-deadline.json"):
    env = ({"GITHUB_ACTIONS": "true", "GITHUB_RUN_ID": "71",
            "GITHUB_RUN_ATTEMPT": "1"} if ci else {})
    with (mock.patch.dict(module.os.environ, env, clear=True),
          mock.patch.object(module.time, "monotonic", return_value=origin),
          mock.patch.object(module.time, "time", return_value=epoch),
          mock.patch.object(module, "read_json", return_value=copy.deepcopy(observed))):
        return module.Budget(path)


def record(budget, elapsed=1.0):
    with mock.patch.object(repaired.time, "monotonic",
                           return_value=budget.started + elapsed):
        return budget.record()


class DurationControls(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # A regression may not silently edit its frozen comparator.
        actual = hashlib.sha256((HERE / "fe09_b3_f0_qualification.py").read_bytes()).hexdigest()
        if actual != "f782660590731e73f43c2fab638e84d277c11d36119560dfb8878b28e2456f6c":
            raise AssertionError("frozen original collector changed")
        identity_bytes = (repaired.REPAIR_DOCS / "IDENTITY_CONTROL.json").read_bytes()
        if hashlib.sha256(identity_bytes).hexdigest() != repaired.IDENTITY_CONTROL_SHA:
            raise AssertionError("actual failed-run identity projections changed")
        cls.identity_control = json.loads(identity_bytes)

    def test_C01_original_counterexample_and_new_scalar(self):
        origin = 212.2
        old = construct(original, origin=origin)
        old_record = record(old)
        self.assertEqual(old_record["effective_deadline_offset_seconds"],
                         math.nextafter(300.0, math.inf))
        new_record = record(construct(origin=origin))
        self.assertEqual(new_record["effective_deadline_offset_seconds"], 300.0)
        repaired.validate_retained_budget(new_record)

    def test_C02_local_zero_origin(self):
        r = record(construct(origin=0.0))
        self.assertEqual(r["effective_deadline_offset_seconds"], 300.0)
        repaired.validate_retained_budget(r)

    def test_C03_large_monotonic_origin(self):
        r = record(construct(origin=2**32 + 0.125))
        self.assertEqual(r["effective_deadline_offset_seconds"], 300.0)
        repaired.validate_retained_budget(r)

    def test_C04_ample_original_job_window(self):
        r = record(construct(ci=True, observed=job()))
        self.assertEqual(r["effective_deadline_offset_seconds"], 300.0)
        repaired.validate_retained_budget(r)

    def test_C05_original_job_window_40_25(self):
        b = construct(ci=True, observed=job(), epoch=1799.75)
        r = record(b)
        self.assertEqual(r["effective_deadline_offset_seconds"], 40.25)
        with mock.patch.object(repaired.time, "monotonic", return_value=b.started + 1.0):
            self.assertEqual(b.remaining(), 39.25)
        repaired.validate_retained_budget(r)

    def test_C06_exhausted_original_job_window(self):
        b = construct(ci=True, observed=job(), epoch=1840.0)
        with (mock.patch.object(repaired.time, "monotonic", return_value=b.started),
              self.assertRaisesRegex(repaired.ExecutionBlocked, "BUDGET_EXHAUSTED")):
            b.remaining()

    def test_C07_child_cap_is_preserved(self):
        b = construct()
        with mock.patch.object(repaired.time, "monotonic", return_value=b.started + 1.0):
            self.assertEqual(b.remaining(10), 10)

    def test_C08_elapsed_above_effective_rejected(self):
        r = record(construct(), elapsed=301.0)
        with self.assertRaisesRegex(repaired.Rejected, "RETAINED_FROZEN_WALL_BUDGET"):
            repaired.validate_retained_budget(r)

    def test_C09_nextafter_300_still_rejected(self):
        r = record(construct())
        r["effective_deadline_offset_seconds"] = math.nextafter(300.0, math.inf)
        with self.assertRaisesRegex(repaired.Rejected, "RETAINED_FROZEN_WALL_BUDGET"):
            repaired.validate_retained_budget(r)

    def test_C10_zero_elapsed_still_rejected(self):
        r = record(construct(), elapsed=0.0)
        with self.assertRaisesRegex(repaired.Rejected, "RETAINED_FROZEN_WALL_BUDGET"):
            repaired.validate_retained_budget(r)

    def test_C11_changed_job_timeout_rejected(self):
        j = job(); j["timeout_minutes"] = 16
        with self.assertRaisesRegex(repaired.Rejected, "ORIGINAL_JOB_TIMEOUT_CHANGED"):
            construct(ci=True, observed=j)

    def test_C12_changed_archive_reserve_rejected(self):
        j = job(); j["archive_reserve_seconds"] = 61
        with self.assertRaisesRegex(repaired.Rejected, "ORIGINAL_JOB_TIMEOUT_CHANGED"):
            construct(ci=True, observed=j)

    def test_C13_mismatched_run_identity_rejected(self):
        j = job(); j["run_id"] = 72
        with self.assertRaisesRegex(repaired.Rejected, "ORIGINAL_JOB_DEADLINE_UNPROVEN"):
            construct(ci=True, observed=j)

    def test_C14_missing_CI_deadline_rejected(self):
        with self.assertRaisesRegex(repaired.ExecutionBlocked, "ORIGINAL_JOB_DEADLINE_MISSING"):
            construct(ci=True, observed=job(), path=None)

    def test_C15_retained_timeout_still_rejected(self):
        r = record(construct())
        r["commands"] = [{"timeout": True, "elapsed_seconds": 1.0,
                          "timeout_seconds": 2.0, "started_offset_seconds": 0.0}]
        with self.assertRaisesRegex(repaired.Rejected, "RETAINED_CHILD_DEADLINE"):
            repaired.validate_retained_budget(r)

    def test_C16_command_over_original_bound_rejected(self):
        r = record(construct())
        r["commands"] = [{"elapsed_seconds": 3.01,
                          "timeout_seconds": 2.0, "started_offset_seconds": 0.0}]
        with self.assertRaisesRegex(repaired.Rejected, "RETAINED_CHILD_DEADLINE"):
            repaired.validate_retained_budget(r)

    def test_C17_actual_case_and_collector_namespace_projections(self):
        f = self.identity_control
        self.assertFalse(f["source"]["original_qualification"])
        self.assertEqual(f["source"]["complete_admitted_cohorts"], 0)
        self.assertEqual(repaired.IDENTITY, original.IDENTITY)
        self.assertNotEqual(repaired.IDENTITY, repaired.COLLECTOR_IDENTITY)
        repaired.validate_case_identity(f["case_identity_projection"])
        repaired.validate_collector_identity(f["collector_identity_projection"],
                                            f["source"]["execution_source"])

    def test_C18_collector_ID_in_actual_case_projection_rejected(self):
        r = copy.deepcopy(self.identity_control["case_identity_projection"])
        r["id"] = repaired.COLLECTOR_IDENTITY
        with self.assertRaisesRegex(repaired.Rejected, "CASE_IDENTITY_OR_SOURCE_ROLE"):
            repaired.validate_case_identity(r)

    def test_C19_scientific_ID_in_actual_receipt_projection_rejected(self):
        r = copy.deepcopy(self.identity_control["collector_identity_projection"])
        r["id"] = original.IDENTITY
        with self.assertRaisesRegex(repaired.Rejected, "RETAINED_SOURCE_OR_AUTHORITY"):
            repaired.validate_collector_identity(
                r, self.identity_control["source"]["execution_source"])


def main() -> int:
    started = time.monotonic()
    signal.alarm(10)
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(DurationControls)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    elapsed = time.monotonic() - started
    signal.alarm(0)
    passed = result.wasSuccessful() and result.testsRun == 19 and elapsed <= 10
    print(json.dumps({"id": "FE09-B3-F0-DEADLINE-ACCOUNTING-R1-METADATA",
                      "role": "SYNTHETIC_BUDGET_AND_ACTUAL_IDENTITY_PROJECTIONS_ONLY",
                      "controls": result.testsRun, "expected_controls": 19,
                      "failures": len(result.failures), "errors": len(result.errors),
                      "elapsed_seconds": elapsed, "budget_seconds": 10,
                      "DSP_frames": 0, "engineering_target_processes": 0,
                      "status": "PASS" if passed else "FAIL"}, sort_keys=True))
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
