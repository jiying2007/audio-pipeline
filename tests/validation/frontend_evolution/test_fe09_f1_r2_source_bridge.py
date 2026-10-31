#!/usr/bin/env python3
"""Offline source-bridge controls; synthetic bytes are not research evidence."""
import contextlib
import copy
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock

SPEC = importlib.util.spec_from_file_location("f1_source_bridge", Path(__file__).with_name("fe09_f1_r2_source_bridge.py"))
M = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(M)


class BridgeTests(unittest.TestCase):
    def setUp(self):
        self.names = sorted(M.CURRENT) + ["unchanged/member-%03d.c" % i for i in range(87)]
        self.before = {p: ("offline historical fixture: " + p + "\n").encode() for p in self.names}
        self.after = {p: (("offline current fixture: " + p + "\n").encode()
                         if i < 9 else self.before[p]) for i, p in enumerate(self.names)}
        self.reviewed = {p: M.identity(self.after[p])["git_blob_sha1"] for p in self.names[:9]}
        self.rows = [{"path": p, "role": "IMMUTABLE_ORIGINAL_F0_LOCKED_SOURCE",
                      "source_commit": M.ORIGINAL, **M.identity(self.before[p])} for p in self.names]
        self.revision, self.tree = "a" * 40, "b" * 40
        self.proof = {"status": "R5_T1_EXACT_SOURCE_IDENTITY_VERIFIED_NO_DSP_EXECUTION",
                      "execution_source": self.revision, "execution_tree": self.tree,
                      "candidate_version": "2.3.61", "reviewed_source_blobs": self.reviewed,
                      "source_delta_members_verified": 9,
                      **dict.fromkeys(("science_executed", "shipping_authority", "ssc305_hil_qualified",
                      "four_mic_public_sdk", "r1_or_r2_result_inherited", "r3_result_inherited",
                      "r4_result_inherited"), False)}
        self.patcher = mock.patch.object(M, "CURRENT", self.reviewed)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)

    def call(self, **changes):
        values = dict(rows=self.rows, historical=self.before, current=self.after,
                      proof=self.proof, revision=self.revision, tree=self.tree)
        values.update(changes)
        return M.reconcile(**values)

    def lock(self):
        return {"schema_version": 1, "id": M.OLD_ID, "execution_admitted": False,
                "source_anchor": {"commit": M.ORIGINAL, "tree": M.ORIGINAL_TREE},
                "file_count": 109, "immutable_original_file_count": 96,
                "files": self.rows + [{"path": "pending/file-%d" % i, "role": "PENDING_IMPLEMENTATION"}
                                        for i in range(13)]}

    def parse(self, data=None, raw=None):
        raw = json.dumps(self.lock() if data is None else data).encode() if raw is None else raw
        # Only the local fixture's outer lock hash is patched. All structural,
        # membership, anchor, mode and partition rules remain the real code.
        with mock.patch.object(M, "LOCK_BLOB", M.identity(raw)["git_blob_sha1"]), mock.patch.object(
                M, "LOCK_SHA256", hashlib.sha256(raw).hexdigest()):
            return M.load_lock(raw)

    def test_exact_partition_and_byte_roles(self):
        result = self.call()
        self.assertEqual(len(result), 96)
        self.assertEqual(sum(r["role"].startswith("R5_REVIEWED") for r in result), 9)
        self.assertEqual(sum(r["role"] == "BYTE_IDENTICAL_HISTORICAL_MEMBER" for r in result), 87)
        self.assertEqual([r["path"] for r in result], sorted(self.names))

    def test_every_historical_member_change_rejects(self):
        for path in self.names:
            with self.subTest(path=path), self.assertRaisesRegex(M.Rejected, "HISTORICAL_MEMBER_DRIFT"):
                self.call(historical={**self.before, path: self.before[path] + b"edited"})

    def test_each_reviewed_current_member_drift_rejects(self):
        for path in self.names[:9]:
            with self.subTest(path=path), self.assertRaisesRegex(M.Rejected, "CURRENT_REVIEWED_MEMBER_DRIFT"):
                self.call(current={**self.after, path: self.after[path] + b"edited"})

    def test_each_reviewed_current_rollback_rejects(self):
        for path in self.names[:9]:
            with self.subTest(path=path), self.assertRaises(M.Rejected):
                self.call(current={**self.after, path: self.before[path]})

    def test_all_87_other_changes_reject(self):
        for path in self.names[9:]:
            with self.subTest(path=path), self.assertRaisesRegex(M.Rejected, "UNREVIEWED_CURRENT_MEMBER_DRIFT"):
                self.call(current={**self.after, path: self.after[path] + b"edited"})

    def test_missing_extra_and_renamed_paths_reject(self):
        for field, value in (("historical", self.before), ("current", self.after)):
            for mutation in ("missing", "extra", "renamed"):
                altered = dict(value)
                if mutation != "extra":
                    content = altered.pop(self.names[0])
                if mutation != "missing":
                    altered["other.c"] = content if mutation == "renamed" else b"extra"
                with self.subTest(field=field, mutation=mutation), self.assertRaises(M.Rejected):
                    self.call(**{field: altered})

    def test_duplicate_or_missing_original_rows_reject(self):
        for rows in (self.rows[:-1], self.rows + [self.rows[0]], self.rows[:-1] + [self.rows[0]]):
            with self.assertRaises(M.Rejected):
                self.call(rows=rows)

    def test_untrusted_receipt_identity_rejects(self):
        for key, value in (("status", "PASS"), ("execution_source", "c" * 40),
                           ("execution_tree", "c" * 40), ("candidate_version", "2.3.60"),
                           ("source_delta_members_verified", True),
                           ("source_delta_members_verified", 8), ("reviewed_source_blobs", {})):
            with self.subTest(key=key), self.assertRaisesRegex(M.Rejected, "R5_CURRENT_PROOF_REQUIRED"):
                self.call(proof={**self.proof, key: value})

    def test_missing_and_promoting_proof_flags_reject(self):
        for key, value in self.proof.items():
            for new_value in (None, True, 0):
                if value is not False:
                    continue
                with self.subTest(key=key, value=new_value), self.assertRaises(M.Rejected):
                    self.call(proof={**self.proof, key: new_value})
            altered = dict(self.proof)
            altered.pop(key)
            with self.subTest(missing=key), self.assertRaises(M.Rejected):
                self.call(proof=altered)

    def test_invalid_current_identity_rejects(self):
        for value in ("0" * 40, "A" * 40, "x", None, True):
            with self.assertRaises(M.Rejected):
                self.call(revision=value)

    def test_original_row_hash_size_and_blob_checked(self):
        for field, value in (("bytes", 99), ("sha256", "0" * 64), ("git_blob_sha1", "0" * 40)):
            rows = copy.deepcopy(self.rows)
            rows[0][field] = value
            with self.assertRaises(M.Rejected):
                self.call(rows=rows)

    def test_lock_fixture_structure(self):
        self.assertEqual(self.parse(), self.rows)

    def test_real_outer_lock_pin_not_replaceable(self):
        with self.assertRaisesRegex(M.Rejected, "ARCHIVED_LOCK_IDENTITY_DRIFT"):
            M.load_lock(json.dumps(self.lock()).encode())

    def test_lock_anchor_identity_count_and_authority_reject(self):
        changes = (("schema_version", True), ("id", "OTHER"), ("execution_admitted", True),
                   ("source_anchor", {"commit": "c" * 40, "tree": M.ORIGINAL_TREE}),
                   ("file_count", 108), ("file_count", True),
                   ("immutable_original_file_count", 95))
        for key, value in changes:
            with self.subTest(key=key), self.assertRaises(M.Rejected):
                self.parse({**self.lock(), key: value})

    def test_lock_row_invalid_identities_reject(self):
        for key, value in (("bytes", True), ("bytes", M.MAX_FILE + 1), ("bytes", 0),
                           ("source_commit", "c" * 40), ("git_blob_sha1", "0" * 40),
                           ("sha256", "bad"), ("role", None)):
            lock = copy.deepcopy(self.lock())
            lock["files"][0][key] = value
            with self.subTest(key=key), self.assertRaises(M.Rejected):
                self.parse(lock)

    def test_lock_duplicate_paths_reject(self):
        lock = copy.deepcopy(self.lock())
        lock["files"][-1]["path"] = lock["files"][0]["path"]
        with self.assertRaises(M.Rejected):
            self.parse(lock)

    def test_unsafe_paths_and_quoting_reject(self):
        for path in ("../x", "/tmp/x", "a//b", "a/./b", "a/../b", ".git/config",
                     "-x", "a\nb", "a\x00b", "x:y", "x\\y", "x" * 301):
            with self.subTest(path=path), self.assertRaises(M.Rejected):
                M.path_name(path)
        self.assertEqual(M.path_name(".github/a-b.py"), ".github/a-b.py")

    def test_duplicate_and_nonfinite_lock_json_reject(self):
        prefix = json.dumps(self.lock()).encode()[:-1]
        for addition in (b'"schema_version":1', b'"extra":NaN', b'"extra":Infinity',
                         b'"extra":1e999', b'"extra":{"a":[-1e999]}'):
            with self.assertRaises(M.Rejected):
                self.parse(raw=prefix + b"," + addition + b"}")

    def test_finite_extra_json_does_not_change_partition(self):
        self.assertEqual(self.parse({**self.lock(), "offline_extra": 1.7e308}), self.rows)

    def test_member_bytes_bounds(self):
        for raw in (b"", b"a" * (M.MAX_FILE + 1), "not bytes"):
            with self.assertRaises(M.Rejected):
                M.identity(raw)
        self.assertEqual(M.identity(b"x" * M.MAX_FILE)["bytes"], M.MAX_FILE)


class LocalGitTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.command("init", "-q")
        self.command("config", "user.name", "offline-fixture")
        self.command("config", "user.email", "offline@example.invalid")
        (self.root / "member.c").write_bytes(b"original local fixture\n")
        self.command("add", ".")
        self.command("commit", "-qm", "local fixture, not provider or experiment")
        self.revision = self.command("rev-parse", "HEAD").decode().strip()
        self.git = M.Git(self.root)

    def command(self, *args):
        return subprocess.check_output(["git", *args], cwd=self.root, stderr=subprocess.PIPE)

    def test_real_local_blob_and_worktree_match(self):
        self.assertEqual(self.git.current(self.revision, "member.c"), b"original local fixture\n")
        self.assertEqual(self.git.oid("HEAD^{commit}"), self.revision)

    def test_missing_git_object_fails_without_fetch(self):
        with self.assertRaises(M.Rejected):
            self.git.blob("f" * 40, "member.c")
        self.assertEqual(self.git.env["GIT_ALLOW_PROTOCOL"], "")
        self.assertEqual(self.git.env["GIT_NO_LAZY_FETCH"], "1")

    def test_missing_member_rejects(self):
        with self.assertRaisesRegex(M.Rejected, "SOURCE_MISSING_OR_MODE_DRIFT"):
            self.git.blob(self.revision, "other.c")

    def test_executable_git_mode_rejects(self):
        (self.root / "member.c").chmod(0o755)
        self.command("add", ".")
        self.command("commit", "-qm", "fixture executable")
        revision = self.command("rev-parse", "HEAD").decode().strip()
        with self.assertRaisesRegex(M.Rejected, "SOURCE_MISSING_OR_MODE_DRIFT"):
            self.git.blob(revision, "member.c")

    def test_symlink_git_mode_rejects(self):
        path = self.root / "member.c"
        path.unlink()
        path.symlink_to("elsewhere")
        self.command("add", ".")
        self.command("commit", "-qm", "fixture symlink")
        revision = self.command("rev-parse", "HEAD").decode().strip()
        with self.assertRaisesRegex(M.Rejected, "SOURCE_MISSING_OR_MODE_DRIFT"):
            self.git.blob(revision, "member.c")

    def test_worktree_symlink_and_mode_change_reject(self):
        path = self.root / "member.c"
        path.chmod(0o755)
        with self.assertRaisesRegex(M.Rejected, "SOURCE_WORKTREE_MODE_OR_SIZE_DRIFT"):
            self.git.current(self.revision, "member.c")
        path.unlink()
        path.symlink_to("missing")
        with self.assertRaisesRegex(M.Rejected, "SOURCE_WORKTREE_SYMLINK"):
            self.git.current(self.revision, "member.c")

    def test_same_size_dirty_worktree_rejects(self):
        path = self.root / "member.c"
        path.write_bytes(path.read_bytes().replace(b"original", b"modified"))
        with self.assertRaisesRegex(M.Rejected, "SOURCE_WORKTREE_BYTES_DRIFT"):
            self.git.current(self.revision, "member.c")
        with self.assertRaises(M.Rejected):
            self.git.run(["diff-index", "--quiet", "HEAD", "--"])

    def test_unreviewed_command_and_excess_output_reject(self):
        with self.assertRaisesRegex(M.Rejected, "LOCAL_GIT_READ_ONLY"):
            self.git.run(["fetch"])
        with self.assertRaisesRegex(M.Rejected, "LOCAL_GIT_OUTPUT_BOUND"):
            self.git.run(["rev-parse", "HEAD"], 8)

    def test_external_context_refused_before_subprocess(self):
        with mock.patch.dict(os.environ, {"GIT_DIR": "/untrusted"}), mock.patch.object(M.subprocess, "Popen") as run:
            with self.assertRaisesRegex(M.Rejected, "EXTERNAL_GIT_CONTEXT_REFUSED"):
                M.Git(self.root)
            run.assert_not_called()

    def test_r5_source_must_match_before_import(self):
        fake_git = mock.Mock()
        fake_git.current.return_value = b'raise RuntimeError("must not execute")\n'
        with mock.patch.object(M.importlib.util, "spec_from_file_location") as importer:
            with self.assertRaisesRegex(M.Rejected, "PROTECTED_R5_HELPER_DRIFT"):
                M.load_r5(self.root, fake_git, self.revision)
            importer.assert_not_called()


class ReceiptTests(unittest.TestCase):
    def fixture(self):
        return {"status": M.STATUS, "execution_source": "a" * 40, "historical_members": 96,
                "unchanged_current_members": 87, "separately_reviewed_current_members": 9,
                **dict.fromkeys(M.DENIALS, False)}

    def test_complete_source_only_receipt(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "receipt.json"
            with mock.patch.object(M, "check", return_value=self.fixture()), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(M.main(["--check", "--output", str(path)]), 0)
            self.assertEqual(json.loads(path.read_bytes()), self.fixture())

    def test_existing_receipt_is_never_overwritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "receipt.json"
            path.write_bytes(b"old evidence")
            with mock.patch.object(M, "check", return_value=self.fixture()), contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(M.main(["--check", "--output", str(path)]), 2)
            self.assertEqual(path.read_bytes(), b"old evidence")

    def test_error_has_no_positive_flags_or_raw_exception(self):
        with mock.patch.object(M, "check", side_effect=OSError("private details /tmp/unknown")), contextlib.redirect_stderr(io.StringIO()) as out:
            self.assertEqual(M.main(["--check"]), 2)
        result = json.loads(out.getvalue())
        self.assertEqual(result["status"], "F1_R2_T0_REJECTED")
        self.assertEqual(result["reason"], "SOURCE_OR_RECEIPT_UNAVAILABLE")
        for key in M.DENIALS:
            self.assertIs(result[key], False)

    def test_short_write_and_close_failure_reject(self):
        class Stream:
            def __init__(self, failure):
                self.failure = failure
            def __enter__(self):
                return self
            def write(self, raw):
                return len(raw) - 1 if self.failure == "short" else len(raw)
            def __exit__(self, *args):
                if self.failure == "close":
                    raise OSError("close error")
        for failure in ("short", "close"):
            with mock.patch.object(M, "check", return_value=self.fixture()), mock.patch.object(
                    Path, "open", return_value=Stream(failure)), contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(M.main(["--check", "--output", "unused.json"]), 2)

    def test_oversize_receipt_is_rejected(self):
        result = {**self.fixture(), "oversize": "x" * M.MAX_RECEIPT}
        with mock.patch.object(M, "check", return_value=result), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(M.main(["--check"]), 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
