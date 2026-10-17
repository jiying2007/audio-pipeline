#!/usr/bin/env python3
"""B1-S1 #778: actual first-party APX3 C chunks + verified source row hash-chain.

Software research ONLY. One-frame/large hosted buffers; this is not a
durable rolling recorder, encrypted/authenticated source, public ABI,
physical AEC timebase, 192KiB SSC305 or device/HIL certification.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import zlib

import fe09_array_sdk_draft_qualification_r2a as tools
import fe09_b2s3_t2b_b1s0_owner_spsc_qualification as b1

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
BASE = "2c8025f68753891e07f2754e74e24cf50aff5f16"
DECISION = "FE09_T2B_B1S1_SOURCE_EXACT_ONE_FRAME_APX3_CHUNKS_NO_DURABILITY"
FAILURE = "FE09_T2B_B1S1_SOURCE_EXACT_CHUNKS_NOT_ADMITTED"
TARGETS = ("native", "sanitized", "arm", "tsan")
MEMBERS = ("SHA256SUMS", "receipt.json", "collect.log", "verify.log")
CHUNKS_C = HERE / "fe09_b2s3_t2b_b1s1_source_chunks.c"
CHUNKS_H = HERE / "fe09_b2s3_t2b_b1s1_source_chunks.h"
SHA_C = HERE / "fe09_b2s3_t2b_b1s1_chunk_sha256.c"
SHA_H = HERE / "fe09_b2s3_t2b_b1s1_chunk_sha256.h"
TEST_C = HERE / "fe09_b2s3_t2b_b1s1_source_chunks_test.c"
OWN = (SHA_H, SHA_C, CHUNKS_H, CHUNKS_C, TEST_C, Path(__file__).resolve())
FROZEN = tuple(dict.fromkeys((*b1.FROZEN, *b1.OWN)))
SOURCES = (*b1.SOURCES[:-1], SHA_C, CHUNKS_C, TEST_C)


class Denied(ValueError):
    pass


def need(predicate: object, code: str) -> None:
    if not predicate:
        raise Denied(code)


def file_sha(path: Path) -> str:
    need(path.is_file() and not path.is_symlink() and
         0 < path.stat().st_size <= 16 * 1024 * 1024,
         "SOURCE_ABSENT_OR_OVERSIZE_" + path.name)
    return hashlib.sha256(path.read_bytes()).hexdigest()


def frozen() -> dict[str, str]:
    need(b1.BASE == "58c9c77567998839c38bf1d8a6da72bdbead1620",
         "PREDECESSOR_HISTORY_DRIFT")
    pins = {}
    for file in FROZEN:
        path = str(file.relative_to(ROOT))
        raw = subprocess.check_output(
            ["git", "-c", "safe.directory=" + str(ROOT),
             "show", BASE + ":" + path], cwd=ROOT, timeout=30)
        need(0 < len(raw) <= 16 * 1024 * 1024 and
             hashlib.sha256(raw).hexdigest() == file_sha(file),
             "FROZEN_ORIGINAL_CHANGED_" + path)
        pins[path] = hashlib.sha256(raw).hexdigest()
    return pins


def identity(commit: str) -> dict:
    need(re.fullmatch("[a-f0-9]{40}", commit) is not None,
         "SOURCE_COMMIT_NOT_EXACT")
    return {
        "schema_version": 1,
        "stage": "FE09-R2B2-S3-T2B-B1S1-ONE-FRAME-SOURCE-EXACT-APX3",
        "preregistration": "https://github.com/jiying2007/audio-pipeline/issues/778",
        "source_commit": commit,
        "protected_predecessor_main": BASE,
        "protected_predecessor_verify": 38928394697,
        "protected_predecessor_verify_attempt": 2,
        "protected_predecessor_release": 38940767664,
        "source_role": "first-party-synthetic",
        "own_source_sha256": {
            str(file.relative_to(ROOT)): file_sha(file) for file in OWN
        },
        "frozen_first_party_sha256": frozen(),
        "one_frame_chunks_hosted_only": True,
        "durable_io_qualified": False,
        "full_rolling_recorder_qualified": False,
        "physical_adc_dac_timebase_measured": False,
        "source_cryptographically_authenticated": False,
        "ssc305_device_qualified": False,
        "public_sdk_installed": False,
        "shipping_dsp_modified": False,
        "legacy_apd2_modified": False,
    }


def u32(raw: bytes, start: int) -> int:
    return int.from_bytes(raw[start:start + 4], "little")


def u64(raw: bytes, start: int) -> int:
    return int.from_bytes(raw[start:start + 8], "little")


def fnv_le(pcm_bytes: bytes) -> int:
    h = 14695981039346656037
    for char in pcm_bytes:
        h = ((h ^ char) * 1099511628211) & ((1 << 64) - 1)
    return h


def check_independent_source_sample(result: dict) -> None:
    chunk_hex, row_hex = result["source_chunk_hex"], result["source_manifest_hex"]
    need(type(chunk_hex) is str and
         len(chunk_hex) % 2 == 0 and 256 < len(chunk_hex) <= 10240 and
         re.fullmatch("[a-f0-9]+", chunk_hex) is not None and
         type(row_hex) is str and len(row_hex) == 400 and
         re.fullmatch("[a-f0-9]{400}", row_hex) is not None,
         "MALFORMED_SOURCE_BYTES_OR_CANONICAL_ROW")
    chunk, row = bytes.fromhex(chunk_hex), bytes.fromhex(row_hex)
    # Exact independent Python SHA256 audit of REAL ORIGINAL-C S2 bytes
    # and canonical C manifest row. This is NOT a Python replacement codec.
    need(chunk[:4] == b"APX3" and len(chunk) == 4964 and
         row[:4] == b"FBS1" and
         row[104:136] == hashlib.sha256(chunk).digest() and
         row[168:200] == hashlib.sha256(row[:168]).digest(),
         "FIPS_SHA256_CHUNK_OR_MANIFEST_INDEPENDENT_REHASH")
    need(u32(row, 4) == 1 and u32(row, 8) == 1 and
         u32(row, 12) == 48000 and u32(row, 16) == 4 and
         u64(row, 20) == 900001 and u64(row, 48) == 24 and
         u64(row, 56) == 1 and u32(row, 64) == 1 and
         u32(row, 68) == len(chunk) and
         [u32(row, 88 + i * 4) for i in range(4)] == [3, 2, 1, 0] and
         row[136:168] != bytes(32),
         "GLOBAL_CAPTURE_TO_APX3_LOCAL_MAPPING_DRIFT")
    need(u32(chunk, 4) == 2 and u32(chunk, 20) == 1 and
         u32(chunk, 16) == len(chunk) and
         u32(chunk, 24) == 48000 and
         u32(chunk, 32) == 4 and u32(chunk, 36) == 1 and
         u64(chunk, 128) == 1 and
         [u32(chunk, 48 + i * 4) for i in range(4)] ==
         [3, 2, 1, 0] and
         u32(chunk, 64) == u32(row, 28) and
         u32(chunk, 68) == u32(row, 32) and
         u32(chunk, 72) == 1 and
         u32(chunk, 76) == u32(row, 40),
         "ACTUAL_FIRST_PARTY_APX3_SOURCE_SCHEMA_OR_SEQUENCE_DRIFT")
    need(u32(chunk, 124) == zlib.crc32(chunk[:124]) and
         u32(chunk, len(chunk) - 4) ==
         zlib.crc32(chunk[128:len(chunk) - 4]),
         "ORIGINAL_APX3_HEADER_OR_FRAME_CRC_DRIFT")
    mic = chunk[160:160 + 480 * 4 * 2]
    render = chunk[160 + 480 * 4 * 2:-4]
    need(len(render) == 480 * 2 and
         u64(row, 72) == fnv_le(mic) and
         u64(row, 80) == fnv_le(render),
         "OWNER_SOURCE_BYTES_NOT_MATCHING_ORIGINAL_S2_PCM")


def check_result(result: dict) -> None:
    keys = {
        "schema_version", "decision", "source_role",
        "real_original_s2_codec", "real_capture_source_before_queue_tail",
        "chunk_hash_chain_verified", "apx3_chunks_replayed",
        "physical_clock_qualified", "durable_io_qualified",
        "ssc305_device_qualified", "public_sdk_installed",
        "profiles", "profile_count", "negative_checks", "control_digest",
        "source_chunk_hex", "source_manifest_hex",
    }
    need(type(result) is dict and set(result) == keys, "RESULT_SCHEMA_CHANGED")
    need(type(result["schema_version"]) is int and
         result["schema_version"] == 1 and
         result["decision"] == DECISION and
         result["source_role"] == "first-party-synthetic" and
         all(result[key] is True for key in (
             "real_original_s2_codec", "real_capture_source_before_queue_tail",
             "chunk_hash_chain_verified", "apx3_chunks_replayed")) and
         all(result[key] is False for key in (
             "physical_clock_qualified", "durable_io_qualified",
             "ssc305_device_qualified", "public_sdk_installed")) and
         type(result["profile_count"]) is int and
         result["profile_count"] == 48 and
         type(result["negative_checks"]) is int and
         result["negative_checks"] >= 720 and
         type(result["control_digest"]) is str and
         re.fullmatch("[0-9a-f]{16}", result["control_digest"]) is not None,
         "B1S1_FALSE_APX3_OR_PRODUCT_ADMISSION")
    profiles = result["profiles"]
    needed = [(scene, rate, depth, render)
              for scene in ("C1_BASELINE", "C2_ULA", "C4_ULA", "C4_UCA")
              for rate in (16000, 32000, 48000)
              for depth in (2, 4)
              for render in (0, 1)]
    need(type(profiles) is list and len(profiles) == 48,
         "MISSING_REAL_FIRST_PARTY_CHUNK_CONFIGURATIONS")
    for item, (scene, rate, depth, render) in zip(profiles, needed):
        need(type(item) is dict and set(item) == {
            "scene", "rate", "depth", "render_enabled", "frames",
            "chunk_count", "control_hash", "bf_hash"
        } and item["scene"] == scene and
             type(item["rate"]) is int and item["rate"] == rate and
             type(item["depth"]) is int and item["depth"] == depth and
             type(item["render_enabled"]) is int and
             item["render_enabled"] == render and
             type(item["frames"]) is int and item["frames"] == 24 and
             type(item["chunk_count"]) is int and item["chunk_count"] == 24 and
             type(item["control_hash"]) is str and
             re.fullmatch("[0-9a-f]{16}", item["control_hash"]) is not None and
             type(item["bf_hash"]) is str and
             re.fullmatch("[0-9a-f]{16}", item["bf_hash"]) is not None,
             "INVALID_CONCURRENT_SOURCE_CODEC_PROFILE_" + scene)
    check_independent_source_sample(result)


def check_targets(targets: dict) -> None:
    need(type(targets) is dict and set(targets) == set(TARGETS),
         "MISSING_ACTUAL_NATIVE_ASAN_ARM_TSAN")
    for row in targets.values():
        check_result(row)
    ref = targets["native"]
    for target in TARGETS[1:]:
        row = targets[target]
        for key in ("schema_version", "decision", "source_role",
                    "real_original_s2_codec", "real_capture_source_before_queue_tail",
                    "chunk_hash_chain_verified", "apx3_chunks_replayed",
                    "physical_clock_qualified", "durable_io_qualified",
                    "ssc305_device_qualified", "public_sdk_installed",
                    "profile_count", "negative_checks", "control_digest",
                    "source_chunk_hex", "source_manifest_hex"):
            need(row[key] == ref[key],
                 "INTEGER_OR_CANONICAL_APX3_CROSS_TARGET_DRIFT_" + key)
        for item, prior in zip(row["profiles"], ref["profiles"]):
            for field in ("scene", "rate", "depth", "render_enabled",
                          "frames", "chunk_count", "control_hash"):
                need(item[field] == prior[field],
                     "INTEGER_PER_PROFILE_SOURCE_DRIFT_" + field)
    # Never require Float32 BF hash equality between ARM and x86 ISA.


def self_test() -> None:
    frozen()
    # An independent bounded artificial BYTES test vector. This is ONLY
    # a policy-verifier self-test, not a substitution for C codec execution.
    raw = bytearray(4964)
    raw[:4] = b"APX3"
    for p, v in ((4, 2), (16, 4964), (20, 1), (24, 48000),
                 (32, 4), (36, 1), (64, 105), (68, 205),
                 (72, 1), (76, 4)):
        raw[p:p + 4] = v.to_bytes(4, "little")
    for i, slot in enumerate((3, 2, 1, 0)):
        raw[48 + i * 4:52 + i * 4] = slot.to_bytes(4, "little")
    raw[128:136] = (1).to_bytes(8, "little")
    raw[124:128] = zlib.crc32(raw[:124]).to_bytes(4, "little")
    raw[-4:] = zlib.crc32(raw[128:-4]).to_bytes(4, "little")
    manifest = bytearray(200)
    manifest[:4] = b"FBS1"
    for p, v in ((4, 1), (8, 1), (12, 48000),
                 (16, 4), (28, 105), (32, 205),
                 (36, 1), (40, 4), (48, 24), (56, 1),
                 (64, 1), (68, len(raw))):
        manifest[p:p + (8 if p in (48, 56) else 4)] = (
            v.to_bytes(8 if p in (48, 56) else 4, "little"))
    manifest[20:28] = (900001).to_bytes(8, "little")
    for i, slot in enumerate((3, 2, 1, 0)):
        manifest[88 + i * 4:92 + i * 4] = slot.to_bytes(4, "little")
    manifest[72:80] = fnv_le(bytes(raw[160:4000])).to_bytes(8, "little")
    manifest[80:88] = fnv_le(bytes(raw[4000:-4])).to_bytes(8, "little")
    manifest[104:136] = hashlib.sha256(raw).digest()
    manifest[136:168] = bytes([1] * 32)
    manifest[168:200] = hashlib.sha256(manifest[:168]).digest()
    profiles = [{"scene": s, "rate": r, "depth": d, "render_enabled": e,
                 "frames": 24, "chunk_count": 24,
                 "control_hash": "0123456789abcdef",
                 "bf_hash": "fedcba9876543210"}
                for s in ("C1_BASELINE", "C2_ULA", "C4_ULA", "C4_UCA")
                for r in (16000, 32000, 48000)
                for d in (2, 4) for e in (0, 1)]
    good = {
        "schema_version": 1, "decision": DECISION,
        "source_role": "first-party-synthetic",
        "real_original_s2_codec": True,
        "real_capture_source_before_queue_tail": True,
        "chunk_hash_chain_verified": True,
        "apx3_chunks_replayed": True,
        "physical_clock_qualified": False,
        "durable_io_qualified": False,
        "ssc305_device_qualified": False,
        "public_sdk_installed": False,
        "profiles": profiles, "profile_count": 48,
        "negative_checks": 720, "control_digest": "0123456789abcdef",
        "source_chunk_hex": bytes(raw).hex(),
        "source_manifest_hex": bytes(manifest).hex(),
    }
    check_targets({key: good for key in TARGETS})
    negative = 0
    for name, invalid in (
        ("decision", FAILURE), ("source_role", "real-ADC"),
        ("real_original_s2_codec", False),
        ("real_capture_source_before_queue_tail", False),
        ("chunk_hash_chain_verified", False),
        ("apx3_chunks_replayed", False),
        ("physical_clock_qualified", True),
        ("durable_io_qualified", True),
        ("ssc305_device_qualified", True),
        ("public_sdk_installed", True),
        ("negative_checks", 719),
        ("control_digest", "malformed"),
    ):
        variant = json.loads(json.dumps(good))
        variant[name] = invalid
        try: check_result(variant)
        except Denied: negative += 1
        else: raise Denied("FALSE_SELFTEST_PROMOTION_" + name)
    for name, val in (
        ("source_chunk_hex", "00"),
        ("source_manifest_hex", "00" * 200),
    ):
        variant = json.loads(json.dumps(good))
        variant[name] = val
        try: check_result(variant)
        except Denied: negative += 1
        else: raise Denied("FALSE_SOURCE_REHASH_PROMOTION_" + name)
    need(negative == 14, "SELFTEST_NEGATIVE_COUNT_MISMATCH")
    print("FE09_B1S1_INDEPENDENT_SOURCE_BYTES_SELFTEST_PASS controls=14")


def verify_output(output: Path, commit: str) -> None:
    need(output.is_dir() and {p.name for p in output.iterdir()} ==
         set(MEMBERS), "ARTIFACT_MEMBERS_CHANGED")
    for name in MEMBERS:
        p = output/name
        cap = (1024 if name == "SHA256SUMS" else
               262144 if name == "receipt.json" else
               2097152 if name == "collect.log" else 256)
        need(p.is_file() and not p.is_symlink() and
             0 < p.stat().st_size <= cap,
             "ARTIFACT_MEMBER_SIZE_BOUND_" + name)
    manifest = "".join(f"{file_sha(output / p)}  {p}\n"
                       for p in ("receipt.json", "collect.log", "verify.log"))
    need((output/"SHA256SUMS").read_text("ascii") == manifest,
         "ARTIFACT_INNER_SHA256_CHANGED")
    receipt = tools.strict_json((output/"receipt.json").read_text("utf-8"))
    for key, value in identity(commit).items():
        need(receipt.get(key) == value,
             "PREDECESSOR_OR_SOURCE_TAMPER_" + key)
    need(receipt.get("decision") == DECISION and
         receipt.get("actual_four_target_source_codec_qualified") is True and
         receipt.get("target_order") == list(TARGETS) and
         receipt.get("source_role") == "first-party-synthetic" and
         receipt.get("durable_io_qualified") is False and
         receipt.get("full_rolling_recorder_qualified") is False and
         receipt.get("physical_adc_dac_timebase_measured") is False and
         receipt.get("ssc305_device_qualified") is False and
         receipt.get("source_cryptographically_authenticated") is False and
         receipt.get("public_sdk_installed") is False,
         "FALSE_B1S1_DURABLE_OR_PHYSICAL_AUTHORITY")
    binaries = receipt.get("binary_sha256")
    compilers = receipt.get("compiler_versions")
    need(type(binaries) is dict and set(binaries) == set(TARGETS) and
         all(type(x) is str and re.fullmatch("[0-9a-f]{64}", x)
             for x in binaries.values()) and
         type(compilers) is dict and set(compilers) == set(TARGETS) and
         all(type(x) is str and bool(x) for x in compilers.values()),
         "MISSING_ACTUAL_NATIVE_ASAN_ARM_TSAN_ELFS")
    check_targets(receipt.get("target_results"))
    need((output/"verify.log").read_text("ascii") ==
         "FE09_B1S1_FIRST_PARTY_APX3_CHUNKS_VERIFIED\n",
         "VERIFY_MARKER_DRIFT")


def collect(output: Path, commit: str) -> None:
    need(not output.exists(), "DO_NOT_OVERWRITE_PRIOR_ARTIFACT")
    need(tools.source_head() == commit, "RUNNING_SOURCE_DIFFERENT")
    receipt = identity(commit)
    receipt["decision"] = FAILURE
    receipt["actual_four_target_source_codec_qualified"] = False
    logs: list[str] = []
    output.mkdir(parents=True)
    try:
        targets, versions, hashes = {}, {}, {}
        with tempfile.TemporaryDirectory(prefix="fe09-b1s1-") as tmp:
            wd = Path(tmp)
            hdr = wd/"include/audio_pipeline/audio_pipeline_build.h"
            hdr.parent.mkdir(parents=True)
            hdr.write_text(
                "#ifndef AUDIO_PIPELINE_AUDIO_PIPELINE_BUILD_H\n"
                "#define AUDIO_PIPELINE_AUDIO_PIPELINE_BUILD_H\n"
                "#define AP_BUILD_RESAMPLER_BANDLIMITED 1\n"
                "#endif\n", encoding="ascii")
            for target in TARGETS:
                compiler = ("arm-linux-gnueabihf-gcc" if target == "arm"
                            else "cc")
                need(shutil.which(compiler) is not None,
                     "COMPILER_MISSING_" + target)
                versions[target] = tools.run(
                    [compiler, "--version"], logs).splitlines()[0]
                flags = [compiler, "-std=c11", "-Wall", "-Wextra", "-Werror",
                         "-O2", "-ffp-contract=off", "-fno-fast-math",
                         "-pthread", "-DAP_BUILD_RESAMPLER_BANDLIMITED=1",
                         "-I" + str(wd/"include"), "-I" + str(ROOT/"src"),
                         "-I" + str(HERE)]
                if target == "sanitized":
                    flags += ["-O1", "-g", "-fsanitize=address,undefined",
                              "-fno-omit-frame-pointer"]
                if target == "tsan":
                    flags += ["-O1", "-g", "-fsanitize=thread",
                              "-fno-omit-frame-pointer"]
                if target == "arm":
                    flags += ["-march=armv7-a", "-mfpu=neon-vfpv4",
                              "-mfloat-abi=hard"]
                objects = []
                for i, src in enumerate(SOURCES):
                    obj = wd/f"{target}-{i}.o"
                    warnings = ([] if src in (
                        b1.b0.b1.SOURCE_C, b1.b0.b1.ARRAY_C
                    ) else ["-Wconversion", "-Wshadow", "-Wpedantic"])
                    tools.run(flags + warnings + ["-c", str(src),
                                                  "-o", str(obj)],
                              logs, timeout=120)
                    objects.append(str(obj))
                elf = wd/(target+".elf")
                link = [compiler, *objects, "-pthread", "-lm", "-o", str(elf)]
                if target == "sanitized":
                    link += ["-fsanitize=address,undefined"]
                if target == "tsan":
                    link += ["-fsanitize=thread"]
                if target == "arm":
                    link += ["-march=armv7-a", "-mfpu=neon-vfpv4",
                             "-mfloat-abi=hard"]
                tools.run(link, logs, timeout=120)
                hashes[target] = file_sha(elf)
                command = [str(elf)]
                if target == "arm":
                    need(shutil.which("qemu-arm") is not None and
                         Path("/usr/arm-linux-gnueabihf").is_dir(),
                         "ARM32_QEMU_OR_TOOLCHAIN_MISSING")
                    command = ["qemu-arm", "-L", "/usr/arm-linux-gnueabihf",
                               str(elf)]
                env = dict(os.environ)
                if target == "sanitized":
                    env.update({"ASAN_OPTIONS": "detect_leaks=0:halt_on_error=1",
                                "UBSAN_OPTIONS": "halt_on_error=1"})
                if target == "tsan":
                    env.update({"TSAN_OPTIONS": "halt_on_error=1:exitcode=66"})
                first = tools.strict_json(
                    tools.run(command, logs, timeout=180, env=env))
                again = tools.strict_json(
                    tools.run(command, logs, timeout=180, env=env))
                need(first == again,
                     "ACTUAL_ORIGINAL_CODEC_EXECUTION_NONDETERMINISTIC_" + target)
                check_result(first)
                targets[target] = first
        check_targets(targets)
        receipt.update({
            "decision": DECISION,
            "actual_four_target_source_codec_qualified": True,
            "target_order": list(TARGETS),
            "target_results": targets,
            "compiler_versions": versions,
            "binary_sha256": hashes,
        })
    except Exception as exc:
        receipt["decision"] = FAILURE
        receipt["actual_four_target_source_codec_qualified"] = False
        receipt["failure_type"] = type(exc).__name__
        receipt["failure_reason"] = str(exc)[:250]
        import sys
        print("FE09_B1S1_SOURCE_CODEC_FAILED_LOG_TAIL_BEGIN", file=sys.stderr)
        print("\n".join(logs[-8:])[-5000:], file=sys.stderr)
        print("FE09_B1S1_SOURCE_CODEC_FAILED_LOG_TAIL_END", file=sys.stderr)
        raise
    finally:
        (output/"receipt.json").write_text(
            json.dumps(receipt, sort_keys=True,
                       separators=(",", ":"), allow_nan=False) + "\n",
            encoding="utf-8")
        (output/"collect.log").write_text("\n".join(logs) + "\n",
                                           encoding="utf-8")
        (output/"verify.log").write_text(
            "FE09_B1S1_FIRST_PARTY_APX3_CHUNKS_VERIFIED\n"
            if receipt.get("decision") == DECISION else FAILURE + "\n",
            encoding="ascii")
        (output/"SHA256SUMS").write_text(
            "".join(f"{file_sha(output / p)}  {p}\n"
                    for p in ("receipt.json", "collect.log", "verify.log")),
            encoding="ascii")
    verify_output(output, commit)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    g = parser.add_mutually_exclusive_group(required=True)
    g.add_argument("--self-test", action="store_true")
    g.add_argument("--collect", action="store_true")
    g.add_argument("--verify", action="store_true")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--execution-source")
    args = parser.parse_args()
    try:
        if args.self_test:
            self_test()
        else:
            need(args.output is not None and
                 re.fullmatch("[0-9a-f]{40}", args.execution_source or "")
                 is not None, "OUTPUT_OR_SOURCE_NOT_EXACT")
            need(tools.source_head() == args.execution_source,
                 "GIT_SOURCE_HEAD_CHANGED")
            if args.collect:
                collect(args.output, args.execution_source)
            else:
                verify_output(args.output, args.execution_source)
                print("FE09_B1S1_FIRST_PARTY_APX3_CHUNKS_VERIFIED")
    except (Denied, tools.GateFailure, ValueError, OSError,
            subprocess.CalledProcessError) as exc:
        raise SystemExit(FAILURE + ": " + str(exc)) from None


if __name__ == "__main__":
    main()
