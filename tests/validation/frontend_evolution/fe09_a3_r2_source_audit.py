#!/usr/bin/env python3
"""A3-R2-T0: read-only archive/88-source identity and current-tree delta."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[3]
SELF = "tests/validation/frontend_evolution/fe09_a3_r2_source_audit.py"
ARCHIVE = "c4e9cb92af2fe42f09f09bcac0d0a814a511aab8"
ARCHIVE_TREE = "66a5e619587dcaf44c0fbd3c7292435e95190179"
BASELINE = "7138b17acd6246cc779efa7597d25771ddfc8c7a"
COMPARISON = "5187c5e59526d4047b3965b44c770ab21edbde9f"
LOCK_DIR = "docs/research/frontend-evolution-v1/FE09_A3_F0_LIVE_ROLL_PREREGISTRATION_R1_20261024/"
LOCK = LOCK_DIR + "source-lock.json"
LOCK_BLOB = "02a08648d829e3d27b7acb0bf1a1eb71790999df"
IDENTITY = "FE09-A3-F0-LIVE-SOURCE-ROLL-33-49-R1"
STATUS = "A3_R2_T0_ARCHIVE_DELTA_RECORDED_NO_EXECUTION"
SOURCE_DIR = "tests/validation/frontend_evolution/"
ARCHIVE_FILES = {
    "fe09_a3_f0_source_admission.py": "02566cc2904921fc6ea5a23129cae0a5e5ae4ce1",
    "fe09_a3_f0_live_roll.c": "3b79ca0681afd77e48d85fa0646ccea4fa744d62",
    "fe09_a3_f0_live_roll.h": "dff07def1aabcd2c1e3361e3f55f4050e4676cc1",
    "fe09_a3_f0_original_validator.c": "3d9af35bd4323716e43bc6d82e552a267a5905af",
}
REGISTERED_DOCS = {
    "README.md": "f0b95af09be542d6e3ef22321b16e8f5c4377dd6",
    "test-contract.json": "99f3f3a0857b138f6a5f53e4da15b9ade2ca8979",
    "EXECUTION_BASELINE.json": "a8d65656e654cd5596d251afb812f578f0f3546c",
}
DENIALS = dict.fromkeys((
    "a3_target_executed", "source_admission_granted", "a3_build_qualified",
    "provider_qualified", "external_freeze_verified", "formal_controls_qualified",
    "rss_measured", "public_sdk_qualified", "ssc305_hil_qualified",
    "shipping_authority"), False)
OID = re.compile(r"[0-9a-f]{40}\Z")
SHA256 = re.compile(r"[0-9a-f]{64}\Z")
PATH = re.compile(r"[a-zA-Z0-9_.\-/]+\Z")
MAX_FILE = 1048576
MAX_TREE = 4000000


class Rejected(ValueError):
    pass


def need(ok: bool, reason: str) -> None:
    if not ok:
        raise Rejected(reason)


def git_blob(raw: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(raw)).encode("ascii") + b"\0" + raw).hexdigest()


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def safe_path(path: object) -> str:
    need(type(path) is str and 0 < len(path) < 300 and
         PATH.fullmatch(path) is not None and not path.startswith(("/", "-")) and
         all(p not in ("", ".", "..", ".git") for p in path.split("/")),
         "A3_UNSAFE_ARCHIVED_PATH")
    return path


def json_pairs(rows):
    value = {}
    for key, item in rows:
        need(key not in value, "A3_DUPLICATE_LOCK_FIELD")
        value[key] = item
    return value


def finite_float(value: str) -> float:
    result = float(value)
    need(math.isfinite(result), "A3_LOCK_NONFINITE")
    return result


def decode_lock(raw: bytes) -> list[dict]:
    need(0 < len(raw) <= MAX_FILE and git_blob(raw) == LOCK_BLOB,
         "A3_ORIGINAL_LOCK_BYTES_CHANGED")
    try:
        data = json.loads(raw.decode("utf-8"), object_pairs_hook=json_pairs,
                          parse_constant=lambda _: (_ for _ in ()).throw(Rejected("A3_LOCK_NONFINITE")),
                          parse_float=finite_float)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise Rejected("A3_LOCK_INVALID_JSON") from exc
    need(type(data) is dict and data.get("schema_version") == 2 and
         data.get("id") == IDENTITY and data.get("original_baseline") == BASELINE and
         data.get("original_comparison_commit") == COMPARISON and
         data.get("execution_admitted_by_this_file") is False and
         type(data.get("status")) is str and data["status"].startswith("DRAFT_") and
         data.get("known_immutable_file_count") == 88 and
         data.get("pending_implementation_file_count") == 6,
         "A3_ORIGINAL_LOCK_SCOPE_DRIFT")
    rows = data.get("known_immutable_files")
    need(type(rows) is list and len(rows) == 88, "A3_ORIGINAL_88_MISSING")
    validate_rows(rows)
    pending = data.get("pending_implementation_files")
    need(type(pending) is list and len(pending) == 6 and
         all(type(p) is dict and p.get("status") == "NOT_IMPLEMENTED_NOT_AUTHORIZED"
             for p in pending), "A3_ORIGINAL_PENDING_WORK_REWRITTEN")
    return rows


def validate_rows(rows: list[dict]) -> None:
    names = set()
    for row in rows:
        need(type(row) is dict, "A3_ORIGINAL_ROW_INVALID")
        name = safe_path(row.get("path"))
        need(name not in names, "A3_ORIGINAL_DUPLICATE_PATH")
        names.add(name)
        need(row.get("baseline") == BASELINE and
             row.get("equals_5187_original_bytes") is True and
             type(row.get("bytes")) is int and
             0 < row["bytes"] <= MAX_FILE and
             type(row.get("git_blob_sha1")) is str and
             OID.fullmatch(row["git_blob_sha1"]) is not None and
             row["git_blob_sha1"] != "0" * 40 and
             type(row.get("sha256")) is str and
             SHA256.fullmatch(row["sha256"]) is not None and
             row["sha256"] != "0" * 64,
             "A3_ORIGINAL_ROW_IDENTITY_INVALID")


def parse_tree(raw: bytes) -> dict:
    need(type(raw) is bytes and len(raw) < MAX_TREE, "A3_TREE_BYTES_BOUND")
    result = {}
    for entry in raw.split(b"\0"):
        if not entry:
            continue
        try:
            metadata, raw_path = entry.split(b"\t", 1)
            mode, kind, oid = metadata.decode("ascii").split()
            path = raw_path.decode("utf-8")
        except (ValueError, UnicodeError) as exc:
            raise Rejected("A3_GIT_TREE_INVALID") from exc
        need(mode in ("100644", "100755", "120000") and kind == "blob" and
             OID.fullmatch(oid) is not None and oid != "0" * 40 and path not in result,
             "A3_GIT_TREE_INVALID")
        result[path] = (mode, oid)
    return result


class GitReader:
    """Exact local Git objects only: no HTTP, ref updates or lazy fetch."""
    def __init__(self, root: Path):
        self.root = root
        self.env = {"PATH": "/usr/bin:/bin", "HOME": "/tmp", "LC_ALL": "C",
                    "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_SYSTEM": "/dev/null",
                    "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_NO_REPLACE_OBJECTS": "1",
                    "GIT_NO_LAZY_FETCH": "1", "GIT_ALLOW_PROTOCOL": "",
                    "GIT_TERMINAL_PROMPT": "0", "GIT_OPTIONAL_LOCKS": "0"}

    def run(self, args: list[str], maximum: int = MAX_TREE) -> bytes:
        need(args and args[0] in ("rev-parse", "ls-tree", "cat-file", "diff-index"),
             "A3_LOCAL_GIT_READONLY")
        try:
            proc = subprocess.run(
                ["git", "--no-replace-objects", "-c",
                 "safe.directory=" + str(self.root),
                 "-c", "protocol.allow=never", "-c", "core.hooksPath=/dev/null",
                 "-c", "core.fsmonitor=false", *args],
                cwd=self.root, env=self.env, stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                timeout=12, check=False)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise Rejected("A3_GIT_OBJECT_UNAVAILABLE") from exc
        need(proc.returncode == 0 and len(proc.stdout) <= maximum and
             len(proc.stderr) <= 4096, "A3_GIT_OBJECT_UNAVAILABLE_OR_OVERSIZE")
        return proc.stdout

    def tree(self, rev: str) -> dict:
        need(OID.fullmatch(rev) is not None and rev != "0" * 40, "A3_GIT_REF_INVALID")
        return parse_tree(self.run(["ls-tree", "-rz", "--full-tree", rev]))

    def blob(self, oid: str, cap: int) -> bytes:
        need(OID.fullmatch(oid) is not None and oid != "0" * 40 and 0 < cap <= MAX_FILE,
             "A3_GIT_BLOB_BOUND_INVALID")
        raw = self.run(["cat-file", "blob", oid], cap)
        need(len(raw) <= cap and git_blob(raw) == oid, "A3_GIT_BLOB_DRIFT")
        return raw


def archived_member(reader: GitReader, tree: dict, path: str, blob: str) -> dict:
    entry = tree.get(path)
    need(entry is not None and entry[0] == "100644" and entry[1] == blob,
         "A3_ARCHIVED_MEMBER_DRIFT")
    raw = reader.blob(blob, MAX_FILE)
    return {"git_blob": blob, "sha256": digest(raw), "bytes": len(raw)}


def inspect_originals(rows: list[dict], base: dict, comparison: dict,
                      current: dict, read_blob) -> dict:
    validate_rows(rows)
    same = []
    changed = []
    missing = []
    for row in rows:
        path = row["path"]
        expected = row["git_blob_sha1"]
        original, compared = base.get(path), comparison.get(path)
        need(original is not None and compared is not None and
             original[0] in ("100644", "100755") and original == compared and
             original[1] == expected, "A3_ORIGINAL_BASELINE_OR_COMPARISON_DRIFT")
        raw = read_blob(expected, row["bytes"])
        need(type(raw) is bytes and len(raw) == row["bytes"] and
             git_blob(raw) == expected and digest(raw) == row["sha256"],
             "A3_ORIGINAL_BYTE_DIGEST_DRIFT")
        live = current.get(path)
        if live is None:
            missing.append(path)
        elif live == original:
            same.append(path)
        else:
            changed.append(path)
    return {"original_88_checked": len(rows), "current_same": len(same),
            "current_changed": len(changed), "current_missing": len(missing),
            "changed_current_paths": sorted(changed), "missing_current_paths": sorted(missing),
            "registered_88_equal_current": len(same) == len(rows),
            "current_tree_is_original_tree": (len(base) == len(current) and
                all(current.get(path) == identity for path, identity in base.items()))}


def execute(root: Path) -> dict:
    g = GitReader(root)
    source = g.run(["rev-parse", "HEAD"], 100).decode().strip()
    tree_oid = g.run(["rev-parse", "HEAD^{tree}"], 100).decode().strip()
    need(OID.fullmatch(source) is not None and OID.fullmatch(tree_oid) is not None,
         "A3_EXECUTION_IDENTITY")
    g.run(["diff-index", "--quiet", "HEAD", "--"], 256)
    current = g.tree(source)
    need(SELF in current and current[SELF][0] == "100644", "A3_AUDITOR_NOT_COMMITTED")
    own = root / SELF
    need(not own.is_symlink() and stat.S_ISREG(own.stat().st_mode) and
         git_blob(own.read_bytes()) == current[SELF][1], "A3_AUDITOR_WORKTREE_DRIFT")
    actual_tree = g.run(["rev-parse", ARCHIVE + "^{tree}"], 100).decode().strip()
    need(actual_tree == ARCHIVE_TREE, "A3_ARCHIVED_COMMIT_TREE_DRIFT")
    old = g.tree(ARCHIVE)
    docs = {name: archived_member(g, old, LOCK_DIR + name, oid)
            for name, oid in REGISTERED_DOCS.items()}
    source_members = {name: archived_member(g, old, SOURCE_DIR + name, oid)
                      for name, oid in ARCHIVE_FILES.items()}
    lock_entry = archived_member(g, old, LOCK, LOCK_BLOB)
    original_rows = decode_lock(g.blob(LOCK_BLOB, MAX_FILE))
    base, compare = g.tree(BASELINE), g.tree(COMPARISON)
    result = inspect_originals(original_rows, base, compare, current, g.blob)
    need(g.run(["rev-parse", "HEAD"], 100).decode().strip() == source and
         g.run(["rev-parse", "HEAD^{tree}"], 100).decode().strip() == tree_oid and
         git_blob(own.read_bytes()) == current[SELF][1], "A3_SOURCE_CHANGED_DURING_CHECK")
    return {"status": STATUS, "schema_version": 1,
            "execution_commit": source, "execution_tree": tree_oid,
            "original_baseline_commit": BASELINE,
            "original_comparison_commit": COMPARISON,
            "source_archive_commit": ARCHIVE, "source_archive_tree": ARCHIVE_TREE,
            "archived_lock": lock_entry, "archived_documents": docs,
            "archived_draft_source_members": source_members,
            "source_comparison": result, "source_only": True, **DENIALS}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    if not args.check:
        parser.error("--check is required for the committed source audit")
    try:
        print(json.dumps(execute(ROOT), sort_keys=True, allow_nan=False))
        return 0
    except (Rejected, OSError, ValueError, UnicodeError) as exc:
        print(json.dumps({"status": "A3_R2_T0_ARCHIVE_SOURCE_REJECTED",
                          "reason": str(exc) if isinstance(exc, Rejected) else "AUDIT_UNAVAILABLE",
                          "source_only": True, **DENIALS}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
