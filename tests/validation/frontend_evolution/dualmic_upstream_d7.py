#!/usr/bin/env python3
"""Neutral D7 HPF/BF observation. No candidate, quality gate, or model run."""
from __future__ import annotations
import argparse
from array import array
import copy
import csv
import io
import json
import math
import os
from pathlib import Path
import statistics
import struct
import sys
import time

import dualmic_upstream_d7_build as build
from dualmic_upstream_d7_build import (ROOT, INPUT, OUTPUT, EXPERIMENT, FREEZE, Phase,
    need, read, dump, digest, desc, contract)
d2, d1, admission = build.d2, build.d2.d1, build.admission
LANES = ("hpf_input_l", "hpf_input_r", "hpf_output_l", "hpf_output_r", "bf_output")
BF_NAMES = ("lag", "max_lag", "fallback_lag", "counter", "score_updates",
            "fallback_active", "fallback_strong_channel", "fallback_recovery_count",
            "fallback_hard_fault", "fallback_hard_arm_count", "fixed_health_counter")
HPF = struct.Struct("<5fI")
BF = struct.Struct("<34f3i8I")
HEADER = struct.Struct("<IiII")
RECORD = 472
STATUS = "UPSTREAM_OBSERVATION_VALID_NO_PROMOTION"
OLD = "cc853616685b9faf7880e6d8f8f1a89d187d342a"
FINAL = {"seal.json", "readback.json", "negative-tests.json", "summary.json", "completion.json"}
LATE_PHASES = ("verify", "negative")
FLOAT = struct.Struct("<f")

def f32(value):
    return FLOAT.unpack(FLOAT.pack(value))[0]

def bits(values):
    a = array("f", values)
    if sys.byteorder != "little":
        a.byteswap()
    return a.tobytes()

def scalar_bits(value):
    return FLOAT.pack(value)

def finite(values, reason):
    need(all(math.isfinite(v) for v in values), reason)

def receipt_admission(value):
    lock = contract()["original_admission"]
    need(value.get("experiment") == lock["experiment"] and
         value.get("status") == "INPUT_ADMITTED_NO_DSP_EXECUTION" and
         value.get("freeze") == admission.FREEZE and value.get("artifact") == lock["artifact"] and
         value.get("source_revision") == OLD and value.get("original_D2_readback_exact") is True and
         value.get("DSP_executed") is False and value.get("models_executed") is False and
         value.get("promotion_allowed") is False and
         (value.get("case_count"), value.get("frames"), value.get("samples")) == (60, 35916, 5746560) and
         value.get("member_count") == 3551 and value.get("uncompressed_bytes") == 861385743 and
         value.get("budget_seconds") == 300 and
         value.get("elapsed_scope") == "through first receipt write; final write deadline checked" and
         type(value.get("elapsed_seconds")) in (float, int) and 0 <= value["elapsed_seconds"] <= 300,
         "D7_SAVED_ADMISSION")

def input_identity(phase, *, deep=True):
    lock = contract()
    receipt_admission(read(INPUT / "admission.json"))
    need(desc(INPUT / "original.zip") == {"bytes": 474165229,
         "sha256": lock["original_admission"]["artifact"]["sha256"]}, "D7_ORIGINAL_ZIP")
    parent, prior = INPUT / "original/result", INPUT / "original/gain-d2"
    for root, expected in ((parent, lock["original_d1_inside_d2"]),
                           (prior, lock["original_admission"])):
        need(digest(root / "report.json") == expected["report_sha256"] and
             digest(root / "artifact-manifest.json") == expected["manifest_sha256"],
             "D7_ORIGINAL_REPORT")
    need(read(parent / "artifact-manifest.json")["files"] == d1.payload_inventory(parent),
         "D7_ORIGINAL_D1_PAYLOAD")
    need(read(prior / "artifact-manifest.json")["files"] == d2.payload_inventory(prior),
         "D7_ORIGINAL_D2_PAYLOAD")
    catalogs = [entry["catalog"] for entry in lock["original_d2_case_input_lock"]["cases"]]
    need(d1.catalog(parent / "originals/A", parent / "originals/C") == catalogs, "D7_INPUT_BINDING")
    if deep:
        d1.verify_origins(parent)
        binding, _, _ = d2.parent_binding(parent, lock["original_d2_case_input_lock"], phase.started)
        need(binding == read(prior / "parent-binding.json"), "D7_INPUT_BINDING")
        d2.verify_sources(prior, lock["original_d2_case_input_lock"])
    bindings = []
    for case, spec in zip(catalogs, lock["input_member_bindings"]):
        expected = {"key": case["key"],
                    "inputs": {k: "original/result/originals/" + case["group"] + "/" + v
                               for k, v in case["inputs"].items() if v},
                    "auxiliary_inputs": ["original/result/originals/" + case["group"] + "/" + v
                                         for v in case["auxiliary_inputs"]],
                    "old_output_root": "original/result/originals/" + case["group"] + "/" + case["original_dir"],
                    "old_D1_taps_root": "original/result/cases/" + case["key"] + "/taps"}
        need(all(spec.get(k) == v for k, v in expected.items()), "D7_INPUT_BINDING")
        bindings.append({"key": case["key"], "inputs": {
            k: {"path": value, **desc(INPUT / value)} for k, value in spec["inputs"].items()},
            "old_outputs": {n: desc(INPUT / spec["old_output_root"] / n) for n in ("out.pcm", "metrics.jsonl")},
            "old_taps": {n: desc(INPUT / spec["old_D1_taps_root"] / n) for n in
                         [*(x + ".f32le" for x in d1.LANES), "control.csv"]}})
        phase.remaining()
    return {"admission": desc(INPUT / "admission.json"),
            "original_zip": desc(INPUT / "original.zip"), "parent_report": desc(parent / "report.json"),
            "parent_manifest": desc(parent / "artifact-manifest.json"), "cases": bindings}

def admit():
    with Phase("admission") as phase:
        admission.acquire(INPUT)  # unchanged complete D3 reader; not a 300-second child process
        identity = input_identity(phase)
        dump(OUTPUT / "input-binding.json", identity)

def catalogs():
    return [e["catalog"] for e in contract()["original_d2_case_input_lock"]["cases"]]

def paths(case):
    new = OUTPUT / "cases" / case["key"]
    parent = INPUT / "original/result"
    original = parent / "originals" / case["group"]
    return new, original, original / case["original_dir"], parent / "cases" / case["key"] / "taps"

def argv(case, kind, built):
    directory, original, _, _ = paths(case)
    return d1.mapped_argv(case, OUTPUT / built["programs"][kind]["path"], directory / kind, original)

def environment_for(case, kind):
    directory, _, _, _ = paths(case)
    return build.environment(directory / "d1" if kind == "observer" else None,
                             directory / "upstream" if kind == "observer" else None)

def compare_bytes(actual, expected, category):
    need(actual == expected, "D7_" + category)

def check_raw(signals, stereo):
    for channel, name in enumerate(LANES[:2]):
        compare_bytes(bits(signals[name]), bits(float(x) / 32768.0 for x in stereo[channel::2]),
                      "RAW_LEFT" if channel == 0 else "RAW_RIGHT")

def compare_original(case):
    directory, _, old, taps = paths(case)
    for name in ("out.pcm", "metrics.jsonl"):
        raw = (old / name).read_bytes()
        for kind in ("plain", "observer"):
            compare_bytes((directory / kind / name).read_bytes(), raw,
                          "OLD_PCM" if name == "out.pcm" else "OLD_METRICS_JSONL")
    for name in [*(n + ".f32le" for n in d1.LANES), "control.csv"]:
        compare_bytes((directory / "d1" / name).read_bytes(), (taps / name).read_bytes(),
                      "OLD_CONTROL" if name == "control.csv" else "OLD_D1_LANE")

def run(built):
    with Phase("run") as phase:
        completed = []
        for index, case in enumerate(catalogs()):
            directory, _, _, _ = paths(case)
            for name in ("plain", "observer", "d1", "upstream"):
                (directory / name).mkdir(parents=True)
            for kind in ("plain", "observer"):
                phase.run("%03d-%s" % (index, kind), argv(case, kind, built),
                          env=environment_for(case, kind))
            compare_original(case)
            completed.append(case["key"])
        dump(OUTPUT / "run-index.json", {"experiment": EXPERIMENT, "source": built["source"],
            "completed": completed, "cases": catalogs(), "status": "ALL_ORIGINAL_BYTES_IDENTICAL"})

def check_execution(receipt, case, kind, built):
    need(receipt["argv"] == argv(case, kind, built), "D7_EXECUTION_ARGV")
    env = environment_for(case, kind)
    need(receipt["environment"] == {"keys": sorted(env), "LC_ALL": env.get("LC_ALL"),
         "AP_D1_STAGE_DIR": env.get("AP_D1_STAGE_DIR"), "AP_D7_STAGE_DIR": env.get("AP_D7_STAGE_DIR")},
         "D7_EXECUTION_ENVIRONMENT")

def check_run(built):
    build.check_phase(OUTPUT, "run")
    index = read(OUTPUT / "run-index.json")
    need(index == {"experiment": EXPERIMENT, "source": built["source"],
         "completed": [c["key"] for c in catalogs()], "cases": catalogs(),
         "status": "ALL_ORIGINAL_BYTES_IDENTICAL"}, "D7_RUN_MATRIX")
    for i, case in enumerate(catalogs()):
        for kind in ("plain", "observer"):
            receipt = build.check_command(OUTPUT / ("run-logs/%03d-%s.command.json" % (i, kind)))
            check_execution(receipt, case, kind, built)

def hpf_decode(raw):
    values = HPF.unpack(raw)
    finite(values[:5], "D7_HPF_STATE_NONFINITE")
    return {"r": values[0], "x": list(values[1:3]), "y": list(values[3:5]), "channels": values[5]}

def bf_decode(raw):
    v = BF.unpack(raw)
    finite(v[:34], "D7_BF_STATE_NONFINITE")
    return {"history": [list(v[:8]), list(v[8:16])], "lag_score": list(v[16:33]),
            "fallback_gain": v[33], **dict(zip(BF_NAMES, v[34:]))}

def effective(state):
    return state["fallback_lag"] if state["fallback_active"] else state["lag"]

def initial_states():
    r = f32(math.exp(f32(f32(f32(-2.0 * f32(math.pi)) * 80.0) / 16000.0)))
    h = HPF.pack(r, 0, 0, 0, 0, 2)
    b = BF.pack(*([0.0] * 33), 1.0, 0, 3, 0, 3, 0, 0, 0, 0, 0, 0, 3)
    return h, b

def scheduled_near(case, frame):
    if case["group"] == "C":
        return "unknown"
    if case["inputs"]["clean_near"] is None:
        return "no_near_source"
    return "scheduled_present" if 150 <= frame < 550 else "scheduled_absent"

def check_events(case):
    resets = []
    for event in case["input_events"]:
        if event["kind"] == "cli_discontinuity":
            need(event == {"frame": 300, "sample": 48000, "kind": "cli_discontinuity",
                           "flags": 2, "lost_frames": 4}, "D7_RESET_COORDINATE")
            resets.append(300)
        else:
            need(event == {"frame": 300, "sample": 48000, "kind": "cli_echo_path_change"},
                 "D7_RESET_COORDINATE")
    return set(resets)

def check_hpf(before, after, raw_before, raw_after, inputs, outputs, channel):
    need(before["channels"] == after["channels"] == 2 and
         scalar_bits(before["r"]) == scalar_bits(after["r"]), "D7_HPF_STATE_AFTER")
    other = 1 - channel
    need(all(scalar_bits(before[k][other]) == scalar_bits(after[k][other]) for k in ("x", "y")),
         "D7_HPF_STATE_AFTER")
    need(scalar_bits(after["x"][channel]) == scalar_bits(inputs[-1]) and
         scalar_bits(after["y"][channel]) == scalar_bits(outputs[-1]), "D7_HPF_STATE_AFTER")
    px, py, r = before["x"][channel], before["y"][channel], before["r"]
    reconstructed = []
    for value in inputs:
        y = f32(f32(value - px) + f32(r * py))
        reconstructed.append(y)
        px, py = value, y
    need(bits(reconstructed) == bits(outputs),
         "D7_HPF_LEFT" if channel == 0 else "D7_HPF_RIGHT")

def check_bf(before, after, tracking, left, right, out):
    need(after["max_lag"] == before["max_lag"] == 3 and
         all(-3 <= s[k] <= 3 for s in (before, after) for k in ("lag", "fallback_lag")),
         "D7_BF_LAG")
    need(all(s[k] in (0, 1) for s in (before, after) for k in
             ("fallback_active", "fallback_hard_fault", "fallback_strong_channel")) and
         all(not s["fallback_hard_fault"] or s["fallback_active"] for s in (before, after)) and
         all(0 < s["fallback_gain"] <= 1 for s in (before, after)), "D7_FALLBACK_ROUTE")
    need(tracking in (0, 1), "D7_TRACK_DIRECTION")
    update = bool(tracking and ((before["counter"] + 1) & 3) == 0)
    expected_updates = min(before["score_updates"] + int(update), 0xffffffff)
    need(after["score_updates"] == expected_updates, "D7_SCORE_UPDATES")
    need(after["counter"] == ((before["counter"] + 1) & 0xffffffff if tracking else before["counter"]),
         "D7_BF_STATE_AFTER")
    if tracking:
        need(after["fixed_health_counter"] == 3, "D7_BF_STATE_AFTER")
    else:
        phase = before["fixed_health_counter"]
        phase = phase if 4 <= phase <= 7 else 3
        need(after["fixed_health_counter"] == 4 | ((phase + 1) & 3), "D7_BF_STATE_AFTER")
    indices = range(17) if not update else list(range(5)) + list(range(12, 17))
    need(all(scalar_bits(before["lag_score"][i]) == scalar_bits(after["lag_score"][i]) for i in indices),
         "D7_BF_LAG_SCORES")
    lag = before["lag"]
    if update:
        best = max(range(-3, 4), key=lambda j: after["lag_score"][j + 8])
        if after["lag_score"][best + 8] > f32(0.15):
            lag += int(best > lag) - int(best < lag)
    need(after["lag"] == lag, "D7_BF_LAG")
    need(bits(after["history"][0]) == bits(left[-8:]) and bits(after["history"][1]) == bits(right[-8:]),
         "D7_BF_HISTORY")
    output_lag = effective(after)
    result = []
    for i in range(160):
        a = i + output_lag if output_lag < 0 else i
        b = i - output_lag if output_lag >= 0 else i
        x = left[a] if a >= 0 else before["history"][0][8 + a]
        y = right[b] if b >= 0 else before["history"][1][8 + b]
        if after["fallback_active"]:
            strong, weak = (x, y) if after["fallback_strong_channel"] == 0 else (y, x)
            z = strong if after["fallback_hard_fault"] else f32(
                after["fallback_gain"] * f32(f32(0.75 * strong) + f32(0.25 * weak)))
        else:
            z = f32(0.5 * f32(x + y))
        result.append(z)
    need(bits(result) == bits(out), "D7_BF_OUTPUT_RECONSTRUCTION")
    return int(update)

def frame_trace(case, signals, trace, control):
    need(len(trace) == case["frames"] * RECORD, "D7_TRACE_GEOMETRY")
    initial_h, initial_b = initial_states()
    previous_h, previous_b = initial_h, initial_b
    resets = check_events(case)
    rows = []
    for frame in range(case["frames"]):
        start = frame * RECORD
        raw = trace[start:start + RECORD]
        number, tracking, alias, count = HEADER.unpack_from(raw)
        need((number, alias, count) == (frame, 0, 160), "D7_TRACE_GEOMETRY")
        h0, h1, h2, h3 = (raw[16:40], raw[40:64], raw[64:88], raw[88:112])
        rb, ra = raw[112:292], raw[292:472]
        is_reset = frame in resets
        want_h, want_b = (initial_h, initial_b) if frame == 0 or is_reset else (previous_h, previous_b)
        reason = "D7_SPURIOUS_PATH_RESET" if frame == 300 and any(
            e["kind"] == "cli_echo_path_change" for e in case["input_events"]) else "D7_HPF_STATE_BEFORE"
        need(h0 == want_h, reason)
        need(h1 == h2, "D7_HPF_CHANNEL_ORDER")
        need(rb == want_b, "D7_SPURIOUS_PATH_RESET" if reason == "D7_SPURIOUS_PATH_RESET" else "D7_BF_STATE_BEFORE")
        a, b, c, d = map(hpf_decode, (h0, h1, h2, h3))
        begin, end = frame * 160, (frame + 1) * 160
        frame_signals = {name: value[begin:end] for name, value in signals.items()}
        check_hpf(a, b, h0, h1, frame_signals["hpf_input_l"], frame_signals["hpf_output_l"], 0)
        check_hpf(c, d, h2, h3, frame_signals["hpf_input_r"], frame_signals["hpf_output_r"], 1)
        before, after = bf_decode(rb), bf_decode(ra)
        update = check_bf(before, after, tracking, frame_signals["hpf_output_l"],
                          frame_signals["hpf_output_r"], frame_signals["bf_output"])
        rows.append({"frame": frame, "physical_sample_range": [begin, end],
            "trace_byte_range": [start, start + RECORD], "track_direction": tracking,
            "output_alias": alias, "reset": is_reset, "scheduled_near": scheduled_near(case, frame),
            "actual_activity_far": int(control[frame]["far"]), "actual_activity_dt": int(control[frame]["dt"]),
            "before": {k: before[k] for k in (*BF_NAMES, "fallback_gain")},
            "after": {k: after[k] for k in (*BF_NAMES, "fallback_gain")},
            "effective_lag_before": effective(before), "effective_output_lag": effective(after),
            "score_update": update,
            "lag_score_ema_after": after["lag_score"]})
        previous_h, previous_b = h3, ra
    return rows

def histogram(values):
    result = {}
    for value in values:
        key = str(value)
        result[key] = result.get(key, 0) + 1
    return result

def association(rows, first, last):
    need(first % 160 == last % 160 == 0, "D7_WRONG_WINDOW")
    selected = rows[first // 160:last // 160]
    need(len(selected) == (last - first) // 160, "D7_ASSOCIATION_COUNT")
    return {"physical_sample_range": [first, last], "frames": len(selected),
        "actual_tracking": histogram(r["track_direction"] for r in selected),
        "scheduled_near": histogram(r["scheduled_near"] for r in selected),
        "actual_far_dt": histogram(str(r["actual_activity_far"]) + "/" + str(r["actual_activity_dt"]) for r in selected),
        "tracked_lag_before": histogram(r["before"]["lag"] for r in selected),
        "tracked_lag_after": histogram(r["after"]["lag"] for r in selected),
        "effective_output_lag": histogram(r["effective_output_lag"] for r in selected),
        "fallback_active": histogram(r["after"]["fallback_active"] for r in selected),
        "hard_fault": histogram(r["after"]["fallback_hard_fault"] for r in selected),
        "strong_channel": histogram(r["after"]["fallback_strong_channel"] for r in selected),
        "score_updates": sum(r["score_update"] for r in selected),
        "resets": sum(r["reset"] for r in selected),
        "tracked_lag_transitions": sum(r["before"]["lag"] != r["after"]["lag"] for r in selected),
        "effective_lag_transitions": sum(r["effective_lag_before"] != r["effective_output_lag"] for r in selected),
        "actual_ema_score_by_lag": {str(lag): {
            "minimum": min(r["lag_score_ema_after"][lag + 8] for r in selected),
            "maximum": max(r["lag_score_ema_after"][lag + 8] for r in selected),
            "mean": statistics.mean(r["lag_score_ema_after"][lag + 8] for r in selected)}
            for lag in range(-8, 9)}}

def check_observer(case, built):
    directory, _, _, _ = paths(case)
    n = case["frames"]
    new = read(directory / "upstream/observer.json")
    need(new == {"experiment": EXPERIMENT, "status": "OBSERVED",
         "source_revision": built["source"]["revision"] + "-D7-observer",
         "frames": n, "hpf_calls": 2 * n, "bf_calls": n, "cli_exit_code": 0,
         "observer_error_count": 0, "first_error": "", "layout_checked": True,
         "hpf_state_bytes": 24, "bf_state_bytes": 180, "record_bytes": 472,
         "hpf_state_offsets": [0, 4, 12, 20],
         "bf_state_offsets": [0, 64, 132, 136, 140, 144, 148, 152, 156, 160, 164, 168, 172, 176],
         "offset_samples": 0, "sample_format": "float32le"}, "D7_OBSERVER_RECEIPT")
    old = read(directory / "d1/observer.json")
    need(old["status"] == "OBSERVED" and old["source_revision"] ==
         built["source"]["revision"] + "-D7-observer" and old["frames"] == n and
         old["cli_exit_code"] == old["observer_error_count"] == 0 and old["first_error"] == "" and
         old["capture_only"] is case["capture_only"] and old["calls"] == {
             "activity": n, "aec": 0 if case["capture_only"] else n, "ns": n, "agc": n, "res": 0},
         "D7_OLD_OBSERVER_RECEIPT")
    for lane, offset in d1.LANES.items():
        count = 0 if case["capture_only"] and lane in d1.AEC_LANES else n
        need(old["lanes"][lane] == {"file": lane + ".f32le", "present": count != 0,
             "frames": count, "samples": count * 160, "bytes": count * 640, "offset_samples": offset},
             "D7_OLD_OBSERVER_RECEIPT")
    return new, old

def score_shape(case, stages):
    end = case["samples"] - 160
    windows = [[first, min(first + 16000, end)] for first in range(0, end, 16000)]
    for name, stage in stages.items():
        need(stage["common"]["physical_sample_range"] == [0, end] and
             [w["physical_sample_range"] for w in stage["one_second_windows"]] == windows,
             "D7_WRONG_WINDOW")
        if case["inputs"]["clean_near"] is None:
            reason = "C_has_no_admitted_clean_near_reference" if case["group"] == "C" else "no_clean_near_reference"
            need(all(v["near_si_sdr_db"] is None and v["near_si_sdr_null_reason"] == reason for v in
                     [stage["common"], *stage["one_second_windows"]]), "D7_NULL_TO_ZERO")
    return windows

def case_result(case, old_case, built):
    directory = paths(case)[0]
    members = {"plain/out.pcm", "plain/metrics.jsonl", "observer/out.pcm", "observer/metrics.jsonl",
               "d1/control.csv", "d1/observer.json", "upstream/state.bin", "upstream/observer.json"}
    members |= {"d1/" + name + ".f32le" for name in d1.LANES}
    members |= {"upstream/" + name + ".f32le" for name in LANES}
    build.exact_closure(directory, members, "D7_CASE_CLOSURE", limit=build.OUTPUT_LIMIT)
    compare_original(case)  # Historical endpoints and all original D1 lanes, not just two new builds.
    directory, original, _, _ = paths(case)
    check_observer(case, built)
    n = case["samples"]
    signals = {name: d1.samples(directory / "upstream" / (name + ".f32le"), "f", n) for name in LANES}
    stereo = d1.samples(original / case["inputs"]["mic"], "h", 2 * n)
    check_raw(signals, stereo)
    bridge = "ns_input" if case["capture_only"] else "aec_input"
    compare_bytes((directory / "upstream/bf_output.f32le").read_bytes(),
                  (directory / "d1" / (bridge + ".f32le")).read_bytes(), "BF_OUTPUT")
    metrics = d1.metric_rows(directory / "observer/metrics.jsonl", case["frames"])
    counts, events = d1.controls(directory / "d1/control.csv", case, metrics)
    control = list(csv.DictReader(io.StringIO((directory / "d1/control.csv").read_text())))
    frames = frame_trace(case, signals, (directory / "upstream/state.bin").read_bytes(), control)
    reference = None
    reason = "C_has_no_admitted_clean_near_reference" if case["group"] == "C" else "no_clean_near_reference"
    if case["group"] == "A" and case["inputs"]["clean_near"]:
        reference = [float(v) / 32768.0 for v in d1.samples(original / case["inputs"]["clean_near"], "h", n)]
    stages = {name: d1.measure_lane(values, 0, n, reference, reason, True) for name, values in signals.items()}
    windows = score_shape(case, stages)
    old_stages = {}
    for name, offset in d1.LANES.items():
        if case["capture_only"] and name in d1.AEC_LANES:
            old_stages[name] = {"present": False, "offset_samples": offset,
                                "reason": "capture_only_route_has_no_AEC_call"}
        else:
            values = d1.samples(directory / "d1" / (name + ".f32le"), "f", n)
            old_stages[name] = d1.measure_lane(values, offset, n, reference, reason, name in d1.NEAR_LANES)
    need(old_stages == old_case["stages"] and counts == old_case["control_counts"] and
         events == old_case["events"], "D7_OLD_D1_SCORES")
    changes = {left + "_to_" + right: d1.stage_delta(stages, left, right, left + "_to_" + right)
               for left, right in contract()["scoring"]["comparisons"]}
    result = {k: case[k] for k in ("key", "group", "profile", "scenario", "frames", "samples", "capture_only")}
    result.update(stages=stages, stage_changes=changes, original_D1_stages=old_stages,
        original_events=case["input_events"], source_placement_metadata=case["dimensions"],
        frame_associations=frames, common_association=association(frames, 0, n - 160),
        window_associations=[association(frames, a, b) for a, b in windows],
        whole_association=association(frames, 0, n), human_vad_labels=False,
        all_original_bytes_equal=True, raw_clean_HPF_delta_is_damage=False,
        state_origin="actual complete HPF/BF before-after state in upstream/state.bin; lag_score is EMA, not instantaneous coherence",
        output_equation_origin="independent Float32 reconstruction using actual after-route and before-history",
        waveform_identity={name: desc(directory / "upstream" / (name + ".f32le")) for name in LANES},
        state_identity=desc(directory / "upstream/state.bin"))
    # All 17 EMA scores and both complete histories remain in the binary trace.
    # Avoid repeating them in every JSON row after the fixed-window summaries.
    for row in frames:
        del row["lag_score_ema_after"]
    return result

def check_saved_case(case, actual, saved):
    score_shape(case, saved["stages"])
    need([w["physical_sample_range"] for w in saved["window_associations"]] ==
         [w["physical_sample_range"] for w in actual["window_associations"]], "D7_WRONG_WINDOW")
    need(len(saved["frame_associations"]) == case["frames"], "D7_ASSOCIATION_COUNT")
    for a, s in zip(actual["frame_associations"], saved["frame_associations"]):
        need(s["scheduled_near"] == a["scheduled_near"], "D7_NEAR_SCHEDULE")
        need(s["effective_output_lag"] == effective(s["after"]) == a["effective_output_lag"],
             "D7_EFFECTIVE_LAG")
    need(saved["whole_association"] == actual["whole_association"] and
         saved["common_association"] == actual["common_association"] and
         saved["window_associations"] == actual["window_associations"], "D7_ASSOCIATION_COUNT")
    need(saved == actual, "D7_READBACK_CASE")

def check_report_identity(saved, built):
    need(saved["source"] == built["source"], "D7_REPORT_SOURCE")
    need([c["key"] for c in saved["cases"]] == [c["key"] for c in catalogs()], "D7_MISSING_CASE")

def check_input_binding(actual, saved):
    need(actual == saved, "D7_INPUT_BINDING")

def analyze(phase, saved=None):
    lock = contract()
    build.check_phase(OUTPUT, "admission")
    inputs = input_identity(phase)
    check_input_binding(inputs, read(OUTPUT / "input-binding.json"))
    built = build.verify_build(phase)
    check_run(built)
    if saved is not None:
        check_report_identity(saved, built)
    old = read(INPUT / "original/result/report.json")
    cases = []
    for i, (case, old_case) in enumerate(zip(catalogs(), old["cases"])):
        need(old_case["key"] == case["key"], "D7_ORIGINAL_CASE")
        actual = case_result(case, old_case, built)
        if saved is not None:
            check_saved_case(case, actual, saved["cases"][i])
        cases.append(actual)
        phase.remaining()
    totals = {"cases": len(cases), "frames": sum(c["frames"] for c in cases),
              "samples_per_lane": sum(c["samples"] for c in cases),
              "resets": sum(c["whole_association"]["resets"] for c in cases),
              "windows": sum(len(c["window_associations"]) for c in cases),
              "reference_cases": sum(c["stages"]["bf_output"]["common"]["near_si_sdr_db"] is not None for c in cases)}
    need(totals == {"cases": 60, "frames": 35916, "samples_per_lane": 5746560,
                   "resets": 8, "windows": 362, "reference_cases": 32}, "D7_MATRIX_TOTALS")
    groups = []
    for group, profile, scenario in sorted({(c["group"], c["profile"], c["scenario"]) for c in cases}):
        selected = [c for c in cases if (c["group"], c["profile"], c["scenario"]) == (group, profile, scenario)]
        changes = {}
        for name in selected[0]["stage_changes"]:
            values = [c["stage_changes"][name]["common"]["near_si_sdr_change_db"] for c in selected
                      if c["stage_changes"][name]["common"]["near_si_sdr_change_db"] is not None]
            changes[name] = {"count": len(values), "min": min(values) if values else None,
                "median": statistics.median(values) if values else None, "max": max(values) if values else None}
        groups.append({"group": group, "profile": profile, "scenario": scenario, "cases": len(selected),
                       "descriptive_si_sdr_changes_db": changes})
    result = {"experiment": EXPERIMENT, "freeze": FREEZE, "source": built["source"],
        "original_source": OLD, "original_AC_production_source": d1.BASE_SHA,
        "original_artifact": lock["original_admission"]["artifact"],
        "status": STATUS, "measurement_valid": True, "totals": totals,
        "hpf_calls": 71832, "bf_calls": 35916, "bytes_per_new_lane": 22986240, "trace_bytes": 16952352,
        "null_reference_cases": 28, "cases": cases, "aggregates": groups, "input_identity": inputs,
        "actual_mode_census": histogram(r["track_direction"] for c in cases for r in c["frame_associations"]),
        "interpretation": {"association_only": True, "causal_echo_following": False,
                          "HPF_raw_clean_metric_is_confounded": True, "candidate_admission": False},
        "promotion_allowed": False, "models_executed": False, "physical_devices_executed": False,
        "automatic_followup": False, "independent_observations": False}
    if saved is not None:
        need(result == saved, "D7_READBACK_REPORT")
    return result

def seal_payload():
    all_entries = build.inventory(OUTPUT)
    files = {n: v for n, v in all_entries["files"].items() if n not in FINAL
             and not any(n == p + "-phase.json" or n.startswith(p + "-logs/") for p in LATE_PHASES)}
    dirs = [n for n in all_entries["directories"] if not any(
        n == p + "-logs" or n.startswith(p + "-logs/") for p in LATE_PHASES)]
    need(sum(v["bytes"] for v in all_entries["files"].values()) <= build.OUTPUT_LIMIT, "D7_OUTPUT_BYTES_BOUND")
    return {"files": files, "directories": dirs}

def check_seal():
    need(seal_payload() == read(OUTPUT / "seal.json"), "D7_OUTPUT_CLOSURE")

def check_readback(value):
    need(value == {"experiment": EXPERIMENT, "status": "PASS", "DSP_executed": False,
         "models_executed": False, "report": desc(OUTPUT / "report.json"),
         "seal": desc(OUTPUT / "seal.json")}, "D7_READBACK_RECEIPT")

def verify(phase):
    build.check_phase(OUTPUT, "analysis")
    check_seal()
    report = analyze(phase, read(OUTPUT / "report.json"))
    if (OUTPUT / "readback.json").exists():
        check_readback(read(OUTPUT / "readback.json"))
    check_seal()
    return report

def complete_report():
    negative = read(OUTPUT / "negative-tests.json")
    names = contract()["test_contract"]["actual_negative_categories"]
    need(negative["status"] == "PASS" and negative["count"] == 51 and
         [r["category"] for r in negative["targeted_mutations"]] == names and
         all(r["status"] == "PASS" and r["untouched_guard_passed"] is True and
             r["observed_reason"] == r["expected_reason"] for r in negative["targeted_mutations"]),
         "D7_NEGATIVE_RECEIPT")
    payload = build.inventory(OUTPUT)
    need(sum(v["bytes"] for v in payload["files"].values()) <= build.OUTPUT_LIMIT, "D7_OUTPUT_BYTES_BOUND")
    dump(OUTPUT / "completion.json", {"experiment": EXPERIMENT, "status": "PASS",
         "complete_payload": payload, "promotion_allowed": False,
         "independent_audit": "not executed by this driver; separately authored read-only audit still required"})

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("all",))
    parser.add_argument("--source-revision", required=True)
    args = parser.parse_args()
    need(not OUTPUT.exists() and not OUTPUT.is_symlink() and not INPUT.exists() and not INPUT.is_symlink(),
         "D7_NEW_OUTPUT_REQUIRED")
    OUTPUT.mkdir(parents=True)
    need(not any(p.is_symlink() for p in (OUTPUT, *OUTPUT.parents)), "D7_OUTPUT_SYMLINK")
    started = time.monotonic()
    first = None
    try:
        need(os.environ.get("GITHUB_ACTIONS") == "true", "D7_ACTIONS_ONLY")
        admit()
        built = build.build()
        need(built["source"]["revision"] == args.source_revision, "D7_EXECUTION_HEAD")
        run(built)
        with Phase("analysis") as phase:
            report = analyze(phase)
            dump(OUTPUT / "report.json", report, compact=True)
        dump(OUTPUT / "seal.json", seal_payload())
        with Phase("verify") as phase:
            verify(phase)
            dump(OUTPUT / "readback.json", {"experiment": EXPERIMENT, "status": "PASS",
                "DSP_executed": False, "models_executed": False,
                "report": desc(OUTPUT / "report.json"), "seal": desc(OUTPUT / "seal.json")})
        # This imports only the current retained test module. It does not start
        # another interpreter or assign a hidden 300-second child timeout.
        import test_dualmic_upstream_d7 as tests
        with Phase("negative") as phase:
            tests.actual_negatives(phase)
        build.check_phase(OUTPUT, "verify")
        build.check_phase(OUTPUT, "negative")
        check_readback(read(OUTPUT / "readback.json"))
        check_seal()
        need(time.monotonic() - started <= 1200, "D7_TOTAL_JOB_BUDGET")
        dump(OUTPUT / "summary.json", {k: report[k] for k in
            ("experiment", "status", "totals", "aggregates", "actual_mode_census",
             "measurement_valid", "promotion_allowed", "models_executed")})
        complete_report()
        need(time.monotonic() - started <= 1200, "D7_TOTAL_JOB_BUDGET")
        print(json.dumps(read(OUTPUT / "summary.json"), sort_keys=True))
        return 0
    except BaseException as error:
        first = {"experiment": EXPERIMENT, "status": "MEASUREMENT_INVALID",
                 "type": type(error).__name__,
                 "reason": str(error) if isinstance(error, (ValueError, TimeoutError)) else "execution failed",
                 "elapsed_seconds": time.monotonic() - started, "promotion_allowed": False}
        dump(OUTPUT / "first-failure.json", first)
        print(json.dumps(first), file=sys.stderr)
        return 1

if __name__ == "__main__":
    raise SystemExit(main())
