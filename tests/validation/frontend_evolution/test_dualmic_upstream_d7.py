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

def engineering_supervisor(parent_phase):
    """Actual child timeout with <1s remaining, plus preserved first failure."""
    root = parent_phase.logs / "supervisor-probes"
    root.mkdir()
    probe = b.Phase("bounded-probe", root=root)
    probe.logs = root / "logs"
    probe.logs.mkdir()
    probe.started = time.monotonic() - 299.8
    try:
        probe.run("deadline", [sys.executable, "-c", "import time; time.sleep(2)"])
    except TimeoutError as error:
        b.need(str(error) == "D7_COMMAND_TIMEOUT", "D7_ENGINEERING_TIMEOUT_REASON")
    else:
        raise ValueError("D7_ENGINEERING_TIMEOUT_NOT_ENFORCED")
    first = copy.deepcopy(probe.report["first_failure"])
    receipt = b.read(probe.logs / "deadline.command.json")
    b.need(receipt["status"] == "FAIL" and receipt["timed_out"] is True and
           0 < receipt["timeout_seconds"] <= 0.21 and
           receipt["elapsed_seconds"] < 2, "D7_ENGINEERING_TIMEOUT_RECEIPT")
    probe.started = time.monotonic()
    try:
        probe.run("second-failure", [sys.executable, "-c", "raise SystemExit(7)"])
    except ValueError as error:
        b.need(str(error) == "D7_COMMAND_EXIT", "D7_ENGINEERING_EXIT_REASON")
    else:
        raise ValueError("D7_ENGINEERING_EXIT_NOT_ENFORCED")
    b.need(probe.report["first_failure"] == first, "D7_ENGINEERING_FIRST_FAILURE")
    result = {"status": "PASS", "actual_timeout": receipt["timeout_seconds"],
              "first_failure_preserved": True, "expected_failed_commands": 2}
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
