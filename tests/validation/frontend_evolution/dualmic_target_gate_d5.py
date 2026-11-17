#!/usr/bin/env python3
"""D5: one target-gate deletion, two continuous arms, original D2 byte authority."""
from __future__ import annotations
import argparse
import csv
import hashlib
import io
import json
import math
import os
from pathlib import Path
import shutil
import statistics
import struct
import subprocess
import sys
import tarfile
import time

import dualmic_gain_d2 as d2
import dualmic_zero_d3_source as admission
from dualmic_stages_source import digest, need, remaining

ROOT = admission.ROOT
EXPERIMENT = "FE-DUALMIC-TARGET-GATE-D5"
FREEZE = "84a557868a341adbc8e0338034809bd040d5c992"
OLD = "cc853616685b9faf7880e6d8f8f1a89d187d342a"
C_PATH = "tests/validation/frontend_evolution/dualmic_target_gate_d5.c"
PY_PATH = "tests/validation/frontend_evolution/dualmic_target_gate_d5.py"
TEST = "tests/validation/frontend_evolution/test_dualmic_target_gate_d5.py"
PLAN = "docs/research/frontend-evolution-v1/DUALMIC_TARGET_GATE_D5_PLAN.zh-CN.md"
LOCK = "docs/research/frontend-evolution-v1/dualmic-target-gate-d5-input-lock.json"
WORKFLOW = ".github/workflows/frontend-research.yml"
NOTE = "docs/research/frontend-evolution-v1/DUALMIC_TARGET_GATE_D5_IMPLEMENTATION.zh-CN.md"
EXECUTION_ROOT = Path("/tmp/ap-dualmic-d5/result")
INPUT_ROOT = Path("/tmp/ap-dualmic-d5/input")
BEFORE = "        if (!allow_gain_increase && target_gain > 1.0f) target_gain = 1.0f;"
PINS = {PLAN: "68c8e2a3ff5059730f282e2a5ff035cc6225c4da",
        LOCK: "a96cf7d6714343dd8184f8dafe7d82f2db34cdd6"}
FROZEN_HELPERS = {
    "docs/research/frontend-evolution-v1/DUALMIC_GAIN_D2_PLAN.zh-CN.md": "14867b1128ffbd532e72aa38a62f0800476db66d",
    "docs/research/frontend-evolution-v1/DUALMIC_STAGES_D1_PLAN.zh-CN.md": "b9c463cb601ed83eff69390dc9a6d222276975a1",
    "docs/research/frontend-evolution-v1/DUALMIC_ZERO_D3_PLAN.zh-CN.md": "070545d075cc32ccdf33cd532d450170419be986",
    "docs/research/frontend-evolution-v1/dualmic-gain-d2-input-lock.json": "903e5fc75ae49308b48ea9627d98b764a6515990",
    "docs/research/frontend-evolution-v1/dualmic-stages-d1-source-lock.json": "0d3f9aef2db02261303dcffd3c463fb6ad6e19bb",
    "docs/research/frontend-evolution-v1/dualmic-zero-d3-input-lock.json": "d973fcd88a52787b6026ddb8add815c5f4475e54",
    "tests/validation/frontend_evolution/dualmic_gain_d2.c": "db9f7f60be55b55967cc1fa7a81dceea9470369e",
    "tests/validation/frontend_evolution/dualmic_gain_d2.py": "7a002e6b56e5ac819e0125f3c15f1b4a5e72c460",
    "tests/validation/frontend_evolution/dualmic_stages_d1.c": "21332fc1ddb9d797e25f94d58473b3ef34be9e4c",
    "tests/validation/frontend_evolution/dualmic_stages_d1.py": "4584f30c19d4637f6b46fc78796c80769addf4dd",
    "tests/validation/frontend_evolution/dualmic_stages_source.py": "79407dd5db81ba4eba7f8602f048024fb45d58bc",
    "tests/validation/frontend_evolution/dualmic_zero_d3_source.py": "c7c0831c5ca3c5263fd5de759d181e553db80905",
    "tests/validation/frontend_evolution/test_dualmic_gain_d2_integrity.py": "abe5486d0c266e1f7064402f953be87f947921b7",
    "tests/validation/frontend_evolution/test_dualmic_stages_source.py": "6be206d7edcbe5c6bcf58405f71f0b09459c03e4",
    "tests/validation/frontend_evolution/test_dualmic_zero_d3_source.py": "ef80d05293adf4e9e2a6a4252c0a13ff3cdac774",
    "tools/codex_assets/__init__.py": "f651dcc381e2e3ca78bf1a6f28f0c2f9b7125edc",
    "tools/codex_assets/device_alignment.py": "c91e5efadcdaa02629677372c68fd5b745e84431",
    "tools/codex_assets/device_capture.py": "9c8cced09f8031c49591791385792b0d4902146b",
    "tools/codex_assets/device_exact_reference.py": "6f41754aa008e343142cfae676e4c203d5f0caa9",
    "tools/codex_assets/device_replay.py": "b85374ec90e063d76e187e1e49e6bddb0c9fd0c0",
    "tools/codex_assets/device_stages.py": "fb1201ded543a04000938748e8b777cae5dcf72e",
    "tools/codex_assets/dualmic_stages_build.py": "d54a348cacb1d0b1be994d1687290ef4150bef9d",
    "validation/tools/run_validation_engine.py": "356458acb4457240aefaf20ebf3f437225b10295"
}
COPIES = {"admission.json":"admission.json",
          "original-d2-report.json":"original/gain-d2/report.json",
          "original-d2-manifest.json":"original/gain-d2/artifact-manifest.json",
          "original-d1-report.json":"original/result/report.json"}
CASE_FILES = {"control.bin","baseline.f32le","candidate.f32le","trace.bin",
              "execution.log","execution-command.json"}
BUILD_FILES = {"compiler.log","compiler-command.json","build.log","build-command.json",
               "self-test.log","self-test-command.json","build.json","replay","build-phase.json"}
OPTIONAL_FILES = {"run-phase.json","analysis-phase.json","report.json","verify-phase.json","readback.json"}
AUDIT_ORIGIN = "Float32 formula reconstruction; state bytes and PCM measured by replay; applied gains reconstructed and verified against every output sample"

def dump(path, value):
    with Path(path).open("x",encoding="utf-8") as out:
        json.dump(value,out,ensure_ascii=False,sort_keys=True,indent=2,allow_nan=False)
        out.write("\n")

def descriptor(path):
    need(path.is_file() and not path.is_symlink(),"D5_REGULAR_FILE_REQUIRED")
    return {"bytes":path.stat().st_size,"sha256":digest(path)}

def blob(raw):
    return hashlib.sha1(b"blob "+str(len(raw)).encode()+b"\0"+raw).hexdigest()

def git(start,*args):
    return subprocess.check_output(["git",*args],cwd=ROOT,
        env=d2.d1.process_environment(),timeout=remaining(start,300)).decode().strip()

def frozen():
    for name,expected in {**PINS,**FROZEN_HELPERS}.items():
        need(blob((ROOT/name).read_bytes())==expected,"D5_FROZEN_CONTRACT_CHANGED")
    lock=d2.read_json(ROOT/LOCK)
    need(lock["experiment"]==EXPERIMENT and lock["intervention_remove"]==BEFORE,
         "D5_CONTRACT_IDENTITY")
    return admission.frozen_lock()

def source_names():
    return {C_PATH,PY_PATH,TEST,PLAN,LOCK,WORKFLOW,NOTE,
            "tests/validation/frontend_evolution/dualmic_zero_d3_source.py",
            "tests/validation/frontend_evolution/test_dualmic_zero_d3_source.py",
            "tests/validation/frontend_evolution/test_dualmic_stages_source.py",
            admission.PLAN_PATH,admission.LOCK_PATH,*d2.input_lock()["D1_SOURCE_FILES"],
            d2.SELF_NAME,d2.C_NAME,d2.TEST_NAME,d2.LOCK_NAME,d2.PLAN_NAME,
            "tools/codex_assets/device_alignment.py","tools/codex_assets/__init__.py"}

def source_proof(start):
    head,tree=git(start,"rev-parse","HEAD"),git(start,"rev-parse","HEAD^{tree}")
    names=source_names()
    for name in sorted(names):
        need(git(start,"rev-parse",head+":"+name)==blob((ROOT/name).read_bytes()),"D5_UNCOMMITTED_SOURCE")
    # Explicitly prove all imported repository modules belong to the retained closure.
    for module in list(sys.modules.values()):
        path=getattr(module,"__file__",None)
        if path is None:
            continue
        try:
            relative=Path(path).resolve().relative_to(ROOT).as_posix()
        except ValueError:
            continue
        need(relative in names,"D5_UNRETAINED_IMPORTED_MODULE:"+relative)
    return {"revision":head,"tree":tree,"files":{n:descriptor(ROOT/n) for n in sorted(names)}}

def original(input_root,start):
    lock=frozen()
    receipt=d2.read_json(input_root/"admission.json")
    need(receipt["status"]=="INPUT_ADMITTED_NO_DSP_EXECUTION" and
         receipt["freeze"]==admission.FREEZE and receipt["artifact"]==lock["artifact"] and
         receipt["source_revision"]==OLD and receipt["original_D2_readback_exact"] is True and
         receipt["DSP_executed"] is False and receipt["models_executed"] is False and
         (receipt["case_count"],receipt["frames"],receipt["samples"])==(60,35916,5746560) and
         receipt["budget_seconds"]==300 and 0<=receipt["elapsed_seconds"]<=300,
         "D5_INPUT_NOT_ADMITTED")
    prior,parent=input_root/"original/gain-d2",input_root/"original/result"
    need(digest(prior/"report.json")==lock["report_sha256"] and
         digest(prior/"artifact-manifest.json")==lock["manifest_sha256"],"D5_ORIGINAL_REPORT_CHANGED")
    need(d2.read_json(prior/"artifact-manifest.json")["files"]==d2.payload_inventory(prior),
         "D5_ORIGINAL_D2_PAYLOAD_CHANGED")
    binding=d2.read_json(prior/"parent-binding.json")
    for name,key in (("report.json","report"),("artifact-manifest.json","manifest"),
                     ("readback.json","readback"),("run-index.json","run_index"),
                     ("build/build-manifest.json","build_manifest")):
        need(descriptor(parent/name)==binding[key],"D5_ORIGINAL_PARENT_CHANGED")
    need(d2.read_json(parent/"artifact-manifest.json")["files"]==d2.d1.payload_inventory(parent),
         "D5_ORIGINAL_D1_PAYLOAD_CHANGED")
    old_lock=d2.input_lock()
    need((prior/"input-lock.json").read_bytes()==(ROOT/d2.LOCK_NAME).read_bytes(),"D5_ORIGINAL_LOCK_CHANGED")
    d2.verify_sources(prior,old_lock)
    remaining(start,300)
    return prior,parent,old_lock

def old_sources(input_root,parent):
    manifest=d2.read_json(parent/"build/build-manifest.json")
    spec=manifest["source_archive"]
    archive=d2.safe(input_root/"original/build",spec["path"])
    need(descriptor(archive)=={k:spec[k] for k in ("bytes","sha256")},"D5_ORIGINAL_SOURCE_ARCHIVE")
    result={}
    with tarfile.open(archive,"r:") as stream:
        for name in ("src/enhance/ap_agc.c","src/enhance/ap_enhance.h"):
            members=[m for m in stream.getmembers() if m.name==name]
            need(len(members)==1 and members[0].isfile() and
                 0 < members[0].size <= 262144,"D5_EXACT_ARCHIVE_SOURCE_MEMBER")
            f=stream.extractfile(members[0])
            need(f is not None,"D5_MISSING_ARCHIVE_MEMBER")
            raw=f.read(members[0].size+1)
            need(len(raw)==members[0].size,"D5_TRUNCATED_ARCHIVE_SOURCE")
            import hashlib
            need(hashlib.sha256(raw).hexdigest()==manifest["production_files"][name]["sha256"],
                 "D5_ARCHIVED_PRODUCTION_SOURCE_CHANGED")
            result[name]=raw
    return result



def derived(baseline):
    need(baseline.count(BEFORE)==1,"D5_EXACT_INTERVENTION_SITE")
    candidate=baseline.replace(BEFORE,"")
    for name in ("ap_agc_init","ap_agc_process_controlled","ap_agc_process"):
        candidate=candidate.replace(name,"d5"+name[2:])
    return candidate

def command(argv,log,start):
    begin=time.monotonic()
    receipt={"argv":argv,"returncode":None,"budget_seconds":30,"status":"FAIL"}
    try:
        with log.open("xb") as stream:
            r=subprocess.run(argv,cwd=ROOT,env=d2.d1.process_environment(),stdout=stream,
                stderr=subprocess.STDOUT,timeout=remaining(start,300),check=False)
        receipt.update(returncode=r.returncode,status="PASS" if r.returncode==0 else "FAIL")
    except Exception as error:
        receipt.update(reason=type(error).__name__)
        raise
    finally:
        receipt["elapsed_seconds"]=time.monotonic()-begin
        dump(log.with_name(log.stem+"-command.json"),receipt)
    need(receipt["status"]=="PASS" and receipt["elapsed_seconds"]<=30,"D5_COMMAND_FAILED")
    remaining(start,300)

def compiler_identity():
    """Resolve the system compiler selector, without permitting evidence symlinks."""
    lookup=shutil.which("cc")
    need(lookup is not None,"D5_COMPILER_MISSING")
    path=Path(lookup).absolute()
    resolved=path.resolve(strict=True)
    return {"lookup_path":str(path),"lookup_symlink_target":os.readlink(path) if path.is_symlink() else None,
            "resolved_path":str(resolved),"file":descriptor(resolved)}

def verify_compiler(expected):
    actual=compiler_identity()
    need(actual==expected,"D5_COMPILER_IDENTITY")
    return actual["resolved_path"]

def compile_argv(compiler):
    return [compiler,"-std=c11","-O2","-ffp-contract=off","-Wall","-Wextra","-Werror",
            "-DAP_BUILD_STAGE_AGC=1","-I"+str(EXECUTION_ROOT/"source"),
            str(EXECUTION_ROOT/"source/runner.c"),str(EXECUTION_ROOT/"source/candidate.c"),
            str(EXECUTION_ROOT/"source/original-library.a"),"-lm","-o",str(EXECUTION_ROOT/"replay")]

def dirs_for(files):
    result=set()
    for name in files:
        parent=Path(name).parent
        while str(parent)!=".":
            result.add(parent.as_posix());parent=parent.parent
    return result

def closure(root,files,reason,max_bytes=256*1024*1024):
    need(root.is_dir() and not root.is_symlink(),reason)
    paths=list(root.rglob("*"))
    need(all(not p.is_symlink() and (p.is_file() or p.is_dir()) for p in paths),reason)
    need({p.relative_to(root).as_posix() for p in paths if p.is_file()}==set(files) and
         {p.relative_to(root).as_posix() for p in paths if p.is_dir()}==dirs_for(files),reason)
    need(sum(p.stat().st_size for p in paths if p.is_file())<=max_bytes,"D5_OUTPUT_BYTES_BOUND")

def build(input_root,output,start):
    need(output==EXECUTION_ROOT and input_root==INPUT_ROOT,"D5_FROZEN_EXECUTION_ROOT")
    prior,parent,lock=original(input_root,start)
    archived=old_sources(input_root,parent)
    (output/"source/enhance").mkdir(parents=True)
    for name,dest in (("src/enhance/ap_agc.c","baseline.c"),("src/enhance/ap_enhance.h","enhance/ap_enhance.h")):
        (output/"source"/dest).write_bytes(archived[name])
    (output/"source/candidate.c").write_text(derived(archived["src/enhance/ap_agc.c"].decode()))
    proof=source_proof(start)
    for name in source_names():
        dest=output/"source/repository"/name;dest.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(ROOT/name,dest)
    shutil.copyfile(ROOT/C_PATH,output/"source/runner.c")
    for dest,origin in COPIES.items():
        shutil.copyfile(input_root/origin,output/dest)
    _,old_build=d2.verify_sources(prior,lock)
    library=old_build["parent_plain"]["library"]
    old_library=prior/"proof/plain"/library["path"]
    need(descriptor(old_library)=={k:library[k] for k in ("bytes","sha256")},"D5_ORIGINAL_LIBRARY_CHANGED")
    shutil.copyfile(old_library,output/"source/original-library.a")
    compiler_record=compiler_identity()
    compiler=compiler_record["resolved_path"]
    command([compiler,"--version"],output/"compiler.log",start)
    command(compile_argv(compiler),output/"build.log",start)
    command([str(output/"replay"),"--self-test"],output/"self-test.log",start)
    files={p.relative_to(output/"source").as_posix():descriptor(p)
           for p in (output/"source").rglob("*") if p.is_file()}
    dump(output/"build.json",{"experiment":EXPERIMENT,"freeze":FREEZE,"source":proof,
         "original_source":OLD,"source_files":files,"compiler_path":compiler,
         "compiler":compiler_record,"compiler_version":descriptor(output/"compiler.log"),
         "command":compile_argv(compiler),"program":descriptor(output/"replay"),
         "intervention_remove":BEFORE,"original_D2_library_used":True,"same_old_compiler_claim":False,
         "promotion_allowed":False,"python":sys.version})

def verify_build(input_root,output,start):
    b=d2.read_json(output/"build.json")
    need(b["experiment"]==EXPERIMENT and b["freeze"]==FREEZE and b["original_source"]==OLD,
         "D5_BUILD_IDENTITY")
    need(b["source"]==source_proof(start),"D5_SOURCE_IDENTITY")
    names={"runner.c","candidate.c","baseline.c","original-library.a","enhance/ap_enhance.h",
           *("repository/"+name for name in source_names())}
    closure(output/"source",names,"D5_SOURCE_CLOSURE",16*1024*1024)
    actual={name:descriptor(output/"source"/name) for name in names}
    need(actual==b["source_files"],"D5_SOURCE_SEAL_CHANGED")
    for name in source_names():
        need((output/"source/repository"/name).read_bytes()==(ROOT/name).read_bytes(),"D5_SAVED_SOURCE_CHANGED")
    need((output/"source/runner.c").read_bytes()==(ROOT/C_PATH).read_bytes(),"D5_SAVED_SOURCE_CHANGED")
    archive=old_sources(input_root,input_root/"original/result")
    for name,dest in (("src/enhance/ap_agc.c","baseline.c"),("src/enhance/ap_enhance.h","enhance/ap_enhance.h")):
        need((output/"source"/dest).read_bytes()==archive[name],"D5_SAVED_ARCHIVE_SOURCE_CHANGED")
    need((output/"source/candidate.c").read_text()==derived(archive["src/enhance/ap_agc.c"].decode()) and
         b["intervention_remove"]==BEFORE,"D5_CANDIDATE_DERIVATION")
    library=d2.read_json(input_root/"original/gain-d2/build-manifest.json")["parent_plain"]["library"]
    need(descriptor(output/"source/original-library.a")=={k:library[k] for k in ("bytes","sha256")},
         "D5_BASELINE_LIBRARY_NOT_ORIGINAL")
    need(b["program"]==descriptor(output/"replay"),"D5_PROGRAM_CHANGED")
    compiler=verify_compiler(b["compiler"])
    need(compiler==b["compiler_path"] and
         descriptor(output/"compiler.log")==b["compiler_version"],"D5_COMPILER_IDENTITY")
    argv={"build":compile_argv(compiler),"compiler":[compiler,"--version"],
          "self-test":[str(EXECUTION_ROOT/"replay"),"--self-test"]}
    need(b["command"]==argv["build"],"D5_BUILD_ARGV_CHANGED")
    for key,expected in argv.items():
        check_command(output/(key+"-command.json"),expected)
    for dest,origin in COPIES.items():
        need((output/dest).read_bytes()==(input_root/origin).read_bytes(),"D5_SAVED_INPUT_CHANGED")
    return b

def check_command(path,argv):
    receipt=d2.read_json(path)
    need(receipt["argv"]==argv,"D5_COMMAND_ARGV_CHANGED")
    need(receipt["status"]=="PASS" and receipt["returncode"]==0 and
         receipt["budget_seconds"]==30 and 0<=receipt["elapsed_seconds"]<=30,"D5_COMMAND_RECEIPT_FAILED")

def phase_pass(output,phase):
    receipt=d2.read_json(output/(phase+"-phase.json"))
    need(receipt["phase"]==phase and receipt["status"]=="PASS" and receipt["budget_seconds"]==300 and
         0<=receipt["elapsed_seconds"]<=300,"D5_PHASE_FAILED")

def case_argv(case):
    folder=EXECUTION_ROOT/"cases"/case["key"]
    taps=INPUT_ROOT/"original/result/cases"/case["key"]/"taps"
    return [str(EXECUTION_ROOT/"replay"),str(taps/"ns_output.f32le"),str(taps/"agc_output.f32le"),
            str(folder/"control.bin"),str(folder/"baseline.f32le"),str(folder/"candidate.f32le"),
            str(folder/"trace.bin"),case["profile"],str(case["frames"])]

def run(input_root,output,start):
    need(output==EXECUTION_ROOT and input_root==INPUT_ROOT,"D5_FROZEN_EXECUTION_ROOT")
    prior,parent,lock=original(input_root,start);verify_build(input_root,output,start);phase_pass(output,"build")
    (output/"cases").mkdir()
    for entry in lock["cases"]:
        case=entry["catalog"];folder=output/"cases"/case["key"];folder.mkdir(parents=True)
        taps=parent/"cases"/case["key"]/"taps"
        for name,expected in entry["parent_taps"].items():
            need(descriptor(taps/name)==expected,"D5_INPUT_CHANGED")
        (folder/"control.bin").write_bytes(d2.control_bytes(taps/"control.csv",case))
        command(case_argv(case),folder/"execution.log",start)
    dump(output/"run-index.json",{"experiment":EXPERIMENT,"completed":[e["catalog"]["key"] for e in lock["cases"]],
                                 "expected":60})

def observation(signal,before,allow,target,limit,candidate):
    # Preserve the canonical original Float32 audit, then remove only target cap.
    values,flags=d2.gain_observation(signal,before,1 if candidate else allow,target,limit)
    if candidate:
        after=values["expected_state_gain_after"]
        gate=min(after,1.0) if not allow else after
        peak=values["input_peak"]
        active=int(d2.f32(peak*gate)>limit and peak>d2.f32(1e-6))
        values.update(gate_cap_gain=gate,applied_gain=values["peak_limit_gain"] if active else gate)
        flags.update(target_gate_cap_active=0,output_gate_cap_active=int(not allow and after>1.0),
                     peak_cap_active=active)
    products=[d2.f32(x*values["applied_gain"]) for x in signal]
    flags["final_sample_clamp_count"]=sum(x < -limit or x > limit for x in products)
    pcm=d2.float_bytes(max(-limit,min(limit,x)) for x in products)
    return {**values,**flags},pcm

def audit_case(entry,old_case,prior,parent,output,start):
    case=entry["catalog"];folder=output/"cases"/case["key"];taps=parent/"cases"/case["key"]/"taps"
    check_command(folder/"execution-command.json",case_argv(case))
    for name,expected in entry["parent_taps"].items():
        need(descriptor(taps/name)==expected,"D5_INPUT_CHANGED")
    controls=d2.control_bytes(taps/"control.csv",case)
    need((folder/"control.bin").read_bytes()==controls,"D5_CONTROLS_CHANGED")
    raw=(taps/"ns_output.f32le").read_bytes()
    samples=struct.unpack("<"+str(case["samples"])+"f",raw)
    base=(folder/"baseline.f32le").read_bytes();candidate=(folder/"candidate.f32le").read_bytes()
    need(base==(taps/"agc_output.f32le").read_bytes(),"D5_BASELINE_NOT_ORIGINAL")
    need(len(candidate)==len(base),"D5_CANDIDATE_SIZE")
    trace=(folder/"trace.bin").read_bytes()
    need(len(trace)==case["frames"]*68,"D5_TRACE_SIZE")
    reader=csv.DictReader(io.StringIO((prior/"cases"/case["key"]/"views/gain.csv").read_text()))
    need(reader.fieldnames==d2.TRACE_FIELDS,"D5_ORIGINAL_TRACE_SCHEMA")
    rows=list(reader);need(len(rows)==case["frames"],"D5_ORIGINAL_TRACE_SIZE")
    counts={"frames":case["frames"],"samples":case["samples"],"resets":0,"zero_frames":0,
            "target_cap_opportunities":0,"prefix_control_frames":0,"changed_output_frames":0,
            "changed_state_frames":0,"baseline_target_caps":0,"baseline_output_caps":0,
            "candidate_target_caps":0,"candidate_output_caps":0,"baseline_peak_caps":0,
            "candidate_peak_caps":0,"baseline_clamped_samples":0,"candidate_clamped_samples":0}
    previous=None;opportunity_seen=False;audit=[];first_state=None;first_frame=None
    max_delta=0.0;all_allow=all(c[0]==1 for c in struct.iter_unpack("<IIff",controls))
    for frame,(state,ctl,row) in enumerate(zip(struct.iter_unpack("<14f3I",trace),
                                             struct.iter_unpack("<IIff",controls),rows)):
        allow,reset,before,after=ctl
        need(tuple(state[14:16])==(allow,reset),"D5_TRACE_CONTROLS")
        signal=samples[frame*160:(frame+1)*160]
        need(all(math.isfinite(x) for x in signal) and all(math.isfinite(x) for x in state[:14]),"D5_NONFINITE")
        zero=all(x==0.0 for x in signal);need(state[16]==int(zero),"D5_ZERO_FLAG")
        need(int(row["frame"])==frame and int(row["allow"])==allow and int(row["reset"])==reset,
             "D5_ORIGINAL_ROW_ID")
        target=d2.f32(float(row["target_linear"]));limit=d2.f32(float(row["limiter_linear"]))
        row_before=d2.f32(float(row["state_gain_before"]));row_after=d2.f32(float(row["state_gain_after"]))
        need(d2.same_float(row_before,before) and d2.same_float(row_after,after),"D5_ORIGINAL_STATE_AUTHORITY")
        need(struct.pack("<6f",*state[:6])==struct.pack("<6f",row_before,target,limit,row_after,target,limit),
             "D5_BASELINE_FULL_STATE")
        expected_before=(1.0,target,limit) if frame==0 or reset else previous
        need(struct.pack("<3f",*state[6:9])==struct.pack("<3f",*expected_before),"D5_STATE_CONTINUITY")
        b,bpcm=observation(signal,before,allow,target,limit,False)
        c,cpcm=observation(signal,state[6],allow,target,limit,True)
        for key in ("input_rms","input_peak","target_gain_raw","target_gain_bounded","target_gain",
                    "alpha","expected_state_gain_after","gate_cap_gain","applied_gain"):
            need(d2.same_float(b[key],d2.f32(float(row[key]))),"D5_BASELINE_AUDIT_NOT_ORIGINAL")
        for key in (*d2.CAP_FIELDS,"final_sample_clamp_count"):
            need(b[key]==int(row[key]),"D5_BASELINE_AUDIT_NOT_ORIGINAL")
        need(struct.pack("<3f",*state[9:12])==struct.pack("<3f",c["expected_state_gain_after"],target,limit),
             "D5_CANDIDATE_STATE_FORMULA")
        need(d2.same_float(state[12],b["applied_gain"]) and d2.same_float(state[13],c["applied_gain"]),
             "D5_APPLIED_GAIN_FORMULA")
        need(allow or state[13]<=1.0,"D5_OUTPUT_UNITY_GATE")
        need(base[frame*640:(frame+1)*640]==bpcm,"D5_BASELINE_OUTPUT_FORMULA")
        need(candidate[frame*640:(frame+1)*640]==cpcm,"D5_CANDIDATE_OUTPUT_FORMULA")
        state_changed=struct.pack("<6f",*state[:6])!=struct.pack("<6f",*state[6:12])
        pcm_changed=bpcm!=cpcm
        if frame==0 or reset: opportunity_seen=False
        opportunity=not allow and b["target_gain_bounded"]>1.0
        if not opportunity_seen:
            need(struct.pack("<3f",*state[:3])==struct.pack("<3f",*state[6:9]),"D5_PREFIX_BEFORE_MISMATCH")
        if not opportunity_seen and not opportunity:
            need(not state_changed and not pcm_changed,"D5_PREFIX_CONTROL_MISMATCH")
            counts["prefix_control_frames"]+=1
        if all_allow:
            need(not state_changed and not pcm_changed,"D5_ALLOW_TRUE_CONTROL_MISMATCH")
        opportunity_seen=opportunity_seen or opportunity
        counts["resets"]+=reset;counts["zero_frames"]+=zero
        counts["target_cap_opportunities"]+=opportunity
        counts["changed_state_frames"]+=state_changed;counts["changed_output_frames"]+=pcm_changed
        if state_changed and first_state is None:first_state=frame
        if pcm_changed and first_frame is None:first_frame=frame
        for arm,obs in (("baseline",b),("candidate",c)):
            for dst,src in (("target_caps","target_gate_cap_active"),("output_caps","output_gate_cap_active"),
                            ("peak_caps","peak_cap_active"),("clamped_samples","final_sample_clamp_count")):
                counts[arm+"_"+dst]+=obs[src]
        max_delta=max(max_delta,abs(state[3]-state[9]))
        audit.append({"frame":frame,"allow":allow,"reset":reset,"digital_zero":zero,
                      "target_cap_opportunity":bool(opportunity),"baseline":b,"candidate":c})
        previous=state[9:12]
        if frame%100==0:remaining(start,300)
    if case["scenario"] in ("near-only","silent-render"):
        need(all_allow,"D5_WHOLE_CONTROL_NOT_ALLOW_TRUE")
    reference=None;reason="no_clean_near_reference"
    if entry["clean_near"] is not None:
        path=d2.safe(parent/"originals/A",case["inputs"]["clean_near"])
        need(descriptor(path)==entry["clean_near"],"D5_REFERENCE_CHANGED")
        reference=[x/32768.0 for x in d2.d1.samples(path,"h",case["samples"])]
    if case["group"]=="C":reason="C_has_no_admitted_clean_near_reference"
    stages={name:d2.d1.measure_lane(list(struct.unpack("<"+str(case["samples"])+"f",value)),
                 160,case["samples"],reference,reason,True)
            for name,value in (("baseline",base),("candidate",candidate))}
    need(old_case["key"]==case["key"] and stages["baseline"]==old_case["stages"]["replay_final"],
         "D5_ORIGINAL_ENDPOINT_SCORE")
    delta=d2.d1.stage_delta(stages,"baseline","candidate","target_gate_removal_total_intervention_effect")
    changed,first=d2.differences(base,candidate)
    return {"key":case["key"],"group":case["group"],"profile":case["profile"],"scenario":case["scenario"],
            "counts":counts,"changed_samples":changed,"first_difference":first,
            "first_changed_state_frame":first_state,"first_changed_output_frame":first_frame,
            "max_state_gain_delta":max_delta,"whole_allow_true":all_allow,"prefix_control_exact":True,
            "baseline_original_state_and_output_exact":True,"continuous_candidate_arithmetic_exact":True,
            "audit_origin":AUDIT_ORIGIN,"frame_audit":audit,"stages":stages,"delta":delta,
            "files":{name:descriptor(folder/name) for name in sorted(CASE_FILES)}}

def analyze(input_root,output,start,saved=None):
    prior,parent,lock=original(input_root,start)
    b=verify_build(input_root,output,start)
    phase_pass(output,"build");phase_pass(output,"run")
    names={"source/"+name for name in b["source_files"]}|set(COPIES)|BUILD_FILES|{"run-index.json"}
    names|={name for name in OPTIONAL_FILES if (output/name).exists()}
    names|={"cases/"+entry["catalog"]["key"]+"/"+name for entry in lock["cases"] for name in CASE_FILES}
    closure(output,names,"D5_OUTPUT_CLOSURE")
    expected_keys=[entry["catalog"]["key"] for entry in lock["cases"]]
    need(d2.read_json(output/"run-index.json")=={"experiment":EXPERIMENT,"completed":expected_keys,"expected":60},
         "D5_RUN_MATRIX_CHANGED")
    if saved is not None:
        need(saved["source"]==b["source"],"D5_REPORT_SOURCE_CHANGED")
        need([c["key"] for c in saved["cases"]]==expected_keys,"D5_REPORT_CASE_SET")
    old=d2.read_json(prior/"report.json")
    need([c["key"] for c in old["cases"]]==expected_keys,"D5_ORIGINAL_CASE_SET")
    cases=[];totals={};windows=0;scored=0
    for index,(entry,old_case) in enumerate(zip(lock["cases"],old["cases"])):
        case=audit_case(entry,old_case,prior,parent,output,start)
        if saved is not None:
            need(case==saved["cases"][index],"D5_READBACK_CASE_DIFFERS")
        cases.append(case)
        for key,value in case["counts"].items():totals[key]=totals.get(key,0)+value
        windows+=len(case["stages"]["baseline"]["one_second_windows"])
        scored+=case["stages"]["baseline"]["common"]["near_si_sdr_db"] is not None
        remaining(start,300)
    need((len(cases),windows,totals["frames"],totals["samples"],totals["resets"],scored)==
         (60,362,35916,5746560,8,32),"D5_MATRIX_TOTALS")
    groups=[]
    for group,profile,scenario in sorted({(c["group"],c["profile"],c["scenario"]) for c in cases}):
        selected=[c for c in cases if (c["group"],c["profile"],c["scenario"])==(group,profile,scenario)]
        vals=[c["delta"]["common"]["near_si_sdr_change_db"] for c in selected
              if c["delta"]["common"]["near_si_sdr_change_db"] is not None]
        # Preserve every metric below; these descriptive groups never select a candidate.
        groups.append({"group":group,"profile":profile,"scenario":scenario,"cases":len(selected),
                       "scored":len(vals),"null":len(selected)-len(vals),
                       "min":min(vals) if vals else None,"median":statistics.median(vals) if vals else None,
                       "max":max(vals) if vals else None,
                       "rms_change_db":[c["delta"]["common"]["rms_change_db"] for c in selected]})
    report={"experiment":EXPERIMENT,"status":"TARGET_GATE_CONTROLLED_DIAGNOSIS_NO_PROMOTION",
            "freeze":FREEZE,"source":b["source"],"original_source":OLD,"input_artifact":frozen()["artifact"],
            "case_count":60,"window_count":windows,"scored_cases":scored,"null_cases":60-scored,
            "totals":totals,"cases":cases,"aggregates":groups,"audit_origin":AUDIT_ORIGIN,
            "effect":"total intervention, including same-frame state/alpha and downstream cap mediators",
            "data_role":"disclosed-regression","independent_observations":False,
            "fresh_baseline_matches_original_D2":True,"promotion_allowed":False,"models_executed":False,
            "physical_device_executed":False,
            "limitations":["fixed original inputs/gates, not feedback-integrated Activity",
                           "not integrated 2.3.64 pipeline, listening, ASR/KWS or physical-target evidence",
                           "real English recording with synthetic propagation; one Chinese recording; no independent validation"],
            "input_bindings":{name:descriptor(output/name) for name in COPIES}}
    if saved is not None:need(report==saved,"D5_READBACK_REPORT_DIFFERS")
    return report

def verify_report(input_root,output,start):
    phase_pass(output,"analysis")
    if (output/"verify-phase.json").exists():phase_pass(output,"verify")
    saved=d2.read_json(output/"report.json")
    if (output/"readback.json").exists():
        need(d2.read_json(output/"readback.json")==
             {"status":"PASS","DSP_executed":False,"models_executed":False,
              "report":descriptor(output/"report.json")},"D5_READBACK_RECEIPT_CHANGED")
    return analyze(input_root,output,start,saved)

def summary(report):
    return {key:report[key] for key in ("experiment","status","case_count","window_count","scored_cases",
                                      "null_cases","totals","aggregates","promotion_allowed")}

def no_symlink_path(path):
    return not any(p.is_symlink() for p in (path,*path.parents))

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase",choices=("build","run","analysis","verify"))
    parser.add_argument("--input",required=True,type=Path)
    parser.add_argument("--output",required=True,type=Path)
    args=parser.parse_args();start=time.monotonic()
    output=args.output.absolute();input_root=args.input.resolve();can_write=False
    receipt={"phase":args.phase,"status":"FAIL","budget_seconds":300}
    marker=output/(args.phase+"-phase.json")
    try:
        if args.phase=="build":
            need(not output.exists() and no_symlink_path(output),"D5_FRESH_OUTPUT_REQUIRED")
            need(output==EXECUTION_ROOT and input_root==INPUT_ROOT,"D5_FROZEN_EXECUTION_ROOT")
            output.mkdir(parents=True);can_write=True
            build(input_root,output,start)
        else:
            need(output.is_dir() and no_symlink_path(output) and
                 not marker.exists() and not marker.is_symlink(),"D5_NEW_PHASE_RECEIPT_REQUIRED")
            extras={"run":("cases","run-index.json"),"analysis":("report.json",),
                    "verify":("readback.json",)}[args.phase]
            need(all(not (output/n).exists() and not (output/n).is_symlink() for n in extras),
                 "D5_NEW_PHASE_OUTPUT_REQUIRED")
            can_write=True
            if args.phase=="run":run(input_root,output,start)
            else:
                report=analyze(input_root,output,start) if args.phase=="analysis" else verify_report(input_root,output,start)
                if args.phase=="analysis":dump(output/"report.json",report)
                else:dump(output/"readback.json",{"status":"PASS","DSP_executed":False,"models_executed":False,
                                                  "report":descriptor(output/"report.json")})
                print(json.dumps(summary(report),sort_keys=True))
        remaining(start,300);receipt["status"]="PASS"
    except Exception as error:
        receipt.update(reason=str(error),error_type=type(error).__name__)
        raise
    finally:
        if can_write:
            receipt["elapsed_seconds"]=time.monotonic()-start;dump(marker,receipt)
            if time.monotonic()-start>300:
                receipt.update(status="FAIL",reason="D5_FINAL_WRITE_BUDGET_EXCEEDED",
                               elapsed_seconds=time.monotonic()-start)
                # Only this invocation's newly-created receipt may record its final-write failure.
                marker.write_text(json.dumps(receipt,sort_keys=True)+"\n")
                raise ValueError(receipt["reason"])

if __name__=="__main__":
    main()
