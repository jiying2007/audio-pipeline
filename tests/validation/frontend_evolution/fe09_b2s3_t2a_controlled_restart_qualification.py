#!/usr/bin/env python3
"""S3-T2A: real pthread source-owned nonseamless epoch restart and quarantine.

An independently preregistered *control-plane only* change. No continuous
mic BF history, physical clock, product or public-ABI qualifications.
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

import fe09_array_sdk_draft_qualification_r2a as tools
import fe09_b1b1_single_bf_qualification as b1
import fe09_b2s3_t1_source_wrap_qualification as t1
import fe09_b2s3_threaded_qualification as t0
import fe09_b2s3_t2_f0_feasibility_qualification as f0

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
BASE = "d911547091c792c4cded48283499361833674917"
DECISION = "FE09_S3_T2A_NONSEAMLESS_RESTART_CONTROL_ONLY"
FAILURE = "FE09_S3_T2A_CONTROLLED_RESTART_NOT_ADMITTED"
TARGETS = ("native", "sanitized", "arm", "tsan")
MEMBERS = ("SHA256SUMS", "receipt.json", "collect.log", "verify.log")
TEST_C = HERE / "fe09_b2s3_t2a_controlled_restart_test.c"
CONTROL_C = HERE / "fe09_b2s3_t2a_controlled_restart.c"
CONTROL_H = HERE / "fe09_b2s3_t2a_controlled_restart.h"
OWN = (TEST_C, CONTROL_C, CONTROL_H, Path(__file__).resolve())
FROZEN = (
    *t1.OWN,
    *f0.OWN,
    HERE / "fe09_b2s3_t1_source_witness.c",
    HERE / "fe09_b2s1_private_queue.c",
    HERE / "fe09_b2s1_private_queue.h",
    HERE / "fe09_b2s3_private_bridge.c",
    HERE / "fe09_b2s3_threaded_bridge_test.c",
    HERE / "fe09_b2s2_private_apd.c",
)
# The test C directly includes the frozen S1 and T0 test C source.
SOURCES = (
    b1.SOURCE_C, b1.B1B0_C, b1.ARRAY_C, b1.NEW_C,
    t0.s2.SOURCE, HERE / "fe09_b2s1_private_queue.c",
    HERE / "fe09_b2s3_private_bridge.c",
    HERE / "fe09_b2s3_t1_source_witness.c", CONTROL_C, TEST_C,
)


class Denied(ValueError):
    pass


def need(cond: bool, reason: str) -> None:
    if not cond:
        raise Denied(reason)


def sha(blob: bytes) -> str:
    return hashlib.sha256(blob).hexdigest()


def file_sha(path: Path) -> str:
    need(path.is_file() and not path.is_symlink() and
         0 < path.stat().st_size <= 16 * 1024 * 1024,
         "MISSING_OR_OVERSIZE_SOURCE_" + path.name)
    return sha(path.read_bytes())


def frozen() -> dict:
    need(t1.BASE == "97e0704bd97e4709571e727d7f5c818e13bb8f97",
         "T1_QUALIFIED_MAIN_SHA_DRIFT")
    prior = t1.frozen()
    pins = {}
    for path in dict.fromkeys(FROZEN):
        rel = str(path.relative_to(ROOT))
        raw = subprocess.check_output(
            ["git", "-c", "safe.directory=" + str(ROOT),
             "show", BASE + ":" + rel], cwd=ROOT, timeout=30)
        need(0 < len(raw) <= 16 * 1024 * 1024 and file_sha(path) == sha(raw),
             "FROZEN_SRC_CHANGED_" + rel)
        pins[rel] = sha(raw)
    return {"t1_upstream_s1_s2_sha256":
            prior["t0_s1_s2_source_sha256"],
            "protected_t1_and_s1_sha256": pins}


def identity(commit: str) -> dict:
    need(re.fullmatch(r"[0-9a-f]{40}", commit) is not None,
         "SOURCE_SHA_NOT_EXACT")
    return {
        "schema_version": 1,
        "stage": "FE09-R2B2-S3-T2A-NONSEAMLESS-CONTROLLED-RESTART",
        "preregistration": "https://github.com/jiying2007/audio-pipeline/issues/769",
        "source_commit": commit,
        "protected_predecessor_main": BASE,
        "protected_predecessor_verify": 38856220869,
        "protected_predecessor_release": 38858932544,
        "source_role": "first-party-synthetic",
        "own_sha256": {str(p.relative_to(ROOT)): file_sha(p) for p in OWN},
        **frozen(),
        "real_render_recovery_qualified": False,
        "capture_bf_history_preserved_qualified": False,
        "physical_timebase_measured": False,
        "ssc305_device_qualified": False,
        "public_sdk_installed": False,
        "shipping_s1_modified": False,
        "legacy_apd2_modified": False,
    }


def check_result(result: dict) -> None:
    keys = {"schema_version", "decision", "source_role",
            "actual_postrestart_bf", "bf_continuity_preserved",
            "device_qualified", "public_sdk_admitted", "cases",
            "profile_count", "negative_checks", "digest"}
    need(type(result) is dict and set(result) == keys,
         "RESULT_SCHEMA_DRIFT")
    need(type(result["schema_version"]) is int and
         result["schema_version"] == 1 and
         result["decision"] == DECISION and
         result["source_role"] == "first-party-synthetic" and
         result["actual_postrestart_bf"] is True and
         result["bf_continuity_preserved"] is False and
         result["device_qualified"] is False and
         result["public_sdk_admitted"] is False and
         type(result["profile_count"]) is int and
         result["profile_count"] == 48 and
         type(result["negative_checks"]) is int and
         result["negative_checks"] >= 600 and
         type(result["digest"]) is str and
         re.fullmatch("[a-f0-9]{16}", result["digest"]) is not None,
         "FALSE_SEAMLESS_OR_DEVICE_PROMOTION")
    rows = result["cases"]
    required = [(scene, rate, render, depth)
                for scene in ("C1_BASELINE", "C2_ULA", "C4_ULA", "C4_UCA")
                for rate in (16000, 32000, 48000)
                for render in (0, 1) for depth in (2, 4)]
    need(type(rows) is list and len(rows) == 48,
         "PROFILE_COUNT_DRIFT")
    for row, (scene, rate, render, depth) in zip(rows, required):
        need(type(row) is dict and set(row) == {
            "scene", "rate", "render", "depth", "control_hash"
        } and row["scene"] == scene and
             type(row["rate"]) is int and row["rate"] == rate and
             type(row["render"]) is int and row["render"] == render and
             type(row["depth"]) is int and row["depth"] == depth and
             type(row["control_hash"]) is str and
             re.fullmatch("[a-f0-9]{16}", row["control_hash"]) is not None,
             "INVALID_PROFILE_OR_HASH_" + scene)


def check_targets(targets: dict) -> None:
    need(type(targets) is dict and set(targets) == set(TARGETS),
         "MISSING_REAL_NATIVE_SANITIZER_ARM_TSAN")
    for row in targets.values():
        check_result(row)
    for target in TARGETS[1:]:
        need(targets[target] == targets["native"],
             "CROSS_TARGET_CONTROL_VERDICT_MISMATCH_" + target)


def self_test() -> None:
    frozen()
    rows = [{"scene": scene, "rate": rate, "render": render,
             "depth": depth, "control_hash": "0123456789abcdef"}
            for scene in ("C1_BASELINE", "C2_ULA", "C4_ULA", "C4_UCA")
            for rate in (16000, 32000, 48000)
            for render in (0, 1) for depth in (2, 4)]
    good = {"schema_version": 1, "decision": DECISION,
            "source_role": "first-party-synthetic",
            "actual_postrestart_bf": True,
            "bf_continuity_preserved": False,
            "device_qualified": False,
            "public_sdk_admitted": False,
            "cases": rows, "profile_count": 48,
            "negative_checks": 600, "digest": "0123456789abcdef"}
    check_targets({target: good for target in TARGETS})
    count = 0
    for name, bad in (
        ("schema_version", 2), ("decision", FAILURE),
        ("source_role", "hardware"), ("actual_postrestart_bf", False),
        ("bf_continuity_preserved", True), ("device_qualified", True),
        ("public_sdk_admitted", True), ("profile_count", 47),
        ("negative_checks", 599), ("digest", "malformed")
    ):
        item = json.loads(json.dumps(good))
        item[name] = bad
        try:
            check_result(item)
        except Denied:
            count += 1
        else:
            raise Denied("FALSE_CONTROL_ADMISSION_" + name)
    for name, bad in (
        ("scene", "C3"), ("rate", 24000), ("render", 2),
        ("depth", 8), ("control_hash", "bad")
    ):
        item = json.loads(json.dumps(good))
        item["cases"][0][name] = bad
        try:
            check_result(item)
        except Denied:
            count += 1
        else:
            raise Denied("FALSE_PROFILE_ADMISSION_" + name)
    need(count == 15, "NEGATIVE_SELF_TEST_COUNT_DRIFT")
    print("FE09_S3_T2A_CONTROL_RESTART_SELF_TEST_PASS cases=15")


def verify_output(output: Path, commit: str) -> None:
    need(output.is_dir() and
         {x.name for x in output.iterdir()} == set(MEMBERS),
         "ARTIFACT_MEMBER_DRIFT")
    for member in MEMBERS:
        p = output / member
        limit = 1024 if member == "SHA256SUMS" else (
            65536 if member == "receipt.json" else
            1048576 if member == "collect.log" else 256)
        need(p.is_file() and not p.is_symlink() and
             0 < p.stat().st_size <= limit, "MEMBER_BOUNDS_" + member)
    manifest = "".join(f"{file_sha(output / n)}  {n}\n"
                       for n in ("receipt.json", "collect.log", "verify.log"))
    need((output / "SHA256SUMS").read_text("ascii") == manifest,
         "INDEPENDENT_FILE_SHA_MISMATCH")
    rec = tools.strict_json((output / "receipt.json").read_text("utf-8"))
    for key, value in identity(commit).items():
        need(rec.get(key) == value, "SOURCE_IDENTITY_CHANGED_" + key)
    need(rec.get("decision") == DECISION and
         rec.get("target_order") == list(TARGETS) and
         rec.get("controlled_restart_verified") is True and
         rec.get("real_render_recovery_qualified") is False and
         rec.get("capture_bf_history_preserved_qualified") is False and
         rec.get("physical_timebase_measured") is False and
         rec.get("ssc305_device_qualified") is False,
         "MISATTRIBUTED_RENDER_LIVENESS_AUTHORITY")
    binary = rec.get("binary_sha256")
    need(type(binary) is dict and set(binary) == set(TARGETS) and
         all(type(v) is str and re.fullmatch(r"[a-f0-9]{64}", v)
             for v in binary.values()), "MISSING_TARGET_BINARY")
    check_targets(rec.get("target_results"))
    need((output / "verify.log").read_text("utf-8") ==
         "FE09_S3_T2A_SOURCE_RESTART_CONTROL_VERIFIED\n",
         "VERIFY_MARKER_DRIFT")


def collect(output: Path, commit: str) -> None:
    need(not output.exists(), "REFUSE_OVERWRITE")
    need(tools.source_head() == commit, "WRONG_EXECUTING_SOURCE")
    receipt = identity(commit)
    receipt["decision"] = FAILURE
    logs: list[str] = []
    output.mkdir(parents=True)
    try:
        targets, versions, hashes = {}, {}, {}
        with tempfile.TemporaryDirectory(prefix="fe09-s3-t2a-") as temp:
            wd = Path(temp)
            hdr = wd / "include/audio_pipeline/audio_pipeline_build.h"
            hdr.parent.mkdir(parents=True)
            hdr.write_text(
                "#ifndef AUDIO_PIPELINE_AUDIO_PIPELINE_BUILD_H\n"
                "#define AUDIO_PIPELINE_AUDIO_PIPELINE_BUILD_H\n"
                "#define AP_BUILD_RESAMPLER_BANDLIMITED 1\n"
                "#endif\n", encoding="ascii")
            for target in TARGETS:
                compiler = "arm-linux-gnueabihf-gcc" if target == "arm" else "cc"
                need(shutil.which(compiler) is not None,
                     "REAL_COMPILER_NOT_AVAILABLE_" + target)
                versions[target] = tools.run(
                    [compiler, "--version"], logs).splitlines()[0]
                flags = [compiler, "-std=c11", "-Wall", "-Wextra", "-Werror",
                         "-O2", "-ffp-contract=off", "-fno-fast-math",
                         "-pthread", "-DAP_BUILD_RESAMPLER_BANDLIMITED=1",
                         "-I" + str(wd / "include"), "-I" + str(ROOT / "src"),
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
                for i, source in enumerate(SOURCES):
                    obj = wd / f"{target}-{i}.o"
                    warning = [] if source in (b1.SOURCE_C,b1.ARRAY_C) else [
                        "-Wconversion", "-Wshadow", "-Wpedantic"
                    ]
                    tools.run(flags + warning + [
                        "-c", str(source), "-o", str(obj)
                    ], logs, timeout=120)
                    objects.append(str(obj))
                elf = wd / (target + ".elf")
                link = [compiler, *objects, "-pthread", "-lm",
                        "-o", str(elf)]
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
                         "ARM32_QEMU_MISSING")
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
                second = tools.strict_json(
                    tools.run(command, logs, timeout=180, env=env))
                need(first == second, "NONDETERMINISTIC_NEGATIVE_RESULT_" + target)
                check_result(first)
                targets[target] = first
        check_targets(targets)
        receipt.update({
            "decision": DECISION, "target_order": list(TARGETS),
            "target_results": targets, "compiler_versions": versions,
            "binary_sha256": hashes, "controlled_restart_verified": True,
        })
    except Exception as exc:
        receipt["decision"] = FAILURE
        receipt["failure_type"] = type(exc).__name__
        receipt["failure_code"] = str(exc)[:200]
        import sys
        print("FE09_S3_T2A_EXECUTION_FAILURE_LOG_TAIL_BEGIN",
              file=sys.stderr)
        print("\n".join(logs[-5:])[-4000:], file=sys.stderr)
        print("FE09_S3_T2A_EXECUTION_FAILURE_LOG_TAIL_END",
              file=sys.stderr)
        raise
    finally:
        (output / "receipt.json").write_text(
            json.dumps(receipt, sort_keys=True, separators=(",", ":"),
                       allow_nan=False) + "\n", encoding="utf-8")
        (output / "collect.log").write_text(
            "\n".join(logs) + "\n", encoding="utf-8")
        (output / "verify.log").write_text(
            ("FE09_S3_T2A_SOURCE_RESTART_CONTROL_VERIFIED\n"
             if receipt.get("decision") == DECISION else FAILURE + "\n"),
            encoding="utf-8")
        (output / "SHA256SUMS").write_text(
            "".join(f"{file_sha(output / n)}  {n}\n"
                    for n in ("receipt.json","collect.log","verify.log")),
            encoding="ascii")
    verify_output(output, commit)


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
                 re.fullmatch(r"[0-9a-f]{40}", args.execution_source or "")
                 is not None, "OUTPUT_OR_SOURCE_IDENTITY_MISSING")
            need(tools.source_head() == args.execution_source,
                 "GIT_SOURCE_DIFFERENT")
            if args.collect:
                collect(args.output, args.execution_source)
            else:
                verify_output(args.output, args.execution_source)
                print("FE09_S3_T2A_SOURCE_RESTART_CONTROL_VERIFIED")
    except (Denied, tools.GateFailure, ValueError, OSError,
            subprocess.CalledProcessError) as exc:
        raise SystemExit(FAILURE + ": " + str(exc)) from None


if __name__ == "__main__":
    main()
