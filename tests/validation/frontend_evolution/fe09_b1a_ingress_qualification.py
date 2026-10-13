#!/usr/bin/env python3
"""FE09-R2B1A noninstalled 16kHz N-capture + separate render identity qualification.

Reuses existing first-party FE09-R2A bounded tool/JSON runners, NOT its BF kernel.
No waveforms, third-party models, device clock authority or SDK release.
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

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
SOURCES = (
    HERE / "fe09_b1a_ingress.h",
    HERE / "fe09_b1a_ingress.c",
    HERE / "fe09_b1a_ingress_test.c",
    Path(__file__).resolve(),
    HERE / "fe09_array_sdk_draft_r2a.c",  # previous sole BF adapter unchanged
    HERE / "array_native.c",              # same first-party BF authority
)
DECISION = "FE09_R2B1A_SEPARATE_CAPTURE_RENDER_INGRESS_RESEARCH_ONLY_NO_RELEASE"
FAILURE = "FE09_R2B1A_CHANNEL_OR_EPOCH_NOT_ADMITTED"
TARGETS = ("native", "sanitized", "arm")
PROFILES = (
    ("C1_BASELINE", 1, 0),
    ("C2_ULA", 2, 1),
    ("C4_ULA", 4, 1),
    ("C4_UCA", 4, 1),
)
MEMBERS = ("SHA256SUMS", "receipt.json", "collect.log", "verify.log")
CAP = 16 * 1024 * 1024


class B1AFailure(ValueError):
    pass


def require(condition: bool, code: str) -> None:
    if not condition:
        raise B1AFailure(code)


def digest(path: Path, cap: int = CAP) -> str:
    require(path.is_file() and not path.is_symlink() and
            0 < path.stat().st_size <= cap, "MISSING_OR_OVERSIZED_SOURCE")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def strict_json(data: str) -> dict:
    return tools.strict_json(data)


def source_identity(sha: str) -> dict:
    return {
        "schema_version": 1,
        "source_commit": sha,
        "preregistration": "https://github.com/jiying2007/audio-pipeline/issues/735",
        "parent_preregistration": "https://github.com/jiying2007/audio-pipeline/issues/733",
        "stage": "FE09-R2B1A-NONINSTALLED-IDENTITY-INGRESS",
        "source_sha256": {p.name: digest(p) for p in SOURCES},
        "predecessor_main_sha": "a0fc70d8fd1f325d8e86189eb0b131e034a79ecc",
        "predecessor_verify_run": 38351439101,
        "predecessor_release_run": 38353815260,
        "official_2x_sdk_unchanged": True,
        "public_3x_sdk_installed": False,
        "shipping_authority": False,
        "ssc305_dut_qualified": False,
        "realman_adc_clock_qualified": False,
        "multirate_src_qualified": False,
        "real_speech_bf_gain_qualified": False,
        "render_is_not_aec": True,
        "c4_system_budget_qualified": False,
    }


def check_one(result: dict) -> None:
    required = {
        "schema_version", "decision", "source_role", "profile_count",
        "repeats", "sample_rate_hz", "frame_ms", "identity_only",
        "public_sdk_installed", "shipping_authority", "render_is_not_aec",
        "multirate_src_qualified", "real_adc_clock_qualified",
        "ssc305_dut_qualified", "profiles",
    }
    require(type(result) is dict and set(result) == required and
            type(result["schema_version"]) is int and result["schema_version"] == 1 and
            result["decision"] == DECISION and
            result["source_role"] == "first-party-synthetic" and
            result["profile_count"] == 4 and result["repeats"] == 2 and
            result["sample_rate_hz"] == 16000 and result["frame_ms"] == 10 and
            result["identity_only"] is True and
            result["render_is_not_aec"] is True and
            all(result[k] is False for k in (
                "public_sdk_installed", "shipping_authority",
                "multirate_src_qualified", "real_adc_clock_qualified",
                "ssc305_dut_qualified")),
            "FALSE_STAGE_OR_PRODUCT_PROMOTION")
    rows = result["profiles"]
    require(type(rows) is list and len(rows) == len(PROFILES),
            "MISSING_FIXED_SCENE")
    expected_keys = {
        "name", "physical_mics", "render_channels", "state_bytes",
        "frames_per_repeat", "negative_checks", "capture_epoch",
        "render_epoch", "clock_epoch", "capture_frames_in_epoch",
        "render_frames_in_epoch", "input_fnv64", "output_fnv64",
        "render_fnv64", "capture_stream_hashes", "render_stream_hash",
    }
    previous = 0
    for row, (name, count, render) in zip(rows, PROFILES):
        require(type(row) is dict and set(row) == expected_keys and
                row["name"] == name and row["physical_mics"] == count and
                row["render_channels"] == render and
                type(row["state_bytes"]) is int and
                0 < row["state_bytes"] <= 512 and
                row["state_bytes"] % 16 == 0 and
                row["state_bytes"] >= previous and
                row["frames_per_repeat"] == 100 and
                type(row["negative_checks"]) is int and
                row["negative_checks"] >= 25 and
                row["capture_epoch"] == 2 and
                row["render_epoch"] == (2 if render else 0) and
                row["clock_epoch"] == 1 and
                row["capture_frames_in_epoch"] == 10 and
                row["render_frames_in_epoch"] == (10 if render else 0) and
                type(row["capture_stream_hashes"]) is list and
                len(row["capture_stream_hashes"]) == count,
                "NEGATIVE_OR_EPOCH_OR_RESOURCE_MATRIX_INVALID")
        previous = row["state_bytes"]
        for key in ("input_fnv64", "output_fnv64", "render_fnv64",
                    "render_stream_hash"):
            require(bool(re.fullmatch(r"[0-9a-f]{16}", str(row[key]))),
                    "FINGERPRINT_MALFORMED_" + key)
        require(all(bool(re.fullmatch(r"[0-9a-f]{16}", str(s)))
                    for s in row["capture_stream_hashes"]),
                "CAPTURE_SOURCE_HASH_MALFORMED")
        if not render:
            require(row["render_stream_hash"] == "0000000000000000",
                    "FALSE_RENDER_WHEN_ABSENT")


def check_targets(results: dict) -> None:
    require(type(results) is dict and set(results) == set(TARGETS),
            "TARGET_MATRIX_INCOMPLETE")
    for target in TARGETS:
        check_one(results[target])
    # Per-target pointer layout is allowed to differ; no invented CPU equivalence.
    for i in range(len(PROFILES)):
        for key in ("name", "physical_mics", "render_channels",
                    "frames_per_repeat", "negative_checks", "capture_epoch",
                    "render_epoch", "clock_epoch", "capture_frames_in_epoch",
                    "render_frames_in_epoch", "input_fnv64", "render_fnv64",
                    "capture_stream_hashes", "render_stream_hash"):
            baseline = results["native"]["profiles"][i][key]
            require(all(results[t]["profiles"][i][key] == baseline
                        for t in TARGETS),
                    "CROSS_TARGET_SOURCE_CONTROL_DRIFT_" + key)


def self_test() -> None:
    rows = []
    for i, (name, n, render) in enumerate(PROFILES):
        rows.append({
            "name": name, "physical_mics": n, "render_channels": render,
            "state_bytes": 128 + i * 16, "frames_per_repeat": 100,
            "negative_checks": 30, "capture_epoch": 2,
            "render_epoch": 2 if render else 0, "clock_epoch": 1,
            "capture_frames_in_epoch": 10,
            "render_frames_in_epoch": 10 if render else 0,
            "input_fnv64": "a" * 16, "output_fnv64": "b" * 16,
            "render_fnv64": "c" * 16,
            "capture_stream_hashes": ["d" * 16] * n,
            "render_stream_hash": "e" * 16 if render else "0" * 16,
        })
    exemplar = {
        "schema_version": 1, "decision": DECISION,
        "source_role": "first-party-synthetic", "profile_count": 4,
        "repeats": 2, "sample_rate_hz": 16000, "frame_ms": 10,
        "identity_only": True, "public_sdk_installed": False,
        "shipping_authority": False, "render_is_not_aec": True,
        "multirate_src_qualified": False, "real_adc_clock_qualified": False,
        "ssc305_dut_qualified": False, "profiles": rows,
    }
    check_one(exemplar)
    check_targets({t: copy.deepcopy(exemplar) for t in TARGETS})
    for key, value in (
        ("decision", "PUBLIC_3X_SHIPPING"), ("public_sdk_installed", True),
        ("render_is_not_aec", False), ("multirate_src_qualified", True),
        ("ssc305_dut_qualified", True), ("profile_count", 3),
    ):
        bad = copy.deepcopy(exemplar)
        bad[key] = value
        try:
            check_one(bad)
        except B1AFailure:
            pass
        else:
            raise B1AFailure("FALSE_PROMOTION_ACCEPTED_" + key)
    for key, value in (
        ("negative_checks", 24), ("capture_epoch", 1),
        ("clock_epoch", 0), ("render_stream_hash", "not-a-digest"),
    ):
        bad = copy.deepcopy(exemplar)
        bad["profiles"][1][key] = value
        try:
            check_one(bad)
        except B1AFailure:
            pass
        else:
            raise B1AFailure("BAD_CONTROL_ACCEPTED_" + key)
    wrong_targets = {t: copy.deepcopy(exemplar) for t in TARGETS}
    wrong_targets["arm"]["profiles"][1]["input_fnv64"] = "0" * 16
    try:
        check_targets(wrong_targets)
    except B1AFailure:
        pass
    else:
        raise B1AFailure("ARM_SOURCE_DRIFT_FALSE_ACCEPT")
    # Different private sizeof on 32/64-bit must NOT itself fail.
    accepted_layouts = {t: copy.deepcopy(exemplar) for t in TARGETS}
    accepted_layouts["arm"]["profiles"][0]["state_bytes"] = 112
    check_targets(accepted_layouts)
    try:
        strict_json('{"schema_version":1,"schema_version":2}')
    except tools.GateFailure:
        pass
    else:
        raise B1AFailure("DUPLICATE_JSON_ACCEPTED")
    print("FE09_B1A_INGRESS_SELF_TEST_PASS negatives=12")


def verify_artifact(output: Path, sha: str) -> None:
    require(output.is_dir() and
            {p.name for p in output.iterdir()} == set(MEMBERS),
            "ARTIFACT_FILE_SET_INVALID")
    expected = "".join(f"{digest(output / name)}  {name}\n"
                       for name in ("receipt.json", "collect.log", "verify.log"))
    require((output / "SHA256SUMS").read_text("ascii") == expected,
            "ARTIFACT_INNER_SHA256_MISMATCH")
    receipt = strict_json((output / "receipt.json").read_text("utf-8"))
    for k, v in source_identity(sha).items():
        require(receipt.get(k) == v, "SOURCE_OR_PROVENANCE_DRIFT_" + k)
    require(receipt.get("decision") == DECISION and
            receipt.get("targets") == list(TARGETS) and
            receipt.get("execution_mode") == "16kHz_10ms_identity_ingress_only" and
            receipt.get("render_is_not_aec") is True and
            receipt.get("public_3x_sdk_installed") is False,
            "STAGE_AUTHORITY_MISMATCH")
    require(type(receipt.get("binary_sha256")) is dict and
            set(receipt["binary_sha256"]) == set(TARGETS) and
            all(bool(re.fullmatch(r"[0-9a-f]{64}", value))
                for value in receipt["binary_sha256"].values()),
            "COMPILER_BINARY_DIGEST_INVALID")
    results = receipt.get("target_results")
    check_targets(results)
    require("FE09_B1A_SOURCE_RECEIPT_VERIFIED" in
            (output / "verify.log").read_text("utf-8"),
            "INDEPENDENT_VERIFY_LOG_MISSING")


def collect(output: Path, sha: str) -> None:
    require(not output.exists(), "OUTPUT_ALREADY_EXISTS")
    require(tools.source_head() == sha, "WRONG_CHECKOUT_SOURCE_SHA")
    output.mkdir(parents=True)
    log: list[str] = []
    receipt = source_identity(sha)
    receipt["decision"] = FAILURE  # Nothing is positive before all gates.
    try:
        results, binary_hashes, compilers = {}, {}, {}
        with tempfile.TemporaryDirectory(prefix="fe09-b1a-") as folder:
            temp = Path(folder)
            for target in TARGETS:
                compiler = "arm-linux-gnueabihf-gcc" if target == "arm" else "cc"
                require(shutil.which(compiler) is not None,
                        "TOOLCHAIN_NOT_FOUND_" + target)
                compilers[target] = tools.run([compiler, "--version"], log).splitlines()[0]
                exe = temp / ("b1a-" + target)
                cmd = [compiler, "-std=c11", "-Wall", "-Wextra", "-Wpedantic",
                       "-Werror", "-Wshadow", "-Wconversion", "-ffp-contract=off",
                       "-fno-fast-math", "-O2"]
                if target == "sanitized":
                    cmd += ["-O1", "-g", "-fsanitize=address,undefined",
                            "-fno-omit-frame-pointer"]
                if target == "arm":
                    cmd += ["-march=armv7-a", "-mfpu=neon-vfpv4",
                            "-mfloat-abi=hard"]
                cmd += ["-I" + str(HERE),
                        str(HERE / "fe09_b1a_ingress_test.c"),
                        str(HERE / "fe09_b1a_ingress.c"),
                        "-o", str(exe)]
                tools.run(cmd, log, timeout=120)
                binary_hashes[target] = digest(exe)
                if target == "arm":
                    require(shutil.which("qemu-arm") is not None and
                            Path("/usr/arm-linux-gnueabihf").is_dir(),
                            "ARM_QEMU_SYSROOT_MISSING")
                    exe_cmd = ["qemu-arm", "-L", "/usr/arm-linux-gnueabihf", str(exe)]
                else:
                    exe_cmd = [str(exe)]
                env = dict(os.environ)
                if target == "sanitized":
                    env.update({"ASAN_OPTIONS": "detect_leaks=0:halt_on_error=1",
                                "UBSAN_OPTIONS": "halt_on_error=1"})
                first = strict_json(tools.run(exe_cmd, log, timeout=70, env=env))
                second = strict_json(tools.run(exe_cmd, log, timeout=70, env=env))
                require(first == second, "TARGET_REPLAY_DRIFT_" + target)
                check_one(first)
                results[target] = first
        # Critical: cross-target checks happen BEFORE publishing success.
        check_targets(results)
        receipt.update({
            "decision": DECISION,
            "targets": list(TARGETS),
            "execution_mode": "16kHz_10ms_identity_ingress_only",
            "binary_sha256": binary_hashes,
            "compiler_first_lines": compilers,
            "target_results": results,
            "timing_methodology": "none; functional native, sanitized, AArch32/QEMU, no SSC305 device",
        })
    except Exception as exc:
        receipt["decision"] = FAILURE
        receipt["failure_class"] = type(exc).__name__
        receipt["failure_code"] = str(exc)[:180]
        raise
    finally:
        (output / "receipt.json").write_text(
            json.dumps(receipt, sort_keys=True, separators=(",", ":"),
                       allow_nan=False) + "\n", encoding="utf-8")
        (output / "collect.log").write_text("\n".join(log) + "\n",
                                            encoding="utf-8")
        (output / "verify.log").write_text(
            ("FE09_B1A_SOURCE_RECEIPT_VERIFIED\n"
             if receipt.get("decision") == DECISION else FAILURE + "\n"),
            encoding="utf-8")
        (output / "SHA256SUMS").write_text(
            "".join(f"{digest(output / name)}  {name}\n"
                    for name in ("receipt.json", "collect.log", "verify.log")),
            encoding="ascii")
    verify_artifact(output, sha)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--self-test", action="store_true")
    mode.add_argument("--collect", action="store_true")
    mode.add_argument("--verify", action="store_true")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--execution-source", type=str)
    args = parser.parse_args()
    try:
        if args.self_test:
            self_test()
            return
        require(args.output is not None and args.execution_source is not None and
                bool(re.fullmatch(r"[0-9a-f]{40}", args.execution_source)),
                "EXACT_SOURCE_AND_OUTPUT_REQUIRED")
        if args.collect:
            collect(args.output, args.execution_source)
        else:
            require(tools.source_head() == args.execution_source,
                    "WRONG_INDEPENDENT_VERIFY_CHECKOUT")
            verify_artifact(args.output, args.execution_source)
        print(DECISION if args.collect else "FE09_B1A_SOURCE_RECEIPT_VERIFIED")
    except (B1AFailure, tools.GateFailure, OSError, ValueError, KeyError,
            AssertionError) as exc:
        print(FAILURE + ": " + str(exc))
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
