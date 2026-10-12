#!/usr/bin/env python3
"""FE09-R0 first-party C2/C4 → existing 2.x mono SDK bridge; research only."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
SOURCE = HERE / "array_sdk_bridge_r0.c"
ARRAY = HERE / "array_native.c"
ARRAY_HEADER = HERE / "array_native.h"
SDK_HEADER = ROOT / "include/audio_pipeline/audio_types.h"
PIPELINE_HEADER = ROOT / "include/audio_pipeline/audio_pipeline.h"
DECISION = "FE09_R0_C2_C4_MONO_SDK_BRIDGE_RESEARCH_ONLY_NO_PROMOTION"
FAILURE = "FE09_R0_INTEGRATION_OR_ABI_GATE_FAILED"
PROFILE = (
    ("C2_ULA_35MM", 2, 19, 2152),
    ("C4_ULA_105MM", 4, 22, 3704),
    ("C4_UCA_RADIUS35MM", 4, 21, 3704),
)
MEMBERS = ("receipt.json", "collect.log", "verify.log", "SHA256SUMS")


class Rejected(ValueError):
    pass


def require(ok: bool, reason: str) -> None:
    if not ok:
        raise Rejected(reason)


def digest_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def hash_file(path: Path, cap: int = 4 * 1024 * 1024) -> str:
    require(path.is_file() and path.stat().st_size <= cap, "SOURCE_FILE_BOUNDS")
    return digest_bytes(path.read_bytes())


def strict_json(raw: str) -> dict:
    def unique(pairs: list) -> dict:
        result = {}
        for k, v in pairs:
            require(k not in result, "DUPLICATE_JSON_KEY")
            result[k] = v
        return result

    def bad_constant(value: str) -> None:
        raise Rejected("NONFINITE_JSON_CONSTANT_" + value)

    result = json.loads(raw, object_pairs_hook=unique, parse_constant=bad_constant)
    require(isinstance(result, dict), "JSON_OBJECT_EXPECTED")
    return result


def repo_head() -> str:
    result = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, timeout=15, text=True
    ).strip()
    require(bool(re.fullmatch(r"[0-9a-f]{40}", result)), "GIT_COMMIT_IDENTITY")
    return result


def run_cmd(args: list[str], *, timeout: int, log: list[str]) -> str:
    require(len(args) <= 30 and all(isinstance(x, str) for x in args),
            "COMMAND_INVALID")
    try:
        completed = subprocess.run(
            args, cwd=ROOT, check=False, capture_output=True,
            text=True, encoding="utf-8", errors="replace", timeout=timeout
        )
    except (OSError, subprocess.TimeoutExpired) as err:
        log.append("EXECUTION_FAILED command=" + repr(args) +
                   " error=" + type(err).__name__)
        raise Rejected("REFERENCE_TOOL_OR_RUNTIME_FAILED") from None
    out = completed.stdout + completed.stderr
    require(len(out.encode("utf-8")) <= 512 * 1024, "UNBOUNDED_TOOL_OUTPUT")
    log.append("command=" + repr(args))
    log.append("exit=" + str(completed.returncode))
    log.append("output_sha256=" + digest_bytes(out.encode("utf-8")))
    if completed.returncode:
        log.append("output_tail=" + out[-3000:])
        raise Rejected("REFERENCE_COMMAND_FAILED")
    return completed.stdout


def identity(source: str) -> dict:
    return {
        "schema_version": 1,
        "experiment_id": "FE09-R0-C2-C4-TO-SDK-MONO-BRIDGE",
        "preregistration": "https://github.com/jiying2007/audio-pipeline/issues/726",
        "source_commit": source,
        "source_role": "first-party-deterministic-synthetic",
        "c_harness_sha256": hash_file(SOURCE),
        "python_qualifier_sha256": hash_file(Path(__file__)),
        "array_core_sha256": hash_file(ARRAY),
        "array_header_sha256": hash_file(ARRAY_HEADER),
        "sdk_public_types_sha256": hash_file(SDK_HEADER),
        "sdk_public_pipeline_sha256": hash_file(PIPELINE_HEADER),
        "original_realman_data_used": False,
        "four_mic_public_sdk": False,
        "shipping_authority": False,
        "ssc305_hardware_qualified": False,
    }


def validate_payload(data: dict) -> None:
    require(data.get("schema_version") == 1 and
            data.get("decision") == DECISION and
            data.get("source_role") == "first-party-deterministic-synthetic" and
            data.get("installed_public_c4_supported") is False and
            data.get("shipping_authority") is False and
            data.get("product_qualification") is False and
            data.get("geometry_count") == 3 and data.get("run_repeats") == 2,
            "BRIDGE_DECISION_OR_BOUNDARY_TAMPER")
    build = data.get("sdk_build_info")
    require(isinstance(build, dict) and build.get("major") == 2 and
            build.get("max_mic_channels") == 2 and
            re.fullmatch(r"[0-9a-f]{64}", str(build.get("config_digest", ""))),
            "BUILT_PUBLIC_2X_SDK_IDENTITY")
    items = data.get("profiles")
    require(isinstance(items, list) and len(items) == len(PROFILE),
            "FROZEN_PROFILE_COUNT")
    previous_sdk_bytes = None
    for entry, (name, count, delay, state_bytes) in zip(items, PROFILE):
        require(isinstance(entry, dict) and
                set(entry) == {
                    "name", "mic_count", "fir33_common_delay_samples",
                    "array_state_bytes", "sdk_mono_state_bytes",
                    "capture_frame_bytes", "mono_frame_bytes",
                    "frames_per_repeat", "capture_gap_at_frame",
                    "negative_checks", "clipped_samples", "input_fnv64",
                    "bridge_fnv64", "sdk_fnv64"
                } and entry["name"] == name and
                entry["mic_count"] == count and
                entry["fir33_common_delay_samples"] == delay and
                entry["array_state_bytes"] == state_bytes and
                type(entry["sdk_mono_state_bytes"]) is int and
                0 < entry["sdk_mono_state_bytes"] <= 80000 and
                entry["capture_frame_bytes"] == 320 * count and
                entry["mono_frame_bytes"] == 320 and
                entry["frames_per_repeat"] == 100 and
                entry["capture_gap_at_frame"] == 50 and
                entry["negative_checks"] == 11 and
                type(entry["clipped_samples"]) is int and
                0 <= entry["clipped_samples"] <= 16000,
                "FROZEN_FRAME_GEOMETRY_OR_NEGATIVE_GATE")
        for key in ("input_fnv64", "bridge_fnv64", "sdk_fnv64"):
            require(bool(re.fullmatch(r"[0-9a-f]{16}", str(entry[key]))),
                    "RESULT_HASH_FORMAT")
        if previous_sdk_bytes is not None:
            require(entry["sdk_mono_state_bytes"] == previous_sdk_bytes,
                    "SDK_MONO_STATE_DRIFT_ACROSS_GEOMETRIES")
        previous_sdk_bytes = entry["sdk_mono_state_bytes"]


def collect(output: Path, source: str) -> None:
    require(not output.exists(), "OUTPUT_ALREADY_EXISTS")
    source_id = repo_head()
    require(source == source_id, "EXACT_SOURCE_COMMIT_DRIFT")
    data = identity(source)
    commands: list[str] = []
    output.mkdir(parents=True)
    result = None
    try:
        with tempfile.TemporaryDirectory(prefix="fe09-r0-") as tmp:
            work = Path(tmp)
            build = work / "cmake"
            binary = work / "fe09-bridge"
            cmake = [
                "cmake", "-S", str(ROOT), "-B", str(build),
                "-DCMAKE_BUILD_TYPE=Release",
                "-DAP_BUILD_PIPELINE=ON",
                "-DAP_BUILD_TESTS=OFF",
                "-DAP_BUILD_BENCH=OFF",
                "-DAP_BUILD_EXAMPLES=OFF",
                "-DAP_ENABLE_LINUX_RUNTIME=OFF",
                "-DAP_BUILD_MAX_MIC_CHANNELS=2",
                "-DAP_ENABLE_FAST_MATH=OFF",
            ]
            run_cmd(cmake, timeout=120, log=commands)
            run_cmd(["cmake", "--build", str(build), "--target",
                     "audio_pipeline", "--parallel", "2"],
                    timeout=240, log=commands)
            library = build / "libaudio_pipeline.a"
            generated = build / "generated/audio_pipeline/audio_pipeline_build.h"
            require(library.is_file() and generated.is_file(),
                    "REAL_PUBLIC_SDK_BUILD_MISSING")
            run_cmd([
                "cc", "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror",
                "-Wshadow", "-Wconversion", "-pedantic",
                "-ffp-contract=off", "-fno-fast-math",
                "-I" + str(ROOT / "include"),
                "-I" + str(build / "generated"),
                "-I" + str(HERE), str(SOURCE), str(ARRAY),
                str(library), "-lm", "-o", str(binary)
            ], timeout=90, log=commands)
            first = strict_json(run_cmd([str(binary)], timeout=45, log=commands))
            second = strict_json(run_cmd([str(binary)], timeout=45, log=commands))
            require(first == second, "DOUBLE_RUN_OUTPUT_FINGERPRINT_MISMATCH")
            validate_payload(first)
            timing = strict_json(
                run_cmd([str(binary), "--timing"], timeout=45, log=commands))
            assert "profiles" in timing
            for p in timing["profiles"]:
                require(type(p.get("combined_host_thread_cpu_ns_two_repeats"))
                        is int and p["combined_host_thread_cpu_ns_two_repeats"] > 0,
                        "HOST_TIMING_MISSING")
                del p["combined_host_thread_cpu_ns_two_repeats"]
            require(timing == first, "HOST_TIMED_PROFILE_CHANGED")
            data.update({
                "decision": DECISION,
                "sdk_library_sha256": hash_file(library, 100 * 1024 * 1024),
                "sdk_generated_header_sha256": hash_file(generated),
                "harness_elf_sha256": hash_file(binary, 32 * 1024 * 1024),
                "profile_results": first,
                "host_timing_two_repeats_ns": {
                    name: elapsed["combined_host_thread_cpu_ns_two_repeats"]
                    for name, elapsed in (
                        (t["name"], t) for t in strict_json(
                            run_cmd([str(binary), "--timing"], timeout=45,
                                    log=commands))["profiles"]
                    )
                },
                "total_physical_input_frames_per_repeat": 300,
                "total_mono_output_frames_per_repeat": 300,
                "decision_scope": "software-bridge-only-no-public-c4",
            })
            result = data
    except (Rejected, ValueError, KeyError, TypeError) as exc:
        data["decision"] = FAILURE
        data["failure_code"] = str(exc)[:128]
        result = data
        raise
    finally:
        # Original RAR, third-party source and PCM are never downloaded.
        # All compiler objects, executable and temporary generated files are gone.
        (output / "receipt.json").write_text(
            json.dumps(result, sort_keys=True, separators=(",", ":"),
                       allow_nan=False) + "\n", encoding="utf-8")
        (output / "collect.log").write_text(
            "\n".join(commands) + "\n", encoding="utf-8")
        (output / "verify.log").write_text(
            "FE09_R0_RESEARCH_BOUNDARY=NO_SHIPPING_PROMOTION\n"
            "TWO_IDENTICAL_100_FRAME_REPLAYS_PER_GEOMETRY="
            + ("PASS" if data.get("decision") == DECISION else "FAILED") + "\n",
            encoding="utf-8")
        seal(output)


def seal(output: Path) -> None:
    manifest = "".join(
        f"{hash_file(output/name)}  {name}\n"
        for name in ("receipt.json", "collect.log", "verify.log"))
    (output / "SHA256SUMS").write_text(manifest, encoding="ascii")


def verify(output: Path, source: str) -> None:
    require(output.is_dir() and {p.name for p in output.iterdir()} == set(MEMBERS),
            "ARTIFACT_FOUR_FILE_SET_INVALID")
    require(repo_head() == source, "RECEIPT_COMMIT_NOT_CURRENT")
    manifest = (output / "SHA256SUMS").read_text("ascii")
    require(manifest == "".join(
        f"{hash_file(output/name)}  {name}\n"
        for name in ("receipt.json", "collect.log", "verify.log")),
        "ARTIFACT_INNER_SHA256SUMS_MISMATCH")
    data = strict_json((output / "receipt.json").read_text("utf-8"))
    stable = identity(source)
    require(all(data.get(k) == v for k, v in stable.items()),
            "SOURCE_OR_BOUNDARY_IDENTITY_TAMPER")
    require(data.get("decision") == DECISION and
            data.get("decision_scope") == "software-bridge-only-no-public-c4" and
            data.get("total_physical_input_frames_per_repeat") == 300 and
            data.get("total_mono_output_frames_per_repeat") == 300,
            "RESEARCH_PROMOTION_OR_FRAME_COUNT_TAMPER")
    for key in ("sdk_library_sha256", "sdk_generated_header_sha256",
                "harness_elf_sha256"):
        require(bool(re.fullmatch(r"[0-9a-f]{64}", str(data.get(key, "")))),
                "SDK_BINARY_IDENTITY_MISSING")
    validate_payload(data["profile_results"])
    timings = data.get("host_timing_two_repeats_ns")
    require(isinstance(timings, dict) and
            set(timings) == {x[0] for x in PROFILE} and
            all(type(x) is int and 0 < x < 30000000000
                for x in timings.values()), "HOST_TIMING_PROFILE_INVALID")
    require("TWO_IDENTICAL_100_FRAME_REPLAYS_PER_GEOMETRY=PASS" in
            (output / "verify.log").read_text("utf-8"),
            "REPEAT_PROOF_NOT_RETAINED")


def self_test() -> None:
    fake = {
        "schema_version": 1, "decision": DECISION,
        "source_role": "first-party-deterministic-synthetic",
        "installed_public_c4_supported": False,
        "shipping_authority": False, "product_qualification": False,
        "geometry_count": 3, "run_repeats": 2,
        "sdk_build_info": {
            "major": 2, "max_mic_channels": 2, "config_digest": "a"*64
        },
        "profiles": [{
            "name": name, "mic_count": mic, "fir33_common_delay_samples": delay,
            "array_state_bytes": bytes_, "sdk_mono_state_bytes": 12345,
            "capture_frame_bytes": 320*mic, "mono_frame_bytes": 320,
            "frames_per_repeat": 100, "capture_gap_at_frame": 50,
            "negative_checks": 11, "clipped_samples": 0,
            "input_fnv64": "1234567890abcdef",
            "bridge_fnv64": "1234567890abcdef",
            "sdk_fnv64": "1234567890abcdef",
        } for name, mic, delay, bytes_ in PROFILE]
    }
    validate_payload(fake)
    for tampered in (
        {"decision": "SHIPPING_QUALIFIED"},
        {"installed_public_c4_supported": True},
        {"geometry_count": 4},
    ):
        invalid = dict(fake, **tampered)
        try:
            validate_payload(invalid)
        except Rejected:
            pass
        else:
            raise Rejected("NEGATIVE_FIXTURE_FALSE_ACCEPTED")
    print("FE09_R0_OFFLINE_SELF_TEST_PASS")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--self-test", action="store_true")
    modes.add_argument("--collect", action="store_true")
    modes.add_argument("--verify", action="store_true")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--execution-source")
    args = parser.parse_args()
    try:
        if args.self_test:
            self_test()
            return
        require(args.output is not None and args.execution_source is not None,
                "OUTPUT_AND_SOURCE_REQUIRED")
        require(bool(re.fullmatch(r"[0-9a-f]{40}", args.execution_source)),
                "EXECUTION_SOURCE_SHA_INVALID")
        if args.collect:
            collect(args.output, args.execution_source)
        else:
            verify(args.output, args.execution_source)
        print(DECISION if args.collect else "FE09_R0_SOURCE_RECEIPT_VERIFIED")
    except (Rejected, OSError, ValueError, json.JSONDecodeError) as exc:
        print("FE09_R0_INTEGRATION_OR_ABI_GATE_FAILED: " + str(exc))
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
