#!/usr/bin/env python3
"""D8 persisted targeted negatives and explicitly scoped engineering controls.

Targeted fixtures launch no DSP, compiler, subprocess, temporary directory,
hard link, historical-global patch, or full result/source-tree copy. Initial
qualification uses normal driver readback, including its supervised read-only
source-identity commands. Every fixture is retained below result/negatives
through the production bounded writer.

The driver supplies negative_material(category, phase):
  raw: exact bytes of a verified actual slice (or explicitly scoped template)
  origin: source path and optional JSON pointer, not an invented measured source
  scope: one of SCOPES below
  guard_name: qualified normal production guard name
  guard: read-only callable taking the persisted fixture Path
  mutation: JSON path/index/frame metadata, never a function or mutant bytes

The bound guard must be the SAME normal readback predicate with independently
loaded context. It must not merely compare against the pristine fixture and
must not translate I/O, parse, timeout, or unrelated errors into the expected
reason. Its source binding is checked in independent implementation review.
Each guard must first accept its persisted pristine slice. A valid NO_ADVANCE
is not a rejection: only the exact frozen ValueError identifies a corruption.

Inventory negatives are actual inventory-slice mutations, not claims that a
cloned filesystem tree was traversed. Missing-finalization uses a current-
inventory-backed pre-finalization template, never a claim of completed work.
Synthetic threshold/projection controls and actual binary evidence are counted
separately. No actual adverse-window result is invented if none exists.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
from pathlib import Path
import struct
import time

import dualmic_broadside_output_d8 as d8
import dualmic_broadside_output_d8_build as b

FIXTURE_BYTES = 2 * 1024 * 1024
FIXTURE_TOTAL_BYTES = 32 * 1024 * 1024
SCOPES = {
    "actual_binary", "actual_report", "actual_source", "actual_inventory",
    "actual_budget_snapshot", "synthetic_engineering", "pre_finalization_template",
}
_written = 0
_fixture_files = {}

REASONS = {
    "raw_left": "D8_RAW_LEFT",
    "raw_right": "D8_RAW_RIGHT",
    "hpf_left": "D8_HPF_LEFT",
    "hpf_right": "D8_HPF_RIGHT",
    "bf_output": "D8_BF_OUTPUT",
    "hpf_state_before": "D8_HPF_STATE_BEFORE",
    "hpf_state_after": "D8_HPF_STATE_AFTER",
    "hpf_channel_order": "D8_HPF_CHANNEL_ORDER",
    "bf_state_before": "D8_BF_STATE_BEFORE",
    "bf_state_after": "D8_BF_STATE_AFTER",
    "bf_history": "D8_BF_HISTORY",
    "bf_lag_scores": "D8_BF_LAG_SCORES",
    "bf_lag": "D8_BF_LAG",
    "effective_lag": "D8_EFFECTIVE_LAG",
    "score_updates": "D8_SCORE_UPDATES",
    "fallback_route": "D8_FALLBACK_ROUTE",
    "track_direction": "D8_TRACK_DIRECTION",
    "trace_geometry": "D8_TRACE_GEOMETRY",
    "reset_coordinate": "D8_RESET_COORDINATE",
    "spurious_path_reset": "D8_SPURIOUS_PATH_RESET",
    "old_PCM": "D8_OLD_PCM",
    "old_metrics_JSONL": "D8_OLD_METRICS_JSONL",
    "old_D1_lane": "D8_OLD_D1_LANE",
    "old_control": "D8_OLD_CONTROL",
    "wrong_window": "D8_WRONG_WINDOW",
    "missing_case": "D8_MISSING_CASE",
    "null_to_zero": "D8_NULL_TO_ZERO",
    "near_schedule": "D8_NEAR_SCHEDULE",
    "association_count": "D8_ASSOCIATION_COUNT",
    "source_tree": "D8_SOURCE_TREE",
    "report_source": "D8_REPORT_SOURCE",
    "source_resealed": "D8_SOURCE_RESEALED",
    "transform_body_change": "D8_TRANSFORM_BODY",
    "observer_entry_change": "D8_OBSERVER_ENTRY",
    "header_resealed": "D8_HEADER_RESEALED",
    "compiler_identity": "D8_COMPILER_IDENTITY",
    "argv": "D8_ARGV",
    "execution_argv": "D8_EXECUTION_ARGV",
    "source_extra_file": "D8_SOURCE_CLOSURE",
    "source_extra_dir": "D8_SOURCE_CLOSURE",
    "extra_file": "D8_OUTPUT_CLOSURE",
    "extra_dir": "D8_OUTPUT_CLOSURE",
    "output_symlink": "D8_OUTPUT_SYMLINK",
    "failed_build_phase": "D8_FAILED_PHASE:baseline-build",
    "failed_run_phase": "D8_FAILED_PHASE:run",
    "failed_analysis_phase": "D8_FAILED_PHASE:analysis",
    "failed_verify_phase": "D8_FAILED_PHASE:verify",
    "failed_command": "D8_FAILED_COMMAND",
    "saved_admission": "D8_SAVED_ADMISSION",
    "input_binding": "D8_INPUT_BINDING",
    "readback_receipt": "D8_READBACK_RECEIPT",
    "second_mathematical_change": "D8_TRANSFORM_BODY",
    "tracking_off": "D8_TRACKING_OFF",
    "fallback_weight_or_gain_change": "D8_TRANSFORM_BODY",
    "history_or_state_change": "D8_TRANSFORM_BODY",
    "forced_baseline_downstream": "D8_FORCED_BASELINE_DOWNSTREAM",
    "wrong_output_offset": "D8_WRONG_OUTPUT_OFFSET",
    "lag_search": "D8_LAG_SEARCH",
    "omitted_bad_window": "D8_OMITTED_SCORED_WINDOW",
    "omitted_null_window": "D8_OMITTED_NULL_WINDOW",
    "silent_false_improvement": "D8_SILENT_FALSE_IMPROVEMENT",
    "threshold_boundary": "D8_THRESHOLD_BOUNDARY",
    "projection_boundary": "D8_PROJECTION_BOUNDARY",
    "forged_dedup": "D8_FORGED_DEDUP",
    "missing_actual_candidate_state": "D8_MISSING_ACTUAL_CANDIDATE_STATE",
    "missing_AGC_state": "D8_MISSING_AGC_STATE",
    "AGC_output_or_clamp_forged": "D8_AGC_OUTPUT_OR_CLAMP_FORGED",
    "near_silent_mutation": "D8_NEAR_SILENT_MUTATION",
    "recovery_None_to_zero": "D8_RECOVERY_NONE_TO_ZERO",
    "recovery_curve_change": "D8_RECOVERY_CURVE_CHANGE",
    "metric_category_overflow": "D8_METRIC_CATEGORY_OVERFLOW",
    "control_header_overflow": "D8_CONTROL_HEADER_OVERFLOW",
    "source_build_category_overflow": "D8_SOURCE_BUILD_CATEGORY_OVERFLOW",
    "report_finalization_overflow": "D8_REPORT_FINALIZATION_OVERFLOW",
    "scratch_overflow": "D8_SCRATCH_OVERFLOW",
    "missing_finalization": "D8_MISSING_FINALIZATION",
}

def encode(value):
    return (json.dumps(value, sort_keys=True, ensure_ascii=True,
                       separators=(",", ":"), allow_nan=False) + "\n").encode("ascii")

def _store(path, raw):
    global _written
    relative = path.relative_to(b.OUTPUT).as_posix()
    b.need(relative.startswith("negatives/") and relative not in _fixture_files,
           "D8_TEST_FIXTURE_PATH")
    b.need(isinstance(raw, bytes) and len(raw) <= FIXTURE_BYTES, "D8_TEST_FIXTURE_BYTES")
    b.need(_written + len(raw) <= FIXTURE_TOTAL_BYTES, "D8_TEST_FIXTURE_TOTAL")
    _written += len(raw)  # Count an attempted write even if its prefix later fails.
    b.bounded_write(path, raw)
    identity = b.desc(path)
    _fixture_files[relative] = identity
    return identity

def _json(raw):
    def reject_constant(value):
        raise ValueError("D8_TEST_NONFINITE_JSON:" + value)
    return json.loads(raw.decode("utf-8"), parse_constant=reject_constant)

def _at(value, path):
    b.need(isinstance(path, list), "D8_TEST_MUTATION_PATH")
    for part in path:
        b.need(isinstance(part, (str, int)) and not isinstance(part, bool),
               "D8_TEST_MUTATION_PATH")
        value = value[part]
    return value

def _set(value, path, replacement):
    b.need(isinstance(path, list) and len(path) > 0, "D8_TEST_MUTATION_PATH")
    parent = _at(value, path[:-1])
    parent[path[-1]] = replacement

def _changed_byte(raw):
    b.need(len(raw) > 0, "D8_TEST_EMPTY_PRISTINE")
    changed = bytearray(raw)
    changed[0] ^= 1
    return bytes(changed)

def _word(raw, offset, value, fmt="<f"):
    b.need(type(offset) is int and 0 <= offset <= len(raw) - struct.calcsize(fmt),
           "D8_TEST_WORD_OFFSET")
    result = bytearray(raw)
    struct.pack_into(fmt, result, offset, value)
    return bytes(result)

def _different_float(raw, offset):
    value = struct.unpack_from("<f", raw, offset)[0]
    b.need(math.isfinite(value), "D8_TEST_PRISTINE_NONFINITE")
    return -0.125 if value == 0.125 else 0.125

def _replace_once(raw, before, after):
    b.need(raw.count(before) == 1 and before != after, "D8_TEST_SOURCE_SITE")
    return raw.replace(before, after, 1)

def adjacent(value, upward):
    """Adjacent IEEE binary64, including +/-zero; supports Python 3.8."""
    b.need(type(value) in (int, float) and math.isfinite(value), "D8_TEST_ADJACENT")
    value = float(value)
    if value == 0.0:
        return struct.unpack(">d", struct.pack(">Q", 1 if upward else (1 << 63) | 1))[0]
    bits = struct.unpack(">Q", struct.pack(">d", value))[0]
    bits += 1 if (value > 0) == bool(upward) else -1
    return struct.unpack(">d", struct.pack(">Q", bits))[0]

SOURCE_MUTATIONS = {
    "source_resealed": (
        b"const float y = in - px + s->r * py;",
        b"const float y = in - px;"),
    "transform_body_change": (
        b"const float y = in - px + s->r * py;",
        b"const float y = in - px;"),
    "observer_entry_change": (
        b"int ap_d8_d1_main(", b"int ap_d8_bad_main("),
    "header_resealed": (
        b"AP_BUILD_MAX_MIC_CHANNELS 2", b"AP_BUILD_MAX_MIC_CHANNELS 1"),
    "second_mathematical_change": (
        b"const int lag = s->fallback_active ? s->fallback_lag : s->lag;",
        b"const int lag = 0;"),
    "fallback_weight_or_gain_change": (
        b"#define AP_BF_FALLBACK_STRONG_WEIGHT 0.75f",
        b"#define AP_BF_FALLBACK_STRONG_WEIGHT 0.50f"),
    "history_or_state_change": (
        b"memcpy(s->history, next_history, sizeof(next_history));",
        b"memset(s->history, 0, sizeof(s->history));"),
}

TRACE_WORDS = {
    "hpf_state_before": (16 + 4, "<f", None),
    "hpf_channel_order": (64 + 4, "<f", None),
    "bf_state_before": (112, "<f", None),
    "bf_state_after": (292 + 176, "<I", 99),
    "bf_history": (292, "<f", None),
    "bf_lag_scores": (292 + 64, "<f", None),
    "bf_lag": (292 + 136, "<i", 4),
    "score_updates": (292 + 152, "<I", 99),
    "fallback_route": (292 + 156, "<I", 2),
    "track_direction": (4, "<i", 2),
    "tracking_off": (4, "<i", 0),
}

BUDGET_CATEGORIES = {
    "metric_category_overflow": "candidate_metrics_including_newlines",
    "source_build_category_overflow": "all_source_archive_derived_build_provenance",
    "report_finalization_overflow": "all_reports_receipts_logs_negatives_seals_completion",
    "scratch_overflow": "all_current_case_transient_and_failure_prefix",
}

def mutate(category, raw, meta):
    """All corruptions are authored here, not supplied by the material adapter."""
    b.need(isinstance(meta, dict), "D8_TEST_MUTATION_METADATA")
    if category in SOURCE_MUTATIONS:
        return _replace_once(raw, *SOURCE_MUTATIONS[category])
    if category in TRACE_WORDS:
        offset, fmt, value = TRACE_WORDS[category]
        if value is None:
            value = _different_float(raw, offset)
        return _word(raw, offset, value, fmt)
    if category == "hpf_state_after":
        value = _different_float(raw, 40 + 4)
        return _word(_word(raw, 40 + 4, value), 64 + 4, value)
    if category in ("raw_left", "raw_right", "bf_output", "old_PCM",
                    "old_metrics_JSONL", "old_D1_lane", "old_control", "near_silent_mutation"):
        return _changed_byte(raw)
    if category in ("hpf_left", "hpf_right"):
        return _word(raw, 0, _different_float(raw, 0))
    if category == "trace_geometry":
        b.need(len(raw) >= 472, "D8_TEST_TRACE_PRISTINE")
        return raw[:-1]
    if category in ("missing_actual_candidate_state", "missing_AGC_state"):
        b.need(len(raw) > 0, "D8_TEST_EMPTY_PRISTINE")
        return b""
    if category == "spurious_path_reset":
        b.need(meta.get("frame", 300) == 300, "D8_TEST_RESET_COORDINATE")
        # Initial bytes are actual stream-start bytes in this very trace.
        # Copy only HPF0-before and BF-before, not fabricated state fields.
        offset = 300 * 472
        b.need(len(raw) >= offset + 472, "D8_TEST_TRACE_PRISTINE")
        changed = bytearray(raw)
        changed[offset + 16:offset + 40] = raw[16:40]
        changed[offset + 112:offset + 292] = raw[112:292]
        return bytes(changed)
    if category == "silent_false_improvement":
        b.need(len(raw) > 0 and len(raw) % 2 == 0 and any(raw), "D8_TEST_SILENT_APPLICABILITY")
        return bytes(len(raw))
    if category == "control_header_overflow":
        frames = meta.get("frames")
        b.need(type(frames) is int and 529 <= frames <= 629, "D8_TEST_CASE_FRAMES")
        split = raw.find(b"\n")
        b.need(split == 454 and len(raw) <= frames * 1024 and
               all(len(line) <= 1024 for line in raw[split + 1:].splitlines(keepends=True)),
               "D8_TEST_CONTROL_PRISTINE")
        # Only the header changes; all data rows remain exactly the original.
        extra = frames * 1024 + 1 - len(raw)
        return raw[:split] + b"x" * extra + raw[split:]

    value = _json(raw)
    path = meta.get("path")
    current = _at(value, path)
    if category in ("source_tree", "report_source", "compiler_identity",
                    "saved_admission", "input_binding", "forged_dedup"):
        b.need(isinstance(current, str) and len(current) in (40, 64), "D8_TEST_HASH_FIELD")
        replacement = ("f" if set(current) == {"0"} else "0") * len(current)
    elif category in ("effective_lag", "reset_coordinate", "wrong_window",
                      "association_count", "AGC_output_or_clamp_forged"):
        b.need(type(current) is int, "D8_TEST_INTEGER_FIELD")
        replacement = current + 1
    elif category == "recovery_curve_change":
        b.need(type(current) in (int, float) and math.isfinite(current), "D8_TEST_CURVE_FIELD")
        replacement = current + 0.125
    elif category in ("null_to_zero", "recovery_None_to_zero"):
        b.need(current is None, "D8_TEST_NULL_APPLICABILITY")
        replacement = 0
    elif category == "near_schedule":
        b.need(current in ("scheduled_present", "scheduled_absent", "unknown"),
               "D8_TEST_NEAR_SCHEDULE")
        replacement = "scheduled_absent" if current == "scheduled_present" else "scheduled_present"
    elif category in ("failed_build_phase", "failed_run_phase", "failed_analysis_phase",
                      "failed_verify_phase", "failed_command", "readback_receipt"):
        b.need(current == "PASS", "D8_TEST_PRISTINE_STATUS")
        replacement = "FAIL"
    elif category in ("argv", "execution_argv"):
        b.need(isinstance(current, list) and all(isinstance(x, str) for x in current),
               "D8_TEST_ARGV_FIELD")
        replacement = current + ["-ffast-math" if category == "argv" else "--d8-unexpected-option"]
    elif category in ("missing_case", "omitted_bad_window", "omitted_null_window"):
        b.need(isinstance(current, list) and len(current) > 0, "D8_TEST_ROWS_FIELD")
        index = meta.get("index", len(current) - 1)
        b.need(type(index) is int and 0 <= index < len(current), "D8_TEST_ROW_INDEX")
        if category != "missing_case":
            selection = meta.get("selection")
            b.need(selection in ("adverse", "null", "geometry"), "D8_TEST_ROW_SELECTION")
            if selection != "geometry":
                selected = _at(current[index], meta.get("condition_path"))
                b.need(selected is None if selection == "null" else
                       type(selected) in (int, float) and math.isfinite(selected) and selected < 0,
                       "D8_TEST_ROW_APPLICABILITY")
            if category == "omitted_null_window":
                b.need(selection == "null", "D8_TEST_NULL_APPLICABILITY")
        replacement = current[:index] + current[index + 1:]
    elif category in ("source_extra_file", "extra_file"):
        b.need(isinstance(current, dict) and "d8-undeclared.bin" not in current,
               "D8_TEST_INVENTORY_FIELD")
        replacement = copy.deepcopy(current)
        replacement["d8-undeclared.bin"] = {"bytes": 1, "sha256": hashlib.sha256(b"x").hexdigest()}
    elif category in ("source_extra_dir", "extra_dir"):
        b.need(isinstance(current, list) and "d8-undeclared" not in current,
               "D8_TEST_INVENTORY_FIELD")
        replacement = current + ["d8-undeclared"]
    elif category == "output_symlink":
        b.need(isinstance(current, dict), "D8_TEST_INVENTORY_FIELD")
        replacement = dict(current, type="symlink", target="report.json")
    elif category == "forced_baseline_downstream":
        b.need(isinstance(current, str) and "candidate" in current, "D8_TEST_CANDIDATE_POINTER")
        replacement = current.replace("candidate", "baseline", 1)
    elif category == "wrong_output_offset":
        b.need(current == 160, "D8_TEST_OUTPUT_OFFSET")
        replacement = 159
    elif category == "lag_search":
        b.need(current is False, "D8_TEST_LAG_SEARCH")
        replacement = True
    elif category == "threshold_boundary":
        b.need(type(current) in (int, float) and current in (0.0, 1.0), "D8_TEST_THRESHOLD")
        replacement = adjacent(current, False)
    elif category == "projection_boundary":
        b.need(current == -120.0, "D8_TEST_PROJECTION_THRESHOLD")
        replacement = adjacent(-120.0, False)
    elif category in BUDGET_CATEGORIES:
        b.need(type(current) is int and current >= 0, "D8_TEST_BUDGET_FIELD")
        replacement = b.contract()["budgets"]["categories"][BUDGET_CATEGORIES[category]] + 1
    elif category == "missing_finalization":
        parent = _at(value, path[:-1])
        b.need(isinstance(parent, dict) and path[-1] in parent, "D8_TEST_FINALIZATION_FIELD")
        del parent[path[-1]]
        return encode(value)
    else:
        raise ValueError("D8_TEST_UNIMPLEMENTED_MUTATION:" + category)
    _set(value, path, replacement)
    return encode(value)

def _expect_reason(category, action, phase, reason=None):
    phase.remaining()
    started = time.monotonic()
    expected = reason if reason is not None else REASONS[category]
    try:
        action()
    except ValueError as error:
        # OSError/TimeoutError and all other exception classes propagate.
        b.need(str(error) == expected,
               "D8_NEGATIVE_WRONG_REASON:" + category + ":" + str(error))
    else:
        raise ValueError("D8_NEGATIVE_ACCEPTED:" + category)
    phase.remaining()
    return {"expected_reason": expected, "observed_reason": expected,
            "elapsed_seconds": time.monotonic() - started}

def _exercise(category, material, phase):
    required = {"raw", "origin", "scope", "guard_name", "guard", "mutation"}
    b.need(isinstance(material, dict) and required <= set(material), "D8_TEST_MATERIAL")
    raw, guard, meta = material["raw"], material["guard"], material["mutation"]
    b.need(material["scope"] in SCOPES and callable(guard) and
           isinstance(material["origin"], str) and 0 < len(material["origin"]) <= 2048 and
           isinstance(material["guard_name"], str) and
           material["guard_name"].startswith(("dualmic_broadside_output_d8.",
                                               "dualmic_broadside_output_d8_build.")),
           "D8_TEST_GUARD_BINDING")
    b.need(material["scope"] != "synthetic_engineering" or category in
           ("threshold_boundary", "projection_boundary"), "D8_TEST_ACTUAL_SCOPE")
    b.need(material["scope"] != "pre_finalization_template" or category == "missing_finalization",
           "D8_TEST_FINALIZATION_SCOPE")
    root = b.OUTPUT / "negatives" / category
    root.mkdir()
    pristine, mutant = root / "pristine.bin", root / "mutant.bin"
    first = _store(pristine, raw)
    phase.remaining()
    guard(pristine)
    b.need(b.desc(pristine) == first, "D8_TEST_GUARD_WROTE_PRISTINE")
    changed = mutate(category, raw, meta)
    b.need(changed != raw, "D8_NEGATIVE_NO_MUTATION:" + category)
    second = _store(mutant, changed)
    if category == "source_resealed":
        # The supplied full-member guard computes the mutant's new digest but
        # must still compare against immutable source authority, not this seal.
        _store(root / "self-resealed-descriptor.json", encode(second))
    outcome = _expect_reason(category, lambda: guard(mutant), phase)
    b.need(b.desc(mutant) == second and b.desc(pristine) == first,
           "D8_TEST_GUARD_WROTE_FIXTURE")
    result = {
        "category": category, "status": "PASS", "origin": material["origin"],
        "scope": material["scope"], "guard": material["guard_name"],
        "untouched_guard_passed": True,
        "pristine": {"path": pristine.relative_to(b.OUTPUT).as_posix(), **first},
        "mutant": {"path": mutant.relative_to(b.OUTPUT).as_posix(), **second},
        "mutation": meta, **outcome,
    }
    if category == "omitted_bad_window" and meta.get("selection") == "geometry":
        result["adverse_actual_window_present"] = False
        result["claim"] = "actual fixed-window completeness; synthetic adverse-row screen is separate"
    elif category == "omitted_bad_window":
        result["adverse_actual_window_present"] = True
    _store(root / "receipt.json", encode(result))
    return result

def _decode_engineering_numbers(value):
    if isinstance(value, dict):
        return {k: _decode_engineering_numbers(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_decode_engineering_numbers(v) for v in value]
    return {"NaN": float("nan"), "+Infinity": float("inf"),
            "-Infinity": -float("inf")}.get(value, value) if isinstance(value, str) else value

def engineering_screens(phase):
    """Persisted synthetic boundary predicates, never measured case results."""
    root = b.OUTPUT / "negatives" / "engineering-screens"
    root.mkdir()
    vectors = []

    def add(label, kind, values, expected=None, reason=None):
        vectors.append({"label": label, "kind": kind, "values": values,
                        "expected": expected, "expected_reason": reason})

    for kind, boundary in (("primary", 1.0), ("near", 0.0)):
        add(kind + "-below", kind, {"delta": adjacent(boundary, False)}, False)
        add(kind + "-equal", kind, {"delta": boundary}, True)
        add(kind + "-above", kind, {"delta": adjacent(boundary, True)}, True)
        add(kind + "-missing", kind, {"delta": None}, False)
    for label, value, result in (
        ("below", adjacent(-120.0, False), False),
        ("equal", -120.0, False),
        ("above", adjacent(-120.0, True), True)):
        add("projection-floor-" + label, "projection",
            {"baseline": value, "candidate": value, "required": True}, result)
    for label, value, result in (
        ("below", adjacent(-20.0, False), False),
        ("equal", -20.0, True),
        ("above", adjacent(-20.0, True), True)):
        add("projection-nonregression-" + label, "projection",
            {"baseline": -20.0, "candidate": value, "required": True}, result)
    for values in (
        {"baseline": None, "candidate": -20.0, "required": True},
        {"baseline": -20.0, "candidate": None, "required": True},
        {"baseline": None, "candidate": None, "required": True}):
        add("projection-missing-" + str(len(vectors)), "projection", values, False)
    add("projection-not-applicable", "projection",
        {"baseline": None, "candidate": None, "required": False}, True)
    for kind in ("energy", "recovery"):
        extra = {"required": True} if kind == "recovery" else {}
        for label, value, result in (
            ("below", adjacent(10.0, False), True),
            ("equal", 10.0, True),
            ("above", adjacent(10.0, True), False)):
            add(kind + "-" + label, kind, {"baseline": 10.0, "candidate": value, **extra}, result)
    for baseline, candidate in ((None, 10.0), (10.0, None), (None, None)):
        add("recovery-missing-" + str(len(vectors)), "recovery",
            {"baseline": baseline, "candidate": candidate, "required": True}, False)
    add("recovery-not-applicable", "recovery",
        {"baseline": None, "candidate": None, "required": False}, True)
    for baseline, candidate, result in ((0, 0, True), (1, 0, True), (1, 1, True), (0, 1, False)):
        add("count-" + str(len(vectors)), "counts",
            {"baseline": baseline, "candidate": candidate}, result)
    for invalid in (-1, 1.0, True, "not-a-count"):
        add("count-type-" + str(len(vectors)), "counts",
            {"baseline": 0, "candidate": invalid}, reason="D8_SCREEN_COUNT")
    for token in ("NaN", "+Infinity", "-Infinity"):
        for kind in ("primary", "near"):
            add(kind + "-" + token, kind, {"delta": token}, reason="D8_SCREEN_NONFINITE")
        for kind in ("projection", "energy", "recovery"):
            for field in ("baseline", "candidate"):
                values = {"baseline": 1.0, "candidate": 1.0}
                if kind != "energy":
                    values["required"] = True
                values[field] = token
                add(kind + "-" + field + "-" + token, kind, values,
                    reason="D8_SCREEN_NONFINITE")
        for kind in ("projection", "recovery"):
            add(kind + "-inapplicable-" + token, kind,
                {"baseline": None, "candidate": token, "required": False},
                reason="D8_SCREEN_NONFINITE")
    # An adverse synthetic window remains a veto; the actual omission guard
    # independently checks original fixed-window completeness, without requiring
    # the experiment to produce an adverse outcome to qualify its measurement.
    add("synthetic-adverse-window", "near", {"delta": -0.25}, False)
    add("synthetic-zero-delta-window", "near", {"delta": 0.0}, True)

    records = []
    for index, vector in enumerate(vectors):
        phase.remaining()
        path = root / ("%03d-%s.json" % (index, vector["label"].replace("+", "plus")))
        identity = _store(path, encode(vector))
        saved = _json(path.read_bytes())
        values = _decode_engineering_numbers(saved["values"])
        if saved["expected_reason"] is not None:
            outcome = _expect_reason(saved["label"],
                lambda saved=saved, values=values: d8.screen_check(saved["kind"], values),
                phase, saved["expected_reason"])
        else:
            actual = d8.screen_check(saved["kind"], values)
            b.need(type(actual) is bool and actual is saved["expected"],
                   "D8_ENGINEERING_SCREEN_RESULT:" + saved["label"])
            outcome = {"actual": actual}
        records.append({"label": saved["label"], "scope": "synthetic_engineering",
                        "fixture": {"path": path.relative_to(b.OUTPUT).as_posix(), **identity},
                        **outcome})
    result = {"status": "PASS", "scope": "synthetic predicate boundaries, no DSP",
              "count": len(records), "records": records}
    _store(root / "receipt.json", encode(result))
    return result

def engineering_silent_projection(phase):
    """Canonical fixed vectors expose the known zero-SI-SDR false improvement."""
    root = b.OUTPUT / "negatives" / "engineering-silent"
    root.mkdir()
    reference = [1000 if i % 2 == 0 else -1000 for i in range(320)]
    orthogonal = [1000 if i % 4 < 2 else -1000 for i in range(160)]
    baseline = [0] * 160 + [reference[i] // 10 + orthogonal[i] for i in range(160)]
    candidate = [0] * 320
    identities = {}
    for name, values in (("reference", reference), ("baseline", baseline), ("candidate", candidate)):
        path = root / (name + ".s16le")
        raw = struct.pack("<%dh" % len(values), *values)
        identities[name] = {"path": path.relative_to(b.OUTPUT).as_posix(), **_store(path, raw)}
    # Consume the persisted bytes, not the construction arrays.
    def read_samples(name):
        return list(struct.unpack("<320h", (root / (name + ".s16le")).read_bytes()))
    reference, baseline, candidate = (read_samples(n) for n in ("reference", "baseline", "candidate"))
    normalized = [[v / 32768.0 for v in signal] for signal in (reference, baseline, candidate)]
    baseline_score = d8.d1.si_sdr_span(normalized[0], normalized[1], 0, 160, 160)
    candidate_score = d8.d1.si_sdr_span(normalized[0], normalized[2], 0, 160, 160)
    baseline_gain = d8.quality.projection_gain_db(reference, baseline, 160)
    candidate_gain = d8.quality.projection_gain_db(reference, candidate, 160)
    b.need(baseline_score is not None and baseline_score < 0.0 and candidate_score == 0.0 and
           baseline_gain is not None and math.isfinite(baseline_gain) and baseline_gain > -120.0 and
           candidate_gain == -120.0, "D8_ENGINEERING_SILENT_CANONICAL")
    b.need(d8.screen_check("primary", {"delta": candidate_score - baseline_score}) is True and
           d8.screen_check("projection", {"baseline": baseline_gain, "candidate": candidate_gain,
                                         "required": True}) is False,
           "D8_ENGINEERING_SILENT_VETO")
    short = []
    for count in (15, 16, 159, 160):
        ref = reference[:count]
        out = candidate[:count]
        score = d8.d1.si_sdr_span([v / 32768.0 for v in ref],
                                     [v / 32768.0 for v in out], 0, 0, count)
        gain = d8.quality.projection_gain_db(ref, out, 0)
        applicable = count >= 16
        b.need((score is None) == (not applicable) and
               (gain is None if count < 160 else gain == -120.0),
               "D8_ENGINEERING_SHORT_NULL")
        permitted = d8.screen_check("projection",
            {"baseline": gain, "candidate": gain, "required": applicable})
        b.need(permitted is (not applicable), "D8_ENGINEERING_SHORT_SCREEN")
        short.append({"count": count, "canonical_score": score, "projection": gain,
                      "original_reference_applicable": applicable, "screen": permitted})
    lane = d8.d1.measure_lane(normalized[2], 160, 320, normalized[0], None, True)
    b.need(lane["offset_samples"] == 160 and
           lane["common"]["physical_sample_range"] == [0, 160] and
           lane["common"]["signal_sample_range"] == [160, 320] and
           len(lane["one_second_windows"]) == 1, "D8_ENGINEERING_FIXED_COORDINATES")
    result = {"status": "PASS", "scope": "synthetic fixed S16 vectors, no DSP or quality claim",
              "fixtures": identities, "baseline_si_sdr_db": baseline_score,
              "candidate_si_sdr_db": candidate_score, "baseline_projection_db": baseline_gain,
              "candidate_projection_db": candidate_gain, "projection_screen": False,
              "short_spans": short, "fixed_lane_coordinates": lane}
    _store(root / "receipt.json", encode(result))
    phase.remaining()
    return result

def engineering_flags(phase):
    """Both complete frozen flag orders and every single-field corruption."""
    root = b.OUTPUT / "negatives" / "engineering-flags"
    root.mkdir()
    actual_path = b.OUTPUT / "build/baseline-plain-build/CMakeFiles/audio_pipeline.dir/flags.make"
    build_path = b.TOOL / "baseline-plain-build"
    actual = actual_path.read_bytes()
    parsed = b.parse_flags(actual.decode("utf-8"), build_path)
    original = root / "actual-flags.make"
    _store(original, actual)
    b.parse_flags(original.read_text(encoding="utf-8"), build_path)
    sequences = [
        ["-O3", "-DNDEBUG", "-Wall", "-Wextra", "-Wpedantic", "-Werror", "-std=c11"],
        ["-O3", "-DNDEBUG", "-std=c11", "-Wall", "-Wextra", "-Wpedantic", "-Werror"],
    ]
    b.need(len(parsed["C_DEFINES"]) == 13 and len(parsed["C_INCLUDES"]) == 3,
           "D8_ENGINEERING_FLAGS_PRISTINE")
    records = []

    def exercise(label, sequence, reject=False, mutation=None, raw_mutation=None):
        value = {"C_DEFINES": list(parsed["C_DEFINES"]), "C_INCLUDES": list(parsed["C_INCLUDES"]),
                 "C_FLAGS": list(sequence)}
        if mutation:
            mutation(value)
        text = "".join(key + " = " + " ".join(value[key]) + "\n"
                       for key in ("C_DEFINES", "C_INCLUDES", "C_FLAGS"))
        if raw_mutation:
            text = raw_mutation(text)
        path = root / (label + ".make")
        identity = _store(path, text.encode("utf-8"))
        action = lambda: b.parse_flags(path.read_text(encoding="utf-8"), build_path)
        if reject:
            outcome = _expect_reason(label, action, phase, "D8_BUILD_FLAGS")
        else:
            result = action()
            b.need(result == value, "D8_ENGINEERING_FLAGS_ACCEPTANCE")
            outcome = {"accepted": True}
        records.append({"label": label, "scope": "synthetic_parser_fixture",
                        "fixture": {"path": path.relative_to(b.OUTPUT).as_posix(), **identity},
                        **outcome})
        phase.remaining()

    for n, sequence in enumerate(sequences):
        prefix = str(n) + "-"
        exercise(prefix + "accepted", sequence)
        for i in range(7):
            exercise(prefix + "missing-" + str(i), sequence[:i] + sequence[i + 1:], True)
            exercise(prefix + "duplicate-" + str(i), sequence + [sequence[i]], True)
        for i, extra in enumerate(("-funexpected", "-ffast-math", "-O2", "-std=gnu11", "-Wno-error")):
            exercise(prefix + "extra-" + str(i), sequence + [extra], True)
        for before, after in (("-O3", "-O2"), ("-std=c11", "-std=gnu11"), ("-Werror", "-Wno-error")):
            exercise(prefix + "replace-" + before[1:],
                     [after if item == before else item for item in sequence], True)
        exercise(prefix + "wrong-order", [sequence[1], sequence[0], *sequence[2:]], True)
    for field, count in (("C_DEFINES", 13), ("C_INCLUDES", 3)):
        for i in range(count):
            exercise(field + "-missing-" + str(i), sequences[0], True,
                     mutation=lambda v, f=field, i=i: v[f].pop(i))
            exercise(field + "-duplicate-" + str(i), sequences[0], True,
                     mutation=lambda v, f=field, i=i: v[f].append(v[f][i]))
            exercise(field + "-replace-" + str(i), sequences[0], True,
                     mutation=lambda v, f=field, i=i: v[f].__setitem__(i, v[f][i] + "-unexpected"))
        exercise(field + "-extra", sequences[0], True,
                 mutation=lambda v, f=field: v[f].append("-unexpected"))
    exercise("include-order", sequences[0], True, mutation=lambda v: v["C_INCLUDES"].reverse())
    for field in ("C_DEFINES", "C_INCLUDES", "C_FLAGS"):
        exercise(field + "-missing-assignment", sequences[0], True,
                 raw_mutation=lambda text, f=field: "\n".join(
                     line for line in text.splitlines() if not line.startswith(f + " =")))
        exercise(field + "-duplicate-assignment", sequences[0], True,
                 raw_mutation=lambda text, f=field: text + f + " =\n")
    exercise("unclosed-quote", sequences[0], True,
             raw_mutation=lambda text: text.replace("C_FLAGS =", "C_FLAGS = '", 1))
    exercise("long-invalid-token", sequences[0] + ["x" * 10000], True)
    b.need(len(records) == 107, "D8_ENGINEERING_FLAGS_COUNT")
    result = {"status": "PASS", "scope": "synthetic strict parser controls; no compiler execution",
              "actual_parser_origin": {"path": str(actual_path), **b.desc(actual_path)},
              "accepted_sequences": 2, "rejected_fixtures": 105, "records": records}
    _store(root / "receipt.json", encode(result))
    return result

def engineering_unity(phase):
    """Exact whole-document templates; no arbitrary comment stripping."""
    root = b.OUTPUT / "negatives" / "engineering-unity"
    root.mkdir()
    retained_source = b.OUTPUT / "build/baseline-plain-source"
    emitted_source = b.TOOL / "baseline-plain-source"
    built = b.read(b.OUTPUT / "build/build.json")
    identity = built["source"]
    actual_path = b.OUTPUT / "build/baseline-plain-build" / b.UNITY_NAME
    actual_fixture = root / "actual-unity.c.txt"
    actual_identity = _store(actual_fixture, actual_path.read_bytes())
    b.parse_generated_unity(actual_fixture.read_bytes(), retained_source, identity)
    names = tuple(b.UNITY_SOURCES)
    b.need(len(names) == 17, "D8_ENGINEERING_UNITY_COUNT")
    comments = ("", "/* NOLINTNEXTLINE(bugprone-suspicious-include,misc-include-cleaner) */\n")
    records = []

    def document(comment, sequence=names):
        return ("/* generated by CMake */\n\n" + "".join(
            comment + '#include "' + str(emitted_source / name) + '"\n\n'
            for name in sequence)).encode("utf-8")

    def exercise(label, raw, reject=False):
        path = root / (label + ".c.txt")
        saved = _store(path, raw)
        action = lambda: b.parse_generated_unity(path.read_bytes(), retained_source, identity)
        if reject:
            outcome = _expect_reason(label, action, phase, "D8_GENERATED_UNITY")
        else:
            action()
            outcome = {"accepted": True}
        records.append({"label": label, "scope": "synthetic_generated_document",
                        "fixture": {"path": path.relative_to(b.OUTPUT).as_posix(), **saved},
                        **outcome})
        phase.remaining()

    for index, comment in enumerate(comments):
        prefix = str(index) + "-"
        good = document(comment)
        exercise(prefix + "valid", good)
        for i in range(len(names)):
            exercise(prefix + "missing-" + str(i), document(comment, names[:i] + names[i + 1:]), True)
            exercise(prefix + "duplicate-" + str(i), document(comment, names + (names[i],)), True)
        exercise(prefix + "reordered", document(comment, names[::-1]), True)
        for i, tail in enumerate((b"int injected;\n", b"#define injected 1\n",
                                  b"/* arbitrary comment */\n", b'#include "/tmp/outside.c"\n')):
            exercise(prefix + "extra-" + str(i), good + tail, True)
        exercise(prefix + "unknown-source", document(comment, names[:-1] + ("src/unknown.c",)), True)
        exercise(prefix + "observer-source", document(comment, names[:-1] +
                 ("tests/validation/frontend_evolution/dualmic_stages_d1.c",)), True)
        exercise(prefix + "parent-path", good.replace(b"/src/ap_build_info.c",
                 b"/src/../src/ap_build_info.c"), True)
        exercise(prefix + "bom", b"\xef\xbb\xbf" + good, True)
        exercise(prefix + "crlf", good.replace(b"\n", b"\r\n"), True)
    good = document(comments[1])
    exercise("mixed-comment", good.replace(comments[1].encode("utf-8"), b"", 1), True)
    exercise("wrong-comment", good.replace(b"misc-include-cleaner", b"other-check"), True)
    result = {"status": "PASS", "scope": "synthetic generated-document controls; never compiled",
              "actual_parser_origin": {"path": str(actual_path), **b.desc(actual_path)},
              "actual_parser_fixture": {"path": actual_fixture.relative_to(b.OUTPUT).as_posix(),
                                       **actual_identity},
              "accepted_forms": 2, "count": len(records), "records": records}
    _store(root / "receipt.json", encode(result))
    return result

def engineering_protocol(phase):
    """Pure protocol/state controls only. No fork, signal, group, or subprocess."""
    root = b.OUTPUT / "negatives" / "engineering-protocol"
    root.mkdir()
    started, worker = 1000.0, 17

    def event(kind, now, seq, alone=True, **fields):
        return {"now": now, "alone": alone,
                "message": {"type": kind, "seq": seq, "pid": worker, **fields}}

    hello = [event("HELLO", 1000.1, 1)]
    active = hello + [event("PHASE_BEGIN", 1001.0, 2, name="admission")]
    command = active + [event("COMMAND_BEGIN", 1002.0, 3, label="tool")]
    complete = list(hello)
    for i, name in enumerate(b.supervision.PHASES):
        complete.append(event("PHASE_BEGIN", 1001.0 + i * 10.0, len(complete) + 1, name=name))
        if name != "negative":
            complete.append(event("PHASE_END", 1002.0 + i * 10.0, len(complete) + 1, name=name))
    before_fixtures = copy.deepcopy(complete)
    def next_sequence(events):
        return 1 + sum("message" in item for item in events)
    fixture_names = ("startup_before_group", "child_tree_timeout",
                     "exception_finally_timeout", "pipe_drain_timeout")
    for i, name in enumerate(fixture_names):
        complete.append(event("FIXTURE", 1061.1 + i * 0.15, next_sequence(complete), name=name))
        complete.append({"action": "fixture_complete", "name": name, "now": 1061.15 + i * 0.15})
    before_finish = copy.deepcopy(complete)
    complete.append(event("FINISH", 1062.0, next_sequence(complete),
                          completion_checked=True, stdout_flushed=True))
    vectors = []

    def add(label, events, reason=None, expected=None):
        vectors.append({"label": label, "started": started, "worker": worker,
                        "events": events, "expected_reason": reason, "expected": expected or {}})

    add("hello", hello, expected={"root_deadline": 2200.0, "deadline": 2200.0})
    add("phase-cap", active, expected={"phase_deadline": 1301.0, "deadline": 1301.0})
    add("command-cap", command, expected={"command_deadline": 1032.0, "deadline": 1032.0})
    add("quiescent-keeps-deadline", command + [
        event("COMMAND_QUIESCENT", 1031.0, 4, label="tool")],
        expected={"command_deadline": 1032.0, "deadline": 1032.0})
    add("command-end", command + [event("COMMAND_END", 1003.0, 4, label="tool", terminal=True)],
        expected={"command": None, "command_deadline": None, "deadline": 1301.0})
    add("phase-caps-command", active + [event("COMMAND_BEGIN", 1290.0, 3, label="tool")],
        expected={"command_deadline": 1301.0, "deadline": 1301.0})
    add("root-caps-both", hello + [event("PHASE_BEGIN", 2190.0, 2, name="admission"),
        event("COMMAND_BEGIN", 2195.0, 3, label="tool")],
        expected={"root_deadline": 2200.0, "phase_deadline": 2200.0, "command_deadline": 2200.0})
    add("complete-keeps-negative-deadline", complete,
        expected={"finished": True, "phase": "negative", "phase_deadline": 1361.0, "deadline": 1361.0,
                  "fixture": None, "fixture_deadline": None, "fixture_index": 4})
    add("missing-hello", [event("PHASE_BEGIN", 1001.0, 1, name="admission")], "D8_IPC_STATE")
    add("duplicate-hello", hello + [event("HELLO", 1001.0, 2)], "D8_IPC_STATE")
    add("bad-phase-order", hello + [event("PHASE_BEGIN", 1001.0, 2, name="run")], "D8_PHASE_ORDER")
    add("active-phase-replaced", active + [event("PHASE_BEGIN", 1002.0, 3, name="baseline-build")],
        "D8_PHASE_ORDER")
    add("active-command-phase-end", command + [event("PHASE_END", 1003.0, 4, name="admission")],
        "D8_PHASE_END")
    add("active-command-replaced", command + [event("COMMAND_BEGIN", 1003.0, 4, label="second")],
        "D8_COMMAND_STATE")
    add("wrong-command-label", command + [event("COMMAND_END", 1003.0, 4, label="other", terminal=True)],
        "D8_COMMAND_END")
    add("unterminated-command", command + [event("COMMAND_END", 1003.0, 4, label="tool", terminal=False)],
        "D8_COMMAND_END")
    add("quiescent-without-command", active + [event("COMMAND_QUIESCENT", 1002.0, 3)],
        "D8_COMMAND_QUIESCENT")
    add("end-without-command", active + [event("COMMAND_END", 1002.0, 3, terminal=True)],
        "D8_COMMAND_END")
    add("end-without-phase", hello + [event("PHASE_END", 1001.0, 2)], "D8_PHASE_END")
    for label, replacement in (("sequence-zero", 0), ("sequence-boolean", True), ("sequence-float", 1.0)):
        value = copy.deepcopy(hello)
        value[0]["message"]["seq"] = replacement
        add(label, value, "D8_IPC_SEQUENCE")
    for label, replacement in (("pid-wrong", 18), ("pid-float", 17.0), ("pid-boolean", True)):
        value = copy.deepcopy(hello)
        value[0]["message"]["pid"] = replacement
        add(label, value, "D8_IPC_SEQUENCE")
    add("duplicate-sequence", hello + [event("PHASE_BEGIN", 1001.0, 1, name="admission")],
        "D8_IPC_SEQUENCE")
    for label, prefix, last, reason in (
        ("hello-descendant", [], event("HELLO", 1000.1, 1, alone=False), "D8_IPC_STATE"),
        ("phase-descendant", hello, event("PHASE_BEGIN", 1001.0, 2, alone=False, name="admission"),
         "D8_PHASE_ORDER"),
        ("command-descendant", active, event("COMMAND_BEGIN", 1002.0, 3, alone=False, label="tool"),
         "D8_COMMAND_STATE"),
        ("quiescent-descendant", command, event("COMMAND_QUIESCENT", 1003.0, 4, alone=False, label="tool"),
         "D8_COMMAND_QUIESCENT"),
        ("end-descendant", command, event("COMMAND_END", 1003.0, 4, alone=False, label="tool", terminal=True),
         "D8_COMMAND_END"),
        ("phase-end-descendant", active, event("PHASE_END", 1002.0, 3, alone=False, name="admission"),
         "D8_PHASE_END")):
        add(label, prefix + [last], reason)
    add("command-deadline-equality", command + [
        event("COMMAND_END", 1032.0, 4, label="tool", terminal=True)], "D8_SUPERVISOR_TIMEOUT")
    add("quiescent-cannot-extend", command + [
        event("COMMAND_QUIESCENT", 1031.0, 4, label="tool"),
        event("COMMAND_END", 1032.0, 5, label="tool", terminal=True)], "D8_SUPERVISOR_TIMEOUT")
    add("phase-deadline-equality", active + [
        event("COMMAND_BEGIN", 1301.0, 3, label="tool")], "D8_SUPERVISOR_TIMEOUT")
    add("root-deadline-equality", hello + [
        event("PHASE_BEGIN", 2200.0, 2, name="admission")], "D8_SUPERVISOR_TIMEOUT")
    add("finish-without-fixed-fixtures", before_fixtures + [
        event("FINISH", 1062.0, next_sequence(before_fixtures),
              completion_checked=True, stdout_flushed=True)], "D8_FINISH")
    add("early-finish", active + [event("FINISH", 1002.0, 3,
        completion_checked=True, stdout_flushed=True)], "D8_FINISH")
    for label, fields in (
        ("missing-completion", {"completion_checked": False, "stdout_flushed": True}),
        ("missing-stdout-flush", {"completion_checked": True, "stdout_flushed": False})):
        add(label, before_finish + [event("FINISH", 1062.0, next_sequence(before_finish), **fields)], "D8_FINISH")
    add("finish-descendant", before_finish + [event("FINISH", 1062.0, next_sequence(before_finish),
        alone=False, completion_checked=True, stdout_flushed=True)], "D8_FINISH")
    add("negative-phase-cannot-disarm", before_finish + [
        event("PHASE_END", 1062.0, next_sequence(before_finish), name="negative")], "D8_PHASE_END")
    add("post-finish-message", complete + [event("PHASE_BEGIN", 1063.0, next_sequence(complete),
        name="negative")], "D8_IPC_STATE")
    add("worker-abort", hello + [event("ABORT", 1001.0, 2)], "D8_WORKER_ABORT")
    add("unknown-message", hello + [event("UNKNOWN", 1001.0, 2)], "D8_IPC_UNKNOWN")


    b.need(tuple(b.supervision.FIXTURE_NAMES) == fixture_names, "D8_ENGINEERING_FIXTURE_NAMES")
    first_fixture = before_fixtures + [
        event("FIXTURE", 1061.1, next_sequence(before_fixtures), name=fixture_names[0])]
    first_complete = first_fixture + [
        {"action": "fixture_complete", "name": fixture_names[0], "now": 1061.2}]
    add("fixture-two-second-lease", first_fixture,
        expected={"fixture": fixture_names[0], "fixture_index": 0,
                  "fixture_deadline": 1063.1, "deadline": 1063.1})
    add("fixture-completion-keeps-phase", first_complete,
        expected={"fixture": None, "fixture_index": 1, "fixture_deadline": None, "deadline": 1361.0})
    add("fixture-wrong-phase", active + [
        event("FIXTURE", 1002.0, 3, name=fixture_names[0])], "D8_FIXTURE_STATE")
    add("fixture-wrong-order", before_fixtures + [
        event("FIXTURE", 1061.1, next_sequence(before_fixtures), name=fixture_names[1])],
        "D8_FIXTURE_STATE")
    add("fixture-descendant", before_fixtures + [
        event("FIXTURE", 1061.1, next_sequence(before_fixtures), alone=False, name=fixture_names[0])],
        "D8_FIXTURE_STATE")
    negative_command = before_fixtures + [
        event("COMMAND_BEGIN", 1061.1, next_sequence(before_fixtures), label="existing")]
    add("fixture-active-command", negative_command + [
        event("FIXTURE", 1061.2, next_sequence(negative_command), name=fixture_names[0])],
        "D8_FIXTURE_STATE")
    for label, name in (("fixture-completion-without-active", fixture_names[0]),
                        ("fixture-null-completion-without-active", None)):
        add(label, before_fixtures + [
            {"action": "fixture_complete", "name": name, "now": 1061.1}], "D8_FIXTURE_STATE")
    add("fixture-wrong-completion-name", first_fixture + [
        {"action": "fixture_complete", "name": fixture_names[1], "now": 1061.2}], "D8_FIXTURE_STATE")
    add("fixture-duplicate-completion", first_complete + [
        {"action": "fixture_complete", "name": fixture_names[0], "now": 1061.3}], "D8_FIXTURE_STATE")
    add("fixture-no-ordinary-request", first_fixture + [
        event("COMMAND_BEGIN", 1061.2, next_sequence(first_fixture), label="unexpected")],
        "D8_FIXTURE_STATE")
    add("fixture-no-second-fixture", first_fixture + [
        event("FIXTURE", 1061.2, next_sequence(first_fixture), name=fixture_names[1])],
        "D8_FIXTURE_STATE")
    add("fixture-completion-deadline-equality", first_fixture + [
        {"action": "fixture_complete", "name": fixture_names[0], "now": 1063.1}],
        "D8_SUPERVISOR_TIMEOUT")
    add("fixture-request-deadline-equality", first_fixture + [
        event("COMMAND_BEGIN", 1063.1, next_sequence(first_fixture), label="unexpected")],
        "D8_SUPERVISOR_TIMEOUT")
    add("fixture-no-fifth-request", before_finish + [
        event("FIXTURE", 1062.0, next_sequence(before_finish), name=fixture_names[0])],
        "D8_FIXTURE_STATE")
    add("phase-caps-fixture", before_fixtures + [
        event("FIXTURE", 1360.0, next_sequence(before_fixtures), name=fixture_names[0])],
        expected={"fixture_deadline": 1361.0, "deadline": 1361.0})
    root_capped = copy.deepcopy(before_fixtures)
    root_capped[-1]["now"] = 2199.0
    add("root-caps-fixture", root_capped + [
        event("FIXTURE", 2199.5, next_sequence(root_capped), name=fixture_names[0])],
        expected={"fixture_deadline": 2200.0, "phase_deadline": 2200.0, "deadline": 2200.0})

    def play(value):
        protocol = b.supervision.Protocol(value["started"], value["worker"])
        for item in value["events"]:
            if item.get("action") == "fixture_complete":
                protocol.fixture_complete(item["name"], item["now"])
            else:
                protocol.request(item["message"], item["now"], alone=item["alone"])
        actual = {key: getattr(protocol, key) for key in
                  ("root_deadline", "phase_deadline", "command_deadline", "phase", "command", "finished",
                   "fixture", "fixture_deadline", "fixture_index")}
        actual["deadline"] = protocol.deadline()
        b.need(all(actual[k] == v for k, v in value["expected"].items()),
               "D8_ENGINEERING_PROTOCOL_STATE")
        return actual

    records = []
    for index, vector in enumerate(vectors):
        path = root / ("%03d-%s.json" % (index, vector["label"]))
        identity = _store(path, encode(vector))
        saved = _json(path.read_bytes())
        if saved["expected_reason"]:
            outcome = _expect_reason(saved["label"], lambda saved=saved: play(saved),
                                     phase, saved["expected_reason"])
        else:
            outcome = {"state": play(saved)}
        records.append({"label": saved["label"], "scope": "synthetic_protocol",
                        "fixture": {"path": path.relative_to(b.OUTPUT).as_posix(), **identity}, **outcome})
    first_path = root / "first-failure.json"
    _store(first_path, encode({"first": "first reason", "later": "later reason"}))
    messages = _json(first_path.read_bytes())
    protocol = b.supervision.Protocol(started, worker)
    for reason in (messages["first"], messages["later"]):
        _expect_reason("first-failure", lambda reason=reason: protocol.fail(reason), phase, messages["first"])
    _expect_reason("request-after-first-failure",
        lambda: protocol.request({"type": "HELLO", "seq": 1, "pid": worker},
                                 1000.1, alone=True), phase, messages["first"])
    _expect_reason("fixture-completion-after-first-failure",
        lambda: protocol.fixture_complete(None, 1000.1), phase, messages["first"])
    b.need(protocol.first_failure == messages["first"], "D8_ENGINEERING_FIRST_FAILURE")
    protocol = b.supervision.Protocol(started, worker)
    for item in before_fixtures:
        protocol.request(item["message"], item["now"], alone=item["alone"])
    _expect_reason("fixture-first-error", lambda: protocol.fixture_complete(None, 1061.1),
                   phase, "D8_FIXTURE_STATE")
    _expect_reason("fixture-first-error-retained",
        lambda: protocol.request({"type": "UNKNOWN", "seq": next_sequence(before_fixtures),
                                  "pid": worker}, 1061.2, alone=True), phase, "D8_FIXTURE_STATE")
    b.need(protocol.first_failure == "D8_FIXTURE_STATE", "D8_ENGINEERING_FIRST_FAILURE")
    result = {"status": "PASS", "scope": "pure protocol only, not an OS kill or group-containment test",
              "count": len(records), "records": records, "first_failure_preserved": True,
              "OS_SIGKILL_control": "NOT_EXECUTED_BY_THIS_IN_PROCESS_SUITE",
              "group_escape_prevention_claimed": False}
    _store(root / "receipt.json", encode(result))
    return result

def engineering_budgets(phase):
    """Pure shared category predicates and frozen closed-writer accounting."""
    root = b.OUTPUT / "negatives" / "engineering-budgets"
    root.mkdir()
    lock = b.contract()
    caps = lock["budgets"]["categories"]
    b.need(caps == b.CAPS, "D8_ENGINEERING_BUDGET_CAPS")
    records = []
    for name, cap in caps.items():
        for label, amount, rejects in (("below", cap - 1, False), ("equal", cap, False),
                                       ("above", cap + 1, True)):
            totals = dict.fromkeys(caps, 0)
            totals[name] = amount
            path = root / (name + "-" + label + ".json")
            identity = _store(path, encode(totals))
            action = lambda path=path: b.check_category_totals(_json(path.read_bytes()))
            if rejects:
                reason = b.CATEGORY_REASONS.get(name, "D8_CATEGORY_OVERFLOW:" + name)
                outcome = _expect_reason(name + "-" + label, action, phase, reason)
            else:
                action()
                outcome = {"accepted": True}
            records.append({"category": name, "boundary": label,
                            "fixture": {"path": path.relative_to(b.OUTPUT).as_posix(), **identity},
                            **outcome})
    total_records = []
    ceiling = sum(caps.values())
    for label, amount, rejects in (("below", ceiling - 1, False),
                                   ("equal", ceiling, False), ("above", ceiling + 1, True)):
        path = root / ("total-" + label + ".json")
        identity = _store(path, encode({"bytes": amount}))
        action = lambda path=path: b.check_total_bytes(_json(path.read_bytes())["bytes"])
        if rejects:
            outcome = _expect_reason("total-" + label, action, phase, "D8_OUTPUT_BYTES_BOUND")
        else:
            action()
            outcome = {"accepted": True}
        total_records.append({"boundary": label,
            "fixture": {"path": path.relative_to(b.OUTPUT).as_posix(), **identity}, **outcome})
    frames = [entry["catalog"]["frames"] for entry in lock["original_d2_case_input_lock"]["cases"]]
    b.need(len(frames) == 60 and min(frames) == 529 and max(frames) == 629,
           "D8_ENGINEERING_FRAME_MATRIX")
    values = []
    for frame_count in sorted(set(frames)):
        plain, observed = 320 * frame_count, 640 * frame_count
        scientific = 2 * 2 * plain + 2 * 19 * observed
        reservation = scientific + 8 * 1024 * 1024
        b.need(314 * frame_count <= plain and 455 + 440 * frame_count <= observed and
               max(2019, 4096, 472 * frame_count, 24 * frame_count) <= observed and
               reservation <= 24 * 1024 * 1024, "D8_ENGINEERING_SCRATCH_PROOF")
        values.append({"frames": frame_count, "plain_rlimit_fsize": plain,
                       "observed_rlimit_fsize": observed, "scientific_files": 42,
                       "scientific_bound": scientific, "ancillary": 8 * 1024 * 1024,
                       "total_reserved": reservation})
    b.need(max(row["scientific_bound"] for row in values) == 16102400 and
           max(row["total_reserved"] for row in values) == 24491008 and
           sum(caps.values()) == 535454336 < b.OUTPUT_LIMIT,
           "D8_ENGINEERING_GLOBAL_BOUND")
    # Exercise real category resolution on every original two-component key.
    classification = {}
    for entry in lock["original_d2_case_input_lock"]["cases"]:
        key = entry["catalog"]["key"]
        for template in lock["retention"]["files"]:
            if not template.startswith("cases/{key}/"):
                continue
            relative = template.format(key=key)
            classification[relative] = b.category(b.OUTPUT / relative)
    b.need(len(classification) == 60 * len([p for p in lock["retention"]["files"]
           if p.startswith("cases/{key}/")]), "D8_ENGINEERING_CATEGORY_CLOSURE")
    result = {"status": "PASS", "scope": "pure budget predicates and finite scientific writer proof",
              "boundary_fixtures": records, "total_boundary_fixtures": total_records,
              "scientific_cases": values,
              "original_key_category_mapping": classification,
              "toolchain_temporary_aggregate_prewrite_guarantee": False,
              "free_space_is_reservation": False, "OS_rlimit_reinstallation_in_test": False}
    _store(root / "receipt.json", encode(result))
    phase.remaining()
    return result

def engineering_observer_receipts(phase):
    """Read back already-executed build controls. Never launch another process."""
    root = b.OUTPUT / "negatives" / "engineering-observer-receipts"
    root.mkdir()
    built_path = b.OUTPUT / "build/build.json"
    built = b.read(built_path)
    records = {}
    for arm in ("baseline", "candidate"):
        form = arm + "-observed"
        expected = {"status": "PASS", "arm": arm, "comparisons": 10584,
                    "equation_comparisons": 10584, "equation_samples": 1693440,
                    "agc_comparisons": 32, "record_comparisons": 4,
                    "layout_checked": True, "negative_checks": 21}
        path = root / (form + ".json")
        identity = _store(path, encode(built["forms"][form]["engineering"]))
        actual = _json(path.read_bytes())
        b.need(actual == expected, "D8_ENGINEERING")
        records[form] = {"origin": "build/build.json#forms/" + form + "/engineering",
                         "fixture": {"path": path.relative_to(b.OUTPUT).as_posix(), **identity},
                         "result": actual}
    result = {"status": "PASS", "scope": "qualified actual build engineering receipts, no new DSP",
              "source_build": b.desc(built_path), "forms": records,
              "scientific_tracking_off_experiment": False}
    _store(root / "receipt.json", encode(result))
    phase.remaining()
    return result


def engineering_original_locks(phase):
    """Regression for the three D8 annotations on the complete original locks."""
    root = b.OUTPUT / "negatives" / "engineering-original-locks"
    root.mkdir()
    lock_path = b.ROOT / b.LOCK
    frozen = b.read(lock_path)
    value = {key: frozen[key] for key in
             ("original_admission", "original_d2_case_input_lock")}
    # Independent, unchanged historical helpers provide the full authorities.
    # Do not derive either expected object by deleting fields from the fixture.
    expected_admission = b.admission.frozen_lock()
    expected_d2 = b.d2.input_lock()
    authorities_before = encode([expected_admission, expected_d2])
    pristine = root / "pristine.json"
    pristine_identity = _store(pristine, encode(value))

    def guard(path):
        saved = _json(path.read_bytes())
        return b.check_original_locks(
            saved["original_admission"], saved["original_d2_case_input_lock"],
            expected_admission, expected_d2, b.admission.FREEZE)

    b.need(guard(pristine) is True, "D8_ENGINEERING_ORIGINAL_LOCK_PRISTINE")
    b.need(value["original_admission"]["required_status"] ==
           "INPUT_ADMITTED_NO_DSP_EXECUTION", "D8_ENGINEERING_ORIGINAL_LOCK_PRISTINE")
    old_hash = value["original_admission"]["artifact"]["sha256"]
    b.need(isinstance(old_hash, str) and len(old_hash) == 64,
           "D8_ENGINEERING_ORIGINAL_LOCK_PRISTINE")
    changed_hash = ("1" if old_hash[0] == "0" else "0") + old_hash[1:]
    frame_count = value["original_d2_case_input_lock"]["cases"][0]["catalog"]["frames"]
    b.need(type(frame_count) is int, "D8_ENGINEERING_ORIGINAL_LOCK_PRISTINE")
    mutations = (
        ("wrong-required-status", "replace", ["original_admission", "required_status"],
         "INPUT_ADMITTED"),
        ("missing-required-status", "delete", ["original_admission", "required_status"], None),
        ("altered-original-field", "replace", ["original_admission", "artifact", "sha256"],
         changed_hash),
        ("missing-original-field", "delete", ["original_admission", "report_sha256"], None),
        ("nested-D2-drift", "replace",
         ["original_d2_case_input_lock", "cases", 0, "catalog", "frames"], frame_count + 1),
    )
    records = []
    for label, operation, path, replacement in mutations:
        phase.remaining()
        b.need(guard(pristine) is True, "D8_ENGINEERING_ORIGINAL_LOCK_PRISTINE")
        mutant = copy.deepcopy(value)
        if operation == "delete":
            parent = _at(mutant, path[:-1])
            b.need(path[-1] in parent, "D8_ENGINEERING_ORIGINAL_LOCK_PRISTINE")
            del parent[path[-1]]
        else:
            _set(mutant, path, replacement)
        raw = encode(mutant)
        b.need(raw != pristine.read_bytes(), "D8_NEGATIVE_NO_MUTATION:" + label)
        target = root / (label + ".json")
        identity = _store(target, raw)
        outcome = _expect_reason(label, lambda target=target: guard(target),
                                 phase, "D8_FULL_ORIGINAL_LOCK")
        b.need(b.desc(pristine) == pristine_identity and b.desc(target) == identity and
               encode([expected_admission, expected_d2]) == authorities_before,
               "D8_ENGINEERING_ORIGINAL_LOCK_MUTATED_AUTHORITY")
        records.append({"label": label, "operation": operation, "path": path,
                        "scope": "isolated mutation of actual frozen contract metadata",
                        "untouched_guard_passed": True,
                        "fixture": {"path": target.relative_to(b.OUTPUT).as_posix(), **identity},
                        **outcome})
    result = {"status": "PASS", "scope": "full original-lock metadata regression, no DSP or audio claim",
              "guard": "dualmic_broadside_output_d8_build.check_original_locks",
              "origin": {"path": str(lock_path), **b.desc(lock_path)},
              "pristine": {"path": pristine.relative_to(b.OUTPUT).as_posix(), **pristine_identity},
              "authorities": ["dualmic_zero_d3_source.frozen_lock", "dualmic_gain_d2.input_lock"],
              "pristine_passed": True, "rejected_mutants": len(records), "records": records,
              "full_original_admission_equality_required": True,
              "full_nested_D2_equality_required": True,
              "frozen_scientific_negative_category_added": False}
    _store(root / "receipt.json", encode(result))
    phase.remaining()
    return result


def engineering_tool_lookup(phase):
    """Synthetic sealed-path selection; no executable probe or tool invocation."""
    root = b.OUTPUT / "negatives" / "engineering-tool-lookup"
    root.mkdir()
    sealed = "/usr/bin:/bin:/usr/local/bin"
    b.need(b.SEALED_PATH == sealed and b.environment()["PATH"] == sealed,
           "D8_ENGINEERING_SEALED_PATH")
    vectors = [
        {"label": "usr-bin-precedence", "tool": "cmake",
         "executable_paths": ["/usr/local/bin/cmake", "/bin/cmake", "/usr/bin/cmake"],
         "ambient_PATH": "/usr/local/bin:/bin:/usr/bin", "expected": "/usr/bin/cmake"},
        {"label": "bin-precedence", "tool": "cmake",
         "executable_paths": ["/usr/local/bin/cmake", "/bin/cmake"],
         "ambient_PATH": "/usr/local/bin:/bin", "expected": "/bin/cmake"},
        {"label": "local-fallback", "tool": "cmake",
         "executable_paths": [None, None, "/usr/local/bin/cmake"],
         "ambient_PATH": "/opt/unregistered", "expected": "/usr/local/bin/cmake"},
        {"label": "compiler-precedence", "tool": "cc",
         "executable_paths": ["/usr/local/bin/cc", "/bin/cc", "/usr/bin/cc"],
         "ambient_PATH": "/bin:/usr/local/bin:/usr/bin", "expected": "/usr/bin/cc"},
        {"label": "ambient-order-ignored", "tool": "cmake",
         "executable_paths": ["/opt/unregistered/cmake", "/usr/local/bin/cmake", "/usr/bin/cmake"],
         "ambient_PATH": "/opt/unregistered:/usr/local/bin:/usr/bin", "expected": "/usr/bin/cmake"},
        {"label": "missing-tool", "tool": "cmake", "executable_paths": [None, None, None],
         "ambient_PATH": "", "expected": None},
        {"label": "ambient-only-ignored", "tool": "cmake",
         "executable_paths": ["/opt/unregistered/cmake", "/home/runner/bin/cmake"],
         "ambient_PATH": "/opt/unregistered:/home/runner/bin", "expected": None},
        {"label": "unregistered-neighbors-ignored", "tool": "cc",
         "executable_paths": ["/usr/local/sbin/cc", "/usr/bin-extra/cc"],
         "ambient_PATH": "/usr/local/sbin:/usr/bin-extra", "expected": None},
        {"label": "bounded-long-name-diagnostic", "tool": "d8-" + "x" * 61,
         "executable_paths": [], "ambient_PATH": "/opt/unregistered", "expected": None},
    ]
    records = []
    for vector in vectors:
        phase.remaining()
        path = root / (vector["label"] + ".json")
        identity = _store(path, encode(vector))
        saved = _json(path.read_bytes())
        # ambient_PATH is deliberately only fixture metadata. The shared
        # production selector has no ambient-path argument and sees the exact
        # executable inventory, including paths it must ignore.
        available = list(saved["executable_paths"])
        observed = {}

        def action():
            try:
                selected = b.select_tool_lookup(saved["tool"], available)
            except ValueError as error:
                detail = getattr(error, "d8_tool_lookup", None)
                expected = {"tool": saved["tool"], "path": sealed,
                            "candidates": [directory + "/" + saved["tool"]
                                           for directory in sealed.split(":")]}
                b.need(str(error) == "D8_TOOL_MISSING" and detail == expected and
                       len(encode({"reason": "D8_TOOL_MISSING", "tool_lookup": detail})) <= 1024,
                       "D8_ENGINEERING_TOOL_DIAGNOSTIC")
                observed["diagnostic"] = copy.deepcopy(detail)
                raise
            b.need(type(selected) is str and selected == saved["expected"],
                   "D8_ENGINEERING_TOOL_SELECTION")
            observed["selected"] = selected

        if saved["expected"] is None:
            outcome = _expect_reason(saved["label"], action, phase, "D8_TOOL_MISSING")
        else:
            action()
            outcome = {"accepted": True}
        b.need(available == saved["executable_paths"] and b.desc(path) == identity,
               "D8_ENGINEERING_TOOL_LOOKUP_MUTATION")
        records.append({"label": saved["label"], "scope": "synthetic executable-path inventory",
                        "fixture": {"path": path.relative_to(b.OUTPUT).as_posix(), **identity},
                        **observed, **outcome})
    result = {"status": "PASS", "guard": "dualmic_broadside_output_d8_build.select_tool_lookup",
              "scope": "pure sealed-PATH selection and bounded missing-tool diagnostics",
              "sealed_path": sealed, "diagnostic_line_cap_bytes": 1024,
              "count": len(records), "records": records,
              "ambient_PATH_values_are_synthetic_metadata": True,
              "production_globals_monkeypatched": False, "executable_probes_run": False,
              "tools_invoked": False, "frozen_scientific_negative_category_added": False}
    _store(root / "receipt.json", encode(result))
    phase.remaining()
    return result

def engineering_controls(phase):
    # No mutation of D7 globals, no compiler flags, and no subprocess launch.
    return {
        "original_locks": engineering_original_locks(phase),
        "tool_lookup": engineering_tool_lookup(phase),
        "observer_receipts": engineering_observer_receipts(phase),
        "strict_flags": engineering_flags(phase),
        "generated_unity": engineering_unity(phase),
        "screens": engineering_screens(phase),
        "silent_projection": engineering_silent_projection(phase),
        "protocol": engineering_protocol(phase),
        "budgets": engineering_budgets(phase),
    }


def check_fatal_prefix(fixture_files):
    """Only the fixed, already-run supervisor subtree may predate this suite."""
    b.need(isinstance(fixture_files, dict), "D8_TEST_FATAL_FIXTURE_MAP")
    names = ("startup_before_group", "child_tree_timeout",
             "exception_finally_timeout", "pipe_drain_timeout")
    leaves = {"pending.json": 4096, "stdout.bin": 65536,
              "stderr.bin": 65536, "receipt.json": 8192}
    allowed = {"negatives/supervisor-fatal/" + name + "/" + leaf: cap
               for name in names for leaf, cap in leaves.items()}
    b.need(set(fixture_files) == set(allowed), "D8_TEST_FATAL_FIXTURE_MAP")
    for path, descriptor in fixture_files.items():
        b.need(isinstance(descriptor, dict) and set(descriptor) == {"bytes", "sha256"} and
               type(descriptor["bytes"]) is int and 0 <= descriptor["bytes"] <= allowed[path] and
               b.desc(b.OUTPUT / path) == descriptor, "D8_TEST_FATAL_FIXTURE_READBACK")
    root = b.OUTPUT / "negatives"
    actual = b.inventory(root)
    expected = {path.removeprefix("negatives/"): value for path, value in fixture_files.items()}
    b.need(actual["files"] == expected and
           set(actual["directories"]) == b.directories(expected),
           "D8_TEST_FATAL_PREFIX_CLOSURE")
    # Both forbidden marker names, all unknown outputs, and empty extra dirs
    # are rejected by the exact closure above, not hidden by a wildcard.
    return dict(sorted(fixture_files.items()))

def actual_negatives(phase, fatal_fixture_files):
    """One qualified readback, persisted isolated controls, and a closed receipt."""
    b.need(not _fixture_files and _written == 0, "D8_NEGATIVE_ALREADY_STARTED")
    phase.remaining()
    order = b.contract()["tests"]["negative_categories"]
    b.need(len(order) == 76 and len(set(order)) == 76 and set(order) == set(REASONS),
           "D8_NEGATIVE_CATEGORY_SET")
    fatal_files = check_fatal_prefix(fatal_fixture_files)
    b.check_phase(b.OUTPUT, "verify")
    # This shared driver entrypoint performs normal full readback with original
    # source/input/state bindings, checks saved report/seal/readback identities,
    # and binds the independently loaded context used by negative_material.
    qualification = d8.qualify_negative_inputs(phase)
    b.need(isinstance(qualification, dict) and len(qualification) > 0,
           "D8_NEGATIVE_QUALIFICATION")
    root = b.OUTPUT / "negatives"
    _store(root / "qualification.json", encode(qualification))
    records = []
    for category in order:
        phase.remaining()
        material = d8.negative_material(category, phase)
        records.append(_exercise(category, material, phase))
    b.need([record["category"] for record in records] == order and
           all(record["status"] == "PASS" and record["untouched_guard_passed"] is True and
               record["expected_reason"] == REASONS[record["category"]] ==
               record["observed_reason"] for record in records),
           "D8_NEGATIVE_CATEGORY_SET")
    engineering = engineering_controls(phase)
    scope_counts = {scope: sum(record["scope"] == scope for record in records)
                    for scope in sorted(SCOPES)}
    # All fixture paths and bytes are exact, including intermediate receipts.
    # The final report sits outside negatives and is independently included in
    # the driver's fixed final closure. There is no negatives/** allow wildcard.
    fixture_files = dict(sorted(_fixture_files.items()))
    b.need(sum(item["bytes"] for item in fixture_files.values()) == _written and
           all(b.desc(b.OUTPUT / path) == identity for path, identity in fixture_files.items()),
           "D8_TEST_FIXTURE_READBACK")
    result = {
        "experiment": b.EXPERIMENT, "status": "PASS", "count": len(records),
        "qualification": qualification, "canonical_analysis_runs": 1,
        "DSP_executed": False, "models_executed": False,
        "test_fixture_subprocesses_executed": False,
        "qualification_source_commands": "normal supervised read-only source-identity commands",
        "targeted_mutations": records, "scope_counts": scope_counts,
        "engineering_controls": engineering,
        "fixture_files": fixture_files, "fixture_bytes": _written,
        "fixture_subcap_bytes": FIXTURE_TOTAL_BYTES,
        "shared_report_category_cap_bytes":
            b.CAPS["all_reports_receipts_logs_negatives_seals_completion"],
        "OS_fatal_fixture_scope": "separate supervisor-owned result appended by driver",
        "supervisor_fixture_files_verified": fatal_files,
        "synthetic_controls_are_actual_measurements": False,
        "full_unobserved_SYNC_AEC_NS_state_capture_claimed": False,
        "toolchain_temporary_aggregate_prewrite_guarantee": False,
    }
    phase.remaining()
    b.dump(b.OUTPUT / "negative-tests.json", result, compact=True)
    phase.remaining()
    return result
