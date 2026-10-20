#!/usr/bin/env python3
"""Offline transport/failure tests; test doubles never admit real speech bytes."""
from __future__ import annotations

import json
import os
import select
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

import speech_pinned_snapshot as recovery

COMMIT = subprocess.check_output(
    ["git", "-c", "safe.directory=" + str(recovery.ROOT), "rev-parse", "HEAD"],
    cwd=recovery.ROOT, text=True).strip()


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

    def fake_official(self, output, transfer, commit, *, cache_failure):
        # Control-flow double only. Every such test also patches source_check;
        # these files are not original data and cannot pass the real verifier.
        self.assertEqual(commit, COMMIT)
        self.assertEqual(cache_failure, self.failure)
        self.assertNotIn("GH_TOKEN", os.environ)
        self.assertNotIn("GITHUB_TOKEN", os.environ)
        output.mkdir()
        (output / "source-receipt.json").write_text("{}\n")
        record = {"source_commit": COMMIT, "decision": recovery.DECISION,
                  "acquisition_path": "official-original-archive",
                  "cache_failure_receipt_sha256":
                      recovery.sha256_file(self.failure)}
        self.transfer.write_text(json.dumps(record))
        return True

    def acquire(self):
        return recovery.acquire_source_worker(self.archive, self.output,
                                       self.transfer, self.failure, COMMIT)

    def test_cache_hit_keeps_original_restore_and_does_not_call_official(self):
        expected = {"acquisition_path": "protected-artifact-cache"}
        with mock.patch.object(recovery, "cache_api",
                               side_effect=[self.run_metadata(),
                                            self.artifact_metadata(), None]) as api, \
             mock.patch.object(recovery, "restore", return_value=expected) as restore, \
             mock.patch.object(recovery, "reacquire_official") as worker:
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
             mock.patch.object(recovery, "reacquire_official",
                               side_effect=self.fake_official), \
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
             mock.patch.object(recovery, "reacquire_official",
                               side_effect=self.fake_official), \
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
             mock.patch.object(recovery, "reacquire_official",
                               side_effect=self.fake_official) as worker, \
             mock.patch.object(recovery, "source_check"):
            self.acquire()
            worker.assert_called_once()
            self.assertEqual(os.environ["SOURCE_TEST_SENTINEL"], "preserved")
            self.assertEqual(os.environ["GH_TOKEN"], "offline-test-only")

    def test_successful_worker_exit_without_admitted_source_is_rejected(self):
        with mock.patch.object(recovery, "restore_cache",
                 side_effect=recovery.CacheFailure("PINNED_CACHE_RUN_UNAVAILABLE")), \
             mock.patch.object(recovery, "reacquire_official", return_value={}):
            with self.assertRaises((OSError, ValueError)):
                self.acquire()
        self.assertTrue(self.failure.is_file())
        self.assertFalse(self.transfer.exists())

    def fake_completed_cache_stage(self, command, output, deadline, **kwargs):
        self.assertIn("--acquire-worker", command)
        self.assertNotIn("--acquire", command)
        output.mkdir()
        (output / "source-receipt.json").write_text("{}\n")
        self.transfer.write_text(json.dumps({
            "source_commit": COMMIT, "decision": recovery.DECISION,
            "acquisition_path": "protected-artifact-cache",
            "original_source_artifact_zip_sha256": recovery.ORIGIN_ZIP_SHA256,
        }))
        return True

    def test_supervisor_deducts_elapsed_before_one_whole_stage(self):
        with mock.patch.object(recovery.time, "monotonic",
                               side_effect=[100.0, 700.0, 701.0]), \
             mock.patch.object(recovery.stage_budget, "run_bounded",
                               side_effect=self.fake_completed_cache_stage) as worker:
            result = recovery.acquire_source(self.archive, self.output,
                                             self.transfer, self.failure, COMMIT)
        self.assertEqual(worker.call_args.args[2], 1200.0)
        self.assertEqual(result["acquisition_path"], "protected-artifact-cache")

    def test_late_successful_cache_completion_becomes_negative_receipt(self):
        with mock.patch.object(recovery.time, "monotonic",
                               side_effect=[100.0, 100.0, 1900.1]), \
             mock.patch.object(recovery.stage_budget, "run_bounded",
                               side_effect=self.fake_completed_cache_stage):
            with self.assertRaisesRegex(recovery.AdmissionError, "WALL_DEADLINE"):
                recovery.acquire_source(self.archive, self.output,
                                        self.transfer, self.failure, COMMIT)
        receipt = json.loads((self.output / "source-failure.json").read_text())
        self.assertEqual(receipt["reason_code"], "ORIGINAL_SOURCE_STAGE_REJECTED")
        self.assertIn("WALL_DEADLINE", receipt["reason_detail"])
        self.assertFalse(receipt["acoustic_validation_qualified"])

    def test_real_delayed_cache_hit_worker_is_terminated_by_total_budget(self):
        # Wait for explicit IPC readiness before exercising the real supervisor.
        # Import/startup speed is outside this offline timeout experiment.
        child = self.root / "delayed-cache-worker.py"
        entered = self.root / "cache-entered"
        completed = self.root / "cache-completed"
        child.write_text(
            "import sys\nfrom pathlib import Path\n"
            "sys.path.insert(0," + repr(str(Path(recovery.__file__).parent)) + ")\n"
            "import speech_pinned_snapshot as r\n"
            "def cache(*args):\n"
            "    Path(" + repr(str(entered)) + ").write_text('entered')\n"
            "    print('CACHE_HIT_READY',flush=True)\n"
            "    sys.stdin.buffer.read(1)\n"
            "    Path(" + repr(str(completed)) + ").write_text('completed')\n"
            "    return {'acquisition_path':'protected-artifact-cache'}\n"
            "r.restore_cache=cache\n"
            "r.acquire_source_worker(" + ",".join(
                "Path(" + repr(str(p)) + ")" for p in
                (self.archive, self.output, self.transfer, self.failure)) +
            "," + repr(COMMIT) + ")\n")
        bounded = recovery.stage_budget.run_bounded
        def real_delayed(command, output, deadline, **kwargs):
            self.assertIn("--acquire-worker", command)
            self.assertLessEqual(deadline, recovery.stage_budget.DEADLINE_SECONDS)
            proc = subprocess.Popen(
                [sys.executable, str(child)], stdin=subprocess.PIPE,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                start_new_session=True, cwd=recovery.ROOT)
            try:
                ready, _, _ = select.select([proc.stdout], [], [], 30)
                self.assertTrue(ready, "test worker did not reach IPC checkpoint")
                self.assertEqual(proc.stdout.readline(), b"CACHE_HIT_READY\n")
                self.assertTrue(entered.exists())
                # Popen substitution only schedules this already-ready real
                # process. Actual wait, killpg, reap and failure writing execute.
                with mock.patch.object(recovery.stage_budget.subprocess, "Popen",
                                       return_value=proc):
                    return bounded(command, output, 0.05, **kwargs)
            finally:
                if proc.poll() is None:
                    recovery.stage_budget._terminate_process_group(proc)
                for stream in (proc.stdin, proc.stdout, proc.stderr):
                    stream.close()
        with mock.patch.object(recovery.stage_budget, "run_bounded",
                               side_effect=real_delayed):
            with self.assertRaisesRegex(recovery.AdmissionError, "WORKER_FAILED"):
                recovery.acquire_source(self.archive, self.output,
                                        self.transfer, self.failure, COMMIT)
        self.assertFalse(completed.exists())
        receipt = json.loads((self.output / "source-failure.json").read_text())
        self.assertEqual(receipt["reason_code"], recovery.stage_budget.REASON_TIMEOUT)
        self.assertFalse(receipt["acoustic_validation_qualified"])

    def test_exhausted_total_budget_never_starts_another_worker(self):
        with mock.patch.object(recovery.time, "monotonic", side_effect=[100.0, 1900.0]), \
             mock.patch.object(recovery, "restore_cache",
                 side_effect=recovery.CacheFailure("PINNED_CACHE_DOWNLOAD_TIMEOUT")), \
             mock.patch.object(recovery, "reacquire_official") as worker:
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

    def test_real_cli_official_replay_requires_explicit_local_archive(self):
        result = subprocess.run(
            [sys.executable, str(Path(recovery.__file__).resolve()),
             "--reacquire-official", "--output", str(self.output),
             "--transfer", str(self.transfer), "--execution-source", COMMIT],
            capture_output=True, text=True, check=False, timeout=30)
        self.assertNotEqual(result.returncode, 0)
        receipt = json.loads((self.output / "source-failure.json").read_text())
        self.assertIn("EXPLICIT_LOCAL_ORIGINAL_ARCHIVE_REQUIRED", receipt["reason_detail"])
        self.assertFalse(self.transfer.exists())

    def test_callable_official_download_strips_tokens_and_restores_on_failure(self):
        def probe(*args, **kwargs):
            self.assertNotIn("GH_TOKEN", os.environ)
            self.assertNotIn("GITHUB_TOKEN", os.environ)
            self.assertEqual(os.environ["SOURCE_TEST_SENTINEL"], "preserved")
            raise RuntimeError("OFFLINE_DOWNLOAD_ENTRY_ONLY")
        with mock.patch.dict(os.environ, {"GH_TOKEN": "offline-test-only",
                  "GITHUB_TOKEN": "offline-test-only", "SOURCE_TEST_SENTINEL": "preserved"}), \
             mock.patch.object(recovery.speech_source, "download", side_effect=probe) as download:
            with self.assertRaisesRegex(RuntimeError, "OFFLINE_DOWNLOAD_ENTRY_ONLY"):
                recovery.reacquire_official(self.output, self.transfer, COMMIT)
            download.assert_called_once()
            self.assertEqual(os.environ["GH_TOKEN"], "offline-test-only")
            self.assertEqual(os.environ["GITHUB_TOKEN"], "offline-test-only")
        self.assertFalse(self.output.exists())

    def test_callable_local_replay_decoder_strips_tokens(self):
        with self.archive.open("wb") as stream:
            stream.truncate(337926286)
        def probe(*args, **kwargs):
            self.assertNotIn("GH_TOKEN", os.environ)
            self.assertNotIn("GITHUB_TOKEN", os.environ)
            raise RuntimeError("OFFLINE_DECODER_ENTRY_ONLY")
        # The hash double reaches only the decoder environment probe; no source
        # can be published or admitted by this deliberately interrupted test.
        with mock.patch.dict(os.environ, {"GH_TOKEN": "offline-test-only",
                                         "GITHUB_TOKEN": "offline-test-only"}), \
             mock.patch.object(recovery, "sha256_file", return_value=recovery.ORIGIN_ARCHIVE_SHA256), \
             mock.patch.object(recovery.speech_source, "acquire", side_effect=probe) as decode, \
             mock.patch.object(recovery.speech_source, "download") as download:
            with self.assertRaisesRegex(RuntimeError, "OFFLINE_DECODER_ENTRY_ONLY"):
                recovery.reacquire_official(self.output, self.transfer,
                                            COMMIT, archive=self.archive)
            decode.assert_called_once()
            download.assert_not_called()
            self.assertEqual(os.environ["GH_TOKEN"], "offline-test-only")
            self.assertEqual(os.environ["GITHUB_TOKEN"], "offline-test-only")
        self.assertFalse(self.output.exists())

    def fake_completed_local_replay(self, command, output, deadline, **kwargs):
        # Control-flow receipt double only; not evidence of admitted bytes.
        self.assertIn("--replay-official-worker", command)
        self.assertIn("--original-archive", command)
        self.assertNotIn("--reacquire-official", command)
        self.assertNotIn("--acquire-worker", command)
        self.assertNotIn("GH_TOKEN", kwargs["env"])
        self.assertNotIn("GITHUB_TOKEN", kwargs["env"])
        output.mkdir()
        (output / "source-receipt.json").write_text("{}\n")
        self.transfer.write_text(json.dumps({
            "source_commit": COMMIT, "decision": recovery.DECISION,
            "acquisition_path": "official-original-archive",
            "original_full_archive_redownloaded": False,
            "original_full_archive_rehashed_this_run": True,
            "cache_failure_receipt_sha256": None,
            "verified_selected_source_member_count": 46,
        }))
        return True

    def test_direct_cli_uses_one_supervised_worker_with_clean_environment(self):
        self.archive.write_bytes(b"offline-control-flow-only")
        command = [str(Path(recovery.__file__)), "--reacquire-official",
                   "--original-archive", str(self.archive),
                   "--output", str(self.output), "--transfer", str(self.transfer),
                   "--execution-source", COMMIT]
        with mock.patch.object(sys, "argv", command), \
             mock.patch.dict(os.environ, {"GH_TOKEN": "offline-test-only",
                                         "GITHUB_TOKEN": "offline-test-only"}), \
             mock.patch.object(recovery.stage_budget, "run_bounded",
                               side_effect=self.fake_completed_local_replay) as worker, \
             mock.patch.object(recovery, "reacquire_official") as inline:
            recovery.main()
            self.assertEqual(worker.call_count, 1)
            self.assertLessEqual(worker.call_args.args[2], 1800)
            inline.assert_not_called()
            self.assertEqual(os.environ["GH_TOKEN"], "offline-test-only")

    def test_local_replay_supervisor_deducts_elapsed_and_rejects_late_success(self):
        self.archive.write_bytes(b"offline-control-flow-only")
        with mock.patch.object(recovery.time, "monotonic",
                               side_effect=[100.0, 700.0, 1900.1]), \
             mock.patch.object(recovery.stage_budget, "run_bounded",
                               side_effect=self.fake_completed_local_replay) as worker:
            with self.assertRaisesRegex(recovery.AdmissionError, "WALL_DEADLINE"):
                recovery.replay_official_archive(self.archive, self.output,
                                                  self.transfer, COMMIT)
        self.assertEqual(worker.call_args.args[2], 1200.0)
        receipt = json.loads((self.output / "source-failure.json").read_text())
        self.assertIn("WALL_DEADLINE", receipt["reason_detail"])
        self.assertFalse(receipt["acoustic_validation_qualified"])

    def test_local_archive_symlink_is_rejected_before_resolving_worker_argument(self):
        original = self.root / "original.tar.gz"
        original.write_bytes(b"offline-control-flow-only")
        self.archive.symlink_to(original)
        with mock.patch.object(recovery.stage_budget, "run_bounded") as worker:
            with self.assertRaisesRegex(recovery.AdmissionError, "SIZE_OR_FILE_REJECTED"):
                recovery.replay_official_archive(self.archive, self.output,
                                                  self.transfer, COMMIT)
            worker.assert_not_called()

    def test_local_replay_readback_stays_inside_worker(self):
        with mock.patch.object(recovery, "reacquire_official", return_value={}) as source, \
             mock.patch.object(recovery, "source_check") as check, \
             mock.patch.object(recovery.stage_budget, "run_bounded") as supervisor:
            recovery.replay_official_worker(self.archive, self.output, self.transfer, COMMIT)
            source.assert_called_once_with(self.output, self.transfer, COMMIT,
                                           archive=self.archive, cache_failure=None)
            check.assert_called_once_with(self.output)
            supervisor.assert_not_called()

    def test_real_local_replay_decoder_group_is_terminated_by_total_budget(self):
        with self.archive.open("wb") as stream:
            stream.truncate(337926286)
        child = self.root / "delayed-official-worker.py"
        entered = self.root / "decode-entered"
        completed = self.root / "decode-completed"
        decoder = ("import os,sys\nfrom pathlib import Path\n"
                   "assert 'GH_TOKEN' not in os.environ and 'GITHUB_TOKEN' not in os.environ\n"
                   "Path(" + repr(str(entered)) + ").write_text('entered')\n"
                   "print('OFFICIAL_DECODE_READY',flush=True)\n"
                   "sys.stdin.buffer.read(1)\n"
                   "Path(" + repr(str(completed)) + ").write_text('completed')\n")
        child.write_text(
            "import sys,subprocess\nfrom pathlib import Path\n"
            "sys.path.insert(0," + repr(str(Path(recovery.__file__).parent)) + ")\n"
            "import speech_pinned_snapshot as r\n"
            "r.sha256_file=lambda path:r.ORIGIN_ARCHIVE_SHA256\n"
            "r.speech_source.acquire=lambda *args,**kwargs:subprocess.run("
            "[sys.executable,'-c'," + repr(decoder) + "],check=True)\n"
            "r.replay_official_worker(" + ",".join(
                "Path(" + repr(str(p)) + ")" for p in
                (self.archive, self.output, self.transfer)) + "," + repr(COMMIT) + ")\n")
        bounded = recovery.stage_budget.run_bounded
        def real_delayed(command, output, deadline, **kwargs):
            self.assertIn("--replay-official-worker", command)
            self.assertLessEqual(deadline, 1800)
            proc = subprocess.Popen([sys.executable, str(child)],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                start_new_session=True, cwd=recovery.ROOT, env=kwargs["env"])
            try:
                ready, _, _ = select.select([proc.stdout], [], [], 30)
                self.assertTrue(ready, "test decoder did not reach IPC checkpoint")
                self.assertEqual(proc.stdout.readline(), b"OFFICIAL_DECODE_READY\n")
                self.assertTrue(entered.exists())
                with mock.patch.object(recovery.stage_budget.subprocess, "Popen",
                                       return_value=proc):
                    return bounded(command, output, 0.05, **kwargs)
            finally:
                if proc.poll() is None:
                    recovery.stage_budget._terminate_process_group(proc)
                for stream in (proc.stdin, proc.stdout, proc.stderr):
                    stream.close()
        with mock.patch.dict(os.environ, {"GH_TOKEN": "offline-test-only",
                                         "GITHUB_TOKEN": "offline-test-only"}), \
             mock.patch.object(recovery.stage_budget, "run_bounded", side_effect=real_delayed):
            with self.assertRaisesRegex(recovery.AdmissionError, "WORKER_FAILED"):
                recovery.replay_official_archive(self.archive, self.output,
                                                  self.transfer, COMMIT)
        self.assertFalse(completed.exists())
        receipt = json.loads((self.output / "source-failure.json").read_text())
        self.assertEqual(receipt["reason_code"], recovery.stage_budget.REASON_TIMEOUT)
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
