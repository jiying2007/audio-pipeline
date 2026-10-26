#!/usr/bin/env python3
"""F0 R2 independent 88-member source gate; NO DSP or resource experiment.

Separately checks the original T3S3 F0 lock as well as its 22 F0-only source
rows. The B3 T1 77-member readback alone is NOT an F0 source qualification.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys
import tempfile

import fe09_b3_f0_r2_source_admission as b3

HERE = Path(__file__).resolve().parent
ROOT = b3.ROOT
LOCK = "docs/research/frontend-evolution-v1/FE09_T3S3_F0_RESOURCE_PREREGISTRATION_20261024/source-lock.json"
F0_LOCK_BLOB = "54278f28e9e61c2714d0fc0581b9f6e915c9f368"
F0_BASE = "5187c5e59526d4047b3965b44c770ab21edbde9f"
F0_ID = "FE09-T3S3-F0-ACTUAL-CALL-RESOURCE-V1"
F0_MEMBER_COUNT = 88
B3_SHARED_MEMBERS = 66
F0_ONLY_MEMBERS = 22
VERSION_PROFILE_KEYS = {
    "2.3.56": frozenset(),
    "2.3.57": frozenset((b3.CMAKE, b3.RUNTIME)),
    "2.3.58": frozenset((b3.CMAKE, b3.RUNTIME, b3.PC_CORE, b3.PC_RUNTIME)),
}

class Rejected(ValueError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise Rejected(message)


def lock_schema(lock: dict, b3_lock: dict) -> tuple[list[dict], dict]:
    require(type(lock) is dict and lock.get("baseline") == F0_BASE and
            lock.get("id") == F0_ID and lock.get("file_count") == F0_MEMBER_COUNT,
            "F0_ORIGINAL_LOCK_IDENTITY_DRIFT")
    rows = lock.get("files")
    require(type(rows) is list and len(rows) == F0_MEMBER_COUNT,
            "F0_88_LOCK_MEMBER_COUNT")
    names = [row.get("path") for row in rows]
    require(len(set(names)) == F0_MEMBER_COUNT and
            all(type(name) is str and name == b3.safe_path(name).relative_to(ROOT).as_posix()
                for name in names), "F0_LOCK_DUPLICATE_OR_UNSAFE_PATH")
    require(all(type(row) is dict and
                set(row) == {"bytes", "git_blob_sha1", "path", "sha256"} and
                type(row["bytes"]) is int and row["bytes"] > 0 and
                bool(re.fullmatch(r"[0-9a-f]{40}", row["git_blob_sha1"])) and
                bool(re.fullmatch(r"[0-9a-f]{64}", row["sha256"]))
                for row in rows), "F0_LOCK_MEMBER_SHAPE")
    b3_rows = {row["path"]: row for row in b3_lock["files"]}
    overlap = set(names) & set(b3_rows)
    require(len(overlap) == B3_SHARED_MEMBERS and
            len(set(names) - overlap) == F0_ONLY_MEMBERS and
            all(all(row[k] == b3_rows[row["path"]][k]
                    for k in ("bytes", "git_blob_sha1", "sha256"))
                for row in rows if row["path"] in overlap),
            "F0_R1_SHARED_66_SOURCE_BYTES_DRIFT")
    by_name = {row["path"]: row for row in rows}
    require(set(b3.ORIGINAL_BUILD).issubset(by_name),
            "F0_VERSIONED_SOURCE_MEMBERS_MISSING")
    return rows, by_name


def check_one(data: bytes, row: dict, replacement: tuple[str, bytes] | None) -> None:
    require(type(data) is bytes, "F0_SOURCE_BYTES_REQUIRED")
    if replacement is None:
        require(len(data) == row["bytes"] and
                b3.sha256(data) == row["sha256"] and
                b3.git_blob(data) == row["git_blob_sha1"],
                "F0_UNCHANGED_SOURCE_DRIFT:" + row["path"])
    else:
        expected_blob, exact_bytes = replacement
        require(b3.git_blob(data) == expected_blob and data == exact_bytes,
                "F0_FORWARD_SOURCE_BYTES_DRIFT:" + row["path"])


def replay_expected(version: str, original: dict[str, bytes]) -> dict[str, bytes]:
    require(version in VERSION_PROFILE_KEYS, "F0_UNREGISTERED_VERSION")
    if version == "2.3.56":
        return {}
    with tempfile.TemporaryDirectory(prefix="fe09-f0-r2-forward-source-") as tmp:
        home = Path(tmp)
        for path in (b3.CMAKE, b3.RUNTIME):
            output = home / path
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_bytes(original[path])
        patch = b3.verified_patch(version)
        for args in (("apply", "--check", "--unidiff-zero", "-"),
                     ("apply", "--unidiff-zero", "-")):
            b3.git(*args, cwd=home, input_bytes=patch)
        expected = {path: (home / path).read_bytes() for path in (b3.CMAKE, b3.RUNTIME)}
        for path in expected:
            require(b3.git_blob(expected[path]) == b3.SOURCE_PROFILES[version][path],
                    "F0_FORWARD_PATCH_SOURCE_DRIFT:" + path)
        for args in (("apply", "--reverse", "--check", "--unidiff-zero", "-"),
                     ("apply", "--reverse", "--unidiff-zero", "-")):
            b3.git(*args, cwd=home, input_bytes=patch)
        require(all((home / path).read_bytes() == original[path] for path in expected),
                "F0_FORWARD_PATCH_PREIMAGE_NOT_RECOVERED")
    if version == "2.3.58":
        old_token = b"prefix=" + b"$" + b"{pcfiledir}/../.."
        new_token = b"prefix=" + b"$" + b"{pcfiledir}/@AP_PC_PREFIX_REL@"
        for path in (b3.PC_CORE, b3.PC_RUNTIME):
            require(original[path].count(old_token) == 1,
                    "F0_ORIGINAL_PKGCONFIG_TEMPLATE_DRIFT:" + path)
            expected[path] = original[path].replace(old_token, new_token)
            require(b3.git_blob(expected[path]) == b3.SOURCE_PROFILES[version][path],
                    "F0_CHANGED_PKGCONFIG_EXTRA_BYTES:" + path)
    require(set(expected) == VERSION_PROFILE_KEYS[version],
            "F0_SOURCE_EXCEPTION_SET_DRIFT")
    return expected


def verify_current(revision: str | None = None) -> dict:
    # The underlying B3 77-row check additionally validates the protected T0
    # register, exact current checkout, tracked cleanliness and compiler closure.
    upstream = b3.source_check(revision)
    head = upstream["execution_source"]
    version = upstream["candidate_version"]
    require(version in VERSION_PROFILE_KEYS, "F0_UNREGISTERED_VERSION")
    b3.git("merge-base", "--is-ancestor", F0_BASE, head)
    raw = b3.committed_bytes(LOCK)
    require(b3.git_blob(raw) == F0_LOCK_BLOB and raw == b3.worktree_bytes(LOCK),
            "F0_IMMUTABLE_88_LOCK_CHANGED")
    lock = b3.sealed_json(raw)
    _, b3_lock = b3.load_contract()
    rows, by_name = lock_schema(lock, b3_lock)
    originals = {}
    for row in rows:
        # Read every immutable predecessor file (including F0-only sources).
        previous = b3.committed_bytes(row["path"], F0_BASE)
        check_one(previous, row, None)
        if row["path"] in b3.ORIGINAL_BUILD:
            originals[row["path"]] = previous
    require(set(originals) == set(b3.ORIGINAL_BUILD), "F0_BUILD_SNAPSHOT_INCOMPLETE")
    expected = replay_expected(version, originals)
    require(set(expected) == VERSION_PROFILE_KEYS[version], "F0_ALLOWED_SOURCE_SET_DRIFT")
    # The original F0 study required all 88 member bytes; do not downgrade the
    # 22 F0-only rows to unverified archives.
    for row in rows:
        path = row["path"]
        check_one(b3.committed_bytes(path), row,
                  (b3.SOURCE_PROFILES[version][path], expected[path])
                  if path in expected else None)
    return {
        "schema_version": 1,
        "status": ("F0_R2_EXACT_SOURCE_88_VERIFIED_NOT_EXECUTED" if expected
                   else "F0_R2_ORIGINAL_88_SOURCE_VERIFIED_NOT_AN_R2_RESULT"),
        "execution_source": head, "candidate_version": version,
        "b3_t1_status": upstream["status"],
        "f0_source_lock_git_blob": F0_LOCK_BLOB,
        "f0_immutable_members": len(rows),
        "f0_shared_with_b3": B3_SHARED_MEMBERS,
        "f0_independent_only_members": F0_ONLY_MEMBERS,
        "f0_versioned_source_exceptions": len(expected),
        "f0_unchanged_source_members": len(rows) - len(expected),
        "b3_source_lock_members": upstream["immutable_source_members"],
        "b3_and_f0_dsp_executed": False,
        "device_qualified": False,
        "product_promotion": False,
        "redistribution_authorized": False,
    }


def self_test() -> dict:
    raw = b"unit\n"
    record = {"path": "fixture.c", "bytes": len(raw),
              "sha256": b3.sha256(raw), "git_blob_sha1": b3.git_blob(raw)}
    count = 0
    check_one(raw, record, None)
    for candidate in (b"unit", b"other\n", b"unit\nextra", b""):
        try:
            check_one(candidate, record, None)
        except Rejected:
            count += 1
        else:
            raise Rejected("F0_MUTATED_FROZEN_SOURCE_ACCEPTED")
    check_one(b"next\n", record, (b3.git_blob(b"next\n"), b"next\n"))
    for candidate in ((b"next\n", b3.git_blob(b"wrong\n"), b"next\n"),
                      (b"next\n", b3.git_blob(b"next\n"), b"different\n")):
        try:
            check_one(candidate[0], record, (candidate[1], candidate[2]))
        except Rejected:
            count += 1
        else:
            raise Rejected("F0_MUTATED_NEW_SOURCE_ACCEPTED")
    for forbidden in ("2.3.59", "3.0.0"):
        try:
            replay_expected(forbidden, {})
        except Rejected:
            count += 1
        else:
            raise Rejected("F0_UNKNOWN_VERSION_ACCEPTED")
    original = {"baseline": F0_BASE, "id": F0_ID,
                "file_count": F0_MEMBER_COUNT, "files": []}
    for invalid in (original, {**original, "file_count": 87}):
        try:
            lock_schema(invalid, {"files": []})
        except Rejected:
            count += 1
        else:
            raise Rejected("F0_INCOMPLETE_LOCK_ACCEPTED")
    require(count == 10, "F0_NEGATIVE_MATRIX_INCOMPLETE")
    return {"status": "F0_R2_SOURCE_NEGATIVES_PASS", "rejected": count,
            "actual_f0_processes": 0, "b3_dsp_frames": 0,
            "shipping_authority": False}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--execution-source")
    args = parser.parse_args()
    if not (args.self_test or args.check):
        parser.error("select --self-test and/or --check")
    try:
        if args.self_test:
            print(json.dumps(self_test(), sort_keys=True))
        if args.check:
            print(json.dumps(verify_current(args.execution_source), sort_keys=True))
        return 0
    except (ValueError, OSError, KeyError, TypeError) as exc:
        print("F0_R2_SOURCE_REJECTED:" + str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
