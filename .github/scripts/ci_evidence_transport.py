#!/usr/bin/env python3
"""Lossless run-scoped evidence transport; never scientific admission.

Only the representation changes. Every original path, byte and permission is
restored before the existing independent scientific validators run.
"""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import resource
import shutil
import signal
import stat
import sys
import tempfile
import time
import zipfile

SCHEMA = "audio-pipeline-evidence-cas-v1"
CHUNK = 1024 * 1024
MAX_FILES = 24000
MAX_LOGICAL_BYTES = 2_000_000_000
MAX_FILE_BYTES = 64 * 1024 * 1024
MAX_MANIFEST_BYTES = 8 * 1024 * 1024
MAX_RECEIPT_BYTES = 32 * 1024
STAGE_SECONDS = 180
MEMORY_BYTES = 256 * 1024 * 1024
SHA = re.compile(r"[0-9a-f]{64}")
SOURCE = re.compile(r"[0-9a-f]{40}")
RUN = re.compile(r"(?:[1-9][0-9]{0,19}|local-[a-z0-9-]{1,48})")


class TransportError(ValueError):
    pass


def need(condition, reason):
    if not condition:
        raise TransportError(reason)


def canonical(value):
    return (json.dumps(value, sort_keys=True, separators=(",", ":"),
                       ensure_ascii=True, allow_nan=False) + "\n").encode("utf-8")


def strict_pairs(pairs):
    value = {}
    for key, item in pairs:
        need(key not in value, "DUPLICATE_MANIFEST_KEY")
        value[key] = item
    return value


def parse_json(raw, limit):
    need(0 < len(raw) <= limit, "METADATA_SIZE_LIMIT")
    def invalid_constant(value):
        raise TransportError("NONFINITE_MANIFEST_VALUE")
    value = json.loads(raw, object_pairs_hook=strict_pairs,
                       parse_constant=invalid_constant)
    need(type(value) is dict and canonical(value) == raw,
         "NONCANONICAL_TRANSPORT_METADATA")
    return value


def safe_name(name):
    need(type(name) is str and 0 < len(name.encode("utf-8")) <= 240 and
         not any(ord(c) < 32 or ord(c) == 127 for c in name) and
         "\\" not in name and ":" not in name and
         not PurePosixPath(name).is_absolute() and
         all(p not in ("", ".", "..") for p in name.split("/")) and
         len(name.split("/")) <= 20, "UNSAFE_EVIDENCE_PATH")
    return name


def valid_mode(mode):
    need(type(mode) is int and 0 <= mode <= 0o777, "UNSAFE_EVIDENCE_MODE")


def digest_file(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(CHUNK), b""):
            h.update(block)
    return h.hexdigest()


def inventory(root):
    need(root.is_dir() and not root.is_symlink(), "EVIDENCE_ROOT_NOT_DIRECTORY")
    files, directories, logical = [], [], 0
    for path in root.rglob("*"):
        entry = path.lstat()
        name = safe_name(path.relative_to(root).as_posix())
        mode = stat.S_IMODE(entry.st_mode)
        valid_mode(mode)
        if stat.S_ISDIR(entry.st_mode):
            directories.append({"path": name, "mode": mode})
            need(len(directories) <= MAX_FILES, "DIRECTORY_COUNT_LIMIT")
            continue
        need(stat.S_ISREG(entry.st_mode), "NONREGULAR_EVIDENCE_FILE")
        need(0 <= entry.st_size <= MAX_FILE_BYTES, "FILE_SIZE_LIMIT")
        logical += entry.st_size
        need(logical <= MAX_LOGICAL_BYTES and len(files) < MAX_FILES,
             "LOGICAL_TREE_LIMIT")
        digest = digest_file(path)
        after = path.lstat()
        need((entry.st_dev, entry.st_ino, entry.st_size, entry.st_mtime_ns, entry.st_mode) ==
             (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_mode),
             "SOURCE_CHANGED_DURING_INVENTORY")
        files.append({"path": name, "mode": mode, "bytes": entry.st_size, "sha256": digest})
    need(files, "EMPTY_EVIDENCE_TREE")
    return sorted(files, key=lambda row: row["path"]), sorted(directories, key=lambda row: row["path"])


def validate_manifest(value, source, run):
    need(set(value) == {"schema", "execution_source", "run_id", "tool_sha256",
                       "authority", "files", "directories", "logical_bytes", "unique_bytes"},
         "MANIFEST_SCHEMA_FIELDS")
    need(value["schema"] == SCHEMA and value["authority"] == "BYTE_TRANSPORT_ONLY" and
         SOURCE.fullmatch(source) and RUN.fullmatch(run) and
         value["execution_source"] == source and value["run_id"] == run and
         type(value["tool_sha256"]) is str and SHA.fullmatch(value["tool_sha256"]),
         "RUN_SOURCE_OR_AUTHORITY_MISMATCH")
    files, directories = value["files"], value["directories"]
    need(type(files) is list and 0 < len(files) <= MAX_FILES and
         type(directories) is list and len(directories) <= MAX_FILES,
         "MANIFEST_ENTRY_COUNT_LIMIT")
    paths, dirs, groups = set(), set(), {}
    logical = 0
    for row in directories:
        need(type(row) is dict and set(row) == {"path", "mode"}, "DIRECTORY_RECORD_SHAPE")
        name = safe_name(row["path"]); valid_mode(row["mode"])
        need(name not in dirs, "DUPLICATE_DIRECTORY_PATH")
        dirs.add(name)
    for row in files:
        need(type(row) is dict and set(row) == {"path", "mode", "bytes", "sha256"},
             "FILE_RECORD_SHAPE")
        name = safe_name(row["path"]); valid_mode(row["mode"])
        need(name not in paths and name not in dirs, "DUPLICATE_OR_CONFLICTING_FILE_PATH")
        need(type(row["bytes"]) is int and 0 <= row["bytes"] <= MAX_FILE_BYTES and
             type(row["sha256"]) is str and SHA.fullmatch(row["sha256"]),
             "FILE_SIZE_OR_DIGEST_INVALID")
        paths.add(name); logical += row["bytes"]
        need(logical <= MAX_LOGICAL_BYTES, "LOGICAL_TREE_LIMIT")
        group = groups.setdefault(row["sha256"], [])
        need(not group or group[0]["bytes"] == row["bytes"], "ONE_DIGEST_MULTIPLE_SIZES")
        group.append(row)
    for name in paths | dirs:
        parent = PurePosixPath(name).parent.as_posix()
        need(parent == "." or parent in dirs, "UNLISTED_OR_FILE_PARENT")
    need(files == sorted(files, key=lambda row: row["path"]) and
         directories == sorted(directories, key=lambda row: row["path"]),
         "UNSORTED_TRANSPORT_MANIFEST")
    need(type(value["logical_bytes"]) is int and value["logical_bytes"] == logical and
         type(value["unique_bytes"]) is int and
         value["unique_bytes"] == sum(rows[0]["bytes"] for rows in groups.values()),
         "MANIFEST_TOTAL_MISMATCH")
    return groups


def fresh_output(path):
    need(path.parent.is_dir() and not path.parent.is_symlink() and
         not path.exists() and not path.is_symlink(), "OUTPUT_NOT_FRESH")


def zip_info(name):
    item = zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0))
    item.external_attr = (stat.S_IFREG | 0o644) << 16
    item.compress_type = zipfile.ZIP_DEFLATED
    item._compresslevel = 6
    return item


def pack(root, output, source, run):
    fresh_output(output)
    need(not output.resolve().is_relative_to(root.resolve()), "OUTPUT_INSIDE_EVIDENCE")
    files, directories = inventory(root)
    groups = {}
    for row in files:
        groups.setdefault(row["sha256"], []).append(row)
    value = {"schema": SCHEMA, "execution_source": source, "run_id": run,
             "tool_sha256": digest_file(Path(__file__)), "authority": "BYTE_TRANSPORT_ONLY",
             "files": files, "directories": directories,
             "logical_bytes": sum(row["bytes"] for row in files),
             "unique_bytes": sum(rows[0]["bytes"] for rows in groups.values())}
    validate_manifest(value, source, run)
    raw = canonical(value)
    need(len(raw) <= MAX_MANIFEST_BYTES, "METADATA_SIZE_LIMIT")
    with tempfile.TemporaryDirectory(prefix="evidence-pack-", dir=output.parent) as temp:
        area = Path(temp) / "bundle"; area.mkdir()
        archive = area / "evidence.zip"
        with zipfile.ZipFile(archive, "x", compression=zipfile.ZIP_DEFLATED,
                             compresslevel=6, allowZip64=False) as target:
            target.writestr(zip_info("manifest.json"), raw)
            for digest, rows in sorted(groups.items()):
                row = rows[0]; count = 0; hashed = hashlib.sha256()
                with (root / row["path"]).open("rb") as inp, \
                        target.open(zip_info("objects/" + digest), "w") as out:
                    for block in iter(lambda: inp.read(CHUNK), b""):
                        count += len(block)
                        need(count <= row["bytes"], "SOURCE_CHANGED_DURING_PACK")
                        hashed.update(block); out.write(block)
                need(count == row["bytes"] and hashed.hexdigest() == digest,
                     "SOURCE_CHANGED_DURING_PACK")
            compressed = {digest: target.getinfo("objects/" + digest).compress_size
                          for digest in groups}
        # A fresh DEFLATE stream for identical bytes has the same compressed
        # size. Include all ordinary per-path local/central headers and EOCD.
        ordinary_size = 22 + sum(compressed[row["sha256"]] + 76 +
                                  2 * len(row["path"].encode("utf-8")) for row in files)
        need(archive.stat().st_size <= ordinary_size, "COMPRESSED_SIZE_REGRESSION")
        # Detect changed/added/deleted files, including a nonrepresentative copy.
        need(inventory(root) == (files, directories), "SOURCE_CHANGED_DURING_PACK")
        record = {"schema": SCHEMA, "authority": "BYTE_TRANSPORT_ONLY",
                  "execution_source": source, "run_id": run,
                  "manifest_sha256": hashlib.sha256(raw).hexdigest(),
                  "archive_sha256": digest_file(archive), "archive_bytes": archive.stat().st_size,
                  "files": len(files), "unique_blobs": len(groups),
                  "logical_bytes": value["logical_bytes"], "unique_bytes": value["unique_bytes"],
                  "equivalent_regular_zip_bytes": ordinary_size,
                  "wire_or_billing_measurement": False}
        receipt_bytes = canonical(record)
        need(len(receipt_bytes) <= MAX_RECEIPT_BYTES and
             archive.stat().st_size + len(receipt_bytes) <= ordinary_size,
             "COMPRESSED_SIZE_REGRESSION")
        (area / "transport.json").write_bytes(receipt_bytes)
        fresh_output(output); area.rename(output)
    return record


def unpack(bundle, output, source, run):
    fresh_output(output)
    need(bundle.is_dir() and not bundle.is_symlink() and
         {p.name for p in bundle.iterdir()} == {"evidence.zip", "transport.json"},
         "BUNDLE_MEMBERSHIP_MISMATCH")
    archive, receipt = bundle / "evidence.zip", bundle / "transport.json"
    for path, limit in ((archive, MAX_LOGICAL_BYTES + MAX_MANIFEST_BYTES),
                        (receipt, MAX_RECEIPT_BYTES)):
        need(path.is_file() and not path.is_symlink() and 0 < path.stat().st_size <= limit,
             "BUNDLE_FILE_OR_SIZE_INVALID")
    record = parse_json(receipt.read_bytes(), MAX_RECEIPT_BYTES)
    need(set(record) == {"schema", "authority", "execution_source", "run_id",
                         "manifest_sha256", "archive_sha256", "archive_bytes",
                         "files", "unique_blobs", "logical_bytes", "unique_bytes",
                         "equivalent_regular_zip_bytes", "wire_or_billing_measurement"},
         "SIDECAR_SCHEMA_FIELDS")
    need(record.get("schema") == SCHEMA and record.get("authority") == "BYTE_TRANSPORT_ONLY" and
         record.get("execution_source") == source and record.get("run_id") == run and
         record.get("wire_or_billing_measurement") is False and
         type(record.get("archive_bytes")) is int and record["archive_bytes"] == archive.stat().st_size and
         record.get("archive_sha256") == digest_file(archive), "BUNDLE_RECEIPT_OR_HASH_MISMATCH")
    with zipfile.ZipFile(archive) as z:
        entries = z.infolist()
        need(0 < len(entries) <= MAX_FILES + 1 and not z.comment,
             "ZIP_ENTRY_COUNT_OR_COMMENT")
        seen = set()
        for item in entries:
            need(item.filename not in seen, "DUPLICATE_ZIP_MEMBER")
            seen.add(item.filename)
            need(not item.is_dir() and stat.S_IFMT(item.external_attr >> 16) == stat.S_IFREG and
                 not item.flag_bits & 1 and item.compress_type == zipfile.ZIP_DEFLATED and
                 (item.filename == "manifest.json" or
                  re.fullmatch(r"objects/[0-9a-f]{64}", item.filename)),
                 "ZIP_MEMBER_TYPE_PATH_OR_ENCODING")
            need(0 <= item.file_size <= MAX_FILE_BYTES, "ZIP_MEMBER_SIZE_LIMIT")
        need("manifest.json" in seen and
             0 < z.getinfo("manifest.json").file_size <= MAX_MANIFEST_BYTES,
             "MANIFEST_MISSING_OR_UNBOUNDED")
        raw = z.read("manifest.json")
        need(hashlib.sha256(raw).hexdigest() == record.get("manifest_sha256"),
             "MANIFEST_DIGEST_MISMATCH")
        value = parse_json(raw, MAX_MANIFEST_BYTES)
        groups = validate_manifest(value, source, run)
        need(seen == {"manifest.json"} | {"objects/" + d for d in groups},
             "UNEXPECTED_OR_MISSING_OBJECT")
        need(all(type(record.get(k)) is int and record[k] == v for k, v in {
            "files": len(value["files"]), "unique_blobs": len(groups),
            "logical_bytes": value["logical_bytes"], "unique_bytes": value["unique_bytes"]}.items()),
             "SIDECAR_MANIFEST_TOTAL_MISMATCH")
        ordinary_size = 22 + sum(z.getinfo("objects/" + row["sha256"]).compress_size +
            76 + 2 * len(row["path"].encode("utf-8")) for row in value["files"])
        need(type(record.get("equivalent_regular_zip_bytes")) is int and
             record["equivalent_regular_zip_bytes"] == ordinary_size and
             archive.stat().st_size + receipt.stat().st_size <= ordinary_size,
             "COMPRESSED_SIZE_REGRESSION")
        with tempfile.TemporaryDirectory(prefix="evidence-unpack-", dir=output.parent) as temp:
            area = Path(temp) / "evidence"; area.mkdir()
            for row in value["directories"]:
                (area / row["path"]).mkdir()
            for digest, rows in groups.items():
                item = z.getinfo("objects/" + digest)
                need(item.file_size == rows[0]["bytes"], "OBJECT_DECLARED_SIZE_MISMATCH")
                first = area / rows[0]["path"]; count = 0; h = hashlib.sha256()
                with z.open(item) as inp, first.open("xb") as out:
                    for block in iter(lambda: inp.read(CHUNK), b""):
                        count += len(block); need(count <= rows[0]["bytes"], "OBJECT_SIZE_OVERFLOW")
                        h.update(block); out.write(block)
                need(count == rows[0]["bytes"] and h.hexdigest() == digest, "OBJECT_HASH_OR_SIZE_MISMATCH")
                for row in rows[1:]:
                    with first.open("rb") as inp, (area / row["path"]).open("xb") as out:
                        shutil.copyfileobj(inp, out, CHUNK)
                for row in rows:
                    (area / row["path"]).chmod(row["mode"])
            # Directory permissions are applied after their children are written.
            for row in reversed(value["directories"]):
                (area / row["path"]).chmod(row["mode"])
            need(inventory(area) == (value["files"], value["directories"]),
                 "RESTORED_TREE_READBACK_MISMATCH")
            fresh_output(output); area.rename(output)
    return record


@contextlib.contextmanager
def wall_budget():
    def expired(signum, frame):
        raise TransportError("TRANSPORT_WALL_DEADLINE")
    previous = signal.signal(signal.SIGALRM, expired)
    signal.setitimer(signal.ITIMER_REAL, STAGE_SECONDS)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("pack", "unpack"))
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--execution-source", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--failure-file", type=Path)
    args = parser.parse_args(); started = time.monotonic()
    try:
        need(sys.platform.startswith("linux"), "LINUX_TRANSPORT_REQUIRED")
        soft, hard = resource.getrlimit(resource.RLIMIT_AS)
        limit = min(MEMORY_BYTES, hard) if hard != resource.RLIM_INFINITY else MEMORY_BYTES
        if soft != resource.RLIM_INFINITY:
            limit = min(limit, soft)
        resource.setrlimit(resource.RLIMIT_AS, (limit, hard))
        with wall_budget():
            operation = pack if args.mode == "pack" else unpack
            record = operation(args.input, args.output, args.execution_source, args.run_id)
        print(json.dumps({"status": "EXACT_FILE_BYTES_TRANSPORTED", "mode": args.mode,
                          "elapsed_seconds": round(time.monotonic() - started, 3), **record}, sort_keys=True))
        return 0
    except Exception as error:
        reason = str(error) if isinstance(error, TransportError) else type(error).__name__
        if args.failure_file is not None and not args.failure_file.is_symlink():
            try:
                args.failure_file.parent.mkdir(parents=True, exist_ok=True)
                with args.failure_file.open("xb") as out:
                    out.write(canonical({"schema": SCHEMA, "status": "TRANSPORT_FAILED",
                        "reason": reason[:160], "source_substitution": False,
                        "scientific_validation_passed": False}))
            except OSError:
                pass
        print("EVIDENCE_TRANSPORT_FAILED: " + reason[:160], file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
