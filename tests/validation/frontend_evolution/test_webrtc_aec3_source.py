#!/usr/bin/env python3
"""Tiny synthetic archive tests; no external source build or acoustic evidence."""
import copy
import io
from pathlib import Path
import stat
import subprocess
import tarfile
import tempfile
import unittest
import warnings
from unittest import mock
import zipfile

from contracts import B0
import webrtc_aec3_source as source


class SourceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        self.repo = self.home / "repo"
        self.registry = self.repo / "registry"
        self.registry.mkdir(parents=True)
        self.archives = self.home / "archives"
        self.archives.mkdir()
        self.prepared = self.home / "prepared"
        for name, value in (("ROOT", self.repo), ("LOCK", self.registry / "lock.json"),
                            ("ADMISSION", self.registry / "admission.json"), ("CATALOG", self.registry / "catalog.json"),
                            ("CONTRACTS", self.repo / "contracts.py")):
            patch = mock.patch.object(source, name, value)
            patch.start()
            self.addCleanup(patch.stop)

    def archive(self, entries=None, zip_format=False):
        entries = entries or [("tiny/a.txt", b"tiny source\n", "file")]
        buffer = io.BytesIO()
        if zip_format:
            with zipfile.ZipFile(buffer, "w") as archive:
                for name, data, kind in entries:
                    entry = zipfile.ZipInfo(name)
                    entry.create_system = 3
                    entry.external_attr = ((stat.S_IFLNK if kind == "symlink" else stat.S_IFREG) | 0o644) << 16
                    with warnings.catch_warnings():
                        warnings.simplefilter("ignore", UserWarning)
                        archive.writestr(entry, data)
        else:
            with tarfile.open(fileobj=buffer, mode="w") as archive:
                for name, data, kind in entries:
                    entry = tarfile.TarInfo(name)
                    entry.mode = 0o644
                    if kind == "file":
                        entry.size = len(data)
                    else:
                        entry.type = {"symlink": tarfile.SYMTYPE, "hardlink": tarfile.LNKTYPE,
                                      "fifo": tarfile.FIFOTYPE, "device": tarfile.CHRTYPE}[kind]
                        entry.linkname = "/outside"
                    archive.addfile(entry, io.BytesIO(data) if kind == "file" else None)
        data = buffer.getvalue()
        path = self.archives / ("tiny.zip" if zip_format else "tiny.tar")
        path.write_bytes(data)
        manifest = {"a.txt": source.file_record(b"tiny source\n", False)}
        return path, {"filename": path.name, "format": "zip" if zip_format else "tar", "root": "tiny",
                      "destination": "", "size": len(data), "sha256": source.sha256(data), "members": len(entries),
                      "files": 1, "unpacked_size": 12, "max_file_size": 128,
                      "files_manifest_sha256": source.sha256(source.encoded(manifest)), "git_tree": source.git_tree(manifest)}

    def fixture(self):
        _, spec = self.archive()
        manifest = {"a.txt": source.file_record(b"tiny source\n", False)}
        lock = {"distribution_commit": "1" * 40, "distribution_tree": spec["git_tree"],
                "archives": {"distribution": spec}, "materialized_source_sha256": source.sha256(source.encoded(manifest)),
                "build_contract": {"wall_seconds": 600, "parallel_jobs": 2, "target": "webrtc-audio-processing-2",
                                   "setup_arguments": ["--wrap-mode=nodownload", "--force-fallback-for=abseil-cpp"]}}
        source.write_json(source.LOCK, lock)
        rights = {key: "ALLOWED" for key in ("code", "dependencies", "weights", "data", "redistribution")}
        review = {"scope": source.SCOPE, "decision": "EXECUTION_ADMITTED_FIXED_REFERENCE_ONLY",
                  "shipping_authority": False, "distribution_commit": lock["distribution_commit"],
                  "distribution_tree": lock["distribution_tree"], "source_lock_sha256": source.sha256(source.LOCK.read_bytes()),
                  "materialized_source_sha256": lock["materialized_source_sha256"], "rights": rights}
        source.write_json(source.ADMISSION, review)
        catalog = {"schema_version": 1, "stage": "frontend-evolution-v1", "baseline_source": B0,
                   "sources": [{"id": "webrtc", "url": "https://example.invalid/tiny-synthetic-test-only", "status": "EXECUTION_ADMITTED",
                                "commit": lock["distribution_commit"], "scope": source.SCOPE, "rights": rights,
                                "admission_receipt_path": source.ADMISSION.relative_to(self.repo).as_posix(),
                                "admission_receipt_sha256": source.sha256(source.ADMISSION.read_bytes()),
                                "materialized_source_sha256": lock["materialized_source_sha256"]}]}
        source.write_json(source.CATALOG, catalog)
        return source.preflight(self.archives, self.prepared)

    def test_valid_tar_zip_and_git_tree(self):
        for kind in (False, True):
            path, spec = self.archive(zip_format=kind)
            self.assertEqual(source.read_archive(path, spec), {"a.txt": (b"tiny source\n", False)})
        self.assertEqual(source.git_tree({}), "4b825dc642cb6eb9a060e54bf8d69288fbee4904")

    def test_wrong_archive_size_hash_and_bounds(self):
        path, spec = self.archive()
        for field, value in (("size", 1), ("sha256", "0" * 64), ("members", 0),
                             ("max_file_size", 1), ("files", 2), ("unpacked_size", 1),
                             ("files_manifest_sha256", "0" * 64), ("git_tree", "0" * 40)):
            with self.subTest(field=field), self.assertRaises(ValueError):
                source.read_archive(path, dict(spec, **{field: value}))

    def test_unsafe_paths(self):
        for name in ("/tiny/a.txt", "tiny/../a.txt", "tiny/./a.txt", "tiny//a.txt", "wrong/a.txt", "tiny\\a.txt", "tiny/C:/a.txt", "tiny/a\nx"):
            with self.subTest(name=name):
                path, spec = self.archive([(name, b"tiny source\n", "file")])
                with self.assertRaises(ValueError):
                    source.read_archive(path, spec)

    def test_duplicate_members(self):
        entries = [("tiny/a.txt", b"tiny source\n", "file")] * 2
        for kind in (False, True):
            with self.subTest(zip=kind):
                path, spec = self.archive(entries, kind)
                with self.assertRaisesRegex(ValueError, "duplicate"):
                    source.read_archive(path, spec)

    def test_tar_links_and_special_files(self):
        for kind in ("symlink", "hardlink", "fifo", "device"):
            with self.subTest(kind=kind):
                path, spec = self.archive([("tiny/a.txt", b"", kind)])
                with self.assertRaisesRegex(ValueError, "link/special"):
                    source.read_archive(path, spec)

    def test_zip_symlink(self):
        path, spec = self.archive([("tiny/a.txt", b"outside", "symlink")], True)
        with self.assertRaisesRegex(ValueError, "link/special"):
            source.read_archive(path, spec)

    def test_parent_file_collision(self):
        path, spec = self.archive([("tiny/a", b"x", "file"), ("tiny/a/b", b"y", "file")])
        with self.assertRaisesRegex(ValueError, "collision"):
            source.read_archive(path, spec)

    def test_valid_preflight_admission_and_plan(self):
        receipt = self.fixture()
        self.assertEqual(source.admitted(self.prepared), receipt)
        plan = source.build_plan(self.prepared, self.home / "build", "/tools/meson")
        self.assertEqual(plan["status"], "BUILD_PLAN_NOT_EXECUTED")
        self.assertIn("--wrap-mode=nodownload", plan["setup"])
        self.assertIn("--force-fallback-for=abseil-cpp", plan["setup"])
        self.assertEqual(plan["compile"][-3:], ["--jobs", "2", "webrtc-audio-processing-2"])
        self.assertEqual(plan["wall_seconds"], 600)
        self.assertEqual(receipt["acoustic_measurement"], "NOT_RUN")

    def test_preflight_freshness_and_archive_symlink(self):
        self.fixture()
        with self.assertRaises(ValueError):
            source.preflight(self.archives, self.prepared)
        path, spec = self.archive()
        linked = self.home / "linked.tar"
        linked.symlink_to(path)
        with self.assertRaisesRegex(ValueError, "symlink"):
            source.read_archive(linked, spec)

    def test_overlay_overwrite_rejected_before_output(self):
        self.fixture()
        lock = source.load_json(source.LOCK)
        lock["archives"]["duplicate"] = copy.deepcopy(lock["archives"]["distribution"])
        source.write_json(source.LOCK, lock)
        output = self.home / "must-not-exist"
        with self.assertRaisesRegex(ValueError, "overwrite"):
            source.preflight(self.archives, output)
        self.assertFalse(output.exists())

    def test_source_mutation_extra_and_mode(self):
        self.fixture()
        path = self.prepared / "source/a.txt"
        original = path.read_bytes()
        for change in ("bytes", "extra", "mode"):
            with self.subTest(change=change):
                if change == "bytes":
                    path.write_bytes(b"changed")
                elif change == "extra":
                    (path.parent / "extra").write_bytes(b"x")
                else:
                    path.chmod(0o755)
                with self.assertRaises(ValueError):
                    source.verify(self.prepared)
                path.write_bytes(original)
                path.chmod(0o644)
                (path.parent / "extra").unlink(missing_ok=True)

    def test_source_symlink_and_hardlink(self):
        self.fixture()
        path = self.prepared / "source/a.txt"
        outside = self.home / "outside"
        outside.write_bytes(path.read_bytes())
        path.unlink()
        path.symlink_to(outside)
        with self.assertRaises(ValueError):
            source.verify(self.prepared)
        path.unlink()
        import os
        os.link(outside, path)
        with self.assertRaises(ValueError):
            source.verify(self.prepared)

    def test_receipt_and_manifest_drift(self):
        self.fixture()
        for name in ("source-receipt.json", "files.json"):
            path = self.prepared / name
            original = path.read_bytes()
            path.write_text("{}")
            with self.subTest(name=name), self.assertRaises(ValueError):
                source.verify(self.prepared)
            path.write_bytes(original)

    def test_unexpected_empty_directory_rejected(self):
        self.fixture()
        (self.prepared / "source/empty-extra").mkdir()
        with self.assertRaisesRegex(ValueError, "directory set"):
            source.verify(self.prepared)

    def test_no_implicit_catalog_admission(self):
        self.fixture()
        catalog = source.load_json(source.CATALOG)
        catalog["sources"][0]["status"] = "REFERENCE_REVIEW_ONLY"
        source.write_json(source.CATALOG, catalog)
        with self.assertRaisesRegex(ValueError, "not admitted"):
            source.admitted(self.prepared)

    def test_wrong_admission_hash_scope_and_rights(self):
        self.fixture()
        original = source.CATALOG.read_bytes()
        for field, value in (("admission_receipt_sha256", "0" * 64), ("scope", "other"),
                             ("commit", "2" * 40), ("materialized_source_sha256", "0" * 64)):
            catalog = source.load_json(source.CATALOG)
            catalog["sources"][0][field] = value
            source.write_json(source.CATALOG, catalog)
            with self.subTest(field=field), self.assertRaises(ValueError):
                source.admitted(self.prepared)
            source.CATALOG.write_bytes(original)

    def test_build_directory_disjoint_fresh_and_no_symlink(self):
        self.fixture()
        alias = self.home / "alias"
        alias.symlink_to(self.prepared, target_is_directory=True)
        for path in (self.prepared, self.prepared / "build", self.repo / "build", self.home, alias / "build"):
            with self.subTest(path=path), self.assertRaises(ValueError):
                source.build_plan(self.prepared, path, "meson")

    def test_build_budget_cannot_expand(self):
        self.fixture()
        lock = source.load_json(source.LOCK)
        lock["build_contract"]["wall_seconds"] = 601
        source.write_json(source.LOCK, lock)
        with mock.patch.object(source, "admitted", return_value={}):
            with self.assertRaisesRegex(ValueError, "budget"):
                source.build_plan(self.prepared, self.home / "build", "meson")

    def test_missing_source_field_rejected(self):
        self.fixture()
        review = source.load_json(source.ADMISSION)
        del review["distribution_tree"]
        source.write_json(source.ADMISSION, review)
        catalog = source.load_json(source.CATALOG)
        catalog["sources"][0]["admission_receipt_sha256"] = source.sha256(source.ADMISSION.read_bytes())
        source.write_json(source.CATALOG, catalog)
        with self.assertRaises(KeyError):
            source.admitted(self.prepared)

    def test_committed_controls_reject_uncommitted_admission(self):
        self.fixture()
        tool = self.repo / "tiny-source-tool.py"
        tool.write_text("# tiny control fixture only\n")
        source.CONTRACTS.write_text("# tiny contract fixture only\n")

        def git(command, **_):
            if command[-2:] == ["rev-parse", "HEAD"]:
                return ("1" * 40 + "\n").encode()
            if command[-2:] == ["rev-parse", "HEAD^{tree}"]:
                return ("2" * 40 + "\n").encode()
            relative = command[-1].split(":", 1)[1]
            return (self.repo / relative).read_bytes()

        with mock.patch.object(source, "__file__", str(tool)), mock.patch.object(source.subprocess, "check_output", side_effect=git):
            controls = source.committed_controls()
            self.assertEqual(len(controls["files_sha256"]), 5)
        original_git = git

        def stale_git(command, **kwargs):
            if command[-1].endswith(":registry/admission.json"):
                return b"stale admission"
            return original_git(command, **kwargs)

        with mock.patch.object(source, "__file__", str(tool)), mock.patch.object(source.subprocess, "check_output", side_effect=stale_git):
            with self.assertRaisesRegex(ValueError, "must be committed"):
                source.committed_controls()

    def test_budget_exhaustion_never_launches_process(self):
        with mock.patch.object(source.subprocess, "Popen") as launch:
            with self.assertRaisesRegex(ValueError, "budget"):
                source.run_logged(["must-not-run"], self.home / "log", {}, 0)
            launch.assert_not_called()

    def test_meson_object_directory_is_not_a_shared_library(self):
        build = self.home / "meson"
        objects = build / "libwebrtc-audio-processing-2.so.1.p"
        objects.mkdir(parents=True)
        (objects / "tiny.o").write_bytes(b"synthetic object-path fixture")
        with self.assertRaisesRegex(ValueError, "missing built"):
            source.built_shared_libraries(build)
        library = build / "libwebrtc-audio-processing-2.so.1"
        library.write_bytes(b"synthetic regular-file fixture; never compiled")
        (build / "libwebrtc-audio-processing-2.so").symlink_to(library)
        self.assertEqual(source.built_shared_libraries(build), [library])

    def test_timeout_terminates_full_process_group(self):
        process = mock.Mock(pid=12345)
        process.wait.side_effect = [subprocess.TimeoutExpired("tiny-fixture", 1), 0]
        with mock.patch.object(source.subprocess, "Popen", return_value=process), mock.patch.object(source.os, "killpg") as terminate:
            with self.assertRaisesRegex(ValueError, "process group terminated"):
                source.run_logged(["tiny-fixture"], self.home / "log", {}, source.time.monotonic() + 1)
            terminate.assert_called_once_with(12345, source.signal.SIGKILL)


if __name__ == "__main__":
    unittest.main()
