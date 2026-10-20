#!/usr/bin/env python3
"""No-network bounded official-source wrapper and failed-Artifact controls."""
from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import time
import unittest

import speech_source_stage_budget as stage
import speech_source


class BoundedSpeechSourceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="speech-stage-budget-")
        self.output = Path(self.tmp.name) / "source"

    def tearDown(self):
        self.tmp.cleanup()

    def worker(self, code: str) -> list[str]:
        return [sys.executable, "-c", code, str(self.output)]

    def assert_failure(self, reason: str, code: int | None):
        marker = self.output / "source-failure.json"
        self.assertTrue(marker.is_file() and not marker.is_symlink())
        receipt = json.loads(marker.read_text("utf-8"))
        self.assertEqual(receipt["status"], "DATA_OR_INFRASTRUCTURE_FAILURE")
        self.assertEqual(receipt["reason_code"], reason)
        self.assertEqual(receipt["source_url"], speech_source.URL)
        self.assertEqual(receipt["expected_archive_md5"], speech_source.MD5)
        self.assertEqual(receipt["transport_attempt_ceiling"], 3)
        self.assertEqual(receipt["worker_exit_code"], code)
        self.assertIs(receipt["source_substitution"], False)
        self.assertIs(receipt["shipping_authority"], False)
        self.assertIs(receipt["acoustic_validation_qualified"], False)
        self.assertFalse((self.output / "source-receipt.json").exists())

    def test_sleeping_network_child_terminated_and_small_negative_receipt(self):
        start = time.monotonic()
        got = stage.run_bounded(self.worker("import time; time.sleep(60)"),
                                self.output, 0.1)
        self.assertFalse(got)
        self.assertLess(time.monotonic() - start, 10.0)
        self.assert_failure(stage.REASON_TIMEOUT, None)
        self.assertLess((self.output / "source-failure.json").stat().st_size,
                        1024)

    def test_child_exit_failure_becomes_durable_negative_receipt(self):
        self.assertFalse(stage.run_bounded(self.worker("raise SystemExit(7)"),
                                           self.output, 2.0))
        self.assert_failure(stage.REASON_CHILD, 7)

    def test_preserve_original_first_party_error_receipt_unchanged(self):
        program = ("from pathlib import Path; import sys;"
                   "p=Path(sys.argv[1]);p.mkdir();"
                   "(p/'source-failure.json').write_text('original-first-party');"
                   "raise SystemExit(4)")
        self.assertFalse(stage.run_bounded(self.worker(program),
                                           self.output, 2.0))
        self.assertEqual((self.output / "source-failure.json").read_text(),
                         "original-first-party")

    def test_missing_success_receipt_fails_closed(self):
        program = ("from pathlib import Path; import sys;"
                   "Path(sys.argv[1]).mkdir();")
        self.assertFalse(stage.run_bounded(self.worker(program),
                                           self.output, 2.0))
        self.assert_failure(stage.REASON_MISSING, 0)

    def test_worker_success_keeps_source_receipt_without_fake_data(self):
        program = ("from pathlib import Path; import sys;"
                   "p=Path(sys.argv[1]);p.mkdir();"
                   "(p/'source-receipt.json').write_text('{\\\"source\\\":\\\"unit-only\\\"}');")
        self.assertTrue(stage.run_bounded(self.worker(program),
                                          self.output, 2.0))
        self.assertTrue((self.output / "source-receipt.json").exists())
        self.assertFalse((self.output / "source-failure.json").exists())

    def test_existing_output_rejects_without_overwrite(self):
        self.output.mkdir()
        original = self.output / "keep.txt"
        original.write_text("keep")
        with self.assertRaises(ValueError):
            stage.run_bounded(self.worker("raise SystemExit(0)"),
                              self.output, 2.0)
        self.assertEqual(original.read_text(), "keep")
        self.assertFalse((self.output / "source-failure.json").exists())

    def test_zero_and_unbounded_deadlines_reject(self):
        for bad in (0.0, -1.0, 2401.0):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    stage.run_bounded(self.worker("raise SystemExit(0)"),
                                      self.output, bad)
        self.assertFalse(self.output.exists())

    def test_no_overwrite_of_prior_failure_marker(self):
        self.output.mkdir()
        p = self.output / "source-failure.json"
        p.write_text("prior-bytes")
        self.assertTrue(stage.preserve_failure(
            self.output, reason=stage.REASON_TIMEOUT,
            deadline=1800, elapsed=1800, exit_code=None))
        self.assertEqual(p.read_text(), "prior-bytes")


if __name__ == "__main__":
    unittest.main(verbosity=2)
