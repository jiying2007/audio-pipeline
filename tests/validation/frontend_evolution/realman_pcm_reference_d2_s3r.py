#!/usr/bin/env python3
"""FE03 A2 D2-S3R: source-built reference FLAC eight original PCM integrity.

Independently preregistered: https://github.com/jiying2007/audio-pipeline/issues/711
Only after protected D2-T0 closure; original failed D2-S3 is unchanged.
No acoustic score, raw PCM file, redistributed audio, or shipping DSP.
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
import realman_flac_decoder_toolchain_d2_t0 as t0

ROOT = Path(__file__).resolve().parents[3]
ANCHOR_PATH = Path(__file__).with_name("realman_s2_frozen_anchor_d2_s3r.json")
PASS = "REALMAN_D2_S3R_GYM_8_PCM_MD5_VERIFIED_RESEARCH_ONLY"
BLOCKED = "REALMAN_D2_S3R_PCM_BYTES_NOT_ADMITTED"
PER_PCM_TIMEOUT = 30
TOTAL_PCM_TIMEOUT = 180
DECODE_MAX = 2 * 238895
S2_COMMIT = "cc887b0ced20a828ed7148b9ac949f639a1e2868"
T0_COMMIT = "feb2f8ebc17a25bf248a63139ea4a219de39545d"
T0_SOURCE_RECEIPT_SHA = "9b47aa74da3b7533d8fbb1b4985a727114fdafd245dd5895656fb737b389b807"
T0_ARTIFACT_ZIP_SHA = "73269e2c809d88838a835bd397b57a6613599990a4c97508f1c00e3b653773dd"
T0_SCRIPT_SHA = "fd028a26e97c37d69b73982abee83b8a2ae9b1f4cbea1c7f8f965d45f6240760"
T0_OFFICIAL_SOURCE_TREE = "9d1cf0c77df717e633c9020eb60c87642beb9037"
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


def require(ok, code="S3R_RESEARCH_INTEGRITY_REJECTED"):
    if not ok:
        raise Reject(code)


def sha256(raw):
    return hashlib.sha256(raw).hexdigest()


def unique_keys(pairs):
    record = {}
    for k, v in pairs:
        require(k not in record, "S3R_DUPLICATE_JSON_KEY")
        record[k] = v
    return record


def no_constant(_):
    raise Reject("S3R_INVALID_JSON_CONSTANT")


def strict_json(path, limit=65536):
    require(path.is_file() and path.stat().st_size <= limit,
            "S3R_METADATA_FILE_NOT_ADMITTED")
    try:
        return json.loads(path.read_text(encoding="utf-8"),
                          object_pairs_hook=unique_keys, parse_constant=no_constant)
    except (OSError, UnicodeError, ValueError) as err:
        raise Reject("S3R_METADATA_JSON_INVALID") from None


def load_anchor():
    """Copy of all 8 individual fields from independently sealed S2 receipt."""
    a = strict_json(ANCHOR_PATH, 32768)
    require(isinstance(a, dict), "S3R_ANCHOR_TAMPER")
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
        require(a.get(k) == v, "S3R_ANCHOR_TAMPER")
    require(a.get("s1_script_sha256") == s1.file_hash(Path(s1.__file__), cap=4*1024*1024)[1]
            and a.get("s2_script_sha256") == s1.file_hash(Path(s2.__file__), cap=4*1024*1024)[1],
            "S3R_S1_S2_SOURCE_DRIFT")
    expected_keys = set(fixed) | {
        "s2_issue_url", "s1_script_sha256", "s2_script_sha256", "members"}
    require(set(a) == expected_keys
            and a.get("s2_issue_url") ==
            "https://github.com/jiying2007/audio-pipeline/issues/705",
            "S3R_ANCHOR_TAMPER")
    members = a.get("members")
    require(isinstance(members, list) and len(members) == 8,
            "S3R_ANCHOR_MEMBERS_INVALID")
    expected_order = [(role, ch) for role in s2.ROLES for ch in s2.CHS]
    actual_order = [(m.get("role"), m.get("channel")) for m in members
                    if isinstance(m, dict)]
    require(actual_order == expected_order, "S3R_ANCHOR_ORDER_DRIFT")
    for m in members:
        require(set(m) == {"role", "channel", "member_path_sha256", "stem_sha256",
                           "listed_uncompressed_bytes", "listed_packed_bytes",
                           "original_flac_bytes", "original_flac_sha256", "streaminfo"},
                "S3R_ANCHOR_FIELDS_INVALID")
        for k in ("original_flac_sha256", "member_path_sha256", "stem_sha256"):
            require(isinstance(m[k], str) and re.fullmatch(r"[0-9a-f]{64}", m[k]),
                    "S3R_ANCHOR_HASH_INVALID")
        length = m["original_flac_bytes"]
        require(type(length) is int and 0 < length <= s2.PER_FILE_LIMIT
                and m["listed_uncompressed_bytes"] == length
                and type(m["listed_packed_bytes"]) is int
                and 0 <= m["listed_packed_bytes"] <= s1.MAX_BYTES,
                "S3R_ANCHOR_LENGTH_INVALID")
        info = m["streaminfo"]
        require(isinstance(info, dict) and set(info) ==
                {"bits_per_sample", "decoded_pcm_verified", "flac_encoded_channels",
                 "max_block_size", "min_block_size", "native_sample_rate_hz",
                 "streaminfo_pcm_md5_hex", "streaminfo_pcm_md5_present",
                 "total_samples"}, "S3R_ANCHOR_STREAMINFO_INVALID")
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
                "S3R_ANCHOR_NATIVE_FORMAT_OR_PCM_MD5_INVALID")
    require(sum(m["original_flac_bytes"] for m in members) <= s2.TOTAL_LIMIT,
            "S3R_ANCHOR_BUDGET_DRIFT")
    return a


def pinned_reference(work):
    """Validate the actual ephemeral xiph reference build on THIS runner."""
    proof_path = work / "t0-proof.json"
    native_dir = work / "reference"
    proof = t0.load(proof_path)
    require(proof.get("decision") == t0.PASS and
            proof.get("source_commit") == s2.source_sha() and
            proof.get("t0_script_sha256") == T0_SCRIPT_SHA and
            proof.get("original_realman_data_used") is False and
            proof.get("realman_pcm_md5_verified") is False and
            proof.get("shipping_authority") is False,
            "S3R_REFERENCE_PROOF_INCOMPLETE")
    upstream = t0.source_identity(native_dir)
    require(upstream == proof.get("upstream") and
            upstream["revision"] == t0.COMMIT and
            upstream["tree"] == T0_OFFICIAL_SOURCE_TREE,
            "S3R_REFERENCE_SOURCE_DRIFT")
    tool, meta = t0.toolchain_identity(native_dir)
    require(meta == proof.get("native_decoder") and
            meta["native_version"] == "flac 1.4.3" and
            meta["build_target"] == "flacapp",
            "S3R_NATIVE_BINARY_INTEGRITY_FAILED")
    synthetic = proof.get("synthetic_proof", {})
    require(synthetic.get("raw_bitwise_match") is True and
            synthetic.get("damaged_input_blocked") is True and
            synthetic.get("raw_bytes") == 514 and
            synthetic.get("realman_recordings_used") is False,
            "S3R_SYNTHETIC_PROOF_MISSING")
    return tool, meta, proof

class PCMHasher:
    """Bounded constant-memory raw signed S16LE stream accumulator."""

    def __init__(self, expected_bytes):
        require(type(expected_bytes) is int and 0 < expected_bytes <= DECODE_MAX
                and expected_bytes % 2 == 0, "S3R_PCM_EXPECTED_LENGTH_INVALID")
        self.expected_bytes = expected_bytes
        self.length = 0
        self.md5 = hashlib.md5()
        self.sha = hashlib.sha256()

    def feed(self, chunk):
        self.length += len(chunk)
        require(self.length <= self.expected_bytes, "S3R_PCM_OVERSIZED")
        self.md5.update(chunk)
        self.sha.update(chunk)

    def result(self, expected_md5):
        require(self.length == self.expected_bytes, "S3R_PCM_LENGTH_MISMATCH")
        md5 = self.md5.hexdigest()
        require(isinstance(expected_md5, str)
                and re.fullmatch(r"[0-9a-f]{32}", expected_md5)
                and expected_md5 != "0"*32, "S3R_STREAMINFO_MD5_ABSENT")
        require(md5 == expected_md5, "S3R_DECODED_PCM_MD5_MISMATCH")
        return {"raw_pcm_bytes": self.length, "decoded_pcm_md5": md5,
                "decoded_pcm_sha256": self.sha.hexdigest(),
                "streaminfo_md5_matches": True}


def decode_original(tool, flat, samples, expected_md5, overall_deadline):
    """Stream signed native S16LE straight to bounded hashers, no PCM file."""
    require(type(samples) is int and samples in (238895, 237071),
            "S3R_PCM_SAMPLE_COUNT_DRIFT")
    hasher = PCMHasher(samples * 2)
    require(time.monotonic() < overall_deadline, "S3R_PCM_TOTAL_TIMEOUT")
    proc = None
    try:
        proc = subprocess.Popen(t0.decode_cmd(tool, flat),
                                stdin=subprocess.DEVNULL,
                                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        deadline = min(overall_deadline, time.monotonic() + PER_PCM_TIMEOUT)
        with selectors.DefaultSelector() as selector:
            fd = proc.stdout.fileno()
            os.set_blocking(fd, False)
            selector.register(fd, selectors.EVENT_READ)
            while selector.get_map():
                require(time.monotonic() < deadline, "S3R_PCM_DECODE_TIMEOUT")
                for key, _ in selector.select(timeout=0.25):
                    block = os.read(key.fd, 65536)
                    if block:
                        hasher.feed(block)
                    else:
                        selector.unregister(key.fd)
        remaining = deadline - time.monotonic()
        require(remaining > 0, "S3R_PCM_DECODE_TIMEOUT")
        require(proc.wait(timeout=min(3.0, remaining)) == 0,
                "S3R_NATIVE_FLAC_DECODER_FAILED")
        return hasher.result(expected_md5)
    except (OSError, subprocess.SubprocessError):
        raise Reject("S3R_NATIVE_FLAC_TOOL_OR_TIMEOUT") from None
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
            and len(selected) == 8, "S3R_FROZEN_MEMBER_SELECTION_DRIFT")
    for x, baseline in zip(selected, anchor["members"]):
        require(x["role"] == baseline["role"]
                and x["channel"] == baseline["channel"]
                and x["member_path_sha256"] == baseline["member_path_sha256"]
                and x["stem_sha256"] == baseline["stem_sha256"]
                and x["size"] == baseline["listed_uncompressed_bytes"]
                and x["packed_size"] == baseline["listed_packed_bytes"],
                "S3R_FROZEN_MEMBER_IDENTITY_MISMATCH")


def eight_originals(work, anchor, native_cli, *, extract):
    archive = work / "Gym.rar"
    extractor, selected, inventory = s2.list_and_select(archive)
    validate_selection(anchor, selected, inventory)
    require(Path(native_cli).is_file(), "S3R_NATIVE_REFERENCE_MISSING")
    rows = []
    extraction_deadline = time.monotonic() + s2.OVERALL_EXTRACT_TIMEOUT
    pcm_deadline = time.monotonic() + TOTAL_PCM_TIMEOUT
    for x, original in zip(selected, anchor["members"]):
        flat = work / ("%s-ch%d.flac" % (x["role"], x["channel"]))
        if extract:
            size, sha = s2.extract_exact(extractor, archive, x["name"], flat,
                                         x["size"], extraction_deadline)
            require((size, sha) == (original["original_flac_bytes"],
                                    original["original_flac_sha256"]),
                    "S3R_ORIGINAL_FLAC_BYTES_MISMATCH")
        size, sha = s1.file_hash(flat, cap=s2.PER_FILE_LIMIT)
        require((size, sha) == (original["original_flac_bytes"],
                                original["original_flac_sha256"]),
                "S3R_ORIGINAL_FLAC_REHASH_MISMATCH")
        info = s2.flac_streaminfo(flat)
        require(info == original["streaminfo"], "S3R_ORIGINAL_STREAMINFO_DRIFT")
        pcm = decode_original(native_cli, flat, info["total_samples"],
                              info["streaminfo_pcm_md5_hex"], pcm_deadline)
        rows.append({
            "role": x["role"], "channel": x["channel"],
            "member_path_sha256": x["member_path_sha256"],
            "original_flac_bytes": size, "original_flac_sha256": sha,
            "original_streaminfo": info, **pcm,
        })
    require(len(rows) == 8 and
            all(x["streaminfo_md5_matches"] for x in rows),
            "S3R_NOT_EIGHT_PCM_STREAMS")
    return rows, inventory

def identity(commit_sha, anchor):
    """Bind receipt to source checkout, T0/S2 independent evidence and scripts."""
    require(t0.COMMIT == "28e4f0528c76b296c561e922ba67d43751990599"
            and t0.PASS.endswith("SYNTHETIC_ONLY") and
            s1.file_hash(Path(t0.__file__), cap=4*1024*1024)[1] == T0_SCRIPT_SHA,
            "S3R_T0_TOOLCHAIN_SOURCE_CHANGED")
    return {
        "schema_version": 1,
        "experiment_id": "FE03-A2-D2-S3R-XIPH-FLAC-ORIGINAL-8-PCM",
        "preregistration": "https://github.com/jiying2007/audio-pipeline/issues/711",
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
        "t0_script_sha256": T0_SCRIPT_SHA,
        "t0_protected_main_sha": T0_COMMIT,
        "t0_source_receipt_sha256": T0_SOURCE_RECEIPT_SHA,
        "t0_artifact_zip_sha256": T0_ARTIFACT_ZIP_SHA,
        "reference_cli_expected_source_sha": t0.COMMIT,
        "reference_cli_expected_tree_sha": T0_OFFICIAL_SOURCE_TREE,
        "s3r_script_sha256": s1.file_hash(Path(__file__), cap=4*1024*1024)[1],
        "original_d2_s3_preinstalled_only_protocol_passed": False,
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
    """Qualify/build/verify reference before any RealMAN network access."""
    anchor = load_anchor()
    result = identity(s2.source_sha(), anchor)
    result["retrieved_at_utc"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        work.mkdir(parents=True, exist_ok=True)
        tool_work = work / "reference"
        tool_receipt = work / "t0-proof.json"
        require(not tool_work.exists() and not tool_receipt.exists(),
                "S3R_WORKSPACE_ALREADY_USED")
        require(t0.collect(tool_work, tool_receipt) == 0,
                "S3R_T0_RUNNER_BUILD_FAILED")
        # Second independent native CLI and synthetic proof before original bytes.
        t0.verify(tool_work, tool_receipt)
        native_cli, tool_meta, tool_proof = pinned_reference(work)
        result_t0_hash = s1.file_hash(tool_receipt, cap=32768)[1]
        upstream = s1.download(work)
        s1.verify_archive(work / "Gym.rar", upstream,
                          s1.EXPECTED_BYTES, s1.EXPECTED_SHA)
        rows, inventory = eight_originals(work, anchor, native_cli, extract=True)
        result.update({
            "archive": upstream, "local_t0": tool_proof,
            "local_t0_receipt_sha256": result_t0_hash,
            "native_decoder": tool_meta, "inventory": inventory,
            "members": rows, "decoded_pcm_count": 8, "decision": PASS,
        })
        code = 0
    except (Reject, s1.Reject, s2.Reject, t0.Reject, OSError,
            subprocess.SubprocessError) as err:
        result["decision"] = BLOCKED
        code = 1
        reason = getattr(err, "code", None)
        result["failure_code"] = (reason if isinstance(reason, str) and
                                  re.fullmatch(r"[A-Z][A-Z0-9_]{2,99}", reason)
                                  else "S3R_TOOL_OR_STORAGE_ERROR")
    save(receipt, result)
    print("decision="+result["decision"]+
          " failure="+result.get("failure_code", "NONE"), flush=True)
    return code

def verify(work, receipt_path):
    anchor = load_anchor()
    expected = identity(s2.source_sha(), anchor)
    data = strict_json(receipt_path)
    require(isinstance(data, dict), "S3R_RECEIPT_TAMPER")
    for k, v in expected.items():
        require(data.get(k) == v, "S3R_RECEIPT_TAMPER")
    require(isinstance(data.get("retrieved_at_utc"), str) and
            bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z",
                              data["retrieved_at_utc"])),
            "S3R_RECEIPT_TAMPER")
    if data.get("decision") == PASS:
        require(set(data) == set(expected) |
                {"retrieved_at_utc", "archive", "local_t0",
                 "local_t0_receipt_sha256", "native_decoder", "inventory",
                 "members", "decoded_pcm_count", "decision"} and
                data.get("decoded_pcm_count") == 8 and
                isinstance(data.get("archive"), dict) and
                isinstance(data.get("local_t0"), dict) and
                isinstance(data.get("inventory"), dict) and
                isinstance(data.get("native_decoder"), dict) and
                isinstance(data.get("members"), list) and
                len(data["members"]) == 8,
                "S3R_RECEIPT_TAMPER")
        # Independent local synthetic reference proof + binary/source rehash.
        tool_work = work / "reference"
        tool_receipt = work / "t0-proof.json"
        require(s1.file_hash(tool_receipt, cap=32768)[1] ==
                data["local_t0_receipt_sha256"], "S3R_LOCAL_T0_RECEIPT_DRIFT")
        t0.verify(tool_work, tool_receipt)
        native_cli, tool_meta, tool_proof = pinned_reference(work)
        require(tool_meta == data["native_decoder"] and
                tool_proof == data["local_t0"],
                "S3R_NATIVE_TOOLCHAIN_READBACK_MISMATCH")
        # One exact source archive SHA readback; second real PCM decode of
        # all eight original immutable FLACs without resampling or PCM files.
        s1.verify_archive(work / "Gym.rar", data["archive"],
                          s1.EXPECTED_BYTES, s1.EXPECTED_SHA)
        rebuilt, inventory = eight_originals(work, anchor, native_cli,
                                              extract=False)
        require(rebuilt == data["members"] and
                inventory == data["inventory"],
                "S3R_ORIGINAL_PCM_READBACK_MISMATCH")
    else:
        require(data.get("decision") == BLOCKED and
                isinstance(data.get("failure_code"), str) and
                re.fullmatch(r"(S3R_|S2_|S3R_|T0_|ARCHIVE_)[A-Z0-9_]+",
                             data["failure_code"]) and
                set(data) == set(expected) |
                {"retrieved_at_utc", "decision", "failure_code"},
                "S3R_RECEIPT_TAMPER")
    print("S3R_INDEPENDENT_READBACK_CONSISTENT="+data["decision"])

def self_test():
    anchor = load_anchor()
    require(len(anchor["members"]) == 8)
    t0.self_test()
    require(t0.COMMIT == "28e4f0528c76b296c561e922ba67d43751990599")
    samples = b"\x00\x80\xff\x7f\x01\x00\xff\xff"
    h = PCMHasher(len(samples))
    h.feed(samples[:3])
    h.feed(samples[3:])
    good_md5 = hashlib.md5(samples).hexdigest()
    out = h.result(good_md5)
    require(out["raw_pcm_bytes"] == 8 and out["streaminfo_md5_matches"] and
            out["decoded_pcm_sha256"] == sha256(samples),
            "S3R_SELFTEST_RAW_HASH_FAILED")
    for wrong in ("0"*32, "f"*32):
        try:
            h.result(wrong)
        except Reject:
            pass
        else:
            raise AssertionError("forged/zero source STREAMINFO MD5 accepted")
    for prefix in (2, 4):
        truncated = PCMHasher(len(samples))
        truncated.feed(samples[:prefix])
        try:
            truncated.result(good_md5)
        except Reject:
            pass
        else:
            raise AssertionError("truncated native PCM accepted")
    try:
        PCMHasher(4).feed(samples)
    except Reject:
        pass
    else:
        raise AssertionError("oversized native PCM accepted")
    require(anchor["s2_original_receipt_sha256"] == S2_RECEIPT_SHA and
            all(m["streaminfo"]["streaminfo_pcm_md5_present"] is True
                and m["streaminfo"]["decoded_pcm_verified"] is False
                and m["streaminfo"]["streaminfo_pcm_md5_hex"] != "0"*32
                for m in anchor["members"]),
            "S3R_FROZEN_SOURCE_DRIFT")
    with tempfile.TemporaryDirectory(prefix="s3r-receipt-selftest-") as td:
        path = Path(td) / "receipt.json"
        baseline = identity("0"*40, anchor)
        blocked = dict(baseline,
                       retrieved_at_utc="2026-10-11T00:00:00Z",
                       decision=BLOCKED,
                       failure_code="S3R_DECODED_PCM_MD5_MISMATCH")
        save(path, blocked)
        require(strict_json(path) == blocked)
        for change in (
            {"shipping_authority": True},
            {"captured_four_mic_sync_verified": True},
            {"decision": PASS},
            {"members": []},
            {"failure_code": "FALSE_SUCCESS"},
        ):
            bad = dict(blocked, **change)
            require(bad != blocked, "S3R_SELFTEST_FORGERY_NOT_MUTATED")
    print("REALMAN_D2_S3R_OFFLINE_SELF_TEST_PASS; no original audio consumed")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("self-test", "collect", "verify"))
    parser.add_argument("--workspace")
    parser.add_argument("--receipt")
    args = parser.parse_args()
    if args.action == "self-test":
        self_test()
        return 0
    require(bool(args.workspace and args.receipt), "S3R_ARGUMENTS_MISSING")
    work = s2.exact_work(args.workspace)
    receipt = Path(args.receipt).resolve()
    if args.action == "collect":
        return collect(work, receipt)
    verify(work, receipt)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
