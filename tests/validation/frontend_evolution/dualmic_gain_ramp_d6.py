#!/usr/bin/env python3
"""D6: one intraframe output gain ramp; original state and D2 byte authority."""
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
EXPERIMENT = "FE-DUALMIC-GAIN-RAMP-D6"
FREEZE = "caaed2efa09243b99064c8ee793d3c27591ab6df"
OLD = "cc853616685b9faf7880e6d8f8f1a89d187d342a"
C_PATH = "tests/validation/frontend_evolution/dualmic_gain_ramp_d6.c"
PY_PATH = "tests/validation/frontend_evolution/dualmic_gain_ramp_d6.py"
TEST = "tests/validation/frontend_evolution/test_dualmic_gain_ramp_d6.py"
PLAN = "docs/research/frontend-evolution-v1/DUALMIC_GAIN_RAMP_D6_PLAN.zh-CN.md"
LOCK = "docs/research/frontend-evolution-v1/dualmic-gain-ramp-d6-input-lock.json"
WORKFLOW = ".github/workflows/frontend-research.yml"
NOTE = "docs/research/frontend-evolution-v1/DUALMIC_GAIN_RAMP_D6_IMPLEMENTATION.zh-CN.md"
EXECUTION_ROOT = Path("/tmp/ap-dualmic-d6/result")
INPUT_ROOT = Path("/tmp/ap-dualmic-d6/input")
H_PATH = "tests/validation/frontend_evolution/dualmic_gain_ramp_d6.h"
PINS = {PLAN: "a01670491a17b4ccb2dbc8d7d2ecdfb7dec9d928",
        LOCK: "00efd3e192093d0e72e93c017e45f87353c7c09b"}
BASE = "6c7752800838f2c7fd707593c658f250a071e98c"
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
CASE_FILES = {"control.bin","baseline.f32le","candidate.f32le","trace.bin","candidate-gain.f32le",
              "execution.log","execution-command.json"}
BUILD_FILES = {"compiler.log","compiler-command.json","build.log","build-command.json",
               "self-test.log","self-test-command.json","build.json","replay","build-phase.json"}
OPTIONAL_FILES = {"run-phase.json","analysis-phase.json","report.json","verify-phase.json","readback.json"}
AUDIT_ORIGIN = "state/PCM/all applied coefficients and S/G/extra state measured by C; target/alpha/caps reconstructed with independent Float32 arithmetic and compared to every actual byte"

def dump(path, value):
    with Path(path).open("x",encoding="utf-8") as out:
        json.dump(value,out,ensure_ascii=False,sort_keys=True,indent=2,allow_nan=False)
        out.write("\n")

def descriptor(path):
    need(path.is_file() and not path.is_symlink(),"D6_REGULAR_FILE_REQUIRED")
    return {"bytes":path.stat().st_size,"sha256":digest(path)}

def blob(raw):
    return hashlib.sha1(b"blob "+str(len(raw)).encode()+b"\0"+raw).hexdigest()

def git(start,*args):
    return subprocess.check_output(["git",*args],cwd=ROOT,
        env=d2.d1.process_environment(),timeout=min(30.0,remaining(start,300))).decode().strip()

def contract():
    for name,expected in PINS.items():
        need(blob((ROOT/name).read_bytes())==expected,"D6_FROZEN_CONTRACT_CHANGED")
    return d2.read_json(ROOT/LOCK)

def frozen():
    locked=contract()
    need(locked["experiment"]==EXPERIMENT and locked["base_sha"]==BASE and
         locked["candidates"]==1,"D6_CONTRACT_IDENTITY")
    need(set(locked["frozen_helper_files"])==set(FROZEN_HELPERS),"D6_HELPER_CLOSURE")
    for name,expected in locked["frozen_helper_files"].items():
        raw=(ROOT/name).read_bytes()
        need(blob(raw)==expected["git_blob"]==FROZEN_HELPERS[name] and
             descriptor(ROOT/name)=={k:expected[k] for k in ("bytes","sha256")},
             "D6_FROZEN_HELPER_CHANGED")
    old=admission.frozen_lock()
    need(all(locked["original_admission"].get(k)==v for k,v in old.items()) and
         locked["original_d2_case_input_lock"]==d2.input_lock(),"D6_COMPLETE_INPUT_LOCK")
    return old

def source_names():
    locked=contract()
    need(set(locked["source_closure"]["frozen_helpers"])==set(FROZEN_HELPERS),"D6_HELPER_CLOSURE")
    return set(locked["source_closure"]["frozen_helpers"])|set(locked["source_closure"]["candidate_files"])

def source_proof(start):
    head,tree=git(start,"rev-parse","HEAD"),git(start,"rev-parse","HEAD^{tree}")
    names=source_names()
    for name,expected in contract()["unchanged_production_objects"].items():
        need(git(start,"rev-parse",head+":"+name)==expected["git_object"],"D6_PRODUCTION_CHANGED")
    for name in sorted(names):
        need(git(start,"rev-parse",head+":"+name)==blob((ROOT/name).read_bytes()),"D6_UNCOMMITTED_SOURCE")
    # Explicitly prove all imported repository modules belong to the retained closure.
    for module in list(sys.modules.values()):
        path=getattr(module,"__file__",None)
        if path is None:
            continue
        try:
            relative=Path(path).resolve().relative_to(ROOT).as_posix()
        except ValueError:
            continue
        need(relative in names,"D6_UNRETAINED_IMPORTED_MODULE:"+relative)
    return {"revision":head,"tree":tree,"files":{n:descriptor(ROOT/n) for n in sorted(names)}}

def original(input_root,start):
    need(input_root.is_dir() and no_symlink_path(input_root),"D6_INPUT_DIRECTORY")
    need((input_root/"admission.json").is_file() and not (input_root/"admission.json").is_symlink(),"D6_INPUT_NOT_ADMITTED")
    lock=frozen()
    receipt=d2.read_json(input_root/"admission.json")
    need(receipt["status"]=="INPUT_ADMITTED_NO_DSP_EXECUTION" and
         receipt["freeze"]==admission.FREEZE and receipt["artifact"]==lock["artifact"] and
         receipt["source_revision"]==OLD and receipt["original_D2_readback_exact"] is True and
         receipt["DSP_executed"] is False and receipt["models_executed"] is False and
         (receipt["case_count"],receipt["frames"],receipt["samples"])==(60,35916,5746560) and
         receipt["budget_seconds"]==300 and 0<=receipt["elapsed_seconds"]<=300,
         "D6_INPUT_NOT_ADMITTED")
    prior,parent=input_root/"original/gain-d2",input_root/"original/result"
    need(digest(prior/"report.json")==lock["report_sha256"] and
         digest(prior/"artifact-manifest.json")==lock["manifest_sha256"],"D6_ORIGINAL_REPORT_CHANGED")
    need(d2.read_json(prior/"artifact-manifest.json")["files"]==d2.payload_inventory(prior),
         "D6_ORIGINAL_D2_PAYLOAD_CHANGED")
    binding=d2.read_json(prior/"parent-binding.json")
    for name,key in (("report.json","report"),("artifact-manifest.json","manifest"),
                     ("readback.json","readback"),("run-index.json","run_index"),
                     ("build/build-manifest.json","build_manifest")):
        need(descriptor(parent/name)==binding[key],"D6_ORIGINAL_PARENT_CHANGED")
    need(d2.read_json(parent/"artifact-manifest.json")["files"]==d2.d1.payload_inventory(parent),
         "D6_ORIGINAL_D1_PAYLOAD_CHANGED")
    old_lock=d2.input_lock()
    need((prior/"input-lock.json").read_bytes()==(ROOT/d2.LOCK_NAME).read_bytes(),"D6_ORIGINAL_LOCK_CHANGED")
    d2.verify_sources(prior,old_lock)
    remaining(start,300)
    return prior,parent,old_lock

def old_sources(input_root,parent):
    manifest=d2.read_json(parent/"build/build-manifest.json")
    spec=manifest["source_archive"]
    archive=d2.safe(input_root/"original/build",spec["path"])
    need(descriptor(archive)=={k:spec[k] for k in ("bytes","sha256")},"D6_ORIGINAL_SOURCE_ARCHIVE")
    result={}
    with tarfile.open(archive,"r:") as stream:
        for name in ("src/enhance/ap_agc.c","src/enhance/ap_enhance.h"):
            members=[m for m in stream.getmembers() if m.name==name]
            need(len(members)==1 and members[0].isfile() and
                 0 < members[0].size <= 262144,"D6_EXACT_ARCHIVE_SOURCE_MEMBER")
            f=stream.extractfile(members[0])
            need(f is not None,"D6_MISSING_ARCHIVE_MEMBER")
            raw=f.read(members[0].size+1)
            need(len(raw)==members[0].size,"D6_TRUNCATED_ARCHIVE_SOURCE")
            import hashlib
            need(hashlib.sha256(raw).hexdigest()==manifest["production_files"][name]["sha256"],
                 "D6_ARCHIVED_PRODUCTION_SOURCE_CHANGED")
            locked=contract()["old_agc_source" if name.endswith("ap_agc.c") else "original_header"]
            need(blob(raw)==locked["git_blob"] and len(raw)==locked["bytes"] and
                 hashlib.sha256(raw).hexdigest()==locked["sha256"],"D6_ORIGINAL_C_HEADER_LOCK")
            result[name]=raw
    return result



DERIVATION = [
    ("#include \"enhance/ap_enhance.h\"", "#include \"enhance/ap_enhance.h\"\n#include \"candidate-api.h\""),
    ("void ap_agc_init(", "static float d6_cap(float value, float peak, float limit, int allow) {\n    if (!allow && value > 1.0f) value = 1.0f;\n    if (peak * value > limit && peak > 1.0e-6f) value = limit / peak;\n    return value;\n}\n\nvoid ap_agc_init("),
    ("                               int allow_gain_increase) {", "                               int allow_gain_increase,\n                               d6_ramp_state_t *ramp, float *coefficients,\n                               d6_observation_t *observation) {"),
    ("                    uint32_t n) {\n    ap_agc_process_controlled(state, x, n, 1);\n}", "                    uint32_t n, d6_ramp_state_t *ramp,\n                    float *coefficients, d6_observation_t *observation) {\n    ap_agc_process_controlled(state, x, n, 1, ramp, coefficients, observation);\n}"),
    ("        for (i = 0u; i < n; ++i) x[i] = ap_agc_clamp(x[i] * gain, -limit, limit);", "        const float start = ramp->initialized ? d6_cap(ramp->previous, peak, limit, allow_gain_increase) : gain;\n        const float delta = gain - start;\n        observation->start = start;\n        observation->end = gain;\n        for (i = 0u; i < n; ++i) {\n            const float weight = (float)(i + 1u) / 160.0f;\n            const float product = delta * weight;\n            const float interpolated = (i == 159u) ? gain : start + product;\n            const float coefficient = d6_cap(interpolated, peak, limit, allow_gain_increase);\n            coefficients[i] = coefficient;\n            x[i] = ap_agc_clamp(x[i] * coefficient, -limit, limit);\n        }\n        ramp->previous = coefficients[159];\n        ramp->initialized = 1u;")
]

def derived(baseline):
    candidate=baseline
    for before,after in DERIVATION:
        need(candidate.count(before)==1,"D6_EXACT_INTERVENTION_SITE")
        candidate=candidate.replace(before,after)
    for name in ("ap_agc_init","ap_agc_process_controlled","ap_agc_process"):
        candidate=candidate.replace(name,"d6"+name[2:])
    return candidate

def command(argv,log,start):
    begin=time.monotonic()
    receipt={"argv":argv,"returncode":None,"budget_seconds":30,"status":"FAIL"}
    try:
        with log.open("xb") as stream:
            r=subprocess.run(argv,cwd=ROOT,env=d2.d1.process_environment(),stdout=stream,
                stderr=subprocess.STDOUT,timeout=min(30.0,remaining(start,300)),check=False)
        receipt.update(returncode=r.returncode,status="PASS" if r.returncode==0 else "FAIL")
    except Exception as error:
        receipt.update(reason=type(error).__name__)
        raise
    finally:
        receipt["elapsed_seconds"]=time.monotonic()-begin
        dump(log.with_name(log.stem+"-command.json"),receipt)
    need(receipt["status"]=="PASS" and receipt["elapsed_seconds"]<=30,"D6_COMMAND_FAILED")
    remaining(start,300)

def compiler_identity():
    """Resolve the system compiler selector, without permitting evidence symlinks."""
    lookup=shutil.which("cc")
    need(lookup is not None,"D6_COMPILER_MISSING")
    path=Path(lookup).absolute()
    resolved=path.resolve(strict=True)
    return {"lookup_path":str(path),"lookup_symlink_target":os.readlink(path) if path.is_symlink() else None,
            "resolved_path":str(resolved),"file":descriptor(resolved)}

def verify_compiler(expected):
    actual=compiler_identity()
    need(actual==expected,"D6_COMPILER_IDENTITY")
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
    need(sum(p.stat().st_size for p in paths if p.is_file())<=max_bytes,"D6_OUTPUT_BYTES_BOUND")

def build(input_root,output,start):
    need(output==EXECUTION_ROOT and input_root==INPUT_ROOT,"D6_FROZEN_EXECUTION_ROOT")
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
    shutil.copyfile(ROOT/H_PATH,output/"source/candidate-api.h")
    for dest,origin in COPIES.items():
        shutil.copyfile(input_root/origin,output/dest)
    _,old_build=d2.verify_sources(prior,lock)
    library=old_build["parent_plain"]["library"]
    old_library=prior/"proof/plain"/library["path"]
    need(descriptor(old_library)=={k:library[k] for k in ("bytes","sha256")},"D6_ORIGINAL_LIBRARY_CHANGED")
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
         "intervention":"frozen output-only intraframe linear gain ramp","original_D2_library_used":True,"same_old_compiler_claim":False,
         "promotion_allowed":False,"python":sys.version})

def verify_build(input_root,output,start):
    b=d2.read_json(output/"build.json")
    need(b["experiment"]==EXPERIMENT and b["freeze"]==FREEZE and b["original_source"]==OLD,
         "D6_BUILD_IDENTITY")
    need(b["source"]==source_proof(start),"D6_SOURCE_IDENTITY")
    names={"runner.c","candidate.c","candidate-api.h","baseline.c","original-library.a","enhance/ap_enhance.h",
           *("repository/"+name for name in source_names())}
    closure(output/"source",names,"D6_SOURCE_CLOSURE",16*1024*1024)
    actual={name:descriptor(output/"source"/name) for name in names}
    need(actual==b["source_files"],"D6_SOURCE_SEAL_CHANGED")
    for name in source_names():
        need((output/"source/repository"/name).read_bytes()==(ROOT/name).read_bytes(),"D6_SAVED_SOURCE_CHANGED")
    need((output/"source/runner.c").read_bytes()==(ROOT/C_PATH).read_bytes(),"D6_SAVED_SOURCE_CHANGED")
    need((output/"source/candidate-api.h").read_bytes()==(ROOT/H_PATH).read_bytes(),"D6_SAVED_HEADER_CHANGED")
    archive=old_sources(input_root,input_root/"original/result")
    for name,dest in (("src/enhance/ap_agc.c","baseline.c"),("src/enhance/ap_enhance.h","enhance/ap_enhance.h")):
        need((output/"source"/dest).read_bytes()==archive[name],"D6_SAVED_ARCHIVE_SOURCE_CHANGED")
    need((output/"source/candidate.c").read_text()==derived(archive["src/enhance/ap_agc.c"].decode()) and
         b["intervention"]=="frozen output-only intraframe linear gain ramp","D6_CANDIDATE_DERIVATION")
    library=d2.read_json(input_root/"original/gain-d2/build-manifest.json")["parent_plain"]["library"]
    need(descriptor(output/"source/original-library.a")=={k:library[k] for k in ("bytes","sha256")},
         "D6_BASELINE_LIBRARY_NOT_ORIGINAL")
    need(b["program"]==descriptor(output/"replay"),"D6_PROGRAM_CHANGED")
    compiler=verify_compiler(b["compiler"])
    need(compiler==b["compiler_path"] and
         descriptor(output/"compiler.log")==b["compiler_version"],"D6_COMPILER_IDENTITY")
    argv={"build":compile_argv(compiler),"compiler":[compiler,"--version"],
          "self-test":[str(EXECUTION_ROOT/"replay"),"--self-test"]}
    need(b["command"]==argv["build"],"D6_BUILD_ARGV_CHANGED")
    for key,expected in argv.items():
        check_command(output/(key+"-command.json"),expected)
    for dest,origin in COPIES.items():
        need((output/dest).read_bytes()==(input_root/origin).read_bytes(),"D6_SAVED_INPUT_CHANGED")
    return b

def check_command(path,argv):
    receipt=d2.read_json(path)
    need(receipt["argv"]==argv,"D6_COMMAND_ARGV_CHANGED")
    need(receipt["status"]=="PASS" and receipt["returncode"]==0 and
         receipt["budget_seconds"]==30 and 0<=receipt["elapsed_seconds"]<=30,"D6_COMMAND_RECEIPT_FAILED")

def phase_pass(output,phase):
    receipt=d2.read_json(output/(phase+"-phase.json"))
    need(receipt["phase"]==phase and receipt["status"]=="PASS" and receipt["measurement_status"]=="PHASE_VALID" and receipt["budget_seconds"]==300 and
         0<=receipt["elapsed_seconds"]<=300,"D6_PHASE_FAILED")

def case_argv(case):
    folder=EXECUTION_ROOT/"cases"/case["key"]
    taps=INPUT_ROOT/"original/result/cases"/case["key"]/"taps"
    return [str(EXECUTION_ROOT/"replay"),str(taps/"ns_output.f32le"),str(taps/"agc_output.f32le"),
            str(folder/"control.bin"),str(folder/"baseline.f32le"),str(folder/"candidate.f32le"),
            str(folder/"trace.bin"),str(folder/"candidate-gain.f32le"),case["profile"],str(case["frames"])]

def run(input_root,output,start):
    need(output==EXECUTION_ROOT and input_root==INPUT_ROOT,"D6_FROZEN_EXECUTION_ROOT")
    prior,parent,lock=original(input_root,start);verify_build(input_root,output,start);phase_pass(output,"build")
    (output/"cases").mkdir()
    for entry in lock["cases"]:
        case=entry["catalog"];folder=output/"cases"/case["key"];folder.mkdir(parents=True)
        taps=parent/"cases"/case["key"]/"taps"
        for name,expected in entry["parent_taps"].items():
            need(descriptor(taps/name)==expected,"D6_INPUT_CHANGED")
        (folder/"control.bin").write_bytes(d2.control_bytes(taps/"control.csv",case))
        command(case_argv(case),folder/"execution.log",start)
    dump(output/"run-index.json",{"experiment":EXPERIMENT,"completed":[e["catalog"]["key"] for e in lock["cases"]],
                                 "expected":60})

def cap_gain(value,peak,limit,allow):
    gate=int(not allow and value>1.0)
    if gate:value=1.0
    peak_active=int(d2.f32(peak*value)>limit and peak>d2.f32(1e-6))
    if peak_active:value=d2.f32(limit/peak)
    return value,gate,peak_active

def observation(signal,before,allow,target,limit,previous,initialized):
    need(len(signal)==160 and allow in (0,1) and initialized in (0,1) and
         all(math.isfinite(x) for x in (*signal,before,target,limit,previous)),"D6_NONFINITE_OR_CONTROL")
    values,flags=d2.gain_observation(signal,before,allow,target,limit)
    G=values["applied_gain"];peak=values["input_peak"]
    need(d2.same_float(cap_gain(G,peak,limit,allow)[0],G),"D6_END_CAP_NOT_IDEMPOTENT")
    S=cap_gain(previous,peak,limit,allow)[0] if initialized else G
    delta=d2.f32(G-S)
    coefficients=[];products=[];unity=0;peak_caps=0
    for i in range(160):
        weight=d2.f32(float(i+1)/160.0)
        product=d2.f32(delta*weight)
        raw=G if i==159 else d2.f32(S+product)
        coefficient,gate,limited=cap_gain(raw,peak,limit,allow)
        coefficients.append(coefficient)
        products.append(d2.f32(signal[i]*coefficient))
        unity+=gate;peak_caps+=limited
    baseline_products=[d2.f32(x*G) for x in signal]
    b={**values,**flags,"final_sample_clamp_count":sum(x < -limit or x > limit for x in baseline_products)}
    c={**values,**flags,"start_gain":S,"end_gain":G,
       "previous_coefficient":previous,"initialized_before":initialized,
       "first_coefficient":coefficients[0],"last_coefficient":coefficients[-1],
       "minimum_coefficient":min(coefficients),"maximum_coefficient":max(coefficients),
       "coefficient_unity_caps":unity,"coefficient_peak_caps":peak_caps,
       "final_sample_clamp_count":sum(x < -limit or x > limit for x in products)}
    # Branchwise clamp preserves the original signed-zero semantics.
    pcm=lambda values:d2.float_bytes(-limit if x < -limit else limit if x > limit else x for x in values)
    return b,pcm(baseline_products),c,d2.float_bytes(coefficients),pcm(products)

def audit_case(entry,old_case,prior,parent,output,start):
    case=entry["catalog"];folder=output/"cases"/case["key"];taps=parent/"cases"/case["key"]/"taps"
    check_command(folder/"execution-command.json",case_argv(case))
    for name,expected in entry["parent_taps"].items():
        need(descriptor(taps/name)==expected,"D6_INPUT_CHANGED")
    controls=d2.control_bytes(taps/"control.csv",case)
    need((folder/"control.bin").read_bytes()==controls,"D6_CONTROLS_CHANGED")
    raw=(taps/"ns_output.f32le").read_bytes()
    samples=struct.unpack("<"+str(case["samples"])+"f",raw)
    base=(folder/"baseline.f32le").read_bytes();candidate=(folder/"candidate.f32le").read_bytes()
    actual_coefficients=(folder/"candidate-gain.f32le").read_bytes()
    need(base==(taps/"agc_output.f32le").read_bytes(),"D6_BASELINE_NOT_ORIGINAL")
    need(len(candidate)==len(base) and len(actual_coefficients)==len(base),"D6_CANDIDATE_SIZE")
    trace=(folder/"trace.bin").read_bytes()
    need(len(trace)==case["frames"]*84,"D6_TRACE_SIZE")
    reader=csv.DictReader(io.StringIO((prior/"cases"/case["key"]/"views/gain.csv").read_text()))
    need(reader.fieldnames==d2.TRACE_FIELDS,"D6_ORIGINAL_TRACE_SCHEMA")
    rows=list(reader);need(len(rows)==case["frames"],"D6_ORIGINAL_TRACE_SIZE")
    counts={"frames":case["frames"],"samples":case["samples"],"resets":0,"zero_frames":0,
            "neutral_frames":0,"warm_start_frames":0,"changed_output_frames":0,
            "changed_state_frames":0,"baseline_target_caps":0,"baseline_output_caps":0,
            "baseline_peak_caps":0,"candidate_coefficient_unity_caps":0,
            "candidate_coefficient_peak_caps":0,"baseline_clamped_samples":0,"candidate_clamped_samples":0,
            "rising_ramp_frames":0,"falling_ramp_frames":0}
    previous=0.0;previous_original=None;audit=[];first_frame=None
    for frame,(state,ctl,row) in enumerate(zip(struct.iter_unpack("<12ffIfIffIII",trace),
                                             struct.iter_unpack("<IIff",controls),rows)):
        allow,reset,before,after=ctl
        need(tuple(state[18:20])==(allow,reset),"D6_TRACE_CONTROLS")
        signal=samples[frame*160:(frame+1)*160]
        need(all(math.isfinite(x) for x in signal) and
             all(math.isfinite(state[i]) for i in (*range(13),14,16,17)),"D6_NONFINITE")
        zero=all(x==0.0 for x in signal);need(state[20]==int(zero),"D6_ZERO_FLAG")
        need(int(row["frame"])==frame and int(row["allow"])==allow and int(row["reset"])==reset,
             "D6_ORIGINAL_ROW_ID")
        target=d2.f32(float(row["target_linear"]));limit=d2.f32(float(row["limiter_linear"]))
        row_before=d2.f32(float(row["state_gain_before"]));row_after=d2.f32(float(row["state_gain_after"]))
        need(d2.same_float(row_before,before) and d2.same_float(row_after,after),"D6_ORIGINAL_STATE_AUTHORITY")
        need(struct.pack("<6f",*state[:6])==struct.pack("<6f",row_before,target,limit,row_after,target,limit),
             "D6_BASELINE_FULL_STATE")
        need(struct.pack("<6f",*state[6:12])==struct.pack("<6f",*state[:6]),"D6_CANDIDATE_STATE_NOT_ORIGINAL")
        warm=frame==0 or bool(reset)
        expected_before=(1.0,target,limit) if warm else previous_original
        need(struct.pack("<3f",*state[:3])==struct.pack("<3f",*expected_before),"D6_ORIGINAL_STATE_CONTINUITY")
        P=0.0 if warm else previous;initialized=0 if warm else 1
        need(state[13]==initialized and state[15]==1,"D6_EXTRA_INITIALIZED")
        need(d2.same_float(state[12],P),"D6_EXTRA_PREVIOUS")
        b,bpcm,c,coefficients,cpcm=observation(signal,before,allow,target,limit,P,initialized)
        for key in ("input_rms","input_peak","target_gain_raw","target_gain_bounded","target_gain",
                    "alpha","expected_state_gain_after","gate_cap_gain","applied_gain"):
            need(d2.same_float(b[key],d2.f32(float(row[key]))),"D6_BASELINE_AUDIT_NOT_ORIGINAL")
        for key in (*d2.CAP_FIELDS,"final_sample_clamp_count"):
            need(b[key]==int(row[key]),"D6_BASELINE_AUDIT_NOT_ORIGINAL")
        need(d2.same_float(state[16],c["start_gain"]),"D6_START_GAIN")
        need(d2.same_float(state[17],c["end_gain"]),"D6_END_GAIN")
        actual=actual_coefficients[frame*640:(frame+1)*640]
        need(actual[-4:]==d2.bits(c["end_gain"]),"D6_COEFFICIENT_ENDPOINT")
        need(actual==coefficients,"D6_COEFFICIENT_FORMULA")
        need(d2.same_float(state[14],c["last_coefficient"]),"D6_EXTRA_PREVIOUS")
        need(allow or c["maximum_coefficient"]<=1.0,"D6_OUTPUT_UNITY_GATE")
        need(base[frame*640:(frame+1)*640]==bpcm,"D6_BASELINE_OUTPUT_FORMULA")
        need(candidate[frame*640:(frame+1)*640]==cpcm,"D6_CANDIDATE_OUTPUT_FORMULA")
        need(all(abs(x)<=limit for x in struct.unpack("<160f",cpcm)),"D6_SAMPLE_CLAMP_BOUND")
        neutral=d2.same_float(c["start_gain"],c["end_gain"])
        if neutral:
            need(bpcm==cpcm and coefficients==d2.bits(c["end_gain"])*160,"D6_NEUTRAL_FRAME_CHANGED")
        if warm:need(neutral,"D6_WARM_START_CHANGED")
        pcm_changed=bpcm!=cpcm
        counts["resets"]+=reset;counts["zero_frames"]+=zero;counts["neutral_frames"]+=neutral
        counts["warm_start_frames"]+=warm;counts["changed_output_frames"]+=pcm_changed
        counts["rising_ramp_frames"]+=c["start_gain"]<c["end_gain"]
        counts["falling_ramp_frames"]+=c["start_gain"]>c["end_gain"]
        if pcm_changed and first_frame is None:first_frame=frame
        for dst,src in (("target_caps","target_gate_cap_active"),("output_caps","output_gate_cap_active"),
                        ("peak_caps","peak_cap_active"),("clamped_samples","final_sample_clamp_count")):
            counts["baseline_"+dst]+=b[src]
        counts["candidate_coefficient_unity_caps"]+=c["coefficient_unity_caps"]
        counts["candidate_coefficient_peak_caps"]+=c["coefficient_peak_caps"]
        counts["candidate_clamped_samples"]+=c["final_sample_clamp_count"]
        audit.append({"frame":frame,"allow":allow,"reset":reset,"digital_zero":zero,
                      "warm_start":warm,"neutral":neutral,"baseline":b,"candidate":c,
                      "previous_actual_endpoint":None if warm else P,
                      "boundary_coefficient_step":None if warm else d2.f32(c["first_coefficient"]-P)})
        previous=c["last_coefficient"];previous_original=state[3:6]
        if frame%100==0:remaining(start,300)
    reference=None;reason="no_clean_near_reference"
    if entry["clean_near"] is not None:
        path=d2.safe(parent/"originals/A",case["inputs"]["clean_near"])
        need(descriptor(path)==entry["clean_near"],"D6_REFERENCE_CHANGED")
        reference=[x/32768.0 for x in d2.d1.samples(path,"h",case["samples"])]
    if case["group"]=="C":reason="C_has_no_admitted_clean_near_reference"
    stages={name:d2.d1.measure_lane(list(struct.unpack("<"+str(case["samples"])+"f",value)),
                 160,case["samples"],reference,reason,True)
            for name,value in (("baseline",base),("candidate",candidate))}
    need(old_case["key"]==case["key"] and stages["baseline"]==old_case["stages"]["replay_final"],
         "D6_ORIGINAL_ENDPOINT_SCORE")
    for name in ("baseline","candidate"):
        stage=stages[name]
        for span in (stage["common"],*stage["one_second_windows"],stage["native_whole_buffer_energy"]):
            need(all(math.isfinite(span[k]) for k in ("rms_dbfs","peak")),"D6_NONFINITE_SCORE")
            if "near_si_sdr_db" in span and span["near_si_sdr_db"] is not None:
                need(math.isfinite(span["near_si_sdr_db"]),"D6_NONFINITE_SCORE")
    for left,right in zip((stages["baseline"]["common"],*stages["baseline"]["one_second_windows"]),
                          (stages["candidate"]["common"],*stages["candidate"]["one_second_windows"])):
        need((left["near_si_sdr_db"] is None)==(right["near_si_sdr_db"] is None) and
             left["near_si_sdr_null_reason"]==right["near_si_sdr_null_reason"],"D6_NULL_IDENTITY_CHANGED")
    delta=d2.d1.stage_delta(stages,"baseline","candidate","output_only_intraframe_linear_gain_ramp")
    changed,first=d2.differences(base,candidate)
    return {"key":case["key"],"group":case["group"],"profile":case["profile"],"scenario":case["scenario"],
            "counts":counts,"changed_samples":changed,"first_difference":first,
            "first_changed_output_frame":first_frame,"max_state_gain_delta":0.0,
            "baseline_original_state_and_output_exact":True,"candidate_original_state_exact":True,
            "continuous_candidate_arithmetic_exact":True,"actual_coefficients_exact":True,
            "audit_origin":AUDIT_ORIGIN,"frame_audit":audit,"stages":stages,"delta":delta,
            "files":{name:descriptor(folder/name) for name in sorted(CASE_FILES)}}

def development_screen(cases):
    common=[];windows=[];positive=[];far=[];clamps=[]
    for case in cases:
        key=case["key"];delta=case["delta"]
        value=delta["common"]["near_si_sdr_change_db"]
        if value is not None:
            common.append({"key":key,"delta":value,"pass":value>=0.0})
            if case["scenario"] in ("doubletalk-nominal","doubletalk-weak") and value>0.0:
                positive.append(key)
        for index,span in enumerate(delta["one_second_windows"]):
            value=span["near_si_sdr_change_db"]
            if value is not None:
                windows.append({"key":key,"window":index,"delta":value,"pass":value>=0.0})
        left,right=case["stages"]["baseline"],case["stages"]["candidate"]
        if case["scenario"] in ("far-only","path-change","render-gap"):
            spans=[("common",left["common"],right["common"]),
                   ("native",left["native_whole_buffer_energy"],right["native_whole_buffer_energy"])]
            spans += [("window-"+str(i),a,b) for i,(a,b) in
                      enumerate(zip(left["one_second_windows"],right["one_second_windows"]))]
            for label,a,b in spans:
                far.append({"key":key,"span":label,"rms_dbfs_baseline":a["rms_dbfs"],
                            "rms_dbfs_candidate":b["rms_dbfs"],"peak_baseline":a["peak"],
                            "peak_candidate":b["peak"],
                            "pass":b["rms_dbfs"]<=a["rms_dbfs"] and b["peak"]<=a["peak"]})
        b=case["counts"]["baseline_clamped_samples"];c=case["counts"]["candidate_clamped_samples"]
        clamps.append({"key":key,"baseline":b,"candidate":c,"pass":c<=b})
    need(len(common)==32 and len({x["key"] for x in far})==24 and len(clamps)==60,
         "D6_SCREEN_MATRIX")
    predicates={"all32_common_nonnegative":all(x["pass"] for x in common),
                "all_scorable_windows_nonnegative":all(x["pass"] for x in windows),
                "doubletalk_common_strict_positive":len(positive)>=1,
                "far_related_level_and_peak_nonincrease":all(x["pass"] for x in far),
                "per_case_clamp_nonincrease":all(x["pass"] for x in clamps)}
    passed=all(predicates.values())
    return {"status":"DEVELOPMENT_SCREEN_PASS_NO_PROMOTION" if passed else "NO_ADVANCE",
            "passed":passed,"predicates":predicates,"common":common,"windows":windows,
            "positive_doubletalk_common_keys":positive,"far_related_spans":far,"clamp_cases":clamps,
            "comparison":"canonical full precision, no epsilon or rounded decision",
            "rms_floor":1e-12,"strict_positive_is_not_material_improvement":True,
            "automatic_followup_execution":False,"promotion_allowed":False}

def analyze(input_root,output,start,saved=None):
    prior,parent,lock=original(input_root,start)
    b=verify_build(input_root,output,start)
    phase_pass(output,"build");phase_pass(output,"run")
    names={"source/"+name for name in b["source_files"]}|set(COPIES)|BUILD_FILES|{"run-index.json"}
    names|={name for name in OPTIONAL_FILES if (output/name).exists()}
    names|={"cases/"+entry["catalog"]["key"]+"/"+name for entry in lock["cases"] for name in CASE_FILES}
    closure(output,names,"D6_OUTPUT_CLOSURE")
    expected_keys=[entry["catalog"]["key"] for entry in lock["cases"]]
    need(d2.read_json(output/"run-index.json")=={"experiment":EXPERIMENT,"completed":expected_keys,"expected":60},
         "D6_RUN_MATRIX_CHANGED")
    if saved is not None:
        need(saved["source"]==b["source"],"D6_REPORT_SOURCE_CHANGED")
        need([c["key"] for c in saved["cases"]]==expected_keys,"D6_REPORT_CASE_SET")
    old=d2.read_json(prior/"report.json")
    need([c["key"] for c in old["cases"]]==expected_keys,"D6_ORIGINAL_CASE_SET")
    cases=[];totals={};windows=0;scored=0
    for index,(entry,old_case) in enumerate(zip(lock["cases"],old["cases"])):
        case=audit_case(entry,old_case,prior,parent,output,start)
        if saved is not None:
            need(case==saved["cases"][index],"D6_READBACK_CASE_DIFFERS")
        cases.append(case)
        for key,value in case["counts"].items():totals[key]=totals.get(key,0)+value
        windows+=len(case["stages"]["baseline"]["one_second_windows"])
        scored+=case["stages"]["baseline"]["common"]["near_si_sdr_db"] is not None
        remaining(start,300)
    need((len(cases),windows,totals["frames"],totals["samples"],totals["resets"],scored)==
         (60,362,35916,5746560,8,32),"D6_MATRIX_TOTALS")
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
    screen=development_screen(cases)
    if saved is not None:
        need(saved["development_screen"]["status"]==screen["status"] and saved["status"]==screen["status"],"D6_SCREEN_DECISION")
        need(saved["development_screen"]==screen,"D6_SCREEN_PREDICATES")
    report={"experiment":EXPERIMENT,"status":screen["status"],"measurement_valid":True,"development_screen":screen,
            "freeze":FREEZE,"source":b["source"],"original_source":OLD,"input_artifact":frozen()["artifact"],
            "case_count":60,"window_count":windows,"scored_cases":scored,"null_cases":60-scored,
            "totals":totals,"cases":cases,"aggregates":groups,"audit_origin":AUDIT_ORIGIN,
            "effect":"output-only intraframe linear gain ramp with original state trajectory unchanged",
            "data_role":"disclosed-regression","independent_observations":False,
            "fresh_baseline_matches_original_D2":True,"promotion_allowed":False,"models_executed":False,
            "physical_device_executed":False,
            "limitations":["fixed original inputs/gates, not feedback-integrated Activity",
                           "not integrated 2.3.64 pipeline, listening, ASR/KWS or physical-target evidence",
                           "real English recording with synthetic propagation; one Chinese recording; no independent validation"],
            "input_bindings":{name:descriptor(output/name) for name in COPIES}}
    if saved is not None:need(report==saved,"D6_READBACK_REPORT_DIFFERS")
    return report

def verify_report(input_root,output,start):
    phase_pass(output,"analysis")
    if (output/"verify-phase.json").exists():phase_pass(output,"verify")
    saved=d2.read_json(output/"report.json")
    if (output/"readback.json").exists():
        need(d2.read_json(output/"readback.json")==
             {"status":"PASS","DSP_executed":False,"models_executed":False,
              "report":descriptor(output/"report.json")},"D6_READBACK_RECEIPT_CHANGED")
    return analyze(input_root,output,start,saved)

def summary(report):
    return {**{key:report[key] for key in ("experiment","status","case_count","window_count","scored_cases",
                                      "null_cases","totals","aggregates","promotion_allowed","measurement_valid")},
            "development_screen_predicates":report["development_screen"]["predicates"]}

def no_symlink_path(path):
    return not any(p.is_symlink() for p in (path,*path.parents))

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase",choices=("build","run","analysis","verify"))
    parser.add_argument("--input",required=True,type=Path)
    parser.add_argument("--output",required=True,type=Path)
    args=parser.parse_args();start=time.monotonic()
    output=args.output.absolute();input_root=args.input.absolute();can_write=False
    receipt={"phase":args.phase,"status":"FAIL","measurement_status":"MEASUREMENT_INVALID","budget_seconds":300}
    marker=output/(args.phase+"-phase.json")
    try:
        if args.phase=="build":
            need(not output.exists() and no_symlink_path(output),"D6_FRESH_OUTPUT_REQUIRED")
            need(output==EXECUTION_ROOT and input_root==INPUT_ROOT,"D6_FROZEN_EXECUTION_ROOT")
            output.mkdir(parents=True);can_write=True
            build(input_root,output,start)
        else:
            need(output.is_dir() and no_symlink_path(output) and
                 not marker.exists() and not marker.is_symlink(),"D6_NEW_PHASE_RECEIPT_REQUIRED")
            extras={"run":("cases","run-index.json"),"analysis":("report.json",),
                    "verify":("readback.json",)}[args.phase]
            need(all(not (output/n).exists() and not (output/n).is_symlink() for n in extras),
                 "D6_NEW_PHASE_OUTPUT_REQUIRED")
            can_write=True
            if args.phase=="run":run(input_root,output,start)
            else:
                report=analyze(input_root,output,start) if args.phase=="analysis" else verify_report(input_root,output,start)
                if args.phase=="analysis":dump(output/"report.json",report)
                else:dump(output/"readback.json",{"status":"PASS","DSP_executed":False,"models_executed":False,
                                                  "report":descriptor(output/"report.json")})
                print(json.dumps(summary(report),sort_keys=True))
        remaining(start,300);receipt["status"]="PASS";receipt["measurement_status"]="PHASE_VALID"
    except Exception as error:
        receipt.update(reason=str(error),error_type=type(error).__name__)
        raise
    finally:
        if can_write:
            receipt["elapsed_seconds"]=time.monotonic()-start;dump(marker,receipt)
            if time.monotonic()-start>300:
                receipt.update(status="FAIL",measurement_status="MEASUREMENT_INVALID",reason="D6_FINAL_WRITE_BUDGET_EXCEEDED",
                               elapsed_seconds=time.monotonic()-start)
                # Only this invocation's newly-created receipt may record its final-write failure.
                marker.write_text(json.dumps(receipt,sort_keys=True)+"\n")
                raise ValueError(receipt["reason"])

if __name__=="__main__":
    main()
