#!/usr/bin/env python3
"""FE09-R2B1B-S0: actual unchanged first-party 16/32/48k N+render SRC qualification.

Uninstalled research-only C11 harness. Uses the existing R2A exact-source bounded
runner, strict JSON reader and no-DUT evidence mechanics. No new DSP evaluator.
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
SRC_C = ROOT / "src/frontend/ap_resampler.c"
SRC_H = ROOT / "src/frontend/ap_resampler.h"
FILES = (
    HERE / "fe09_b1b0_src.h",
    HERE / "fe09_b1b0_src.c",
    HERE / "fe09_b1b0_src_test.c",
    Path(__file__).resolve(),
    SRC_C,
    SRC_H,
)
PINNED_SRC_C_SHA = "5bf5e725dfdc516d82dce145b93ef881b1348bae17d2bd04130e7feb15834aff"
DECISION = "FE09_R2B1B_S0_FIRST_PARTY_N_RENDER_SRC_RESEARCH_ONLY_NO_RELEASE"
FAILURE = "FE09_R2B1B_S0_SRC_OR_CLOCK_OWNERSHIP_NOT_ADMITTED"
TARGETS = ("native", "sanitized", "arm")
RATES = (16000, 32000, 48000)
SCENES = (("C1_BASELINE", 1, 0), ("C2_ULA", 2, 1),
          ("C4_ULA", 4, 1), ("C4_UCA", 4, 1))
MEMBERS = ("SHA256SUMS", "receipt.json", "collect.log", "verify.log")


class B1B0Failure(ValueError):
    pass


def require(ok: bool, code: str) -> None:
    if not ok:
        raise B1B0Failure(code)


def file_hash(path: Path, cap: int = 16 * 1024 * 1024) -> str:
    require(path.is_file() and not path.is_symlink() and
            0 < path.stat().st_size <= cap, "MISSING_OR_OVERSIZED_SOURCE")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def strict_json(raw: str) -> dict:
    return tools.strict_json(raw)


def source_identity(sha: str) -> dict:
    require(file_hash(SRC_C) == PINNED_SRC_C_SHA,
            "UPSTREAM_FIRST_PARTY_SRC_DRIFT")
    return {
        "schema_version": 1,
        "source_commit": sha,
        "preregistration": "https://github.com/jiying2007/audio-pipeline/issues/737",
        "parent": "https://github.com/jiying2007/audio-pipeline/issues/733",
        "stage": "FE09-R2B1B-S0-NONINSTALLED-FIRST-PARTY-SRC",
        "predecessor_main_sha": "4a9ff202862832581cce6990476fbc6216ffbf5e",
        "predecessor_verify_run": 38367239379,
        "predecessor_release_run": 38371240119,
        "pinned_upstream_resampler_sha256": PINNED_SRC_C_SHA,
        "source_sha256": {str(path.relative_to(ROOT)): file_hash(path)
                          for path in FILES},
        "official_2x_sdk_unchanged": True,
        "public_major_3_installed": False,
        "shipping_authority": False,
        "first_party_src_kernel_reused": True,
        "bf_integrated": False,
        "render_is_not_aec": True,
        "capture_adc_clock_qualified": False,
        "ssc305_dut_qualified": False,
        "full_c4_192kib_budget_admitted": False,
        "rates_8k_24k_admitted": False,
    }


def check_one(data: dict) -> None:
    keys = {
        "schema_version", "decision", "source_role", "sample_rate_hz_internal",
        "source_kernel", "bandlimited", "public_sdk_installed",
        "shipping_authority", "render_is_not_aec", "bf_integrated",
        "ssc305_dut_qualified", "real_adc_clock_qualified",
        "full_c4_budget_qualified", "repeats", "profile_count", "profiles",
    }
    require(type(data) is dict and set(data) == keys and
            type(data["schema_version"]) is int and data["schema_version"] == 1 and
            data["decision"] == DECISION and
            data["source_role"] == "first-party-synthetic" and
            data["sample_rate_hz_internal"] == 16000 and
            data["source_kernel"] == "src/frontend/ap_resampler.c" and
            data["bandlimited"] is True and
            data["render_is_not_aec"] is True and
            data["repeats"] == 2 and data["profile_count"] == 12 and
            all(data[k] is False for k in (
                "public_sdk_installed", "shipping_authority",
                "bf_integrated", "ssc305_dut_qualified",
                "real_adc_clock_qualified", "full_c4_budget_qualified")),
            "STAGE_OR_SHIPPING_PROMOTION")
    rows = data["profiles"]
    require(type(rows) is list and len(rows) == 12, "SCENE_MISSING")
    keys_row = {
        "name", "input_rate_hz", "mics", "render", "input_frame_samples",
        "state_bytes", "src_state_per_stream_bytes", "filter_delay_samples",
        "negative_checks", "accepted_frames", "capture_epoch", "render_epoch",
        "clock_epoch", "capture_frames_in_epoch", "render_frames_in_epoch",
        "source_hash", "mic_float_hash", "render_float_hash",
    }
    for i, row in enumerate(rows):
        rate = RATES[i // 4]
        name, n, render = SCENES[i % 4]
        require(type(row) is dict and set(row) == keys_row and
                row["name"] == name and row["input_rate_hz"] == rate and
                row["mics"] == n and row["render"] == render and
                row["input_frame_samples"] == rate // 100 and
                type(row["state_bytes"]) is int and
                0 < row["state_bytes"] <= 4096 and
                row["state_bytes"] % 16 == 0 and
                row["src_state_per_stream_bytes"] == 224 and
                row["filter_delay_samples"] == {16000: 0, 32000: 5, 48000: 7}[rate] and
                type(row["negative_checks"]) is int and
                row["negative_checks"] >= 33 and
                row["accepted_frames"] == 100 and
                row["capture_epoch"] == 2 and
                row["render_epoch"] == (2 if render else 0) and
                row["clock_epoch"] == 1 and
                row["capture_frames_in_epoch"] == 10 and
                row["render_frames_in_epoch"] == (10 if render else 0),
                "UNQUALIFIED_RATE_OR_NEGATIVE_OR_EPOCH")
        for key in ("source_hash", "mic_float_hash", "render_float_hash"):
            require(bool(re.fullmatch(r"[0-9a-f]{16}", str(row[key]))),
                    "BAD_FINGERPRINT_" + key)
        if i % 4 > 0:
            require(row["state_bytes"] >= rows[i - 1]["state_bytes"],
                    "N_PLUS_RENDER_MEMORY_NOT_MONOTONE")
    for i in range(4):
        require(all(rows[4 * k + i]["state_bytes"] == rows[i]["state_bytes"]
                    for k in range(3)),
                "RATE_CHANGED_CONFIG_STATE_ALLOC")


def check_targets(results: dict) -> None:
    require(type(results) is dict and set(results) == set(TARGETS),
            "MISSING_EXECUTED_TARGET")
    for target in TARGETS:
        check_one(results[target])
    # Independent ABI/private state sizes, float output bits may differ.
    for i in range(12):
        for key in (
            "name", "input_rate_hz", "mics", "render", "input_frame_samples",
            "src_state_per_stream_bytes", "filter_delay_samples",
            "negative_checks", "accepted_frames", "capture_epoch",
            "render_epoch", "clock_epoch", "capture_frames_in_epoch",
            "render_frames_in_epoch", "source_hash",
        ):
            baseline = results["native"]["profiles"][i][key]
            require(all(results[t]["profiles"][i][key] == baseline
                        for t in TARGETS),
                    "CROSS_TARGET_CONTROL_OR_SOURCE_DRIFT_" + key)


def self_test() -> None:
    rows = []
    for rate in RATES:
        for name, n, render in SCENES:
            rows.append({
                "name": name, "input_rate_hz": rate, "mics": n,
                "render": render, "input_frame_samples": rate // 100,
                "state_bytes": {1: 400, 2: 640, 4: 1120}[n],
                "src_state_per_stream_bytes": 224,
                "filter_delay_samples": {16000: 0, 32000: 5, 48000: 7}[rate],
                "negative_checks": 43, "accepted_frames": 100,
                "capture_epoch": 2, "render_epoch": 2 if render else 0,
                "clock_epoch": 1, "capture_frames_in_epoch": 10,
                "render_frames_in_epoch": 10 if render else 0,
                "source_hash": "a" * 16, "mic_float_hash": "b" * 16,
                "render_float_hash": "c" * 16,
            })
    example = {
        "schema_version": 1, "decision": DECISION, "source_role": "first-party-synthetic",
        "sample_rate_hz_internal": 16000,
        "source_kernel": "src/frontend/ap_resampler.c",
        "bandlimited": True, "public_sdk_installed": False,
        "shipping_authority": False, "render_is_not_aec": True,
        "bf_integrated": False, "ssc305_dut_qualified": False,
        "real_adc_clock_qualified": False, "full_c4_budget_qualified": False,
        "repeats": 2, "profile_count": 12, "profiles": rows,
    }
    check_one(example)
    check_targets({t: copy.deepcopy(example) for t in TARGETS})
    for k, val in (
        ("decision", "PUBLIC_3X_SHIPPING"),
        ("bandlimited", False), ("bf_integrated", True),
        ("public_sdk_installed", True), ("render_is_not_aec", False),
        ("ssc305_dut_qualified", True), ("profile_count", 8),
    ):
        changed = copy.deepcopy(example)
        changed[k] = val
        try:
            check_one(changed)
        except B1B0Failure:
            pass
        else:
            raise B1B0Failure("FALSE_CLAIM_ACCEPTED_" + k)
    for k, val in (
        ("negative_checks", 3), ("filter_delay_samples", 10),
        ("capture_epoch", 0), ("render_epoch", 0),
        ("src_state_per_stream_bytes", 0),
    ):
        changed = copy.deepcopy(example)
        changed["profiles"][1][k] = val
        try:
            check_one(changed)
        except B1B0Failure:
            pass
        else:
            raise B1B0Failure("BAD_BOUNDARY_ACCEPTED_" + k)
    altered = {t: copy.deepcopy(example) for t in TARGETS}
    altered["arm"]["profiles"][5]["source_hash"] = "0" * 16
    try:
        check_targets(altered)
    except B1B0Failure:
        pass
    else:
        raise B1B0Failure("ARM_SOURCE_DRIFT_ACCEPTED")
    altered = {t: copy.deepcopy(example) for t in TARGETS}
    # Architecture-private state layout may differ, but all THREE input rates
    # must have the same layout for a fixed physical/render configuration.
    for rate_index in range(len(RATES)):
        altered["arm"]["profiles"][4 * rate_index]["state_bytes"] += 16
    check_targets(altered)  # private ARM layout differs; rate geometry does not
    try:
        strict_json('{"schema_version":1,"schema_version":2}')
    except tools.GateFailure:
        pass
    else:
        raise B1B0Failure("DUPLICATE_JSON_ACCEPTED")
    require(file_hash(SRC_C) == PINNED_SRC_C_SHA, "UPSTREAM_SRC_NOT_IDENTICAL")
    print("FE09_B1B0_SRC_SELF_TEST_PASS profiles=12")


def verify_artifact(out: Path, sha: str) -> None:
    require(out.is_dir() and {p.name for p in out.iterdir()} == set(MEMBERS),
            "WRONG_EVIDENCE_MEMBER_SET")
    expected = "".join(f"{file_hash(out / name)}  {name}\n"
                       for name in ("receipt.json", "collect.log", "verify.log"))
    require((out / "SHA256SUMS").read_text("ascii") == expected,
            "INNER_SHA256_MISMATCH")
    data = strict_json((out / "receipt.json").read_text("utf-8"))
    for k, v in source_identity(sha).items():
        require(data.get(k) == v, "SOURCE_IDENTITY_DRIFT_" + k)
    require(data.get("decision") == DECISION and
            data.get("targets") == list(TARGETS) and
            data.get("execution_mode") == "16_32_48k_10ms_bandlimited_N_render_SRC" and
            data.get("compiler_version") is not None and
            data.get("cpu_timing_claim") is False,
            "FALSE_BF_AEC_OR_DUT_PROMOTION")
    bins = data.get("binary_sha256")
    require(type(bins) is dict and set(bins) == set(TARGETS) and
            all(bool(re.fullmatch(r"[0-9a-f]{64}", str(x)))
                for x in bins.values()),
            "BINARY_HASH_INVALID")
    check_targets(data.get("target_results"))
    require("FE09_B1B0_SOURCE_RECEIPT_VERIFIED" in
            (out / "verify.log").read_text("utf-8"),
            "MISSING_VERIFICATION_MARKER")


def collect(out: Path, sha: str) -> None:
    require(not out.exists(), "OUTPUT_ALREADY_EXISTS")
    require(tools.source_head() == sha, "WRONG_GIT_CHECKOUT")
    receipt = source_identity(sha)
    receipt["decision"] = FAILURE
    logs: list[str] = []
    out.mkdir(parents=True)
    try:
        results, bins, compiler_info = {}, {}, {}
        with tempfile.TemporaryDirectory(prefix="fe09-b1b0-") as temp:
            root = Path(temp)
            include_dir = root / "include" / "audio_pipeline"
            include_dir.mkdir(parents=True)
            (include_dir / "audio_pipeline_build.h").write_text(
                "#ifndef AUDIO_PIPELINE_AUDIO_PIPELINE_BUILD_H\n"
                "#define AUDIO_PIPELINE_AUDIO_PIPELINE_BUILD_H\n"
                "#define AP_BUILD_RESAMPLER_BANDLIMITED 1\n"
                "#endif\n", encoding="ascii")
            for target in TARGETS:
                compiler = "arm-linux-gnueabihf-gcc" if target == "arm" else "cc"
                require(shutil.which(compiler) is not None,
                        "MISSING_COMPILER_" + target)
                compiler_info[target] = tools.run([compiler, "--version"], logs).splitlines()[0]
                prefix = root / target
                original = prefix.with_suffix(".src.o")
                test = prefix.with_suffix(".test.o")
                executable = prefix.with_suffix(".elf")
                options = [compiler, "-std=c11", "-Wall", "-Wextra",
                           "-Werror", "-O2", "-ffp-contract=off", "-fno-fast-math",
                           "-DAP_BUILD_RESAMPLER_BANDLIMITED=1",
                           "-I" + str(root / "include"), "-I" + str(ROOT / "src"),
                           "-I" + str(HERE)]
                if target == "sanitized":
                    options += ["-O1", "-g", "-fsanitize=address,undefined",
                                "-fno-omit-frame-pointer"]
                if target == "arm":
                    options += ["-march=armv7-a", "-mfpu=neon-vfpv4",
                                "-mfloat-abi=hard"]
                # Compile the unchanged existing first-party TU as itself, not
                # copied FIR/SRC code. Its older code is not -Wconversion clean;
                # the new private wrapper + tests ARE held to -Wconversion.
                tools.run(options + ["-c", str(SRC_C), "-o", str(original)],
                          logs, timeout=120)
                tools.run(options + ["-Wconversion", "-Wshadow", "-Wpedantic",
                                     "-c", str(HERE / "fe09_b1b0_src_test.c"),
                                     "-o", str(test)], logs, timeout=120)
                link = [compiler, str(original), str(test), "-lm", "-o",
                        str(executable)]
                if target == "sanitized":
                    link += ["-fsanitize=address,undefined"]
                if target == "arm":
                    link += ["-march=armv7-a", "-mfpu=neon-vfpv4",
                             "-mfloat-abi=hard"]
                tools.run(link, logs, timeout=120)
                bins[target] = file_hash(executable)
                if target == "arm":
                    require(shutil.which("qemu-arm") is not None and
                            Path("/usr/arm-linux-gnueabihf").is_dir(),
                            "MISSING_ARM_QEMU_SYSROOT")
                    command = ["qemu-arm", "-L", "/usr/arm-linux-gnueabihf",
                               str(executable)]
                else:
                    command = [str(executable)]
                env = dict(os.environ)
                if target == "sanitized":
                    env.update({"ASAN_OPTIONS": "detect_leaks=0:halt_on_error=1",
                                "UBSAN_OPTIONS": "halt_on_error=1"})
                first = strict_json(tools.run(command, logs, timeout=80, env=env))
                second = strict_json(tools.run(command, logs, timeout=80, env=env))
                require(first == second, "NONDETERMINISTIC_TARGET_" + target)
                check_one(first)
                results[target] = first
        check_targets(results)  # No positive claim before all targets
        receipt.update({
            "decision": DECISION, "targets": list(TARGETS),
            "execution_mode": "16_32_48k_10ms_bandlimited_N_render_SRC",
            "binary_sha256": bins, "compiler_version": compiler_info,
            "target_results": results, "cpu_timing_claim": False,
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
        (out / "collect.log").write_text("\n".join(logs) + "\n", encoding="utf-8")
        (out / "verify.log").write_text(
            "FE09_B1B0_SOURCE_RECEIPT_VERIFIED\n" if receipt.get("decision") == DECISION
            else FAILURE + "\n", encoding="utf-8")
        (out / "SHA256SUMS").write_text(
            "".join(f"{file_hash(out / name)}  {name}\n"
                    for name in ("receipt.json", "collect.log", "verify.log")),
            encoding="ascii")
    verify_artifact(out, sha)


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
        else:
            require(args.output is not None and args.execution_source is not None
                    and bool(re.fullmatch(r"[0-9a-f]{40}", args.execution_source)),
                    "EXACT_SOURCE_SHA_AND_OUTPUT_REQUIRED")
            if args.collect:
                collect(args.output, args.execution_source)
            else:
                require(tools.source_head() == args.execution_source,
                        "INDEPENDENT_VERIFICATION_WRONG_SOURCE")
                verify_artifact(args.output, args.execution_source)
            print(DECISION if args.collect else "FE09_B1B0_SOURCE_RECEIPT_VERIFIED")
    except (B1B0Failure, tools.GateFailure, ValueError, KeyError, OSError,
            AssertionError) as exc:
        print(FAILURE + ": " + str(exc))
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
