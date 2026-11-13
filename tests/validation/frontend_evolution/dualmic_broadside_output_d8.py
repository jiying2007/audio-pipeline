#!/usr/bin/env python3
"""One preregistered broadside-output intervention; no promotion or lag search."""
from __future__ import annotations
import argparse
from array import array
import csv
import hashlib
import io
import json
import math
import os
import re
from pathlib import Path
import statistics
import struct
import sys
import shutil
import time

sys.dont_write_bytecode = True
if __name__ == "__main__":
    sys.modules["dualmic_broadside_output_d8"] = sys.modules[__name__]
import dualmic_broadside_output_d8_build as build
from dualmic_broadside_output_d8_build import (ROOT, INPUT, OUTPUT, EXPERIMENT, FREEZE,
    Phase, need, read, dump, digest, desc, contract)
import dualmic_upstream_d7 as upstream
sys.path.insert(0, str(ROOT / "tests/validation"))
import quality_metric_support as quality
d2, d1, admission = build.d2, build.d2.d1, build.admission
OLD = "cc853616685b9faf7880e6d8f8f1a89d187d342a"
ARMS = ("baseline", "candidate")
FORMS = tuple(arm + "-" + form for arm in ARMS for form in ("plain", "observed"))
HPF_LANES = upstream.LANES[:4]
UNIQUE = ("bf_output", "reference", "echo", "aec_residual", "ns_output", "agc_output")
AGC = struct.Struct("<6f")
FINAL = {"seal.json", "readback.json", "negative-tests.json", "summary.json", "completion.json"}
LATE = ("verify", "negative")
REVIEW = "REVIEW_FOR_INDEPENDENT_CONFIRMATION_NO_PROMOTION"
NO_ADVANCE = "NO_ADVANCE"
EXPORT_LIMIT = 4 * 1024 * 1024 - 65536
f32, bits = upstream.f32, upstream.bits

def byte_equal(left, right, reason):
    need(left == right, reason)

def normalized(raw):
    return [float(value) / 32768.0 for value in raw]

def finite_number(value, reason):
    need(type(value) in (int, float) and math.isfinite(value), reason)
    return value

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
         "D8_SAVED_ADMISSION")

def input_identity(phase, *, deep=True):
    lock = contract()
    receipt_admission(read(INPUT / "admission.json"))
    need(desc(INPUT / "original.zip") == {"bytes": 474165229,
         "sha256": lock["original_admission"]["artifact"]["sha256"]}, "D8_ORIGINAL_ZIP")
    parent, prior = INPUT / "original/result", INPUT / "original/gain-d2"
    for root, expected in ((parent, lock["original_d1_inside_d2"]),
                           (prior, lock["original_admission"])):
        need(digest(root / "report.json") == expected["report_sha256"] and
             digest(root / "artifact-manifest.json") == expected["manifest_sha256"],
             "D8_ORIGINAL_REPORT")
    need(read(parent / "artifact-manifest.json")["files"] == d1.payload_inventory(parent),
         "D8_ORIGINAL_D1_PAYLOAD")
    need(read(prior / "artifact-manifest.json")["files"] == d2.payload_inventory(prior),
         "D8_ORIGINAL_D2_PAYLOAD")
    catalogs = [entry["catalog"] for entry in lock["original_d2_case_input_lock"]["cases"]]
    need(d1.catalog(parent / "originals/A", parent / "originals/C") == catalogs, "D8_INPUT_BINDING")
    if deep:
        d1.verify_origins(parent)
        binding, _, _ = d2.parent_binding(parent, lock["original_d2_case_input_lock"], phase.started)
        need(binding == read(prior / "parent-binding.json"), "D8_INPUT_BINDING")
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
        need(all(spec.get(k) == v for k, v in expected.items()), "D8_INPUT_BINDING")
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


def source_paths(case, live=False):
    directory, original, endpoint, taps = paths(case)
    result = {}
    for arm in ARMS:
        if live:
            scratch = OUTPUT / "scratch/current"
            up, old = scratch / (arm + "-upstream"), scratch / (arm + "-d1")
            observed = scratch / (arm + "-observed")
            streams = {name: up / (name + ".f32le") for name in upstream.LANES}
            streams.update({name: old / (name + ".f32le") for name in d1.LANES})
            result[arm] = {"streams": streams, "pcm": observed / "out.pcm",
                "metrics": observed / "metrics.jsonl", "control": old / "control.csv",
                "trace": up / "state.bin", "agc_trace": up / "agc-state.bin",
                "d1_receipt": old / "observer.json", "upstream_receipt": up / "observer.json",
                "plain_pcm": scratch / (arm + "-plain/out.pcm"),
                "plain_metrics": scratch / (arm + "-plain/metrics.jsonl")}
        else:
            streams = {name: directory / "shared" / (name + ".f32le") for name in HPF_LANES}
            if arm == "baseline":
                streams["bf_output"] = taps / (("ns_input" if case["capture_only"] else "aec_input") + ".f32le")
                streams.update({name: taps / (name + ".f32le") for name in d1.LANES})
            else:
                streams.update({name: directory / "candidate" / (name + ".f32le") for name in UNIQUE})
                streams["aec_input"] = None if case["capture_only"] else streams["bf_output"]
                streams["ns_input"] = streams["bf_output"] if case["capture_only"] else streams["aec_residual"]
            result[arm] = {"streams": streams,
                "pcm": endpoint / "out.pcm" if arm == "baseline" else directory / "candidate/out.pcm",
                "metrics": endpoint / "metrics.jsonl" if arm == "baseline" else directory / "candidate/metrics.jsonl",
                "control": taps / "control.csv" if arm == "baseline" else directory / "candidate/control.csv",
                "trace": directory / arm / "state.bin", "agc_trace": directory / arm / "agc-state.bin",
                "d1_receipt": directory / "receipts" / (arm + "-d1-observer.json"),
                "upstream_receipt": directory / "receipts" / (arm + "-upstream-observer.json")}
    return result

def expected_case_files(case):
    paths_ = source_paths(case)
    names = set()
    for arm in ARMS:
        for field, value in paths_[arm].items():
            values = value.values() if field == "streams" else (value,)
            for path in values:
                if path is not None and path.is_relative_to(paths(case)[0]):
                    names.add(path.relative_to(paths(case)[0]).as_posix())
    names.add("retention.json")
    return names

def raw(path):
    return b"" if path is None else Path(path).read_bytes()

def check_live_neutrality(case):
    live = source_paths(case, True)
    _, _, endpoint, taps = paths(case)
    for arm in ARMS:
        for field in ("pcm", "metrics"):
            byte_equal(raw(live[arm][field]), raw(live[arm]["plain_" + field]),
                       "D8_PLAIN_OBSERVED_" + field.upper())
    for field, name in (("pcm", "out.pcm"), ("metrics", "metrics.jsonl")):
        for key in (field, "plain_" + field):
            byte_equal(raw(live["baseline"][key]), raw(endpoint / name), "D8_OLD_PCM" if field == "pcm" else "D8_OLD_METRICS_JSONL")
    for name in d1.LANES:
        byte_equal(raw(live["baseline"]["streams"][name]), raw(taps / (name + ".f32le")),
                   "D8_OLD_D1_LANE")
    byte_equal(raw(live["baseline"]["control"]), raw(taps / "control.csv"), "D8_OLD_CONTROL")
    for name in HPF_LANES:
        byte_equal(raw(live["baseline"]["streams"][name]), raw(live["candidate"]["streams"][name]),
                   "D8_ACTUAL_HPF_CROSS_ARM")
    byte_equal(raw(live["baseline"]["trace"]), raw(live["candidate"]["trace"]),
               "D8_ACTUAL_STATE_CROSS_ARM")
    for arm in ARMS:
        bridge = "ns_input" if case["capture_only"] else "aec_input"
        byte_equal(raw(live[arm]["streams"]["bf_output"]), raw(live[arm]["streams"][bridge]),
                   "D8_BF_OUTPUT")
        if not case["capture_only"]:
            byte_equal(raw(live[arm]["streams"]["ns_input"]), raw(live[arm]["streams"]["aec_residual"]),
                       "D8_NS_INPUT_ALIAS")
    if case["scenario"] in ("near-only", "silent-render"):
        for field in ("pcm", "metrics", "control", "trace", "agc_trace"):
            byte_equal(raw(live["baseline"][field]), raw(live["candidate"][field]), "D8_NEAR_SILENT_MUTATION")
        for name in live["baseline"]["streams"]:
            byte_equal(raw(live["baseline"]["streams"][name]), raw(live["candidate"]["streams"][name]),
                       "D8_NEAR_SILENT_MUTATION")
    return live

def check_observer_receipts(case, paths_, built):
    n = case["frames"]
    for arm in ARMS:
        suffix = "-D8-" + arm + "-observed"
        new = read(paths_[arm]["upstream_receipt"])
        expected = {"schema_version": 1, "experiment": EXPERIMENT, "status": "OBSERVED",
            "source_revision": built["source"]["revision"] + suffix,
            "frames": n, "expected_frames": n, "maximum_frames": 629,
            "hpf_calls": 2*n, "bf_calls": n, "agc_calls": n, "cli_exit_code": 0,
            "observer_error_count": 0, "first_error": "", "layout_checked": True,
            "hpf_state_bytes": 24, "bf_state_bytes": 180, "agc_state_bytes": 12,
            "hpf_state_offsets": [0,4,12,20],
            "bf_state_offsets": [0,64,132,136,140,144,148,152,156,160,164,168,172,176],
            "agc_state_offsets": [0,4,8], "record_bytes": 472, "agc_record_bytes": 24,
            "record_offsets": [0,4,8,12,16,40,64,88,112,292], "agc_record_offsets": [0,12],
            "lane_bytes": [n*640]*5, "state_bytes": n*472, "agc_trace_bytes": n*24,
            "track_direction_required": 1, "offset_samples": 0, "sample_format": "float32le",
            "d8_file_write_caps_checked": True, "receipt_cap_bytes": 4096,
            "unobserved_downstream_state_claimed": False}
        need(new == expected, "D8_OBSERVER_RECEIPT")
        old = read(paths_[arm]["d1_receipt"])
        need(old["status"] == "OBSERVED" and old["source_revision"] == expected["source_revision"] and
             old["frames"] == n and old["cli_exit_code"] == old["observer_error_count"] == 0 and
             old["first_error"] == "" and old["capture_only"] is case["capture_only"] and
             old["calls"] == {"activity":n,"aec":0 if case["capture_only"] else n,
                             "ns":n,"agc":n,"res":0}, "D8_D1_OBSERVER_RECEIPT")
        need(set(old["lanes"]) == set(d1.LANES), "D8_D1_OBSERVER_RECEIPT")
        for name, offset in d1.LANES.items():
            count = 0 if case["capture_only"] and name in d1.AEC_LANES else n
            need(old["lanes"][name] == {"file":name+".f32le","present":count != 0,
                 "frames":count,"samples":count*160,"bytes":count*640,"offset_samples":offset},
                 "D8_D1_OBSERVER_RECEIPT")

def check_metrics_bytes(data, frames):
    lines = data.splitlines(keepends=True)
    need(len(data) <= frames*2048 and len(lines) == frames and
         all(len(line) <= 2048 and line.endswith(b"\n") for line in lines),
         "D8_METRIC_CATEGORY_OVERFLOW")

def check_control_bytes(data, frames):
    lines = data.splitlines(keepends=True)
    need(len(data) <= frames*1024 and len(lines) == frames+1 and
         all(len(line) <= 1024 and line.endswith(b"\n") for line in lines),
         "D8_CONTROL_HEADER_OVERFLOW")

def load_case(case, paths_):
    _, original, _, _ = paths(case)
    n = case["samples"]
    value = {"paths":paths_, "signals":{}, "traces":{}, "agc_traces":{}, "control":{},
             "controls_raw":{}, "metrics":{}, "control_counts":{}, "events":{},
             "final_pcm":{}, "final_bytes":{}}
    value["stereo"] = d1.samples(original / case["inputs"]["mic"], "h", 2*n)
    value["reference"] = (d1.samples(original / case["inputs"]["clean_near"], "h", n)
                          if case["group"] == "A" and case["inputs"]["clean_near"] else None)
    for arm in ARMS:
        sources = paths_[arm]
        value["signals"][arm] = {}
        for name, path in sources["streams"].items():
            count = 0 if name in d1.AEC_LANES and case["capture_only"] else n
            value["signals"][arm][name] = array("f") if path is None else d1.samples(path, "f", count)
            need(len(value["signals"][arm][name]) == count, "D8_SIGNAL_GEOMETRY")
        value["traces"][arm] = raw(sources["trace"])
        value["agc_traces"][arm] = raw(sources["agc_trace"])
        value["controls_raw"][arm] = raw(sources["control"])
        check_control_bytes(value["controls_raw"][arm],case["frames"])
        check_metrics_bytes(raw(sources["metrics"]),case["frames"])
        value["control"][arm] = list(csv.DictReader(io.StringIO(value["controls_raw"][arm].decode("ascii"))))
        value["metrics"][arm] = d1.metric_rows(sources["metrics"], case["frames"])
        counts, events = d1.controls(sources["control"], case, value["metrics"][arm])
        value["control_counts"][arm], value["events"][arm] = counts, events
        value["final_pcm"][arm] = d1.samples(sources["pcm"], "h", n)
        value["final_bytes"][arm] = raw(sources["pcm"])
    return value

def check_zero_bf(before, after, left, right, actual):
    result = []
    for x, y in zip(left, right):
        if after["fallback_active"]:
            strong, weak = (x,y) if after["fallback_strong_channel"] == 0 else (y,x)
            z = strong if after["fallback_hard_fault"] else f32(after["fallback_gain"] *
                f32(f32(0.75 * strong) + f32(0.25 * weak)))
        else:
            z = f32(0.5 * f32(x+y))
        result.append(z)
    need(bits(result) == bits(actual), "D8_ZERO_BF_RECONSTRUCTION")

def upstream_guard(function, *args):
    try:
        return function(*args)
    except ValueError as error:
        if str(error).startswith("D7_"):
            raise ValueError("D8_" + str(error)[3:]) from None
        raise

def baseline_frame_trace(case, signals, trace, control):
    return upstream_guard(upstream.frame_trace, case, signals, trace, control)

def check_upstream(case, evidence):
    for arm in ARMS:
        upstream_guard(upstream.check_raw, evidence["signals"][arm], evidence["stereo"])
        trace = evidence["traces"][arm]
        if arm == "candidate":
            need(bool(trace),"D8_MISSING_ACTUAL_CANDIDATE_STATE")
        need(len(trace) == case["frames"]*472, "D8_TRACE_GEOMETRY")
        for frame in range(case["frames"]):
            number, tracking, alias, count = struct.unpack_from("<IiII",trace,frame*472)
            need((number,alias,count) == (frame,0,160), "D8_TRACE_GEOMETRY")
            need(tracking != 0, "D8_TRACKING_OFF")
            need(tracking == 1, "D8_TRACK_DIRECTION")
    byte_equal(evidence["traces"]["baseline"], evidence["traces"]["candidate"],
               "D8_ACTUAL_STATE_CROSS_ARM")
    for name in HPF_LANES:
        byte_equal(bits(evidence["signals"]["baseline"][name]), bits(evidence["signals"]["candidate"][name]),
                   "D8_ACTUAL_HPF_CROSS_ARM")
    frames = baseline_frame_trace(case, evidence["signals"]["baseline"], evidence["traces"]["baseline"],
                                  evidence["control"]["baseline"])
    for frame in range(case["frames"]):
        record = evidence["traces"]["candidate"][frame*472:(frame+1)*472]
        first,last = frame*160,(frame+1)*160
        check_zero_bf(upstream.bf_decode(record[112:292]), upstream.bf_decode(record[292:472]),
            evidence["signals"]["candidate"]["hpf_output_l"][first:last],
            evidence["signals"]["candidate"]["hpf_output_r"][first:last],
            evidence["signals"]["candidate"]["bf_output"][first:last])
    return frames

def check_agc(case, evidence, arm):
    trace = evidence["agc_traces"][arm]
    need(bool(trace),"D8_MISSING_AGC_STATE")
    need(len(trace) == 24*case["frames"], "D8_AGC_TRACE_GEOMETRY")
    prior = INPUT / "original/gain-d2/cases" / case["key"] / "views"
    old = list(csv.DictReader(io.StringIO((prior/"gain.csv").read_text(encoding="ascii"))))
    need(len(old) == case["frames"], "D8_ORIGINAL_AGC_TRACE")
    resets = upstream.check_events(case)
    counts = {"target_gate_frames":0,"output_gate_frames":0,"peak_limit_frames":0,"clamped_samples":0}
    rows, previous, constants = [], None, None
    for frame, values in enumerate(AGC.iter_unpack(trace)):
        need(all(math.isfinite(x) for x in values), "D8_AGC_NONFINITE")
        before, after = values[:3], values[3:]
        row = evidence["control"][arm][frame]
        allow = int(row["agc_allow"])
        need(allow in (0,1), "D8_AGC_ALLOW")
        need(bits(before[1:]) == bits(after[1:]), "D8_AGC_CONSTANTS")
        if constants is None:
            constants = bits(before[1:])
        need(bits(before[1:]) == constants, "D8_AGC_CONSTANTS")
        expected_before = f32(1.0) if frame == 0 or frame in resets else previous
        need(upstream.scalar_bits(before[0]) == upstream.scalar_bits(expected_before), "D8_AGC_CONTINUITY")
        need(upstream.scalar_bits(before[0]) == upstream.scalar_bits(float(row["gain_before"])) and
             upstream.scalar_bits(after[0]) == upstream.scalar_bits(float(row["gain_after"])),
             "D8_AGC_D1_STATE_BRIDGE")
        baseline_values = AGC.unpack_from(evidence["agc_traces"]["baseline"], frame*24)
        need(bits(before[1:]) == bits(baseline_values[1:3]), "D8_AGC_CONSTANTS")
        if arm == "baseline":
            oldrow = old[frame]
            wanted = [float(oldrow[k]) for k in ("state_gain_before","target_linear","limiter_linear",
                                                  "state_gain_after","target_linear","limiter_linear")]
            need(bits(values) == bits(wanted), "D8_ORIGINAL_AGC_STATE")
        signal = evidence["signals"][arm]["ns_output"][frame*160:(frame+1)*160]
        actual = evidence["signals"][arm]["agc_output"][frame*160:(frame+1)*160]
        floats, flags = d2.gain_observation(signal, before[0], allow, before[1], before[2])
        need(upstream.scalar_bits(after[0]) == upstream.scalar_bits(floats["expected_state_gain_after"]),
             "D8_AGC_STATE_EQUATION")
        applied, limit = floats["applied_gain"], before[2]
        peak_values = [f32(x*applied) for x in signal]
        reconstructed = [max(-limit,min(limit,x)) for x in peak_values]
        need(bits(reconstructed) == bits(actual), "D8_AGC_OUTPUT_RECONSTRUCTION")
        clamps = sum(upstream.scalar_bits(a) != upstream.scalar_bits(b) for a,b in zip(peak_values,reconstructed))
        if arm == "baseline":
            need(clamps == int(old[frame]["final_sample_clamp_count"]), "D8_ORIGINAL_AGC_CLAMPS")
        for key,field in (("target_gate_frames","target_gate_cap_active"),
                          ("output_gate_frames","output_gate_cap_active"),("peak_limit_frames","peak_cap_active")):
            counts[key] += flags[field]
        counts["clamped_samples"] += clamps
        rows.append({"frame":frame,**flags,"terminal_clamped_samples":clamps})
        previous = after[0]
    if arm == "baseline":
        need(bits(evidence["signals"][arm]["agc_output"]) == raw(prior/"replay_final.f32le"),
             "D8_ORIGINAL_AGC_OUTPUT")
    return {"counts":counts,"frames":rows,"state_identity":desc(evidence["paths"][arm]["agc_trace"]),
            "actual_state_and_full_float_output_bit_checked":True}

def screen_check(kind, values):
    required = values.get("required", True)
    need(type(required) is bool, "D8_SCREEN_APPLICABILITY")
    fields = ("delta",) if kind in ("primary","near") else ("baseline","candidate")
    numbers = [values.get(k) for k in fields]
    if kind == "counts" and any(v is not None and type(v) not in (int,float) for v in numbers):
        raise ValueError("D8_SCREEN_COUNT")
    if any(v is not None and (type(v) not in (int,float) or not math.isfinite(v)) for v in numbers):
        raise ValueError("D8_SCREEN_NONFINITE")
    if not required:
        return True
    if any(v is None for v in numbers):
        return False
    if kind == "primary":
        return numbers[0] >= 1.0
    if kind == "near":
        return numbers[0] >= 0.0
    baseline,candidate = numbers
    if kind == "projection":
        return baseline > -120.0 and candidate > -120.0 and candidate >= baseline
    if kind == "counts":
        need(all(type(v) is int and v >= 0 for v in numbers), "D8_SCREEN_COUNT")
    need(kind in ("energy","counts","recovery"), "D8_SCREEN_KIND")
    return candidate <= baseline

def applicability(reference, first, last):
    return reference is not None and last-first >= 16 and math.fsum(
        (float(x)/32768.0)**2 for x in reference[first:last]) > 1e-12

def score_shape(case, final, reference):
    end = case["samples"]-160
    windows = [[a,min(a+16000,end)] for a in range(0,end,16000)]
    for arm in ARMS:
        value = final[arm]
        need(value["offset_samples"] == 160,"D8_WRONG_OUTPUT_OFFSET")
        need(value["present"] is True and
             value["common"]["physical_sample_range"] == [0,end] and
             value["common"]["signal_sample_range"] == [160,case["samples"]] and
             [x["physical_sample_range"] for x in value["one_second_windows"]] == windows and
             [x["signal_sample_range"] for x in value["one_second_windows"]] ==
                [[a+160,b+160] for a,b in windows], "D8_WRONG_WINDOW")
        for span in [value["common"],*value["one_second_windows"]]:
            a,b = span["physical_sample_range"]
            applies = applicability(reference,a,b)
            score = span["near_si_sdr_db"]
            if applies:
                need(type(score) in (int,float) and math.isfinite(score) and
                     span["near_si_sdr_null_reason"] is None, "D8_SCORE_APPLICABILITY")
            else:
                reason = ("zero_energy_reference_or_short_span" if reference is not None else
                    "C_has_no_admitted_clean_near_reference" if case["group"] == "C" else "no_clean_near_reference")
                need(score is None and span["near_si_sdr_null_reason"] == reason, "D8_NULL_TO_ZERO")
            finite_number(span["rms_dbfs"], "D8_SCREEN_NONFINITE")
            finite_number(span["peak"], "D8_SCREEN_NONFINITE")
    return windows

def projection_values(case, reference, pcm, windows):
    def one(first,last,common):
        applies = applicability(reference,first,last)
        values = {}
        for arm in ARMS:
            values[arm] = None if not applies else quality.projection_gain_db(
                reference if common else reference[first:last],
                pcm[arm] if common else pcm[arm][first+160:last+160],
                160 if common else 0)
            if values[arm] is not None:
                finite_number(values[arm], "D8_SCREEN_NONFINITE")
        return values
    return {"common":one(0,case["samples"]-160,True),
            "windows":[one(a,b,False) for a,b in windows]}

def recovery_values(case, evidence):
    if case["scenario"] not in ("far-only","path-change","render-gap") or case["group"] != "A":
        return {arm:{"curve":[],"convergence_ms":None,"recovery_ms":None,"final_level":None,
                    "reason":"not_applicable"} for arm in ARMS}
    _, original, _, _ = paths(case)
    echo_name = next((x for x in case["auxiliary_inputs"] if x.endswith("echo.pcm")), None)
    need(echo_name is not None, "D8_RECOVERY_ECHO_SOURCE")
    echo = d1.samples(original/echo_name,"h",case["samples"])
    result = {}
    for arm in ARMS:
        curve = quality._window_erle(echo,evidence["final_pcm"][arm],16000,160)
        need(all(type(a) is int and type(b) in (int,float) and math.isfinite(b) for a,b in curve),
             "D8_SCREEN_NONFINITE")
        convergence = quality._settling_ms(curve,16000,0)
        recovery = quality._settling_ms(curve,16000,48000) if case["scenario"] != "far-only" else None
        tail = max(3,len(curve)//4)
        result[arm] = {"curve":[list(x) for x in curve], "convergence_ms":convergence,
            "recovery_ms":recovery,"final_level":statistics.median(v for _,v in curve[-tail:]) if curve else None,
            "semantics":"unchanged own-tail-relative3dB/three-window settling; not absolute quality",
            "recovery_required":case["scenario"] != "far-only"}
    return result

def compute_screens(case, final, scoring, projection, agc, recovery, clips):
    vetoes, checks = [], []
    primary = case["group"] == "A" and case["scenario"] in ("doubletalk-nominal","doubletalk-weak")
    def check(label,kind,values):
        passed = screen_check(kind,values)
        checks.append({"label":label,"kind":kind,"values":values,"passed":passed})
        if not passed:
            vetoes.append(label)
    if primary:
        check("primary_common_at_least1dB","primary",{"delta":scoring["common"]["delta_si_sdr_db"]})
    for label,score,gain in [("common",scoring["common"],projection["common"]),
                             *((str(i),s,g) for i,(s,g) in enumerate(zip(scoring["windows"],projection["windows"])))]:
        if score["applicable"]:
            check("near_nonregression:"+label,"near",{"delta":score["delta_si_sdr_db"]})
            check("anti_collapse:"+label,"projection",{**gain,"required":True})
    far = case["scenario"] in ("far-only","path-change","render-gap") and case["group"] == "A"
    if far or case["group"] == "C":
        pairs = [("common",final["baseline"]["common"],final["candidate"]["common"]),
                 *((str(i),a,b) for i,(a,b) in enumerate(zip(
                     final["baseline"]["one_second_windows"],final["candidate"]["one_second_windows"]))),
                 ("native_whole",final["baseline"]["native_whole_buffer_energy"],
                  final["candidate"]["native_whole_buffer_energy"])]
        for label,a,b in pairs:
            for metric in ("rms_dbfs","peak"):
                check("energy:"+label+":"+metric,"energy",{"baseline":a[metric],"candidate":b[metric]})
    check("S16_clip_count","counts",clips)
    check("AGC_terminal_clamps","counts",{arm:agc[arm]["counts"]["clamped_samples"] for arm in ARMS})
    if far:
        check("convergence","recovery",{**{arm:recovery[arm]["convergence_ms"] for arm in ARMS},"required":True})
        if case["scenario"] != "far-only":
            check("post_event_recovery","recovery",{**{arm:recovery[arm]["recovery_ms"] for arm in ARMS},"required":True})
    return {"primary":primary,"passed":not vetoes,"vetoes":vetoes,"checks":checks}

def scientific_files(case, form):
    arm, mode = form.split("-")
    sources = source_paths(case, True)[arm]
    if mode == "plain":
        return [sources["plain_pcm"],sources["plain_metrics"]]
    return sorted(set([*sources["streams"].values(),sources["pcm"],sources["metrics"],
        sources["control"],sources["trace"],sources["agc_trace"],sources["d1_receipt"],
        sources["upstream_receipt"]]),key=str)

def execution_argv(case, form, built):
    directory = OUTPUT / "scratch/current" / form
    original = paths(case)[1]
    return d1.mapped_argv(case, OUTPUT / built["programs"][form]["path"],directory,original)

def execution_environment(case, form):
    arm,mode = form.split("-")
    return build.environment(
        d1=OUTPUT/"scratch/current"/(arm+"-d1") if mode == "observed" else None,
        d8=OUTPUT/"scratch/current"/(arm+"-upstream") if mode == "observed" else None,
        frames=case["frames"] if mode == "observed" else None)

def retention_views(case):
    result = {}
    for arm,sources in source_paths(case).items():
        result[arm] = {}
        for field,value in sources.items():
            def pointer(path):
                if path is None:
                    return {"present":False,"root":None,"path":None,"bytes":0}
                for name,root in (("input",INPUT),("result",OUTPUT)):
                    if path.is_relative_to(root):
                        return {"root":name,"path":path.relative_to(root).as_posix()}
                raise ValueError("D8_FORGED_DEDUP")
            result[arm][field] = ({k:pointer(v) for k,v in value.items()}
                                  if field == "streams" else pointer(value))
    return result

def retention_operations(case, measured):
    live,final = source_paths(case,True),source_paths(case)
    operations = []
    def add(action,source,target):
        operations.append({"action":action,"source":str(source),
            "destination" if action == "move" else "equal_to":str(target),
            "identity":measured[str(source)]})
    for arm in ARMS:
        a,b = live[arm],final[arm]
        for field in ("pcm","metrics","control","trace","agc_trace","d1_receipt","upstream_receipt"):
            action = "discard_equal" if arm == "baseline" and field in ("pcm","metrics","control") else "move"
            add(action,a[field],b[field])
        for field in ("pcm","metrics"):
            add("discard_equal",a["plain_"+field],b[field])
        for name,path in a["streams"].items():
            target = b["streams"][name]
            if target is None:
                target = b["streams"]["reference"] # explicit measured absent AEC zero-length alias
            action = ("move" if (arm == "baseline" and name in HPF_LANES) or
                      (arm == "candidate" and name in UNIQUE) else "discard_equal")
            add(action,path,target)
    need(len(operations) == 42 and len({x["source"] for x in operations}) == 42,"D8_FORGED_DEDUP")
    return sorted(operations,key=lambda x:(x["action"] != "move",x["source"]))

def check_retention(case, receipt):
    expected_files = {str(p) for form in FORMS for p in scientific_files(case,form)}
    measured = receipt.get("measured_files",{})
    candidate = source_paths(case,True)["candidate"]
    need(str(candidate["trace"]) in measured,"D8_MISSING_ACTUAL_CANDIDATE_STATE")
    need(all(str(source_paths(case,True)[a]["agc_trace"]) in measured for a in ARMS),"D8_MISSING_AGC_STATE")
    need(set(measured) == expected_files and receipt.get("key") == case["key"] and
         receipt.get("frames") == case["frames"] and receipt.get("forms") == list(FORMS),
         "D8_FORGED_DEDUP")
    views = receipt.get("views",{})
    need(views.get("candidate",{}).get("control") == retention_views(case)["candidate"]["control"],
         "D8_FORCED_BASELINE_DOWNSTREAM")
    need(views == retention_views(case),"D8_FORGED_DEDUP")
    operations = retention_operations(case,measured)
    need(receipt.get("operations") == operations and receipt.get("actual_comparisons_before_dedup") is True and
         receipt.get("complete_independent_pipelines") is True,"D8_FORGED_DEDUP")
    for operation in operations:
        path = Path(operation.get("destination",operation.get("equal_to")))
        need(desc(path) == operation["identity"],"D8_FORGED_DEDUP")
    # Both actual states and all actual HPF lane descriptors exist independently.
    for field in ("trace",):
        need(measured[str(source_paths(case,True)["baseline"][field])] ==
             measured[str(source_paths(case,True)["candidate"][field])],"D8_FORGED_DEDUP")
    for name in HPF_LANES:
        need(measured[str(source_paths(case,True)["baseline"]["streams"][name])] ==
             measured[str(source_paths(case,True)["candidate"]["streams"][name])],"D8_FORGED_DEDUP")
    for form in FORMS:
        source = source_paths(case,True)[form.split("-")[0]]
        paths_ = (source["plain_pcm"],source["plain_metrics"]) if form.endswith("plain") else (source["pcm"],source["metrics"])
        need(measured[str(paths_[0])]["bytes"] == case["samples"]*2 and
             measured[str(paths_[1])]["bytes"] <= case["frames"]*2048,"D8_FORGED_DEDUP")

def retain_case(case):
    directory = paths(case)[0]
    measured = {str(path):desc(path) for form in FORMS for path in scientific_files(case,form)}
    operations = retention_operations(case,measured)
    receipt = {"schema_version":1,"experiment":EXPERIMENT,"key":case["key"],"frames":case["frames"],
        "forms":list(FORMS),"measured_files":measured,"operations":operations,"views":retention_views(case),
        "actual_comparisons_before_dedup":True,"complete_independent_pipelines":True,
        "absent_AEC_is_measured_zero_length":case["capture_only"],
        "actual_state_scope":["HPF","BF","AGC"],"unobserved_full_downstream_state_claimed":False}
    proof = directory/"retention.json"
    directory.mkdir(parents=True,exist_ok=False)
    dump(proof,receipt,compact=True)
    with build.budget().retirement(proof):
        for operation in operations:
            source = Path(operation["source"])
            if operation["action"] == "move":
                build.retain_move(source,Path(operation["destination"]),operation["identity"],proof)
            else:
                build.discard_equal(source,Path(operation["equal_to"]),proof)
    check_retention(case,receipt)

def retained_case(case,built=None):
    directory = paths(case)[0]
    build.exact_closure(directory,expected_case_files(case),"D8_CASE_CLOSURE",limit=25*1024*1024)
    receipt = read(directory/"retention.json")
    check_retention(case,receipt)
    sources = source_paths(case)
    if built is not None:
        check_observer_receipts(case,sources,built)
    value = load_case(case,sources)
    value["retention"] = receipt
    return value

def run(built):
    with Phase("run") as phase:
        completed = []
        for index,case in enumerate(catalogs()):
            need(529 <= case["frames"] <= 629 and case["samples"] == 160*case["frames"],"D8_CASE_GEOMETRY")
            with build.budget().case(case["frames"]):
                scratch = OUTPUT/"scratch/current"
                for name in contract()["retention"]["scratch_forms"]:
                    (scratch/name).mkdir(parents=True)
                for form in FORMS:
                    phase.run("%03d-%s"%(index,form),execution_argv(case,form,built),
                        env=execution_environment(case,form),scientific={"frames":case["frames"],"form":form,
                        "files":scientific_files(case,form)},stdout_limit=65536,stderr_limit=65536)
                sources = check_live_neutrality(case)
                check_observer_receipts(case,sources,built)
                evidence = load_case(case,sources)
                check_upstream(case,evidence)
                for arm in ARMS:
                    check_agc(case,evidence,arm)
                retain_case(case)
            completed.append(case["key"])
            phase.remaining()
        dump(OUTPUT/"run-index.json",{"experiment":EXPERIMENT,"source":built["source"],
             "completed":completed,"cases":catalogs(),"forms":list(FORMS),
             "status":"FOUR_FORMS_MEASURED_ORIGINAL_BRIDGES_EXACT"},compact=True)

def check_execution(receipt,case,form,built):
    need(receipt["argv"] == execution_argv(case,form,built),"D8_EXECUTION_ARGV")
    build.check_execution_environment(receipt,execution_environment(case,form))
    need(receipt.get("scientific",{}).get("frames") == case["frames"] and
         receipt["scientific"]["form"] == form,"D8_EXECUTION_GEOMETRY")

def check_run(built):
    build.check_phase(OUTPUT,"run")
    index = read(OUTPUT/"run-index.json")
    need(index == {"experiment":EXPERIMENT,"source":built["source"],
        "completed":[c["key"] for c in catalogs()],"cases":catalogs(),"forms":list(FORMS),
        "status":"FOUR_FORMS_MEASURED_ORIGINAL_BRIDGES_EXACT"},"D8_RUN_MATRIX")
    expected_commands = ["run-logs/%03d-%s.command.json"%(i,form)
                         for i,_ in enumerate(catalogs()) for form in FORMS]
    need(read(OUTPUT/"run-phase.json")["commands"] == expected_commands,"D8_RUN_MATRIX")
    for i,case in enumerate(catalogs()):
        for form in FORMS:
            receipt = build.check_command(OUTPUT/("run-logs/%03d-%s.command.json"%(i,form)))
            check_execution(receipt,case,form,built)

def case_result(case,old_case,built):
    evidence = retained_case(case,built)
    frames = check_upstream(case,evidence)
    agc = {arm:check_agc(case,evidence,arm) for arm in ARMS}
    reference = evidence["reference"]
    ref = normalized(reference) if reference is not None else None
    reason = "C_has_no_admitted_clean_near_reference" if case["group"] == "C" else "no_clean_near_reference"
    final = {arm:d1.measure_lane(normalized(evidence["final_pcm"][arm]),160,case["samples"],
                                ref,reason,True) for arm in ARMS}
    windows = score_shape(case,final,reference)
    projection = projection_values(case,reference,evidence["final_pcm"],windows)
    def one(a,b,left,right):
        applies = applicability(reference,a,b)
        delta = right["near_si_sdr_db"]-left["near_si_sdr_db"] if applies else None
        if delta is not None:
            finite_number(delta,"D8_SCREEN_NONFINITE")
        return {"physical_sample_range":[a,b],"applicable":applies,"delta_si_sdr_db":delta}
    scoring = {"common":one(0,case["samples"]-160,final["baseline"]["common"],final["candidate"]["common"]),
        "windows":[one(a,b,left,right) for (a,b),left,right in zip(windows,
            final["baseline"]["one_second_windows"],final["candidate"]["one_second_windows"])]}
    recovery = recovery_values(case,evidence)
    clips = {arm:sum(abs(v)>=32760 for v in evidence["final_pcm"][arm]) for arm in ARMS}
    stages = {}
    for arm in ARMS:
        stages[arm] = {}
        for name,offset in d1.LANES.items():
            if name in d1.AEC_LANES and case["capture_only"]:
                stage = {"present":False,"offset_samples":offset,"reason":"capture_only_route_has_no_AEC_call"}
            else:
                stage = d1.measure_lane(evidence["signals"][arm][name],offset,case["samples"],
                                        ref,reason,name in d1.NEAR_LANES)
            stages[arm][name] = stage
    need(stages["baseline"] == old_case["stages"] and
         evidence["control_counts"]["baseline"] == old_case["control_counts"] and
         evidence["events"]["baseline"] == old_case["events"],"D8_OLD_D1_SCORES")
    unchanged = case["scenario"] in ("near-only","silent-render")
    if unchanged:
        for field in ("traces","agc_traces","controls_raw","final_bytes"):
            byte_equal(evidence[field]["baseline"],evidence[field]["candidate"],"D8_NEAR_SILENT_MUTATION")
        for name in evidence["signals"]["baseline"]:
            byte_equal(bits(evidence["signals"]["baseline"][name]),bits(evidence["signals"]["candidate"][name]),
                       "D8_NEAR_SILENT_MUTATION")
        byte_equal(raw(evidence["paths"]["baseline"]["metrics"]),raw(evidence["paths"]["candidate"]["metrics"]),
                   "D8_NEAR_SILENT_MUTATION")
    result = {k:case[k] for k in ("key","group","profile","scenario","frames","samples","capture_only")}
    result.update(final_s16=final,scoring=scoring,scoring_method={"canonical":"si_sdr_span","lag_search":False,"offset_samples":160,"primary_min_delta_db":1.0,"near_min_delta_db":0.0,"projection_min_exclusive_db":-120.0},projection=projection,agc=agc,recovery=recovery,
        clip_counts=clips,stages=stages,
        controls={arm:{"counts":evidence["control_counts"][arm],"events":evidence["events"][arm]} for arm in ARMS},
        associations={"first_frame":{"frame":0,"effective_output_lag":frames[0]["effective_output_lag"],"scheduled_near":frames[0]["scheduled_near"]},
            "common":upstream.association(frames,0,case["samples"]-160),
            "windows":[upstream.association(frames,a,b) for a,b in windows],
            "whole":upstream.association(frames,0,case["samples"])},
        original_events=case["input_events"],source_placement_metadata=case["dimensions"],
        near_silent_exact=True if unchanged else None,
        screens=compute_screens(case,final,scoring,projection,agc,recovery,clips),
        retention_identity=desc(paths(case)[0]/"retention.json"),
        observations={"actual_HPFBF_state_equal":True,"actual_HPF_lanes_equal":True,
          "actual_AGC_state_recorded":True,"baseline_effective_lag_reconstruction_exact":True,
          "candidate_zero_lag_reconstruction_exact":True,"source_roles":"disclosed-regression",
          "independent_pipelines_including_SYNC":True,"unobserved_full_downstream_state_claimed":False})
    return result

def check_scoring_method(value):
    need(value.get("lag_search") is False and value.get("canonical") == "si_sdr_span","D8_LAG_SEARCH")
    need(type(value.get("offset_samples")) is int and value["offset_samples"] == 160,"D8_WRONG_OUTPUT_OFFSET")
    need(all(type(value.get(k)) in (int,float) and value[k] == wanted for k,wanted in
             (("primary_min_delta_db",1.0),("near_min_delta_db",0.0))),"D8_THRESHOLD_BOUNDARY")
    need(type(value.get("projection_min_exclusive_db")) in (int,float) and
         value["projection_min_exclusive_db"] == -120.0,"D8_PROJECTION_BOUNDARY")

def check_scoring_windows(case,reference,value):
    end = case["samples"]-160
    expected = [[a,min(a+16000,end)] for a in range(0,end,16000)]
    actual = [x["physical_sample_range"] for x in value["windows"]]
    if len(actual) < len(expected):
        missing = [span for span in expected if span not in actual]
        reason = "D8_OMITTED_SCORED_WINDOW" if any(applicability(reference,*span) for span in missing) else "D8_OMITTED_NULL_WINDOW"
        need(not missing,reason)
    need(actual == expected,"D8_WRONG_WINDOW")
    for span,score in zip([[0,end],*expected],[value["common"],*value["windows"]]):
        need(score["physical_sample_range"] == span and score["applicable"] is applicability(reference,*span),
             "D8_SCORE_APPLICABILITY")
        if not score["applicable"]:
            need(score["delta_si_sdr_db"] is None,"D8_NULL_TO_ZERO")
        else:
            finite_number(score["delta_si_sdr_db"],"D8_SCREEN_NONFINITE")

def check_screen_claim(value):
    reason = {"primary":"D8_THRESHOLD_BOUNDARY","near":"D8_THRESHOLD_BOUNDARY",
              "projection":"D8_PROJECTION_BOUNDARY"}.get(value["kind"],"D8_SCREEN_DECISION")
    need(type(value.get("passed")) is bool and
         value["passed"] is screen_check(value["kind"],value["values"]),reason)

def check_projection_claim(case,reference,pcm,claimed):
    windows = [[a,min(a+16000,case["samples"]-160)] for a in range(0,case["samples"]-160,16000)]
    expected = projection_values(case,reference,pcm,windows)
    need(claimed == expected,"D8_SILENT_FALSE_IMPROVEMENT")

def check_associations(actual,saved):
    need(saved["first_frame"]["effective_output_lag"] == actual["first_frame"]["effective_output_lag"],
         "D8_EFFECTIVE_LAG")
    need(saved["first_frame"]["scheduled_near"] == actual["first_frame"]["scheduled_near"],"D8_NEAR_SCHEDULE")
    for field,reason in (("effective_output_lag","D8_EFFECTIVE_LAG"),
                         ("scheduled_near","D8_NEAR_SCHEDULE"),("frames","D8_ASSOCIATION_COUNT")):
        need(saved["whole"][field] == actual["whole"][field],reason)
    need(saved == actual,"D8_ASSOCIATION_COUNT")

def check_agc_claim(actual,saved):
    need(saved == actual,"D8_AGC_OUTPUT_OR_CLAMP_FORGED")

def check_recovery_claim(actual,saved):
    for arm in ARMS:
        for field in ("convergence_ms","recovery_ms"):
            if actual[arm][field] is None:
                need(saved[arm][field] is None,"D8_RECOVERY_NONE_TO_ZERO")
        need(saved[arm]["curve"] == actual[arm]["curve"],"D8_RECOVERY_CURVE_CHANGE")
    need(saved == actual,"D8_RECOVERY_CURVE_CHANGE")

def check_saved_case(case,actual,saved):
    reference = (d1.samples(paths(case)[1]/case["inputs"]["clean_near"],"h",case["samples"])
                 if case["group"] == "A" and case["inputs"]["clean_near"] else None)
    check_scoring_method(saved["scoring_method"])
    score_shape(case,saved["final_s16"],reference)
    check_scoring_windows(case,reference,saved["scoring"])
    pcm = {arm:d1.samples(source_paths(case)[arm]["pcm"],"h",case["samples"]) for arm in ARMS}
    check_projection_claim(case,reference,pcm,saved["projection"])
    check_associations(actual["associations"],saved["associations"])
    check_agc_claim(actual["agc"],saved["agc"])
    check_recovery_claim(actual["recovery"],saved["recovery"])
    for value in saved["screens"]["checks"]:
        check_screen_claim(value)
    for key,reason in (("associations","D8_ASSOCIATION_COUNT"),("projection","D8_PROJECTION_RECOMPUTATION"),
                       ("recovery","D8_RECOVERY_CURVE_CHANGE"),("agc","D8_AGC_OUTPUT_OR_CLAMP_FORGED"),
                       ("scoring","D8_SCORE_RECOMPUTATION"),("screens","D8_SCREEN_DECISION")):
        need(saved[key] == actual[key],reason)
    need(saved == actual,"D8_CASE_READBACK")

def check_report_identity(saved,built):
    need(saved.get("source") == built["source"],"D8_REPORT_SOURCE")
    need([c["key"] for c in saved.get("cases",[])] == [c["key"] for c in catalogs()],"D8_MISSING_CASE")

def check_input_binding(actual,saved):
    need(actual == saved,"D8_INPUT_BINDING")

def analyze(phase,saved=None):
    build.check_phase(OUTPUT,"admission")
    inputs = input_identity(phase)
    check_input_binding(inputs,read(OUTPUT/"input-binding.json"))
    built = build.verify_build(phase)
    check_run(built)
    if saved is not None:
        check_report_identity(saved,built)
    old = read(INPUT/"original/result/report.json")
    cases = []
    for i,(case,old_case) in enumerate(zip(catalogs(),old["cases"])):
        need(case["key"] == old_case["key"],"D8_ORIGINAL_CASE")
        actual = case_result(case,old_case,built)
        if saved is not None:
            check_saved_case(case,actual,saved["cases"][i])
        cases.append(actual)
        phase.remaining()
    totals = {"cases":len(cases),"frames":sum(x["frames"] for x in cases),
        "samples":sum(x["samples"] for x in cases),
        "windows":sum(len(x["scoring"]["windows"]) for x in cases),
        "reference_cases":sum(x["scoring"]["common"]["applicable"] for x in cases),
        "primary_cases":sum(x["screens"]["primary"] for x in cases),
        "resets":sum(x["associations"]["whole"]["resets"] for x in cases)}
    need(totals == {"cases":60,"frames":35916,"samples":5746560,"windows":362,
                   "reference_cases":32,"primary_cases":16,"resets":8},"D8_MATRIX_TOTALS")
    passed = all(c["screens"]["passed"] for c in cases)
    report = {"schema_version":1,"experiment":EXPERIMENT,"freeze":FREEZE,"source":built["source"],
        "original_source":OLD,"original_artifact":contract()["original_admission"]["artifact"],
        "status":REVIEW if passed else NO_ADVANCE,"measurement_valid":True,"totals":totals,"cases":cases,
        "input_identity":inputs,"independent_pairs":4,"independent_views":False,
        "all16_primary_common_deltas":[{"key":c["key"],"delta_si_sdr_db":c["scoring"]["common"]["delta_si_sdr_db"]}
                                      for c in cases if c["screens"]["primary"]],
        "interpretation":{"one_preregistered_total_effect":True,"perceptual_or_statistical_claim":False,
          "primary_endpoint":"deliveredS16/32768 canonicalfixed160 SI-SDR","HPF_raw_clean_damage_claim":False,
          "material_screen":"each16 common delta>=1dB, conservative finite research allocation",
          "scope":"four correlated recorded pairs with disclosed synthetic broadside propagation"},
        "promotion_allowed":False,"automatic_followup":False,"models_executed":False,"physical_devices_executed":False}
    if saved is not None:
        need(report == saved,"D8_READBACK_REPORT")
    return report

_CURRENT_REPORT = None
_FATAL_FIXTURES = None
_NEGATIVE_REPORT = None
_NEGATIVE_CONTEXT = {}

def encode(value):
    return (json.dumps(value,sort_keys=True,separators=(",",":"),allow_nan=False)+"\n").encode()

def check_inventory_shape(value,expected_files,reason="D8_OUTPUT_CLOSURE"):
    need(type(value) is dict and set(value) == {"files","directories"},reason)
    files = value["files"]
    need(type(files) is dict and type(value["directories"]) is list,reason)
    for record in files.values():
        need(type(record) is dict,reason)
        need(record.get("type") != "symlink","D8_OUTPUT_SYMLINK")
        need(set(record) == {"bytes","sha256"} and type(record["bytes"]) is int and record["bytes"] >= 0 and
             re.fullmatch("[0-9a-f]{64}",record["sha256"]) is not None,reason)
    need(set(files) == set(expected_files) and len(value["directories"]) == len(set(value["directories"])) and
         set(value["directories"]) == build.directories(expected_files),reason)

def case_file_names():
    return {str((paths(case)[0]/name).relative_to(OUTPUT))
            for case in catalogs() for name in expected_case_files(case)}

def negative_file_names():
    value = read(OUTPUT/"negative-tests.json")
    files = dict(value["fixture_files"])
    if _FATAL_FIXTURES is not None:
        files.update(_FATAL_FIXTURES["fixture_files"])
    for name,record in files.items():
        need(name.startswith("negatives/") and not any(x in (".","..") for x in Path(name).parts),
             "D8_NEGATIVE_FILE_MAP")
        need(desc(OUTPUT/name) == record,"D8_NEGATIVE_FILE_MAP")
    return set(files)

def all_expected_files(built,*,late):
    names = case_file_names() | build.managed_files(built,include_late=late)
    names |= {"input-binding.json","run-index.json","report.json"}
    if late:
        names |= {"seal.json","readback.json","negative-tests.json","summary.json"}
        names |= negative_file_names()
    return names

def core_inventory(built):
    actual = build.inventory(OUTPUT)
    late = {name for name in actual["files"] if name in FINAL or
            name.startswith(("verify-logs/","negative-logs/","negatives/")) or
            name in ("verify-phase.json","negative-phase.json")}
    files = {k:v for k,v in actual["files"].items() if k not in late}
    value = {"files":files,"directories":sorted(build.directories(files))}
    check_inventory_shape(value,all_expected_files(built,late=False))
    # The complete walk may contain only core or explicitly admitted late roots.
    allowed_dirs = build.directories(actual["files"])
    need(set(actual["directories"]) == allowed_dirs,"D8_OUTPUT_CLOSURE")
    return value

def write_analysis_seal(phase):
    built = read(OUTPUT/"build/build.json")
    value = {"experiment":EXPERIMENT,"source":built["source"],"payload":core_inventory(built),
             "scope":"core analysis evidence; completion closes later verify/negative/final files"}
    dump(OUTPUT/"seal.json",value,compact=True)
    build.budget().check()

def check_seal():
    saved = read(OUTPUT/"seal.json")
    built = read(OUTPUT/"build/build.json")
    need(saved.get("experiment") == EXPERIMENT and saved.get("source") == built["source"],"D8_SEAL_IDENTITY")
    need(saved["payload"] == core_inventory(built),"D8_SEAL_PAYLOAD")
    return saved

def check_readback(value):
    need(value == {"experiment":EXPERIMENT,"status":"PASS","DSP_executed":False,"models_executed":False,
         "report":desc(OUTPUT/"report.json"),"seal":desc(OUTPUT/"seal.json"),
         "scope":"normal full original/source/actual waveform/state/window recomputation; not independent-author audit"},
         "D8_READBACK_RECEIPT")

def verify(phase):
    check_seal()
    report = read(OUTPUT/"report.json")
    return analyze(phase,report)

def qualify_negative_inputs(phase):
    global _NEGATIVE_REPORT
    build.check_phase(OUTPUT,"verify")
    check_readback(read(OUTPUT/"readback.json"))
    _NEGATIVE_REPORT = verify(phase)
    return {"status":"QUALIFIED","report":desc(OUTPUT/"report.json"),"seal":desc(OUTPUT/"seal.json"),
            "readback":desc(OUTPUT/"readback.json"),"normal_full_readback_qualified":True,
            "DSP_executed":False,"independent_author_audit":False}

def report_projection(report):
    cases = []
    for value in report["cases"]:
        cases.append({k:value[k] for k in ("key","group","profile","scenario","frames","samples","capture_only",
            "final_s16","scoring","scoring_method","projection","recovery","clip_counts","near_silent_exact","screens")} |
            {"agc_counts":{arm:value["agc"][arm]["counts"] for arm in ARMS}})
    return {"experiment":EXPERIMENT,"source":report["source"]["revision"],"freeze":FREEZE,
        "status":report["status"],"measurement_valid":report["measurement_valid"],"totals":report["totals"],
        "all16_primary_common_deltas":report["all16_primary_common_deltas"],"cases":cases,
        "interpretation":report["interpretation"],"promotion_allowed":False,
        "full_AGC_events_and_states":"retained in report.json and actual binary evidence",
        "independent_binary_audit_completed":False}

def completion_template():
    built = read(OUTPUT/"build/build.json")
    actual = build.inventory(OUTPUT)
    actual["files"].pop("completion.json",None)
    return {"schema_version":1,"experiment":EXPERIMENT,"completed":True,
        "source_revision":built["source"]["revision"],"status":read(OUTPUT/"report.json")["status"],
        "measurement_valid":True,"payload":actual,
        "promotion_allowed":False,"root_budget_seconds":1200,
        "all_phases":["admission","baseline-build","candidate-build","run","analysis","verify","negative"],
        "own_file_bytes":0}

def check_completion_shape(value):
    need(value.get("schema_version") == 1 and value.get("experiment") == EXPERIMENT and
         value.get("completed") is True and value.get("measurement_valid") is True and
         value.get("status") in (NO_ADVANCE,REVIEW) and value.get("promotion_allowed") is False and
         value.get("root_budget_seconds") == 1200 and value.get("all_phases") ==
         ["admission","baseline-build","candidate-build","run","analysis","verify","negative"],
         "D8_MISSING_FINALIZATION")
    need(type(value.get("own_file_bytes")) is int and value["own_file_bytes"] >= 0,"D8_MISSING_FINALIZATION")

def check_completion(value,built):
    check_completion_shape(value)
    for name in value["all_phases"]:
        build.check_phase(OUTPUT,name)
    need(value["source_revision"] == built["source"]["revision"],"D8_REPORT_SOURCE")
    check_inventory_shape(value["payload"],all_expected_files(built,late=True))
    actual = build.inventory(OUTPUT)
    complete = actual["files"].pop("completion.json")
    need(actual == value["payload"] and complete["bytes"] == value["own_file_bytes"],
         "D8_MISSING_FINALIZATION")
    check_seal()
    check_readback(read(OUTPUT/"readback.json"))
    build.budget().check()

def finalizer(phase,report,negative_report):
    check_seal()
    check_readback(read(OUTPUT/"readback.json"))
    need(negative_report["status"] == "PASS","D8_NEGATIVES_FAILED")
    need(read(OUTPUT/"negative-tests.json") == negative_report,"D8_NEGATIVES_READBACK")
    need(negative_report["supervisor_fatal_fixtures"] == _FATAL_FIXTURES,"D8_FIXTURE_RECEIPT")
    projection = report_projection(report)
    dump(OUTPUT/"summary.json",projection,compact=True)
    built = read(OUTPUT/"build/build.json")
    inventory = build.inventory(OUTPUT)
    check_inventory_shape(inventory,all_expected_files(built,late=True))
    completion = completion_template()
    for _ in range(8):
        data = encode(completion)
        if completion["own_file_bytes"] == len(data):
            break
        completion["own_file_bytes"] = len(data)
    else:
        raise ValueError("D8_COMPLETION_SIZE")
    build.bounded_write(OUTPUT/"completion.json",data)
    check_completion(completion,built)
    export = encode({"D8_RESULT":projection,"completion":desc(OUTPUT/"completion.json"),
                     "report":desc(OUTPUT/"report.json"),"negatives":desc(OUTPUT/"negative-tests.json")})
    need(len(export) <= EXPORT_LIMIT,"D8_EXPORT_BOUND")
    phase.remaining()
    sys.stdout.buffer.write(export)
    sys.stdout.flush()
    phase.remaining()
    build.finish_job(OUTPUT/"completion.json")

def main():
    global _CURRENT_REPORT,_FATAL_FIXTURES
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-head",required=True)
    args = parser.parse_args()
    need(os.environ.get("GITHUB_ACTIONS") == "true","D8_ACTIONS_ONLY")
    need(not OUTPUT.exists() and not OUTPUT.is_symlink() and not INPUT.exists() and not INPUT.is_symlink(),
         "D8_NEW_OUTPUT_REQUIRED")
    build.start_job()
    try:
        admit()
        built = build.build(args.expected_head)
        run(built)
        with Phase("analysis") as phase:
            _CURRENT_REPORT = analyze(phase)
            dump(OUTPUT/"report.json",_CURRENT_REPORT,compact=True)
            phase.finalizer = write_analysis_seal
        with Phase("verify") as phase:
            verify(phase)
            dump(OUTPUT/"readback.json",{"experiment":EXPERIMENT,"status":"PASS",
                "DSP_executed":False,"models_executed":False,"report":desc(OUTPUT/"report.json"),
                "seal":desc(OUTPUT/"seal.json"),
                "scope":"normal full original/source/actual waveform/state/window recomputation; not independent-author audit"})
        with Phase("negative") as phase:
            _FATAL_FIXTURES = build.run_fatal_fixtures()
            import test_dualmic_broadside_output_d8 as tests
            negatives = tests.actual_negatives(phase,fatal_fixture_files=_FATAL_FIXTURES["fixture_files"])
            negatives["supervisor_fatal_fixtures"] = _FATAL_FIXTURES
            dump(OUTPUT/"negative-tests.json",negatives,compact=True,replace=True)
            phase.finalizer = lambda current:finalizer(current,_CURRENT_REPORT,negatives)
        return 0
    except BaseException as error:
        if build.FINISHED:
            os._exit(1)
        # The Phase retains only the first bounded failure while its deadline is live.
        # Fatal expiry is external SIGKILL or local immediate exit: no cleanup branch.
        build.job_remaining()
        failure = {"experiment":EXPERIMENT,"status":"MEASUREMENT_INVALID",
            "type":type(error).__name__,"reason":str(error) if isinstance(error,ValueError) else "execution failed",
            "promotion_allowed":False}
        if not (OUTPUT/"first-failure.json").exists():
            dump(OUTPUT/"first-failure.json",failure)
        sys.stderr.write(json.dumps(failure,sort_keys=True)+"\n")
        sys.stderr.flush()
        return 1

def _negative_case(case):
    need(_NEGATIVE_REPORT is not None,"D8_NEGATIVE_NOT_QUALIFIED")
    if case["key"] not in _NEGATIVE_CONTEXT:
        built = read(OUTPUT/"build/build.json")
        evidence = retained_case(case,built)
        saved = next(x for x in _NEGATIVE_REPORT["cases"] if x["key"] == case["key"])
        _NEGATIVE_CONTEXT[case["key"]] = (evidence,saved)
    return _NEGATIVE_CONTEXT[case["key"]]

def _material(data,origin,scope,name,guard,mutation=None):
    return {"raw":data if isinstance(data,bytes) else encode(data),"origin":origin,"scope":scope,
            "guard_name":"dualmic_broadside_output_d8."+name,"guard":guard,"mutation":mutation or {}}

def negative_material(category,phase):
    need(_NEGATIVE_REPORT is not None,"D8_NEGATIVE_NOT_QUALIFIED")
    cases = catalogs()
    case = cases[0]
    evidence,saved = _negative_case(case)
    built = read(OUTPUT/"build/build.json")
    a = evidence["paths"]["baseline"]
    base_trace = evidence["traces"]["baseline"]
    base_signals = evidence["signals"]["baseline"]
    base_control = evidence["control"]["baseline"]
    trace_categories = {"hpf_state_before","hpf_state_after","hpf_channel_order","bf_state_before",
        "bf_state_after","bf_history","bf_lag_scores","bf_lag","score_updates","fallback_route",
        "track_direction","trace_geometry"}
    if category in trace_categories:
        return _material(base_trace,str(a["trace"]),"actual_binary","baseline_frame_trace",
            lambda p:baseline_frame_trace(case,base_signals,p.read_bytes(),base_control))
    if category in ("raw_left","raw_right","hpf_left","hpf_right"):
        name = {"raw_left":"hpf_input_l","raw_right":"hpf_input_r",
                "hpf_left":"hpf_output_l","hpf_right":"hpf_output_r"}[category]
        def guard(path):
            signals = dict(base_signals)
            signals[name] = d1.samples(path,"f",case["samples"])
            if category.startswith("raw_"):
                upstream_guard(upstream.check_raw,signals,evidence["stereo"])
            else:
                baseline_frame_trace(case,signals,base_trace,base_control)
        return _material(raw(a["streams"][name]),str(a["streams"][name]),"actual_binary",
                         "upstream_guard" if category.startswith("raw_") else "baseline_frame_trace",guard)
    if category == "bf_output":
        bridge = "ns_input" if case["capture_only"] else "aec_input"
        return _material(raw(a["streams"]["bf_output"]),str(a["streams"]["bf_output"]),"actual_binary",
            "byte_equal",lambda p:byte_equal(p.read_bytes(),raw(a["streams"][bridge]),"D8_BF_OUTPUT"))
    if category in ("tracking_off","missing_actual_candidate_state"):
        arm = "baseline" if category == "tracking_off" else "candidate"
        def guard(path):
            copied = dict(evidence,traces=dict(evidence["traces"]))
            copied["traces"][arm] = path.read_bytes()
            check_upstream(case,copied)
        return _material(evidence["traces"][arm],str(evidence["paths"][arm]["trace"]),
                         "actual_binary","check_upstream",guard)
    if category == "missing_AGC_state":
        def guard(path):
            copied = dict(evidence,agc_traces=dict(evidence["agc_traces"]))
            copied["agc_traces"]["candidate"] = path.read_bytes()
            check_agc(case,copied,"candidate")
        return _material(evidence["agc_traces"]["candidate"],str(evidence["paths"]["candidate"]["agc_trace"]),
                         "actual_binary","check_agc",guard)
    if category == "reset_coordinate":
        selected = next(c for c in cases if any(e["kind"] == "cli_discontinuity" for e in c["input_events"]))
        index = next(i for i,e in enumerate(selected["input_events"]) if e["kind"] == "cli_discontinuity")
        return _material(selected,"original input-lock#"+selected["key"],"actual_report","upstream_guard",
                         lambda p:upstream_guard(upstream.check_events,read(p)),{"path":["input_events",index,"frame"]})
    if category == "spurious_path_reset":
        selected = next(c for c in cases if any(e["kind"] == "cli_echo_path_change" for e in c["input_events"]))
        context,_ = _negative_case(selected)
        return _material(context["traces"]["baseline"],str(context["paths"]["baseline"]["trace"]),
            "actual_binary","baseline_frame_trace",lambda p:baseline_frame_trace(selected,
                context["signals"]["baseline"],p.read_bytes(),context["control"]["baseline"]),{"frame":300})
    old_cases = {"old_PCM":("pcm","D8_OLD_PCM"),"old_metrics_JSONL":("metrics","D8_OLD_METRICS_JSONL"),
                 "old_D1_lane":("agc_output","D8_OLD_D1_LANE"),"old_control":("control","D8_OLD_CONTROL")}
    if category in old_cases:
        field,reason = old_cases[category]
        path = a["streams"][field] if field in d1.LANES else a[field]
        expected = raw(path)
        return _material(expected,str(path)+" (qualified actual baseline bridge retained by original pointer)",
            "actual_binary","byte_equal",lambda p:byte_equal(p.read_bytes(),expected,reason))
    if category in ("effective_lag","near_schedule","association_count"):
        path = {"effective_lag":["first_frame","effective_output_lag"],
                "near_schedule":["first_frame","scheduled_near"],"association_count":["whole","frames"]}[category]
        return _material(saved["associations"],"report.json#"+case["key"]+"/associations","actual_report",
            "check_associations",lambda p:check_associations(saved["associations"],read(p)),{"path":path})
    if category in ("wrong_window","null_to_zero"):
        selected = case if category == "wrong_window" else next(c for c in cases if c["inputs"]["clean_near"] is None)
        context,value = _negative_case(selected)
        path = (["candidate","common","physical_sample_range",0] if category == "wrong_window" else
                ["candidate","common","near_si_sdr_db"])
        return _material(value["final_s16"],"report.json#"+selected["key"]+"/final_s16","actual_report",
            "score_shape",lambda p:score_shape(selected,read(p),context["reference"]),{"path":path})
    if category in ("wrong_output_offset","lag_search","threshold_boundary","projection_boundary"):
        key = {"wrong_output_offset":"offset_samples","lag_search":"lag_search",
               "threshold_boundary":"primary_min_delta_db","projection_boundary":"projection_min_exclusive_db"}[category]
        scope = "synthetic_engineering" if category in ("threshold_boundary","projection_boundary") else "actual_report"
        origin = ("fixed preregistered screen policy, not observed audio" if scope == "synthetic_engineering" else
                  "report.json#"+case["key"]+"/scoring_method")
        return _material(saved["scoring_method"],origin,scope,"check_scoring_method",
                         lambda p:check_scoring_method(read(p)),{"path":[key]})
    if category in ("omitted_bad_window","omitted_null_window"):
        selected,context,value,index,selection = None,None,None,None,None
        for current in cases:
            current_value = next(x for x in _NEGATIVE_REPORT["cases"] if x["key"] == current["key"])
            for i,row in enumerate(current_value["scoring"]["windows"]):
                desired = row["delta_si_sdr_db"] is None if category == "omitted_null_window" else (
                    row["delta_si_sdr_db"] is not None and row["delta_si_sdr_db"] < 0)
                if desired:
                    selected,index,selection = current,i,"null" if category == "omitted_null_window" else "adverse"
                    break
            if selected is not None:
                break
        if selected is None:
            need(category == "omitted_bad_window","D8_TEST_NULL_APPLICABILITY")
            selected = case
            _,first = _negative_case(selected)
            index = next(i for i,row in enumerate(first["scoring"]["windows"]) if row["applicable"])
            selection = "geometry"
        context,value = _negative_case(selected)
        return _material(value["scoring"],"report.json#"+selected["key"]+"/scoring","actual_report",
            "check_scoring_windows",lambda p:check_scoring_windows(selected,context["reference"],read(p)),
            {"path":["windows"],"index":index,"selection":selection,"condition_path":["delta_si_sdr_db"]})
    if category == "silent_false_improvement":
        selected = next((c for c,v in zip(cases,_NEGATIVE_REPORT["cases"]) if
                         v["projection"]["common"]["candidate"] is not None and
                         v["projection"]["common"]["candidate"] > -120),None)
        need(selected is not None,"D8_SILENT_CONTROL_NO_APPLICABLE_ACTUAL_SPAN")
        context,value = _negative_case(selected)
        def guard(path):
            pcm = dict(context["final_pcm"])
            pcm["candidate"] = d1.samples(path,"h",selected["samples"])
            check_projection_claim(selected,context["reference"],pcm,value["projection"])
        return _material(context["final_bytes"]["candidate"],str(context["paths"]["candidate"]["pcm"]),
                         "actual_binary","check_projection_claim",guard)
    if category in ("forged_dedup","forced_baseline_downstream"):
        receipt = evidence["retention"]
        path = (["views","candidate","control","path"] if category == "forced_baseline_downstream" else
                ["measured_files",str(source_paths(case,True)["candidate"]["trace"]),"sha256"])
        return _material(receipt,str(paths(case)[0]/"retention.json"),"actual_report","check_retention",
                         lambda p:check_retention(case,read(p)),{"path":path})
    if category == "near_silent_mutation":
        return _material(evidence["final_bytes"]["candidate"],str(evidence["paths"]["candidate"]["pcm"]),
            "actual_binary","byte_equal",lambda p:byte_equal(p.read_bytes(),evidence["final_bytes"]["baseline"],
                                                            "D8_NEAR_SILENT_MUTATION"))
    if category == "AGC_output_or_clamp_forged":
        return _material(saved["agc"],"report.json#"+case["key"]+"/agc","actual_report","check_agc_claim",
            lambda p:check_agc_claim(saved["agc"],read(p)),{"path":["candidate","counts","clamped_samples"]})
    if category in ("recovery_None_to_zero","recovery_curve_change"):
        selected = next(c for c in cases if c["group"] == "A" and c["scenario"] == "far-only")
        _,value = _negative_case(selected)
        path = ["candidate","recovery_ms"] if category == "recovery_None_to_zero" else ["candidate","curve",0,1]
        return _material(value["recovery"],"report.json#"+selected["key"]+"/recovery","actual_report",
            "check_recovery_claim",lambda p:check_recovery_claim(value["recovery"],read(p)),
            {"path":path,"null_role":"not_applicable_far_only; requiredNone refusal separately tested in engineering"})
    if category in ("missing_case","report_source"):
        header = {"source":_NEGATIVE_REPORT["source"],"cases":[{"key":c["key"]} for c in cases]}
        return _material(header,"report.json#identity","actual_report","check_report_identity",
            lambda p:check_report_identity(read(p),built),
            {"path":["cases"] if category == "missing_case" else ["source","revision"]})
    if category in ("extra_file","extra_dir","output_symlink"):
        value = check_seal()["payload"]
        first = next(iter(value["files"]))
        path = ["files"] if category == "extra_file" else ["directories"] if category == "extra_dir" else ["files",first]
        return _material(value,"seal.json#payload (actual inventory slice, not a new filesystem walk)",
            "actual_inventory","check_inventory_shape",
            lambda p:check_inventory_shape(read(p),set(value["files"])),{"path":path})
    if category == "execution_argv":
        receipt = read(OUTPUT/"run-logs/000-baseline-plain.command.json")
        return _material(receipt,"run-logs/000-baseline-plain.command.json","actual_report","check_execution",
            lambda p:check_execution(read(p),case,"baseline-plain",built),{"path":["argv"]})
    if category.startswith("failed_") and category.endswith("_phase"):
        name = {"failed_build_phase":"baseline-build","failed_run_phase":"run",
                "failed_analysis_phase":"analysis","failed_verify_phase":"verify"}[category]
        return _material(read(OUTPUT/(name+"-phase.json")),name+"-phase.json","actual_report",
            "phase_record_guard",lambda p:phase_record_guard(read(p),name),{"path":["status"]})
    if category == "failed_command":
        receipt = read(OUTPUT/"run-logs/000-baseline-plain.command.json")
        return _material(receipt,"run-logs/000-baseline-plain.command.json","actual_report",
            "command_record_guard",lambda p:command_record_guard(read(p)),{"path":["status"]})
    if category == "saved_admission":
        return _material(read(INPUT/"admission.json"),"input/admission.json","actual_report","receipt_admission",
            lambda p:receipt_admission(read(p)),{"path":["source_revision"]})
    if category == "input_binding":
        actual = read(OUTPUT/"input-binding.json")
        return _material(actual,"input-binding.json","actual_report","check_input_binding",
            lambda p:check_input_binding(actual,read(p)),{"path":["cases",0,"inputs","mic","sha256"]})
    if category == "readback_receipt":
        return _material(read(OUTPUT/"readback.json"),"readback.json","actual_report","check_readback",
            lambda p:check_readback(read(p)),{"path":["status"]})
    if category == "control_header_overflow":
        return _material(evidence["controls_raw"]["candidate"],str(evidence["paths"]["candidate"]["control"]),
            "actual_binary","check_control_bytes",lambda p:check_control_bytes(p.read_bytes(),case["frames"]),
            {"frames":case["frames"]})
    if category == "missing_finalization":
        template = completion_template()
        return _material(template,"prospective terminal shape bound to current actual inventory; not yet completed",
            "pre_finalization_template","check_completion_shape",lambda p:check_completion_shape(read(p)),
            {"path":["completed"]})
    return build.negative_material(category,phase)

def phase_record_guard(value,name):
    return build.check_phase_record(value,name)

def command_record_guard(value):
    return build.check_command_record(value)

if __name__ == "__main__":
    raise SystemExit(main())
