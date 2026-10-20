#!/usr/bin/env python3
"""FE09-R2B2-S0: read-only Linux runtime/Flight Recorder cutover authority.

This is synthetic next-major design screening ONLY, not an implemented runtime,
APD3 reader, public 3.x ABI, real-array benefit, physical timebase or HIL proof.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
CONTRACT = HERE / "fe09_r2b2_runtime_recorder_contract_s0.json"
BASE = "e30c1e5e0619f02554077ed81dac312245aa4a31"
DECISION = "FE09_R2B2_S0_RUNTIME_RECORDER_PREFLIGHT_RESEARCH_ONLY_NO_PUBLIC_ABI"
FAILURE = "FE09_R2B2_S0_RUNTIME_DUMP_OR_ABI_DRIFT_NOT_ADMITTED"
SHA = re.compile(r"[0-9a-f]{40}")
MAX_FILE_BYTES = 256 * 1024

# Source bytes are immutable authority; these are literal anchors of actual
# existing shipping/runtime/reader code, NOT copies of any DSP implementation.
ANCHORS: dict[str, tuple[str, ...]] = {
    "src/platform/linux/ap_runtime.c": (
        "AP_RT_MAX_CAPTURE (AP_BUILD_IO_FRAME_MAX * AP_BUILD_MAX_MIC_CHANNELS)",
        "config->mic_channels > 2u",
        "typedef struct ap_dump_file_header",
        "typedef struct ap_dump_record_header",
        "header.format_version = AP_DUMP_FORMAT_VERSION;",
        "header.endian_tag = AP_DUMP_ENDIAN_TAG;",
        "ap_flight_recorder_export(",
    ),
    "src/core/ap_pipeline_internal.h": (
        "ap_resampler_state_t resampler;",
        "float mic1[AP_INTERNAL_FRAME_MAX];",
        "float reference[AP_INTERNAL_FRAME_MAX];",
    ),
    "src/frontend/ap_resampler.c": (
        "ap_resample_input_channel(", "ap_resampler_reset(",
    ),
    "src/frontend/ap_beamformer.c": (
        "mic_spacing_mm", "max_lag",
    ),
    "include/audio_pipeline/audio_runtime.h": (
        "#define AP_RUNTIME_API_VERSION 1u",
        "#define AP_RUNTIME_STATE_MAX_BYTES (64u * 1024u)",
        "AP_FRAME_CLOCK_RESET",
    ),
    "include/audio_pipeline/audio_diag.h": (
        "#define AP_DIAG_API_VERSION 1u",
        "#define AP_DUMP_MAGIC 0x32445041u",
        "#define AP_DUMP_FORMAT_VERSION 1u",
        "typedef struct ap_flight_recorder_config",
    ),
    "include/audio_pipeline/audio_pipeline.h": (
        "#define AP_PIPELINE_CONTROL_API_VERSION 2u",
        "typedef struct ap_config",
        "uint32_t mic_channels;",
    ),
    "tools/apdump.py": (
        'AP_DUMP_FORMAT_VERSION = 1',
        'HEADER = struct.Struct("<12I24s12s12s12s16s")',
        'RECORD_HEADER = struct.Struct("<QQQII")',
        "if channels not in (1, 2)",
        "if fmt != AP_DUMP_FORMAT_VERSION",
    ),
    "tools/apreplay.py": (
        '"--mic-channels"', "header.mic_channels",
    ),
    "tests/diagnostics/generate_fault_dump.c": (
        '"clock-reset"', '"render-gap"', '"capture-gap"',
    ),
    "tests/validation/frontend_evolution/array_native.h": (
        "#define FE_ARRAY_MAX_MICS 4u",
        "fe_array_state_bytes_for_mode",
        "fe_array_process(",
    ),
    "tests/validation/frontend_evolution/fe09_b1b0_src.c": (
        "fe_b1b0_process(", "fe_b1b0_notify_gap(", "ap_resample_input_channel(",
    ),
    "tests/validation/frontend_evolution/fe09_b1b1_single_bf.c": (
        "fe_b1b1_transpose_clamp(", "fe_b1b0_process(",
        "fe_array_process(", "fe_b1b1_notify_gap(",
    ),
}
SOURCE_PATHS = frozenset(ANCHORS)
VERSION_KEYS = frozenset({
    "magic", "format_version", "endian_tag", "allowed_mics",
    "header_struct", "record_header_struct",
    "recorder_api_version", "runtime_api_version",
})
FUTURE_KEYS = frozenset({
    "candidate_version", "physical_mics", "render_channels", "ingress_hz",
    "internal_hz", "frame_ms", "proposed_new_dump_version",
    "clock_source_authority", "source_epochs_separate", "caller_owned_arena",
})
NON_PROMOTION = frozenset({
    "public_sdk_3x_installed", "existing_2x_abi_changed",
    "shipping_src_changed", "full_c4_192kib_budget_qualified",
    "ssc305_hil_qualified", "measured_bf_gain_qualified",
    "real_adc_clock_qualified", "aec_qualified",
})
CONTRACT_KEYS = frozenset({
    "schema_version", "stage", "authority", "preregistration",
    "protected_source_baseline", "source_git_blobs", "legacy_dump",
    "future_private_contract", "admissions", "decision",
})


class GateError(ValueError):
    pass


def need(ok: bool, reason: str) -> None:
    if not ok:
        raise GateError(reason)


def unique_pairs(pairs: list[tuple[str, object]]) -> dict:
    obj: dict = {}
    for key, value in pairs:
        need(key not in obj, "DUPLICATE_JSON_KEY")
        obj[key] = value
    return obj


def file_bytes(path: Path) -> bytes:
    need(path.is_file() and not path.is_symlink() and
         0 < path.stat().st_size < MAX_FILE_BYTES,
         "MISSING_OR_OVERSIZED_SOURCE")
    return path.read_bytes()


def blob_sha(raw: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()


def read_contract() -> tuple[dict, str]:
    data = file_bytes(CONTRACT)
    c = json.loads(data.decode("utf-8"), object_pairs_hook=unique_pairs)
    need(type(c) is dict, "CONTRACT_MUST_BE_OBJECT")
    return c, hashlib.sha256(data).hexdigest()


def check_contract(c: dict) -> None:
    need(type(c) is dict and set(c) == CONTRACT_KEYS,
         "CONTRACT_SCHEMA_DRIFT")
    need(type(c["schema_version"]) is int and c["schema_version"] == 1 and
         c["stage"] == "FE09_R2B2_S0_RUNTIME_RECORDER_PREFLIGHT" and
         c["authority"] == "READ_ONLY_SOURCE_MAP_NONINSTALLED" and
         c["preregistration"] ==
         "https://github.com/jiying2007/audio-pipeline/issues/749" and
         c["protected_source_baseline"] == BASE and
         c["decision"] == DECISION, "STAGE_OR_SCIENCE_AUTHORITY_PROMOTION")
    sources = c["source_git_blobs"]
    need(type(sources) is dict and set(sources) == SOURCE_PATHS and
         all(type(v) is str and SHA.fullmatch(v) is not None
             for v in sources.values()), "SOURCE_SET_OR_SHA_DRIFT")
    legacy = c["legacy_dump"]
    need(type(legacy) is dict and set(legacy) == VERSION_KEYS and
         legacy["magic"] == "0x32445041" and
         type(legacy["format_version"]) is int and legacy["format_version"] == 1 and
         legacy["endian_tag"] == "0x01020304" and
         legacy["allowed_mics"] == [1, 2] and
         legacy["header_struct"] == "<12I24s12s12s12s16s" and
         legacy["record_header_struct"] == "<QQQII" and
         type(legacy["recorder_api_version"]) is int and
         legacy["recorder_api_version"] == 1 and
         type(legacy["runtime_api_version"]) is int and
         legacy["runtime_api_version"] == 1, "LEGACY_V1_BINARY_FORMAT_DRIFT")
    future = c["future_private_contract"]
    need(type(future) is dict and set(future) == FUTURE_KEYS and
         future["candidate_version"] ==
         "PRIVATE_NEXT_MAJOR_EXPERIMENTAL_NOT_INSTALLED" and
         future["physical_mics"] == [1, 2, 4] and
         future["render_channels"] == [0, 1] and
         future["ingress_hz"] == [16000, 32000, 48000] and
         type(future["internal_hz"]) is int and future["internal_hz"] == 16000 and
         type(future["frame_ms"]) is int and future["frame_ms"] == 10 and
         type(future["proposed_new_dump_version"]) is int and
         future["proposed_new_dump_version"] == 2 and
         future["clock_source_authority"] == "UNKNOWN" and
         future["source_epochs_separate"] is True and
         future["caller_owned_arena"] is True,
         "FUTURE_CONTRACT_ACCIDENTALLY_PROMOTED")
    admission = c["admissions"]
    need(type(admission) is dict and set(admission) == NON_PROMOTION and
         all(value is False for value in admission.values()),
         "SHIPPING_REAL_ACOUSTIC_OR_DEVICE_PROMOTION")


def check_sources(c: dict) -> dict:
    details = {}
    for path in sorted(SOURCE_PATHS):
        raw = file_bytes(ROOT / path)
        need(blob_sha(raw) == c["source_git_blobs"][path],
             "SOURCE_GIT_BLOB_DRIFT_" + path)
        content = raw.decode("utf-8")
        for token in ANCHORS[path]:
            need(token in content, "SOURCE_CONTRACT_ANCHOR_MISSING_" + path)
        details[path] = hashlib.sha256(raw).hexdigest()
    return details


def valid_future_sample(d: dict) -> None:
    required = {
        "physical_mics", "render_channels", "input_rate_hz",
        "internal_rate_hz", "frame_ms", "capture_slots", "active_mask",
        "source_frame_samples", "internal_frame_samples", "render_capture_slot",
        "capture_clock_authority", "dump_format_version",
        "new_dump_magic_assigned", "source_epoch_separate",
        "render_gap_resets_array", "capture_gap_resets_array",
        "transaction_on_failure", "public_abi_version",
        "public_sdk_installed", "legacy_reader_accepts_new_dump",
        "legacy_writer_changed", "timestamp_is_measured",
        "device_resources_qualified", "aec_qualified",
    }
    need(type(d) is dict and set(d) == required, "FUTURE_CANDIDATE_SHAPE_DRIFT")
    n, ref, rate = d["physical_mics"], d["render_channels"], d["input_rate_hz"]
    need(type(n) is int and n in (1, 2, 4) and
         type(ref) is int and ref in (0, 1) and
         type(rate) is int and rate in (16000, 32000, 48000) and
         type(d["internal_rate_hz"]) is int and d["internal_rate_hz"] == 16000 and
         type(d["frame_ms"]) is int and d["frame_ms"] == 10 and
         type(d["source_frame_samples"]) is int and
         d["source_frame_samples"] == rate // 100 and
         type(d["internal_frame_samples"]) is int and
         d["internal_frame_samples"] == 160, "UNSUPPORTED_CHANNEL_RATE_OR_FRAME")
    slots = d["capture_slots"]
    need(type(slots) is list and len(slots) == n and
         all(type(x) is int for x in slots) and sorted(slots) == list(range(n)) and
         d["render_capture_slot"] is None, "CAPTURE_SLOT_OR_RENDER_ALIAS")
    mask = d["active_mask"]
    need(type(mask) is int and
         0 < mask < (1 << n) and mask & ~((1 << n) - 1) == 0
         or type(mask) is int and mask == (1 << n) - 1,
         "INVALID_PHYSICAL_MASK")
    need(d["capture_clock_authority"] == "UNKNOWN" and
         type(d["dump_format_version"]) is int and
         d["dump_format_version"] == 2 and
         d["new_dump_magic_assigned"] is False and
         d["source_epoch_separate"] is True and
         d["render_gap_resets_array"] is False and
         d["capture_gap_resets_array"] is True and
         d["transaction_on_failure"] == "ATOMIC_NO_PARTIAL_COMMIT" and
         d["public_abi_version"] == "UNINSTALLED_NEXT_MAJOR" and
         d["public_sdk_installed"] is False and
         d["legacy_reader_accepts_new_dump"] is False and
         d["legacy_writer_changed"] is False and
         d["timestamp_is_measured"] is False and
         d["device_resources_qualified"] is False and
         d["aec_qualified"] is False,
         "PRIVATE_RUNTIME_OR_DUMP_SOURCE_PROMOTION")


def synthetic_candidate(n: int, ref: int, rate: int) -> dict:
    return {
        "physical_mics": n, "render_channels": ref,
        "input_rate_hz": rate, "internal_rate_hz": 16000,
        "frame_ms": 10, "capture_slots": list(reversed(range(n))),
        "active_mask": (1 << n) - 1, "source_frame_samples": rate // 100,
        "internal_frame_samples": 160, "render_capture_slot": None,
        "capture_clock_authority": "UNKNOWN", "dump_format_version": 2,
        "new_dump_magic_assigned": False, "source_epoch_separate": True,
        "render_gap_resets_array": False, "capture_gap_resets_array": True,
        "transaction_on_failure": "ATOMIC_NO_PARTIAL_COMMIT",
        "public_abi_version": "UNINSTALLED_NEXT_MAJOR",
        "public_sdk_installed": False, "legacy_reader_accepts_new_dump": False,
        "legacy_writer_changed": False, "timestamp_is_measured": False,
        "device_resources_qualified": False, "aec_qualified": False,
    }


def negative_controls() -> int:
    cases = []
    exemplar = synthetic_candidate(4, 1, 48000)
    changes = [
        ("C3_UNSUPPORTED", "physical_mics", 3),
        ("ZERO_MICS", "physical_mics", 0),
        ("FIVE_MICS", "physical_mics", 5),
        ("BOOLEAN_MIC_COUNT", "physical_mics", True),
        ("TWO_RENDER", "render_channels", 2),
        ("NEGATIVE_RENDER", "render_channels", -1),
        ("RATE_8K_NOT_B1B", "input_rate_hz", 8000),
        ("RATE_24K_NOT_B1B", "input_rate_hz", 24000),
        ("RATE_44K", "input_rate_hz", 44100),
        ("RATE_ZERO", "input_rate_hz", 0),
        ("INTERNAL_48K", "internal_rate_hz", 48000),
        ("FRAME_20MS", "frame_ms", 20),
        ("FRAMES_WRONG", "source_frame_samples", 160),
        ("INTERNAL_FRAME_WRONG", "internal_frame_samples", 480),
        ("MASK_ZERO", "active_mask", 0),
        ("MASK_FOREIGN", "active_mask", 31),
        ("MASK_NEGATIVE", "active_mask", -1),
        ("MASK_BOOLEAN", "active_mask", True),
        ("CAPTURE_DUP", "capture_slots", [0, 0, 2, 3]),
        ("CAPTURE_SHORT", "capture_slots", [0, 1, 2]),
        ("CAPTURE_LARGE", "capture_slots", [0, 1, 2, 4]),
        ("CAPTURE_NEG", "capture_slots", [0, 1, 2, -1]),
        ("RENDER_MIC5", "render_capture_slot", 4),
        ("REAL_CLOCK_FAKE", "capture_clock_authority", "MEASURED"),
        ("LEGACY_V1_C4", "dump_format_version", 1),
        ("UNKNOWN_VERSION", "dump_format_version", 99),
        ("MAGIC_FAKE", "new_dump_magic_assigned", True),
        ("EPOCHS_SHARED", "source_epoch_separate", False),
        ("RENDER_RESETS_BF", "render_gap_resets_array", True),
        ("CAPTURE_NO_BF_RESET", "capture_gap_resets_array", False),
        ("PARTIAL_COMMIT", "transaction_on_failure", "ALLOW_PARTIAL"),
        ("PUBLISH_ABI", "public_abi_version", 3),
        ("SDK_INSTALLED", "public_sdk_installed", True),
        ("OLD_READER_SILENT_C4", "legacy_reader_accepts_new_dump", True),
        ("OLD_WRITER_RENAMED", "legacy_writer_changed", True),
        ("INVENT_TIMESTAMP", "timestamp_is_measured", True),
        ("FAKE_HIL", "device_resources_qualified", True),
        ("AEC_PROMOTION", "aec_qualified", True),
    ]
    for name, key, value in changes:
        bad = copy.deepcopy(exemplar)
        bad[key] = value
        cases.append((name, bad))
    bad_missing = copy.deepcopy(exemplar)
    bad_missing.pop("capture_slots")
    cases.append(("MISSING_FIELD", bad_missing))
    bad_extra = copy.deepcopy(exemplar)
    bad_extra["shipping_abi_3x"] = True
    cases.append(("ADDITIONAL_FIELD", bad_extra))
    for name, bad in cases:
        try:
            valid_future_sample(bad)
        except GateError:
            continue
        raise GateError("FALSE_NEXT_MAJOR_ADMISSION_" + name)
    return len(cases)


def self_test() -> None:
    contract, _ = read_contract()
    check_contract(contract)
    check_sources(contract)
    for rate in (16000, 32000, 48000):
        for n, ref in ((1, 0), (2, 1), (4, 1)):
            valid_future_sample(synthetic_candidate(n, ref, rate))
    count = negative_controls()
    need(count >= 35, "INSUFFICIENT_INVALID_RUNTIME_CONTROLS")

    mutations = [
        ("schema_version", 2), ("stage", "PRODUCT_RELEASE"),
        ("authority", "SHIPPING_3X"), ("preregistration", "unregistered"),
        ("protected_source_baseline", "f" * 40),
        ("decision", "RELEASE_ALLOWED"),
    ]
    for key, value in mutations:
        wrong = copy.deepcopy(contract)
        wrong[key] = value
        try:
            check_contract(wrong)
        except GateError:
            pass
        else:
            raise GateError("FALSE_CONTRACT_PROMOTION_" + key)
    for group, key, value in (
        ("legacy_dump", "allowed_mics", [1, 2, 4]),
        ("legacy_dump", "format_version", 2),
        ("legacy_dump", "magic", "APD3"),
        ("future_private_contract", "physical_mics", [1, 2, 3, 4]),
        ("future_private_contract", "clock_source_authority", "KNOWN"),
        ("admissions", "public_sdk_3x_installed", True),
        ("admissions", "ssc305_hil_qualified", True),
    ):
        wrong = copy.deepcopy(contract)
        wrong[group][key] = value
        try:
            check_contract(wrong)
        except GateError:
            pass
        else:
            raise GateError("FALSE_NESTED_CONTRACT_PROMOTION_" + key)

    for path in SOURCE_PATHS:
        wrong = copy.deepcopy(contract)
        wrong["source_git_blobs"][path] = "f" * 40
        try:
            check_sources(wrong)
        except GateError:
            pass
        else:
            raise GateError("SOURCE_HASH_MUTATION_ACCEPTED_" + path)
    try:
        json.loads('{"schema_version":1,"schema_version":2}',
                   object_pairs_hook=unique_pairs)
    except GateError:
        pass
    else:
        raise GateError("DUPLICATE_JSON_ACCEPTED")
    print("FE09_R2B2_S0_PREFLIGHT_SELF_TEST_PASS " +
          f"source_blobs={len(SOURCE_PATHS)} synthetic_profiles=9 " +
          f"candidate_negatives={count} source_negatives={len(SOURCE_PATHS)} " +
          "contract_negatives=14")


def check() -> None:
    contract, contract_sha = read_contract()
    check_contract(contract)
    hashes = check_sources(contract)
    negatives = negative_controls()
    receipt = {
        "schema_version": 1, "decision": DECISION,
        "source_authority": "first-party-existing-read-only",
        "protected_predecessor": contract["protected_source_baseline"],
        "preregistration": contract["preregistration"],
        "source_files_checked": len(hashes),
        "source_sha256": hashes,
        "contract_sha256": contract_sha,
        "candidate_negatives": negatives,
        "future_3x_runtime_built": False,
        "legacy_2x_abi_changed": False,
        "future_apd_v2_parser_built": False,
        "public_3x_sdk_installed": False,
        "real_adc_clock_qualified": False,
        "ssc305_hil_qualified": False,
        "complete_c4_budget_qualified": False,
    }
    print(json.dumps(receipt, sort_keys=True, separators=(",", ":"),
                     allow_nan=False))


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    group = p.add_mutually_exclusive_group(required=True)
    group.add_argument("--self-test", action="store_true")
    group.add_argument("--check", action="store_true")
    args = p.parse_args()
    try:
        if args.self_test:
            self_test()
        else:
            check()
    except (GateError, OSError, UnicodeError, json.JSONDecodeError,
            KeyError, TypeError, ValueError) as exc:
        print(FAILURE + ": " + str(exc)[:160], file=sys.stderr)
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
