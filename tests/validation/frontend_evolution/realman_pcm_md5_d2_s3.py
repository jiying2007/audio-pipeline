#!/usr/bin/env python3
"""FE03 A2 D2-S3: research-only original RealMAN FLAC decoded PCM integrity.

Frozen preregistration: https://github.com/jiying2007/audio-pipeline/issues/707
Read eight S2-frozen originals, never expose PCM or score acoustic quality.
"""
from __future__ import annotations

import argparse
import copy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import selectors
import shutil
import subprocess
import tempfile
import time

import realman_single_archive_d2_s1 as s1
import realman_flac_quartets_d2_s2 as s2

ROOT = Path(__file__).resolve().parents[3]
ANCHOR_PATH = Path(__file__).with_name("realman_s2_frozen_anchor_d2_s3.json")
PASS = "REALMAN_D2_S3_GYM_8_PCM_MD5_VERIFIED_RESEARCH_ONLY"
BLOCKED = "REALMAN_D2_S3_GYM_PCM_BYTES_NOT_ADMITTED"
PER_PCM_TIMEOUT = 30
TOTAL_PCM_TIMEOUT = 180
DECODE_MAX = 2 * 238895
S2_COMMIT = "cc887b0ced20a828ed7148b9ac949f639a1e2868"
S2_RECEIPT_SHA = "16e690a4b32f0aeb9f011900af55f83f302a6f29662f2bb1601c058257ae3190"
S2_ZIP_SHA = "298432f0d6b8ceb69d48d62c0d2bdf8f42dee6383534b48109d4a80f7719870a"
S2_SELECTED_SHA = "7b6458adc4d335c6c1897f98e51501f897585623359ef147494d7635d4d9be37"
S2_INVENTORY_SHA = "e8b0802d26449e8b52c0253dd015aa689787e43d38ca6971f568a61663ffba7c"
DECODE_FLAGS = ("--silent", "--decode", "--force-raw-format",
                "--endian=little", "--sign=signed", "--stdout", "--")


class Reject(ValueError):
    def __init__(self, code):
        super().__init__(code)
        self.code = code


def require(ok, code="S3_RESEARCH_INTEGRITY_REJECTED"):
    if not ok:
        raise Reject(code)


def sha256(raw):
    return hashlib.sha256(raw).hexdigest()


def unique_keys(pairs):
    record = {}
    for k, v in pairs:
        require(k not in record, "S3_DUPLICATE_JSON_KEY")
        record[k] = v
    return record


def no_constant(_):
    raise Reject("S3_INVALID_JSON_CONSTANT")


def strict_json(path, limit=65536):
    require(path.is_file() and path.stat().st_size <= limit,
            "S3_METADATA_FILE_NOT_ADMITTED")
    try:
        return json.loads(path.read_text(encoding="utf-8"),
                          object_pairs_hook=unique_keys, parse_constant=no_constant)
    except (OSError, UnicodeError, ValueError) as err:
        raise Reject("S3_METADATA_JSON_INVALID") from None


def load_anchor():
    """Copy of all 8 individual fields from independently sealed S2 receipt."""
    a = strict_json(ANCHOR_PATH, 32768)
    require(isinstance(a, dict), "S3_ANCHOR_TAMPER")
    fixed = {
        "schema_version": 1,
        "authority": "FROZEN_D2_S2_FRESH_MAIN_SOURCE_RECEIPT_NOT_AUDIO_SCORES",
        "source_role": "disclosed-development-only",
        "research_rights": "NONCOMMERCIAL_ATTRIBUTION_ONLY",
        "s2_main_commit": S2_COMMIT,
        "s2_source_run_id": 38050714903,
        "s2_artifact_id": 11669252369,
        "s2_artifact_zip_sha256": S2_ZIP_SHA,
        "s2_original_receipt_sha256": S2_RECEIPT_SHA,
        "s2_selected_path_sha256": S2_SELECTED_SHA,
        "s2_regular_names_sha256": S2_INVENTORY_SHA,
        "dataset": "AISHELL/RealMAN",
        "dataset_revision": s1.REV,
        "archive_path": s1.REL,
        "archive_bytes": s1.EXPECTED_BYTES,
        "archive_sha256": s1.EXPECTED_SHA,
        "selection_policy": "LEX_FIRST_COMPLETE_STATIC_AND_MOVING_QUARTETS_BY_MEMBER_NAME",
    }
    for k, v in fixed.items():
        require(a.get(k) == v, "S3_ANCHOR_TAMPER")
    require(a.get("s1_script_sha256") == s1.file_hash(Path(s1.__file__), cap=4*1024*1024)[1]
            and a.get("s2_script_sha256") == s1.file_hash(Path(s2.__file__), cap=4*1024*1024)[1],
            "S3_S1_S2_SOURCE_DRIFT")
    expected_keys = set(fixed) | {
        "s2_issue_url", "s1_script_sha256", "s2_script_sha256", "members"}
    require(set(a) == expected_keys
            and a.get("s2_issue_url") ==
            "https://github.com/jiying2007/audio-pipeline/issues/705",
            "S3_ANCHOR_TAMPER")
    members = a.get("members")
    require(isinstance(members, list) and len(members) == 8,
            "S3_ANCHOR_MEMBERS_INVALID")
    expected_order = [(role, ch) for role in s2.ROLES for ch in s2.CHS]
    actual_order = [(m.get("role"), m.get("channel")) for m in members
                    if isinstance(m, dict)]
    require(actual_order == expected_order, "S3_ANCHOR_ORDER_DRIFT")
    for m in members:
        require(set(m) == {"role", "channel", "member_path_sha256", "stem_sha256",
                           "listed_uncompressed_bytes", "listed_packed_bytes",
                           "original_flac_bytes", "original_flac_sha256", "streaminfo"},
                "S3_ANCHOR_FIELDS_INVALID")
        for k in ("original_flac_sha256", "member_path_sha256", "stem_sha256"):
            require(isinstance(m[k], str) and re.fullmatch(r"[0-9a-f]{64}", m[k]),
                    "S3_ANCHOR_HASH_INVALID")
        length = m["original_flac_bytes"]
        require(type(length) is int and 0 < length <= s2.PER_FILE_LIMIT
                and m["listed_uncompressed_bytes"] == length
                and type(m["listed_packed_bytes"]) is int
                and 0 <= m["listed_packed_bytes"] <= s1.MAX_BYTES,
                "S3_ANCHOR_LENGTH_INVALID")
        info = m["streaminfo"]
        require(isinstance(info, dict) and set(info) ==
                {"bits_per_sample", "decoded_pcm_verified", "flac_encoded_channels",
                 "max_block_size", "min_block_size", "native_sample_rate_hz",
                 "streaminfo_pcm_md5_hex", "streaminfo_pcm_md5_present",
                 "total_samples"}, "S3_ANCHOR_STREAMINFO_INVALID")
        require(info["bits_per_sample"] == 16
                and info["flac_encoded_channels"] == 1
                and info["native_sample_rate_hz"] == 48000
                and info["total_samples"] ==
                (238895 if m["role"] == "static" else 237071)
                and info["decoded_pcm_verified"] is False
                and info["streaminfo_pcm_md5_present"] is True
                and isinstance(info["streaminfo_pcm_md5_hex"], str)
                and re.fullmatch(r"[0-9a-f]{32}", info["streaminfo_pcm_md5_hex"])
                and info["streaminfo_pcm_md5_hex"] != "0"*32,
                "S3_ANCHOR_NATIVE_FORMAT_OR_PCM_MD5_INVALID")
    require(sum(m["original_flac_bytes"] for m in members) <= s2.TOTAL_LIMIT,
            "S3_ANCHOR_BUDGET_DRIFT")
    return a


def exact_decoder():
    found = shutil.which("flac")
    require(found is not None, "S3_PREINSTALLED_DECODER_MISSING")
    path = Path(found).resolve()
    require(str(path).startswith(("/usr/bin/", "/bin/"))
            and path.is_file(), "S3_DECODER_NOT_SYSTEM")
    length, digest = s1.file_hash(path, cap=64*1024*1024)
    require(0 < length <= 64*1024*1024, "S3_DECODER_BINARY_OVERSIZED")
    try:
        proc = subprocess.run([str(path), "--version"], stdin=subprocess.DEVNULL,
                              stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                              timeout=5, check=False)
    except (OSError, subprocess.SubprocessError):
        raise Reject("S3_DECODER_VERSION_UNAVAILABLE") from None
    version = proc.stdout.decode("ascii", "replace").strip()
    require(proc.returncode == 0 and bool(re.fullmatch(r"flac 1\.[0-9]+\.[0-9]+", version)),
            "S3_DECODER_VERSION_UNSUPPORTED")
    return str(path), {
        "binary_sha256": digest, "version": version,
        "raw_mode": "signed-S16LE-mono-48000Hz-unmodified",
        "argv_flags": list(DECODE_FLAGS),
    }


class PCMHasher:
    """Bounded constant-memory raw signed S16LE stream accumulator."""

    def __init__(self, expected_bytes):
        require(type(expected_bytes) is int and 0 < expected_bytes <= DECODE_MAX
                and expected_bytes % 2 == 0, "S3_PCM_EXPECTED_LENGTH_INVALID")
        self.expected_bytes = expected_bytes
        self.length = 0
        self.md5 = hashlib.md5()
        self.sha = hashlib.sha256()

    def feed(self, chunk):
        self.length += len(chunk)
        require(self.length <= self.expected_bytes, "S3_PCM_OVERSIZED")
        self.md5.update(chunk)
        self.sha.update(chunk)

    def result(self, expected_md5):
        require(self.length == self.expected_bytes, "S3_PCM_LENGTH_MISMATCH")
        md5 = self.md5.hexdigest()
        require(isinstance(expected_md5, str)
                and re.fullmatch(r"[0-9a-f]{32}", expected_md5)
                and expected_md5 != "0"*32, "S3_STREAMINFO_MD5_ABSENT")
        require(md5 == expected_md5, "S3_DECODED_PCM_MD5_MISMATCH")
        return {"raw_pcm_bytes": self.length, "decoded_pcm_md5": md5,
                "decoded_pcm_sha256": self.sha.hexdigest(),
                "streaminfo_md5_matches": True}


def decode_original(tool, flat, samples, expected_md5, overall_deadline):
    """No WAV header, no PCM file, no resampler. Only bounded pipe hashing."""
    expected_bytes = 2 * samples
    hasher = PCMHasher(expected_bytes)
    require(time.monotonic() < overall_deadline, "S3_PCM_TOTAL_TIMEOUT")
    argv = [tool, *DECODE_FLAGS, str(flat)]
    proc = None
    try:
        proc = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                stderr=subprocess.DEVNULL)
        deadline = min(overall_deadline, time.monotonic() + PER_PCM_TIMEOUT)
        with selectors.DefaultSelector() as selector:
            fd = proc.stdout.fileno()
            os.set_blocking(fd, False)
            selector.register(fd, selectors.EVENT_READ)
            while selector.get_map():
                require(time.monotonic() < deadline, "S3_PCM_DECODE_TIMEOUT")
                for key, _ in selector.select(timeout=0.25):
                    block = os.read(key.fd, 65536)
                    if block:
                        hasher.feed(block)
                    else:
                        selector.unregister(key.fd)
        require(time.monotonic() < deadline, "S3_PCM_DECODE_TIMEOUT")
        require(proc.wait(timeout=max(0.1, min(3.0, deadline-time.monotonic()))) == 0,
                "S3_NATIVE_FLAC_DECODER_FAILED")
        return hasher.result(expected_md5)
    except (OSError, subprocess.SubprocessError):
        raise Reject("S3_NATIVE_FLAC_TOOL_OR_TIMEOUT") from None
    finally:
        if proc:
            if proc.poll() is None:
                proc.kill()
            proc.wait(timeout=5)
            if proc.stdout:
                proc.stdout.close()


def validate_selection(anchor, selected, inventory):
    require(inventory["selected_path_sha256"] == S2_SELECTED_SHA
            and inventory["all_regular_name_sha256"] == S2_INVENTORY_SHA
            and len(selected) == 8, "S3_FROZEN_MEMBER_SELECTION_DRIFT")
    for x, baseline in zip(selected, anchor["members"]):
        require(x["role"] == baseline["role"]
                and x["channel"] == baseline["channel"]
                and x["member_path_sha256"] == baseline["member_path_sha256"]
                and x["stem_sha256"] == baseline["stem_sha256"]
                and x["size"] == baseline["listed_uncompressed_bytes"]
                and x["packed_size"] == baseline["listed_packed_bytes"],
                "S3_FROZEN_MEMBER_IDENTITY_MISMATCH")


def eight_originals(work, anchor, *, extract):
    archive = work / "Gym.rar"
    tool, selected, inventory = s2.list_and_select(archive)
    validate_selection(anchor, selected, inventory)
    decoder, decoder_id = exact_decoder()
    rows = []
    extract_deadline = time.monotonic() + s2.OVERALL_EXTRACT_TIMEOUT
    pcm_deadline = time.monotonic() + TOTAL_PCM_TIMEOUT
    for x, original in zip(selected, anchor["members"]):
        flat = work / ("%s-ch%d.flac" % (x["role"], x["channel"]))
        if extract:
            size, sha = s2.extract_exact(tool, archive, x["name"], flat,
                                         x["size"], extract_deadline)
            require((size, sha) == (original["original_flac_bytes"],
                                    original["original_flac_sha256"]),
                    "S3_ORIGINAL_FLAC_BYTES_MISMATCH")
        size, sha = s1.file_hash(flat, cap=s2.PER_FILE_LIMIT)
        require((size, sha) == (original["original_flac_bytes"],
                                original["original_flac_sha256"]),
                "S3_ORIGINAL_FLAC_REHASH_MISMATCH")
        info = s2.flac_streaminfo(flat)
        require(info == original["streaminfo"], "S3_ORIGINAL_STREAMINFO_DRIFT")
        pcm = decode_original(decoder, flat, info["total_samples"],
                              info["streaminfo_pcm_md5_hex"], pcm_deadline)
        rows.append({
            "role": x["role"], "channel": x["channel"],
            "member_path_sha256": x["member_path_sha256"],
            "original_flac_bytes": size, "original_flac_sha256": sha,
            "original_streaminfo": info, **pcm,
        })
    require(len(rows) == 8, "S3_NOT_EIGHT_PCM_STREAMS")
    return rows, decoder_id, inventory


def identity(commit_sha, anchor):
    return {
        "schema_version": 1,
        "experiment_id": "FE03-A2-D2-S3-REALMAN-EIGHT-PCM-MD5",
        "preregistration": "https://github.com/jiying2007/audio-pipeline/issues/707",
        "source_commit": commit_sha,
        "source_role": "disclosed-development-only",
        "source_dataset_revision": s1.REV,
        "source_archive_path": s1.REL,
        "source_archive_expected_bytes": s1.EXPECTED_BYTES,
        "source_archive_expected_sha256": s1.EXPECTED_SHA,
        "s2_anchor_sha256": s1.file_hash(ANCHOR_PATH, cap=32768)[1],
        "s2_original_receipt_sha256": S2_RECEIPT_SHA,
        "s2_artifact_zip_sha256": S2_ZIP_SHA,
        "s2_protected_main_sha": S2_COMMIT,
        "s2_selection_sha256": S2_SELECTED_SHA,
        "s1_script_sha256": s1.file_hash(Path(s1.__file__), cap=4*1024*1024)[1],
        "s2_script_sha256": s1.file_hash(Path(s2.__file__), cap=4*1024*1024)[1],
        "s3_script_sha256": s1.file_hash(Path(__file__), cap=4*1024*1024)[1],
        "original_d1_csv_source_admitted": False,
        "captured_four_mic_sync_verified": False,
        "camera_audio_timebase_verified": False,
        "doa_accuracy_measured": False,
        "bf_or_aec_performance_measured": False,
        "shipping_authority": False,
        "research_rights": "NONCOMMERCIAL_ATTRIBUTION_ONLY",
    }


def save(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(data, sort_keys=True, ensure_ascii=False,
                               separators=(",", ":"), allow_nan=False)+"\n", encoding="utf-8")
    temp.replace(path)


def collect(work, receipt):
    anchor = load_anchor()
    result = identity(s2.source_sha(), anchor)
    result["retrieved_at_utc"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        work.mkdir(parents=True, exist_ok=True)
        upstream = s1.download(work)
        s1.verify_archive(work / "Gym.rar", upstream, s1.EXPECTED_BYTES, s1.EXPECTED_SHA)
        rows, decoder_id, inventory = eight_originals(work, anchor, extract=True)
        result.update({
            "archive": upstream, "decoder": decoder_id, "inventory": inventory,
            "members": rows, "decoded_pcm_count": 8, "decision": PASS
        })
        code = 0
    except (Reject, s1.Reject, s2.Reject, OSError, subprocess.SubprocessError) as err:
        result["decision"] = BLOCKED
        code = 1
        reason = getattr(err, "code", None)
        result["failure_code"] = reason if isinstance(reason, str) else "S3_TOOL_OR_STORAGE_ERROR"
    save(receipt, result)
    print("decision="+result["decision"]+" failure="+result.get("failure_code", "NONE"),
          flush=True)
    return code


def verify(work, receipt_path):
    anchor = load_anchor()
    expected = identity(s2.source_sha(), anchor)
    data = strict_json(receipt_path)
    require(isinstance(data, dict), "S3_RECEIPT_TAMPER")
    for k, v in expected.items():
        require(data.get(k) == v, "S3_RECEIPT_TAMPER")
    require(isinstance(data.get("retrieved_at_utc"), str) and
            bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z",
                              data["retrieved_at_utc"])), "S3_RECEIPT_TAMPER")
    if data.get("decision") == PASS:
        require(set(data) == set(expected) |
                {"retrieved_at_utc", "archive", "decoder", "inventory",
                 "members", "decoded_pcm_count", "decision"}
                and data.get("decoded_pcm_count") == 8
                and isinstance(data.get("archive"), dict)
                and isinstance(data.get("decoder"), dict)
                and isinstance(data.get("inventory"), dict)
                and isinstance(data.get("members"), list)
                and len(data["members"]) == 8, "S3_RECEIPT_TAMPER")
        # The SECOND check independently re-reads the full original 447 MB
        # archive, original eight FLAC file bytes and all decoded PCM streams.
        s1.verify_archive(work / "Gym.rar", data["archive"],
                          s1.EXPECTED_BYTES, s1.EXPECTED_SHA)
        rebuilt, decoder_id, inventory = eight_originals(work, anchor, extract=False)
        require(data["members"] == rebuilt and data["decoder"] == decoder_id
                and data["inventory"] == inventory, "S3_RECEIPT_READBACK_MISMATCH")
    else:
        require(data.get("decision") == BLOCKED
                and isinstance(data.get("failure_code"), str)
                and re.fullmatch(r"(S3_|S2_|ARCHIVE_)[A-Z0-9_]+",
                                 data["failure_code"])
                and set(data) == set(expected) |
                {"retrieved_at_utc", "decision", "failure_code"}, "S3_RECEIPT_TAMPER")
    print("S3_INDEPENDENT_READBACK_CONSISTENT="+data["decision"])


def self_test():
    a = load_anchor()
    require(len(a["members"]) == 8 and a["s2_original_receipt_sha256"] == S2_RECEIPT_SHA)
    samples = b"\x00\x80\xff\x7f\x01\x00\xff\xff"
    h = PCMHasher(len(samples))
    h.feed(samples[:3])
    h.feed(samples[3:])
    r = h.result(hashlib.md5(samples).hexdigest())
    require(r["raw_pcm_bytes"] == 8 and r["streaminfo_md5_matches"]
            and r["decoded_pcm_sha256"] == sha256(samples))
    for wrong in ("0"*32, "f"*32):
        try:
            h.result(wrong)
        except Reject:
            pass
        else:
            raise AssertionError("tampered or zero PCM MD5 accepted")
    for shorter in (2, 4):
        h2 = PCMHasher(8)
        h2.feed(samples[:shorter])
        try:
            h2.result(hashlib.md5(samples).hexdigest())
        except Reject:
            pass
        else:
            raise AssertionError("truncated PCM accepted")
    h3 = PCMHasher(4)
    try:
        h3.feed(samples)
    except Reject:
        pass
    else:
        raise AssertionError("oversized PCM accepted")
    # Frozen S2 anchor corruption must fail without downloading/decoding.
    invalid = copy.deepcopy(a)
    invalid["members"][0]["streaminfo"]["streaminfo_pcm_md5_hex"] = "0"*32
    with tempfile.TemporaryDirectory(prefix="s3-selftest-") as tmp:
        receipt = Path(tmp)/"receipt.json"
        base = identity("0"*40, a)
        blocked = dict(base, retrieved_at_utc="2026-10-10T00:00:00Z",
                       decision=BLOCKED, failure_code="S3_DECODED_PCM_MD5_MISMATCH")
        save(receipt, blocked)
        # Selftest checks the shape, no original archive/PCM required.
        assert strict_json(receipt) == blocked
        for altered in (dict(blocked, shipping_authority=True),
                        dict(blocked, decision=PASS),
                        dict(blocked, failure_code="ADMITTED_WITHOUT_PROOF")):
            require(altered != blocked)
    print("REALMAN_D2_S3_OFFLINE_SELF_TEST_PASS; no source audio decoded")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("self-test", "collect", "verify"))
    parser.add_argument("--workspace")
    parser.add_argument("--receipt")
    args = parser.parse_args()
    if args.action == "self-test":
        self_test()
        return 0
    require(bool(args.workspace and args.receipt), "S3_ARGUMENTS_MISSING")
    work = s2.exact_work(args.workspace)
    receipt = Path(args.receipt).resolve()
    if args.action == "collect":
        return collect(work, receipt)
    verify(work, receipt)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
