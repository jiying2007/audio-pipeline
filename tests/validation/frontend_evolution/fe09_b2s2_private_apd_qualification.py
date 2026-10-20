#!/usr/bin/env python3
"""FE09-R2B2-S2 private APX3 record/parser/replay qualification, not an SDK."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import sys
import tempfile

import fe09_array_sdk_draft_qualification_r2a as tools
import fe09_b2s1_private_queue_qualification as s1

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
SOURCE = HERE / "fe09_b2s2_private_apd.c"
HEADER = HERE / "fe09_b2s2_private_apd.h"
FIXTURE = HERE / "fe09_b2s2_private_apd_test.c"
BASE = "580d2b565f62fc9b29ef9237b498898c89e51b05"
STAGE = "FE09-R2B2-S2-PRIVATE-APX3-RECORD-PARSER-REPLAY"
DECISION = "FE09_R2B2_S2_PRIVATE_APD_V2_READ_WRITE_REPLAY_RESEARCH_ONLY_NO_PUBLIC_ABI"
FAILURE = "FE09_R2B2_S2_FORMAT_PROVENANCE_OR_ARITHMETIC_DRIFT_NOT_ADMITTED"
TARGETS = ("native", "sanitized", "arm")
RATES = (16000, 32000, 48000)
SCENES = (("C1_BASELINE", 1), ("C2_ULA", 2),
          ("C4_ULA", 4), ("C4_UCA", 4))
MEMBERS = ("SHA256SUMS", "receipt.json", "collect.log", "verify.log")
LEGACY = (
    "tools/apdump.py", "tools/apreplay.py",
    "include/audio_pipeline/audio_diag.h",
    "src/platform/linux/ap_runtime.c",
)
FROZEN_S1 = (
    "tests/validation/frontend_evolution/fe09_b2s1_private_queue.c",
    "tests/validation/frontend_evolution/fe09_b2s1_private_queue.h",
    "tests/validation/frontend_evolution/fe09_b2s1_private_queue_qualification.py",
)
OWN = (SOURCE, HEADER, FIXTURE, Path(__file__).resolve())
NEGATIVE_FIELDS = (
    "public_api_installed", "publication_permission",
    "real_clock_measured", "ssc305_dut_qualified",
    "physical_four_mic_acoustic_gain_measured",
    "concurrent_spsc_tsan_qualified",
    "hosted_perf_is_device_budget",
)


class Denied(ValueError):
    pass


def need(condition: bool, reason: str) -> None:
    if not condition:
        raise Denied(reason)


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def file_sha(path: Path, cap: int = 16 * 1024 * 1024) -> str:
    need(path.is_file() and not path.is_symlink() and
         0 < path.stat().st_size <= cap, "MISSING_OR_OVERSIZE_FILE_" + path.name)
    return sha(path.read_bytes())


def frozen_source_identity() -> dict:
    """Require actual immutable S1 and public legacy bytes from protected main."""
    prior = s1.frozen_sources()
    witnessed = {}
    for path in (*LEGACY, *FROZEN_S1):
        live = ROOT / path
        wanted = subprocess.check_output(
            ["git", "-c", "safe.directory=" + str(ROOT),
             "show", BASE + ":" + path],
            cwd=ROOT, timeout=30)
        need(0 < len(wanted) <= 16 * 1024 * 1024,
             "FROZEN_MAIN_BLOB_UNREADABLE_" + path)
        digest = file_sha(live)
        need(digest == sha(wanted), "LEGACY_OR_S1_DRIFT_" + path)
        witnessed[path] = digest
    return {"s1_b2s0_contract_sha256": prior["b2_s0_contract_sha256"],
            "s1_b2s0_git_source_sha256": prior["b2_s0_source_sha256"],
            "protected_unchanged_sha256": witnessed}


def identity(source_commit: str) -> dict:
    need(bool(re.fullmatch(r"[a-f0-9]{40}", source_commit)),
         "MALFORMED_SOURCE_COMMIT")
    frozen = frozen_source_identity()
    return {
        "schema_version": 1,
        "stage": STAGE,
        "preregistration": "https://github.com/jiying2007/audio-pipeline/issues/760",
        "protected_predecessor_main": BASE,
        "protected_predecessor_verify": 38694644604,
        "protected_predecessor_release": 38698209211,
        "source_commit": source_commit,
        "source_sha256": {str(p.relative_to(ROOT)): file_sha(p) for p in OWN},
        **frozen,
        "public_api_installed": False,
        "publication_permission": False,
        "real_clock_measured": False,
        "ssc305_dut_qualified": False,
        "physical_four_mic_acoustic_gain_measured": False,
        "concurrent_spsc_tsan_qualified": False,
        "hosted_perf_is_device_budget": False,
        "source_role": "first-party-synthetic",
    }


def check_result(value: dict) -> None:
    keys = {
        "schema_version", "decision", "source_role", "public_sdk_installed",
        "actual_device_clock_qualified", "legacy_apd2_modified",
        "ssc305_dut_qualified", "profiles", "profile_count",
        "replay_subcases", "total_negatives", "stream_digest",
    }
    need(type(value) is dict and set(value) == keys,
         "TARGET_RESULT_SCHEMA_DRIFT")
    need(type(value["schema_version"]) is int and
         value["schema_version"] == 1 and
         value["decision"] == DECISION and
         value["source_role"] == "first-party-synthetic" and
         all(value[f] is False for f in (
             "public_sdk_installed", "actual_device_clock_qualified",
             "legacy_apd2_modified", "ssc305_dut_qualified")) and
         type(value["profile_count"]) is int and
         value["profile_count"] == 12 and
         type(value["replay_subcases"]) is int and
         value["replay_subcases"] == 24 and
         type(value["total_negatives"]) is int and
         value["total_negatives"] >= 1440 and
         isinstance(value["stream_digest"], str) and
         re.fullmatch(r"[0-9a-f]{16}", value["stream_digest"]) is not None,
         "NEGATIVE_OR_NONPROMOTION_RESULT_DRIFT")
    rows = value["profiles"]
    need(type(rows) is list and len(rows) == 12, "PROFILE_SET_DRIFT")
    expected = [(name, rate, n) for name, n in SCENES for rate in RATES]
    seen = set()
    for row, (name, rate, mics) in zip(rows, expected):
        need(type(row) is dict and set(row) == {
            "scene", "rate", "mics", "render_subcases", "repeats",
            "frames_per_subcase", "negative_cases", "byte_hash",
        }, "PROFILE_SCHEMA_DRIFT")
        need(row["scene"] == name and type(row["rate"]) is int and
             row["rate"] == rate and type(row["mics"]) is int and
             row["mics"] == mics and
             type(row["render_subcases"]) is int and
             row["render_subcases"] == 2 and
             type(row["repeats"]) is int and row["repeats"] == 2 and
             type(row["frames_per_subcase"]) is int and
             row["frames_per_subcase"] == 100 and
             type(row["negative_cases"]) is int and
             row["negative_cases"] >= 120 and
             type(row["byte_hash"]) is str and
             re.fullmatch(r"[a-f0-9]{16}", row["byte_hash"]) is not None,
             "PROFILE_CONTENT_DRIFT")
        need((name, rate) not in seen, "DUPLICATE_PROFILE")
        seen.add((name, rate))
    need(sum(row["negative_cases"] for row in rows) ==
         value["total_negatives"], "NEGATIVE_COUNT_MISMATCH")


def check_targets(target_results: dict) -> None:
    need(type(target_results) is dict and set(target_results) == set(TARGETS),
         "TARGETS_MISSING")
    for t in TARGETS:
        check_result(target_results[t])
    first = target_results["native"]
    for t in TARGETS[1:]:
        need(target_results[t] == first, "CROSS_ISA_SERIALIZATION_DRIFT_" + t)


def old_reader_rejects_new_magic() -> None:
    sys.path.insert(0, str(ROOT / "tools"))
    import apdump  # noqa: PLC0415 - deliberate real legacy reader check
    for mics in (1, 2, 4):
        buffer = bytearray(128)
        struct.pack_into("<I", buffer, 0, 0x33585041)
        struct.pack_into("<I", buffer, 32, mics)
        try:
            apdump.read_header(bytes(buffer))
        except ValueError as exc:
            need("bad APD magic" in str(exc),
                 "LEGACY_READER_REJECTED_WRONG_REASON")
        else:
            raise Denied("LEGACY_READER_ACCEPTED_PRIVATE_APX3")
    need(apdump.AP_DUMP_MAGIC == 0x32445041 and
         apdump.AP_DUMP_FORMAT_VERSION == 1,
         "LEGACY_DUMP_FORMAT_DRIFT")


def self_test() -> None:
    old_reader_rejects_new_magic()
    frozen_source_identity()
    fixture = {
        "schema_version": 1, "decision": DECISION,
        "source_role": "first-party-synthetic",
        "public_sdk_installed": False, "actual_device_clock_qualified": False,
        "legacy_apd2_modified": False, "ssc305_dut_qualified": False,
        "profiles": [
            {"scene": name, "rate": rate, "mics": mics,
             "render_subcases": 2, "repeats": 2, "frames_per_subcase": 100,
             "negative_cases": 144, "byte_hash": "abcdef0123456789"}
            for name, mics in SCENES for rate in RATES
        ],
        "profile_count": 12, "replay_subcases": 24,
        "total_negatives": 12 * 144, "stream_digest": "0123456789abcdef",
    }
    check_result(fixture)
    failures = 0
    for key, bad in (
        ("decision", FAILURE),
        ("source_role", "real-microphone"),
        ("public_sdk_installed", True),
        ("actual_device_clock_qualified", True),
        ("legacy_apd2_modified", True),
        ("ssc305_dut_qualified", True),
        ("total_negatives", 59),
        ("profile_count", 11),
        ("replay_subcases", 12),
        ("stream_digest", "not-sha"),
    ):
        altered = json.loads(json.dumps(fixture))
        altered[key] = bad
        try:
            check_result(altered)
        except Denied:
            failures += 1
        else:
            raise Denied("SELF_TEST_FALSE_ADMISSION_" + key)
    for idx, mutation in enumerate((
        ("scene", "C3_FAKE"), ("rate", 24000), ("mics", 3),
        ("render_subcases", 1), ("repeats", 1),
        ("frames_per_subcase", 1), ("negative_cases", 59),
        ("byte_hash", "abc"),
    )):
        altered = json.loads(json.dumps(fixture))
        altered["profiles"][0][mutation[0]] = mutation[1]
        try:
            check_result(altered)
        except Denied:
            failures += 1
        else:
            raise Denied("SELF_TEST_FALSE_PROFILE_" + str(idx))
    need(failures == 18, "INCOMPLETE_SELF_TEST")
    print("FE09_B2S2_APX3_PRIVATE_FORMAT_SELF_TEST_PASS negatives=18")


def verified_output(output: Path, source: str) -> None:
    need(output.is_dir() and
         {p.name for p in output.iterdir()} == set(MEMBERS),
         "ARTIFACT_MEMBER_DRIFT")
    for name in MEMBERS:
        p = output / name
        need(p.is_file() and not p.is_symlink() and
             0 < p.stat().st_size <= (
                 1_048_576 if name == "collect.log" else
                 65_536 if name == "receipt.json" else 2_048),
             "ARTIFACT_MEMBER_UNBOUNDED_" + name)
    hashes = "".join(f"{file_sha(output / name)}  {name}\n" for name
                     in ("receipt.json", "collect.log", "verify.log"))
    need((output / "SHA256SUMS").read_text("ascii") == hashes,
         "ARTIFACT_SHA256_MISMATCH")
    receipt = tools.strict_json((output / "receipt.json").read_text("utf-8"))
    for key, value in identity(source).items():
        need(receipt.get(key) == value, "SOURCE_IDENTITY_CHANGED_" + key)
    need(receipt.get("decision") == DECISION and
         receipt.get("target_order") == list(TARGETS) and
         receipt.get("old_reader_reject_new_magic") is True and
         receipt.get("new_reader_reject_old_magic") is True and
         all(receipt.get(key) is False for key in NEGATIVE_FIELDS),
         "FALSE_SHIPPING_OR_SOURCE_AUTHORITY")
    binaries = receipt.get("binary_sha256")
    need(type(binaries) is dict and set(binaries) == set(TARGETS) and
         all(type(s) is str and re.fullmatch(r"[a-f0-9]{64}", s)
             for s in binaries.values()), "MISSING_BINARY_SHA256")
    compilers = receipt.get("compiler_version")
    need(type(compilers) is dict and set(compilers) == set(TARGETS) and
         all(isinstance(x, str) and 0 < len(x) <= 200
             for x in compilers.values()), "COMPILER_RECEIPT_MISSING")
    check_targets(receipt.get("target_results"))
    need((output / "verify.log").read_text("utf-8") ==
         "FE09_B2S2_SOURCE_AND_APX3_RECEIPT_VERIFIED\n",
         "VERIFY_MARKER_DRIFT")


def collect(output: Path, source: str) -> None:
    need(not output.exists(), "REFUSE_OVERWRITE")
    need(tools.source_head() == source, "WRONG_EXECUTING_SOURCE")
    old_reader_rejects_new_magic()
    receipt = identity(source)
    receipt["decision"] = FAILURE
    logs: list[str] = []
    output.mkdir(parents=True)
    try:
        results, bins, compilers = {}, {}, {}
        with tempfile.TemporaryDirectory(prefix="fe09-b2s2-") as temp:
            tmp = Path(temp)
            for target in TARGETS:
                compiler = ("arm-linux-gnueabihf-gcc" if target == "arm"
                            else "cc")
                need(shutil.which(compiler) is not None,
                     "MISSING_COMPILER_" + target)
                compilers[target] = tools.run(
                    [compiler, "--version"], logs).splitlines()[0]
                flags = [
                    compiler, "-std=c11", "-Wall", "-Wextra", "-Werror",
                    "-Wconversion", "-Wshadow", "-Wpedantic", "-O2",
                    "-ffp-contract=off", "-fno-fast-math", "-I" + str(HERE),
                ]
                if target == "sanitized":
                    flags += ["-O1", "-g", "-fsanitize=address,undefined",
                              "-fno-omit-frame-pointer"]
                if target == "arm":
                    flags += ["-march=armv7-a", "-mfpu=neon-vfpv4",
                              "-mfloat-abi=hard"]
                elf = tmp / (target + ".elf")
                args = flags + [str(SOURCE), str(FIXTURE), "-o", str(elf)]
                if target == "sanitized":
                    args += ["-fsanitize=address,undefined"]
                tools.run(args, logs, timeout=120)
                bins[target] = file_sha(elf)
                if target == "arm":
                    need(shutil.which("qemu-arm") is not None and
                         Path("/usr/arm-linux-gnueabihf").is_dir(),
                         "ARM_QEMU_NOT_AVAILABLE")
                    command = ["qemu-arm", "-L", "/usr/arm-linux-gnueabihf",
                               str(elf)]
                else:
                    command = [str(elf)]
                env = dict(os.environ)
                if target == "sanitized":
                    env.update({"ASAN_OPTIONS": "detect_leaks=0:halt_on_error=1",
                                "UBSAN_OPTIONS": "halt_on_error=1"})
                first = tools.strict_json(
                    tools.run(command, logs, timeout=240, env=env))
                second = tools.strict_json(
                    tools.run(command, logs, timeout=240, env=env))
                need(first == second, "NONDETERMINISTIC_REPLAY_" + target)
                check_result(first)
                results[target] = first
        check_targets(results)
        receipt.update({
            "decision": DECISION,
            "target_order": list(TARGETS),
            "target_results": results,
            "binary_sha256": bins,
            "compiler_version": compilers,
            "old_reader_reject_new_magic": True,
            "new_reader_reject_old_magic": True,
            "execution_type": "hosted-private-synthetic-native-sanitized-qemu",
        })
    except Exception as exc:
        receipt["decision"] = FAILURE
        receipt["failure_type"] = type(exc).__name__
        receipt["failure_code"] = str(exc)[:180]
        raise
    finally:
        (output / "receipt.json").write_text(
            json.dumps(receipt, sort_keys=True, separators=(",", ":"),
                       allow_nan=False) + "\n", encoding="utf-8")
        (output / "collect.log").write_text(
            "\n".join(logs) + "\n", encoding="utf-8")
        (output / "verify.log").write_text(
            ("FE09_B2S2_SOURCE_AND_APX3_RECEIPT_VERIFIED\n"
             if receipt.get("decision") == DECISION else FAILURE + "\n"),
            encoding="utf-8")
        (output / "SHA256SUMS").write_text(
            "".join(f"{file_sha(output / name)}  {name}\n"
                    for name in ("receipt.json", "collect.log", "verify.log")),
            encoding="ascii")
    verified_output(output, source)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument("--self-test", action="store_true")
    mode.add_argument("--collect", action="store_true")
    mode.add_argument("--verify", action="store_true")
    p.add_argument("--output", type=Path)
    p.add_argument("--execution-source")
    args = p.parse_args()
    try:
        if args.self_test:
            self_test()
        else:
            need(args.output is not None and
                 args.execution_source is not None and
                 bool(re.fullmatch(r"[a-f0-9]{40}", args.execution_source)),
                 "MISSING_EXACT_SOURCE_OR_OUTPUT")
            need(tools.source_head() == args.execution_source,
                 "EXECUTING_WRONG_SOURCE")
            if args.collect:
                collect(args.output, args.execution_source)
            else:
                verified_output(args.output, args.execution_source)
                print("FE09_B2S2_SOURCE_AND_APX3_RECEIPT_VERIFIED")
    except (Denied, tools.GateFailure, OSError, ValueError) as exc:
        raise SystemExit(FAILURE + ": " + str(exc)) from None


if __name__ == "__main__":
    main()
