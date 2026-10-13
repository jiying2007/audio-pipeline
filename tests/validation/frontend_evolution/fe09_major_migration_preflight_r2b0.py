#!/usr/bin/env python3
"""FE09-R2B0 read-only next-major source preflight; no SDK release or migration."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[3]
CONTRACT = ".github/research/frontend-evolution-v1/fe09-r2b0-major-migration-contract.json"
ADR = "docs/research/frontend-evolution-v1/FE09_R2B0_MAJOR_MIGRATION_PREFLIGHT.md"
PROBES = [
  [
    "CMAKE_MAJOR_TWO",
    "CMakeLists.txt",
    "project(audio_pipeline VERSION 2.3.55 LANGUAGES C)"
  ],
  [
    "CMAKE_DEFAULT_C2",
    "CMakeLists.txt",
    "set(AP_BUILD_MAX_MIC_CHANNELS 2 CACHE STRING \"Maximum microphone channels compiled into this SKU\")"
  ],
  [
    "CMAKE_REJECT_C4",
    "CMakeLists.txt",
    "if(AP_BUILD_MAX_MIC_CHANNELS LESS 1 OR AP_BUILD_MAX_MIC_CHANNELS GREATER 2)"
  ],
  [
    "PUBLIC_MAX_C2",
    "include/audio_pipeline/audio_types.h",
    "#define AP_MAX_MIC_CHANNELS 2u"
  ],
  [
    "PUBLIC_10MS",
    "include/audio_pipeline/audio_types.h",
    "#define AP_FRAME_MS 10u"
  ],
  [
    "PUBLIC_ARENA_80000",
    "include/audio_pipeline/audio_pipeline.h",
    "#define AP_PIPELINE_STATE_MAX_BYTES 80000u"
  ],
  [
    "PUBLIC_CTRL_V2",
    "include/audio_pipeline/audio_pipeline.h",
    "#define AP_PIPELINE_CONTROL_API_VERSION 2u"
  ],
  [
    "PUBLIC_CONFIG_VALUE_STRUCT",
    "include/audio_pipeline/audio_pipeline.h",
    "typedef struct ap_config {"
  ],
  [
    "PUBLIC_CONFIG_STRUCT_END",
    "include/audio_pipeline/audio_pipeline.h",
    "} ap_config_t;"
  ],
  [
    "PUBLIC_METRICS_VALUE_STRUCT",
    "include/audio_pipeline/audio_pipeline.h",
    "typedef struct ap_metrics {"
  ],
  [
    "PUBLIC_METRICS_END",
    "include/audio_pipeline/audio_pipeline.h",
    "} ap_metrics_t;"
  ],
  [
    "PUBLIC_GLOBAL_STATE_QUERY",
    "include/audio_pipeline/audio_pipeline.h",
    "size_t ap_pipeline_state_size(void);"
  ],
  [
    "PUBLIC_CAPTURE_INGRESS",
    "include/audio_pipeline/audio_pipeline.h",
    "ap_status_t ap_pipeline_process_capture("
  ],
  [
    "PUBLIC_SEPARATE_RENDER",
    "include/audio_pipeline/audio_pipeline.h",
    "ap_status_t ap_pipeline_push_render("
  ],
  [
    "CORE_BF_C2_ONLY",
    "src/core/ap_pipeline.c",
    "if (config->mic_channels != 2u ||"
  ],
  [
    "CORE_FIXED_STATE",
    "src/core/ap_pipeline.c",
    "size_t ap_pipeline_state_size(void) { return sizeof(ap_pipeline_t); }"
  ],
  [
    "SRC_THREE_STREAMS",
    "src/frontend/ap_resampler.h",
    "#define AP_RESAMPLER_INPUT_STREAMS 3u"
  ],
  [
    "SRC_HISTORY_LAYOUT",
    "src/frontend/ap_resampler.h",
    "float input_history[AP_RESAMPLER_INPUT_STREAMS][AP_RESAMPLER_HISTORY];"
  ],
  [
    "SRC_UNCHECKED_VOID_API",
    "src/frontend/ap_resampler.h",
    "void ap_resample_input_channel("
  ],
  [
    "SRC_DIRECT_INDEX",
    "src/frontend/ap_resampler.c",
    "float *hist=s->input_history[stream];"
  ],
  [
    "RUNTIME_C2_QUEUE",
    "src/platform/linux/ap_runtime.c",
    "#define AP_RT_MAX_CAPTURE (AP_BUILD_IO_FRAME_MAX * AP_BUILD_MAX_MIC_CHANNELS)"
  ],
  [
    "RECORDER_REJECT_C4",
    "src/platform/linux/ap_runtime.c",
    "config->mic_channels > 2u"
  ],
  [
    "RECORDER_MIC_STRIDE",
    "src/platform/linux/ap_runtime.c",
    "bytes += (size_t)config->frame_samples * config->mic_channels * sizeof(int16_t);"
  ],
  [
    "DUMP_FORMAT_FIELD",
    "src/platform/linux/ap_runtime.c",
    "uint32_t format_version;"
  ],
  [
    "DUMP_STRIDE_FIELD",
    "src/platform/linux/ap_runtime.c",
    "uint32_t record_stride;"
  ],
  [
    "DUMP_ENDIAN_TAG",
    "src/platform/linux/ap_runtime.c",
    "#define AP_DUMP_ENDIAN_TAG 0x01020304u"
  ],
  [
    "DIAG_DUMP_V1",
    "include/audio_pipeline/audio_diag.h",
    "#define AP_DUMP_FORMAT_VERSION 1u"
  ],
  [
    "RUNTIME_SUBMIT_C2",
    "include/audio_pipeline/audio_runtime.h",
    "ap_status_t ap_runtime_submit_frame("
  ],
  [
    "RUNTIME_CAPTURE_CLOCK_FIELD",
    "include/audio_pipeline/audio_runtime.h",
    "uint64_t capture_timestamp_ns;"
  ],
  [
    "R2A_PRIVATE_RATE",
    "tests/validation/frontend_evolution/fe09_array_sdk_draft_r2a.h",
    "#define FE_R2A_RATE_HZ 16000u"
  ],
  [
    "R2A_DRAFT_ONLY",
    "tests/validation/frontend_evolution/fe09_array_sdk_draft_r2a.h",
    "#define FE_R2A_DRAFT_VERSION UINT32_C(0x00030000)"
  ],
  [
    "R2A_UNQUALIFIED_ADC",
    "tests/validation/frontend_evolution/fe09_array_sdk_draft_r2a.h",
    "uint32_t capture_clock_authority;"
  ],
  [
    "PUBLIC_2X_LINE",
    "docs/API_CONTRACT.md",
    "2.x is the current public C API/ABI compatibility line."
  ],
  [
    "R1_PROVISIONAL_B",
    "docs/research/frontend-evolution-v1/FE09_R1_ARRAY_ABI_ADR.md",
    "**Architectural decision (provisional):** `B_NEXT_MAJOR_SINGLE_PRIVATE_ARRAY_CORE`."
  ]
]
BLOBS = {
  "CMakeLists.txt": "2c7ac085e04ab8f3b9682698001a50b8a2a0cf75",
  "include/audio_pipeline/audio_types.h": "f7bc9819d51770d919e0020193205908ad9dcd88",
  "include/audio_pipeline/audio_pipeline.h": "8df6d78b41610f191de1a3e90704507b58ee4d9d",
  "src/core/ap_pipeline.c": "7fc79076224fd306dacdf9770f30609cfad27fd3",
  "src/frontend/ap_resampler.h": "f502b794cdab261d2f57991b54aae44f3703121a",
  "src/frontend/ap_resampler.c": "24b979221adef7d099cb73ec9b986f17a64d63d7",
  "src/platform/linux/ap_runtime.c": "9a0013f1983f8e2dc807fd9b8493837f7d53ef83",
  "include/audio_pipeline/audio_diag.h": "1eff3abd18bcf99f325c2e1370e795a81735344e",
  "include/audio_pipeline/audio_runtime.h": "57488eb20164cbe78a7b030e33b2fb3b4ef94103",
  "tests/validation/frontend_evolution/fe09_array_sdk_draft_r2a.h": "656d736eb2ac69933ccfc0cb125189c98fee62da",
  "docs/API_CONTRACT.md": "bd7be016153ed09c83194bf7d20816e9788a4356",
  "docs/research/frontend-evolution-v1/FE09_R1_ARRAY_ABI_ADR.md": "f9d1a18263c9be2d98218caca14d6751ac4844b7"
}
PREDECESSORS = {
  "r2a_main_sha": "36944fa85e180bdadbac5800bd7fe3cf35d6a619",
  "r2a_verify_run": 38325347248,
  "r2a_release_run": 38327722158,
  "r2a_artifact_id": 11780358590,
  "r2a_artifact_zip_sha256": "c15d83903a572ec51a07d2130c8e198d8628e25d9b55330ac51190acabb5f801",
  "r2a_decision": "FE09_R2A_UNIFIED_ARRAY_SDK_PROTOTYPE_RESEARCH_ONLY_NO_RELEASE",
  "b0_base_main_sha": "6fcb74f5f498dc68fab6127d8bf9bf35411f7d61",
  "b0_base_verify_run": 38330235032,
  "b0_base_release_run": 38333092634,
  "b0_base_research_gc_run": 38330234686,
  "b0_base_terminal_gc_run": 38330234666
}
LEGACY = {
  "frame_ms": 10,
  "max_physical_microphones": 2,
  "installed_major": 2,
  "state_arena_ceiling_bytes": 80000,
  "control_api_version": 2,
  "src_histories_total": 3,
  "flight_recorder_max_mics": 2,
  "dump_format_version": 1,
  "config_struct_is_version_tagged": False,
  "metrics_struct_is_version_tagged": False,
  "state_query_is_config_specific": False
}
PROPOSED = {
  "mic_counts": [
    1,
    2,
    4
  ],
  "render_reference_channels": [
    0,
    1
  ],
  "r2a_only_admitted_io_hz": 16000,
  "additional_io_rates_not_qualified": [
    8000,
    24000,
    32000,
    48000
  ],
  "capture_clock_authority": "UNKNOWN",
  "calibration_authority": "UNKNOWN",
  "two_x_abi_can_be_silently_widened": False,
  "public_major3_abi_status": "UNIMPLEMENTED_UNFROZEN",
  "bf_aec_order": "PAIRED_EVIDENCE_NOT_ADMITTED",
  "config_specific_state_size": "NOT_IMPLEMENTED",
  "target_C4_full_budget_KiB": 192,
  "full_C4_system_budget_qualified": False,
  "c4_r0_array_plus_mono_state_bytes": 81896,
  "c4_r0_sum_is_full_runtime_budget": False
}
CLAIMS = {
  "public_c4_enabled": False,
  "release_3x_published": False,
  "shipping_authority": False,
  "ssc305_dut_qualified": False,
  "realman_capture_clock_qualified": False,
  "real_c4_acoustic_gain_qualified": False,
  "hardened_full_duplex_admitted": False,
  "e001_product_certified": False
}
PHASES = {
  "R2B0": "READ_ONLY_PREFLIGHT_ONLY",
  "R2B1": "BLOCKED_INDEPENDENT_ADMISSION_REQUIRED",
  "R2B2": "BLOCKED_INDEPENDENT_ADMISSION_REQUIRED",
  "R2B3": "BLOCKED_INDEPENDENT_ADMISSION_REQUIRED",
  "R2B4": "BLOCKED_REAL_DEVICE_EVIDENCE"
}
WORKSTREAMS = [
  {
    "id": "PUBLIC_ABI",
    "source": "include/audio_pipeline/audio_pipeline.h",
    "stage": "R2B2",
    "reason": "no by-value 2.x struct extension",
    "status": "NOT_IMPLEMENTED"
  },
  {
    "id": "PRIVATE_ARRAY_CORE",
    "source": "tests/validation/frontend_evolution/fe09_array_sdk_draft_r2a.h",
    "stage": "R2B1",
    "reason": "one first-party FIR33 core, C1/C2/C4",
    "status": "NOT_IMPLEMENTED"
  },
  {
    "id": "MULTI_SRC_AND_RENDER",
    "source": "src/frontend/ap_resampler.h",
    "stage": "R2B1",
    "reason": "N physical histories plus independent mono render",
    "status": "NOT_IMPLEMENTED"
  },
  {
    "id": "PIPELINE_LIFECYCLE",
    "source": "src/core/ap_pipeline.c",
    "stage": "R2B1",
    "reason": "caller-owned per-config arena and epochs",
    "status": "NOT_IMPLEMENTED"
  },
  {
    "id": "LINUX_QUEUE",
    "source": "src/platform/linux/ap_runtime.c",
    "stage": "R2B2",
    "reason": "capture queues, API and thread ownership",
    "status": "NOT_IMPLEMENTED"
  },
  {
    "id": "FLIGHT_RECORDER",
    "source": "include/audio_pipeline/audio_diag.h",
    "stage": "R2B2",
    "reason": "versioned dump format/readers and stride",
    "status": "NOT_IMPLEMENTED"
  },
  {
    "id": "BF_AEC_TOPOLOGY",
    "source": "src/core/ap_pipeline.c",
    "stage": "R2B3",
    "reason": "BF->AEC versus AEC->BF paired evidence",
    "status": "NOT_IMPLEMENTED"
  },
  {
    "id": "DUT_RESOURCE",
    "source": "docs/API_CONTRACT.md",
    "stage": "R2B4",
    "reason": "SSC305 CPU p99 RAM thermal and E001 not qualified",
    "status": "NOT_IMPLEMENTED"
  }
]
BLOCKERS = [
  "N_MIC_PLUS_RENDER_SRC_NOT_QUALIFIED",
  "PUBLIC_V3_ABI_AND_CONSUMER_MIGRATION_UNBUILT",
  "LINUX_RUNTIME_FLIGHT_RECORDER_V3_NOT_QUALIFIED",
  "BF_AEC_ORDER_AND_REAL_SPEECH_GAIN_NOT_QUALIFIED",
  "REALMAN_ADC_SAMPLE_ZERO_CLOCK_AND_CALIBRATION_UNKNOWN",
  "FULL_C4_192KIB_SYSTEM_RAM_CPU_NOT_MEASURED",
  "SSC305_10MS_P99_THERMAL_POWER_HIL_E001_NOT_QUALIFIED"
]

DECISION = "FE09_R2B0_MAJOR_MIGRATION_PREFLIGHT_RESEARCH_ONLY_NO_PUBLIC_ABI"
FAIL = "FE09_R2B0_SOURCE_OR_MIGRATION_CONTRACT_NOT_ADMITTED"
SOURCE_CAP = 1024 * 1024
DOC_MARKERS = (
    "# FE09-R2B0",
    "## Scope and limits / 范围与边界",
    "## Current-source cutover matrix / 源代码迁移矩阵",
    "## ABI and memory ownership / ABI与内存归属",
    "## Timebase, render and recorder / 时钟、回声参考与录制",
    "## Independent gates and rollback / 独立门禁与回滚",
    "## Explicit nonclaims / 不得宣称",
    DECISION, "B_NEXT_MAJOR_SINGLE_PRIVATE_ARRAY_CORE",
    "192 KiB", "UNKNOWN", "SSC305",
)


class GateFailure(ValueError):
    """Explicit fail-closed contract rejection."""


def require(ok: bool, code: str) -> None:
    if not ok:
        raise GateFailure(code)


def pairs_unique(pairs: list[tuple[str, object]]) -> dict:
    result: dict = {}
    for k, v in pairs:
        require(k not in result, "DUPLICATE_JSON_KEY")
        result[k] = v
    return result


def reject_constant(_: str) -> None:
    raise GateFailure("NONFINITE_JSON")


def strict_json(raw: str) -> dict:
    obj = json.loads(raw, object_pairs_hook=pairs_unique,
                     parse_constant=reject_constant)
    require(type(obj) is dict, "JSON_OBJECT_REQUIRED")
    return obj


def git_blob(raw: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(raw)).encode("ascii") +
                        b"\0" + raw).hexdigest()


def read(root: Path, rel: str) -> str:
    require(rel in BLOBS or rel in {CONTRACT, ADR}, "UNKNOWN_SOURCE_PATH")
    p = root / rel
    require(p.is_file() and not p.is_symlink() and
            0 < p.stat().st_size <= SOURCE_CAP, "MISSING_OR_OVERSIZED_SOURCE")
    return p.read_text(encoding="utf-8")


def read_all(root: Path) -> dict[str, str]:
    return {p: read(root, p) for p in set(BLOBS) | {CONTRACT, ADR}}


def validate_policy(p: dict) -> None:
    keys = {"schema_version", "experiment_id", "preregistration", "parent_issue",
            "stage", "decision", "decision_status", "selected_architecture",
            "predecessors", "legacy_public_2x", "proposed_major", "claims",
            "phases", "workstreams", "blockers", "source_trace",
            "source_blobs_sha1"}
    require(set(p) == keys and type(p.get("schema_version")) is int and
            p["schema_version"] == 1 and
            p.get("experiment_id") == "FE09-R2B0-MAJOR-MIGRATION-PREFLIGHT-V1" and
            p.get("preregistration") ==
                "https://github.com/jiying2007/audio-pipeline/issues/733" and
            p.get("parent_issue") == 730 and
            p.get("stage") == "READ_ONLY_SOURCE_PREFLIGHT" and
            p.get("decision") == DECISION and
            p.get("decision_status") == "PROPOSED_NONSHIPPING_PREQUALIFICATION" and
            p.get("selected_architecture") == "B_NEXT_MAJOR_SINGLE_PRIVATE_ARRAY_CORE",
            "UNAUTHORIZED_STAGE_OR_DECISION")
    require(p.get("predecessors") == PREDECESSORS, "PREDECESSOR_MISMATCH")
    require(p.get("legacy_public_2x") == LEGACY, "LEGACY_2X_DRIFT")
    require(p.get("proposed_major") == PROPOSED, "FUTURE_MAJOR_PROMOTION")
    require(p.get("claims") == CLAIMS and
            all(value is False for value in p["claims"].values()),
            "UNQUALIFIED_PUBLIC_OR_DUT_CLAIM")
    require(p.get("phases") == PHASES and
            p.get("workstreams") == WORKSTREAMS and
            p.get("blockers") == BLOCKERS, "CUTOVER_SCOPE_DRIFT")
    require(p.get("source_trace") ==
            [{"id": n, "path": path} for n, path, _ in PROBES] and
            p.get("source_blobs_sha1") == BLOBS, "SOURCE_LINEAGE_DRIFT")


def validate(p: dict, src: dict[str, str], *, check_blobs: bool = True) -> None:
    validate_policy(p)
    for n, path, needle in PROBES:
        require(src[path].count(needle) == 1, "SOURCE_ANCHOR_DRIFT_" + n)
    public = src["include/audio_pipeline/audio_pipeline.h"]
    for tag in ("ap_config", "ap_metrics"):
        matched = re.search(r"typedef struct " + tag +
                            r"\s*\{(.*?)\}\s*" + tag + r"_t;",
                            public, flags=re.S)
        require(matched is not None and
                re.search(r"\bstruct_size\b|\bapi_version\b", matched.group(1))
                is None, "LEGACY_LAYOUT_PROMOTED_" + tag)
    require("fe09_array_sdk_draft_r2a" not in src["CMakeLists.txt"],
            "R2A_DRAFT_ACCIDENTALLY_PACKAGED")
    require(all(m in src[ADR] for m in DOC_MARKERS),
            "ADR_MISSING_SCOPE_OR_NONCLAIM")
    require("public_c4_enabled=true" not in src[ADR] and
            "release_3x_published=true" not in src[ADR] and
            "3.x SDK is released" not in src[ADR],
            "ADR_FALSE_PROMOTION")
    if check_blobs:
        for path, frozen in BLOBS.items():
            require(git_blob(src[path].encode("utf-8")) == frozen,
                    "SOURCE_BLOB_DRIFT_" + path)


def run_check(root: Path) -> dict:
    src = read_all(root)
    p = strict_json(src[CONTRACT])
    validate(p, src)
    return {
        "decision": DECISION, "source_probes_checked": len(PROBES),
        "source_files_checked": len(BLOBS),
        "preflight_main": PREDECESSORS["b0_base_main_sha"],
        "source_sha256": {k: hashlib.sha256(src[k].encode("utf-8")).hexdigest()
                          for k in sorted(BLOBS)},
        "contract_sha256": hashlib.sha256(src[CONTRACT].encode("utf-8")).hexdigest(),
        "adr_sha256": hashlib.sha256(src[ADR].encode("utf-8")).hexdigest(),
        "public_3x_sdk_installed": False,
        "ssc305_hil_qualified": False,
    }


def expect_fail(fn, code: str) -> None:
    try:
        fn()
    except GateFailure as exc:
        require(str(exc) == code, "WRONG_REJECTION_" + code)
    else:
        raise GateFailure("MISSING_REJECTION_" + code)


def self_test() -> None:
    src = read_all(ROOT)
    p = strict_json(src[CONTRACT])
    validate(p, src)
    for n, path, needle in PROBES:
        changed = dict(src)
        changed[path] = changed[path].replace(needle, "DELETED_PROBE", 1)
        expect_fail(lambda s=changed: validate(p, s, check_blobs=False),
                    "SOURCE_ANCHOR_DRIFT_" + n)
    for name in ("ap_config", "ap_metrics"):
        changed = dict(src)
        key = "include/audio_pipeline/audio_pipeline.h"
        changed[key] = changed[key].replace(
            "typedef struct " + name + " {",
            "typedef struct " + name + " {\n    uint32_t api_version;", 1)
        expect_fail(lambda s=changed: validate(p, s, check_blobs=False),
                    "LEGACY_LAYOUT_PROMOTED_" + name)
    changed = dict(src)
    changed["CMakeLists.txt"] += "\nfe09_array_sdk_draft_r2a.h\n"
    expect_fail(lambda: validate(p, changed, check_blobs=False),
                "R2A_DRAFT_ACCIDENTALLY_PACKAGED")
    changed = dict(src)
    changed["src/frontend/ap_resampler.c"] += "\n"
    expect_fail(lambda: validate(p, changed),
                "SOURCE_BLOB_DRIFT_src/frontend/ap_resampler.c")
    for k in CLAIMS:
        wrong = dict(p, claims={**CLAIMS, k: True})
        expect_fail(lambda q=wrong: validate_policy(q),
                    "UNQUALIFIED_PUBLIC_OR_DUT_CLAIM")
    for k, v, error in (
        ("source_trace", p["source_trace"][:-1], "SOURCE_LINEAGE_DRIFT"),
        ("source_blobs_sha1", {}, "SOURCE_LINEAGE_DRIFT"),
        ("phases", {**PHASES, "R2B1": "ACCEPTED"}, "CUTOVER_SCOPE_DRIFT"),
        ("predecessors", {**PREDECESSORS, "b0_base_release_run": 0},
         "PREDECESSOR_MISMATCH"),
        ("legacy_public_2x", {**LEGACY, "max_physical_microphones": 4},
         "LEGACY_2X_DRIFT"),
        ("proposed_major", {**PROPOSED, "full_C4_system_budget_qualified": True},
         "FUTURE_MAJOR_PROMOTION"),
    ):
        wrong = dict(p, **{k: v})
        expect_fail(lambda q=wrong: validate_policy(q), error)
    changed = dict(src)
    changed[ADR] = changed[ADR].replace(DOC_MARKERS[0], "INVALID", 1)
    expect_fail(lambda: validate(p, changed, check_blobs=False),
                "ADR_MISSING_SCOPE_OR_NONCLAIM")
    expect_fail(lambda: strict_json('{"a":1,"a":2}'), "DUPLICATE_JSON_KEY")
    expect_fail(lambda: strict_json('{"a":NaN}'), "NONFINITE_JSON")
    print("FE09_R2B0_PREFLIGHT_SELF_TEST_PASS probes=" + str(len(PROBES)))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    flags = ap.add_mutually_exclusive_group(required=True)
    flags.add_argument("--self-test", action="store_true")
    flags.add_argument("--check", action="store_true")
    args = ap.parse_args()
    try:
        if args.self_test:
            self_test()
        else:
            print(json.dumps(run_check(ROOT), sort_keys=True,
                             separators=(",", ":"), allow_nan=False))
    except (GateFailure, OSError, UnicodeError, ValueError, KeyError) as exc:
        print(FAIL + ": " + str(exc))
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
