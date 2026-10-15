#!/usr/bin/env python3
"""FE09-R2B2-S3 actual pthread SPSC+APX3 research qualification, nonshipping."""
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
import fe09_b2s1_private_queue_qualification as s1
import fe09_b2s2_private_apd_qualification as s2

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
BASE = "6fafcc868c5d3a0c4aa328e3d6ab54109cf5a741"
DECISION = "FE09_R2B2_S3_PRIVATE_THREADED_BRIDGE_RESEARCH_ONLY_NO_PUBLIC_ABI"
FAILURE = "FE09_R2B2_S3_CONCURRENCY_SOURCE_OR_RECORDER_NOT_ADMITTED"
MEMBERS = ("SHA256SUMS", "receipt.json", "collect.log", "verify.log")
TARGETS = ("native", "sanitized", "arm", "tsan")
SOURCES = (
    b1.SOURCE_C, b1.B1B0_C, b1.ARRAY_C, b1.NEW_C,
    s1.CORE, s2.SOURCE,
    HERE / "fe09_b2s3_private_bridge.c",
    HERE / "fe09_b2s3_threaded_bridge_test.c",
)
LOCAL_FILES = (
    HERE / "fe09_b2s3_private_bridge.h",
    HERE / "fe09_b2s3_private_bridge.c",
    HERE / "fe09_b2s3_threaded_bridge_test.c",
    Path(__file__).resolve(),
)
PRIOR_SOURCE_PATHS = tuple(sorted(set(
    [str(x.relative_to(ROOT)) for x in s1.FILES] +
    [str(x.relative_to(ROOT)) for x in s2.OWN] +
    list(s2.LEGACY))))
NOT_ADMITTED = (
    "public_sdk_installed", "ssc305_dut_qualified",
    "real_adc_dac_clock_authority", "full_duplex_aec_qualified",
    "physical_c4_acoustic_gain", "fully_recovered_render_mismatch",
    "device_10ms_or_192kib_qualified",
)


class Denied(ValueError):
    pass


def need(value: bool, reason: str) -> None:
    if not value:
        raise Denied(reason)


def sha_bytes(blob: bytes) -> str:
    return hashlib.sha256(blob).hexdigest()


def file_sha(path: Path) -> str:
    need(path.is_file() and not path.is_symlink() and
         0 < path.stat().st_size <= 16 * 1024 * 1024,
         "SOURCE_FILE_MISSING_OR_UNBOUNDED_" + path.name)
    return sha_bytes(path.read_bytes())


def old_sources() -> dict:
    need(s2.BASE == "580d2b565f62fc9b29ef9237b498898c89e51b05",
         "S2_QUALIFIED_PREDECESSOR_SHA_DRIFT")
    upstream = s2.frozen_source_identity()
    pins = {}
    for rel in PRIOR_SOURCE_PATHS:
        path = ROOT / rel
        command = ["git", "-c", "safe.directory=" + str(ROOT),
                   "show", BASE + ":" + rel]
        source = subprocess.check_output(command, cwd=ROOT, timeout=30)
        need(0 < len(source) <= 16 * 1024 * 1024,
             "FROZEN_S1_S2_SOURCE_UNREADABLE_" + rel)
        need(file_sha(path) == sha_bytes(source),
             "FROZEN_S1_S2_SOURCE_DRIFT_" + rel)
        pins[rel] = sha_bytes(source)
    return {
        "s2_b2s0_contract_sha256": upstream["s1_b2s0_contract_sha256"],
        "frozen_s1_s2_source_sha256": pins,
    }


def identity(source_commit: str) -> dict:
    need(re.fullmatch(r"[0-9a-f]{40}", source_commit) is not None,
         "EXECUTION_SOURCE_SHA_MALFORMED")
    return {
        "schema_version": 1,
        "stage": "FE09-R2B2-S3-THREADS-FIRST-PARTY-S1-APX3-S2",
        "preregistration": "https://github.com/jiying2007/audio-pipeline/issues/762",
        "protected_predecessor_main": BASE,
        "protected_predecessor_verify": 38750288576,
        "protected_predecessor_release": 38754899952,
        "source_commit": source_commit,
        "source_sha256": {
            str(p.relative_to(ROOT)): file_sha(p) for p in LOCAL_FILES
        },
        **old_sources(),
        "source_role": "first-party-synthetic",
        **{k: False for k in NOT_ADMITTED},
    }


def check_result(result: dict) -> None:
    keys = {
        "schema_version", "decision", "source_role",
        "physical_clock_qualified", "ssc305_dut_qualified",
        "public_sdk_installed", "actual_pthread_producers",
        "profiles", "profile_count", "total_frames",
        "negative_cases", "source_only_digest",
    }
    need(type(result) is dict and set(result) == keys, "TARGET_SCHEMA_DRIFT")
    need(type(result["schema_version"]) is int and
         result["schema_version"] == 1 and
         result["decision"] == DECISION and
         result["source_role"] == "first-party-synthetic" and
         result["physical_clock_qualified"] is False and
         result["ssc305_dut_qualified"] is False and
         result["public_sdk_installed"] is False and
         result["actual_pthread_producers"] is True and
         type(result["profile_count"]) is int and
         result["profile_count"] == 48 and
         type(result["total_frames"]) is int and
         result["total_frames"] == 4800 and
         type(result["negative_cases"]) is int and
         result["negative_cases"] >= 99 and
         type(result["source_only_digest"]) is str and
         re.fullmatch("[0-9a-f]{16}", result["source_only_digest"]),
         "FALSE_CONCURRENCY_OR_PRODUCT_QUALIFICATION")
    values = result["profiles"]
    need(type(values) is list and len(values) == 48,
         "THREADED_PROFILE_COUNT_DRIFT")
    scenes = (("C1_BASELINE", 1), ("C2_ULA", 2),
              ("C4_ULA", 4), ("C4_UCA", 4))
    expected = [(name, rate, mics, render, depth)
                for name, mics in scenes
                for rate in (16000, 32000, 48000)
                for render in (0, 1) for depth in (2, 4)]
    seen = set()
    for row, (scene, rate, mics, render, depth) in zip(values, expected):
        need(type(row) is dict and set(row) == {
            "scene", "rate", "mics", "render", "depth", "frames", "apx_hash",
        }, "THREADED_PROFILE_SCHEMA_DRIFT")
        need(row["scene"] == scene and
             type(row["rate"]) is int and row["rate"] == rate and
             type(row["mics"]) is int and row["mics"] == mics and
             type(row["render"]) is int and row["render"] == render and
             type(row["depth"]) is int and row["depth"] == depth and
             type(row["frames"]) is int and row["frames"] == 100 and
             type(row["apx_hash"]) is str and
             re.fullmatch("[0-9a-f]{16}", row["apx_hash"]) is not None,
             "THREADED_PROFILE_CONTENT_DRIFT")
        need((scene, rate, render, depth) not in seen,
             "DUPLICATED_STRESS_PROFILE")
        seen.add((scene, rate, render, depth))


def check_long(value: dict) -> None:
    need(type(value) is dict and set(value) == {
        "schema_version", "decision", "accepted_frames",
        "actual_threads", "real_clock_measured",
    } and value["schema_version"] == 1 and
         value["decision"] == "S3_NATIVE_HOSTED_STRESS_ONLY_NOT_DEVICE" and
         type(value["accepted_frames"]) is int and
         value["accepted_frames"] == 100000 and
         type(value["actual_threads"]) is int and
         value["actual_threads"] == 3 and
         value["real_clock_measured"] is False,
         "NATIVE_100K_STRESS_NOT_QUALIFIED")


def check_targets(rows: dict) -> None:
    need(type(rows) is dict and set(rows) == set(TARGETS),
         "MISSING_EXECUTED_TARGETS")
    for v in rows.values():
        check_result(v)
    master = rows["native"]
    for target in TARGETS[1:]:
        need(rows[target] == master,
             "CROSS_ISA_APX3_WIRE_IDENTITY_DRIFT_" + target)


def self_test() -> None:
    old_sources()
    rows = [{"scene": scene, "rate": rate, "mics": mics,
             "render": render, "depth": depth, "frames": 100,
             "apx_hash": "fedcba0123456789"}
            for scene, mics in (
                ("C1_BASELINE", 1), ("C2_ULA", 2),
                ("C4_ULA", 4), ("C4_UCA", 4))
            for rate in (16000, 32000, 48000)
            for render in (0, 1) for depth in (2, 4)]
    good = {
        "schema_version": 1, "decision": DECISION,
        "source_role": "first-party-synthetic",
        "physical_clock_qualified": False, "ssc305_dut_qualified": False,
        "public_sdk_installed": False, "actual_pthread_producers": True,
        "profiles": rows, "profile_count": 48,
        "total_frames": 4800, "negative_cases": 99,
        "source_only_digest": "0123456789abcdef",
    }
    check_result(good)
    count = 0
    for key, bad in (
        ("decision", FAILURE), ("source_role", "actual-room"),
        ("physical_clock_qualified", True), ("ssc305_dut_qualified", True),
        ("public_sdk_installed", True), ("actual_pthread_producers", False),
        ("profile_count", 47), ("total_frames", 10),
        ("negative_cases", 80), ("source_only_digest", "broken"),
    ):
        row = json.loads(json.dumps(good))
        row[key] = bad
        try:
            check_result(row)
        except Denied:
            count += 1
        else:
            raise Denied("FALSE_POSITIVE_SELF_TEST_" + key)
    for key, bad in (
        ("scene", "C3_FAKE"), ("rate", 24000), ("mics", 3),
        ("render", 2), ("depth", 8), ("frames", 99), ("apx_hash", "broken"),
    ):
        row = json.loads(json.dumps(good))
        row["profiles"][0][key] = bad
        try:
            check_result(row)
        except Denied:
            count += 1
        else:
            raise Denied("FALSE_PROFILE_SELF_TEST_" + key)
    need(count == 17, "INCOMPLETE_NEGATIVE_SELF_TEST")
    check_long({
        "schema_version": 1, "decision": "S3_NATIVE_HOSTED_STRESS_ONLY_NOT_DEVICE",
        "accepted_frames": 100000, "actual_threads": 3,
        "real_clock_measured": False,
    })
    print("FE09_B2S3_THREADED_BRIDGE_SELF_TEST_PASS negatives=17")


def verify_output(out: Path, source: str) -> None:
    need(out.is_dir() and {x.name for x in out.iterdir()} == set(MEMBERS),
         "ARTIFACT_MEMBERSHIP_DRIFT")
    for name in MEMBERS:
        p = out / name
        limit = (1024 if name == "SHA256SUMS" else
                 65536 if name == "receipt.json" else
                 1048576 if name == "collect.log" else 256)
        need(p.is_file() and not p.is_symlink() and
             0 < p.stat().st_size <= limit, "MEMBER_BOUNDS_" + name)
    manifest = "".join(f"{file_sha(out / n)}  {n}\n" for n in
                       ("receipt.json", "collect.log", "verify.log"))
    need((out / "SHA256SUMS").read_text("ascii") == manifest,
         "INNER_SHA256_MISMATCH")
    rec = tools.strict_json((out / "receipt.json").read_text("utf-8"))
    for name, value in identity(source).items():
        need(rec.get(name) == value, "SOURCE_DRIFT_" + name)
    need(rec.get("decision") == DECISION and
         rec.get("target_order") == list(TARGETS) and
         rec.get("native_100k_hosted_only") is True and
         rec.get("real_liveness_resynchronization_qualified") is False and
         all(rec.get(k) is False for k in NOT_ADMITTED),
         "INVALID_DEVICE_OR_AUTOMATIC_RECOVERY_CLAIM")
    bins = rec.get("binary_sha256")
    need(type(bins) is dict and set(bins) == set(TARGETS) and
         all(type(d) is str and
             re.fullmatch(r"[a-f0-9]{64}", d) for d in bins.values()),
         "UNQUALIFIED_TARGET_BINARY")
    check_long(rec.get("native_long_stress"))
    check_targets(rec.get("target_results"))
    need((out / "verify.log").read_text("ascii") ==
         "FE09_B2S3_SOURCE_AND_THREAD_BRIDGE_VERIFIED\n",
         "VERIFICATION_MARKER_DRIFT")


def collect(out: Path, source: str) -> None:
    need(not out.exists(), "REFUSE_OVERWRITE")
    need(tools.source_head() == source, "WRONG_EXECUTING_GIT_SOURCE")
    rec = identity(source)
    rec["decision"] = FAILURE
    logs: list[str] = []
    out.mkdir(parents=True)
    try:
        results, binaries, compilers = {}, {}, {}
        long_result = None
        with tempfile.TemporaryDirectory(prefix="fe09-b2s3-") as temp:
            wd = Path(temp)
            generated_header = wd / "include/audio_pipeline/audio_pipeline_build.h"
            generated_header.parent.mkdir(parents=True)
            generated_header.write_text(
                "#ifndef AUDIO_PIPELINE_AUDIO_PIPELINE_BUILD_H\n"
                "#define AUDIO_PIPELINE_AUDIO_PIPELINE_BUILD_H\n"
                "#define AP_BUILD_RESAMPLER_BANDLIMITED 1\n"
                "#endif\n", encoding="ascii")
            for target in TARGETS:
                compiler = ("arm-linux-gnueabihf-gcc" if target == "arm"
                            else "cc")
                need(shutil.which(compiler) is not None,
                     "MISSING_COMPILER_" + target)
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
                    warning_flags = [] if path in (b1.SOURCE_C, b1.ARRAY_C) else [
                        "-Wconversion", "-Wshadow", "-Wpedantic",
                    ]
                    tools.run(flags + warning_flags + [
                        "-c", str(path), "-o", str(obj)
                    ], logs, timeout=150)
                    objects.append(str(obj))
                executable = wd / (target + ".elf")
                link = [compiler, *objects, "-lm", "-pthread", "-o", str(executable)]
                if target == "sanitized":
                    link += ["-fsanitize=address,undefined"]
                if target == "tsan":
                    link += ["-fsanitize=thread"]
                if target == "arm":
                    link += ["-march=armv7-a", "-mfpu=neon-vfpv4",
                             "-mfloat-abi=hard"]
                tools.run(link, logs, timeout=150)
                binaries[target] = file_sha(executable)
                if target == "arm":
                    need(shutil.which("qemu-arm") is not None and
                         Path("/usr/arm-linux-gnueabihf").is_dir(),
                         "REAL_ARM_QEMU_ENVIRONMENT_MISSING")
                    run = ["qemu-arm", "-L", "/usr/arm-linux-gnueabihf",
                           str(executable)]
                else:
                    run = [str(executable)]
                env = dict(os.environ)
                if target == "sanitized":
                    env.update({"ASAN_OPTIONS": "detect_leaks=0:halt_on_error=1",
                                "UBSAN_OPTIONS": "halt_on_error=1"})
                if target == "tsan":
                    env.update({"TSAN_OPTIONS": "halt_on_error=1:exitcode=66"})
                first = tools.strict_json(tools.run(
                    run, logs, timeout=240, env=env))
                second = tools.strict_json(tools.run(
                    run, logs, timeout=240, env=env))
                need(first == second, "NONDETERMINISTIC_THREAD_RESULT_" + target)
                check_result(first)
                results[target] = first
                if target == "native":
                    long_result = tools.strict_json(tools.run(
                        run + ["--long"], logs, timeout=240, env=env))
                    check_long(long_result)
        check_targets(results)
        rec.update({
            "decision": DECISION,
            "target_order": list(TARGETS),
            "target_results": results,
            "native_long_stress": long_result,
            "native_100k_hosted_only": True,
            "real_liveness_resynchronization_qualified": False,
            "compiler_version": compilers,
            "binary_sha256": binaries,
        })
    except Exception as exc:
        rec["decision"] = FAILURE
        rec["failure_type"] = type(exc).__name__
        rec["failure_code"] = str(exc)[:200]
        raise
    finally:
        (out / "receipt.json").write_text(
            json.dumps(rec, sort_keys=True, separators=(",", ":"),
                       allow_nan=False) + "\n", encoding="utf-8")
        (out / "collect.log").write_text("\n".join(logs) + "\n",
                                         encoding="utf-8")
        (out / "verify.log").write_text(
            ("FE09_B2S3_SOURCE_AND_THREAD_BRIDGE_VERIFIED\n"
             if rec.get("decision") == DECISION else FAILURE + "\n"),
            encoding="utf-8")
        (out / "SHA256SUMS").write_text(
            "".join(f"{file_sha(out / n)}  {n}\n" for n in
                    ("receipt.json", "collect.log", "verify.log")),
            encoding="ascii")
    verify_output(out, source)


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
                 re.fullmatch("[0-9a-f]{40}", args.execution_source) is not None,
                 "MISSING_SOURCE_OR_OUTPUT")
            need(tools.source_head() == args.execution_source,
                 "WRONG_EXECUTING_GIT_SOURCE")
            if args.collect:
                collect(args.output, args.execution_source)
            else:
                verify_output(args.output, args.execution_source)
                print("FE09_B2S3_SOURCE_AND_THREAD_BRIDGE_VERIFIED")
    except (Denied, tools.GateFailure, ValueError, OSError,
            subprocess.CalledProcessError) as exc:
        raise SystemExit(FAILURE + ": " + str(exc)) from None


if __name__ == "__main__":
    main()
