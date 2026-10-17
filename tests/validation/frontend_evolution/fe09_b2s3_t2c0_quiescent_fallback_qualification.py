#!/usr/bin/env python3
"""#784 first-party T2-C0 logical ACK / NONSEAMLESS BF and APX3 proof.

Logical controller and hosted synthetic PCM only. Acknowledgements cannot
authenticate a physical driver; no clock, device, durable IO or public SDK.
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
import fe09_b2s3_t2b_b1s1_source_chunks_qualification as b1

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
BASE = "b29252d182e5ba8f76313ed1c75b41221e5b372a"
DECISION = "FE09_T2C0_LOGICAL_OWNER_ACK_NONSEAMLESS_FALLBACK_NO_PHYSICAL_AUTHORITY"
FAILURE = "FE09_T2C0_QUISCIENT_SESSION_NOT_ADMITTED"
TARGETS = ("native", "sanitized", "arm", "tsan")
MEMBERS = ("SHA256SUMS", "receipt.json", "collect.log", "verify.log")
SOURCE_C = HERE / "fe09_b2s3_t2c0_quiescent_fallback.c"
SOURCE_H = HERE / "fe09_b2s3_t2c0_quiescent_fallback.h"
TEST_C = HERE / "fe09_b2s3_t2c0_quiescent_fallback_test.c"
OWN = (SOURCE_H, SOURCE_C, TEST_C, Path(__file__).resolve())
FROZEN = tuple(dict.fromkeys((*b1.FROZEN, *b1.OWN)))
SOURCES = (*b1.SOURCES[:-1], SOURCE_C, TEST_C)


class Denied(ValueError):
    pass


def need(yes: object, code: str) -> None:
    if not yes:
        raise Denied(code)


def file_sha(path: Path) -> str:
    need(path.is_file() and not path.is_symlink() and
         0 < path.stat().st_size <= 16 * 1024 * 1024,
         "SOURCE_MISSING_OR_OVERSIZE_" + path.name)
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_pins() -> dict[str, str]:
    need(b1.BASE == "2c8025f68753891e07f2754e74e24cf50aff5f16",
         "B1_S1_FROZEN_LINEAGE_CHANGED")
    # Verify all previous private C sources against immutable B1-S1 base
    # and call that qualifier's recursively frozen predecessor audit too.
    b1.frozen()
    pins = {}
    for path in FROZEN:
        rel = str(path.relative_to(ROOT))
        raw = subprocess.check_output(
            ["git", "-c", "safe.directory=" + str(ROOT),
             "show", BASE + ":" + rel], cwd=ROOT, timeout=30)
        need(0 < len(raw) <= 16 * 1024 * 1024 and
             hashlib.sha256(raw).hexdigest() == file_sha(path),
             "FROZEN_PREDECESSOR_DRIFT_" + rel)
        pins[rel] = hashlib.sha256(raw).hexdigest()
    return pins


def identity(commit: str) -> dict:
    need(re.fullmatch(r"[0-9a-f]{40}", commit) is not None,
         "UNBOUND_RESEARCH_COMMIT")
    return {
        "schema_version": 1,
        "stage": "FE09-S3-T2-C0-LOGICAL-ACK-NONSEAMLESS-FALLBACK",
        "preregistration": "https://github.com/jiying2007/audio-pipeline/issues/784",
        "source_commit": commit,
        "protected_predecessor_main": BASE,
        "protected_predecessor_verify": 39017374545,
        "source_role": "first-party-synthetic",
        "own_source_sha256": {
            str(p.relative_to(ROOT)): file_sha(p) for p in OWN
        },
        "immutable_predecessor_sha256": source_pins(),
        "physical_owner_stop_verified": False,
        "capture_bf_history_preserved": False,
        "durable_archive_qualified": False,
        "ssc305_device_qualified": False,
        "public_sdk_installed": False,
        "shipped_code_modified": False,
        "legacy_apd2_modified": False,
    }


def check_result(item: dict) -> None:
    exact = {
        "schema_version", "decision", "source_role",
        "real_first_party_bf_and_apx3", "logical_owner_ack_qualified",
        "physical_owner_stop_verified", "capture_bf_history_preserved",
        "durable_archive_qualified", "ssc305_device_qualified",
        "public_sdk_installed", "profiles", "profile_count",
        "negative_checks", "control_digest",
    }
    need(type(item) is dict and set(item) == exact, "SCHEMA_MISMATCH")
    need(type(item["schema_version"]) is int and item["schema_version"] == 1
         and item["decision"] == DECISION
         and item["source_role"] == "first-party-synthetic"
         and item["real_first_party_bf_and_apx3"] is True
         and item["logical_owner_ack_qualified"] is True
         and all(item[k] is False for k in (
             "physical_owner_stop_verified", "capture_bf_history_preserved",
             "durable_archive_qualified", "ssc305_device_qualified",
             "public_sdk_installed"))
         and type(item["profile_count"]) is int
         and item["profile_count"] == 48
         and type(item["negative_checks"]) is int
         and item["negative_checks"] >= 624
         and type(item["control_digest"]) is str
         and re.fullmatch(r"[0-9a-f]{16}", item["control_digest"]),
         "FALSE_CONTINUITY_OR_DEVICE_PROMOTION")
    expected = [(scene, rate, depth, new_render)
                for scene in ("C1_BASELINE", "C2_ULA", "C4_ULA", "C4_UCA")
                for rate in (16000, 32000, 48000)
                for depth in (2, 4) for new_render in (0, 1)]
    rows = item["profiles"]
    need(type(rows) is list and len(rows) == 48, "MISSING_48_PROFILES")
    for row, (scene, rate, depth, new_render) in zip(rows, expected):
        need(type(row) is dict and set(row) == {
            "scene", "rate", "depth", "new_render",
            "old_apx3", "fresh_apx3", "quarantined_capture",
            "control_hash", "beam_hash"
        } and row["scene"] == scene
             and type(row["rate"]) is int and row["rate"] == rate
             and type(row["depth"]) is int and row["depth"] == depth
             and type(row["new_render"]) is int
             and row["new_render"] == new_render
             and row["old_apx3"] == row["fresh_apx3"] == 1
             and row["quarantined_capture"] == 1
             and type(row["control_hash"]) is str
             and re.fullmatch("[a-f0-9]{16}", row["control_hash"])
             and type(row["beam_hash"]) is str
             and re.fullmatch("[a-f0-9]{16}", row["beam_hash"]),
             "FALSE_OWNER_SOURCE_CASE_" + scene)


def check_targets(items: dict) -> None:
    need(type(items) is dict and set(items) == set(TARGETS),
         "MISSING_TRUE_NATIVE_SANITIZER_ARM_TSAN")
    for item in items.values():
        check_result(item)
    origin = items["native"]
    for target in TARGETS[1:]:
        other = items[target]
        for key in ("schema_version", "decision", "source_role",
                    "real_first_party_bf_and_apx3",
                    "logical_owner_ack_qualified",
                    "physical_owner_stop_verified",
                    "capture_bf_history_preserved",
                    "durable_archive_qualified",
                    "ssc305_device_qualified", "public_sdk_installed",
                    "profile_count", "negative_checks", "control_digest"):
            need(other[key] == origin[key],
                 "CROSS_TARGET_CONTROL_DRIFT_" + target + "_" + key)
        for row, prior in zip(other["profiles"], origin["profiles"]):
            for key in ("scene", "rate", "depth", "new_render",
                        "old_apx3", "fresh_apx3",
                        "quarantined_capture", "control_hash"):
                need(row[key] == prior[key],
                     "CROSS_TARGET_INTEGRITY_DRIFT_" + target + "_" + key)
    # Float32 BF hashes are verified against direct first-party BF on each
    # target inside actual C execution, NOT x86 vs ARM bitwise.


def self_test() -> None:
    source_pins()
    valid = {
        "schema_version": 1, "decision": DECISION,
        "source_role": "first-party-synthetic",
        "real_first_party_bf_and_apx3": True,
        "logical_owner_ack_qualified": True,
        "physical_owner_stop_verified": False,
        "capture_bf_history_preserved": False,
        "durable_archive_qualified": False,
        "ssc305_device_qualified": False,
        "public_sdk_installed": False,
        "profiles": [{
            "scene": s, "rate": rate, "depth": d, "new_render": nr,
            "old_apx3": 1, "fresh_apx3": 1, "quarantined_capture": 1,
            "control_hash": "0123456789abcdef",
            "beam_hash": "fedcba9876543210"
        } for s in ("C1_BASELINE", "C2_ULA", "C4_ULA", "C4_UCA")
            for rate in (16000, 32000, 48000)
            for d in (2, 4) for nr in (0, 1)],
        "profile_count": 48,
        "negative_checks": 624,
        "control_digest": "0123456789abcdef",
    }
    check_targets({target: valid for target in TARGETS})
    failures = 0
    for field, bad in (
        ("decision", FAILURE), ("source_role", "real-hardware"),
        ("physical_owner_stop_verified", True),
        ("capture_bf_history_preserved", True),
        ("real_first_party_bf_and_apx3", False),
        ("logical_owner_ack_qualified", False),
        ("durable_archive_qualified", True),
        ("ssc305_device_qualified", True),
        ("public_sdk_installed", True), ("profile_count", 47),
        ("negative_checks", 623), ("control_digest", "bad")
    ):
        sample = json.loads(json.dumps(valid))
        sample[field] = bad
        try:
            check_result(sample)
        except Denied:
            failures += 1
        else:
            raise Denied("SELFTEST_FALSE_QUALIFICATION_" + field)
    for field, bad in (
        ("scene", "C3"), ("rate", 24000), ("depth", 8),
        ("new_render", 2), ("old_apx3", 2), ("fresh_apx3", 0),
        ("quarantined_capture", 0), ("control_hash", "bad"),
        ("beam_hash", "bad")
    ):
        sample = json.loads(json.dumps(valid))
        sample["profiles"][0][field] = bad
        try:
            check_result(sample)
        except Denied:
            failures += 1
        else:
            raise Denied("SELFTEST_BOGUS_CASE_" + field)
    need(failures == 21, "SELFTEST_NEGATIVE_COUNT")
    print("FE09_T2C0_OWNER_ACK_POLICY_SELFTEST_PASS negatives=21")


def verify_output(output: Path, commit: str) -> None:
    need(output.is_dir() and
         {p.name for p in output.iterdir()} == set(MEMBERS),
         "ARTIFACT_MISSING_OR_EXTRA_MEMBERS")
    for name in MEMBERS:
        path = output / name
        limit = (1024 if name == "SHA256SUMS" else
                 262144 if name == "receipt.json" else
                 2097152 if name == "collect.log" else 256)
        need(path.is_file() and not path.is_symlink() and
             0 < path.stat().st_size <= limit,
             "ARTIFACT_MEMBER_SIZE_" + name)
    manifest = "".join(f"{file_sha(output / name)}  {name}\n"
                       for name in ("receipt.json", "collect.log",
                                    "verify.log"))
    need((output / "SHA256SUMS").read_text("ascii") == manifest,
         "ARTIFACT_INNER_SHA256_MISMATCH")
    row = tools.strict_json((output / "receipt.json").read_text("utf-8"))
    for key, val in identity(commit).items():
        need(row.get(key) == val, "IMMUTABLE_SOURCE_DRIFT_" + key)
    need(row.get("decision") == DECISION and
         row.get("first_party_target_execution_complete") is True and
         row.get("target_order") == list(TARGETS) and
         row.get("physical_owner_stop_verified") is False and
         row.get("capture_bf_history_preserved") is False and
         row.get("durable_archive_qualified") is False and
         row.get("ssc305_device_qualified") is False and
         row.get("public_sdk_installed") is False,
         "FALSE_OWNER_OR_DEVICE_ADMISSION")
    binaries = row.get("binary_sha256")
    versions = row.get("compiler_versions")
    need(type(binaries) is dict and set(binaries) == set(TARGETS) and
         all(type(x) is str and re.fullmatch("[0-9a-f]{64}", x)
             for x in binaries.values()) and
         type(versions) is dict and set(versions) == set(TARGETS) and
         all(type(x) is str and bool(x) for x in versions.values()),
         "ELF_OR_COMPILER_SOURCE_NOT_PINNED")
    check_targets(row.get("target_results"))
    need((output / "verify.log").read_text("ascii") ==
         "FE09_T2C0_FIRST_PARTY_OWNER_FALLBACK_VERIFIED\n",
         "VERIFY_MARKER_DRIFT")


def collect(output: Path, commit: str) -> None:
    need(not output.exists(), "REFUSE_EVIDENCE_OVERWRITE")
    need(tools.source_head() == commit, "RUNNING_SOURCE_DIFFERS")
    receipt = identity(commit)
    receipt["decision"] = FAILURE
    receipt["first_party_target_execution_complete"] = False
    logs: list[str] = []
    output.mkdir(parents=True)
    try:
        results, versions, hashes = {}, {}, {}
        with tempfile.TemporaryDirectory(prefix="fe09-t2c0-") as temp:
            wd = Path(temp)
            hdr = wd / "include/audio_pipeline/audio_pipeline_build.h"
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
                         "-I" + str(wd / "include"),
                         "-I" + str(ROOT / "src"), "-I" + str(HERE)]
                if target in ("sanitized", "tsan"):
                    flags += ["-O1", "-g",
                              "-fsanitize=thread" if target == "tsan"
                              else "-fsanitize=address,undefined",
                              "-fno-omit-frame-pointer"]
                if target == "arm":
                    flags += ["-march=armv7-a", "-mfpu=neon-vfpv4",
                              "-mfloat-abi=hard"]
                objects = []
                for idx, source in enumerate(SOURCES):
                    obj = wd / f"{target}-{idx}.o"
                    exempt = (b1.b1.b0.b1.SOURCE_C, b1.b1.b0.b1.ARRAY_C)
                    warns = ([] if source in exempt
                             else ["-Wconversion", "-Wshadow", "-Wpedantic"])
                    tools.run(flags + warns +
                              ["-c", str(source), "-o", str(obj)],
                              logs, timeout=120)
                    objects.append(str(obj))
                elf = wd / (target + ".elf")
                link = [compiler, *objects, "-pthread", "-lm", "-o", str(elf)]
                if target == "sanitized":
                    link.append("-fsanitize=address,undefined")
                if target == "tsan":
                    link.append("-fsanitize=thread")
                if target == "arm":
                    link += ["-march=armv7-a", "-mfpu=neon-vfpv4",
                             "-mfloat-abi=hard"]
                tools.run(link, logs, timeout=120)
                hashes[target] = file_sha(elf)
                command = [str(elf)]
                if target == "arm":
                    need(shutil.which("qemu-arm") is not None and
                         Path("/usr/arm-linux-gnueabihf").is_dir(),
                         "ARM_QEMU_TOOLCHAIN_NOT_AVAILABLE")
                    command = ["qemu-arm", "-L",
                               "/usr/arm-linux-gnueabihf", str(elf)]
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
                need(first == second, "REPLAY_NONDETERMINISM_" + target)
                check_result(first)
                results[target] = first
        check_targets(results)
        receipt.update({
            "decision": DECISION,
            "first_party_target_execution_complete": True,
            "target_order": list(TARGETS),
            "target_results": results,
            "compiler_versions": versions,
            "binary_sha256": hashes,
        })
    except Exception as exc:
        receipt["decision"] = FAILURE
        receipt["first_party_target_execution_complete"] = False
        receipt["failure_type"] = type(exc).__name__
        receipt["failure_code"] = str(exc)[:250]
        import sys
        print("FE09_T2C0_NEGATIVE_EXECUTION_LOG_BEGIN", file=sys.stderr)
        print("\n".join(logs[-8:])[-4000:], file=sys.stderr)
        print("FE09_T2C0_NEGATIVE_EXECUTION_LOG_END", file=sys.stderr)
        raise
    finally:
        (output / "receipt.json").write_text(
            json.dumps(receipt, sort_keys=True, separators=(",", ":"),
                       allow_nan=False) + "\n", encoding="utf-8")
        (output / "collect.log").write_text(
            "\n".join(logs) + "\n", encoding="utf-8")
        (output / "verify.log").write_text(
            "FE09_T2C0_FIRST_PARTY_OWNER_FALLBACK_VERIFIED\n"
            if receipt.get("decision") == DECISION else FAILURE + "\n",
            encoding="ascii")
        (output / "SHA256SUMS").write_text(
            "".join(f"{file_sha(output / p)}  {p}\n" for p in
                    ("receipt.json", "collect.log", "verify.log")),
            encoding="ascii")
    verify_output(output, commit)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--self-test", action="store_true")
    mode.add_argument("--collect", action="store_true")
    mode.add_argument("--verify", action="store_true")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--execution-source")
    args = parser.parse_args()
    try:
        if args.self_test:
            self_test()
        else:
            need(args.output is not None and
                 re.fullmatch("[0-9a-f]{40}",
                              args.execution_source or "") is not None,
                 "OUTPUT_OR_COMMIT_UNBOUND")
            need(tools.source_head() == args.execution_source,
                 "HEAD_CHANGED")
            if args.collect:
                collect(args.output, args.execution_source)
            else:
                verify_output(args.output, args.execution_source)
                print("FE09_T2C0_FIRST_PARTY_OWNER_FALLBACK_VERIFIED")
    except (Denied, tools.GateFailure, ValueError, OSError,
            subprocess.CalledProcessError) as exc:
        raise SystemExit(FAILURE + ": " + str(exc)) from None


if __name__ == "__main__":
    main()
