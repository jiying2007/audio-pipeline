#!/usr/bin/env python3
"""FE09 T2-B/B0: execute first-party capture-only BF under absent Render.

Research-only proof of software microphone-history equivalence. Not an APX3
recorder, real source authority, SPSC liveness, shared physical clock or SDK.
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
import fe09_b2s3_t2a_controlled_restart_qualification as t2a

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
BASE = "46a29d288f4b58a940400e1f0a50195863631d18"
DECISION = "FE09_S3_T2B_B0_CAPTURE_ONLY_BF_EQUIVALENCE_NO_QUEUE_OR_RECORDER"
FAILURE = "FE09_S3_T2B_B0_CAPTURE_BF_NOT_ADMITTED"
TARGETS = ("native", "sanitized", "arm", "tsan")
MEMBERS = ("SHA256SUMS", "receipt.json", "collect.log", "verify.log")
ADAPTER_C = HERE / "fe09_b2s3_t2b_b0_capture_only.c"
ADAPTER_H = HERE / "fe09_b2s3_t2b_b0_capture_only.h"
TEST_C = HERE / "fe09_b2s3_t2b_b0_capture_only_test.c"
OWN = (ADAPTER_C, ADAPTER_H, TEST_C, Path(__file__).resolve())
FROZEN = tuple(dict.fromkeys((
    *t2a.OWN, *t2a.FROZEN,
    b1.SOURCE_C, b1.B1B0_C, b1.ARRAY_C, b1.NEW_C,
    ROOT / "tools/apdump.py", ROOT / "tools/apreplay.py",
)))
SOURCES = (
    b1.SOURCE_C, b1.B1B0_C, b1.ARRAY_C, b1.NEW_C,
    HERE / "fe09_b2s1_private_queue.c",
    HERE / "fe09_b2s2_private_apd.c",
    HERE / "fe09_b2s3_private_bridge.c",
    HERE / "fe09_b2s3_t1_source_witness.c",
    HERE / "fe09_b2s3_t2a_controlled_restart.c",
    ADAPTER_C, TEST_C,
)


class Denied(ValueError):
    pass


def need(condition: bool, code: str) -> None:
    if not condition:
        raise Denied(code)


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def file_sha(path: Path) -> str:
    need(path.is_file() and not path.is_symlink() and
         0 < path.stat().st_size <= 16 * 1024 * 1024,
         "MISSING_OR_OVERSIZE_SOURCE_" + path.name)
    return sha(path.read_bytes())


def frozen() -> dict:
    need(t2a.BASE == "d911547091c792c4cded48283499361833674917",
         "PROTECTED_T2A_LINEAGE_DRIFT")
    pins: dict[str, str] = {}
    for path in FROZEN:
        rel = str(path.relative_to(ROOT))
        raw = subprocess.check_output(
            ["git", "-c", "safe.directory=" + str(ROOT),
             "show", BASE + ":" + rel], cwd=ROOT, timeout=30)
        need(0 < len(raw) <= 16 * 1024 * 1024 and sha(raw) == file_sha(path),
             "FROZEN_ORIGINAL_CHANGED_" + rel)
        pins[rel] = sha(raw)
    return pins


def identity(commit: str) -> dict:
    need(re.fullmatch(r"[0-9a-f]{40}", commit) is not None,
         "SOURCE_COMMIT_NOT_EXACT")
    return {
        "schema_version": 1,
        "stage": "FE09-R2B2-S3-T2B-B0-CAPTURE-ONLY-FIRST-PARTY-BF",
        "preregistration": "https://github.com/jiying2007/audio-pipeline/issues/771",
        "source_commit": commit,
        "protected_predecessor_main": BASE,
        "protected_predecessor_verify": 38871738147,
        "protected_predecessor_release": 38876039158,
        "source_role": "first-party-synthetic",
        "own_sha256": {str(p.relative_to(ROOT)): file_sha(p) for p in OWN},
        "frozen_predecessor_sha256": frozen(),
        "real_source_attestation_qualified": False,
        "render_optional_recorder_qualified": False,
        "spsc_liveness_qualified": False,
        "physical_clock_measured": False,
        "ssc305_device_qualified": False,
        "public_sdk_installed": False,
        "shipping_dsp_modified": False,
        "legacy_apd2_modified": False,
    }


def check_result(result: dict) -> None:
    keys = {
        "schema_version", "decision", "source_role",
        "capture_bf_progress_qualified", "recorder_qualified",
        "spsc_liveness_qualified", "physical_clock_qualified",
        "public_sdk_installed", "device_qualified",
        "profiles", "profile_count", "negative_checks", "control_digest",
    }
    need(type(result) is dict and set(result) == keys, "RESULT_KEYS_CHANGED")
    need(type(result["schema_version"]) is int and
         result["schema_version"] == 1 and
         result["decision"] == DECISION and
         result["source_role"] == "first-party-synthetic" and
         result["capture_bf_progress_qualified"] is True and
         all(result[x] is False for x in (
             "recorder_qualified", "spsc_liveness_qualified",
             "physical_clock_qualified", "public_sdk_installed",
             "device_qualified")) and
         type(result["profile_count"]) is int and
         result["profile_count"] == 48 and
         type(result["negative_checks"]) is int and
         result["negative_checks"] >= 9000 and
         type(result["control_digest"]) is str and
         re.fullmatch(r"[0-9a-f]{16}", result["control_digest"]),
         "FALSE_AUDIO_OR_HARDWARE_PROMOTION")
    rows = result["profiles"]
    required = [(s, rate, sched)
                for s in ("C1_BASELINE", "C2_ULA", "C4_ULA", "C4_UCA")
                for rate in (16000, 32000, 48000)
                for sched in (0, 1, 2, 3)]
    need(type(rows) is list and len(rows) == len(required),
         "NOT_48_REAL_CONFIGURATIONS")
    for row, (scene, rate, schedule) in zip(rows, required):
        need(type(row) is dict and set(row) == {
            "scene", "rate", "schedule", "frames",
            "control_hash", "bf_hash",
        } and row["scene"] == scene and
             type(row["rate"]) is int and row["rate"] == rate and
             type(row["schedule"]) is int and row["schedule"] == schedule and
             type(row["frames"]) is int and row["frames"] == 48 and
             type(row["control_hash"]) is str and
             re.fullmatch(r"[a-f0-9]{16}", row["control_hash"]) and
             type(row["bf_hash"]) is str and
             re.fullmatch(r"[a-f0-9]{16}", row["bf_hash"]),
             "FALSE_BF_OUTPUT_EVIDENCE_" + scene)


def check_targets(targets: dict) -> None:
    need(type(targets) is dict and set(targets) == set(TARGETS),
         "MISSING_NATIVE_SANITIZER_ARM_TSAN")
    for value in targets.values():
        check_result(value)
    native = targets["native"]
    # Floating-point BF hashes may depend on the target ISA. Compare only
    # actual INTEGER control decisions; each target proves its local BF
    # bitwise equality to two different first-party configurations.
    for target in TARGETS[1:]:
        value = targets[target]
        for key in ("schema_version", "decision", "source_role",
                    "capture_bf_progress_qualified", "recorder_qualified",
                    "spsc_liveness_qualified", "physical_clock_qualified",
                    "public_sdk_installed", "device_qualified",
                    "profile_count", "negative_checks", "control_digest"):
            need(value[key] == native[key],
                 "INTEGER_CROSS_TARGET_DRIFT_" + key + "_" + target)
        for actual, expected in zip(value["profiles"], native["profiles"]):
            for key in ("scene", "rate", "schedule", "frames", "control_hash"):
                need(actual[key] == expected[key],
                     "PROFILE_CONTROL_DRIFT_" + target + "_" + key)


def self_test() -> None:
    frozen()
    rows = [{"scene": sc, "rate": rate, "schedule": schedule,
             "frames": 48, "control_hash": "0123456789abcdef",
             "bf_hash": "fedcba9876543210"}
            for sc in ("C1_BASELINE", "C2_ULA", "C4_ULA", "C4_UCA")
            for rate in (16000, 32000, 48000)
            for schedule in (0, 1, 2, 3)]
    good = {
        "schema_version": 1, "decision": DECISION,
        "source_role": "first-party-synthetic",
        "capture_bf_progress_qualified": True,
        "recorder_qualified": False, "spsc_liveness_qualified": False,
        "physical_clock_qualified": False,
        "public_sdk_installed": False, "device_qualified": False,
        "profiles": rows, "profile_count": 48, "negative_checks": 9000,
        "control_digest": "0123456789abcdef",
    }
    check_targets({target: good for target in TARGETS})
    rejected = 0
    for key, invalid in (
        ("schema_version", 2),
        ("decision", FAILURE),
        ("source_role", "trusted-physical-hardware"),
        ("capture_bf_progress_qualified", False),
        ("recorder_qualified", True),
        ("spsc_liveness_qualified", True),
        ("physical_clock_qualified", True),
        ("public_sdk_installed", True),
        ("device_qualified", True),
        ("profile_count", 47),
        ("negative_checks", 8999),
        ("control_digest", "bad"),
    ):
        bad = json.loads(json.dumps(good))
        bad[key] = invalid
        try:
            check_result(bad)
        except Denied:
            rejected += 1
        else:
            raise Denied("FALSE_ADMISSION_ACCEPTED_" + key)
    for key, invalid in (
        ("scene", "C3"), ("rate", 24000), ("schedule", 4),
        ("frames", 47), ("control_hash", "bad"), ("bf_hash", "bad"),
    ):
        bad = json.loads(json.dumps(good))
        bad["profiles"][0][key] = invalid
        try:
            check_result(bad)
        except Denied:
            rejected += 1
        else:
            raise Denied("BAD_SCENE_ACCEPTED_" + key)
    need(rejected == 18, "NEGATIVE_SELF_TEST_COUNT_DRIFT")
    # This deliberately DOES NOT demand cross-ISA Float32 bitwise equality.
    variant = json.loads(json.dumps(good))
    variant["profiles"][0]["bf_hash"] = "0123456789abcdef"
    check_targets({"native": good, "sanitized": variant,
                   "arm": variant, "tsan": variant})
    print("FE09_T2B_B0_FIRST_PARTY_CONTROL_SELF_TEST_PASS negatives=18")


def verify_output(output: Path, commit: str) -> None:
    need(output.is_dir() and
         {p.name for p in output.iterdir()} == set(MEMBERS),
         "ARTIFACT_MEMBERS_CHANGED")
    for name in MEMBERS:
        p = output / name
        cap = (1024 if name == "SHA256SUMS" else
               262144 if name == "receipt.json" else
               2097152 if name == "collect.log" else 256)
        need(p.is_file() and not p.is_symlink() and
             0 < p.stat().st_size <= cap, "ARTIFACT_MEMBER_BOUNDS_" + name)
    manifest = "".join(f"{file_sha(output / x)}  {x}\n"
                       for x in ("receipt.json", "collect.log", "verify.log"))
    need((output / "SHA256SUMS").read_text("ascii") == manifest,
         "ARTIFACT_INNER_SHA_DRIFT")
    rec = tools.strict_json((output / "receipt.json").read_text("utf-8"))
    for key, value in identity(commit).items():
        need(rec.get(key) == value, "SOURCE_OR_FROZEN_ID_CHANGED_" + key)
    need(rec.get("decision") == DECISION and
         rec.get("capture_bf_continuity_software_qualified") is True and
         rec.get("target_order") == list(TARGETS) and
         rec.get("actual_first_party_src_and_fir33") is True and
         rec.get("paired_oracle_counterfactual_only") is True and
         rec.get("real_source_attestation_qualified") is False and
         rec.get("render_optional_recorder_qualified") is False and
         rec.get("spsc_liveness_qualified") is False and
         rec.get("physical_clock_measured") is False and
         rec.get("ssc305_device_qualified") is False and
         rec.get("public_sdk_installed") is False,
         "MISATTRIBUTED_BF_OR_RECORDER_ADMISSION")
    versions = rec.get("compiler_versions")
    hashes = rec.get("binary_sha256")
    need(type(versions) is dict and set(versions) == set(TARGETS) and
         all(type(x) is str and bool(x) for x in versions.values()) and
         type(hashes) is dict and set(hashes) == set(TARGETS) and
         all(type(x) is str and re.fullmatch(r"[a-f0-9]{64}", x)
             for x in hashes.values()),
         "MISSING_REAL_COMPILER_OR_ELF")
    check_targets(rec.get("target_results"))
    need((output / "verify.log").read_text("ascii") ==
         "FE09_T2B_B0_CAPTURE_BF_SOURCE_VERIFIED\n",
         "VERIFY_MARKER_NOT_EXACT")


def collect(output: Path, commit: str) -> None:
    need(not output.exists(), "REFUSE_OVERWRITE")
    need(tools.source_head() == commit, "WRONG_RUNNING_HEAD")
    receipt = identity(commit)
    receipt["decision"] = FAILURE
    # A failed compiler/test/sanitizer job must not carry a true acceptance
    # flag in the retained failure Artifact, even if preregistration is valid.
    receipt["capture_bf_continuity_software_qualified"] = False
    logs: list[str] = []
    output.mkdir(parents=True)
    try:
        targets, versions, hashes = {}, {}, {}
        with tempfile.TemporaryDirectory(prefix="fe09-t2b-b0-") as temp:
            wd = Path(temp)
            header = wd / "include/audio_pipeline/audio_pipeline_build.h"
            header.parent.mkdir(parents=True)
            header.write_text(
                "#ifndef AUDIO_PIPELINE_AUDIO_PIPELINE_BUILD_H\n"
                "#define AUDIO_PIPELINE_AUDIO_PIPELINE_BUILD_H\n"
                "#define AP_BUILD_RESAMPLER_BANDLIMITED 1\n"
                "#endif\n", encoding="ascii")
            for target in TARGETS:
                compiler = ("arm-linux-gnueabihf-gcc"
                            if target == "arm" else "cc")
                need(shutil.which(compiler) is not None,
                     "COMPILER_NOT_AVAILABLE_" + target)
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
                    warnings = ([] if source in (b1.SOURCE_C, b1.ARRAY_C)
                                else ["-Wconversion", "-Wshadow", "-Wpedantic"])
                    tools.run(flags + warnings + ["-c", str(source),
                                                  "-o", str(obj)],
                              logs, timeout=120)
                    objects.append(str(obj))
                elf = wd / (target + ".elf")
                cmd = [compiler, *objects, "-pthread", "-lm", "-o", str(elf)]
                if target == "sanitized":
                    cmd += ["-fsanitize=address,undefined"]
                if target == "tsan":
                    cmd += ["-fsanitize=thread"]
                if target == "arm":
                    cmd += ["-march=armv7-a", "-mfpu=neon-vfpv4",
                            "-mfloat-abi=hard"]
                tools.run(cmd, logs, timeout=120)
                hashes[target] = file_sha(elf)
                exe = [str(elf)]
                if target == "arm":
                    need(shutil.which("qemu-arm") is not None and
                         Path("/usr/arm-linux-gnueabihf").is_dir(),
                         "ARM_QEMU_ENVIRONMENT_MISSING")
                    exe = ["qemu-arm", "-L", "/usr/arm-linux-gnueabihf",
                           str(elf)]
                env = dict(os.environ)
                if target == "sanitized":
                    env.update({"ASAN_OPTIONS": "detect_leaks=0:halt_on_error=1",
                                "UBSAN_OPTIONS": "halt_on_error=1"})
                if target == "tsan":
                    env.update({"TSAN_OPTIONS": "halt_on_error=1:exitcode=66"})
                first = tools.strict_json(
                    tools.run(exe, logs, timeout=180, env=env))
                second = tools.strict_json(
                    tools.run(exe, logs, timeout=180, env=env))
                need(first == second, "TARGET_REEXECUTION_DRIFT_" + target)
                check_result(first)
                targets[target] = first
        check_targets(targets)
        receipt.update({
            "decision": DECISION,
            "capture_bf_continuity_software_qualified": True,
            "target_order": list(TARGETS),
            "target_results": targets,
            "compiler_versions": versions,
            "binary_sha256": hashes,
            "actual_first_party_src_and_fir33": True,
            "paired_oracle_counterfactual_only": True,
        })
    except Exception as exc:
        receipt["decision"] = FAILURE
        receipt["failure_type"] = type(exc).__name__
        receipt["failure_code"] = str(exc)[:200]
        import sys
        print("FE09_T2B_B0_FAILING_LOG_TAIL_BEGIN", file=sys.stderr)
        print("\n".join(logs[-8:])[-5000:], file=sys.stderr)
        print("FE09_T2B_B0_FAILING_LOG_TAIL_END", file=sys.stderr)
        raise
    finally:
        (output / "receipt.json").write_text(
            json.dumps(receipt, sort_keys=True, separators=(",", ":"),
                       allow_nan=False) + "\n", encoding="utf-8")
        (output / "collect.log").write_text(
            "\n".join(logs) + "\n", encoding="utf-8")
        (output / "verify.log").write_text(
            ("FE09_T2B_B0_CAPTURE_BF_SOURCE_VERIFIED\n"
             if receipt.get("decision") == DECISION else FAILURE + "\n"),
            encoding="ascii")
        (output / "SHA256SUMS").write_text(
            "".join(f"{file_sha(output / x)}  {x}\n"
                    for x in ("receipt.json", "collect.log", "verify.log")),
            encoding="ascii")
    verify_output(output, commit)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--self-test", action="store_true")
    group.add_argument("--collect", action="store_true")
    group.add_argument("--verify", action="store_true")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--execution-source")
    args = parser.parse_args()
    try:
        if args.self_test:
            self_test()
        else:
            need(args.output is not None and
                 re.fullmatch(r"[a-f0-9]{40}", args.execution_source or "")
                 is not None, "OUTPUT_OR_HEAD_MISSING")
            need(tools.source_head() == args.execution_source,
                 "RUNNING_HEAD_NOT_EXACT")
            if args.collect:
                collect(args.output, args.execution_source)
            else:
                verify_output(args.output, args.execution_source)
                print("FE09_T2B_B0_CAPTURE_BF_SOURCE_VERIFIED")
    except (Denied, tools.GateFailure, ValueError, OSError,
            subprocess.CalledProcessError) as exc:
        raise SystemExit(FAILURE + ": " + str(exc)) from None


if __name__ == "__main__":
    main()
