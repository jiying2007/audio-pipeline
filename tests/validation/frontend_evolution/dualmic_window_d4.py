#!/usr/bin/env python3
"""D4 read-only fixed-window joins of admitted original D1/D2 evidence."""
from __future__ import annotations
import argparse
import csv
import hashlib
import io
import json
import math
from pathlib import Path
import shutil
import statistics
import struct
import subprocess
import time

import dualmic_gain_d2 as d2
import dualmic_zero_d3_source as admission
from dualmic_stages_source import digest, dump, need, remaining

ROOT = admission.ROOT
EXPERIMENT = "FE-DUALMIC-WINDOW-D4"
FREEZE = "29a04701d8d555e46c82ecde86e83175fb16d526"
SELF = "tests/validation/frontend_evolution/dualmic_window_d4.py"
TEST = "tests/validation/frontend_evolution/test_dualmic_window_d4.py"
PLAN = "docs/research/frontend-evolution-v1/DUALMIC_WINDOW_D4_PLAN.zh-CN.md"
LOCK = "docs/research/frontend-evolution-v1/dualmic-window-d4-input-lock.json"
WORKFLOW = ".github/workflows/frontend-research.yml"
PINS = {PLAN: "21505125478bc472a44cf6cca174ce87eed950bb",
        LOCK: "230aff8c36aae1c3379961434b0443efeb868509"}
COPIES = {"admission.json": "admission.json",
          "original-d2-report.json": "original/gain-d2/report.json",
          "original-d1-report.json": "original/result/report.json",
          "original-d2-manifest.json": "original/gain-d2/artifact-manifest.json"}

def descriptor(path):
    return {"bytes": path.stat().st_size, "sha256": digest(path)}

def blob(raw):
    return hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()

def frozen():
    for name, expected in PINS.items():
        need(blob((ROOT/name).read_bytes()) == expected, "D4_FROZEN_CONTRACT_CHANGED")
    lock = d2.read_json(ROOT/LOCK)
    for name, expected in lock["helper_git_blobs"].items():
        need(blob((ROOT/name).read_bytes()) == expected, "D4_READER_CHANGED")
    admission.frozen_lock()
    return lock

def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT, timeout=30).decode().strip()

def source_names(lock):
    return {SELF, TEST, PLAN, LOCK, WORKFLOW, *lock["helper_git_blobs"]}

def source_proof(lock):
    names = source_names(lock)
    head, tree = git("rev-parse", "HEAD"), git("rev-parse", "HEAD^{tree}")
    for name in names:
        need(git("rev-parse", head+":"+name) == blob((ROOT/name).read_bytes()),
             "D4_UNCOMMITTED_SOURCE")
    return {"revision": head, "tree": tree,
            "files": {name: descriptor(ROOT/name) for name in sorted(names)}}

def original(input_root, lock, start):
    receipt = d2.read_json(input_root/"admission.json")
    need(receipt["status"] == "INPUT_ADMITTED_NO_DSP_EXECUTION" and
         receipt["DSP_executed"] is False and receipt["models_executed"] is False and
         receipt["freeze"] == admission.FREEZE and receipt["artifact"] == lock["artifact"] and
         receipt["source_revision"] == lock["source_revision"] and
         receipt["original_D2_readback_exact"] is True and receipt["case_count"] == lock["cases"] and
         receipt["frames"] == lock["frames"] and receipt["samples"] == lock["samples"] and
         receipt["budget_seconds"] == 300 and 0 <= receipt["elapsed_seconds"] <= 300,
         "D4_ORIGINAL_NOT_ADMITTED")
    prior, parent = input_root/"original/gain-d2", input_root/"original/result"
    need(digest(prior/"report.json") == lock["report_sha256"] and
         digest(prior/"artifact-manifest.json") == lock["manifest_sha256"],
         "D4_ORIGINAL_D2_REPORT_CHANGED")
    need(d2.read_json(prior/"artifact-manifest.json")["files"] == d2.payload_inventory(prior),
         "D4_ORIGINAL_D2_PAYLOAD_CHANGED")
    binding = d2.read_json(prior/"parent-binding.json")
    for name, key in (("report.json","report"), ("artifact-manifest.json","manifest"),
                      ("readback.json","readback"), ("run-index.json","run_index"),
                      ("build/build-manifest.json","build_manifest")):
        need(descriptor(parent/name) == binding[key], "D4_PARENT_BINDING_CHANGED")
    need(d2.read_json(parent/"artifact-manifest.json")["files"] == d2.d1.payload_inventory(parent),
         "D4_ORIGINAL_D1_PAYLOAD_CHANGED")
    old_lock = d2.input_lock()
    d2.verify_sources(prior, old_lock)
    remaining(start,300)
    return prior, parent, old_lock

def finite_zero(signal):
    need(all(math.isfinite(x) for x in signal), "D4_NONFINITE_SIGNAL")
    return all(x == 0.0 for x in signal)

def gain_rows(prior, parent, entry):
    case = entry["catalog"]
    directory = prior/"cases"/case["key"]
    taps = parent/"cases"/case["key"]/"taps"
    for name, expected in entry["parent_taps"].items():
        need(descriptor(taps/name) == expected, "D4_ORIGINAL_INPUT_CHANGED")
    raw = (taps/"ns_output.f32le").read_bytes()
    need(len(raw) == case["samples"]*4, "D4_INPUT_SIZE")
    values = struct.unpack("<"+str(case["samples"])+"f", raw)
    controls = d2.control_bytes(taps/"control.csv", case)
    need((directory/"control.bin").read_bytes() == controls, "D4_CONTROLS_CHANGED")
    reader = csv.DictReader(io.StringIO((directory/"views/gain.csv").read_text()))
    need(reader.fieldnames == d2.TRACE_FIELDS, "D4_TRACE_SCHEMA")
    rows = list(reader)
    need(len(rows) == case["frames"], "D4_TRACE_COUNT")
    result = []
    for index, (row, ctl) in enumerate(zip(rows, struct.iter_unpack("<IIff",controls))):
        allow, reset, before, after = ctl
        need(int(row["frame"]) == index and int(row["allow"]) == allow and int(row["reset"]) == reset,
             "D4_ORIGINAL_ROW_ID")
        floats = {name: d2.f32(float(row[name])) for name in d2.TRACE_FIELDS
                  if name not in d2.INT_FIELDS and row[name] != ""}
        need(all(math.isfinite(v) for v in floats.values()), "D4_NONFINITE_TRACE")
        need(d2.same_float(floats["state_gain_before"], before) and
             d2.same_float(floats["state_gain_after"], after), "D4_CONTROL_STATE_MISMATCH")
        zero = finite_zero(values[index*160:(index+1)*160])
        need(zero == (floats["input_peak"] == 0.0), "D4_ZERO_PEAK_DISAGREES")
        flags = {name: int(row[name]) for name in d2.CAP_FIELDS}
        need(allow in (0,1) and reset in (0,1) and all(v in (0,1) for v in flags.values()),
             "D4_INVALID_FLAGS")
        result.append({"frame": index, "native_sample_range": [index*160,(index+1)*160],
                       "zero": zero, "allow": allow, "reset": reset, **flags,
                       "state_before": before, "state_after": after,
                       "applied_gain": floats["applied_gain"],
                       "input_peak": floats["input_peak"], "input_rms": floats["input_rms"]})
    return result

def span_summary(rows, first, last):
    need(0 <= first < last <= len(rows), "D4_FRAME_SPAN")
    selected = rows[first:last]
    need([r["frame"] for r in selected] == list(range(first,last)), "D4_FRAME_ORDER")
    directions = {kind: {"up":0,"down":0,"unchanged":0} for kind in ("zero","nonzero")}
    for r in selected:
        direction = "up" if r["state_after"] > r["state_before"] else (
            "down" if r["state_after"] < r["state_before"] else "unchanged")
        directions["zero" if r["zero"] else "nonzero"][direction] += 1
    zero = sum(r["zero"] for r in selected)
    need(sum(directions["zero"].values()) == zero and
         sum(directions["nonzero"].values()) == len(selected)-zero, "D4_COUNT_CLOSURE")
    ranges = {}
    for key in ("state_before","state_after","applied_gain","input_peak","input_rms"):
        vals = [r[key] for r in selected]
        ranges[key] = {"first":vals[0],"last":vals[-1],"min":min(vals),"max":max(vals)}
    return {"original_frame_range": [first,last], "control_frame_shift":0,
            "frames":len(selected), "zero_frames":zero, "nonzero_frames":len(selected)-zero,
            "state_update_directions":directions, "ranges":ranges,
            "sum_absolute_same_row_state_update":sum(abs(r["state_after"]-r["state_before"]) for r in selected),
            "allow_counts":{"0":sum(r["allow"] == 0 for r in selected),
                            "1":sum(r["allow"] == 1 for r in selected)},
            "event_frame_ids":{key:[r["frame"] for r in selected if r[key]] for key in
                               ("reset","target_gate_cap_active","output_gate_cap_active","peak_cap_active")}}

def payload(input_root, start):
    lock = frozen()
    prior,parent,old_lock = original(input_root,lock,start)
    proof = source_proof(lock)
    d1_report,d2_report = d2.read_json(parent/"report.json"),d2.read_json(prior/"report.json")
    need(len(d1_report["cases"]) == len(d2_report["cases"]) == len(old_lock["cases"]) == 60,
         "D4_CASE_COUNT")
    cases=[]; total_windows=0; total_resets=0; total_frames=0
    for entry,first,second in zip(old_lock["cases"],d1_report["cases"],d2_report["cases"]):
        catalog=entry["catalog"]; key=catalog["key"]; n=catalog["samples"]
        need(first["key"] == second["key"] == key, "D4_CASE_ORDER")
        need(second["stages"]["pre_agc"] == first["stages"]["ns_output"] and
             second["stages"]["replay_final"] == first["stages"]["agc_output"], "D4_ENDPOINT_DIFFERS")
        rows=gain_rows(prior,parent,entry)
        native=span_summary(rows,0,len(rows))
        common=span_summary(rows,1,len(rows))
        spans=[[a,min(a+16000,n-160)] for a in range(0,n-160,16000)]
        need(len(second["stages"]["pre_agc"]["one_second_windows"]) == len(spans), "D4_WINDOW_COUNT")
        windows=[]
        for index,(a,b) in enumerate(spans):
            need(a%160 == b%160 == 0, "D4_FRAME_ALIGNMENT")
            metrics={name:stage["one_second_windows"][index] for name,stage in second["stages"].items()}
            changes={name:delta["one_second_windows"][index]
                     for name,delta in second["ordered_conditional_changes"].items()}
            for m in metrics.values():
                need(m["physical_sample_range"] == [a,b] and m["signal_sample_range"] == [a+160,b+160],
                     "D4_ORIGINAL_WINDOW_COORDINATES")
            for d in changes.values():
                need(d["physical_sample_range"] == [a,b], "D4_DELTA_COORDINATES")
            joined=span_summary(rows,(a+160)//160,(b+160)//160)
            windows.append({"index":index,"physical_sample_range":[a,b],
                            "signal_sample_range":[a+160,b+160],"gain":joined,
                            "original_d2_stages":metrics,"original_d2_changes":changes})
        need(sum(w["gain"]["frames"] for w in windows) == len(rows)-1 and
             sum(w["gain"]["zero_frames"] for w in windows) == common["zero_frames"],
             "D4_WINDOW_COVERAGE")
        resets=[{"original_frame":r["frame"],"native_sample_range":r["native_sample_range"],
                 "aligned_output_physical_range":[r["frame"]*160-160,r["frame"]*160],
                 "window_index":None if r["frame"] == 0 else (r["frame"]-1)//100}
                for r in rows if r["reset"]]
        directory=prior/"cases"/key
        cases.append({"key":key,"group":catalog["group"],"profile":catalog["profile"],
                      "scenario":catalog["scenario"],"frames":catalog["frames"],"samples":n,
                      "original_d1_stages":first["stages"],
                      "original_d2_stages":second["stages"],
                      "original_d2_changes":second["ordered_conditional_changes"],
                      "original_frame_zero":rows[0],"native_gain":native,"common_gain":common,
                      "reset_coordinates":resets,"windows":windows,
                      "trace":descriptor(directory/"views/gain.csv"),
                      "control":descriptor(directory/"control.bin"),"parent_taps":entry["parent_taps"]})
        total_windows+=len(windows);total_frames+=len(rows);total_resets+=len(resets)
        remaining(start,300)
    need(total_windows == lock["windows"] == 362 and total_frames == lock["frames"] == 35916 and
         total_resets == lock["resets"] == 8, "D4_MATRIX_TOTALS")
    groups=[]
    for group,profile,scenario in sorted({(c["group"],c["profile"],c["scenario"]) for c in cases}):
        selected=[c for c in cases if (c["group"],c["profile"],c["scenario"]) == (group,profile,scenario)]
        windows=[w for c in selected for w in c["windows"]]
        changes={}
        for name in d2.STEPS:
            scored=[w for w in windows if w["original_d2_changes"][name]["near_si_sdr_change_db"] is not None]
            vals=[w["original_d2_changes"][name]["near_si_sdr_change_db"] for w in scored]
            negative=[w for w in scored if w["original_d2_changes"][name]["near_si_sdr_change_db"] < 0]
            changes[name]={"total_windows":len(windows),"scored_windows":len(scored),
                           "null_windows":len(windows)-len(scored),
                           "negative_sign":sum(v<0 for v in vals),"zero_sign":sum(v==0 for v in vals),
                           "positive_sign":sum(v>0 for v in vals),
                           "min":min(vals) if vals else None,"median":statistics.median(vals) if vals else None,
                           "max":max(vals) if vals else None,
                           "negative_window_zero_frames":sum(w["gain"]["zero_frames"] for w in negative),
                           "negative_window_nonzero_frames":sum(w["gain"]["nonzero_frames"] for w in negative)}
        groups.append({"group":group,"profile":profile,"scenario":scenario,"cases":len(selected),
                       "windows":len(windows),"ordered_changes":changes})
    return {"experiment":EXPERIMENT,"status":"FIXED_WINDOW_GAIN_LOCALIZATION_VALID_NO_PROMOTION",
            "freeze":FREEZE,"source":proof,"input_artifact":lock["artifact"],
            "original_source":lock["source_revision"],"data_role":"disclosed-regression",
            "DSP_executed":False,"models_executed":False,"promotion_allowed":False,
            "independent_observations":False,"control_frame_shift":0,
            "case_count":len(cases),"window_count":total_windows,"frames":total_frames,
            "scored_common_frames":total_frames-len(cases),"resets":total_resets,
            "cases":cases,"aggregates":groups}

def phase_pass(output,name):
    r=d2.read_json(output/(name+"-phase.json"))
    need(r["phase"] == name and r["status"] == "PASS" and r["budget_seconds"] == 300 and
         0 <= r["elapsed_seconds"] <= 300,"D4_PHASE_NOT_QUALIFIED")

def verify(input_root,output,start):
    phase_pass(output,"analysis")
    lock=frozen()
    allowed={"source",*COPIES,"report.json","analysis-phase.json","verify-phase.json","readback.json"}
    need({p.name for p in output.iterdir()} <= allowed and
         all(not p.is_symlink() for p in output.rglob("*")), "D4_OUTPUT_MEMBERS")
    names=source_names(lock)
    need(d2.file_set(output/"source") == names, "D4_SOURCE_MEMBERS")
    expected_dirs=set()
    for name in names:
        p=Path(name).parent
        while str(p) != ".":
            expected_dirs.add(p.as_posix()); p=p.parent
    need({p.relative_to(output/"source").as_posix() for p in (output/"source").rglob("*") if p.is_dir()} ==
         expected_dirs, "D4_SOURCE_DIRECTORIES")
    for name in names:
        need((output/"source"/name).read_bytes() == (ROOT/name).read_bytes(), "D4_SAVED_SOURCE_CHANGED")
    for dest,origin in COPIES.items():
        need((output/dest).read_bytes() == (input_root/origin).read_bytes(), "D4_SAVED_INPUT_CHANGED")
    report=payload(input_root,start)
    need(report == d2.read_json(output/"report.json"), "D4_READBACK_DIFFERS")
    return report

def summary(report):
    return {k:report[k] for k in ("experiment","status","case_count","window_count","frames",
                                 "scored_common_frames","resets","aggregates","promotion_allowed")}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("phase",choices=("analysis","verify"))
    p.add_argument("--input",required=True,type=Path);p.add_argument("--output",required=True,type=Path)
    a=p.parse_args();start=time.monotonic();output=a.output.resolve();input_root=a.input.resolve()
    receipt={"phase":a.phase,"status":"FAIL","budget_seconds":300}
    try:
        if a.phase == "analysis":
            need(not output.exists(),"D4_FRESH_OUTPUT_REQUIRED")
            output.mkdir(parents=True)
            report=payload(input_root,start)
            for name in source_names(frozen()):
                dest=output/"source"/name;dest.parent.mkdir(parents=True,exist_ok=True)
                shutil.copyfile(ROOT/name,dest)
            for dest,origin in COPIES.items():
                shutil.copyfile(input_root/origin,output/dest)
            dump(output/"report.json",report)
        else:
            report=verify(input_root,output,start)
            dump(output/"readback.json",{"status":"PASS","report":descriptor(output/"report.json"),
                                        "DSP_executed":False,"models_executed":False})
        print(json.dumps(summary(report),sort_keys=True))
        remaining(start,300);receipt["status"]="PASS"
    except Exception as error:
        receipt.update(reason=str(error),error_type=type(error).__name__)
        raise
    finally:
        output.mkdir(parents=True,exist_ok=True)
        receipt["elapsed_seconds"]=time.monotonic()-start
        dump(output/(a.phase+"-phase.json"),receipt)
        if time.monotonic()-start>300:
            receipt.update(status="FAIL",reason="D4_FINAL_WRITE_BUDGET_EXCEEDED")
            dump(output/(a.phase+"-phase.json"),receipt)
            raise ValueError(receipt["reason"])

if __name__=="__main__":
    main()
