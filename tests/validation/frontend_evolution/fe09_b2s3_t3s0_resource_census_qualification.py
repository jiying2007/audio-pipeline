#!/usr/bin/env python3
"""#787: Native/ASan+UBSan/ARM-QEMU/TSan ACTUAL compiled first-party memory census.

The numeric evidence is sizeof + exact existing BF/S2 allocation queries,
not product RAM, process RSS, stack high-water, IO durability or DUT timing.
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
import fe09_b2s3_t2c0_quiescent_fallback_qualification as c0

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
BASE = "40581c71c07d4a9de8073c2f73a5d0f2293a3e1f"
DECISION = "FE09_T3S0_COMPILER_AND_FIRST_PARTY_BF_RESOURCE_OVER_BUDGET_NO_DEVICE_AUTHORITY"
FAILURE = "FE09_T3S0_COMPILED_RESOURCE_EVIDENCE_NOT_ADMITTED"
TARGETS = ("native", "sanitized", "arm", "tsan")
MEMBERS = ("SHA256SUMS", "receipt.json", "collect.log", "verify.log")
TEST_C = HERE / "fe09_b2s3_t3s0_resource_census_test.c"
OWN = (TEST_C, Path(__file__).resolve())
FROZEN = tuple(dict.fromkeys((*c0.FROZEN, *c0.OWN)))
SOURCES = (*c0.SOURCES[:-1], TEST_C)
BUDGET = 196608
RAW_TWO_ARCHIVES = 255552
KEYS = {
    "scene", "rate", "depth", "render", "bf_state", "bf_work",
    "source_state", "array_state", "queue_reserved", "ring_capture",
    "ring_render", "b0_adapter", "apx3_store", "apx3_arrays",
    "apx3_one_frame", "single_owned_min", "dual_owned_min",
    "dual_exceeds_192kib", "complete_device_memory_qualified"
}
FALSE_FLAGS = (
    "whole_device_memory_qualified", "device_192kib_pass",
    "durable_rolling_recorder_qualified", "physical_ssc305_qualified",
    "hardened_stack_rss_measured", "public_sdk_installed"
)
SCENES = ("C1_BASELINE", "C2_ULA", "C4_ULA", "C4_UCA")


class NotAdmitted(ValueError):
    pass


def need(value: object, reason: str) -> None:
    if not value:
        raise NotAdmitted(reason)


def digest(path: Path) -> str:
    need(path.is_file() and not path.is_symlink() and
         0 < path.stat().st_size <= 16 * 1024 * 1024,
         "FILE_MISSING_OR_OVERSIZE_" + path.name)
    return hashlib.sha256(path.read_bytes()).hexdigest()


def pins() -> dict[str, str]:
    need(c0.BASE == "b29252d182e5ba8f76313ed1c75b41221e5b372a",
         "FROZEN_T2_C0_LINEAGE_DRIFT")
    c0.source_pins()
    results: dict[str, str] = {}
    for file in FROZEN:
        rel = file.relative_to(ROOT).as_posix()
        original = subprocess.check_output(
            ["git", "-c", "safe.directory=" + str(ROOT),
             "show", BASE + ":" + rel], cwd=ROOT, timeout=30)
        need(0 < len(original) <= 16 * 1024 * 1024 and
             hashlib.sha256(original).hexdigest() == digest(file),
             "FROZEN_SOURCE_CHANGED_" + rel)
        results[rel] = hashlib.sha256(original).hexdigest()
    return results


def identity(commit: str) -> dict:
    need(type(commit) is str and
         re.fullmatch(r"[0-9a-f]{40}", commit) is not None,
         "SOURCE_NOT_EXACT_HEAD")
    return {
        "schema_version": 1,
        "stage": "FE09-S3-T3-S0-EXACT-COMPILED-CALLER-OWNED-MEMORY-CENSUS",
        "preregistration": "https://github.com/jiying2007/audio-pipeline/issues/787",
        "source_commit": commit,
        "protected_predecessor_main": BASE,
        "protected_predecessor_verify": 39041419374,
        "protected_predecessor_release": 39044613074,
        "source_role": "first-party-synthetic",
        "immutable_predecessor_sha256": pins(),
        "own_source_sha256": {
            p.relative_to(ROOT).as_posix(): digest(p) for p in OWN
        },
        "resource_measurement": "compiled_sizes_and_first_party_query_only",
        "complete_192kib_device_measured": False,
        "process_rss_measured": False,
        "stack_highwater_measured": False,
        "physical_adc_dac_clock_measured": False,
        "durable_archive_qualified": False,
        "new_rolling_recorder_built": False,
        "ssc305_hil_qualified": False,
        "public_sdk_installed": False,
        "shipping_dsp_modified": False,
        "legacy_apd2_modified": False,
    }


def verify_result(result: dict) -> None:
    need(type(result) is dict and set(result) == {
        "schema_version", "decision", "source_role",
        "measurement_class", *FALSE_FLAGS,
        "static_two_archive_arrays", "device_budget_bytes",
        "profile_rows", "profile_count", "negative_checks",
    }, "RESOURCE_SCHEMA_DRIFT")
    need(type(result["schema_version"]) is int and
         result["schema_version"] == 1 and
         result["decision"] == DECISION and
         result["source_role"] == "first-party-synthetic" and
         result["measurement_class"] ==
         "declared_caller_owned_lower_bound_not_rss" and
         all(result[k] is False for k in FALSE_FLAGS) and
         type(result["static_two_archive_arrays"]) is int and
         result["static_two_archive_arrays"] == RAW_TWO_ARCHIVES and
         type(result["device_budget_bytes"]) is int and
         result["device_budget_bytes"] == BUDGET and
         type(result["profile_count"]) is int and
         result["profile_count"] == 48 and
         type(result["negative_checks"]) is int and
         result["negative_checks"] == 720,
         "FALSE_192KIB_OR_HARDWARE_AUTHORITY")
    rows = result["profile_rows"]
    need(type(rows) is list and len(rows) == 48, "RESOURCE_MATRIX_MISSING")
    expected = [(scene, rate, d, render)
                for scene in SCENES for rate in (16000, 32000, 48000)
                for d in (2, 4) for render in (0, 1)]
    observed = {}
    for row, (scene, rate, depth, render) in zip(rows, expected):
        need(type(row) is dict and set(row) == KEYS,
             "RESOURCE_ROW_SCHEMA_CHANGED")
        need(row["scene"] == scene and
             type(row["rate"]) is int and row["rate"] == rate and
             type(row["depth"]) is int and row["depth"] == depth and
             type(row["render"]) is int and row["render"] == render and
             row["dual_exceeds_192kib"] is True and
             row["complete_device_memory_qualified"] is False,
             "RESOURCE_SOURCE_OR_POLICY_WRONG")
        nums = {k: v for k, v in row.items()
                if k not in ("scene", "dual_exceeds_192kib",
                             "complete_device_memory_qualified")}
        need(all(type(value) is int and 0 <= value <= (1 << 32)
                 for value in nums.values()),
             "RESOURCE_ARITHMETIC_OR_TYPE_UNSAFE")
        need(row["apx3_arrays"] == RAW_TWO_ARCHIVES // 2 and
             row["apx3_store"] >= row["apx3_arrays"] and
             row["queue_reserved"] >=
             row["ring_capture"] + row["ring_render"] and
             row["bf_state"] >=
             row["source_state"] + row["array_state"] and
             row["bf_work"] >= row["bf_state"] and
             row["apx3_one_frame"] >= 128 + 32 and
             row["apx3_one_frame"] <= 5120,
             "FROZEN_FIRST_PARTY_STRUCT_OR_S2_LAYOUT_DRIFT")
        known = (row["queue_reserved"] + row["b0_adapter"] +
                 row["apx3_store"] + row["bf_state"] + row["bf_work"])
        session = row["single_owned_min"] - known
        shared = row["dual_owned_min"] - 2 * row["single_owned_min"]
        need(4 <= session <= 64 and 32 <= shared <= 1024 and
             row["dual_owned_min"] > BUDGET and
             row["dual_owned_min"] >= RAW_TWO_ARCHIVES and
             row["single_owned_min"] > row["apx3_store"],
             "DOUBLE_RETAINED_SESSION_IMPOSSIBLE_FIT_NOT_FLAGGED")
        pair = (scene, rate, render)
        signature = (row["bf_state"], row["bf_work"],
                     row["queue_reserved"], row["ring_capture"],
                     row["ring_render"], row["b0_adapter"],
                     row["apx3_store"], row["single_owned_min"],
                     row["dual_owned_min"], row["apx3_one_frame"])
        if pair in observed:
            need(observed[pair] == signature,
                 "FAKE_DEPTH_DEPENDENT_FIXED_FOUR_SLOT_MEMORY")
        else:
            observed[pair] = signature


def check_targets(items: dict) -> None:
    need(type(items) is dict and set(items) == set(TARGETS),
         "MISSING_ACTUAL_NATIVE_ASAN_ARM_TSAN")
    for data in items.values():
        verify_result(data)
    first = items["native"]
    for target in TARGETS[1:]:
        data = items[target]
        for key in ("schema_version", "decision", "source_role",
                    "measurement_class", "static_two_archive_arrays",
                    "device_budget_bytes", "profile_count",
                    "negative_checks", *FALSE_FLAGS):
            need(data[key] == first[key],
                 "CROSS_TARGET_AUTHORITY_DRIFT_" + target)
        for row, control in zip(data["profile_rows"], first["profile_rows"]):
            for key in ("scene", "rate", "depth", "render",
                        "apx3_arrays", "apx3_one_frame",
                        "dual_exceeds_192kib",
                        "complete_device_memory_qualified"):
                need(row[key] == control[key],
                     "CROSS_ISA_PROTOCOL_DRIFT_" + target + "_" + key)
        # ABI sizeof/pointer padding legitimately differs on ARM32.


def self_test() -> None:
    pins()
    row = dict(scene="C1_BASELINE", rate=16000, depth=2, render=0,
               bf_state=8192, bf_work=10000, source_state=4096,
               array_state=2048, queue_reserved=22000,
               ring_capture=16000, ring_render=4000,
               b0_adapter=1500, apx3_store=127800,
               apx3_arrays=127776, apx3_one_frame=500,
               single_owned_min=169508, dual_owned_min=339196,
               dual_exceeds_192kib=True,
               complete_device_memory_qualified=False)
    row["single_owned_min"] = (row["queue_reserved"] +
                               row["b0_adapter"] + row["apx3_store"] +
                               row["bf_state"] + row["bf_work"] + 16)
    row["dual_owned_min"] = 2 * row["single_owned_min"] + 180
    rows = []
    for scene in SCENES:
        for rate in (16000, 32000, 48000):
            for depth in (2, 4):
                for render in (0, 1):
                    current = dict(row)
                    current.update(scene=scene, rate=rate,
                                   depth=depth, render=render)
                    rows.append(current)
    valid = {
        "schema_version": 1, "decision": DECISION,
        "source_role": "first-party-synthetic",
        "measurement_class": "declared_caller_owned_lower_bound_not_rss",
        **{k: False for k in FALSE_FLAGS},
        "static_two_archive_arrays": RAW_TWO_ARCHIVES,
        "device_budget_bytes": BUDGET,
        "profile_rows": rows,
        "profile_count": 48, "negative_checks": 720
    }
    check_targets({target: valid for target in TARGETS})
    failed = 0
    mutations = [
        ("decision", FAILURE), ("source_role", "real-hardware"),
        ("whole_device_memory_qualified", True),
        ("device_192kib_pass", True),
        ("physical_ssc305_qualified", True),
        ("durable_rolling_recorder_qualified", True),
        ("hardened_stack_rss_measured", True),
        ("public_sdk_installed", True),
        ("profile_count", 47), ("negative_checks", 719),
        ("static_two_archive_arrays", 196608),
    ]
    for key, bad in mutations:
        trial = json.loads(json.dumps(valid))
        trial[key] = bad
        try:
            verify_result(trial)
        except NotAdmitted:
            failed += 1
        else:
            raise NotAdmitted("SELFTEST_FALSE_SOURCE_ADMISSION_" + key)
    for key, bad in (
        ("scene", "C3"), ("rate", 24000), ("depth", 8),
        ("render", 2), ("bf_state", 0), ("bf_work", 1),
        ("queue_reserved", 1), ("apx3_arrays", 1),
        ("apx3_one_frame", 999999),
        ("dual_owned_min", 160000),
        ("complete_device_memory_qualified", True),
    ):
        trial = json.loads(json.dumps(valid))
        trial["profile_rows"][0][key] = bad
        try:
            verify_result(trial)
        except NotAdmitted:
            failed += 1
        else:
            raise NotAdmitted("SELFTEST_FALSE_RESOURCE_FIT_" + key)
    need(failed == 22, "SELFTEST_NEGATIVE_MATRIX_NOT_EXECUTED")
    print("FE09_T3S0_RESOURCE_POLICY_SELFTEST_PASS negatives=22")


def verify_output(output: Path, commit: str) -> None:
    need(output.is_dir() and not output.is_symlink() and
         {p.name for p in output.iterdir()} == set(MEMBERS),
         "ARTIFACT_MISSING_OR_EXTRA_MEMBER")
    caps = {"SHA256SUMS": 512, "receipt.json": 262144,
            "collect.log": 4194304, "verify.log": 256}
    for name in MEMBERS:
        p = output / name
        need(p.is_file() and not p.is_symlink() and
             0 < p.stat().st_size <= caps[name],
             "ARTIFACT_MEMBER_BOUND_" + name)
    manifest = "".join(f"{digest(output / p)}  {p}\n" for p in
                       ("receipt.json", "collect.log", "verify.log"))
    need((output / "SHA256SUMS").read_text("ascii") == manifest,
         "INNER_SOURCE_SHA256_MISMATCH")
    report = tools.strict_json((output / "receipt.json").read_text("utf-8"))
    for key, value in identity(commit).items():
        need(report.get(key) == value, "IMMUTABLE_SOURCE_RECEIPT_DRIFT_" + key)
    need(report.get("decision") == DECISION and
         report.get("actual_compiled_targets_complete") is True and
         report.get("target_order") == list(TARGETS) and
         report.get("device_memory_admitted") is False and
         report.get("only_declared_buffers_counted") is True,
         "FALSE_DEVICE_QUALIFICATION")
    hashes = report.get("binary_sha256")
    versions = report.get("compiler_versions")
    need(type(hashes) is dict and set(hashes) == set(TARGETS) and
         all(type(x) is str and re.fullmatch(r"[a-f0-9]{64}", x)
             for x in hashes.values()) and
         type(versions) is dict and set(versions) == set(TARGETS) and
         all(type(x) is str and x for x in versions.values()),
         "MISSING_ELF_OR_COMPILER_SHA_AUTHORITY")
    check_targets(report.get("target_results"))
    need((output / "verify.log").read_text("ascii") ==
         "FE09_T3S0_COMPILED_FIRST_PARTY_MEMORY_OVER_BUDGET_VERIFIED\n",
         "COMPILED_MODEL_MARKER_CHANGED")


def collect(output: Path, commit: str) -> None:
    need(not output.exists() and not output.is_symlink(),
         "REFUSE_ARTIFACT_OVERWRITE")
    need(tools.source_head() == commit, "GIT_HEAD_NOT_CURRENT")
    report = identity(commit)
    report.update(decision=FAILURE, actual_compiled_targets_complete=False,
                  device_memory_admitted=False,
                  only_declared_buffers_counted=True)
    logs: list[str] = []
    output.mkdir(parents=True)
    try:
        targets, versions, binaries = {}, {}, {}
        with tempfile.TemporaryDirectory(prefix="fe09-t3s0-") as tmp:
            wd = Path(tmp)
            header = wd / "include/audio_pipeline/audio_pipeline_build.h"
            header.parent.mkdir(parents=True)
            header.write_text(
                "#ifndef AUDIO_PIPELINE_AUDIO_PIPELINE_BUILD_H\n"
                "#define AUDIO_PIPELINE_AUDIO_PIPELINE_BUILD_H\n"
                "#define AP_BUILD_RESAMPLER_BANDLIMITED 1\n"
                "#endif\n", encoding="ascii")
            for target in TARGETS:
                compiler = ("arm-linux-gnueabihf-gcc" if target == "arm"
                            else "cc")
                need(shutil.which(compiler) is not None,
                     "MISSING_REAL_TARGET_COMPILER_" + target)
                versions[target] = tools.run(
                    [compiler, "--version"], logs).splitlines()[0]
                flags = [compiler, "-std=c11", "-Wall", "-Wextra", "-Werror",
                         "-O2", "-ffp-contract=off", "-fno-fast-math",
                         "-pthread", "-DAP_BUILD_RESAMPLER_BANDLIMITED=1",
                         "-I" + str(wd/"include"), "-I" + str(ROOT/"src"),
                         "-I" + str(HERE)]
                if target in ("sanitized", "tsan"):
                    flags += ["-O1", "-g",
                              "-fsanitize=thread" if target == "tsan"
                              else "-fsanitize=address,undefined",
                              "-fno-omit-frame-pointer"]
                if target == "arm":
                    flags += ["-march=armv7-a", "-mfpu=neon-vfpv4",
                              "-mfloat-abi=hard"]
                objects = []
                for index, source in enumerate(SOURCES):
                    obj = wd / f"{target}-{index}.o"
                    exempt = (c0.b1.b1.b0.b1.SOURCE_C,
                              c0.b1.b1.b0.b1.ARRAY_C)
                    warnings = ([] if source in exempt else
                                ["-Wconversion", "-Wshadow", "-Wpedantic"])
                    tools.run(flags + warnings +
                              ["-c", str(source), "-o", str(obj)],
                              logs, timeout=120)
                    objects.append(str(obj))
                binary = wd / (target + ".elf")
                link = [compiler, *objects, "-pthread", "-lm", "-o",
                        str(binary)]
                if target == "sanitized":
                    link.append("-fsanitize=address,undefined")
                if target == "tsan":
                    link.append("-fsanitize=thread")
                if target == "arm":
                    link += ["-march=armv7-a", "-mfpu=neon-vfpv4",
                             "-mfloat-abi=hard"]
                tools.run(link, logs, timeout=120)
                binaries[target] = digest(binary)
                command = [str(binary)]
                if target == "arm":
                    need(shutil.which("qemu-arm") is not None and
                         Path("/usr/arm-linux-gnueabihf").is_dir(),
                         "ARM32_QEMU_OR_TOOLCHAIN_NOT_AVAILABLE")
                    command = ["qemu-arm", "-L",
                               "/usr/arm-linux-gnueabihf", str(binary)]
                env = dict(os.environ)
                if target == "sanitized":
                    env.update({"ASAN_OPTIONS": "detect_leaks=0:halt_on_error=1",
                                "UBSAN_OPTIONS": "halt_on_error=1"})
                if target == "tsan":
                    env.update({"TSAN_OPTIONS": "halt_on_error=1:exitcode=66"})
                first = tools.strict_json(
                    tools.run(command, logs, timeout=180, env=env))
                repeat = tools.strict_json(
                    tools.run(command, logs, timeout=180, env=env))
                need(first == repeat, "ACTUAL_COMPILED_BYTE_REPLAY_DRIFT_"+target)
                verify_result(first)
                targets[target] = first
        check_targets(targets)
        report.update(decision=DECISION, actual_compiled_targets_complete=True,
                      target_order=list(TARGETS), target_results=targets,
                      compiler_versions=versions, binary_sha256=binaries)
    except Exception as exc:
        report.update(decision=FAILURE, actual_compiled_targets_complete=False,
                      failure_type=type(exc).__name__,
                      failure_code=str(exc)[:250])
        import sys
        print("FE09_T3S0_NEGATIVE_EXECUTION_LOG_BEGIN", file=sys.stderr)
        print("\n".join(logs[-10:])[-5500:], file=sys.stderr)
        print("FE09_T3S0_NEGATIVE_EXECUTION_LOG_END", file=sys.stderr)
        raise
    finally:
        (output / "receipt.json").write_text(
            json.dumps(report, sort_keys=True, separators=(",", ":"),
                       allow_nan=False) + "\n", encoding="utf-8")
        (output / "collect.log").write_text("\n".join(logs) + "\n",
                                            encoding="utf-8")
        (output / "verify.log").write_text(
            ("FE09_T3S0_COMPILED_FIRST_PARTY_MEMORY_OVER_BUDGET_VERIFIED\n"
             if report.get("decision") == DECISION else FAILURE + "\n"),
            encoding="ascii")
        (output / "SHA256SUMS").write_text(
            "".join(f"{digest(output / item)}  {item}\n" for item in
                    ("receipt.json", "collect.log", "verify.log")),
            encoding="ascii")
    verify_output(output, commit)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    modes = p.add_mutually_exclusive_group(required=True)
    modes.add_argument("--self-test", action="store_true")
    modes.add_argument("--collect", action="store_true")
    modes.add_argument("--verify", action="store_true")
    p.add_argument("--output", type=Path)
    p.add_argument("--execution-source")
    args = p.parse_args()
    try:
        if args.self_test:
            self_test()
        else:
            need(args.output is not None and
                 type(args.execution_source) is str and
                 re.fullmatch(r"[0-9a-f]{40}", args.execution_source),
                 "OUTPUT_OR_SHA_UNBOUND")
            need(tools.source_head() == args.execution_source,
                 "SOURCE_HEAD_CHANGED")
            if args.collect:
                collect(args.output, args.execution_source)
            else:
                verify_output(args.output, args.execution_source)
                print("FE09_T3S0_COMPILED_FIRST_PARTY_MEMORY_OVER_BUDGET_VERIFIED")
    except (NotAdmitted, tools.GateFailure, OSError,
            subprocess.CalledProcessError, ValueError) as exc:
        raise SystemExit(FAILURE + ": " + str(exc)) from None


if __name__ == "__main__":
    main()
