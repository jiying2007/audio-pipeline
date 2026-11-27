#!/usr/bin/env python3
"""Offline recovery controls; tiny fake ZIPs are never original audio evidence."""
import copy
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest import mock
import zipfile

import dualmic_archive_recovery as recovery


class ArchiveRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.archive, self.output = self.root / "retained.zip", self.root / "recovered"
        with zipfile.ZipFile(self.archive, "w") as archive:
            archive.writestr("original-marker.txt", b"synthetic transport control only\n")
        self.lock = copy.deepcopy(recovery.original.frozen_lock())
        self.lock["artifact"].update(zip_bytes=self.archive.stat().st_size,
            sha256=recovery.source.digest(self.archive), members=1)
        self.lock.update(max_members=1,
                         max_uncompressed_bytes=len(b"synthetic transport control only\n"))

    def synthetic_recovery(self, **kwargs):
        # Only the transport is exercised here.  These patched contracts/readback
        # cannot admit test data with the real, fixed production entrypoint.
        with mock.patch.object(recovery, "contract", return_value=self.lock), \
             mock.patch.object(recovery, "read_original", return_value={"test_double": True}), \
             mock.patch.object(recovery.source, "api_json", side_effect=AssertionError("network forbidden")), \
             mock.patch.object(recovery.source, "fetch_zip", side_effect=AssertionError("download forbidden")), \
             mock.patch.object(recovery.original, "metadata", side_effect=AssertionError("live metadata forbidden")):
            return recovery.recover(kwargs.get("archive", self.archive),
                                    kwargs.get("output", self.output))

    def test_current_frozen_contract_and_source_closure(self):
        lock = recovery.contract()
        self.assertEqual(lock["run_id"], 42321833898)
        self.assertEqual(lock["artifact"]["artifact_id"], 13553232106)

    def test_tiny_transport_retains_exact_zip_without_live_metadata_claim(self):
        before = self.archive.read_bytes()
        result = self.synthetic_recovery()
        self.assertEqual(result["status"], recovery.SUCCESS)
        self.assertEqual(self.archive.read_bytes(), before)
        self.assertEqual((self.output / "original.zip").read_bytes(), before)
        self.assertEqual((self.output / "original/original-marker.txt").read_bytes(),
                         b"synthetic transport control only\n")
        self.assertFalse(result["live_actions_metadata_queried"])
        self.assertFalse(result["artifact_expiration_checked"])
        self.assertFalse(result["new_acoustic_experiment"])
        self.assertNotIn("expired", json.loads((self.output / "recovery.json").read_text()))
        self.assertFalse((self.output / "admission.json").exists())
        self.assertFalse((self.output / "acquisition.json").exists())

    def test_real_entrypoint_rejects_tiny_zip_before_creating_output(self):
        with mock.patch.object(recovery, "read_original") as readback:
            with self.assertRaisesRegex(ValueError, "hash/size mismatch"):
                recovery.recover(self.archive, self.output)
            readback.assert_not_called()
        self.assertFalse(self.output.exists())

    def test_changed_zip_hash_or_size_is_rejected_before_output(self):
        for value in (self.archive.read_bytes() + b"x", b"x" * self.archive.stat().st_size):
            self.archive.write_bytes(value)
            with self.assertRaisesRegex(ValueError, "hash/size mismatch"):
                self.synthetic_recovery()
            self.assertFalse(self.output.exists())

    def test_missing_archive_and_existing_output_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "REGULAR_ZIP_REQUIRED"):
            self.synthetic_recovery(archive=self.root / "missing.zip")
        self.output.mkdir()
        sentinel = self.output / "keep"
        sentinel.write_bytes(b"unchanged")
        with self.assertRaisesRegex(ValueError, "NEW_OUTPUT_REQUIRED"):
            self.synthetic_recovery()
        self.assertEqual(sentinel.read_bytes(), b"unchanged")

    def test_archive_output_and_parent_symlinks_are_rejected(self):
        alias = self.root / "alias.zip"
        alias.symlink_to(self.archive)
        with self.assertRaisesRegex(ValueError, "SYMLINK_PATH"):
            self.synthetic_recovery(archive=alias)
        self.output.symlink_to(self.root / "future")
        with self.assertRaisesRegex(ValueError, "SYMLINK_PATH"):
            self.synthetic_recovery()
        self.output.unlink()
        directory_alias = self.root / "alias-dir"
        directory_alias.symlink_to(self.root, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "SYMLINK_PATH"):
            self.synthetic_recovery(output=directory_alias / "new-output")

    def test_frozen_metadata_cannot_be_replaced_by_wrong_run_source_or_missing_fields(self):
        current = recovery.original.ROOT
        lock_path = self.root / recovery.original.LOCK_PATH
        lock_path.parent.mkdir(parents=True)
        original_lock = json.loads((current / recovery.original.LOCK_PATH).read_text())
        variants = []
        for key, value in (("run_id", 1), ("run_attempt", 2),
                           ("source_revision", "0" * 40)):
            changed = copy.deepcopy(original_lock)
            changed[key] = value
            variants.append(changed)
        changed = copy.deepcopy(original_lock)
        del changed["artifact"]["sha256"]
        variants.append(changed)
        changed = copy.deepcopy(original_lock)
        changed["artifact"]["expired"] = False
        variants.append(changed)
        for changed in variants:
            lock_path.write_text(json.dumps(changed))
            with self.subTest(changed=changed), \
                 mock.patch.object(recovery.original, "ROOT", self.root), \
                 self.assertRaisesRegex(ValueError, "D3_FROZEN_CONTRACT_CHANGED"):
                recovery.recover(self.archive, self.output)
        self.assertFalse(self.output.exists())

    def test_existing_live_reader_still_rejects_expired_metadata(self):
        lock = recovery.original.frozen_lock()
        spec = lock["artifact"]
        run = dict(id=lock["run_id"], head_sha=lock["source_revision"],
                   run_attempt=1, status="completed", conclusion="success")
        item = dict(id=spec["artifact_id"], name=spec["name"],
                    size_in_bytes=spec["zip_bytes"], digest="sha256:" + spec["sha256"],
                    expired=True, workflow_run=dict(id=lock["run_id"], head_sha=lock["source_revision"]))
        with self.assertRaisesRegex(ValueError, "D3_ORIGINAL_ARTIFACT_MISMATCH"):
            recovery.original.metadata(run, dict(total_count=1, artifacts=[item]), lock)
        self.assertIs(item["expired"], True)

    def test_wrong_member_count_and_total_bytes_leave_failure_receipt(self):
        for key in ("members", "max_uncompressed_bytes"):
            with self.subTest(key=key):
                output = self.root / ("failure-" + key)
                changed = copy.deepcopy(self.lock)
                if key == "members":
                    changed["artifact"][key] += 1
                else:
                    changed[key] += 1
                with mock.patch.object(recovery, "contract", return_value=changed), \
                     mock.patch.object(recovery, "read_original") as readback:
                    with self.assertRaises(ValueError):
                        recovery.recover(self.archive, output)
                    readback.assert_not_called()
                result = json.loads((output / "recovery.json").read_text())
                self.assertEqual(result["status"], "FAIL")

    def test_readback_failure_keeps_original_and_never_claims_recovery(self):
        before = self.archive.read_bytes()
        with mock.patch.object(recovery, "contract", return_value=self.lock), \
             mock.patch.object(recovery, "read_original",
                               side_effect=ValueError("D3_ORIGINAL_D2_READBACK_DIFFERS")):
            with self.assertRaisesRegex(ValueError, "READBACK_DIFFERS"):
                recovery.recover(self.archive, self.output)
        self.assertEqual(self.archive.read_bytes(), before)
        result = json.loads((self.output / "recovery.json").read_text())
        self.assertEqual(result["status"], "FAIL")
        self.assertNotIn("original_D2_readback_exact", result)

    def test_missing_or_changed_report_is_rejected_before_frozen_analysis(self):
        extracted = self.root / "extracted"
        prior = extracted / "gain-d2"
        prior.mkdir(parents=True)
        with mock.patch.object(recovery.original.d2, "analysis_payload") as analyze:
            with self.assertRaises(OSError):
                recovery.read_original(extracted, self.lock, time.monotonic())
            (prior / "report.json").write_text("{}\n")
            with self.assertRaisesRegex(ValueError, "D3_ORIGINAL_REPORT_IDENTITY"):
                recovery.read_original(extracted, self.lock, time.monotonic())
            analyze.assert_not_called()

    def test_readback_wrong_source_or_matrix_is_not_admitted(self):
        extracted = self.root / "extracted"
        prior = extracted / "gain-d2"
        prior.mkdir(parents=True)
        for key, value in (("source_revision", "0" * 40), ("case_count", 59),
                           ("frames", 35915), ("samples", 5746559)):
            result = dict(source_revision=self.lock["source_revision"],
                          case_count=60, frames=35916, samples=5746560)
            result[key] = value
            recovery.source.dump(prior / "report.json", result)
            recovery.source.dump(prior / "artifact-manifest.json", {
                "files": recovery.original.d2.payload_inventory(prior)})
            lock = copy.deepcopy(self.lock)
            lock.update(report_sha256=recovery.source.digest(prior / "report.json"),
                        manifest_sha256=recovery.source.digest(prior / "artifact-manifest.json"))
            with self.subTest(key=key), \
                 mock.patch.object(recovery.original.d2, "analysis_payload", return_value=result), \
                 self.assertRaisesRegex(ValueError, "D3_ORIGINAL_SOURCE_OR_MATRIX"):
                recovery.read_original(extracted, lock, time.monotonic())

    def test_exhausted_budget_is_rejected_before_output(self):
        self.lock["budget_seconds"] = 0
        with self.assertRaisesRegex(ValueError, "SOURCE_BUDGET_EXCEEDED"):
            self.synthetic_recovery()
        self.assertFalse(self.output.exists())

    def test_late_receipt_write_is_converted_to_failure(self):
        now = [0.0]
        real_dump = recovery.source.dump

        def dump(path, value):
            real_dump(path, value)
            if value.get("status") == recovery.SUCCESS:
                now[0] = self.lock["budget_seconds"] + 1

        with mock.patch.object(recovery.time, "monotonic", side_effect=lambda: now[0]), \
             mock.patch.object(recovery.source, "dump", side_effect=dump):
            with self.assertRaisesRegex(ValueError, "SOURCE_BUDGET_EXCEEDED"):
                self.synthetic_recovery()
        self.assertEqual(json.loads((self.output / "recovery.json").read_text())["status"], "FAIL")


if __name__ == "__main__":
    unittest.main(verbosity=2)
