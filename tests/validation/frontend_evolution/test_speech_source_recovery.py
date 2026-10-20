#!/usr/bin/env python3
"""Offline transport/failure tests; test doubles never admit real speech bytes."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

import speech_pinned_snapshot as recovery

COMMIT = subprocess.check_output(
    ["git", "rev-parse", "HEAD"], cwd=recovery.ROOT, text=True).strip()


class SourceRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.output = self.root / "source"
        self.transfer = self.root / "source-transfer.json"
        self.archive = self.root / "cache.zip"
        self.failure = self.root / "source-cache-failure.json"

    def run_metadata(self):
        return {"id": recovery.ORIGIN_VERIFY_RUN,
                "head_sha": recovery.ORIGIN_MAIN, "event": "push",
                "conclusion": "success"}

    def artifact_metadata(self):
        return {"id": recovery.ORIGIN_ARTIFACT,
                "name": recovery.ORIGIN_ARTIFACT_NAME,
                "size_in_bytes": recovery.ORIGIN_ZIP_BYTES,
                "digest": "sha256:" + recovery.ORIGIN_ZIP_SHA256,
                "expired": False,
                "workflow_run": {"id": recovery.ORIGIN_VERIFY_RUN,
                                 "head_sha": recovery.ORIGIN_MAIN}}

    def fake_worker(self, command, output, deadline, **kwargs):
        # Control-flow double only. Every such test also patches source_check;
        # these files are not original data and cannot pass the real verifier.
        self.assertIn("--reacquire-official", command)
        self.assertNotIn("--original-archive", command)
        self.assertEqual(command[-1], COMMIT)
        self.assertGreater(deadline, 0)
        self.assertLessEqual(deadline, recovery.stage_budget.DEADLINE_SECONDS)
        self.assertNotIn("GH_TOKEN", kwargs["env"])
        self.assertNotIn("GITHUB_TOKEN", kwargs["env"])
        output.mkdir()
        (output / "source-receipt.json").write_text("{}\n")
        record = {"source_commit": COMMIT, "decision": recovery.DECISION,
                  "acquisition_path": "official-original-archive",
                  "cache_failure_receipt_sha256":
                      recovery.sha256_file(self.failure)}
        self.transfer.write_text(json.dumps(record))
        return True

    def acquire(self):
        return recovery.acquire_source(self.archive, self.output,
                                       self.transfer, self.failure, COMMIT)

    def test_cache_hit_keeps_original_restore_and_does_not_call_official(self):
        expected = {"acquisition_path": "protected-artifact-cache"}
        with mock.patch.object(recovery, "cache_api",
                               side_effect=[self.run_metadata(),
                                            self.artifact_metadata(), None]) as api, \
             mock.patch.object(recovery, "restore", return_value=expected) as restore, \
             mock.patch.object(recovery.stage_budget, "run_bounded") as worker:
            self.assertEqual(self.acquire(), expected)
            restore.assert_called_once_with(self.archive, self.output,
                                             self.transfer, COMMIT)
            worker.assert_not_called()
            self.assertEqual(api.call_count, 3)
        self.assertFalse(self.failure.exists())
        self.assertFalse(self.archive.exists())

    def test_expired_cache_is_preserved_then_same_original_is_requested(self):
        artifact = self.artifact_metadata()
        artifact["expired"] = True
        with mock.patch.object(recovery, "cache_api",
                               side_effect=[self.run_metadata(), artifact]), \
             mock.patch.object(recovery.stage_budget, "run_bounded",
                               side_effect=self.fake_worker), \
             mock.patch.object(recovery, "source_check") as check:
            result = self.acquire()
            check.assert_called_once_with(self.output)
        receipt = json.loads(self.failure.read_text())
        self.assertEqual(receipt["reason_code"], "PINNED_CACHE_ARTIFACT_EXPIRED")
        self.assertEqual(receipt["next_allowed_source"], recovery.speech_source.URL)
        self.assertEqual(receipt["next_allowed_archive_sha256"],
                         recovery.ORIGIN_ARCHIVE_SHA256)
        self.assertFalse(receipt["original_source_reacquisition_completed"])
        self.assertEqual(result["cache_failure_receipt_sha256"],
                         recovery.sha256_file(self.failure))

    def test_unavailable_cache_is_preserved_on_successful_reacquisition(self):
        with mock.patch.object(recovery, "cache_api",
                 side_effect=recovery.CacheFailure("PINNED_CACHE_RUN_UNAVAILABLE")), \
             mock.patch.object(recovery.stage_budget, "run_bounded",
                               side_effect=self.fake_worker), \
             mock.patch.object(recovery, "source_check"):
            result = self.acquire()
        self.assertEqual(json.loads(self.failure.read_text())["reason_code"],
                         "PINNED_CACHE_RUN_UNAVAILABLE")
        self.assertEqual(result["acquisition_path"], "official-original-archive")

    def test_wrong_run_identity_rejected_before_download(self):
        run = self.run_metadata()
        run["head_sha"] = "0" * 40
        with mock.patch.object(recovery, "cache_api", return_value=run) as api, \
             mock.patch.object(recovery, "restore") as restore:
            with self.assertRaisesRegex(recovery.CacheFailure, "RUN_IDENTITY_REJECTED"):
                recovery.restore_cache(self.archive, self.output,
                                       self.transfer, COMMIT)
            self.assertEqual(api.call_count, 1)
            restore.assert_not_called()
        self.assertFalse(self.archive.exists())

    def test_wrong_artifact_identity_rejected_before_download(self):
        for field, value in (("id", 1), ("digest", "sha256:" + "0"*64),
                             ("size_in_bytes", 1), ("expired", None),
                             ("workflow_run", {"id": recovery.ORIGIN_VERIFY_RUN,
                                               "head_sha": "0"*40})):
            with self.subTest(field=field):
                artifact = self.artifact_metadata()
                artifact[field] = value
                with mock.patch.object(recovery, "cache_api",
                         side_effect=[self.run_metadata(), artifact]) as api:
                    with self.assertRaisesRegex(recovery.CacheFailure,
                                                "ARTIFACT_IDENTITY_REJECTED"):
                        recovery.restore_cache(self.archive, self.output,
                                               self.transfer, COMMIT)
                    self.assertEqual(api.call_count, 2)
                self.assertFalse(self.archive.exists())

    def test_real_wrong_zip_hash_rejected_before_source_verification(self):
        with self.archive.open("wb") as stream:
            stream.truncate(recovery.ORIGIN_ZIP_BYTES)
        with mock.patch.object(recovery, "source_check") as check:
            with self.assertRaisesRegex(recovery.AdmissionError, "ZIP_SHA256_CHANGED"):
                recovery.restore(self.archive, self.output, self.transfer, COMMIT)
            check.assert_not_called()
        self.assertFalse(self.output.exists())

    def test_real_wrong_original_hash_rejected_before_decode(self):
        with self.archive.open("wb") as stream:
            stream.truncate(337926286)
        with mock.patch.object(recovery.speech_source, "acquire") as decode:
            with self.assertRaisesRegex(recovery.AdmissionError,
                                        "ORIGINAL_ARCHIVE_SHA256_REJECTED"):
                recovery.reacquire_official(self.output, self.transfer,
                                            COMMIT, archive=self.archive)
            decode.assert_not_called()
        self.assertFalse(self.output.exists())

    def test_wrong_original_size_rejected_before_decode(self):
        self.archive.write_bytes(b"not-source-data")
        with mock.patch.object(recovery.speech_source, "acquire") as decode:
            with self.assertRaisesRegex(recovery.AdmissionError, "SIZE_OR_FILE_REJECTED"):
                recovery.reacquire_official(self.output, self.transfer,
                                            COMMIT, archive=self.archive)
            decode.assert_not_called()

    def test_wrong_commit_rejected_before_transport(self):
        with mock.patch.object(recovery, "restore_cache") as cache:
            with self.assertRaisesRegex(recovery.AdmissionError,
                                        "CHECKED_OUT_SHA_NOT_EXECUTION_SOURCE"):
                recovery.acquire_source(self.archive, self.output, self.transfer,
                                        self.failure, "0" * 40)
            cache.assert_not_called()
        self.assertFalse(self.failure.exists())

    def test_existing_and_symlink_destinations_are_not_overwritten(self):
        self.output.mkdir()
        sentinel = self.output / "sentinel"
        sentinel.write_bytes(b"preserve")
        with self.assertRaisesRegex(recovery.AdmissionError, "NOT_FRESH"):
            self.acquire()
        self.assertEqual(sentinel.read_bytes(), b"preserve")
        sentinel.unlink()
        self.output.rmdir()
        target = self.root / "target"
        target.mkdir()
        self.output.symlink_to(target, target_is_directory=True)
        with self.assertRaisesRegex(recovery.AdmissionError, "NOT_FRESH"):
            self.acquire()
        self.assertEqual(list(target.iterdir()), [])

    def test_overlapping_transport_paths_are_rejected(self):
        with self.assertRaisesRegex(recovery.AdmissionError, "OVERLAPPING"):
            recovery.acquire_source(self.archive, self.output, self.transfer,
                                    self.archive, COMMIT)
        self.assertFalse(self.archive.exists())

    def test_official_worker_has_no_github_auth_environment(self):
        with mock.patch.dict(os.environ,
                             {"GH_TOKEN": "offline-test-only",
                              "GITHUB_TOKEN": "offline-test-only",
                              "SOURCE_TEST_SENTINEL": "preserved"}), \
             mock.patch.object(recovery, "restore_cache",
                 side_effect=recovery.CacheFailure("PINNED_CACHE_RUN_UNAVAILABLE")), \
             mock.patch.object(recovery.stage_budget, "run_bounded",
                               side_effect=self.fake_worker) as worker, \
             mock.patch.object(recovery, "source_check"):
            self.acquire()
            self.assertEqual(worker.call_args.kwargs["env"]["SOURCE_TEST_SENTINEL"],
                             "preserved")

    def test_successful_worker_exit_without_admitted_source_is_rejected(self):
        with mock.patch.object(recovery, "restore_cache",
                 side_effect=recovery.CacheFailure("PINNED_CACHE_RUN_UNAVAILABLE")), \
             mock.patch.object(recovery.stage_budget, "run_bounded", return_value=True):
            with self.assertRaises((OSError, ValueError)):
                self.acquire()
        self.assertTrue(self.failure.is_file())
        self.assertFalse(self.transfer.exists())

    def test_cache_elapsed_is_deducted_from_original_stage_budget(self):
        with mock.patch.object(recovery.time, "monotonic", side_effect=[100.0, 700.0]), \
             mock.patch.object(recovery, "restore_cache",
                 side_effect=recovery.CacheFailure("PINNED_CACHE_DOWNLOAD_TIMEOUT")), \
             mock.patch.object(recovery.stage_budget, "run_bounded",
                               side_effect=self.fake_worker) as worker, \
             mock.patch.object(recovery, "source_check"):
            self.acquire()
        self.assertEqual(worker.call_args.args[2], 1200.0)

    def test_exhausted_total_budget_never_starts_another_worker(self):
        with mock.patch.object(recovery.time, "monotonic", side_effect=[100.0, 1900.0]), \
             mock.patch.object(recovery, "restore_cache",
                 side_effect=recovery.CacheFailure("PINNED_CACHE_DOWNLOAD_TIMEOUT")), \
             mock.patch.object(recovery.stage_budget, "run_bounded") as worker:
            with self.assertRaisesRegex(recovery.AdmissionError, "WALL_DEADLINE"):
                self.acquire()
            worker.assert_not_called()
        self.assertTrue(self.failure.is_file())

    def test_api_failure_receipt_omits_response_body_and_signed_url(self):
        private = b"https://example.invalid/signed?signature=offline-test-only"
        response = subprocess.CompletedProcess(["gh"], 1, stdout=private,
                                                stderr=private)
        with mock.patch.object(recovery.subprocess, "run", return_value=response):
            with self.assertRaises(recovery.CacheFailure) as caught:
                recovery.cache_api("/actions/runs/1",
                                   recovery.time.monotonic()+10, "RUN")
        recovery.preserve_cache_failure(self.failure, caught.exception, COMMIT)
        self.assertNotIn("signature", self.failure.read_text())
        self.assertNotIn("example.invalid", self.failure.read_text())

    def test_partial_output_gets_failure_but_existing_failure_is_preserved(self):
        self.output.mkdir()
        self.assertTrue(recovery.preserve_failure(
            self.output, ValueError("original-failure"), COMMIT))
        marker = self.output / "source-failure.json"
        original = marker.read_bytes()
        self.assertTrue(recovery.preserve_failure(
            self.output, ValueError("later-failure"), COMMIT))
        self.assertEqual(marker.read_bytes(), original)

    def test_real_cli_bad_original_keeps_specific_failure_receipt(self):
        self.archive.write_bytes(b"not-an-official-archive")
        result = subprocess.run(
            [sys.executable, str(Path(recovery.__file__).resolve()),
             "--reacquire-official", "--original-archive", str(self.archive),
             "--output", str(self.output), "--transfer", str(self.transfer),
             "--execution-source", COMMIT],
            capture_output=True, text=True, check=False)
        self.assertNotEqual(result.returncode, 0)
        receipt = json.loads((self.output/"source-failure.json").read_text())
        self.assertEqual(receipt["reason_code"],
                         "OFFICIAL_ORIGINAL_SOURCE_REACQUISITION_REJECTED")
        self.assertIn("SIZE_OR_FILE_REJECTED", receipt["reason_detail"])
        self.assertFalse(receipt["acoustic_validation_qualified"])

    def test_real_cli_existing_output_is_unchanged(self):
        self.output.mkdir()
        sentinel = self.output / "sentinel"
        sentinel.write_bytes(b"preserve")
        result = subprocess.run(
            [sys.executable, str(Path(recovery.__file__).resolve()),
             "--reacquire-official", "--output", str(self.output),
             "--transfer", str(self.transfer), "--execution-source", COMMIT],
            capture_output=True, text=True, check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual({p.name for p in self.output.iterdir()}, {"sentinel"})
        self.assertEqual(sentinel.read_bytes(), b"preserve")


if __name__ == "__main__":
    unittest.main()
