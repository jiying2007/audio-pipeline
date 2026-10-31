#!/usr/bin/env python3
"""F1-R2-T0 source reconciliation only; no F1/DSP/provider execution.

Read the archived R1 lock as data, prove its originals at D, and separately
bind the current 2.3.61 source to the protected R5 maintenance proof. Never
edit old locks or treat an old measurement as a current-source result.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import selectors
import signal
import stat
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[3]
REL = "tests/validation/frontend_evolution/"
SELF = REL + "fe09_f1_r2_source_bridge.py"
ARCHIVE = "9ac5a209b16210c7e514d57711f22c9b27354cb8"
ARCHIVE_TREE = "c957b8f835f7d3fee1707d1bda9f689013676afa"
ORIGINAL = "92a7546a75cfe0d8aca132c7ee5996dcf0005c74"
ORIGINAL_TREE = "894253393823d842f620be408ec12339a61771d2"
CURRENT_BASE = "52abb9036e4660b58c110b58b0c568fa400d94c3"
LOCK = "docs/research/frontend-evolution-v1/FE09_T3S3_F1_RSS_PREREGISTRATION_R1_20261024/source-lock.json"
LOCK_BLOB = "460c6fbabf766c249602067863ed2b195e06cd5f"
LOCK_SHA256 = "c2e4454f960bcb70e84184effd335f53a2245145d6bced77c0dbb5ed35144575"
ARCHIVED_HELPER = REL + "fe09_t3s3_f1_rss_qualification.py"
ARCHIVED_HELPER_BLOB = "26ffa7922f8425ede57780a516772eb2c4ff5682"
R5 = REL + "fe09_b3_f0_r5_source_admission.py"
R5_BLOB = "1839ca3271e7006abcf4c132a12fb7b1683a3696"
STATUS = "F1_R2_T0_SOURCE_BRIDGE_VERIFIED_NO_EXECUTION"
OLD_ID = "FE09-T3S3-F1-TARGET-LIFETIME-AND-IMAGE-RSS-R1"
MAX_FILE = 262144
MAX_RECEIPT = 100000
OID = re.compile(r"[0-9a-f]{40}")
H256 = re.compile(r"[0-9a-f]{64}")
CURRENT = {
    "CMakeLists.txt": "754a5233998a79d4c1f9e86ae4628f6c5d046550",
    "cmake/audio-pipeline-runtime.pc.in": "079ee9edf1fb9e13bfa0936355556b48ca408155",
    "cmake/audio-pipeline.pc.in": "29fbd3746b65e54c438e375815a44f076f3b255c",
    "include/audio_pipeline/audio_modules.h": "98f0dc8309d1be1f2b964bc165406fd555de3a7d",
    "include/audio_pipeline/audio_runtime.h": "ad72e40b5b343aee4589ee50dfd07fe1a85e0ea9",
    "src/modules/ap_beamformer_module.c": "c55cca0d5352b6d27066ea4a447ccaa583109411",
    "src/modules/ap_resampler_module.c": "3edc2730f7641ff7242e2666492c993e6b068439",
    "src/platform/linux/ap_runtime.c": "b6c36e195c1ac967e450a1e32506e0b6859a581b",
    "src/sync/ap_sync.c": "83b79caf78f03e9689416c8afbb1e04f444314e8",
}
DENIALS = ("f1_executed", "provider_authority_acquired", "measurement_qualified",
           "full_f1_source_closure_qualified", "workflow_hookup_admitted",
           "historical_result_inherited", "shipping_authority", "ssc305_hil_qualified")


class Rejected(ValueError):
    pass


def need(condition: bool, reason: str) -> None:
    if not condition:
        raise Rejected(reason)


def valid_oid(value: object) -> bool:
    return type(value) is str and OID.fullmatch(value) is not None and value != "0" * 40


def path_name(value: object) -> str:
    need(type(value) is str and 0 < len(value) <= 300 and
         re.fullmatch(r"[A-Za-z0-9_./-]+", value) is not None and
         not value.startswith(("/", "-")) and
         all(p not in ("", ".", "..", ".git") for p in value.split("/")) and
         PurePosixPath(value).as_posix() == value, "UNSAFE_SOURCE_PATH")
    return value


def identity(raw: bytes) -> dict:
    need(type(raw) is bytes and 0 < len(raw) <= MAX_FILE, "SOURCE_BYTES_BOUND")
    return {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest(),
            "git_blob_sha1": hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()}


def load_lock(raw: bytes) -> list[dict]:
    need(identity(raw)["git_blob_sha1"] == LOCK_BLOB and
         hashlib.sha256(raw).hexdigest() == LOCK_SHA256, "ARCHIVED_LOCK_IDENTITY_DRIFT")
    def pairs(items):
        out = {}
        for key, value in items:
            need(key not in out, "DUPLICATE_LOCK_KEY")
            out[key] = value
        return out
    def number(value):
        result = float(value)
        need(math.isfinite(result), "NONFINITE_LOCK_JSON")
        return result
    def constant(_value):
        raise Rejected("NONFINITE_LOCK_JSON")
    data = json.loads(raw.decode("utf-8"), object_pairs_hook=pairs,
                      parse_float=number, parse_constant=constant)
    need(type(data) is dict and type(data.get("schema_version")) is int and
         data["schema_version"] == 1 and data.get("id") == OLD_ID and
         data.get("execution_admitted") is False and
         data.get("source_anchor") == {"commit": ORIGINAL, "tree": ORIGINAL_TREE},
         "ORIGINAL_LOCK_AUTHORITY_DRIFT")
    rows = data.get("files")
    need(type(rows) is list and type(data.get("file_count")) is int and
         data["file_count"] == len(rows) == 109 and
         type(data.get("immutable_original_file_count")) is int and
         data["immutable_original_file_count"] == 96, "ORIGINAL_LOCK_COUNT_DRIFT")
    names = []
    originals = []
    for row in rows:
        need(type(row) is dict and type(row.get("role")) is str, "INVALID_LOCK_ROW")
        names.append(path_name(row.get("path")))
        if row["role"].startswith("IMMUTABLE_ORIGINAL"):
            need(row.get("source_commit") == ORIGINAL and
                 type(row.get("bytes")) is int and 0 < row["bytes"] <= MAX_FILE and
                 valid_oid(row.get("git_blob_sha1")) and
                 type(row.get("sha256")) is str and H256.fullmatch(row["sha256"]) is not None,
                 "INVALID_ORIGINAL_IDENTITY")
            originals.append(row)
    need(len(set(names)) == len(names) and len(originals) == 96, "ORIGINAL_LOCK_MEMBERSHIP_DRIFT")
    return originals


class Git:
    """Local object reads only; capped pipes and one per-command cleanup deadline."""
    def __init__(self, root: Path):
        self.root = root.resolve()
        forbidden = ("GIT_DIR", "GIT_WORK_TREE", "GIT_OBJECT_DIRECTORY",
                     "GIT_ALTERNATE_OBJECT_DIRECTORIES", "GIT_CONFIG_PARAMETERS",
                     "GIT_CONFIG_COUNT", "GIT_NAMESPACE", "GIT_SHALLOW_FILE",
                     "GIT_REPLACE_REF_BASE")
        need(not any(os.environ.get(k) for k in forbidden), "EXTERNAL_GIT_CONTEXT_REFUSED")
        self.env = {k: v for k, v in os.environ.items()
                    if not k.startswith("GIT_") and k not in ("GH_TOKEN", "GITHUB_TOKEN")}
        self.env.update(GIT_CONFIG_GLOBAL="/dev/null", GIT_CONFIG_SYSTEM="/dev/null",
                        GIT_CONFIG_NOSYSTEM="1", GIT_NO_REPLACE_OBJECTS="1",
                        GIT_NO_LAZY_FETCH="1", GIT_ALLOW_PROTOCOL="",
                        GIT_TERMINAL_PROMPT="0", GIT_OPTIONAL_LOCKS="0",
                        GIT_LITERAL_PATHSPECS="1")

    def run(self, args: list[str], cap: int = MAX_FILE) -> bytes:
        need(args and args[0] in ("rev-parse", "ls-tree", "cat-file", "merge-base", "diff-index"),
             "LOCAL_GIT_READ_ONLY")
        command = ["git", "--no-replace-objects", "-c", "safe.directory=" + str(self.root),
                   "-c", "protocol.allow=never", "-c", "core.hooksPath=/dev/null",
                   "-c", "core.fsmonitor=false", *args]
        end = time.monotonic() + 10
        buffers = [bytearray(), bytearray()]
        proc = subprocess.Popen(command, cwd=self.root, env=self.env, stdin=subprocess.DEVNULL,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
        done = False
        try:
            with selectors.DefaultSelector() as selected:
                for index, stream in enumerate((proc.stdout, proc.stderr)):
                    os.set_blocking(stream.fileno(), False)
                    selected.register(stream, selectors.EVENT_READ, index)
                while selected.get_map():
                    remaining = end - .5 - time.monotonic()
                    need(remaining > 0, "LOCAL_GIT_TIMEOUT")
                    for key, _ in selected.select(remaining):
                        index = key.data
                        limit = cap if index == 0 else 4096
                        try:
                            chunk = os.read(key.fileobj.fileno(), min(65536, limit - len(buffers[index]) + 1))
                        except BlockingIOError:
                            continue
                        need(len(buffers[index]) + len(chunk) <= limit, "LOCAL_GIT_OUTPUT_BOUND")
                        if chunk:
                            buffers[index].extend(chunk)
                        else:
                            selected.unregister(key.fileobj)
                need(end - .5 - time.monotonic() > 0, "LOCAL_GIT_TIMEOUT")
                code = proc.wait(timeout=end - .5 - time.monotonic())
                done = True
                need(code == 0, "LOCAL_GIT_OBJECT_OR_CONTEXT_UNAVAILABLE")
        finally:
            try:
                if not done:
                    try:
                        os.killpg(proc.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    remaining = end - time.monotonic()
                    need(remaining > 0, "LOCAL_GIT_CLEANUP_DEADLINE")
                    proc.wait(timeout=remaining)
            finally:
                proc.stdout.close()
                proc.stderr.close()
        return bytes(buffers[0])

    def oid(self, expression: str) -> str:
        value = self.run(["rev-parse", "--verify", expression], 4096).decode("ascii").strip()
        need(valid_oid(value), "INVALID_GIT_OBJECT_IDENTITY")
        return value

    def blob(self, revision: str, path: str) -> bytes:
        need(valid_oid(revision), "FULL_COMMIT_REQUIRED")
        path_name(path)
        raw = self.run(["ls-tree", "-z", revision, "--", path], 4096)
        match = re.fullmatch(rb"100644 blob ([0-9a-f]{40})\t" + re.escape(path.encode()) + b"\0", raw)
        need(match is not None, "SOURCE_MISSING_OR_MODE_DRIFT")
        oid = match[1].decode("ascii")
        size = self.run(["cat-file", "-s", oid], 64).strip()
        need(re.fullmatch(rb"[0-9]+", size) is not None and 0 < int(size) <= MAX_FILE,
             "SOURCE_BYTES_BOUND")
        content = self.run(["cat-file", "blob", oid], int(size))
        need(len(content) == int(size) and identity(content)["git_blob_sha1"] == oid,
             "GIT_BLOB_BYTES_DRIFT")
        return content

    def current(self, revision: str, path: str) -> bytes:
        content = self.blob(revision, path)
        target = self.root
        for part in path.split("/"):
            target = target / part
            need(not target.is_symlink(), "SOURCE_WORKTREE_SYMLINK")
        info = target.stat()
        need(stat.S_ISREG(info.st_mode) and not info.st_mode & 0o111 and
             info.st_size == len(content), "SOURCE_WORKTREE_MODE_OR_SIZE_DRIFT")
        with target.open("rb") as stream:
            need(stream.read(MAX_FILE + 1) == content, "SOURCE_WORKTREE_BYTES_DRIFT")
        return content


def reconcile(rows: list[dict], historical: dict[str, bytes], current: dict[str, bytes],
              proof: dict, revision: str, tree: str) -> list[dict]:
    need(valid_oid(revision) and valid_oid(tree), "CURRENT_IDENTITY_REQUIRED")
    need(type(rows) is list and len(rows) == 96 and all(type(r) is dict for r in rows),
         "ORIGINAL_COUNT_REQUIRED")
    names = [path_name(r.get("path")) for r in rows]
    need(len(set(names)) == 96 and set(historical) == set(current) == set(names) and
         set(CURRENT) <= set(names), "EXACT_96_PATH_PARTITION_REQUIRED")
    need(type(proof) is dict and proof.get("status") == "R5_T1_EXACT_SOURCE_IDENTITY_VERIFIED_NO_DSP_EXECUTION"
         and proof.get("execution_source") == revision and proof.get("execution_tree") == tree
         and proof.get("candidate_version") == "2.3.61"
         and proof.get("reviewed_source_blobs") == CURRENT
         and type(proof.get("source_delta_members_verified")) is int
         and proof["source_delta_members_verified"] == 9
         and all(proof.get(k) is False for k in ("science_executed", "shipping_authority",
             "ssc305_hil_qualified", "four_mic_public_sdk", "r1_or_r2_result_inherited",
             "r3_result_inherited", "r4_result_inherited")), "R5_CURRENT_PROOF_REQUIRED")
    result = []
    for row in sorted(rows, key=lambda r: r["path"]):
        path = row["path"]
        before, after = identity(historical[path]), identity(current[path])
        need(before == {k: row.get(k) for k in before}, "HISTORICAL_MEMBER_DRIFT")
        if path in CURRENT:
            need(after["git_blob_sha1"] == CURRENT[path] and before != after,
                 "CURRENT_REVIEWED_MEMBER_DRIFT")
            role = "R5_REVIEWED_MAINTENANCE_NOT_R1_RESULT"
        else:
            need(after == before, "UNREVIEWED_CURRENT_MEMBER_DRIFT")
            role = "BYTE_IDENTICAL_HISTORICAL_MEMBER"
        result.append({"path": path, "role": role, "historical": before, "current": after})
    return result


def load_r5(root: Path, git: Git, revision: str):
    raw = git.current(revision, R5)
    need(identity(raw)["git_blob_sha1"] == R5_BLOB, "PROTECTED_R5_HELPER_DRIFT")
    spec = importlib.util.spec_from_file_location("f1_bridge_protected_r5", root / R5)
    module = importlib.util.module_from_spec(spec)
    # The regular current helper pins its dependencies before import; archived
    # qualifier/source is NEVER imported, evaluated or passed to a shell.
    spec.loader.exec_module(module)
    return module.source_check(revision)


def check(root: Path = ROOT) -> dict:
    git = Git(root)
    need(git.run(["rev-parse", "--is-shallow-repository"], 64).strip() == b"false",
         "COMPLETE_LOCAL_HISTORY_REQUIRED")
    grafts = git.run(["rev-parse", "--git-path", "info/grafts"], 4096).decode().strip()
    need(not (root / grafts).exists(), "GRAFTED_HISTORY_REFUSED")
    revision, tree = git.oid("HEAD^{commit}"), git.oid("HEAD^{tree}")
    git.run(["diff-index", "--quiet", "HEAD", "--"], 4096)
    git.run(["merge-base", "--is-ancestor", CURRENT_BASE, revision], 4096)
    need(git.oid(ARCHIVE + "^{tree}") == ARCHIVE_TREE and
         git.oid(ORIGINAL + "^{tree}") == ORIGINAL_TREE, "HISTORICAL_TREE_DRIFT")
    git.current(revision, SELF)
    lock_raw = git.blob(ARCHIVE, LOCK)
    rows = load_lock(lock_raw)
    need(identity(git.blob(ARCHIVE, ARCHIVED_HELPER))["git_blob_sha1"] == ARCHIVED_HELPER_BLOB,
         "LATEST_ARCHIVE_HELPER_DRIFT")
    proof = load_r5(root, git, revision)
    historical = {r["path"]: git.blob(ORIGINAL, r["path"]) for r in rows}
    current = {r["path"]: git.current(revision, r["path"]) for r in rows}
    members = reconcile(rows, historical, current, proof, revision, tree)
    need(git.oid("HEAD^{commit}") == revision and git.oid("HEAD^{tree}") == tree,
         "SOURCE_MOVED_DURING_CHECK")
    git.run(["diff-index", "--quiet", "HEAD", "--"], 4096)
    return {"schema_version": 1, "status": STATUS, "execution_source": revision,
            "execution_tree": tree, "archive_commit": ARCHIVE, "original_commit": ORIGINAL,
            "original_lock_blob": LOCK_BLOB, "original_lock_sha256": LOCK_SHA256,
            "archived_helper_blob": ARCHIVED_HELPER_BLOB, "current_r5_helper_blob": R5_BLOB,
            "historical_members": 96, "unchanged_current_members": 87,
            "separately_reviewed_current_members": 9, "r5_source_proof": proof,
            "members": members, **dict.fromkeys(DENIALS, False),
            "scope": "96 original dependencies only; not the complete future F1 build or workflow closure"}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    try:
        result = check()
        raw = (json.dumps(result, sort_keys=True, indent=2, allow_nan=False) + "\n").encode()
        need(len(raw) <= MAX_RECEIPT, "SOURCE_RECEIPT_BOUND")
        if args.output is not None:
            with args.output.open("xb") as stream:
                need(stream.write(raw) == len(raw), "SOURCE_RECEIPT_SHORT_WRITE")
        summary = {k: result[k] for k in ("status", "execution_source", "historical_members",
                   "unchanged_current_members", "separately_reviewed_current_members", *DENIALS)}
        summary["receipt_sha256"] = hashlib.sha256(raw).hexdigest()
        print(json.dumps(summary, sort_keys=True))
        return 0
    except (ValueError, OSError, UnicodeError, KeyError, TypeError, subprocess.SubprocessError) as error:
        reason = str(error)
        print(json.dumps({"status": "F1_R2_T0_REJECTED", **dict.fromkeys(DENIALS, False),
                          "reason": reason if re.fullmatch(r"[A-Z0-9_]{1,100}", reason)
                          else "SOURCE_OR_RECEIPT_UNAVAILABLE"}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
