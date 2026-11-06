#!/usr/bin/env python3
"""Resealed-tamper negatives on actual preparation/results, no model rerun.

With --result omitted, only the prepared source/input contracts and a clearly
simulated timeout are tested. With --result present, real retained model records
are copied into disposable directories for result-integrity mutations.
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

import mandarin_downstream as runner

SOURCE_ROOT = PREPARED = RESULT = None


def reseal_prepared(root):
    meta = runner.load_json(root / "preparation.json")
    manifest = runner.load_json(root / "manifest.json")
    meta["manifest_digest"] = runner.metrics.manifest_digest(manifest)
    inventory = runner.source.file_inventory(root)
    inventory.pop("preparation.json")
    meta["prepared_files"] = inventory
    runner.source.write_json(root / "preparation.json", meta)


def reseal_result(root):
    inventory = runner.source.file_inventory(root)
    inventory.pop("artifact-manifest.json", None)
    runner.source.write_json(root / "artifact-manifest.json", inventory)


class PreparedIntegrity(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="mandarin-prepare-negative-")
        self.prepared = Path(self.tmp.name) / "prepared"
        shutil.copytree(PREPARED, self.prepared)

    def tearDown(self):
        self.tmp.cleanup()

    def reject(self):
        with self.assertRaises((ValueError, subprocess.SubprocessError)):
            runner.verify_prepared(SOURCE_ROOT, self.prepared)

    def test_valid_actual_preparation(self):
        _, _, manifest = runner.verify_prepared(SOURCE_ROOT, self.prepared)
        self.assertEqual(len(manifest["cases"]), 6)

    def test_resealed_changed_raw_pcm(self):
        p = self.prepared / "clean_mono.pcm"
        b = bytearray(p.read_bytes()); b[0] ^= 1; p.write_bytes(b)
        meta = runner.load_json(self.prepared / "preparation.json")
        meta["views"]["raw"]["sha256"] = runner.source.digest(p)
        runner.source.write_json(self.prepared / "preparation.json", meta)
        manifest = runner.load_json(self.prepared / "manifest.json")
        manifest["cases"][0]["pcm_sha256"] = runner.source.digest(p)
        runner.source.write_json(self.prepared / "manifest.json", manifest)
        reseal_prepared(self.prepared)
        self.reject()

    def test_resealed_changed_capture_and_render(self):
        for name in ("clean_capture.pcm", "duplex_capture.pcm", "duplex_render.pcm"):
            with self.subTest(name=name):
                p = self.prepared / name
                original = p.read_bytes()
                b = bytearray(original); b[0] ^= 1; p.write_bytes(b)
                reseal_prepared(self.prepared); self.reject()
                p.write_bytes(original); reseal_prepared(self.prepared)

    def test_resealed_changed_reference_text(self):
        manifest = runner.load_json(self.prepared / "manifest.json")
        manifest["cases"][0]["reference_text"] = "错误转写"
        runner.source.write_json(self.prepared / "manifest.json", manifest)
        reseal_prepared(self.prepared); self.reject()

    def test_resealed_invented_kws_labels(self):
        manifest = runner.load_json(self.prepared / "manifest.json")
        manifest["cases"][0]["kws_annotation"] = {"positive_events": [], "negative_intervals": [[0, 100]], "max_latency_samples": 0}
        runner.source.write_json(self.prepared / "manifest.json", manifest)
        reseal_prepared(self.prepared); self.reject()

    def test_resealed_missing_source_binding(self):
        meta = runner.load_json(self.prepared / "preparation.json")
        meta["source_files"].pop("validation/tools/downstream_metrics.py")
        runner.source.write_json(self.prepared / "preparation.json", meta)
        reseal_prepared(self.prepared); self.reject()

    def test_resealed_wrong_source_revision(self):
        meta = runner.load_json(self.prepared / "preparation.json")
        meta["source_revision"] = "2d93c9ddf74355c7e5ac0bc18c9a6fe3ae53cbd3"
        runner.source.write_json(self.prepared / "preparation.json", meta)
        reseal_prepared(self.prepared); self.reject()

    def test_resealed_extra_and_missing_file(self):
        p = self.prepared / "unexpected.json"
        p.write_text("{}\n"); reseal_prepared(self.prepared); self.reject()
        p.unlink(); reseal_prepared(self.prepared)
        p = self.prepared / "processed/call/stdout.txt"
        p.unlink(); reseal_prepared(self.prepared); self.reject()

    def test_model_environment_does_not_inherit_tokens(self):
        with mock.patch.dict(os.environ, {"GITHUB_TOKEN": "fixture-only", "GH_TOKEN": "fixture-only",
                                         "ACTIONS_RUNTIME_TOKEN": "fixture-only", "PYTHONPATH": "/fixture"}):
            environment = runner.model_environment()
        for key in ("GITHUB_TOKEN", "GH_TOKEN", "ACTIONS_RUNTIME_TOKEN", "PYTHONPATH"):
            self.assertNotIn(key, environment)

    def test_simulated_timeout_preserves_partial_output_and_failure(self):
        output = Path(self.tmp.name) / "timeout-test-output"
        failure = subprocess.TimeoutExpired(["explicit-unit-test-fixture"], 0.1,
                                            output=b"explicit simulated timeout stderr\n")
        with mock.patch.object(runner, "model_child", side_effect=failure) as child, self.assertRaises(subprocess.TimeoutExpired):
            runner.run(SOURCE_ROOT, self.prepared, output)
        self.assertLessEqual(child.call_args.args[1], runner.BUDGET - runner.SEAL_RESERVE)
        self.assertEqual((output / "raw.log").read_bytes(), failure.stdout)
        report = runner.load_json(output / "report.json")
        self.assertEqual(report["status"], "FAIL")
        self.assertEqual(report["exit_code"], 1)
        self.assertEqual(report["cases"][0]["status"], "TIMEOUT")
        self.assertEqual(report["seal_reserve_seconds"], 3.0)

    def test_simulated_final_sealing_budget_exhaustion_is_failure(self):
        output = Path(self.tmp.name) / "sealing-test-output"
        output.mkdir()
        report = {"status": "fixture-only", "exit_code": 0}
        with mock.patch.object(runner.time, "monotonic", side_effect=[299.0, 300.1]), self.assertRaises(TimeoutError):
            runner.seal_report(output, report, 0.0)
        actual = runner.load_json(output / "report.json")
        self.assertEqual(actual["status"], "FAIL")
        self.assertTrue(actual["budget_exceeded"])
        inventory = runner.source.file_inventory(output)
        inventory.pop("artifact-manifest.json")
        self.assertEqual(inventory, runner.load_json(output / "artifact-manifest.json"))


class ResultIntegrity(unittest.TestCase):
    def setUp(self):
        if RESULT is None:
            self.skipTest("real model result not supplied; no fabricated inference evidence")
        self.tmp = tempfile.TemporaryDirectory(prefix="mandarin-result-negative-")
        self.result = Path(self.tmp.name) / "result"
        shutil.copytree(RESULT, self.result)

    def tearDown(self):
        if hasattr(self, "tmp"):
            self.tmp.cleanup()

    def reject(self):
        with self.assertRaises(ValueError):
            runner.verify(SOURCE_ROOT, PREPARED, self.result)

    def test_valid_actual_result(self):
        self.assertEqual(runner.verify(SOURCE_ROOT, PREPARED, self.result)["cases"], 6)

    def test_resealed_actual_case_identity(self):
        p = self.result / "raw.json"
        original = runner.load_json(p)
        for field, bad in (("case_id", "assistant"), ("pcm_sha256", "0" * 64),
                           ("status", "FAIL"), ("exit_code", True)):
            with self.subTest(field=field):
                altered = {**original, field: bad}
                runner.source.write_json(p, altered); reseal_result(self.result); self.reject()
        runner.source.write_json(p, original)

    def test_resealed_actual_native_library(self):
        p = self.result / "raw.json"
        actual = runner.load_json(p)
        actual["loaded_native_files"]["runtime/vosk/libvosk.so"]["sha256"] = "0" * 64
        runner.source.write_json(p, actual); reseal_result(self.result); self.reject()

    def test_resealed_extra_and_missing_result_file(self):
        p = self.result / "unexpected.json"
        p.write_text("{}\n"); reseal_result(self.result); self.reject()
        p.unlink(); reseal_result(self.result)
        (self.result / "raw.log").unlink(); reseal_result(self.result); self.reject()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", required=True, type=Path)
    parser.add_argument("--prepared", required=True, type=Path)
    parser.add_argument("--result", type=Path)
    args, remaining = parser.parse_known_args()
    SOURCE_ROOT, PREPARED = args.source_root.resolve(), args.prepared.resolve()
    RESULT = args.result.resolve() if args.result else None
    unittest.main(argv=[sys.argv[0]] + remaining)
