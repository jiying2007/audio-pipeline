#!/usr/bin/env python3
"""Offline byte-transport tests. Fixtures are not admitted audio or science."""
from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path
import random
import select
import signal
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / ".github" / "scripts"))
import ci_evidence_transport as transport

SOURCE = "1" * 40
RUN = "local-offline-fixture"


class EvidenceTransportTests(unittest.TestCase):
    def setUp(self):
        area = tempfile.TemporaryDirectory(prefix="ci-transport-test-")
        self.addCleanup(area.cleanup)
        self.root = Path(area.name)
        self.source = self.root / "source"; self.source.mkdir()
        (self.source / "cases").mkdir(); (self.source / "empty-directory").mkdir()
        raw = random.Random(417).randbytes(16 * 1024)
        for i in range(24):
            item = self.source / "cases" / ("copy-%02d.f32" % i)
            item.write_bytes(raw)
            item.chmod(0o755 if i == 0 else 0o644)
        (self.source / "empty-file").touch()
        self.bundle = self.root / "bundle"
        self.restored = self.root / "restored"

    def pack(self):
        return transport.pack(self.source, self.bundle, SOURCE, RUN)

    def unpack(self):
        return transport.unpack(self.bundle, self.restored, SOURCE, RUN)

    def rewrite(self, *, manifest=None, objects=None, extra=None, mode=None, duplicate=False):
        """Reseal the outer digest so negatives reach the actual inner checks."""
        path = self.bundle / "evidence.zip"
        with zipfile.ZipFile(path) as z:
            members = {i.filename: z.read(i) for i in z.infolist()}
        value = json.loads(members["manifest.json"])
        if manifest is not None:
            manifest(value)
            members["manifest.json"] = transport.canonical(value)
        if objects is not None:
            objects(members)
        if extra is not None:
            members[extra] = b"offline-extra-member"
        with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as z:
            for name, raw in members.items():
                info = transport.zip_info(name)
                if mode is not None and name != "manifest.json":
                    info.external_attr = (mode | 0o644) << 16
                z.writestr(info, raw)
            if duplicate:
                z.writestr(transport.zip_info("manifest.json"), members["manifest.json"])
            ordinary = 22
            for row in value["files"]:
                name = "objects/" + row["sha256"]
                if name in members:
                    ordinary += z.getinfo(name).compress_size + 76 + 2 * len(row["path"].encode())
        record = json.loads((self.bundle / "transport.json").read_text())
        record.update(archive_sha256=transport.digest_file(path), archive_bytes=path.stat().st_size,
                      manifest_sha256=hashlib.sha256(members["manifest.json"]).hexdigest(),
                      equivalent_regular_zip_bytes=ordinary)
        (self.bundle / "transport.json").write_bytes(transport.canonical(record))

    def test_complete_roundtrip_preserves_files_directories_modes_and_separate_copies(self):
        expected = transport.inventory(self.source)
        record = self.pack(); self.unpack()
        self.assertEqual(transport.inventory(self.restored), expected)
        self.assertEqual(record["files"], 25)
        self.assertEqual(record["unique_blobs"], 2)
        self.assertLess(record["archive_bytes"], record["equivalent_regular_zip_bytes"])
        a = self.restored / "cases/copy-00.f32"
        b = self.restored / "cases/copy-01.f32"
        original = b.read_bytes()
        self.assertNotEqual(a.stat().st_ino, b.stat().st_ino)
        a.write_bytes(b"change-only-one-restored-copy")
        self.assertEqual(b.read_bytes(), original)

    def test_size_estimate_matches_independently_written_regular_zip(self):
        record = self.pack(); ordinary = self.root / "ordinary.zip"
        with zipfile.ZipFile(ordinary, "x", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as z:
            for path in sorted(self.source.rglob("*")):
                if path.is_file():
                    z.writestr(transport.zip_info(path.relative_to(self.source).as_posix()), path.read_bytes())
        self.assertEqual(record["equivalent_regular_zip_bytes"], ordinary.stat().st_size)

    def test_unprofitable_package_is_rejected_without_publication(self):
        tiny = self.root / "tiny"; tiny.mkdir(); (tiny / "file").write_bytes(b"x")
        with self.assertRaisesRegex(transport.TransportError, "COMPRESSED_SIZE_REGRESSION"):
            transport.pack(tiny, self.bundle, SOURCE, RUN)
        self.assertFalse(self.bundle.exists())

    def test_existing_output_and_symlink_are_not_overwritten(self):
        self.pack(); self.restored.mkdir(); sentinel = self.restored / "sentinel"
        sentinel.write_bytes(b"preserve")
        with self.assertRaisesRegex(transport.TransportError, "OUTPUT_NOT_FRESH"):
            self.unpack()
        self.assertEqual(sentinel.read_bytes(), b"preserve")
        sentinel.unlink(); self.restored.rmdir(); self.restored.symlink_to(self.source)
        with self.assertRaisesRegex(transport.TransportError, "OUTPUT_NOT_FRESH"):
            self.unpack()

    def test_pack_rejects_symbolic_links_and_special_mode(self):
        link = self.source / "linked"; link.symlink_to(self.source / "cases/copy-00.f32")
        with self.assertRaisesRegex(transport.TransportError, "NONREGULAR"):
            self.pack()
        link.unlink(); path = self.source / "cases/copy-00.f32"; path.chmod(0o4755)
        with self.assertRaisesRegex(transport.TransportError, "UNSAFE_EVIDENCE_MODE"):
            self.pack()
        path.chmod(0o755)

    def test_pack_rejects_changed_nonrepresentative_copy(self):
        original = transport.zip_info; changed = False
        def alter(name):
            nonlocal changed
            if name.startswith("objects/") and not changed:
                (self.source / "cases/copy-23.f32").write_bytes(b"changed")
                changed = True
            return original(name)
        with mock.patch.object(transport, "zip_info", side_effect=alter):
            with self.assertRaisesRegex(transport.TransportError, "SOURCE_CHANGED_DURING_PACK"):
                self.pack()
        self.assertFalse(self.bundle.exists())

    def test_corrupt_full_archive_fails_before_extraction(self):
        self.pack(); path = self.bundle / "evidence.zip"
        data = bytearray(path.read_bytes()); data[50] ^= 1; path.write_bytes(data)
        with self.assertRaisesRegex(transport.TransportError, "BUNDLE_RECEIPT_OR_HASH_MISMATCH"):
            self.unpack()
        self.assertFalse(self.restored.exists())

    def test_resealed_corrupt_object_fails_its_actual_hash(self):
        self.pack()
        def corrupt(members):
            name = next(k for k, v in members.items() if k.startswith("objects/") and len(v) > 1)
            data = bytearray(members[name]); data[2] ^= 1; members[name] = bytes(data)
        self.rewrite(objects=corrupt)
        with self.assertRaisesRegex(transport.TransportError, "OBJECT_HASH_OR_SIZE_MISMATCH"):
            self.unpack()
        self.assertFalse(self.restored.exists())

    def test_manifest_resealed_adversarial_cases(self):
        self.pack()
        saved = {p.name: p.read_bytes() for p in self.bundle.iterdir()}
        cases = [
            lambda m: m.update(execution_source="2" * 40),
            lambda m: m.update(run_id="local-wrong-run"),
            lambda m: m.update(authority="SCIENTIFIC_PASS"),
            lambda m: m.update(shipping_authority=True),
            lambda m: m["files"][0].update(path="../escape"),
            lambda m: m["files"][0].update(path="/absolute"),
            lambda m: m["files"][0].update(path="cases\\escape"),
            lambda m: m["files"][0].update(path="cases//escape"),
            lambda m: m["files"][0].update(path=m["files"][1]["path"]),
            lambda m: m["files"][0].update(mode=0o4755),
            lambda m: m["files"][0].update(bytes=True),
            lambda m: m["files"][0].update(bytes=transport.MAX_FILE_BYTES + 1),
            lambda m: m["files"][0].update(bytes=m["files"][0]["bytes"] - 1),
            lambda m: m["directories"].clear(),
            lambda m: m.update(logical_bytes=m["logical_bytes"] + 1),
            lambda m: m.update(unique_bytes=m["unique_bytes"] + 1),
            lambda m: m["files"].reverse(),
        ]
        for i, mutate in enumerate(cases):
            with self.subTest(case=i):
                for name, raw in saved.items():
                    (self.bundle / name).write_bytes(raw)
                self.rewrite(manifest=mutate)
                with self.assertRaises(transport.TransportError):
                    self.unpack()
                self.assertFalse(self.restored.exists())

    def test_zip_membership_symlink_and_duplicate_negatives(self):
        self.pack(); saved = {p.name: p.read_bytes() for p in self.bundle.iterdir()}
        probes = [(dict(extra="../escape"), "ZIP_MEMBER_TYPE"),
                  (dict(extra="objects/" + "0" * 64), "UNEXPECTED_OR_MISSING_OBJECT"),
                  (dict(mode=stat.S_IFLNK), "ZIP_MEMBER_TYPE"),
                  (dict(duplicate=True), "DUPLICATE_ZIP_MEMBER")]
        for change, reason in probes:
            with self.subTest(reason=reason):
                for name, raw in saved.items():
                    (self.bundle / name).write_bytes(raw)
                self.rewrite(**change)
                with self.assertRaisesRegex(transport.TransportError, reason):
                    self.unpack()
                self.assertFalse(self.restored.exists())

    def test_duplicate_nonfinite_and_oversize_metadata(self):
        for raw in (b'{"a":1,"a":2}\n', b'{"a":NaN}\n', b'{}\n '):
            with self.assertRaises(transport.TransportError):
                transport.parse_json(raw, 100)
        with self.assertRaisesRegex(transport.TransportError, "METADATA_SIZE_LIMIT"):
            transport.parse_json(b"x" * 101, 100)

    def test_cli_roundtrip_with_fixed_memory_and_deadline(self):
        command = [sys.executable, str(Path(transport.__file__)), "pack", "--input", str(self.source),
                   "--output", str(self.bundle), "--execution-source", SOURCE, "--run-id", RUN]
        result = subprocess.run(command, capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        command[2] = "unpack"; command[4] = str(self.bundle); command[6] = str(self.restored)
        result = subprocess.run(command, capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(transport.inventory(self.source), transport.inventory(self.restored))
        self.assertEqual(transport.STAGE_SECONDS, 180)
        self.assertEqual(transport.MEMORY_BYTES, 256 * 1024 * 1024)

    def test_real_cli_timeout_after_ipc_checkpoint_preserves_failure(self):
        worker = self.root / "timeout-worker.py"
        failure = self.root / "failure.json"
        worker.write_text(
            "import sys,signal\n"
            "sys.path.insert(0," + repr(str(Path(transport.__file__).parent)) + ")\n"
            "import ci_evidence_transport as t\n"
            "def wait(root):\n"
            " print('TRANSPORT_READY',flush=True)\n"
            " sys.stdin.buffer.read(1)\n"
            " signal.setitimer(signal.ITIMER_REAL,0.02)\n"
            " sys.stdin.buffer.read(1)\n"
            " raise AssertionError('timeout did not stop transport')\n"
            "t.inventory=wait\n"
            "raise SystemExit(t.main())\n")
        proc = subprocess.Popen([sys.executable, str(worker), "pack", "--input", str(self.source),
             "--output", str(self.bundle), "--execution-source", SOURCE, "--run-id", RUN,
             "--failure-file", str(failure)], stdin=subprocess.PIPE,
             stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            ready, _, _ = select.select([proc.stdout], [], [], 30)
            self.assertTrue(ready, "test did not reach transport IPC checkpoint")
            self.assertEqual(proc.stdout.readline(), b"TRANSPORT_READY\n")
            proc.stdin.write(b"x"); proc.stdin.flush()
            self.assertEqual(proc.wait(timeout=30), 1)
            record = json.loads(failure.read_text())
            self.assertEqual(record["reason"], "TRANSPORT_WALL_DEADLINE")
            self.assertFalse(record["scientific_validation_passed"])
            self.assertFalse(self.bundle.exists())
        finally:
            if proc.poll() is None:
                proc.kill(); proc.wait()
            for stream in (proc.stdin, proc.stdout, proc.stderr):
                stream.close()


if __name__ == "__main__":
    unittest.main()
