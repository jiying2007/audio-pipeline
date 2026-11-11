#!/usr/bin/env python3
"""D7 targeted actual-evidence negatives, with fixed expected rejection reasons.

The completed untouched evidence is fully qualified once in this phase.
Each negative then reads a persisted isolated corruption through the SAME
guard used by normal production readback. No DSP, build, or scorer is rerun
for the 51 corruptions. A wrong exception, timeout, or I/O error fails the test.
"""
from __future__ import annotations
import contextlib
import copy
import csv
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import struct
import tempfile
import time
import sys

import dualmic_upstream_d7 as d7
import dualmic_upstream_d7_build as b

REASONS = {
    "raw_left": "D7_RAW_LEFT", "raw_right": "D7_RAW_RIGHT",
    "hpf_left": "D7_HPF_LEFT", "hpf_right": "D7_HPF_RIGHT", "bf_output": "D7_BF_OUTPUT",
    "hpf_state_before": "D7_HPF_STATE_BEFORE", "hpf_state_after": "D7_HPF_STATE_AFTER",
    "hpf_channel_order": "D7_HPF_CHANNEL_ORDER", "bf_state_before": "D7_BF_STATE_BEFORE",
    "bf_state_after": "D7_BF_STATE_AFTER", "bf_history": "D7_BF_HISTORY",
    "bf_lag_scores": "D7_BF_LAG_SCORES", "bf_lag": "D7_BF_LAG",
    "effective_lag": "D7_EFFECTIVE_LAG", "score_updates": "D7_SCORE_UPDATES",
    "fallback_route": "D7_FALLBACK_ROUTE", "track_direction": "D7_TRACK_DIRECTION",
    "trace_geometry": "D7_TRACE_GEOMETRY", "reset_coordinate": "D7_RESET_COORDINATE",
    "spurious_path_reset": "D7_SPURIOUS_PATH_RESET",
    "old_PCM": "D7_OLD_PCM", "old_metrics_JSONL": "D7_OLD_METRICS_JSONL",
    "old_D1_lane": "D7_OLD_D1_LANE", "old_control": "D7_OLD_CONTROL",
    "wrong_window": "D7_WRONG_WINDOW", "missing_case": "D7_MISSING_CASE",
    "null_to_zero": "D7_NULL_TO_ZERO", "near_schedule": "D7_NEAR_SCHEDULE",
    "association_count": "D7_ASSOCIATION_COUNT", "source_tree": "D7_SOURCE_TREE",
    "report_source": "D7_REPORT_SOURCE", "source_resealed": "D7_SOURCE_RESEALED",
    "transform_body_change": "D7_TRANSFORM_BODY", "observer_entry_change": "D7_OBSERVER_ENTRY",
    "header_resealed": "D7_HEADER_RESEALED", "compiler_identity": "D7_COMPILER_IDENTITY",
    "argv": "D7_ARGV", "execution_argv": "D7_EXECUTION_ARGV",
    "source_extra_file": "D7_SOURCE_CLOSURE", "source_extra_dir": "D7_SOURCE_CLOSURE",
    "extra_file": "D7_OUTPUT_CLOSURE", "extra_dir": "D7_OUTPUT_CLOSURE",
    "output_symlink": "D7_OUTPUT_SYMLINK",
    "failed_build_phase": "D7_FAILED_PHASE:plain-build",
    "failed_run_phase": "D7_FAILED_PHASE:run",
    "failed_analysis_phase": "D7_FAILED_PHASE:analysis",
    "failed_verify_phase": "D7_FAILED_PHASE:verify",
    "failed_command": "D7_FAILED_COMMAND", "saved_admission": "D7_SAVED_ADMISSION",
    "input_binding": "D7_INPUT_BINDING", "readback_receipt": "D7_READBACK_RECEIPT",
}

def encode(value):
    return (json.dumps(value, sort_keys=True, allow_nan=False) + "\n").encode()

def change_json(raw, operation):
    value = json.loads(raw)
    operation(value)
    return encode(value)

def change_word(raw, offset, value, fmt="<f"):
    result = bytearray(raw)
    struct.pack_into(fmt, result, offset, value)
    return bytes(result)

def changed_byte(raw):
    value = bytearray(raw)
    value[0] ^= 1
    return bytes(value)

@contextlib.contextmanager
def output_at(root):
    original = d7.OUTPUT
    d7.OUTPUT = root
    try:
        yield
    finally:
        d7.OUTPUT = original

def engineering_flags(parent_phase):
    """Synthetic parser fixtures, not observed compiler argv or acoustic evidence."""
    root = parent_phase.logs / "flags-probes"
    root.mkdir()
    definitions = [
        "-DAP_BUILD_ACTIVITY=1", "-DAP_BUILD_AEC_MDF=1", "-DAP_BUILD_BF_DIRECTION_TRACKING=1",
        "-DAP_BUILD_NS_EMA=1", "-DAP_BUILD_RESAMPLER_BANDLIMITED=1", "-DAP_BUILD_STAGE_AEC=1",
        "-DAP_BUILD_STAGE_AGC=1", "-DAP_BUILD_STAGE_BF=1", "-DAP_BUILD_STAGE_HPF=1",
        "-DAP_BUILD_STAGE_NS=1", "-DAP_BUILD_STAGE_RES=1", "-DAP_BUILD_STAGE_SYNC=1",
        "-DAP_BUILD_STAGE_VAD=1"]
    sequences = [
        ["-O3", "-DNDEBUG", "-Wall", "-Wextra", "-Wpedantic", "-Werror", "-std=c11"],
        ["-O3", "-DNDEBUG", "-std=c11", "-Wall", "-Wextra", "-Wpedantic", "-Werror"]]
    records = []
    last_error = None

    def exercise(label, sequence, category=None, mutate=None, raw_change=None):
        nonlocal last_error
        parent_phase.remaining()
        build = root / label / "plain-build"
        source = build.parent / "plain-source"
        path = build / "CMakeFiles/audio_pipeline.dir/flags.make"
        path.parent.mkdir(parents=True)
        value = {"C_DEFINES": list(definitions), "C_FLAGS": list(sequence),
                 "C_INCLUDES": ["-I" + str(build / "generated"), "-I" + str(source / "include"),
                                "-I" + str(source / "src")]}
        if mutate is not None:
            mutate(value)
        text = "".join(key + " = " + " ".join(value[key]) + "\n"
                       for key in ("C_DEFINES", "C_INCLUDES", "C_FLAGS"))
        if raw_change is not None:
            text = raw_change(text)
        path.write_text(text)
        try:
            actual = b.flags(build)
        except ValueError as error:
            b.need(category is not None and str(error) == "D7_BUILD_FLAGS" and
                   error.d7_build_flags["category"] == category, "D7_ENGINEERING_FLAGS_REASON")
            b.need(error.d7_build_flags["target"] == str(path) and
                   len(json.dumps(error.d7_build_flags, ensure_ascii=True)) <= 8192,
                   "D7_ENGINEERING_FLAGS_DIAGNOSTIC")
            last_error = error
            outcome = {"expected_reason": "D7_BUILD_FLAGS", "category": category,
                       "diagnostic": error.d7_build_flags}
        else:
            b.need(category is None and actual == value, "D7_ENGINEERING_FLAGS_ACCEPTANCE")
            outcome = {"actual_tokens_preserved": True, "expected": value}
        records.append({"label": label, "scope": "synthetic parser fixture",
                        "file": path.relative_to(root).as_posix(), **b.desc(path), **outcome})
        parent_phase.remaining()

    for n, sequence in enumerate(sequences):
        prefix = str(n) + "-"
        exercise(prefix + "accepted", sequence)
        for i in range(7):
            exercise(prefix + "missing-" + str(i), sequence[:i] + sequence[i+1:], "flags")
            exercise(prefix + "duplicate-" + str(i), sequence + [sequence[i]], "flags")
        for i, extra in enumerate(("-funexpected", "-ffast-math", "-O2", "-std=gnu11", "-Wno-error")):
            exercise(prefix + "extra-" + str(i), sequence + [extra], "flags")
        for before, after in (("-O3", "-O2"), ("-std=c11", "-std=gnu11"), ("-Werror", "-Wno-error")):
            exercise(prefix + "replace-" + before[1:], [after if v == before else v for v in sequence], "flags")
        exercise(prefix + "wrong-order", [sequence[1], sequence[0], *sequence[2:]], "flags")
    for field, category, count in (("C_DEFINES", "defines", 13), ("C_INCLUDES", "includes", 3)):
        for i in range(count):
            exercise(field + "-missing-" + str(i), sequences[0], category,
                     mutate=lambda v, field=field, i=i: v[field].pop(i))
            exercise(field + "-duplicate-" + str(i), sequences[0], category,
                     mutate=lambda v, field=field, i=i: v[field].append(v[field][i]))
            exercise(field + "-replace-" + str(i), sequences[0], category,
                     mutate=lambda v, field=field, i=i: v[field].__setitem__(i, v[field][i] + "-unexpected"))
        exercise(field + "-extra", sequences[0], category,
                 mutate=lambda v, field=field: v[field].append("-unexpected"))
    exercise("include-order", sequences[0], "includes",
             mutate=lambda v: v["C_INCLUDES"].reverse())
    for field in ("C_DEFINES", "C_INCLUDES", "C_FLAGS"):
        exercise(field + "-missing-assignment", sequences[0], "parse",
                 raw_change=lambda text, field=field: "\n".join(
                     line for line in text.splitlines() if not line.startswith(field + " =")))
        exercise(field + "-duplicate-assignment", sequences[0], "parse",
                 raw_change=lambda text, field=field: text + field + " =\n")
    exercise("unclosed-quote", sequences[0], "parse", raw_change=lambda text: text.replace("C_FLAGS =", "C_FLAGS = '", 1))
    exercise("bounded-diagnostic", sequences[0] + ["x" * 10000], "flags")
    b.need(last_error.d7_build_flags.get("detail_truncated") is True, "D7_ENGINEERING_FLAGS_DIAGNOSTIC")
    probe = b.Phase("flags-failure-probe", root=root)
    probe.path = root / "not-a-run-receipt.json"
    probe._remember_failure(last_error, "body")
    first = copy.deepcopy(probe.report["first_failure"])
    second = ValueError("later failure")
    probe._remember_failure(second, "terminal")
    b.need(probe.report["first_failure"] == first == second.d7_first_failure and
           first["reason"] == "D7_BUILD_FLAGS" and "build_flags" in first, "D7_ENGINEERING_FIRST_FAILURE")
    result = {"status": "PASS", "scope": "synthetic flags parser/first-failure tests; no compiler execution",
              "accepted_sequences": 2, "rejected_fixtures": len(records) - 2,
              "first_failure_preserved": True, "fixtures": records}
    b.need(len(records) == 107, "D7_ENGINEERING_FLAGS_COUNT")
    b.dump(root / "receipt.json", result)
    parent_phase.remaining()
    return result

def engineering_generated(parent_phase, identity):
    """Synthetic exact Unity/dependency fixtures; never compiled or DSP input."""
    root = parent_phase.logs / "generated-probes"
    source, build = root / "plain-source", root / "plain-build"
    cases = root / "cases"
    cases.mkdir(parents=True)
    source.mkdir()
    build.mkdir()
    # Independent fixture source order, checked against the source-bound guard.
    names = (
        "src/ap_build_info.c", "src/core/ap_pipeline.c", "src/core/ap_pipeline_query.c",
        "src/frontend/ap_resampler.c", "src/frontend/ap_hpf.c", "src/frontend/ap_beamformer.c",
        "src/sync/ap_sync.c", "src/activity/ap_activity.c", "src/enhance/ap_res.c",
        "src/enhance/ap_ns.c", "src/enhance/ap_noise_tracker.c", "src/enhance/ap_window.c",
        "src/enhance/ap_agc.c", "src/enhance/ap_vad.c", "src/aec/ap_aec_mdf.c",
        "src/arch/scalar/ap_kernels_scalar.c", "src/dsp/ap_fft.c")
    for name in (*names, "examples/process_pcm.c", "tests/validation/frontend_evolution/dualmic_stages_d1.c"):
        path = source / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("synthetic path fixture; not production source\n")
    path = build / "CMakeFiles/audio_pipeline.dir/Unity/unity_0_c.c"
    path.parent.mkdir(parents=True)
    comments = ("", "/* NOLINTNEXTLINE(bugprone-suspicious-include,misc-include-cleaner) */\n")
    def document(comment, sequence=names):
        return ("/* generated by CMake */\n\n" + "".join(
            comment + '#include "' + str(source / name) + '"\n\n' for name in sequence)).encode()
    records = []
    first_error = None

    def expect(label, action, reason=None):
        nonlocal first_error
        parent_phase.remaining()
        try:
            result = action()
        except ValueError as error:
            b.need(reason is not None and str(error) == reason, "D7_ENGINEERING_GENERATED_REASON")
            if hasattr(error, "d7_generated") and first_error is None:
                first_error = error
            result = {"expected_reason": reason, "observed_reason": str(error),
                      "detail": getattr(error, "d7_generated", None)}
        else:
            b.need(reason is None, "D7_ENGINEERING_GENERATED_ACCEPTED")
        records.append({"label": label, "scope": "synthetic fixture", "result": result})
        parent_phase.remaining()

    def unity(label, raw, reason=None):
        saved = cases / (label + ".c.txt")
        saved.write_bytes(raw)
        path.write_bytes(raw)
        expect(label, lambda: b.generated_unity(path, source, identity), reason)
        records[-1]["fixture"] = {"path": saved.relative_to(root).as_posix(), **b.desc(saved)}

    for form, comment in enumerate(comments):
        prefix = "unity-" + str(form) + "-"
        good = document(comment)
        unity(prefix + "valid", good)
        for i in range(len(names)):
            unity(prefix + "missing-" + str(i), document(comment, names[:i] + names[i+1:]), "D7_GENERATED_UNITY")
            unity(prefix + "duplicate-" + str(i), document(comment, names + (names[i],)), "D7_GENERATED_UNITY")
        unity(prefix + "reordered", document(comment, names[::-1]), "D7_GENERATED_UNITY")
        for i, suffix in enumerate((b"int injected;\n", b"#define injected 1\n", b"/* arbitrary comment */\n",
                                    b'#include "/tmp/outside.c"\n')):
            unity(prefix + "extra-" + str(i), good + suffix, "D7_GENERATED_UNITY")
        unity(prefix + "unknown-source", document(comment, names[:-1] + ("src/unknown.c",)), "D7_GENERATED_UNITY")
        unity(prefix + "helper-source", document(comment, names[:-1] +
              ("tests/validation/frontend_evolution/dualmic_stages_d1.c",)), "D7_GENERATED_UNITY")
        unity(prefix + "parent-path", good.replace(b"/src/ap_build_info.c", b"/src/../src/ap_build_info.c"),
              "D7_GENERATED_UNITY")
        unity(prefix + "bom", b"\xef\xbb\xbf" + good, "D7_GENERATED_UNITY")
        unity(prefix + "crlf", good.replace(b"\n", b"\r\n"), "D7_GENERATED_UNITY")
    good = document(comments[1])
    unity("unity-mixed-comment", good.replace(comments[1].encode(), b"", 1), "D7_GENERATED_UNITY")
    unity("unity-wrong-comment", good.replace(b"misc-include-cleaner", b"other-check"), "D7_GENERATED_UNITY")
    path.write_bytes(good)
    header = build / "generated/audio_pipeline/audio_pipeline_build.h"
    header.parent.mkdir(parents=True)
    header.write_text("synthetic generated path fixture\n")
    extra = source / "undeclared.h"
    extra.write_text("not an identity member\n")
    unexpected = build / "unexpected.h"
    unexpected.write_text("not a generated member\n")
    outside = root / "outside.h"
    outside.write_text("outside source/build/system roots\n")
    system = root / "system"
    system.mkdir()
    (system / "stddef.h").write_text("synthetic system path fixture\n")
    roots = [{"raw": str(system), "canonical": str(system)}]
    def dep(raw, cwd=build):
        return b.dependency_path(str(raw), source, build, identity, roots, cwd)
    for label, raw in (
        ("dep-source", source / names[0]),
        ("dep-intra-root", source / "tests/validation/frontend_evolution/../../../examples/process_pcm.c"),
        ("dep-generated", header),
        ("dep-generated-normalized", build / "generated/audio_pipeline/../audio_pipeline/audio_pipeline_build.h"),
        ("dep-unity", path), ("dep-system", system / "stddef.h")):
        expect(label, lambda raw=raw: dep(raw))
        b.need(records[-1]["result"]["raw"] == str(raw), "D7_ENGINEERING_GENERATED_RAW")
    expect("dep-relative", lambda: dep("src/ap_build_info.c", source))
    for label, raw, reason in (
        ("dep-escape", source / "../outside.h", "D7_DEPENDENCY_ESCAPE"),
        ("dep-exit-reenter", source / "../plain-source/src/ap_build_info.c", "D7_DEPENDENCY_ESCAPE"),
        ("dep-unknown-source", extra, "D7_COMPILED_SOURCE_CLOSURE"),
        ("dep-unknown-generated", unexpected, "D7_GENERATED_HEADER_CLOSURE"),
        ("dep-missing", source / "missing.h", "D7_DEPENDENCY_REGULAR"),
        ("dep-directory", source / "src", "D7_DEPENDENCY_REGULAR"),
        ("dep-outside", outside, "D7_DEPENDENCY_OUTSIDE")):
        expect(label, lambda raw=raw: dep(raw), reason)
    for label, target, tail in (
        ("dep-symlink-file", source / names[0], ""),
        ("dep-symlink-dir", source / "src", "/ap_build_info.c"),
        ("dep-symlink-dotdot", source / "src", "/../src/ap_build_info.c"),
        ("dep-symlink-outside", outside, "")):
        link = source / "alias"
        link.symlink_to(target)
        try:
            expect(label, lambda: dep(str(link) + tail), "D7_DEPENDENCY_SYMLINK")
            records[-1]["symlink"] = {"path": str(link), "target": str(target), "removed_after_probe": True}
        finally:
            link.unlink()
    # Query parser controls use the already observed roots as the valid fixture,
    # not guessed system paths. They do not execute a second compiler query.
    observed_roots = b.system_roots()
    start, end = "#include <...> search starts here:", "End of search list."
    root_lines = "".join(" " + row["raw"] + "\n" for row in observed_roots)
    valid_search = start + "\n" + root_lines + end + "\n"
    search_cases = [
        ("search-valid", valid_search, None),
        ("search-missing-start", root_lines + end + "\n", "D7_COMPILER_SEARCH"),
        ("search-missing-end", start + "\n" + root_lines, "D7_COMPILER_SEARCH"),
        ("search-duplicate-start", start + "\n" + valid_search, "D7_COMPILER_SEARCH"),
        ("search-duplicate-end", valid_search + end + "\n", "D7_COMPILER_SEARCH"),
        ("search-reversed", end + "\n" + start + "\n" + root_lines, "D7_COMPILER_SEARCH"),
        ("search-empty", start + "\n" + end + "\n", "D7_COMPILER_SEARCH"),
        ("search-no-indent", start + "\n" + root_lines.lstrip() + end + "\n", "D7_COMPILER_SEARCH"),
        ("search-relative", start + "\n relative\n" + end + "\n", "D7_COMPILER_SEARCH"),
        ("search-missing-dir", start + "\n " + str(root / "absent") + "\n" + end + "\n", "D7_COMPILER_SEARCH"),
        ("search-outside-usr", start + "\n " + str(root) + "\n" + end + "\n", "D7_COMPILER_SEARCH"),
        ("search-duplicate-root", start + "\n" + root_lines + root_lines + end + "\n", "D7_COMPILER_SEARCH"),
        ("search-not-directory", start + "\n " + str(outside) + "\n" + end + "\n", "D7_COMPILER_SEARCH"),
        ("search-entire-usr", start + "\n /usr\n" + end + "\n", "D7_COMPILER_SEARCH"),
        ("search-malformed-root", start + "\n " + observed_roots[0]["raw"] + " (unexpected)\n" + end + "\n",
         "D7_COMPILER_SEARCH")]
    search_records = []
    for label, text, reason in search_cases:
        saved = cases / (label + ".txt")
        saved.write_text(text)
        expect(label, lambda saved=saved: b.compiler_search_roots(saved.read_text()), reason)
        row = records.pop()
        row["fixture"] = {"path": saved.relative_to(root).as_posix(), **b.desc(saved)}
        if reason is None:
            b.need(row["result"] == observed_roots, "D7_ENGINEERING_GENERATED_SEARCH")
        search_records.append(row)
    b.need(len(search_records) == 15, "D7_ENGINEERING_GENERATED_COUNT")
    # The original diagnostic remains the first error even after another one.
    probe = b.Phase("generated-failure-probe", root=root)
    probe.path = root / "not-a-run-receipt.json"
    probe._remember_failure(first_error, "body")
    first = copy.deepcopy(probe.report["first_failure"])
    later = ValueError("later failure")
    probe._remember_failure(later, "terminal")
    b.need(first == probe.report["first_failure"] == later.d7_first_failure and
           first["reason"] == "D7_GENERATED_UNITY" and "generated" in first,
           "D7_ENGINEERING_FIRST_FAILURE")
    b.need(len(records) == 110, "D7_ENGINEERING_GENERATED_COUNT")
    result = {"status": "PASS", "scope": "synthetic Unity/dependency parser fixtures; never compiled",
              "fixture_count": len(records), "compiler_search_fixture_count": len(search_records),
              "compiler_search_fixtures": search_records,
              "first_failure_preserved": True, "fixtures": records}
    b.dump(root / "receipt.json", result)
    parent_phase.remaining()
    return result

def engineering_export():
    """In-memory transport controls only; no DSP/scoring/files or result claims."""
    records = []
    def reject(label, reason, action):
        try:
            action()
        except ValueError as error:
            b.need(str(error) == reason, "D7_EXPORT_TEST_REASON")
        else:
            raise ValueError("D7_EXPORT_TEST_ACCEPTED")
        records.append({"label": label, "expected_reason": reason})
    fixture = {"key": "second", "stages": {"x": {"common": {"near_si_sdr_db": None,
               "near_si_sdr_null_reason": "fixture"}, "one_second_windows": [{"value": -0.25}]}},
               "whole_association": {"frames": 2}, "common_association": {"frames": 1},
               "window_associations": [{"physical_sample_range": [0, 160]}],
               "frame_associations": [{"omitted": True}], "original_D1_stages": {"omitted": True}}
    before = copy.deepcopy(fixture)
    projected = d7.export_case(fixture)
    b.need(projected == {key: value for key, value in fixture.items()
                        if key not in ("frame_associations", "original_D1_stages")} and fixture == before and
           projected["stages"] is fixture["stages"] and projected["window_associations"] is fixture["window_associations"],
           "D7_EXPORT_TEST_PROJECTION")
    ordered = [d7.export_case(fixture), d7.export_case({**fixture, "key": "first"})]
    b.need([row["key"] for row in ordered] == ["second", "first"], "D7_EXPORT_TEST_ORDER")
    value = {"unicode": "中文", "null": None, "negative": -0.25, "ordered": ordered}
    raw = d7.encode_export(value)
    b.need(json.loads(raw) == value and d7.encode_export(json.loads(raw)) == raw, "D7_EXPORT_TEST_JSON")
    b.need(d7.encode_export(value, limit=len(raw)) == raw, "D7_EXPORT_TEST_BOUNDARY")
    reject("over-bound", "D7_EXPORT_BYTES_BOUND", lambda: d7.encode_export(value, limit=len(raw)-1))
    for label, number in (("nan", float("nan")), ("positive-infinity", float("inf")), ("negative-infinity", -float("inf"))):
        reject(label, "D7_EXPORT_JSON", lambda number=number: d7.encode_export({"value": number}))
    for size in (1, d7.EXPORT_CHUNK_BYTES-1, d7.EXPORT_CHUNK_BYTES, d7.EXPORT_CHUNK_BYTES+1,
                 2*d7.EXPORT_CHUNK_BYTES):
        data = b"x" * size
        manifest, chunks = d7.export_chunks(data)
        b.need(d7.decode_export(manifest, chunks, manifest) == data and
               all(set(row) == {"index", "base64"} for row in chunks), "D7_EXPORT_TEST_ROUNDTRIP")
    data = b"x" * (d7.EXPORT_CHUNK_BYTES + 1)
    manifest, chunks = d7.export_chunks(data)
    reject("missing-end", "D7_EXPORT_END", lambda: d7.decode_export(manifest, chunks, None))
    reject("wrong-end", "D7_EXPORT_END", lambda: d7.decode_export(manifest, chunks, {**manifest, "sha256": "0"*64}))
    reject("missing-chunk", "D7_EXPORT_CHUNKS", lambda: d7.decode_export(manifest, chunks[:-1], manifest))
    reject("extra-chunk", "D7_EXPORT_CHUNKS", lambda: d7.decode_export(manifest, chunks + [chunks[-1]], manifest))
    reject("duplicate-index", "D7_EXPORT_ORDER", lambda: d7.decode_export(manifest, [chunks[0], chunks[0]], manifest))
    reject("reordered", "D7_EXPORT_ORDER", lambda: d7.decode_export(manifest, chunks[::-1], manifest))
    reject("invalid-base64", "D7_EXPORT_BASE64",
           lambda: d7.decode_export(manifest, [{**chunks[0], "base64": "!"}, chunks[1]], manifest))
    changed = [{**chunks[0], "base64": ("A" if chunks[0]["base64"][0] != "A" else "B") + chunks[0]["base64"][1:]}, chunks[1]]
    reject("digest-mismatch", "D7_EXPORT_DIGEST", lambda: d7.decode_export(manifest, changed, manifest))
    wrong_bytes = {**manifest, "raw_bytes": manifest["raw_bytes"] + 1}
    reject("byte-mismatch", "D7_EXPORT_CHUNKS", lambda: d7.decode_export(wrong_bytes, chunks, wrong_bytes))
    wrong_count = {**manifest, "chunk_count": manifest["chunk_count"] + 1}
    reject("count-mismatch", "D7_EXPORT_CHUNKS", lambda: d7.decode_export(wrong_count, chunks, wrong_count))
    b.need(len(records) == 14, "D7_EXPORT_TEST_COUNT")
    return {"status": "PASS", "scope": "synthetic in-memory transport, not independent binary audit",
            "raw_byte_limit": d7.EXPORT_LIMIT, "chunk_bytes": d7.EXPORT_CHUNK_BYTES,
            "positive_checks": ["unchanged projection/nulls", "case order", "finite canonical JSON",
                                "exact byte limit", "five chunk boundary roundtrips"],
            "rejections": records}


def engineering_supervisor(parent_phase):
    """Actual child timeout with <1s remaining, plus preserved first failure."""
    root = parent_phase.logs / "supervisor-probes"
    root.mkdir()
    probe = b.Phase("bounded-probe", root=root)
    probe.logs = root / "logs"
    probe.logs.mkdir()
    probe.started = time.monotonic() - 299.8
    began = time.monotonic()
    try:
        probe.run("deadline", [sys.executable, "-c", "import time; time.sleep(2)"])
    except TimeoutError as error:
        b.need(str(error) == "D7_COMMAND_TIMEOUT", "D7_ENGINEERING_TIMEOUT_REASON")
    else:
        raise ValueError("D7_ENGINEERING_TIMEOUT_NOT_ENFORCED")
    first = copy.deepcopy(probe.report["first_failure"])
    receipt = b.read(probe.logs / "deadline.command.json")
    b.need(receipt["status"] == "FAIL" and receipt["lifecycle"] == "PENDING" and
           0 < receipt["timeout_seconds"] <= 0.21 and time.monotonic() - began < 2 and
           first["reason"] == "D7_COMMAND_TIMEOUT", "D7_ENGINEERING_TIMEOUT_RECEIPT")
    probe.started = time.monotonic()
    try:
        probe.run("second-failure", [sys.executable, "-c", "raise SystemExit(7)"])
    except ValueError as error:
        b.need(str(error) == "D7_COMMAND_EXIT", "D7_ENGINEERING_EXIT_REASON")
    else:
        raise ValueError("D7_ENGINEERING_EXIT_NOT_ENFORCED")
    b.need(probe.report["first_failure"] == first, "D7_ENGINEERING_FIRST_FAILURE")
    result = {"status": "PASS", "actual_timeout": receipt["timeout_seconds"],
              "first_failure_preserved": True, "expired_receipt_not_rewritten": True, "expected_failed_commands": 2}
    b.dump(root / "receipt.json", result)
    parent_phase.remaining()
    return result

def actual_negatives(phase):
    need = b.need
    need(set(REASONS) == set(b.contract()["test_contract"]["actual_negative_categories"]),
         "D7_NEGATIVE_CATEGORY_SET")
    # Full unchanged original/source/build/waveform/state/scorer/readback once.
    b.check_phase(b.OUTPUT, "verify")
    qualified = d7.verify(phase)
    d7.check_readback(b.read(b.OUTPUT / "readback.json"))
    built = b.read(b.OUTPUT / "build/build.json")
    cases = d7.catalogs()
    case = cases[0]
    directory, original, _, old_taps = d7.paths(case)
    signals = {name: d7.d1.samples(directory / "upstream" / (name + ".f32le"), "f", case["samples"])
               for name in d7.LANES}
    stereo = d7.d1.samples(original / case["inputs"]["mic"], "h", 2 * case["samples"])
    trace = (directory / "upstream/state.bin").read_bytes()
    control = list(csv.DictReader(io.StringIO((directory / "d1/control.csv").read_text())))
    records = []
    evidence = phase.logs / "mutations"
    evidence.mkdir()

    def expect(category, action):
        phase.remaining()
        started = time.monotonic()
        try:
            action()
        except ValueError as error:
            need(str(error) == REASONS[category], "D7_NEGATIVE_WRONG_REASON:" + category + ":" + str(error))
        else:
            raise ValueError("D7_NEGATIVE_ACCEPTED:" + category)
        phase.remaining()
        return time.monotonic() - started

    def exercise(category, raw, mutate, guard, origin):
        root = evidence / category
        root.mkdir()
        pristine, corrupted = root / "pristine", root / "mutant"
        pristine.write_bytes(raw)
        guard(pristine)  # Each targeted guard must accept the untouched same slice.
        new = mutate(raw)
        need(new != raw, "D7_NEGATIVE_NO_MUTATION")
        corrupted.write_bytes(new)
        elapsed = expect(category, lambda: guard(corrupted))
        records.append({"category": category, "status": "PASS", "expected_reason": REASONS[category],
            "observed_reason": REASONS[category], "origin": origin,
            "pristine": b.desc(pristine), "mutant": b.desc(corrupted),
            "elapsed_seconds": elapsed, "untouched_guard_passed": True})

    def trace_guard(path):
        d7.frame_trace(case, signals, path.read_bytes(), control)

    for channel, category in enumerate(("raw_left", "raw_right")):
        lane = d7.LANES[channel]
        raw = (directory / "upstream" / (lane + ".f32le")).read_bytes()
        def guard(p, lane=lane):
            copied = dict(signals)
            copied[lane] = d7.d1.samples(p, "f", case["samples"])
            d7.check_raw(copied, stereo)
        exercise(category, raw, changed_byte, guard, case["key"] + "/upstream/" + lane)

    for channel, category in enumerate(("hpf_left", "hpf_right")):
        lane = d7.LANES[channel + 2]
        raw = (directory / "upstream" / (lane + ".f32le")).read_bytes()
        def guard(p, lane=lane):
            copied = dict(signals)
            copied[lane] = d7.d1.samples(p, "f", case["samples"])
            d7.frame_trace(case, copied, trace, control)
        exercise(category, raw, lambda raw: change_word(raw, 0, 0.125), guard,
                 case["key"] + "/upstream/" + lane)
    exercise("bf_output", (directory / "upstream/bf_output.f32le").read_bytes(), changed_byte,
             lambda p: d7.compare_bytes(p.read_bytes(), (directory / "d1/ns_input.f32le").read_bytes(), "BF_OUTPUT"),
             case["key"] + "/upstream/bf_output.f32le")

    transforms = {
        "hpf_state_before": lambda raw: change_word(raw, 16 + 4, 0.125),
        "hpf_state_after": lambda raw: change_word(change_word(raw, 40 + 4, 0.125), 64 + 4, 0.125),
        "hpf_channel_order": lambda raw: change_word(raw, 64 + 4, 0.125),
        "bf_state_before": lambda raw: change_word(raw, 112, 0.125),
        "bf_state_after": lambda raw: change_word(raw, 292 + 176, 99, "<I"),
        "bf_history": lambda raw: change_word(raw, 292, 0.125),
        "bf_lag_scores": lambda raw: change_word(raw, 292 + 64, 0.125),
        "bf_lag": lambda raw: change_word(raw, 292 + 136, 4, "<i"),
        "score_updates": lambda raw: change_word(raw, 292 + 152, 99, "<I"),
        "fallback_route": lambda raw: change_word(raw, 292 + 156, 2, "<I"),
        "track_direction": lambda raw: change_word(raw, 4, 2, "<i"),
        "trace_geometry": lambda raw: raw[:-1],
    }
    for category, mutate in transforms.items():
        exercise(category, trace, mutate, trace_guard, case["key"] + "/upstream/state.bin")

    reset_case = next(c for c in cases if any(e["kind"] == "cli_discontinuity" for e in c["input_events"]))
    exercise("reset_coordinate", encode(reset_case),
        lambda raw: change_json(raw, lambda v: v["input_events"][0].__setitem__("frame", 301)),
        lambda p: d7.check_events(b.read(p)), reset_case["key"] + "/input_events")
    path_case = next(c for c in cases if any(e["kind"] == "cli_echo_path_change" for e in c["input_events"]))
    path_dir = d7.paths(path_case)[0]
    path_signals = {n: d7.d1.samples(path_dir / "upstream" / (n + ".f32le"), "f", path_case["samples"])
                    for n in d7.LANES}
    path_control = list(csv.DictReader(io.StringIO((path_dir / "d1/control.csv").read_text())))
    def reset_upstream(raw):
        mutated = bytearray(raw)
        h, bf = d7.initial_states()
        mutated[300 * d7.RECORD + 16:300 * d7.RECORD + 40] = h
        mutated[300 * d7.RECORD + 112:300 * d7.RECORD + 292] = bf
        return bytes(mutated)
    exercise("spurious_path_reset", (path_dir / "upstream/state.bin").read_bytes(), reset_upstream,
        lambda p: d7.frame_trace(path_case, path_signals, p.read_bytes(), path_control),
        path_case["key"] + "/upstream/state.bin")

    for category, relative, expected, reason in (
        ("old_PCM", "observer/out.pcm", d7.paths(case)[2] / "out.pcm", "OLD_PCM"),
        ("old_metrics_JSONL", "observer/metrics.jsonl", d7.paths(case)[2] / "metrics.jsonl", "OLD_METRICS_JSONL"),
        ("old_D1_lane", "d1/agc_output.f32le", old_taps / "agc_output.f32le", "OLD_D1_LANE"),
        ("old_control", "d1/control.csv", old_taps / "control.csv", "OLD_CONTROL")):
        exercise(category, (directory / relative).read_bytes(), changed_byte,
            lambda p, expected=expected, reason=reason: d7.compare_bytes(p.read_bytes(), expected.read_bytes(), reason),
            case["key"] + "/" + relative)

    saved_case = qualified["cases"][0]
    saved_raw = encode(saved_case)
    changes = {
        "effective_lag": lambda v: v["frame_associations"][0].__setitem__("effective_output_lag", 99),
        "wrong_window": lambda v: v["stages"]["bf_output"]["common"]["physical_sample_range"].__setitem__(0, 1),
        "near_schedule": lambda v: v["frame_associations"][0].__setitem__("scheduled_near", "scheduled_present"),
        "association_count": lambda v: v["whole_association"].__setitem__("frames", 599),
    }
    for category, change in changes.items():
        exercise(category, saved_raw, lambda raw, change=change: change_json(raw, change),
                 lambda p: d7.check_saved_case(case, saved_case, b.read(p)), "report.json#cases/0")

    null_index = next(i for i, c in enumerate(cases) if c["inputs"]["clean_near"] is None)
    null_case = cases[null_index]
    exercise("null_to_zero", encode(qualified["cases"][null_index]["stages"]),
        lambda raw: change_json(raw, lambda v: v["bf_output"]["common"].__setitem__("near_si_sdr_db", 0)),
        lambda p: d7.score_shape(null_case, b.read(p)), "report.json#null-case-stages")

    header = {"source": qualified["source"], "cases": [{"key": c["key"]} for c in cases]}
    for category, change in (
        ("missing_case", lambda v: v["cases"].pop()),
        ("report_source", lambda v: v["source"].__setitem__("revision", "0" * 40))):
        exercise(category, encode(header), lambda raw, change=change: change_json(raw, change),
                 lambda p: d7.check_report_identity(b.read(p), built), "report.json#identity")
    exercise("source_tree", encode(built["source"]),
        lambda raw: change_json(raw, lambda v: v.__setitem__("tree", "0" * 40)),
        lambda p: b.check_source_identity(b.read(p), built["source"]), "build/build.json#source")
    exercise("compiler_identity", encode({"compiler": built["compiler"], "cmake": built["cmake"]}),
        lambda raw: change_json(raw, lambda v: v["compiler"]["file"].__setitem__("sha256", "0" * 64)),
        lambda p: b.check_compiler_identity(b.read(p)["compiler"], b.read(p)["cmake"]), "build/build.json#compiler")

    # Small isolated source copies, never edits to checkout or original evidence.
    for category in ("source_resealed", "transform_body_change", "observer_entry_change",
                     "source_extra_file", "source_extra_dir"):
        root = evidence / category
        root.mkdir()
        for kind in ("plain", "observer"):
            shutil.copytree(b.OUTPUT / "build" / (kind + "-source"), root / (kind + "-source"))
        b.check_sources(root, built["source"])
        if category == "source_extra_file":
            target = root / "plain-source/undeclared.txt"
            target.write_text("extra\n")
        elif category == "source_extra_dir":
            target = root / "plain-source/undeclared"
            target.mkdir()
        else:
            kind = "plain" if category == "source_resealed" else "observer"
            path = "tests/validation/frontend_evolution/dualmic_stages_d1.c" if category == "observer_entry_change" else "src/frontend/ap_hpf.c"
            target = root / (kind + "-source") / path
            raw = target.read_bytes()
            if category == "observer_entry_change":
                changed = raw.replace(b"int ap_d7_d1_main(", b"int ap_d7_bad_main(", 1)
            else:
                changed = raw.replace(b"const float y = in - px + s->r * py;", b"const float y = in - px;", 1)
            need(changed != raw, "D7_NEGATIVE_NO_MUTATION")
            target.write_bytes(changed)
            if category == "source_resealed":
                # A self-resealed descriptor does not replace immutable Git authority.
                b.dump(root / "self-resealed-descriptor.json", b.desc(target))
        elapsed = expect(category, lambda root=root: b.check_sources(root, built["source"]))
        records.append({"category": category, "status": "PASS", "expected_reason": REASONS[category],
                        "observed_reason": REASONS[category], "untouched_guard_passed": True,
                        "target": target.relative_to(evidence).as_posix(),
                        "mutant": b.desc(target) if target.is_file() else {"directory": True},
                        "elapsed_seconds": elapsed})
        phase.remaining()

    root = evidence / "header_resealed"
    root.mkdir()
    (root / "plain-source/cmake").mkdir(parents=True)
    shutil.copyfile(b.OUTPUT / "build/plain-source/cmake/audio_pipeline_build.h.in",
                    root / "plain-source/cmake/audio_pipeline_build.h.in")
    shutil.copyfile(b.OUTPUT / "build/build.json", root / "build.json")
    for kind in ("plain", "observer"):
        target = root / (kind + "-build/generated/audio_pipeline/audio_pipeline_build.h")
        target.parent.mkdir(parents=True)
        shutil.copyfile(b.OUTPUT / "build" / (kind + "-build/generated/audio_pipeline/audio_pipeline_build.h"), target)
    b.check_headers(root, built["source"]["revision"])
    for kind in ("plain", "observer"):
        target = root / (kind + "-build/generated/audio_pipeline/audio_pipeline_build.h")
        target.write_bytes(target.read_bytes().replace(b"AP_BUILD_MAX_MIC_CHANNELS 2", b"AP_BUILD_MAX_MIC_CHANNELS 1"))
    elapsed = expect("header_resealed", lambda: b.check_headers(root, built["source"]["revision"]))
    records.append({"category": "header_resealed", "status": "PASS", "expected_reason": REASONS["header_resealed"],
                    "observed_reason": REASONS["header_resealed"], "untouched_guard_passed": True,
                    "scope": "both headers changed identically; expected frozen-template values still reject",
                    "elapsed_seconds": elapsed})

    configure = b.OUTPUT / "plain-build-logs/configure.command.json"
    execution = b.OUTPUT / "run-logs/000-plain.command.json"
    for category, source, change, expected in (
        ("argv", configure, lambda v: v["argv"].append("-ffast-math"), b.read(configure)["argv"]),
        ("failed_command", configure, lambda v: v.__setitem__("status", "FAIL"), None)):
        root = evidence / category
        root.mkdir()
        receipt = root / "value.command.json"
        for suffix in (".stdout", ".stderr"):
            shutil.copyfile(Path(str(source).removesuffix(".command.json") + suffix), root / ("value" + suffix))
        receipt.write_bytes(source.read_bytes())
        b.check_command(receipt, expected)
        receipt.write_bytes(change_json(receipt.read_bytes(), change))
        elapsed = expect(category, lambda: b.check_command(receipt, expected))
        records.append({"category": category, "status": "PASS", "expected_reason": REASONS[category],
                        "observed_reason": REASONS[category], "untouched_guard_passed": True,
                        "mutant": b.desc(receipt), "elapsed_seconds": elapsed})
    exercise("execution_argv", execution.read_bytes(),
        lambda raw: change_json(raw, lambda v: v["argv"].__setitem__(1, "--capture-only")),
        lambda p: d7.check_execution(b.read(p), case, "plain", built), "run-logs/000-plain.command.json")
    for category, name in (("failed_build_phase", "plain-build"), ("failed_run_phase", "run"),
                           ("failed_analysis_phase", "analysis"), ("failed_verify_phase", "verify")):
        exercise(category, (b.OUTPUT / (name + "-phase.json")).read_bytes(),
            lambda raw: change_json(raw, lambda v: v.__setitem__("status", "FAIL")),
            lambda p, name=name: b.check_phase_record(b.read(p), name), name + "-phase.json")
    exercise("saved_admission", (b.INPUT / "admission.json").read_bytes(),
        lambda raw: change_json(raw, lambda v: v.__setitem__("source_revision", "0" * 40)),
        lambda p: d7.receipt_admission(b.read(p)), "input/admission.json")
    input_binding = b.read(b.OUTPUT / "input-binding.json")
    exercise("input_binding", encode(input_binding),
        lambda raw: change_json(raw, lambda v: v["cases"][0]["inputs"]["mic"].__setitem__("sha256", "0" * 64)),
        lambda p: d7.check_input_binding(input_binding, b.read(p)), "input-binding.json")
    exercise("readback_receipt", (b.OUTPUT / "readback.json").read_bytes(),
        lambda raw: change_json(raw, lambda v: v.__setitem__("status", "FAIL")),
        lambda p: d7.check_readback(b.read(p)), "readback.json")

    # The hard-linked pristine copies are outside the artifact. No existing
    # inode is written; only an added file, directory, or symlink is introduced.
    # Their mutation metadata is retained, not 3 duplicate 400 MiB payloads.
    for category in ("extra_file", "extra_dir", "output_symlink"):
        with tempfile.TemporaryDirectory(prefix="d7-negative-", dir="/tmp/ap-dualmic-d7") as temp:
            root = Path(temp) / "result"
            shutil.copytree(b.OUTPUT, root, copy_function=os.link)
            with output_at(root):
                d7.check_seal()
                target = root / "undeclared"
                if category == "extra_file":
                    target.write_bytes(b"extra\n")
                elif category == "extra_dir":
                    target.mkdir()
                else:
                    target.symlink_to(root / "report.json")
                elapsed = expect(category, d7.check_seal)
            records.append({"category": category, "status": "PASS", "expected_reason": REASONS[category],
                            "observed_reason": REASONS[category], "untouched_guard_passed": True,
                            "mutation": "added " + category + " at result/undeclared",
                            "elapsed_seconds": elapsed})
        phase.remaining()
    need(len(records) == 51 and {r["category"] for r in records} == set(REASONS), "D7_NEGATIVE_CATEGORY_SET")
    # Order is frozen by the lock, even though related guards were tested together.
    order = b.contract()["test_contract"]["actual_negative_categories"]
    by_name = {r["category"]: r for r in records}
    result = {"experiment": b.EXPERIMENT, "status": "PASS", "count": 51,
              "qualification": {"report": b.desc(b.OUTPUT / "report.json"),
                                "seal": b.desc(b.OUTPUT / "seal.json"),
                                "full_unchanged_readback": True},
              "DSP_executed": False, "models_executed": False,
              "canonical_analysis_runs": 1, "targeted_mutations": [by_name[k] for k in order]}
    b.dump(b.OUTPUT / "negative-tests.json", result)
    phase.remaining()
    return result
