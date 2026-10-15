#!/usr/bin/env python3
"""FE09-R2B2-S1 actual first-party SRC/BF + private bounded SPSC queues.

Only native/sanitizer/AArch32 hosted synthetic research. Not installed SDK,
physical ADC/DAC clock, HIL, SSC305 p99, 192 KiB whole-system or AEC proof.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import tempfile

import fe09_array_sdk_draft_qualification_r2a as tools
import fe09_b1b1_single_bf_qualification as b1
import fe09_r2b2_runtime_recorder_preflight_s0 as b2

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
CORE = HERE / "fe09_b2s1_private_queue.c"
API = HERE / "fe09_b2s1_private_queue.h"
TEST = HERE / "fe09_b2s1_private_queue_test.c"
CFILES = (b1.SOURCE_C, b1.B1B0_C, b1.ARRAY_C, b1.NEW_C, CORE, TEST)
FILES = (b1.SOURCE_C, b1.SOURCE_H, b1.B1B0_C, b1.B1B0_H,
         b1.ARRAY_C, b1.ARRAY_H, b1.NEW_C, b1.NEW_H, CORE, API,
         TEST, Path(__file__).resolve())
TARGETS = ("native", "sanitized", "arm")
RATES = (16000, 32000, 48000)
SCENES = (("C1_BASELINE", 1, 0), ("C2_ULA", 2, 1),
          ("C4_ULA", 4, 1), ("C4_UCA", 4, 1))
MEMBERS = ("SHA256SUMS", "receipt.json", "collect.log", "verify.log")
DECISION = "FE09_R2B2_S1_PRIVATE_LINUX_QUEUE_RUNTIME_RESEARCH_ONLY_NO_PUBLIC_ABI"
FAILURE = "FE09_R2B2_S1_QUEUE_EPOCH_OR_SOURCE_NOT_ADMITTED"
BASE = "da8a48b29b482215a0086d3c58e6eed8fc943c28"


class Denied(ValueError):
    pass


def need(condition: bool, reason: str) -> None:
    if not condition:
        raise Denied(reason)


def sha(path: Path, cap: int = 16 * 1024 * 1024) -> str:
    need(path.is_file() and not path.is_symlink() and
         0 < path.stat().st_size <= cap, "SOURCE_MISSING_OR_OVERSIZE")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def frozen_sources() -> dict:
    b1.authority()
    contract, digest = b2.read_contract()
    b2.check_contract(contract)
    source_hashes = b2.check_sources(contract)
    need(len(source_hashes) == 13 and
         digest == "03ce2f77f6227866a4cd0e32c7e7c302bc57fe1d98c9ed4a3a15c029469761d6",
         "B2_S0_SOURCE_CONTRACT_DRIFT")
    return {
        "b2_s0_contract_sha256": digest,
        "b2_s0_source_sha256": source_hashes,
    }


def identity(source: str) -> dict:
    upstream = frozen_sources()
    return {
        "schema_version": 1, "source_commit": source,
        "stage": "FE09-R2B2-S1-PRIVATE-QUEUED-FIRST-PARTY-SRC-FIR33",
        "preregistration": "https://github.com/jiying2007/audio-pipeline/issues/755",
        "predecessor_main": BASE,
        "predecessor_verify": 38583607398,
        "predecessor_release": 38588624391,
        "source_sha256": {str(path.relative_to(ROOT)): sha(path) for path in FILES},
        **upstream,
        "shipping_src_changed": False,
        "public_sdk_3x_installed": False,
        "new_apd_v2_writer_installed": False,
        "new_apd_v2_parser_installed": False,
        "measured_real_bf_gain": False,
        "real_adc_clock_qualified": False,
        "ssc305_device_qualified": False,
        "complete_c4_192kib_qualified": False,
        "aec_qualified": False,
        "untrusted_audio_downloaded": False,
    }


def strict(content: str) -> dict:
    return tools.strict_json(content)


def check_result(data: dict) -> None:
    expected = {
        "schema_version", "decision", "source_role", "public_sdk_installed",
        "actual_apd_v2_writer", "real_adc_clock_qualified",
        "ssc305_dut_qualified", "full_c4_system_budget_qualified",
        "repeats", "profiles", "profile_count", "total_negatives",
        "max_state_bytes",
    }
    need(type(data) is dict and set(data) == expected,
         "TARGET_SCHEMA_OR_SOURCE_CHANGED")
    need(type(data["schema_version"]) is int and data["schema_version"] == 1
         and data["decision"] == DECISION and
         data["source_role"] == "first-party-synthetic" and
         all(data[field] is False for field in (
             "public_sdk_installed", "actual_apd_v2_writer",
             "real_adc_clock_qualified", "ssc305_dut_qualified",
             "full_c4_system_budget_qualified")) and
         type(data["repeats"]) is int and data["repeats"] == 2 and
         type(data["profile_count"]) is int and data["profile_count"] == 12 and
         type(data["max_state_bytes"]) is int and
         0 < data["max_state_bytes"] < 65536 and
         type(data["total_negatives"]) is int and
         data["total_negatives"] >= 600,
         "PRODUCT_OR_ACOUSTIC_PROMOTION")
    rows = data["profiles"]
    need(type(rows) is list and len(rows) == 12, "PROFILE_COUNT_DRIFT")
    row_keys = {
        "scene", "rate", "mics", "render", "depth", "frames", "negatives",
        "state_bytes", "work_bytes", "core_bytes",
        "capture_hash", "beam_hash", "render_hash"
    }
    total_negatives = 0
    for i, row in enumerate(rows):
        scene, n, render = SCENES[i % 4]
        rate = RATES[i // 4]
        need(type(row) is dict and set(row) == row_keys and
             row["scene"] == scene and row["rate"] == rate and
             row["mics"] == n and row["render"] == render and
             row["depth"] == (4 if i % 4 == 3 else 2) and
             type(row["frames"]) is int and row["frames"] == 100 and
             type(row["negatives"]) is int and row["negatives"] >= 50 and
             type(row["state_bytes"]) is int and
             0 < row["state_bytes"] < 65536 and
             type(row["work_bytes"]) is int and
             row["core_bytes"] < row["work_bytes"] < 65536 and
             type(row["core_bytes"]) is int and
             0 < row["core_bytes"] < row["state_bytes"] and
             all(type(row[k]) is str and
                 re.fullmatch(r"[0-9a-f]{16}", row[k]) is not None
                 for k in ("capture_hash", "beam_hash", "render_hash")),
             "INVALID_PROFILE_SCENES_OR_NUMERIC_WITNESS")
        total_negatives += row["negatives"]
    need(total_negatives == data["total_negatives"] and
         max(row["state_bytes"] for row in rows) == data["max_state_bytes"],
         "NEGATIVE_OR_STATE_ACCOUNTING_MISMATCH")


def check_targets(targets: dict) -> None:
    need(type(targets) is dict and set(targets) == set(TARGETS),
         "MISSING_ACTUAL_COMPILER_TARGETS")
    for target in TARGETS:
        check_result(targets[target])
    reference = targets["native"]["profiles"]
    for target in TARGETS[1:]:
        rows = targets[target]["profiles"]
        for expected, observed in zip(reference, rows):
            for key in ("scene", "rate", "mics", "render", "depth", "frames",
                        "negatives"):
                need(expected[key] == observed[key], "CROSS_TARGET_SCENE_DRIFT")
    # Per-target per-replay hashes must be bitwise equal; floats need not
    # match exactly across native, ASan, and QEMU processor/compiler targets.


def self_test() -> None:
    result = {
        "schema_version": 1, "decision": DECISION,
        "source_role": "first-party-synthetic",
        "public_sdk_installed": False, "actual_apd_v2_writer": False,
        "real_adc_clock_qualified": False, "ssc305_dut_qualified": False,
        "full_c4_system_budget_qualified": False, "repeats": 2,
        "profiles": [], "profile_count": 12, "total_negatives": 720,
        "max_state_bytes": 25000,
    }
    for rate in RATES:
        for scene, mics, render in SCENES:
            result["profiles"].append({
                "scene": scene, "rate": rate, "mics": mics,
                "render": render, "depth": 4 if scene == "C4_UCA" else 2,
                "frames": 100, "negatives": 60,
                "state_bytes": 25000, "work_bytes": 20000, "core_bytes": 4800,
                "capture_hash": "1" * 16, "beam_hash": "2" * 16,
                "render_hash": "3" * 16,
            })
    check_result(result)
    check_targets({k: copy.deepcopy(result) for k in TARGETS})
    for name, key, bad in [
        ("release", "decision", "RELEASE_ALLOWED"),
        ("device", "ssc305_dut_qualified", True),
        ("apd_v2", "actual_apd_v2_writer", True),
        ("source", "source_role", "real-room"),
        ("frames", "repeats", 1),
        ("count", "profile_count", 11),
        ("negatives", "total_negatives", 500),
    ]:
        c = copy.deepcopy(result)
        c[key] = bad
        try:
            check_result(c)
        except Denied:
            pass
        else:
            raise Denied("FALSE_PROMOTION_" + name)
    for key, bad in [
        ("rate", 24000), ("mics", 3), ("depth", 8),
        ("negatives", 10), ("frames", 99),
        ("beam_hash", "g" * 16), ("core_bytes", 0),
    ]:
        c = copy.deepcopy(result)
        c["profiles"][0][key] = bad
        try:
            check_result(c)
        except Denied:
            pass
        else:
            raise Denied("FALSE_PROFILE_" + key)
    frozen_sources()
    print("FE09_B2S1_PRIVATE_SPSC_SELF_TEST_PASS profiles=12 negatives=14")


def verify_output(out: Path, source: str) -> None:
    need(out.is_dir() and {x.name for x in out.iterdir()} == set(MEMBERS),
         "EVIDENCE_MEMBERSHIP_DRIFT")
    manifest = "".join(f"{sha(out / name)}  {name}\n"
                       for name in ("receipt.json", "collect.log", "verify.log"))
    need((out / "SHA256SUMS").read_text("ascii") == manifest,
         "INNER_SHA256_MISMATCH")
    rec = strict((out / "receipt.json").read_text("utf-8"))
    for field, value in identity(source).items():
        need(rec.get(field) == value, "SOURCE_IDENTITY_CHANGED_" + field)
    need(rec.get("decision") == DECISION and
         rec.get("target_order") == list(TARGETS) and
         rec.get("hosted_cpu_p99_is_device_budget") is False and
         rec.get("publication_permission") is False,
         "FALSE_SHIPPING_OR_RESOURCE_CLAIM")
    bins = rec.get("binary_sha256")
    need(type(bins) is dict and set(bins) == set(TARGETS) and
         all(type(x) is str and re.fullmatch(r"[0-9a-f]{64}", x)
             for x in bins.values()), "TARGET_BINARY_WITNESS_MISSING")
    check_targets(rec.get("target_results"))
    need((out / "verify.log").read_text("utf-8") ==
         "FE09_B2S1_SOURCE_AND_QUEUE_RECEIPT_VERIFIED\n",
         "VERIFICATION_MARKER_CHANGED")


def collect(out: Path, source: str) -> None:
    need(not out.exists(), "REFUSE_OVERWRITE")
    need(tools.source_head() == source, "WRONG_EXECUTING_GIT_SOURCE")
    rec = identity(source)
    rec["decision"] = FAILURE
    logs: list[str] = []
    out.mkdir(parents=True)
    try:
        results, binaries, compiler_versions = {}, {}, {}
        with tempfile.TemporaryDirectory(prefix="fe09-r2b2-s1-") as temp:
            wd = Path(temp)
            generated_header = wd / "include/audio_pipeline/audio_pipeline_build.h"
            generated_header.parent.mkdir(parents=True)
            generated_header.write_text(
                "#ifndef AUDIO_PIPELINE_AUDIO_PIPELINE_BUILD_H\n"
                "#define AUDIO_PIPELINE_AUDIO_PIPELINE_BUILD_H\n"
                "#define AP_BUILD_RESAMPLER_BANDLIMITED 1\n"
                "#endif\n", encoding="ascii")
            for target in TARGETS:
                compiler = "arm-linux-gnueabihf-gcc" if target == "arm" else "cc"
                need(shutil.which(compiler) is not None,
                     "COMPILER_NOT_INSTALLED_" + target)
                compiler_versions[target] = tools.run(
                    [compiler, "--version"], logs).splitlines()[0]
                base_flags = [
                    compiler, "-std=c11", "-Wall", "-Wextra", "-Werror",
                    "-O2", "-ffp-contract=off", "-fno-fast-math",
                    "-DAP_BUILD_RESAMPLER_BANDLIMITED=1",
                    "-I" + str(wd / "include"), "-I" + str(ROOT / "src"),
                    "-I" + str(HERE)
                ]
                if target == "sanitized":
                    base_flags += [
                        "-O1", "-g", "-fsanitize=address,undefined",
                        "-fno-omit-frame-pointer"
                    ]
                if target == "arm":
                    base_flags += [
                        "-march=armv7-a", "-mfpu=neon-vfpv4",
                        "-mfloat-abi=hard"
                    ]
                objects = []
                for i, path in enumerate(CFILES):
                    obj = wd / f"{target}-{i}.o"
                    flags = [] if path in (b1.SOURCE_C, b1.ARRAY_C) else [
                        "-Wconversion", "-Wshadow", "-Wpedantic"
                    ]
                    tools.run(base_flags + flags + [
                        "-c", str(path), "-o", str(obj)
                    ], logs, timeout=120)
                    objects.append(str(obj))
                elf = wd / (target + ".elf")
                link = [compiler, *objects, "-lm", "-o", str(elf)]
                if target == "sanitized":
                    link += ["-fsanitize=address,undefined"]
                if target == "arm":
                    link += ["-march=armv7-a", "-mfpu=neon-vfpv4",
                             "-mfloat-abi=hard"]
                tools.run(link, logs, timeout=120)
                binaries[target] = sha(elf)
                if target == "arm":
                    need(shutil.which("qemu-arm") is not None and
                         Path("/usr/arm-linux-gnueabihf").is_dir(),
                         "ARM_QEMU_ENVIRONMENT_MISSING")
                    command = ["qemu-arm", "-L", "/usr/arm-linux-gnueabihf",
                               str(elf)]
                else:
                    command = [str(elf)]
                env = dict(os.environ)
                if target == "sanitized":
                    env.update({"ASAN_OPTIONS": "detect_leaks=0:halt_on_error=1",
                                "UBSAN_OPTIONS": "halt_on_error=1"})
                first = strict(tools.run(command, logs, timeout=110, env=env))
                second = strict(tools.run(command, logs, timeout=110, env=env))
                need(first == second, "NONDETERMINISTIC_TARGET_" + target)
                check_result(first)
                results[target] = first
        check_targets(results)
        rec.update({
            "decision": DECISION, "target_order": list(TARGETS),
            "target_results": results,
            "binary_sha256": binaries,
            "compiler_version": compiler_versions,
            "execution_type": "hosted-synthetic-SPSC-first-party-only",
            "hosted_cpu_p99_is_device_budget": False,
            "publication_permission": False,
        })
    except Exception as exc:
        rec["decision"] = FAILURE
        rec["failure_type"] = type(exc).__name__
        rec["failure_code"] = str(exc)[:180]
        raise
    finally:
        (out / "receipt.json").write_text(
            json.dumps(rec, sort_keys=True, separators=(",", ":"),
                       allow_nan=False) + "\n", encoding="utf-8")
        (out / "collect.log").write_text(
            "\n".join(logs) + "\n", encoding="utf-8")
        (out / "verify.log").write_text(
            "FE09_B2S1_SOURCE_AND_QUEUE_RECEIPT_VERIFIED\n"
            if rec.get("decision") == DECISION else FAILURE + "\n",
            encoding="utf-8")
        (out / "SHA256SUMS").write_text(
            "".join(f"{sha(out / name)}  {name}\n"
                    for name in ("receipt.json", "collect.log", "verify.log")),
            encoding="ascii")
    verify_output(out, source)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    arg = p.add_mutually_exclusive_group(required=True)
    arg.add_argument("--self-test", action="store_true")
    arg.add_argument("--collect", action="store_true")
    arg.add_argument("--verify", action="store_true")
    p.add_argument("--output", type=Path)
    p.add_argument("--execution-source")
    args = p.parse_args()
    try:
        if args.self_test:
            self_test()
        else:
            need(args.output is not None and args.execution_source is not None
                 and re.fullmatch(r"[0-9a-f]{40}", args.execution_source)
                 is not None, "EXACT_SOURCE_AND_OUTPUT_REQUIRED")
            if args.collect:
                collect(args.output, args.execution_source)
            else:
                need(tools.source_head() == args.execution_source,
                     "SOURCE_HEAD_DRIFT")
                verify_output(args.output, args.execution_source)
            print(DECISION if args.collect else
                  "FE09_B2S1_SOURCE_AND_QUEUE_RECEIPT_VERIFIED")
    except (Denied, tools.GateFailure, ValueError, OSError, KeyError,
            AssertionError, TypeError) as exc:
        print(FAILURE + ": " + str(exc))
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
