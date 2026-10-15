#!/usr/bin/env python3
"""#764 source-attested real pthread + 32-bit S1 wrap, research-only."""
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

import fe09_array_sdk_draft_qualification_r2a as tools
import fe09_b1b1_single_bf_qualification as b1
import fe09_b2s3_threaded_qualification as t0

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
BASE = "97e0704bd97e4709571e727d7f5c818e13bb8f97"
DECISION = "FE09_R2B2_S3_T1_EXACT_SOURCE_WRAP_RESEARCH_ONLY_NO_PUBLIC_ABI"
FAILURE = "FE09_R2B2_S3_T1_UNBOUND_FRAME_OR_UINT32_WRAP_NOT_ADMITTED"
TARGETS = ("native", "sanitized", "arm", "tsan")
MEMBERS = ("SHA256SUMS", "receipt.json", "collect.log", "verify.log")
ATTEST_C = HERE / "fe09_b2s3_t1_source_witness.c"
ATTEST_H = HERE / "fe09_b2s3_t1_source_witness.h"
TEST_C = HERE / "fe09_b2s3_t1_source_wrap_test.c"
OWN = (ATTEST_C, ATTEST_H, TEST_C, Path(__file__).resolve())
FROZEN_T0 = (
    HERE / "fe09_b2s3_private_bridge.c",
    HERE / "fe09_b2s3_private_bridge.h",
    HERE / "fe09_b2s3_threaded_bridge_test.c",
    HERE / "fe09_b2s3_threaded_qualification.py",
)
# The wrap fixture includes frozen S1.c + T0.c in a single private TU. Do
# NOT also separately compile S1.c: that would duplicate exported symbols.
SOURCES = (
    b1.SOURCE_C, b1.B1B0_C, b1.ARRAY_C, b1.NEW_C,
    t0.s2.SOURCE, HERE / "fe09_b2s3_private_bridge.c",
    ATTEST_C, TEST_C,
)
DISALLOWED = (
    "public_sdk_installed", "physical_clock_qualified",
    "ssc305_dut_qualified", "complete_c4_192kib_qualified",
    "render_only_liveness_qualified", "device_10ms_qualified",
    "real_four_mic_acoustic_gain",
)


class Denied(ValueError):
    pass


def need(value: bool, code: str) -> None:
    if not value:
        raise Denied(code)


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def file_sha(path: Path) -> str:
    need(path.is_file() and not path.is_symlink() and
         0 < path.stat().st_size <= 16 * 1024 * 1024,
         "MISSING_OR_OVERSIZE_" + path.name)
    return digest(path.read_bytes())


def frozen() -> dict:
    need(t0.BASE == "6fafcc868c5d3a0c4aa328e3d6ab54109cf5a741",
         "FROZEN_T0_PREDECESSOR_SHA_DRIFT")
    upstream = t0.old_sources()
    pinned = {}
    for path in FROZEN_T0:
        rel = str(path.relative_to(ROOT))
        before = subprocess.check_output(
            ["git", "-c", "safe.directory=" + str(ROOT),
             "show", BASE + ":" + rel],
            cwd=ROOT, timeout=30)
        need(0 < len(before) <= 16 * 1024 * 1024 and
             file_sha(path) == digest(before),
             "FROZEN_T0_BYTES_DRIFT_" + rel)
        pinned[rel] = digest(before)
    return {"t0_s1_s2_source_sha256":
            upstream["frozen_s1_s2_source_sha256"],
            "t0_unchanged_sha256": pinned,
            "t0_b2s0_contract_sha256":
            upstream["s2_b2s0_contract_sha256"]}


def identity(source: str) -> dict:
    need(re.fullmatch("[a-f0-9]{40}", source) is not None,
         "SOURCE_SHA_MALFORMED")
    return {
        "schema_version": 1, "source_commit": source,
        "stage": "FE09-R2B2-S3-T1-EXACT-PCM-WITNESS-REAL-ATOMIC-ROLLOVER",
        "preregistration": "https://github.com/jiying2007/audio-pipeline/issues/764",
        "protected_predecessor_main": BASE,
        "protected_predecessor_verify": 38764545602,
        "protected_predecessor_release": 38769621816,
        "source_sha256": {str(path.relative_to(ROOT)): file_sha(path)
                          for path in OWN},
        **frozen(),
        "source_role": "first-party-synthetic",
        **{key: False for key in DISALLOWED},
    }


def check_result(row: dict) -> None:
    schema = {
        "schema_version", "decision", "source_role",
        "public_sdk_installed", "physical_clock_qualified",
        "ssc305_dut_qualified", "actual_threaded_fixture",
        "profiles", "wrap_profiles", "profile_count",
        "wrap_profile_count", "total_frames", "negative_cases",
        "source_digest", "wrap_digest",
    }
    need(type(row) is dict and set(row) == schema, "TARGET_SCHEMA_DRIFT")
    need(type(row["schema_version"]) is int and
         row["schema_version"] == 1 and
         row["decision"] == DECISION and
         row["source_role"] == "first-party-synthetic" and
         row["public_sdk_installed"] is False and
         row["physical_clock_qualified"] is False and
         row["ssc305_dut_qualified"] is False and
         row["actual_threaded_fixture"] is True and
         type(row["profile_count"]) is int and row["profile_count"] == 48 and
         type(row["wrap_profile_count"]) is int and
         row["wrap_profile_count"] == 48 and
         type(row["total_frames"]) is int and row["total_frames"] == 9600 and
         type(row["negative_cases"]) is int and
         row["negative_cases"] >= 130 and
         all(type(row[name]) is str and
             re.fullmatch("[0-9a-f]{16}", row[name]) is not None
             for name in ("source_digest", "wrap_digest")),
         "TARGET_FALSE_RESULT_OR_RESOURCE_PROMOTION")
    scenes = (("C1_BASELINE", 1), ("C2_ULA", 2),
              ("C4_ULA", 4), ("C4_UCA", 4))
    expected = [(name, rate, mics, render, depth)
                for name, mics in scenes
                for rate in (16000, 32000, 48000)
                for render in (0, 1)
                for depth in (2, 4)]
    for which in ("profiles", "wrap_profiles"):
        entries = row[which]
        need(type(entries) is list and len(entries) == 48,
             "MISSING_48_REAL_STRESS_PROFILES_" + which)
        for item, (scene, rate, mics, render, depth) in zip(entries, expected):
            need(type(item) is dict and set(item) == {
                "scene", "rate", "mics", "render", "depth", "frames", "apx_hash",
            }, "PROFILE_KEYS_DRIFT_" + which)
            need(item["scene"] == scene and
                 type(item["rate"]) is int and item["rate"] == rate and
                 type(item["mics"]) is int and item["mics"] == mics and
                 type(item["render"]) is int and item["render"] == render and
                 type(item["depth"]) is int and item["depth"] == depth and
                 type(item["frames"]) is int and item["frames"] == 100 and
                 type(item["apx_hash"]) is str and
                 re.fullmatch("[0-9a-f]{16}", item["apx_hash"]) is not None,
                 "PROFILE_INCORRECT_" + which)


def check_targets(results: dict) -> None:
    need(type(results) is dict and set(results) == set(TARGETS),
         "MISSING_REAL_EXECUTION_TARGET")
    for result in results.values():
        check_result(result)
    master = results["native"]
    for target in TARGETS[1:]:
        need(results[target] == master,
             "CROSS_ISA_SOURCE_OR_APX3_BYTES_DRIFT_" + target)


def self_test() -> None:
    frozen()
    profiles = [
        {"scene": scene, "rate": rate, "mics": mics,
         "render": render, "depth": depth, "frames": 100,
         "apx_hash": "abcdef0123456789"}
        for scene, mics in (
            ("C1_BASELINE", 1), ("C2_ULA", 2),
            ("C4_ULA", 4), ("C4_UCA", 4))
        for rate in (16000, 32000, 48000)
        for render in (0, 1) for depth in (2, 4)
    ]
    valid = {
        "schema_version": 1, "decision": DECISION,
        "source_role": "first-party-synthetic",
        "public_sdk_installed": False, "physical_clock_qualified": False,
        "ssc305_dut_qualified": False, "actual_threaded_fixture": True,
        "profiles": profiles, "wrap_profiles": profiles,
        "profile_count": 48, "wrap_profile_count": 48,
        "total_frames": 9600, "negative_cases": 130,
        "source_digest": "0123456789abcdef", "wrap_digest": "abc0123456789def",
    }
    check_result(valid)
    negatives = 0
    for key, bad in (
        ("decision", FAILURE), ("source_role", "hardware"),
        ("public_sdk_installed", True), ("physical_clock_qualified", True),
        ("ssc305_dut_qualified", True), ("actual_threaded_fixture", False),
        ("profile_count", 47), ("wrap_profile_count", 47),
        ("total_frames", 8000), ("negative_cases", 80),
        ("source_digest", "bad"), ("wrap_digest", "bad"),
    ):
        item = json.loads(json.dumps(valid))
        item[key] = bad
        try:
            check_result(item)
        except Denied:
            negatives += 1
        else:
            raise Denied("SELF_TEST_FALSE_PROMOTION_" + key)
    for name in ("profiles", "wrap_profiles"):
        for key, bad in (
            ("scene", "C3"), ("rate", 24000), ("mics", 3),
            ("render", 2), ("depth", 8), ("frames", 99),
            ("apx_hash", "broken"),
        ):
            item = json.loads(json.dumps(valid))
            item[name][0][key] = bad
            try:
                check_result(item)
            except Denied:
                negatives += 1
            else:
                raise Denied("SELF_TEST_FALSE_PROFILE_" + name + "_" + key)
    need(negatives == 26, "SELF_TEST_INCOMPLETE")
    print("FE09_B2S3_T1_SOURCE_WRAP_SELF_TEST_PASS negatives=26")


def verify_output(out: Path, source: str) -> None:
    need(out.is_dir() and {x.name for x in out.iterdir()} == set(MEMBERS),
         "ARTIFACT_MEMBERSHIP_DRIFT")
    for name in MEMBERS:
        path = out / name
        limit = (1024 if name == "SHA256SUMS" else
                 65536 if name == "receipt.json" else
                 1048576 if name == "collect.log" else 256)
        need(path.is_file() and not path.is_symlink() and
             0 < path.stat().st_size <= limit,
             "RETAINED_MEMBER_BOUNDS_" + name)
    reference = "".join(f"{file_sha(out / name)}  {name}\n"
                        for name in ("receipt.json", "collect.log", "verify.log"))
    need((out / "SHA256SUMS").read_text("ascii") == reference,
         "SOURCE_BOUND_INNER_SHA_MISMATCH")
    receipt = tools.strict_json((out / "receipt.json").read_text("utf-8"))
    for key, value in identity(source).items():
        need(receipt.get(key) == value, "SOURCE_IDENTITY_DRIFT_" + key)
    need(receipt.get("decision") == DECISION and
         receipt.get("target_order") == list(TARGETS) and
         receipt.get("real_timestamp_witness_qualified") is False and
         receipt.get("exclusive_facade_owner_tested") is True and
         receipt.get("actual_uint32_wrap_exercised") is True and
         all(receipt.get(key) is False for key in DISALLOWED),
         "SOURCE_OR_FAKE_CLOCK_PROMOTION")
    binary = receipt.get("binary_sha256")
    need(type(binary) is dict and set(binary) == set(TARGETS) and
         all(type(x) is str and re.fullmatch("[0-9a-f]{64}", x)
             for x in binary.values()), "TARGET_BINARY_MISSING")
    check_targets(receipt.get("target_results"))
    need((out / "verify.log").read_text("ascii") ==
         "FE09_B2S3_T1_SOURCE_AND_WRAP_RECEIPT_VERIFIED\n",
         "VERIFY_MARKER_DRIFT")


def collect(out: Path, source: str) -> None:
    need(not out.exists(), "REFUSE_OVERWRITE")
    need(tools.source_head() == source, "GIT_SOURCE_MISMATCH")
    receipt = identity(source)
    receipt["decision"] = FAILURE
    logs: list[str] = []
    out.mkdir(parents=True)
    try:
        results, binaries, compilers = {}, {}, {}
        with tempfile.TemporaryDirectory(prefix="fe09-s3-t1-") as temp:
            wd = Path(temp)
            generated = wd / "include/audio_pipeline/audio_pipeline_build.h"
            generated.parent.mkdir(parents=True)
            generated.write_text(
                "#ifndef AUDIO_PIPELINE_AUDIO_PIPELINE_BUILD_H\n"
                "#define AUDIO_PIPELINE_AUDIO_PIPELINE_BUILD_H\n"
                "#define AP_BUILD_RESAMPLER_BANDLIMITED 1\n"
                "#endif\n", encoding="ascii")
            for target in TARGETS:
                compiler = ("arm-linux-gnueabihf-gcc" if target == "arm"
                            else "cc")
                need(shutil.which(compiler) is not None,
                     "COMPILER_MISSING_" + target)
                compilers[target] = tools.run(
                    [compiler, "--version"], logs).splitlines()[0]
                flags = [
                    compiler, "-std=c11", "-Wall", "-Wextra", "-Werror",
                    "-O2", "-ffp-contract=off", "-fno-fast-math",
                    "-pthread", "-DAP_BUILD_RESAMPLER_BANDLIMITED=1",
                    "-I" + str(wd / "include"), "-I" + str(ROOT / "src"),
                    "-I" + str(HERE),
                ]
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
                for i, path in enumerate(SOURCES):
                    obj = wd / f"{target}-{i}.o"
                    warn = [] if path in (b1.SOURCE_C, b1.ARRAY_C) else [
                        "-Wconversion", "-Wshadow", "-Wpedantic",
                    ]
                    tools.run(flags + warn + [
                        "-c", str(path), "-o", str(obj),
                    ], logs, timeout=150)
                    objects.append(str(obj))
                elf = wd / (target + ".elf")
                link = [compiler, *objects, "-lm", "-pthread", "-o", str(elf)]
                if target == "sanitized":
                    link += ["-fsanitize=address,undefined"]
                if target == "tsan":
                    link += ["-fsanitize=thread"]
                if target == "arm":
                    link += ["-march=armv7-a", "-mfpu=neon-vfpv4",
                             "-mfloat-abi=hard"]
                tools.run(link, logs, timeout=150)
                binaries[target] = file_sha(elf)
                if target == "arm":
                    need(shutil.which("qemu-arm") is not None and
                         Path("/usr/arm-linux-gnueabihf").is_dir(),
                         "ACTUAL_ARM32_QEMU_MISSING")
                    run = ["qemu-arm", "-L", "/usr/arm-linux-gnueabihf",
                           str(elf)]
                else:
                    run = [str(elf)]
                env = dict(os.environ)
                if target == "sanitized":
                    env.update({"ASAN_OPTIONS": "detect_leaks=0:halt_on_error=1",
                                "UBSAN_OPTIONS": "halt_on_error=1"})
                if target == "tsan":
                    env.update({"TSAN_OPTIONS": "halt_on_error=1:exitcode=66"})
                first = tools.strict_json(
                    tools.run(run, logs, timeout=240, env=env))
                second = tools.strict_json(
                    tools.run(run, logs, timeout=240, env=env))
                need(first == second, "NONDETERMINISTIC_T1_" + target)
                check_result(first)
                results[target] = first
        check_targets(results)
        receipt.update({
            "decision": DECISION,
            "target_order": list(TARGETS),
            "target_results": results,
            "compiler_version": compilers,
            "binary_sha256": binaries,
            "real_timestamp_witness_qualified": False,
            "exclusive_facade_owner_tested": True,
            "actual_uint32_wrap_exercised": True,
        })
    except Exception as exc:
        receipt["decision"] = FAILURE
        receipt["failure_type"] = type(exc).__name__
        receipt["failure_code"] = str(exc)[:200]
        # Tool.run captures failed compiler/fixture output in collect.log.
        # Emit only a bounded tail so the exact failing line is actionable
        # without downloading a ZIP or suppressing failure.
        import sys
        diagnostic = "\\n".join(logs[-5:])[-4500:]
        print("FE09_B2S3_T1_FAILED_EXECUTION_DIAGNOSTIC_BEGIN",
              file=sys.stderr)
        print(diagnostic, file=sys.stderr)
        print("FE09_B2S3_T1_FAILED_EXECUTION_DIAGNOSTIC_END",
              file=sys.stderr)
        raise
    finally:
        (out / "receipt.json").write_text(
            json.dumps(receipt, sort_keys=True, separators=(",", ":"),
                       allow_nan=False) + "\n", encoding="utf-8")
        (out / "collect.log").write_text(
            "\n".join(logs) + "\n", encoding="utf-8")
        (out / "verify.log").write_text(
            ("FE09_B2S3_T1_SOURCE_AND_WRAP_RECEIPT_VERIFIED\n"
             if receipt.get("decision") == DECISION else FAILURE + "\n"),
            encoding="ascii")
        (out / "SHA256SUMS").write_text(
            "".join(f"{file_sha(out / name)}  {name}\n"
                    for name in ("receipt.json", "collect.log", "verify.log")),
            encoding="ascii")
    verify_output(out, source)


def main() -> None:
    cli = argparse.ArgumentParser(description=__doc__)
    op = cli.add_mutually_exclusive_group(required=True)
    op.add_argument("--self-test", action="store_true")
    op.add_argument("--collect", action="store_true")
    op.add_argument("--verify", action="store_true")
    cli.add_argument("--output", type=Path)
    cli.add_argument("--execution-source")
    args = cli.parse_args()
    try:
        if args.self_test:
            self_test()
        else:
            need(args.output is not None and args.execution_source is not None,
                 "MISSING_SOURCE_OR_OUTPUT")
            need(tools.source_head() == args.execution_source,
                 "GIT_SOURCE_DOES_NOT_MATCH_EXECUTION")
            if args.collect:
                collect(args.output, args.execution_source)
            else:
                verify_output(args.output, args.execution_source)
                print("FE09_B2S3_T1_SOURCE_AND_WRAP_RECEIPT_VERIFIED")
    except (Denied, tools.GateFailure, OSError, ValueError,
            subprocess.CalledProcessError) as exc:
        raise SystemExit(FAILURE + ": " + str(exc)) from None


if __name__ == "__main__":
    main()
