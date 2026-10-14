#!/usr/bin/env python3
"""FE09-R2B1B-S1: actual unchanged first-party SRC and one array FIR33 BF.

Noninstalled, 12 synthetic N+render profiles x native/sanitized/AArch32.
No 3.x public ABI, acoustic gain, ADC clock, AEC or SSC305 admission.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import tempfile

import fe09_array_sdk_draft_qualification_r2a as tools

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
SOURCE_C = ROOT / "src/frontend/ap_resampler.c"
SOURCE_H = ROOT / "src/frontend/ap_resampler.h"
B1B0_C = HERE / "fe09_b1b0_src.c"
B1B0_H = HERE / "fe09_b1b0_src.h"
ARRAY_C = HERE / "array_native.c"
ARRAY_H = HERE / "array_native.h"
NEW_C = HERE / "fe09_b1b1_single_bf.c"
NEW_H = HERE / "fe09_b1b1_single_bf.h"
TEST_C = HERE / "fe09_b1b1_single_bf_test.c"
FILES = (SOURCE_C, SOURCE_H, B1B0_C, B1B0_H, ARRAY_C, ARRAY_H,
         NEW_C, NEW_H, TEST_C, Path(__file__).resolve())
# Immutable already-qualified first-party source authorities, not ABI evidence.
SOURCE_SHA256 = "5bf5e725dfdc516d82dce145b93ef881b1348bae17d2bd04130e7feb15834aff"
ARRAY_BLOB = "9e2cdfcc26eb93d8d03c53c722801c06981363fc"
B1B0_BLOB = "6d195d7eb36726f6d4a33410d4df97ad392ec15f"
TARGETS = ("native", "sanitized", "arm")
RATES = (16000, 32000, 48000)
SCENES = (("C1_BASELINE", 1, 0), ("C2_ULA", 2, 1),
          ("C4_ULA", 4, 1), ("C4_UCA", 4, 1))
DECISION = "FE09_R2B1B_S1_SINGLE_ARRAY_BF_RESEARCH_ONLY_NO_RELEASE"
FAILURE = "FE09_R2B1B_S1_GEOMETRY_OR_SOURCE_TRANSFER_NOT_ADMITTED"
MEMBERS = ("SHA256SUMS", "receipt.json", "collect.log", "verify.log")


class AdmissionError(ValueError):
    """Malformed source, fixture, binary execution or sealed evidence."""


def require(condition: bool, reason: str) -> None:
    if not condition:
        raise AdmissionError(reason)


def sha_file(path: Path, cap: int = 16 * 1024 * 1024) -> str:
    require(path.is_file() and not path.is_symlink() and
            0 < path.stat().st_size <= cap, "MISSING_OR_OVERSIZED_FILE")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git_blob(path: Path) -> str:
    return tools.run(["git", "-c", "safe.directory=" + str(ROOT),
                      "hash-object", str(path)], []).strip()


def authority() -> None:
    require(sha_file(SOURCE_C) == SOURCE_SHA256,
            "ACTUAL_FIRST_PARTY_RESAMPLER_SOURCE_DRIFT")
    require(git_blob(ARRAY_C) == ARRAY_BLOB,
            "SOLE_FIRST_PARTY_ARRAY_CORE_DRIFT")
    require(git_blob(B1B0_C) == B1B0_BLOB,
            "PREDECESSOR_N_RENDER_SRC_DRIFT")


def source_identity(sha: str) -> dict:
    authority()
    return {
        "schema_version": 1, "source_commit": sha,
        "stage": "FE09-R2B1B-S1-NONINSTALLED-SINGLE-ARRAY-BF",
        "preregistration": "https://github.com/jiying2007/audio-pipeline/issues/743",
        "parent": "https://github.com/jiying2007/audio-pipeline/issues/733",
        "predecessor_main": "65f8589e708b9a2708699a9514f0c414ad4258ab",
        "predecessor_verify": 38427035530,
        "predecessor_release": 38431798704,
        "original_resampler_source_sha256": SOURCE_SHA256,
        "array_native_git_blob": ARRAY_BLOB,
        "predecessor_src_git_blob": B1B0_BLOB,
        "source_sha256": {str(p.relative_to(ROOT)): sha_file(p) for p in FILES},
        "noninstalled_only": True, "production_src_changed": False,
        "public_abi_3x_installed": False, "render_is_not_mic_5": True,
        "real_adc_clock_qualified": False, "beamforming_gain_qualified": False,
        "aec_qualified": False, "ssc305_dut_qualified": False,
        "full_c4_system_budget_qualified": False,
        "shipping_authority": False, "real_array_geometry_authority": "UNKNOWN",
    }


def strict_json(raw: str) -> dict:
    return tools.strict_json(raw)


def check_one(data: dict) -> None:
    keys = {
        "schema_version", "decision", "source_role", "public_sdk_installed",
        "aec_qualified", "real_adc_clock_qualified", "ssc305_dut_qualified",
        "full_c4_budget_qualified", "render_to_bf_forbidden", "repeats",
        "profile_count", "profiles",
    }
    require(type(data) is dict and set(data) == keys and
            type(data["schema_version"]) is int and data["schema_version"] == 1 and
            data["decision"] == DECISION and
            data["source_role"] == "first-party-synthetic" and
            data["repeats"] == 2 and data["profile_count"] == 12 and
            data["render_to_bf_forbidden"] is True and
            all(data[k] is False for k in (
                "public_sdk_installed", "aec_qualified",
                "real_adc_clock_qualified", "ssc305_dut_qualified",
                "full_c4_budget_qualified")),
            "STAGE_OR_PRODUCT_PROMOTION")
    rows = data["profiles"]
    require(type(rows) is list and len(rows) == 12, "MISSING_PROFILE")
    row_keys = {
        "name", "rate", "mics", "render", "frames", "negatives", "clips",
        "state_bytes", "work_bytes", "src_bytes", "bf_bytes",
        "capture_epoch", "render_epoch", "clock_epoch", "array_samples",
        "source_hash", "beam_hash", "render_hash",
    }
    for idx, row in enumerate(rows):
        name, n, render = SCENES[idx % 4]
        rate = RATES[idx // 4]
        require(type(row) is dict and set(row) == row_keys and
                row["name"] == name and row["rate"] == rate and
                row["mics"] == n and row["render"] == render and
                type(row["frames"]) is int and row["frames"] == 100 and
                type(row["negatives"]) is int and row["negatives"] >= 70 and
                type(row["clips"]) is int and 0 <= row["clips"] <= 64000 and
                type(row["state_bytes"]) is int and 0 < row["state_bytes"] < 65536 and
                type(row["work_bytes"]) is int and
                row["state_bytes"] < row["work_bytes"] < 65536 and
                type(row["src_bytes"]) is int and 0 < row["src_bytes"] < row["state_bytes"] and
                type(row["bf_bytes"]) is int and 0 < row["bf_bytes"] < row["state_bytes"] and
                row["capture_epoch"] == 2 and
                row["render_epoch"] == (2 if render else 0) and
                row["clock_epoch"] == 1 and row["array_samples"] == 1760 and
                all(type(row[k]) is str and
                    re.fullmatch(r"[0-9a-f]{16}", row[k])
                    for k in ("source_hash", "beam_hash", "render_hash")),
                "MALFORMED_PROFILE_" + str(idx))


def check_targets(data: dict) -> None:
    require(type(data) is dict and set(data) == set(TARGETS),
            "INCOMPLETE_EXECUTION_TARGETS")
    for target in TARGETS:
        check_one(data[target])
    first = data["native"]["profiles"]
    for target in TARGETS[1:]:
        for left, right in zip(first, data[target]["profiles"]):
            for key in ("name", "rate", "mics", "render", "frames",
                        "negatives", "capture_epoch", "render_epoch",
                        "clock_epoch", "array_samples", "source_hash"):
                require(left[key] == right[key],
                        "CROSS_TARGET_SOURCE_OR_CONTROL_" + target + "_" + key)
    # CPU/RAM sizeof and FIR floating hashes may differ by toolchain/ABI.
    # Never treat QEMU time or a synthetic room as actual DUT timing/benefit.


def synthetic_result() -> dict:
    rows = []
    for rate in RATES:
        for name, n, render in SCENES:
            rows.append({
                "name": name, "rate": rate, "mics": n, "render": render,
                "frames": 100, "negatives": 72, "clips": 0,
                "state_bytes": 8192, "work_bytes": 16384,
                "src_bytes": 2000, "bf_bytes": 4000,
                "capture_epoch": 2, "render_epoch": 2 if render else 0,
                "clock_epoch": 1, "array_samples": 1760,
                "source_hash": "1" * 16, "beam_hash": "2" * 16,
                "render_hash": "3" * 16,
            })
    return {
        "schema_version": 1, "decision": DECISION,
        "source_role": "first-party-synthetic",
        "public_sdk_installed": False, "aec_qualified": False,
        "real_adc_clock_qualified": False, "ssc305_dut_qualified": False,
        "full_c4_budget_qualified": False, "render_to_bf_forbidden": True,
        "repeats": 2, "profile_count": 12, "profiles": rows,
    }


def self_test() -> None:
    import copy
    data = synthetic_result()
    check_one(data)
    check_targets({t: copy.deepcopy(data) for t in TARGETS})
    mutations = [
        ("decision", "SHIPPING_OK"),
        ("aec_qualified", True),
        ("ssc305_dut_qualified", True),
        ("render_to_bf_forbidden", False),
        ("repeats", 1),
        ("profile_count", 11),
    ]
    for key, bad in mutations:
        altered = copy.deepcopy(data)
        altered[key] = bad
        try:
            check_one(altered)
        except AdmissionError:
            pass
        else:
            raise AdmissionError("FALSE_STAGE_PROMOTION_" + key)
    for key, bad in (("negatives", 1), ("frames", 99), ("rate", 24000),
                     ("array_samples", 1600), ("source_hash", "x" * 16),
                     ("capture_epoch", 1)):
        altered = copy.deepcopy(data)
        altered["profiles"][0][key] = bad
        try:
            check_one(altered)
        except AdmissionError:
            pass
        else:
            raise AdmissionError("FALSE_PROFILE_PROMOTION_" + key)
    try:
        strict_json('{"repeats":2,"repeats":1}')
    except tools.GateFailure:
        pass
    else:
        raise AdmissionError("DUPLICATE_JSON_KEY_ACCEPTED")
    authority()
    print("FE09_B1B1_S1_SELF_TEST_PASS 12-synthetic-profiles")


def verify_artifact(out: Path, sha: str) -> None:
    require(out.is_dir() and {p.name for p in out.iterdir()} == set(MEMBERS),
            "EVIDENCE_ARCHIVE_MEMBER_DRIFT")
    manifest = "".join(f"{sha_file(out / p)}  {p}\n"
                       for p in ("receipt.json", "collect.log", "verify.log"))
    require((out / "SHA256SUMS").read_text("ascii") == manifest,
            "INNER_HASH_MISMATCH")
    receipt = strict_json((out / "receipt.json").read_text("utf-8"))
    for key, expected in source_identity(sha).items():
        require(receipt.get(key) == expected, "SOURCE_IDENTITY_" + key)
    require(receipt.get("decision") == DECISION and
            receipt.get("targets") == list(TARGETS) and
            receipt.get("cpu_timing_claim") is False and
            receipt.get("publication_permission") is False,
            "FALSE_RELEASE_OR_DUT_PROMOTION")
    binaries = receipt.get("binary_sha256")
    require(type(binaries) is dict and set(binaries) == set(TARGETS) and
            all(type(x) is str and re.fullmatch(r"[0-9a-f]{64}", x)
                for x in binaries.values()), "BINARY_HASH_MISSING")
    check_targets(receipt.get("target_results"))
    require((out / "verify.log").read_text("utf-8") ==
            "FE09_B1B1_S1_SOURCE_RECEIPT_VERIFIED\n",
            "POSITIVE_RECEIPT_MARKER_MISSING")


def collect(out: Path, sha: str) -> None:
    require(not out.exists(), "REFUSE_OVERWRITE_EVIDENCE")
    require(tools.source_head() == sha, "WRONG_SOURCE_SHA")
    receipt = source_identity(sha)
    receipt["decision"] = FAILURE
    logs: list[str] = []
    out.mkdir(parents=True)
    try:
        results, binaries, compilers = {}, {}, {}
        with tempfile.TemporaryDirectory(prefix="fe09-b1b1-s1-") as tmp:
            wd = Path(tmp)
            build_header = wd / "include/audio_pipeline/audio_pipeline_build.h"
            build_header.parent.mkdir(parents=True)
            build_header.write_text(
                "#ifndef AUDIO_PIPELINE_AUDIO_PIPELINE_BUILD_H\n"
                "#define AUDIO_PIPELINE_AUDIO_PIPELINE_BUILD_H\n"
                "#define AP_BUILD_RESAMPLER_BANDLIMITED 1\n"
                "#endif\n", encoding="ascii")
            for target in TARGETS:
                compiler = ("arm-linux-gnueabihf-gcc" if target == "arm"
                            else "cc")
                require(shutil.which(compiler) is not None,
                        "COMPILER_UNAVAILABLE_" + target)
                compilers[target] = tools.run([compiler, "--version"], logs).splitlines()[0]
                opts = [compiler, "-std=c11", "-Wall", "-Wextra", "-Werror",
                        "-O2", "-ffp-contract=off", "-fno-fast-math",
                        "-DAP_BUILD_RESAMPLER_BANDLIMITED=1",
                        "-I" + str(wd / "include"),
                        "-I" + str(ROOT / "src"), "-I" + str(HERE)]
                if target == "sanitized":
                    opts += ["-O1", "-g", "-fsanitize=address,undefined",
                             "-fno-omit-frame-pointer"]
                if target == "arm":
                    opts += ["-march=armv7-a", "-mfpu=neon-vfpv4",
                             "-mfloat-abi=hard"]
                objects = []
                for i, path in enumerate((SOURCE_C, B1B0_C, ARRAY_C, NEW_C, TEST_C)):
                    obj = wd / f"{target}-{i}.o"
                    flags = [] if path in (SOURCE_C, ARRAY_C) else [
                        "-Wconversion", "-Wshadow", "-Wpedantic"]
                    tools.run(opts + flags + ["-c", str(path), "-o", str(obj)],
                              logs, timeout=120)
                    objects.append(str(obj))
                elf = wd / (target + ".elf")
                link = [compiler, *objects, "-lm", "-o", str(elf)]
                if target == "sanitized":
                    link += ["-fsanitize=address,undefined"]
                if target == "arm":
                    link += ["-march=armv7-a", "-mfpu=neon-vfpv4",
                             "-mfloat-abi=hard"]
                tools.run(link, logs, timeout=120)
                binaries[target] = sha_file(elf)
                if target == "arm":
                    require(shutil.which("qemu-arm") is not None and
                            Path("/usr/arm-linux-gnueabihf").is_dir(),
                            "ARM_QEMU_SYSROOT_UNAVAILABLE")
                    command = ["qemu-arm", "-L", "/usr/arm-linux-gnueabihf",
                               str(elf)]
                else:
                    command = [str(elf)]
                env = dict(os.environ)
                if target == "sanitized":
                    env.update({"ASAN_OPTIONS": "detect_leaks=0:halt_on_error=1",
                                "UBSAN_OPTIONS": "halt_on_error=1"})
                first = strict_json(tools.run(command, logs, timeout=100, env=env))
                second = strict_json(tools.run(command, logs, timeout=100, env=env))
                require(first == second, "TARGET_NONDETERMINISM_" + target)
                check_one(first)
                results[target] = first
        check_targets(results)
        receipt.update({
            "decision": DECISION, "targets": list(TARGETS),
            "binary_sha256": binaries, "compiler_version": compilers,
            "target_results": results,
            "execution_mode": "synthetic-12x100-SRC-to-single-FIR33-BF",
            "cpu_timing_claim": False,
            "publication_permission": False,
        })
    except Exception as exc:
        receipt["decision"] = FAILURE
        receipt["failure_class"] = type(exc).__name__
        receipt["failure_code"] = str(exc)[:160]
        raise
    finally:
        (out / "receipt.json").write_text(
            json.dumps(receipt, sort_keys=True, separators=(",", ":"),
                       allow_nan=False) + "\n", encoding="utf-8")
        (out / "collect.log").write_text(
            "\n".join(logs) + "\n", encoding="utf-8")
        (out / "verify.log").write_text(
            ("FE09_B1B1_S1_SOURCE_RECEIPT_VERIFIED\n" if
             receipt.get("decision") == DECISION else FAILURE + "\n"),
            encoding="utf-8")
        (out / "SHA256SUMS").write_text(
            "".join(f"{sha_file(out / p)}  {p}\n"
                    for p in ("receipt.json", "collect.log", "verify.log")),
            encoding="ascii")
    verify_artifact(out, sha)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument("--self-test", action="store_true")
    mode.add_argument("--collect", action="store_true")
    mode.add_argument("--verify", action="store_true")
    p.add_argument("--output", type=Path)
    p.add_argument("--execution-source", type=str)
    args = p.parse_args()
    try:
        if args.self_test:
            self_test()
        else:
            require(args.output is not None and args.execution_source is not None
                    and re.fullmatch(r"[0-9a-f]{40}", args.execution_source)
                    is not None, "EXACT_SHA_AND_OUTPUT_REQUIRED")
            if args.collect:
                collect(args.output, args.execution_source)
            else:
                require(tools.source_head() == args.execution_source,
                        "VERIFIER_SOURCE_SHA_DRIFT")
                verify_artifact(args.output, args.execution_source)
            print(DECISION if args.collect else
                  "FE09_B1B1_S1_SOURCE_RECEIPT_VERIFIED")
    except (AdmissionError, tools.GateFailure, ValueError, OSError, AssertionError,
            KeyError) as err:
        print(FAILURE + ": " + str(err))
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
