#!/usr/bin/env python3
"""Offline controls for A3-R2-T0; no GitHub HTTP, C/DSP or F1 execution."""
from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest import mock

HERE = Path(__file__).with_name("fe09_a3_r2_source_audit.py")
SPEC = importlib.util.spec_from_file_location("a3_r2_audit", HERE)
M = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(M)


def rows(count=3):
    result, blobs = [], {}
    for i in range(count):
        raw = ("distinct A3 offline test source %03d\n" % i).encode()
        oid = M.git_blob(raw)
        path = "tests/validation/frontend_evolution/offline_a3_%03d.c" % i
        result.append({"path": path, "role": "OFFLINE_TEST",
                       "baseline": M.BASELINE, "equals_5187_original_bytes": True,
                       "bytes": len(raw), "sha256": M.digest(raw),
                       "git_blob_sha1": oid})
        blobs[oid] = raw
    return result, blobs


def trees(data):
    original = {row["path"]: ("100644", row["git_blob_sha1"]) for row in data}
    return original, copy.deepcopy(original), copy.deepcopy(original)


def pending():
    return [{"status": "NOT_IMPLEMENTED_NOT_AUTHORIZED"} for _ in range(6)]


def lock_fixture():
    data, _ = rows(88)
    return {"schema_version": 2, "id": M.IDENTITY, "original_baseline": M.BASELINE,
            "original_comparison_commit": M.COMPARISON,
            "execution_admitted_by_this_file": False,
            "status": "DRAFT_R1_OFFLINE_TEST_NOT_ADMITTED",
            "known_immutable_file_count": 88, "known_immutable_files": data,
            "pending_implementation_file_count": 6, "pending_implementation_files": pending()}


class SourceAuditTests(unittest.TestCase):
    def test_positive_three_original_bytes_current_unchanged(self):
        records, blobs = rows()
        a, b, current = trees(records)
        report = M.inspect_originals(records, a, b, current, lambda oid, cap: blobs[oid])
        self.assertEqual(report["original_88_checked"], 3)
        self.assertEqual(report["current_same"], 3)
        self.assertEqual(report["current_changed"], 0)
        self.assertEqual(report["current_missing"], 0)
        self.assertTrue(report["registered_88_equal_current"])
        self.assertTrue(report["current_tree_is_original_tree"])

    def test_current_source_differences_are_reported_not_promoted(self):
        records, blobs = rows()
        a, b, current = trees(records)
        current[records[0]["path"]] = ("100644", "f" * 40)
        current.pop(records[1]["path"])
        report = M.inspect_originals(records, a, b, current, lambda oid, cap: blobs[oid])
        self.assertEqual((report["current_same"], report["current_changed"],
                          report["current_missing"]), (1, 1, 1))
        self.assertFalse(report["current_tree_is_original_tree"])
        self.assertEqual(report["changed_current_paths"], [records[0]["path"]])
        self.assertEqual(report["missing_current_paths"], [records[1]["path"]])
        self.assertTrue(all(v is False for v in M.DENIALS.values()))

    def test_unregistered_change_is_not_misreported_as_identical_full_tree(self):
        records, blobs = rows()
        original, comparison, current = trees(records)
        current["unregistered-new-file.txt"] = ("100644", "f" * 40)
        report = M.inspect_originals(records, original, comparison, current,
                                     lambda oid, cap: blobs[oid])
        self.assertEqual((report["current_same"], report["current_changed"],
                          report["current_missing"]), (3, 0, 0))
        self.assertTrue(report["registered_88_equal_current"])
        self.assertFalse(report["current_tree_is_original_tree"])

    def test_original_baseline_or_comparison_drift_rejects(self):
        records, blobs = rows()
        for tree_index in (0, 1):
            a, b, current = trees(records)
            selected = a if tree_index == 0 else b
            selected[records[1]["path"]] = ("100644", "f" * 40)
            with self.assertRaisesRegex(M.Rejected, "A3_ORIGINAL_BASELINE_OR_COMPARISON_DRIFT"):
                M.inspect_originals(records, a, b, current, lambda oid, cap: blobs[oid])

    def test_original_missing_or_symlink_rejects(self):
        records, blobs = rows()
        for mode in ("missing", "symlink", "executable_mismatch"):
            a, b, current = trees(records)
            path = records[0]["path"]
            if mode == "missing":
                b.pop(path)
            elif mode == "symlink":
                a[path] = ("120000", records[0]["git_blob_sha1"])
            else:
                b[path] = ("100755", records[0]["git_blob_sha1"])
            with self.assertRaises(M.Rejected):
                M.inspect_originals(records, a, b, current, lambda oid, cap: blobs[oid])

    def test_wrong_bytes_length_digest_or_git_blob_rejected(self):
        records, blobs = rows()
        a, b, current = trees(records)
        for callback in (lambda oid, cap: b"short",
                         lambda oid, cap: blobs[oid] + b"wrong"):
            with self.assertRaisesRegex(M.Rejected, "A3_ORIGINAL_BYTE_DIGEST_DRIFT"):
                M.inspect_originals(records, a, b, current, callback)
        mutated = copy.deepcopy(records)
        mutated[0]["sha256"] = "f" * 64
        with self.assertRaisesRegex(M.Rejected, "A3_ORIGINAL_BYTE_DIGEST_DRIFT"):
            M.inspect_originals(mutated, a, b, current, lambda oid, cap: blobs[oid])

    def test_duplicate_row_and_path_traversal_rejected(self):
        data, _ = rows()
        for path in ("../escape", "/abs", "a//b", "a/./b", "a/../b", ".git/config",
                     "a\\b", "a\nb", "", "-opt"):
            with self.assertRaisesRegex(M.Rejected, "A3_UNSAFE_ARCHIVED_PATH"):
                M.safe_path(path)
        dupe = data + [copy.deepcopy(data[0])]
        with self.assertRaisesRegex(M.Rejected, "A3_ORIGINAL_DUPLICATE_PATH"):
            M.validate_rows(dupe)

    def test_wrong_row_types_and_untrusted_identity_rejected(self):
        data, _ = rows()
        mutations = (("bytes", True), ("bytes", 0), ("bytes", M.MAX_FILE+1),
                     ("sha256", "A"*64), ("sha256", "0"*64), ("git_blob_sha1", "0"*40),
                     ("equals_5187_original_bytes", False), ("baseline", "f"*40))
        for key, value in mutations:
            bad = copy.deepcopy(data)
            bad[0][key] = value
            with self.subTest(key=key, value=value), self.assertRaises(M.Rejected):
                M.validate_rows(bad)

    def test_archived_member_rejects_replaced_blob_or_mode(self):
        raw = b"offline synthetic archived member\n"
        oid = M.git_blob(raw)
        path = "safe/archive.c"
        reader = SimpleNamespace(blob=lambda object_id, limit: raw)
        result = M.archived_member(reader, {path: ("100644", oid)}, path, oid)
        self.assertEqual(result["sha256"], M.digest(raw))
        for value in ({}, {path: ("100755", oid)}, {path: ("100644", "f"*40)}):
            with self.assertRaisesRegex(M.Rejected, "A3_ARCHIVED_MEMBER_DRIFT"):
                M.archived_member(reader, value, path, oid)

    def test_parse_nul_delimited_exact_tree(self):
        blob = "a"*40
        raw = ("100644 blob "+blob+"\tfoo.c\0"+
               "100755 blob "+blob+"\tscripts/runner.sh\0").encode()
        self.assertEqual(M.parse_tree(raw),
                         {"foo.c": ("100644", blob), "scripts/runner.sh": ("100755", blob)})
        for malformed in (b"x\0", raw + raw, b"100644 commit " + blob.encode() + b"\tfoo\0",
                          b"100644 blob " + (b"0" * 40) + b"\tzero\0"):
            with self.assertRaises(M.Rejected):
                M.parse_tree(malformed)

    def test_tree_size_limit_and_duplicate_rejected(self):
        with self.assertRaisesRegex(M.Rejected, "A3_TREE_BYTES_BOUND"):
            M.parse_tree(b"a" * M.MAX_TREE)
        blob = "a"*40
        row = ("100644 blob "+blob+"\tduplicate.c\0").encode()
        with self.assertRaises(M.Rejected):
            M.parse_tree(row + row)

    def test_original_lock_contract_fixtures(self):
        sample = lock_fixture()
        raw = (json.dumps(sample, sort_keys=True) + "\n").encode()
        with mock.patch.object(M, "LOCK_BLOB", M.git_blob(raw)):
            self.assertEqual(len(M.decode_lock(raw)), 88)
            for change in ({"execution_admitted_by_this_file": True},
                           {"known_immutable_file_count": 87},
                           {"pending_implementation_file_count": 5},
                           {"status": "FROZEN_PRODUCTION"},
                           {"original_baseline": "f"*40}):
                bad = {**sample, **change}
                encoded = (json.dumps(bad, sort_keys=True) + "\n").encode()
                with mock.patch.object(M, "LOCK_BLOB", M.git_blob(encoded)):
                    with self.assertRaises(M.Rejected):
                        M.decode_lock(encoded)

    def test_lock_missing_duplicate_and_nonfinite_json_rejected(self):
        sample = lock_fixture()
        sample["known_immutable_files"] = sample["known_immutable_files"][:-1]
        raw = (json.dumps(sample, sort_keys=True) + "\n").encode()
        with mock.patch.object(M, "LOCK_BLOB", M.git_blob(raw)):
            with self.assertRaisesRegex(M.Rejected, "A3_ORIGINAL_88_MISSING"):
                M.decode_lock(raw)
        for raw in (b'{"v":1,"v":2}', b'{"v":NaN}', b'{"v":1e999}',
                    b'{"v":[-1e999]}', b"\xff"):
            with mock.patch.object(M, "LOCK_BLOB", M.git_blob(raw)), self.assertRaises(M.Rejected):
                M.decode_lock(raw)

    def test_source_lock_replaced_bytes_rejected_before_parse(self):
        with self.assertRaisesRegex(M.Rejected, "A3_ORIGINAL_LOCK_BYTES_CHANGED"):
            M.decode_lock(b'{"schema_version":2}')

    def test_git_environment_disallows_network_and_credentials(self):
        reader = M.GitReader(M.ROOT)
        self.assertEqual(reader.env["GIT_NO_LAZY_FETCH"], "1")
        self.assertEqual(reader.env["GIT_ALLOW_PROTOCOL"], "")
        self.assertNotIn("GH_TOKEN", reader.env)
        with self.assertRaisesRegex(M.Rejected, "A3_LOCAL_GIT_READONLY"):
            reader.run(["fetch", "origin"])

    def test_invalid_ref_and_blob_id_reject(self):
        reader = M.GitReader(M.ROOT)
        for invalid in ("f"*39, "0"*40, "0"*40+"X", "../HEAD", "", "F"*40):
            with self.assertRaises(M.Rejected):
                reader.tree(invalid)
            with self.assertRaises(M.Rejected):
                reader.blob(invalid, 64)

    def test_audit_cli_nonpromotion_flags_and_status(self):
        self.assertTrue(all(value is False for value in M.DENIALS.values()))
        self.assertIn("NO_EXECUTION", M.STATUS)
        stdout = []
        with mock.patch.object(M, "execute", return_value={"status": M.STATUS, **M.DENIALS}):
            with mock.patch("builtins.print", side_effect=lambda *args, **kwargs: stdout.extend(args)):
                self.assertEqual(M.main(["--check"]), 0)
        parsed = json.loads(stdout[0])
        self.assertFalse(any(parsed[key] for key in M.DENIALS))


if __name__ == "__main__":
    unittest.main(verbosity=2)
