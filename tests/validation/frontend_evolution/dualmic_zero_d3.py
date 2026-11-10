#!/usr/bin/env python3
"""D3 isolated two-arm AGC replay; original D2 inputs and baseline remain authority."""
from __future__ import annotations
import argparse
import csv
import io
import json
import math
import os
from pathlib import Path
import shutil
import statistics
import struct
import subprocess
import time
import tarfile

import dualmic_gain_d2 as d2
import dualmic_zero_d3_source as admission
from dualmic_stages_source import digest, dump, need, remaining

ROOT = admission.ROOT
C_PATH = "tests/validation/frontend_evolution/dualmic_zero_d3.c"
PY_PATH = "tests/validation/frontend_evolution/dualmic_zero_d3.py"
OLD = "cc853616685b9faf7880e6d8f8f1a89d187d342a"
EXPERIMENT = "FE-DUALMIC-ZERO-D3"
EXECUTION_ROOT = Path("/tmp/ap-dualmic-d3/result")
INPUT_ROOT = Path("/tmp/ap-dualmic-d3/input")
BEFORE = "    state->gain += alpha * (target_gain - state->gain);"
AFTER = "    if (peak != 0.0f || target_gain < state->gain) state->gain += alpha * (target_gain - state->gain);"


def descriptor(p):
    return {"bytes": p.stat().st_size, "sha256": digest(p)}


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT, timeout=30)


def original(input_root):
    receipt = d2.read_json(input_root / "admission.json")
    lock = admission.frozen_lock()
    need(receipt["status"] == "INPUT_ADMITTED_NO_DSP_EXECUTION" and
         receipt["freeze"] == admission.FREEZE and receipt["artifact"] == lock["artifact"] and
         receipt["source_revision"] == OLD and receipt["DSP_executed"] is False and
         receipt["models_executed"] is False and 0 <= receipt["elapsed_seconds"] <= 300,
         "D3_INPUT_NOT_ADMITTED")
    prior, parent = input_root / "original/gain-d2", input_root / "original/result"
    need(digest(prior / "report.json") == lock["report_sha256"] and
         digest(prior / "artifact-manifest.json") == lock["manifest_sha256"], "D3_ORIGINAL_REPORT_CHANGED")
    manifest=d2.read_json(prior/"artifact-manifest.json")
    need(manifest["files"]==d2.payload_inventory(prior),"D3_ORIGINAL_D2_PAYLOAD_CHANGED")
    binding=d2.read_json(prior/"parent-binding.json")
    need(descriptor(parent/"build/build-manifest.json")==binding["build_manifest"],
         "D3_ORIGINAL_PARENT_BUILD_CHANGED")
    old_lock = d2.input_lock()
    need((prior / "input-lock.json").read_bytes() == (ROOT / d2.LOCK_NAME).read_bytes(), "D3_INPUT_LOCK_CHANGED")
    return prior, parent, old_lock


def command(argv, log, start):
    begin = time.monotonic()
    env = d2.d1.process_environment()
    with log.open("wb") as stream:
        r = subprocess.run(argv, cwd=ROOT, env=env, stdout=stream, stderr=subprocess.STDOUT,
                           timeout=remaining(start,300), check=False)
    dump(log.with_name(log.stem+"-command.json"), {"argv": argv, "returncode": r.returncode,
                                   "elapsed_seconds": time.monotonic()-begin})
    need(r.returncode == 0, "D3_COMMAND_FAILED")
    remaining(start,300)


def old_sources(input_root,parent):
    manifest=d2.read_json(parent/"build/build-manifest.json")
    spec=manifest["source_archive"]
    archive=d2.safe(input_root/"original/build",spec["path"])
    need(descriptor(archive)=={k:spec[k] for k in ("bytes","sha256")},"D3_ORIGINAL_SOURCE_ARCHIVE")
    result={}
    with tarfile.open(archive,"r:") as stream:
        for name in ("src/enhance/ap_agc.c","src/enhance/ap_enhance.h"):
            members=[m for m in stream.getmembers() if m.name==name]
            need(len(members)==1 and members[0].isfile() and
                 0 < members[0].size <= 262144,"D3_EXACT_ARCHIVE_SOURCE_MEMBER")
            f=stream.extractfile(members[0])
            need(f is not None,"D3_MISSING_ARCHIVE_MEMBER")
            raw=f.read(members[0].size+1)
            need(len(raw)==members[0].size,"D3_TRUNCATED_ARCHIVE_SOURCE")
            import hashlib
            need(hashlib.sha256(raw).hexdigest()==manifest["production_files"][name]["sha256"],
                 "D3_ARCHIVED_PRODUCTION_SOURCE_CHANGED")
            result[name]=raw
    return result


def compile_argv(compiler):
    return [compiler,"-std=c11","-O2","-ffp-contract=off","-Wall","-Wextra","-Werror",
            "-DAP_BUILD_STAGE_AGC=1","-I"+str(EXECUTION_ROOT/"source"),str(EXECUTION_ROOT/"source/runner.c"),
            str(EXECUTION_ROOT/"source/candidate.c"),str(EXECUTION_ROOT/"source/original-library.a"),
            "-lm","-o",str(EXECUTION_ROOT/"replay")]


def build(input_root, output, start):
    need(output==EXECUTION_ROOT and input_root==INPUT_ROOT,"D3_FROZEN_EXECUTION_ROOT")
    prior, parent, lock = original(input_root)
    archived=old_sources(input_root,parent)
    output.mkdir(parents=True,exist_ok=False)
    (output/"source/enhance").mkdir(parents=True)
    identity, old_build = d2.verify_sources(prior, lock)
    production = d2.read_json(parent/"build/build-manifest.json")["production_files"]
    for remote, dest in (("src/enhance/ap_agc.c","baseline.c"),("src/enhance/ap_enhance.h","enhance/ap_enhance.h")):
        raw = archived[remote]
        p=output/"source"/dest; p.write_bytes(raw)
        need(digest(p)==production[remote]["sha256"],"D3_ORIGINAL_PRODUCTION_SOURCE_CHANGED")
    src=(output/"source/baseline.c").read_text()
    need(src.count(BEFORE)==1,"D3_EXACT_INTERVENTION_SITE")
    candidate=src.replace(BEFORE,AFTER)
    for name in ("ap_agc_init","ap_agc_process_controlled","ap_agc_process"):
        candidate=candidate.replace(name,"d3"+name[2:])
    (output/"source/candidate.c").write_text(candidate)
    revision=git("rev-parse","HEAD").decode().strip()
    for name,dest in ((C_PATH,"runner.c"),(PY_PATH,"driver.py"),
                      ("tests/validation/frontend_evolution/test_dualmic_zero_d3_integrity.py","integrity.py"),
                      ("tests/validation/frontend_evolution/dualmic_zero_d3_source.py","admission.py"),
                      (admission.LOCK_PATH,"input-lock.json"),(admission.PLAN_PATH,"plan.md"),
                      ("docs/research/frontend-evolution-v1/DUALMIC_ZERO_D3_IMPLEMENTATION.md","implementation.md")):
        raw=git("show",revision+":"+name)
        need(raw==(ROOT/name).read_bytes(),"D3_UNCOMMITTED_EXECUTOR")
        (output/"source"/dest).write_bytes(raw)
    library_path=old_build["parent_plain"]["library"]["path"]
    old_library=prior/"proof/plain"/library_path
    need(descriptor(old_library)=={k:old_build["parent_plain"]["library"][k] for k in ("bytes","sha256")},
         "D3_ORIGINAL_LIBRARY_CHANGED")
    shutil.copyfile(old_library,output/"source/original-library.a")
    compiler=shutil.which("cc")
    need(compiler is not None,"D3_COMPILER_MISSING")
    command([compiler,"--version"],output/"compiler.log",start)
    argv=compile_argv(compiler)
    command(argv,output/"build.log",start)
    command([str(output/"replay"),"--self-test"],output/"self-test.log",start)
    files={p.relative_to(output).as_posix():descriptor(p) for p in (output/"source").rglob("*") if p.is_file()}
    dump(output/"build.json",{"experiment":EXPERIMENT,"source_revision":revision,
         "source_tree":git("rev-parse","HEAD^{tree}").decode().strip(),"original_source":OLD,
         "compiler":descriptor(Path(compiler)),"compiler_path":compiler,"command":argv,"source_files":files,
         "program":descriptor(output/"replay"),"intervention_before":BEFORE,"intervention_after":AFTER,
         "original_D2_library_used":True,"same_old_compiler_claim":False,"promotion_allowed":False})


def verify_build(input_root,output):
    b=d2.read_json(output/"build.json")
    head=git("rev-parse","HEAD").decode().strip()
    tree=git("rev-parse","HEAD^{tree}").decode().strip()
    need(b["source_revision"]==head and b["source_tree"]==tree and
         (output/"source/driver.py").read_bytes()==(ROOT/PY_PATH).read_bytes(),"D3_REVIEWED_SOURCE_IDENTITY")
    archived=old_sources(input_root,input_root/"original/result")
    need(b["experiment"]==EXPERIMENT and b["original_source"]==OLD and
         b["program"]==descriptor(output/"replay"),"D3_BUILD_IDENTITY")
    actual={p.relative_to(output).as_posix():descriptor(p) for p in (output/"source").rglob("*") if p.is_file()}
    expected_sources={"source/"+n for n in ("runner.c","driver.py","integrity.py","admission.py",
                      "input-lock.json","plan.md","implementation.md","baseline.c","candidate.c",
                      "original-library.a","enhance/ap_enhance.h")}
    need(set(actual)==expected_sources and actual==b["source_files"] and
         {x.relative_to(output/"source").as_posix() for x in (output/"source").rglob("*") if x.is_dir()}=={"enhance"},
         "D3_BUILD_SOURCE_CHANGED")
    for saved,revision,remote in (("runner.c",b["source_revision"],C_PATH),
                                  ("driver.py",b["source_revision"],PY_PATH),
                                  ("integrity.py",b["source_revision"],"tests/validation/frontend_evolution/test_dualmic_zero_d3_integrity.py"),
                                  ("admission.py",b["source_revision"],"tests/validation/frontend_evolution/dualmic_zero_d3_source.py"),
                                  ("input-lock.json",b["source_revision"],admission.LOCK_PATH),
                                  ("plan.md",b["source_revision"],admission.PLAN_PATH),
                                  ("implementation.md",b["source_revision"],"docs/research/frontend-evolution-v1/DUALMIC_ZERO_D3_IMPLEMENTATION.md"),
                                  ):
        need((output/"source"/saved).read_bytes()==git("show",revision+":"+remote),
             "D3_RETAINED_SOURCE_NOT_COMMITTED")
    for saved,name in (("baseline.c","src/enhance/ap_agc.c"),("enhance/ap_enhance.h","src/enhance/ap_enhance.h")):
        need((output/"source"/saved).read_bytes()==archived[name],"D3_RETAINED_ARCHIVE_SOURCE_CHANGED")
    baseline=(output/"source/baseline.c").read_text()
    need(baseline.count(BEFORE)==1 and b["intervention_before"]==BEFORE and
         b["intervention_after"]==AFTER,"D3_INTERVENTION_CONTRACT")
    expected=baseline.replace(BEFORE,AFTER)
    for name in ("ap_agc_init","ap_agc_process_controlled","ap_agc_process"):
        expected=expected.replace(name,"d3"+name[2:])
    need((output/"source/candidate.c").read_text()==expected,"D3_CANDIDATE_NOT_EXACT_DERIVATION")
    for filename in ("build-command.json","compiler-command.json","self-test-command.json"):
        receipt=d2.read_json(output/filename)
        need(receipt["returncode"]==0 and 0 <= receipt["elapsed_seconds"] <= 300,
             "D3_BUILD_COMMAND_FAILED")
    compiler=shutil.which("cc")
    need(compiler==b["compiler_path"] and descriptor(Path(compiler))==b["compiler"],"D3_COMPILER_IDENTITY")
    need(d2.read_json(output/"build-command.json")["argv"]==b["command"]==compile_argv(compiler),
         "D3_BUILD_COMMAND_CHANGED")
    need(d2.read_json(output/"compiler-command.json")["argv"]==[compiler,"--version"] and
         d2.read_json(output/"self-test-command.json")["argv"]==[str(EXECUTION_ROOT/"replay"),"--self-test"],
         "D3_BUILD_CONTROL_COMMAND_CHANGED")
    return b


def phase_pass(output,phase):
    r=d2.read_json(output/(phase+"-phase.json"))
    need(r["phase"]==phase and r["status"]=="PASS" and r["budget_seconds"]==300 and
         0 <= r["elapsed_seconds"] <= 300,"D3_PHASE_FAILED_OR_OVER_BUDGET")


def run(input_root,output,start):
    need(output==EXECUTION_ROOT and input_root==INPUT_ROOT,"D3_FROZEN_EXECUTION_ROOT")
    prior,parent,lock=original(input_root); verify_build(input_root,output); phase_pass(output,"build")
    (output/"cases").mkdir(exist_ok=False)
    completed=[]
    for entry in lock["cases"]:
        case=entry["catalog"]; folder=output/"cases"/case["key"]; folder.mkdir(parents=True)
        taps=parent/"cases"/case["key"]/"taps"
        for name,expected in entry["parent_taps"].items():
            need(descriptor(taps/name)==expected,"D3_CHANGED_INPUT")
        controls=d2.control_bytes(taps/"control.csv",case)
        (folder/"control.bin").write_bytes(controls)
        argv=[str(output/"replay"),str(taps/"ns_output.f32le"),str(taps/"agc_output.f32le"),
              str(folder/"control.bin"),str(folder/"baseline.f32le"),str(folder/"candidate.f32le"),
              str(folder/"trace.bin"),case["profile"],str(case["frames"])]
        command(argv,folder/"execution.log",start)
        completed.append(case["key"])
        dump(output/"run-index.json",{"experiment":EXPERIMENT,"completed":completed,"expected":60})
    need(len(completed)==60,"D3_INCOMPLETE_MATRIX")


def analyze(input_root,output,start):
    prior,parent,lock=original(input_root); b=verify_build(input_root,output)
    phase_pass(output,"build"); phase_pass(output,"run")
    library=d2.read_json(prior/"build-manifest.json")["parent_plain"]["library"]
    need(descriptor(output/"source/original-library.a")=={k:library[k] for k in ("bytes","sha256")},
         "D3_BASELINE_LIBRARY_NOT_ORIGINAL")
    need(d2.read_json(output/"run-index.json")["completed"]==[e["catalog"]["key"] for e in lock["cases"]],
         "D3_RUN_MATRIX_CHANGED")
    allowed={"source","cases","compiler.log","compiler-command.json","build.log","build-command.json",
             "self-test.log","self-test-command.json","build.json","replay","build-phase.json",
             "run-index.json","run-phase.json","analysis-phase.json","report.json","readback.json","verify-phase.json"}
    need({x.name for x in output.iterdir()} <= allowed and
         all(not x.is_symlink() for x in output.rglob("*")),"D3_OUTPUT_ROOT_MEMBERSHIP")
    expected_files={e["catalog"]["key"]+"/"+name for e in lock["cases"] for name in
                    ("control.bin","baseline.f32le","candidate.f32le","trace.bin","execution.log","execution-command.json")}
    expected_dirs={e["catalog"]["key"] for e in lock["cases"]}|{"A","C"}
    need(d2.file_set(output/"cases")==expected_files and
         {x.relative_to(output/"cases").as_posix() for x in (output/"cases").rglob("*") if x.is_dir()}==expected_dirs,
         "D3_CASE_ROOT_MEMBERSHIP")
    old_report=d2.read_json(prior/"report.json"); cases=[]; totals={"frames":0,"resets":0,"zero_frames":0,"held_updates":0}
    for entry,old_case in zip(lock["cases"],old_report["cases"]):
        case=entry["catalog"]; folder=output/"cases"/case["key"]; taps=parent/"cases"/case["key"]/"taps"
        for name,expected in entry["parent_taps"].items():
            need(descriptor(taps/name)==expected,"D3_CHANGED_INPUT")
        need({x.name for x in folder.iterdir()} == {"control.bin","baseline.f32le","candidate.f32le","trace.bin","execution.log","execution-command.json"} and
             all(x.is_file() and not x.is_symlink() for x in folder.iterdir()),"D3_CASE_FILE_MEMBERSHIP")
        execution=d2.read_json(folder/"execution-command.json")
        need(execution["returncode"]==0 and 0 <= execution["elapsed_seconds"] <= 300,"D3_EXECUTION_FAILED")
        fixed_case=EXECUTION_ROOT/"cases"/case["key"]
        fixed_taps=INPUT_ROOT/"original/result/cases"/case["key"]/"taps"
        expected_argv=[str(EXECUTION_ROOT/"replay"),str(fixed_taps/"ns_output.f32le"),
                       str(fixed_taps/"agc_output.f32le"),str(fixed_case/"control.bin"),
                       str(fixed_case/"baseline.f32le"),str(fixed_case/"candidate.f32le"),
                       str(fixed_case/"trace.bin"),case["profile"],str(case["frames"])]
        need(execution["argv"]==expected_argv,"D3_EXECUTION_COMMAND_CHANGED")
        controls=d2.control_bytes(taps/"control.csv",case)
        need((folder/"control.bin").read_bytes()==controls,"D3_CONTROLS_CHANGED")
        raw=(taps/"ns_output.f32le").read_bytes()
        samples=list(struct.unpack("<"+str(case["samples"])+"f",raw))
        base=(folder/"baseline.f32le").read_bytes(); candidate=(folder/"candidate.f32le").read_bytes()
        need(base==(taps/"agc_output.f32le").read_bytes() and len(candidate)==len(base),"D3_BASELINE_NOT_ORIGINAL")
        trace=(folder/"trace.bin").read_bytes()
        need(len(trace)==case["frames"]*68,"D3_TRACE_SIZE")
        rows=list(csv.DictReader(io.StringIO((prior/"cases"/case["key"]/"views/gain.csv").read_text())))
        need(len(rows)==case["frames"],"D3_ORIGINAL_TRACE_COUNT")
        previous=None; counts={"frames":case["frames"],"resets":0,"zero_frames":0,"held_updates":0}
        max_gain_delta=0.0
        for frame,(state,ctl,row) in enumerate(zip(struct.iter_unpack("<14f3I",trace),struct.iter_unpack("<IIff",controls),rows)):
            allow,reset,before,after=ctl
            need(tuple(state[14:16])==(allow,reset),"D3_TRACE_CONTROLS")
            signal=samples[frame*160:(frame+1)*160]
            need(all(math.isfinite(x) for x in signal) and all(math.isfinite(x) for x in state[:14]),"D3_NONFINITE")
            zero=all(x==0.0 for x in signal)
            need(state[16]==int(zero),"D3_FALSE_ZERO")
            target=d2.f32(float(row["target_linear"])); limit=d2.f32(float(row["limiter_linear"]))
            expected_base=(before,target,limit,after,target,limit)
            need(struct.pack("<6f",*state[:6])==struct.pack("<6f",*expected_base),"D3_BASELINE_FULL_STATE")
            expected_before=(1.0,target,limit) if frame==0 or reset else previous
            need(struct.pack("<3f",*state[6:9])==struct.pack("<3f",*expected_before),"D3_CANDIDATE_STATE_NOT_CONTINUOUS")
            obs,_=d2.gain_observation(signal,state[6],allow,target,limit)
            held=zero and obs["target_gain"]>state[6]
            expected_after=state[6] if held else obs["expected_state_gain_after"]
            need(struct.pack("<3f",*state[9:12])==struct.pack("<3f",expected_after,target,limit),
                 "D3_CANDIDATE_STATE_FORMULA")
            peak=max(abs(x) for x in signal)
            applied=min(expected_after,1.0) if not allow else expected_after
            if d2.f32(peak*applied)>limit and peak>d2.f32(1e-6):
                applied=d2.f32(limit/peak)
            base_obs,_=d2.gain_observation(signal,before,allow,target,limit)
            need(d2.same_float(state[12],base_obs["applied_gain"]) and d2.same_float(state[13],applied),
                 "D3_APPLIED_GAIN_MISMATCH")
            expected=d2.float_bytes(max(-limit,min(limit,d2.f32(x*applied))) for x in signal)
            need(candidate[frame*640:(frame+1)*640]==expected,"D3_CANDIDATE_OUTPUT_FORMULA")
            previous=state[9:12]
            counts["resets"]+=reset; counts["zero_frames"]+=zero; counts["held_updates"]+=held
            max_gain_delta=max(max_gain_delta,abs(state[3]-state[9]))
        reference=None; reason="no_clean_near_reference"
        if entry["clean_near"] is not None:
            p=d2.safe(parent/"originals/A",case["inputs"]["clean_near"])
            need(descriptor(p)==entry["clean_near"],"D3_REFERENCE_CHANGED")
            reference=[x/32768.0 for x in d2.d1.samples(p,"h",case["samples"])]
        if case["group"]=="C": reason="C_has_no_admitted_clean_near_reference"
        values={"baseline":list(struct.unpack("<"+str(case["samples"])+"f",base)),
                "candidate":list(struct.unpack("<"+str(case["samples"])+"f",candidate))}
        stages={name:d2.d1.measure_lane(vals,160,case["samples"],reference,reason,True) for name,vals in values.items()}
        need(stages["baseline"]==old_case["stages"]["replay_final"],"D3_ORIGINAL_ENDPOINT_SCORE")
        delta=d2.d1.stage_delta(stages,"baseline","candidate","isolated_zero_update_total_effect")
        changed,first=d2.differences(base,candidate)
        cases.append({"key":case["key"],"profile":case["profile"],"scenario":case["scenario"],
                      "counts":counts,"changed_samples":changed,"first_difference":first,"max_state_gain_delta":max_gain_delta,
                      "stages":stages,"delta":delta,"baseline_original_state_and_output_exact":True,
                      "continuous_candidate_arithmetic_exact":True,
                      "files":{p.name:descriptor(p) for p in folder.iterdir() if p.is_file()}})
        for k in totals: totals[k]+=counts[k]
        remaining(start,300)
    need(totals["frames"]==35916 and totals["resets"]==8,"D3_TOTALS")
    groups=[]
    for profile in ("call","assistant"):
        for scenario in sorted({c["scenario"] for c in cases}):
            selected=[c for c in cases if c["profile"]==profile and c["scenario"]==scenario]
            scores=[c["delta"]["common"]["near_si_sdr_change_db"] for c in selected
                    if c["delta"]["common"]["near_si_sdr_change_db"] is not None]
            groups.append({"profile":profile,"scenario":scenario,"cases":len(selected),"scored":len(scores),
                           "min":min(scores) if scores else None,"median":statistics.median(scores) if scores else None,
                           "max":max(scores) if scores else None})
    return {"experiment":EXPERIMENT,"status":"CONTROLLED_DIAGNOSIS_NO_PROMOTION","source_revision":b["source_revision"],
            "original_source":OLD,"case_count":60,"totals":totals,"aggregates":groups,"cases":cases,
            "promotion_allowed":False,"models_executed":False,"physical_device_executed":False,
            "fresh_baseline_matches_original_D2":True,"data_role":"disclosed-regression",
            "scope":"isolated original AGC input/gate replay; not integrated 2.3.64 pipeline or acoustic qualification"}


def verify_report(input_root,output,start):
    phase_pass(output,"analysis")
    report=analyze(input_root,output,start)
    need(report==d2.read_json(output/"report.json"),"D3_READBACK_REPORT_DIFFERS")
    return report


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("phase",choices=("build","run","analysis","verify"))
    p.add_argument("--input",required=True,type=Path); p.add_argument("--output",required=True,type=Path)
    a=p.parse_args(); start=time.monotonic(); output=a.output.resolve()
    receipt={"phase":a.phase,"status":"FAIL","budget_seconds":300}
    try:
        if a.phase=="build": build(a.input.resolve(),output,start)
        elif a.phase=="run": run(a.input.resolve(),output,start)
        else:
            report=analyze(a.input.resolve(),output,start) if a.phase=="analysis" else verify_report(a.input.resolve(),output,start)
            if a.phase=="analysis": dump(output/"report.json",report)
            else:
                dump(output/"readback.json",{"status":"PASS","DSP_executed":False,"report":descriptor(output/"report.json")})
            print(json.dumps({k:report[k] for k in ("experiment","status","case_count","totals","aggregates","promotion_allowed")},sort_keys=True))
        remaining(start,300); receipt["status"]="PASS"
    finally:
        output.mkdir(parents=True,exist_ok=True)
        receipt["elapsed_seconds"]=time.monotonic()-start
        dump(output/(a.phase+"-phase.json"),receipt)
        if time.monotonic()-start>300:
            receipt.update(status="FAIL",reason="D3_FINAL_WRITE_BUDGET_EXCEEDED",elapsed_seconds=time.monotonic()-start)
            dump(output/(a.phase+"-phase.json"),receipt)
            raise ValueError("D3_FINAL_WRITE_BUDGET_EXCEEDED")
if __name__=="__main__":
    main()
