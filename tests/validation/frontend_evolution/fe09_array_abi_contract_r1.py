#!/usr/bin/env python3
"""FE09-R1: fail-closed, read-only current 2.x source / C4 ABI design contract."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import tempfile

ROOT = Path(__file__).resolve().parents[3]
CONTRACT = ".github/research/frontend-evolution-v1/fe09-r1-public-array-abi-contract.json"
ADR = "docs/research/frontend-evolution-v1/FE09_R1_ARRAY_ABI_ADR.md"
DECISION = "FE09_R1_PUBLIC_ARRAY_ABI_ARCHITECTURE_REVIEWED_NO_PRODUCT_PROMOTION"
R0_DECISION = "FE09_R0_C2_C4_MONO_SDK_BRIDGE_RESEARCH_ONLY_NO_PROMOTION"
PREDECESSOR_MAIN = "c1b91e5086b0f8a3e82dc35506de4bcc1be58942"
EVIDENCE_ZIP = "829ea522bce9e45b281b752808b2eac79cce620d6e67fc10cbd630d809eee315"
MAX_FILE = 512 * 1024

# Current-source text witnesses are fixed in code, not supplied as executable
# patterns by the policy JSON; an accidental macro-only C4 expansion fails.
# Pair: stable ID, checked repository path, anchored source regex, self-test witness.
PROBES = (
    ("PUBLIC_CAP_TWO", "include/audio_pipeline/audio_types.h",
     r"(?m)^#define AP_MAX_MIC_CHANNELS 2u\s*$", "#define AP_MAX_MIC_CHANNELS 2u"),
    ("FRAME_TEN_MS", "include/audio_pipeline/audio_types.h",
     r"(?m)^#define AP_FRAME_MS 10u\s*$", "#define AP_FRAME_MS 10u"),
    ("PUBLIC_SOURCE_IDENTITY", "include/audio_pipeline/audio_types.h",
     r"\bconst char \*source_revision;", "const char *source_revision;"),
    ("CMAKE_CAP_TWO", "CMakeLists.txt",
     r"(?m)^set\(AP_BUILD_MAX_MIC_CHANNELS 2 CACHE STRING\b",
     'set(AP_BUILD_MAX_MIC_CHANNELS 2 CACHE STRING "Maximum microphones")'),
    ("CMAKE_CAP_REJECTS_THREE_PLUS", "CMakeLists.txt",
     r"if\(AP_BUILD_MAX_MIC_CHANNELS LESS 1 OR AP_BUILD_MAX_MIC_CHANNELS GREATER 2\)",
     "if(AP_BUILD_MAX_MIC_CHANNELS LESS 1 OR AP_BUILD_MAX_MIC_CHANNELS GREATER 2)"),
    ("CMAKE_CURRENT_MAJOR_TWO", "CMakeLists.txt",
     r"project\(audio_pipeline VERSION 2\.\d+\.\d+ LANGUAGES C\)",
     "project(audio_pipeline VERSION 2.3.55 LANGUAGES C)"),
    ("COMPOSED_BF_REQUIRES_TWO", "src/core/ap_pipeline.c",
     r"if\s*\(config->mic_channels\s*!=\s*2u\s*\|\|",
     "if (config->mic_channels != 2u ||"),
    ("PUBLIC_FLOAT_BF_PAIR", "include/audio_pipeline/audio_modules.h",
     r"float \*mic0,\s*float \*mic1,", "float *mic0, float *mic1,"),
    ("FRONTEND_BF_HISTORY_PAIR", "src/frontend/ap_frontend.h",
     r"(?m)^#define AP_FRONTEND_MAX_MIC_CHANNELS 2u\s*$",
     "#define AP_FRONTEND_MAX_MIC_CHANNELS 2u"),
    ("RESAMPLER_TWO_MICS_PLUS_RENDER", "src/frontend/ap_resampler.h",
     r"(?m)^#define AP_RESAMPLER_INPUT_STREAMS 3u\s*$",
     "#define AP_RESAMPLER_INPUT_STREAMS 3u"),
    ("PIPELINE_MIC0_MIC1_MONO_SCRATCH", "src/core/ap_pipeline_internal.h",
     r"float mic0\[AP_INTERNAL_FRAME_MAX\];[\s\S]*?float mic1\[AP_INTERNAL_FRAME_MAX\];[\s\S]*?float mono\[AP_INTERNAL_FRAME_MAX\];",
     "float mic0[AP_INTERNAL_FRAME_MAX];\nfloat mic1[AP_INTERNAL_FRAME_MAX];\nfloat mono[AP_INTERNAL_FRAME_MAX];"),
    ("RUNTIME_CAPTURE_COMPILED_CAP", "src/platform/linux/ap_runtime.c",
     r"#define AP_RT_MAX_CAPTURE \(AP_BUILD_IO_FRAME_MAX \* AP_BUILD_MAX_MIC_CHANNELS\)",
     "#define AP_RT_MAX_CAPTURE (AP_BUILD_IO_FRAME_MAX * AP_BUILD_MAX_MIC_CHANNELS)"),
    ("FLIGHT_RECORDER_TWO", "src/platform/linux/ap_runtime.c",
     r"config->mic_channels\s*>\s*2u", "config->mic_channels > 2u"),
    ("CAPTURE_FRAME_CHANNELS", "src/platform/linux/ap_runtime.c",
     r"runtime->io_frames\s*\*\s*runtime->mic_channels",
     "runtime->io_frames * runtime->mic_channels"),
    ("PUBLIC_CAPTURE_PROCESS", "include/audio_pipeline/audio_pipeline.h",
     r"\bap_pipeline_process_capture\s*\(", "ap_pipeline_process_capture("),
    ("PUBLIC_DISCONTINUITY_CONTROL", "include/audio_pipeline/audio_pipeline.h",
     r"\bap_pipeline_notify_stream_discontinuity\s*\(",
     "ap_pipeline_notify_stream_discontinuity("),
    ("RESEARCH_ARRAY_MAX_FOUR", "tests/validation/frontend_evolution/array_native.h",
     r"(?m)^#define FE_ARRAY_MAX_MICS 4u\s*$",
     "#define FE_ARRAY_MAX_MICS 4u"),
    ("CURRENT_TWO_X_ABI_CONTRACT", "docs/API_CONTRACT.md",
     r"2\.x is the current public C API/ABI compatibility line",
     "2.x is the current public C API/ABI compatibility line"),
    ("PRESERVED_R0_THIRTEEN_NEGATIVES",
     "tests/validation/frontend_evolution/array_sdk_bridge_r0.py",
     r'entry\["negative_checks"\]\s*==\s*13',
     'entry["negative_checks"] == 13'),
)

DOC_MARKERS = (
    "# FE09-R1",
    "## A versus B / 方案对比",
    "## Source traceability / 源代码可追溯矩阵",
    "## Data-flow and ownership / 数据流及控制归属",
    "## Resource, quality and release gates / 资源、效果与发布",
    "## Deterministic offline gate / 防漂移门禁",
    DECISION,
    "B_NEXT_MAJOR_SINGLE_PRIVATE_ARRAY_CORE",
    "RETAIN_AS_BOUNDED_R0_REFERENCE_NOT_PRODUCT_DEFAULT",
    "No published 3.x SDK.",
    "UNKNOWN",
    "NOT an absolute shared hardware timestamp",
    "192 KiB",
    "SSC305",
    "13 negative controls",
)

BLOCKERS = (
    "R2_PUBLIC_3X_ABI_AND_SDK_IMPLEMENTATION_UNBUILT",
    "ORIGINAL_ADC_SAMPLE_ZERO_AND_CLOCK_DRIFT_UNKNOWN",
    "TRUE_C2_VS_C4_ACOUSTIC_GAIN_NOT_PROVED",
    "FULL_DUPLEX_BF_AEC_TOPOLOGY_NOT_ADMITTED",
    "FULL_C4_192KIB_MEMORY_CPU_AND_RUNTIME_NOT_MEASURED",
    "SSC305_BSP_P99_THERMAL_POWER_HIL_E001_NOT_QUALIFIED",
)


class GateError(Exception):
    """Deterministic contract rejection, not an environmental retry."""


def require(condition: bool, code: str) -> None:
    if not condition:
        raise GateError(code)


def digest(blob: bytes) -> str:
    return hashlib.sha256(blob).hexdigest()


def unique_pairs(pairs: list[tuple[str, object]]) -> dict:
    result: dict = {}
    for key, value in pairs:
        require(key not in result, "DUPLICATE_JSON_FIELD")
        result[key] = value
    return result


def reject_float(value: str) -> None:
    raise GateError("NONFINITE_JSON_VALUE")


def strict_json(raw: str) -> dict:
    result = json.loads(raw, object_pairs_hook=unique_pairs,
                        parse_constant=reject_float)
    require(type(result) is dict, "POLICY_NOT_OBJECT")
    return result


def read_source(root: Path, rel: str) -> str:
    require(rel in {path for _, path, _, _ in PROBES} | {ADR, CONTRACT},
            "UNREGISTERED_SOURCE_PATH")
    path = root / rel
    require(path.is_file() and not path.is_symlink() and
            0 < path.stat().st_size <= MAX_FILE, "MISSING_OR_OVERSIZED_SOURCE")
    return path.read_text(encoding="utf-8")


def validate(policy: dict, sources: dict[str, str]) -> None:
    expected_trace = [{"id": name, "path": path}
                      for name, path, _, _ in PROBES]
    require(policy.get("schema_version") == 1 and
            policy.get("experiment_id") ==
                "FE09-R1-PUBLIC-ARRAY-ABI-ARCHITECTURE-V1" and
            policy.get("decision") == DECISION and
            policy.get("decision_status") == "PROVISIONAL_DESIGN_ONLY" and
            policy.get("selected_architecture") ==
                "B_NEXT_MAJOR_SINGLE_PRIVATE_ARRAY_CORE" and
            policy.get("alternative_A_status") ==
                "RETAIN_AS_BOUNDED_R0_REFERENCE_NOT_PRODUCT_DEFAULT" and
            policy.get("source_trace") == expected_trace,
            "UNREGISTERED_DESIGN_OR_SOURCE_TRACE")
    require(policy.get("preregistration") ==
                "https://github.com/jiying2007/audio-pipeline/issues/728" and
            policy.get("predecessor_issue") == 726 and
            policy.get("predecessor_main_sha") == PREDECESSOR_MAIN and
            policy.get("predecessor_verify_run") == 38207813048 and
            policy.get("predecessor_release_run") == 38209605747 and
            policy.get("predecessor_fe09_artifact_id") == 11727908969 and
            policy.get("predecessor_fe09_artifact_zip_sha256") == EVIDENCE_ZIP and
            policy.get("predecessor_decision") == R0_DECISION,
            "R0_QUALIFIED_PREDECESSOR_IDENTITY_MISMATCH")
    for key in ("public_c4_enabled", "release_3x_published",
                "shipping_authority", "device_qualification",
                "realman_sample_clock_qualified",
                "scientific_bf_gain_qualified"):
        require(policy.get(key) is False, "UNQUALIFIED_PRODUCT_PROMOTION")
    require(policy.get("current_public_2x") == {
        "public_mic_max": 2,
        "build_mic_max": 2,
        "beamformer_active_mics": 2,
        "resampler_input_stream_count": 3,
        "flight_recorder_mic_max": 2,
        "frame_duration_ms": 10,
    }, "CURRENT_ABI_ENVELOPE_TAMPER")
    future = policy.get("proposed_future_contract")
    require(type(future) is dict and
            future.get("physical_mic_counts") == [1, 2, 4] and
            future.get("render_reference_channels") == [0, 1] and
            future.get("capture_layout") ==
                "EXPLICIT_S16_INTERLEAVED_BY_PHYSICAL_SLOT" and
            future.get("internal_processing") ==
                "EXPLICIT_NORMALIZED_FLOAT" and
            future.get("future_abi_status") == "UNIMPLEMENTED_UNFROZEN" and
            future.get("audio_clock_provenance") ==
                "UNKNOWN_UNTIL_ORIGINAL_SOURCE_AUDIT" and
            future.get("source_calibration_provenance") ==
                "UNKNOWN_UNTIL_ORIGINAL_SOURCE_AUDIT" and
            future.get("bf_aec_order") == "MEASURE_BOTH_BEFORE_SELECTION" and
            future.get("buffer_lifetime") ==
                "CALLER_OWNED_WITH_ATOMIC_REJECTION" and
            future.get("selected_sdk_release") == "NONE" and
            future.get("ssc305_cpu_p99") == "NOT_MEASURED" and
            future.get("target_C4_budget_KiB") == 192 and
            future.get("full_C4_budget_qualified") is False,
            "UNQUALIFIED_FUTURE_PUBLIC_API_OR_BUDGET")
    measured = policy.get("r0_measurement_boundary")
    require(type(measured) is dict and
            measured.get("c2_bf_state_bytes") == 2152 and
            measured.get("c4_bf_state_bytes") == 3704 and
            measured.get("mono_sdk_state_bytes") == 78192 and
            measured.get("c4_component_plus_mono_sdk_state_bytes") == 81896 and
            measured.get("full_runtime_ram_qualified") is False and
            measured.get("real_c4_dut_audio_qualified") is False and
            measured.get("hosted_timing_dut_authority") is False,
            "R0_PARTIAL_RESOURCE_MISREPRESENTED")
    require(policy.get("independent_blockers") == list(BLOCKERS),
            "REQUIRED_BLOCKER_MISSING_OR_REORDERED")

    for name, path, pattern, _ in PROBES:
        require(path in sources and
                re.search(pattern, sources[path]) is not None,
                "SOURCE_DRIFT_" + name)
    adr = sources.get(ADR, "")
    require(all(marker in adr for marker in DOC_MARKERS),
            "ADR_MISSING_REQUIRED_DECISION_OR_LIMITATION")
    # Static design-only ADR must never masquerade as an installed 3.x API.
    require("public_c4_enabled=true" not in adr and
            "shipping_authority=true" not in adr and
            "3.x SDK is released" not in adr,
            "ADR_FALSE_PRODUCT_PROMOTION")


def check(root: Path) -> dict:
    all_paths = {path for _, path, _, _ in PROBES} | {ADR, CONTRACT}
    contents = {path: read_source(root, path) for path in all_paths}
    policy = strict_json(contents[CONTRACT])
    validate(policy, contents)
    return {
        "status": "FE09_R1_SOURCE_CONTRACT_PASS",
        "decision": DECISION,
        "source_probes_checked": len(PROBES),
        "r0_main": PREDECESSOR_MAIN,
        "adr_sha256": digest(contents[ADR].encode("utf-8")),
        "contract_sha256": digest(contents[CONTRACT].encode("utf-8")),
        "shipping_authority": False,
        "real_hardware_qualified": False,
    }


def self_test() -> None:
    # Every witness is matched by its own regex; removing ANY one must reject.
    files: dict[str, str] = {}
    for _, path, pattern, witness in PROBES:
        require(re.search(pattern, witness) is not None, "BAD_PROBE_WITNESS")
        files[path] = files.get(path, "") + witness + "\n"
    files[ADR] = "\n".join(DOC_MARKERS) + "\n"
    # Small exact policy reads the genuine design manifest at this source root.
    policy = strict_json(read_source(ROOT, CONTRACT))
    validate(policy, files)
    for name, path, _, witness in PROBES:
        altered = dict(files)
        require(files[path].count(witness) == 1,
                "NON_UNIQUE_PROBE_WITNESS_" + name)
        altered[path] = altered[path].replace(witness,
                                              "SOURCE_WITNESS_ERASED", 1)
        try:
            validate(policy, altered)
        except GateError as exc:
            require(str(exc) == "SOURCE_DRIFT_" + name,
                    "WRONG_NEGATIVE_ERROR_" + name)
        else:
            raise GateError("MUTATED_PROBE_FALSE_ACCEPTED_" + name)
    for key in ("public_c4_enabled", "release_3x_published",
                "shipping_authority", "device_qualification",
                "realman_sample_clock_qualified",
                "scientific_bf_gain_qualified"):
        bad = dict(policy, **{key: True})
        try:
            validate(bad, files)
        except GateError as exc:
            require(str(exc) == "UNQUALIFIED_PRODUCT_PROMOTION",
                    "WRONG_PRODUCT_NEGATIVE_" + key)
        else:
            raise GateError("FALSE_PRODUCT_APPROVAL_" + key)
    invalid = dict(policy, source_trace=list(policy["source_trace"][:-1]))
    try:
        validate(invalid, files)
    except GateError as exc:
        require(str(exc) == "UNREGISTERED_DESIGN_OR_SOURCE_TRACE",
                "WRONG_TRACE_ERROR")
    else:
        raise GateError("MISSING_SOURCE_TRACE_FALSE_ACCEPTED")
    removed = dict(files)
    removed[ADR] = removed[ADR].replace(DOC_MARKERS[0], "CORRUPTED_DECISION", 1)
    try:
        validate(policy, removed)
    except GateError as exc:
        require(str(exc) == "ADR_MISSING_REQUIRED_DECISION_OR_LIMITATION",
                "WRONG_ADR_ERROR")
    else:
        raise GateError("CORRUPTED_ADR_FALSE_ACCEPTED")
    try:
        strict_json('{"schema_version":1,"schema_version":1}')
    except GateError as exc:
        require(str(exc) == "DUPLICATE_JSON_FIELD", "WRONG_DUPLICATE_ERROR")
    else:
        raise GateError("DUPLICATE_JSON_ACCEPTED")
    print("FE09_R1_ARCHITECTURE_CONTRACT_SELF_TEST_PASS "
          "source_probes=" + str(len(PROBES)))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--self-test", action="store_true")
    group.add_argument("--check", action="store_true")
    args = parser.parse_args()
    try:
        if args.self_test:
            self_test()
        else:
            print(json.dumps(check(ROOT), sort_keys=True,
                             separators=(",", ":"), allow_nan=False))
    except (GateError, OSError, UnicodeError, ValueError,
            json.JSONDecodeError) as exc:
        print("FE09_R1_ARCHITECTURE_UNRESOLVED: " + str(exc))
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
