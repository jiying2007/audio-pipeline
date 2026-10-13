#!/usr/bin/env python3
"""FE09-R2A nonshipping, one-first-party-core ABI prototype qualification."""
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

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
SOURCES = (
    HERE / "fe09_array_sdk_draft_r2a.h",
    HERE / "fe09_array_sdk_draft_r2a.c",
    HERE / "fe09_array_sdk_draft_test_r2a.c",
    HERE / "array_native.h",
    HERE / "array_native.c",
    Path(__file__).resolve(),
)
DECISION = "FE09_R2A_UNIFIED_ARRAY_SDK_PROTOTYPE_RESEARCH_ONLY_NO_RELEASE"
FAILURE = "FE09_R2A_ABI_OR_LIFECYCLE_NOT_ADMITTED"
MEMBERS = ("SHA256SUMS", "receipt.json", "collect.log", "verify.log")
PROFILE = (
    ("C1_BASELINE", 1, 0, 17, 1376),
    ("C2_ULA_35MM", 2, 1, 19, 2152),
    ("C4_ULA_105MM", 4, 1, 22, 3704),
    ("C4_UCA_RADIUS35MM", 4, 1, 21, 3704),
)
TARGETS = ("native", "sanitized", "arm")
# C11 research adapter contains pointer-bearing private state. Keep the actual
# pinned 64-bit and AArch32 layout individually constrained, never demand
# identical sizeof(private_header) across ABIs or infer any shipping SDK ABI.
EXPECTED_ADAPTER_HEADER_BYTES = {"native": 96, "sanitized": 96, "arm": 80}
CAP = 4 * 1024 * 1024


class GateFailure(ValueError):
    pass


def require(condition: bool, reason: str) -> None:
    if not condition:
        raise GateFailure(reason)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def file_sha(path: Path, cap: int = CAP) -> str:
    require(path.is_file() and not path.is_symlink() and
            0 < path.stat().st_size <= cap, "MISSING_OR_OVERSIZED_SOURCE")
    return sha256(path.read_bytes())


def strict_json(raw: str) -> dict:
    def unique(pairs: list) -> dict:
        out = {}
        for k, v in pairs:
            require(k not in out, "DUPLICATE_JSON_KEY")
            out[k] = v
        return out

    def invalid_float(value: str) -> None:
        raise GateFailure("NONFINITE_JSON")

    result = json.loads(raw, object_pairs_hook=unique, parse_constant=invalid_float)
    require(type(result) is dict, "JSON_OBJECT_EXPECTED")
    return result


def source_head() -> str:
    v = subprocess.check_output(
        ["git", "-c", "safe.directory=" + str(ROOT), "rev-parse", "HEAD"],
        cwd=ROOT, timeout=15, text=True).strip()
    require(bool(re.fullmatch(r"[0-9a-f]{40}", v)), "SOURCE_SHA_MALFORMED")
    return v


def run(args: list[str], log: list[str], timeout: int = 90,
        env: dict | None = None) -> str:
    require(all(isinstance(x, str) for x in args) and len(args) < 32,
            "COMMAND_NOT_BOUNDED")
    try:
        out = subprocess.run(args, cwd=ROOT, text=True, encoding="utf-8",
                             errors="replace", capture_output=True, check=False,
                             timeout=timeout, env=env)
    except (OSError, subprocess.TimeoutExpired) as exc:
        log.append("ERROR " + repr(args) + " " + type(exc).__name__)
        raise GateFailure("TOOL_OR_TIMEOUT_FAILED") from None
    content = out.stdout + out.stderr
    require(len(content.encode("utf-8")) < 512 * 1024, "TOOL_OUTPUT_UNBOUNDED")
    log.append("CMD " + repr(args))
    log.append("EXIT " + str(out.returncode))
    log.append("STDOUT_SHA256 " + sha256(out.stdout.encode("utf-8")))
    log.append("STDERR_SHA256 " + sha256(out.stderr.encode("utf-8")))
    if out.returncode:
        log.append("FAILURE_OUTPUT_TAIL " + content[-5000:])
        raise GateFailure("COMMAND_FAILED")
    return out.stdout


def source_identity(sha: str) -> dict:
    return {
        "source_commit": sha,
        "preregistration": "https://github.com/jiying2007/audio-pipeline/issues/730",
        "stage": "FE09-R2A-NONINSTALLED-SDK-DRAFT",
        "source_sha256": {p.name: file_sha(p) for p in SOURCES},
        "official_2x_sdk_unchanged": True,
        "public_3x_sdk_installed": False,
        "shipping_authority": False,
        "ssc305_dut_qualified": False,
        "realman_adc_clock_qualified": False,
        "real_speech_bf_quality_admitted": False,
        "full_c4_192kib_budget_admitted": False,
    }


def check_result(result: dict) -> None:
    require(result.get("schema_version") == 1 and
            result.get("decision") == DECISION and
            result.get("public_sdk_installed") is False and
            result.get("shipping_authority") is False and
            result.get("actual_adc_clock_qualified") is False and
            result.get("target_cpu_qualified") is False and
            result.get("render_is_not_aec") is True and
            result.get("source_role") == "first-party-synthetic" and
            result.get("profile_count") == 4 and
            result.get("repeats") == 2,
            "PROMOTION_OR_REPLAY_CONTRACT_DRIFT")
    rows = result.get("profiles")
    require(type(rows) is list and len(rows) == len(PROFILE), "PROFILE_SET_INVALID")
    for row, (name, count, render, delay, native_bytes) in zip(rows, PROFILE):
        require(type(row) is dict and
                set(row) == {
                    "name", "physical_mics", "render_channels", "state_bytes",
                    "native_fir33_bytes", "common_delay_samples",
                    "capture_frame_bytes", "render_frame_bytes",
                    "frames_per_repeat", "negative_checks",
                    "capture_epoch", "render_epoch", "clipped_samples",
                    "input_fnv64", "render_fnv64", "output_fnv64"
                } and
                row.get("name") == name and
                row.get("physical_mics") == count and
                row.get("render_channels") == render and
                row.get("native_fir33_bytes") == native_bytes and
                type(row.get("state_bytes")) is int and
                native_bytes < row["state_bytes"] <= native_bytes + 256 and
                row.get("common_delay_samples") == delay and
                row.get("capture_frame_bytes") == 320 * count and
                row.get("render_frame_bytes") == 320 * render and
                row.get("frames_per_repeat") == 100 and
                row.get("negative_checks") == 25 and
                row.get("capture_epoch") == 1 and
                row.get("render_epoch") == render and
                row.get("clipped_samples") == 0,
                "R2A_MATRIX_OR_NEGATIVE_GATE_FAILED")
        for key in ("input_fnv64", "render_fnv64", "output_fnv64"):
            require(bool(re.fullmatch("[0-9a-f]{16}", str(row[key]))),
                    "NONDETERMINISTIC_FINGERPRINT_FORMAT")


def check_target_contract(suites: dict) -> None:
    require(type(suites) is dict and set(suites) == set(TARGETS),
            "MISSING_TARGET_EVIDENCE")
    for target in TARGETS:
        check_result(suites[target])
        rows = suites[target]["profiles"]
        overhead = EXPECTED_ADAPTER_HEADER_BYTES[target]
        for row in rows:
            require(row["state_bytes"] == row["native_fir33_bytes"] + overhead,
                    "ABI_SPECIFIC_ADAPTER_STATE_SIZE_MISMATCH_" + target)
    # Same source/fixture controls must agree, but pointer-layout sizeof
    # differs (64-bit host header=96 B, AArch32 header=80 B). DSP output
    # hashes are intentionally NOT required bit-identical across targets.
    for key in ("native_fir33_bytes", "common_delay_samples",
                "capture_frame_bytes", "render_frame_bytes", "frames_per_repeat",
                "negative_checks", "capture_epoch", "render_epoch",
                "clipped_samples"):
        for index in range(len(PROFILE)):
            baseline = suites["native"]["profiles"][index][key]
            require(all(suites[target]["profiles"][index][key] == baseline
                        for target in TARGETS),
                    "ARCHITECTURE_CONTRACT_MISMATCH_" + key)


def self_test() -> None:
    a = {
        "schema_version": 1, "decision": DECISION,
        "public_sdk_installed": False, "shipping_authority": False,
        "actual_adc_clock_qualified": False, "target_cpu_qualified": False,
        "render_is_not_aec": True, "source_role": "first-party-synthetic",
        "profile_count": 4, "repeats": 2,
        "profiles": [{
            "name": name, "physical_mics": n, "render_channels": render,
            "state_bytes": state + 96, "native_fir33_bytes": state,
            "common_delay_samples": delay, "capture_frame_bytes": 320*n,
            "render_frame_bytes": 320*render, "frames_per_repeat": 100,
            "negative_checks": 25, "capture_epoch": 1, "render_epoch": render,
            "clipped_samples": 0,
            "input_fnv64": "a"*16, "render_fnv64": "b"*16,
            "output_fnv64": "c"*16
        } for name, n, render, delay, state in PROFILE]
    }
    check_result(a)
    valid_targets = {
        target: json.loads(json.dumps(a)) for target in TARGETS
    }
    for row in valid_targets["arm"]["profiles"]:
        row["state_bytes"] -= 16
    check_target_contract(valid_targets)
    # Both a false AArch32 64-bit layout and native/sanitized drift must fail.
    for target, delta in (("arm", 16), ("sanitized", 16)):
        wrong_target = json.loads(json.dumps(valid_targets))
        wrong_target[target]["profiles"][0]["state_bytes"] += delta
        try:
            check_target_contract(wrong_target)
        except GateFailure:
            pass
        else:
            raise GateFailure("CROSS_ARCH_PRIVATE_ABI_LAYOUT_FALSE_ACCEPT")
    for k, val in (
        ("decision", "PUBLIC_3X_RELEASED"), ("shipping_authority", True),
        ("actual_adc_clock_qualified", True), ("profile_count", 3),
        ("render_is_not_aec", False),
    ):
        changed = dict(a, **{k: val})
        try:
            check_result(changed)
        except GateFailure:
            pass
        else:
            raise GateFailure("NEGATIVE_PROMOTION_ACCEPTED")
    wrong = json.loads(json.dumps(a))
    wrong["profiles"][2]["negative_checks"] = 24
    try:
        check_result(wrong)
    except GateFailure:
        pass
    else:
        raise GateFailure("MISSING_NEGATIVE_ACCEPTED")
    try:
        strict_json('{"schema_version":1,"schema_version":1}')
    except GateFailure:
        pass
    else:
        raise GateFailure("DUPLICATE_JSON_ACCEPTED")
    print("FE09_R2A_CONTRACT_SELF_TEST_PASS negatives=7")


def verify_artifact(output: Path, sha: str) -> None:
    require(output.is_dir() and
            {p.name for p in output.iterdir()} == set(MEMBERS),
            "EVIDENCE_FILE_SET_NOT_FOUR")
    expected = "".join(
        f"{file_sha(output / name)}  {name}\n"
        for name in ("receipt.json", "collect.log", "verify.log"))
    require((output / "SHA256SUMS").read_text("ascii") == expected,
            "MANIFEST_SHA_MISMATCH")
    data = strict_json((output / "receipt.json").read_text("utf-8"))
    stable = source_identity(sha)
    require(all(data.get(k) == v for k, v in stable.items()),
            "SOURCE_PROVENANCE_OR_CLAIM_TAMPER")
    require(data.get("schema_version") == 1 and
            data.get("decision") == DECISION and
            data.get("targets") == list(TARGETS) and
            data.get("sample_rate_hz") == 16000 and
            data.get("frame_ms") == 10 and
            data.get("resampler_rate_extension") is False and
            data.get("unstable_major_abi") is True,
            "STAGE_OR_TARGET_AUTHORITY_DRIFT")
    hashes = data.get("binary_sha256")
    require(type(hashes) is dict and set(hashes) == set(TARGETS) and
            all(bool(re.fullmatch(r"[0-9a-f]{64}", str(v))) for v in hashes.values()),
            "BINARY_HASHES_INVALID")
    suites = data.get("target_results")
    require(type(suites) is dict and set(suites) == set(TARGETS),
            "MISSING_TARGET_EVIDENCE")
    check_target_contract(suites)
    observations = data.get("host_process_cpu_ns_two_repeats")
    require(type(observations) is dict and
            set(observations) == {x[0] for x in PROFILE} and
            all(type(v) is int and v > 0 for v in observations.values()),
            "HOST_TIMING_NOT_OBSERVED")
    require("FE09_R2A_SOURCE_RECEIPT_VERIFIED" in
            (output / "verify.log").read_text("utf-8"),
            "VERIFY_PROVENANCE_LOG_MISSING")


def collect(output: Path, sha: str) -> None:
    require(not output.exists(), "OUTPUT_ALREADY_EXISTS")
    require(source_head() == sha, "WRONG_GITHUB_EXECUTION_SOURCE")
    log: list[str] = []
    evidence = source_identity(sha)
    output.mkdir(parents=True)
    try:
        with tempfile.TemporaryDirectory(prefix="fe09-r2a-") as temp:
            tempdir = Path(temp)
            results, binaries = {}, {}
            for target in TARGETS:
                compiler = "arm-linux-gnueabihf-gcc" if target == "arm" else "cc"
                require(shutil.which(compiler) is not None, "COMPILER_NOT_FOUND_" + target)
                exe = tempdir / ("test-" + target)
                args = [compiler, "-std=c11", "-Wall", "-Wextra", "-Werror",
                        "-Wshadow", "-Wconversion", "-Wpedantic",
                        "-ffp-contract=off", "-fno-fast-math", "-O2"]
                if target == "sanitized":
                    args += ["-O1", "-g", "-fsanitize=address,undefined",
                             "-fno-omit-frame-pointer"]
                if target == "arm":
                    args += ["-march=armv7-a", "-mfpu=neon-vfpv4",
                             "-mfloat-abi=hard"]
                args += ["-I" + str(HERE),
                         str(HERE / "fe09_array_sdk_draft_test_r2a.c"),
                         str(HERE / "fe09_array_sdk_draft_r2a.c"),
                         str(HERE / "array_native.c"), "-lm", "-o", str(exe)]
                run(args, log, timeout=120)
                binaries[target] = file_sha(exe, 16 * 1024 * 1024)
                call = ([str(exe)] if target != "arm" else
                        ["qemu-arm", "-L", "/usr/arm-linux-gnueabihf", str(exe)])
                if target == "arm":
                    require(shutil.which("qemu-arm") is not None and
                            Path("/usr/arm-linux-gnueabihf").is_dir(),
                            "ARM_QEMU_SYSROOT_MISSING")
                env = dict(os.environ)
                if target == "sanitized":
                    env.update({"ASAN_OPTIONS": "detect_leaks=0:halt_on_error=1",
                                "UBSAN_OPTIONS": "halt_on_error=1"})
                first = strict_json(run(call, log, timeout=60, env=env))
                second = strict_json(run(call, log, timeout=60, env=env))
                require(first == second, "TARGET_REPEAT_NOT_BITWISE_" + target)
                check_result(first)
                results[target] = first
            # Evaluate cross-target architecture boundaries BEFORE sealing any
            # positive receipt; a failed gate must retain a FAILED decision.
            check_target_contract(results)
            timed = strict_json(run([str(tempdir / "test-native"), "--timing"],
                                    log, timeout=60))
            cpu = {}
            for profile in timed["profiles"]:
                elapsed = profile.pop("host_thread_cpu_ns_two_repeats", None)
                require(type(elapsed) is int and elapsed > 0,
                        "HOST_CPU_CLOCK_NOT_OBSERVED")
                cpu[profile["name"]] = elapsed
            require(timed == results["native"], "TIMED_RUN_FUNCTIONAL_DRIFT")
            evidence.update({
                "schema_version": 1,
                "decision": DECISION,
                "targets": list(TARGETS),
                "sample_rate_hz": 16000,
                "frame_ms": 10,
                "resampler_rate_extension": False,
                "unstable_major_abi": True,
                "binary_sha256": binaries,
                "target_results": results,
                "host_process_cpu_ns_two_repeats": cpu,
                "timing_method": "CLOCK_THREAD_CPUTIME_ID around research adapter process only; hosted-descriptive-not-DUT",
            })
    except Exception as err:
        evidence["decision"] = FAILURE
        evidence["failure_class"] = type(err).__name__
        evidence["failure_code"] = str(err)[:160]
        raise
    finally:
        (output / "receipt.json").write_text(
            json.dumps(evidence, sort_keys=True, separators=(",", ":"),
                       allow_nan=False) + "\n", encoding="utf-8")
        (output / "collect.log").write_text("\n".join(log) + "\n", encoding="utf-8")
        (output / "verify.log").write_text(
            ("FE09_R2A_SOURCE_RECEIPT_VERIFIED\n" if evidence.get("decision") == DECISION
             else "FE09_R2A_ABI_OR_LIFECYCLE_NOT_ADMITTED\n"),
            encoding="utf-8")
        manifest = "".join(f"{file_sha(output / n)}  {n}\n"
                           for n in ("receipt.json", "collect.log", "verify.log"))
        (output / "SHA256SUMS").write_text(manifest, encoding="ascii")
    verify_artifact(output, sha)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--self-test", action="store_true")
    group.add_argument("--collect", action="store_true")
    group.add_argument("--verify", action="store_true")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--execution-source", type=str)
    args = parser.parse_args()
    try:
        if args.self_test:
            self_test()
            return
        require(args.output is not None and args.execution_source is not None and
                bool(re.fullmatch("[0-9a-f]{40}", args.execution_source)),
                "OUTPUT_AND_EXACT_SOURCE_REQUIRED")
        if args.collect:
            collect(args.output, args.execution_source)
        else:
            require(source_head() == args.execution_source,
                    "VERIFICATION_EXECUTION_SHA_DRIFT")
            verify_artifact(args.output, args.execution_source)
        print(DECISION if args.collect else "FE09_R2A_SOURCE_RECEIPT_VERIFIED")
    except (GateFailure, OSError, ValueError, AssertionError, KeyError,
            subprocess.CalledProcessError) as e:
        print(FAILURE + ": " + str(e))
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
