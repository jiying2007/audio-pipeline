#!/usr/bin/env python3
"""#797 exact original FBS1 source-anchored outer index, NONINSTALLED only.

Original first-party S2 APX3, original S1 source consumer + actual S2-A
POSIX storage. B0 is an in-memory manifest contract and does NOT GC/roll
files, create a durable index, certify NAND/UBIFS/powercuts or a public SDK.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

import fe09_b2s3_t3s2a_atomic_spool_qualification as s2a

ROOT=s2a.ROOT
HERE=s2a.HERE
BASE="2dba395fd7d86b1e5b395f142fde15fdcd884f99"
DECISION="FE09_T3S2B0_ORIGINAL_FBS1_SOURCE_INDEX_RESEARCH_ONLY"
FAILURE="FE09_T3S2B0_SOURCE_INDEX_NOT_ADMITTED"
MARKER="FE09_T3S2B0_FIRST_PARTY_ORIGINAL_FBS1_ROLLING_INDEX_CONTRACT_VERIFIED\n"
TARGETS=("native","sanitized","arm","tsan")
MEMBERS=("SHA256SUMS","receipt.json","collect.log","verify.log")
C=HERE/"fe09_b2s3_t3s2b0_manifest.c"
H=HERE/"fe09_b2s3_t3s2b0_manifest.h"
TEST=HERE/"fe09_b2s3_t3s2b0_manifest_test.c"
OWN=(C,H,TEST,Path(__file__).resolve())
FROZEN=tuple(dict.fromkeys((*s2a.FROZEN,*s2a.OWN,
              HERE/"FE09_T3S2A_ORIGINAL_ATOMIC_SPOOL.md")))
SOURCES=(*s2a.SOURCES[:-1],C,TEST)
FALSE=("on_disk_manifest_published","rolling_retention_qualified",
       "durable_powerloss_qualified","ssc305_hardware_qualified",
       "whole_device_memory_qualified","public_sdk_installed")

class NotAdmitted(ValueError):
    pass

def need(ok:object,reason:str)->None:
    if not ok:raise NotAdmitted(reason)

def digest(p:Path)->str:
    need(p.is_file() and not p.is_symlink() and
         0<p.stat().st_size<16*1024*1024,"MISSING_OR_OVERSIZED_"+p.name)
    return hashlib.sha256(p.read_bytes()).hexdigest()

def pins()->dict[str,str]:
    need(s2a.BASE=="da4254b7de46b4b5e61a723c9d0ca170d19cd6d0",
         "SOURCE_PARENT_T3S2A_BASE_CHANGED")
    s2a.pins()
    out={}
    for f in FROZEN:
        name=f.relative_to(ROOT).as_posix()
        raw=subprocess.check_output(
            ["git","-c","safe.directory="+str(ROOT),"show",BASE+":"+name],
            cwd=ROOT,timeout=30)
        need(0<len(raw)<16*1024*1024 and
             hashlib.sha256(raw).hexdigest()==digest(f),
             "FROZEN_ORIGINAL_APX3_SOURCE_CHANGED_"+name)
        out[name]=hashlib.sha256(raw).hexdigest()
    return out

def verify_result(obj:dict)->None:
    expected={"decision","source_role","profiles","negative_checks",
              "roundtrip_checks","original_frames",
              "physical_one_two_slots","maximum_rows",
              "original_apx3_codec_reused",*FALSE}
    need(type(obj) is dict and set(obj)==expected,
         "FALSE_OR_EXTRA_INDEX_AUTHORITY")
    need(obj["decision"]==DECISION and
         obj["source_role"]=="first-party-synthetic" and
         all(obj[k] is False for k in FALSE) and
         obj["physical_one_two_slots"] is True and
         obj["original_apx3_codec_reused"] is True and
         type(obj["profiles"]) is int and obj["profiles"]==48 and
         type(obj["negative_checks"]) is int and
         obj["negative_checks"]>=1500 and
         type(obj["roundtrip_checks"]) is int and
         obj["roundtrip_checks"]==97 and
         type(obj["original_frames"]) is int and
         obj["original_frames"]==112 and
         type(obj["maximum_rows"]) is int and
         obj["maximum_rows"]==16,
         "UNOBSERVED_OR_FALSE_INDEX_CAPACITY")

def identity(sha:str)->dict:
    need(type(sha) is str and re.fullmatch("[0-9a-f]{40}",sha),
         "NOT_EXACT_SOURCE_SHA")
    return {
        "schema_version":1,
        "stage":"FE09_T3_S2_B0_NONINSTALLED_ORIGINAL_FBS1_ROLLING_INDEX_CONTRACT",
        "preregistration":"https://github.com/jiying2007/audio-pipeline/issues/797",
        "source_commit":sha,
        "protected_predecessor_main":BASE,
        "protected_predecessor_verify":39132759577,
        "protected_predecessor_release":39136023423,
        "source_role":"first-party-synthetic",
        "immutable_predecessor_sha256":pins(),
        "own_source_sha256":{
            p.relative_to(ROOT).as_posix():digest(p) for p in OWN},
        "prior_original_s2_apx3_rewritten":False,
        "source_bf_or_s1_consumer_changed":False,
        "rolling_prune_implemented":False,
        "powerloss_device_authority":False,
        "whole_process_rss_measured":False,
        "public_sdk_installed":False,
    }

def verify_output(out:Path,sha:str)->None:
    sizes={"SHA256SUMS":512,"receipt.json":300000,
           "collect.log":4*1024*1024,"verify.log":256}
    need(out.is_dir() and not out.is_symlink() and
         {p.name for p in out.iterdir()}==set(MEMBERS),
         "EXACT_ORIGINAL_FOUR_MEMBER_MANIFEST")
    for name in MEMBERS:
        f=out/name
        need(f.is_file() and not f.is_symlink() and
             0<f.stat().st_size<=sizes[name],
             "UNBOUNDED_OR_MISSING_"+name)
    manifest="".join(f"{digest(out/name)}  {name}\n"
        for name in ("receipt.json","collect.log","verify.log"))
    need((out/"SHA256SUMS").read_text("ascii")==manifest,
         "SOURCE_MANIFEST_HASH_MISMATCH")
    receipt=s2a.s1.s0.tools.strict_json((out/"receipt.json").read_text("utf-8"))
    for key,value in identity(sha).items():
        need(receipt.get(key)==value,"SOURCE_SHA_OR_PIN_DRIFT_"+key)
    need(receipt.get("decision")==DECISION and
         receipt.get("actual_compiled_targets_complete") is True and
         receipt.get("target_order")==list(TARGETS),
         "COMPILER_TARGET_EVIDENCE_MISSING")
    targets=receipt.get("target_results")
    versions=receipt.get("compiler_versions")
    binaries=receipt.get("binary_sha256")
    need(type(targets) is dict and set(targets)==set(TARGETS) and
         type(versions) is dict and set(versions)==set(TARGETS) and
         type(binaries) is dict and set(binaries)==set(TARGETS) and
         all(type(x) is str and len(x)>3 for x in versions.values()) and
         all(type(x) is str and re.fullmatch("[0-9a-f]{64}",x)
             for x in binaries.values()),
         "MISSING_ACTUAL_FOUR_ISA_ELF_SHA256")
    for target in TARGETS:
        verify_result(targets[target])
        need(targets[target]==targets["native"],
             "ACTUAL_CROSS_ISA_INDEX_POLICY_DRIFT_"+target)
    need((out/"verify.log").read_text("ascii")==MARKER,
         "ORIGINAL_SOURCE_READBACK_MARKER_WRONG")

def self_test()->None:
    pins()
    good=dict(decision=DECISION,source_role="first-party-synthetic",
              profiles=48,negative_checks=1900,roundtrip_checks=97,
              original_frames=112,maximum_rows=16,
              physical_one_two_slots=True,original_apx3_codec_reused=True,
              **{k:False for k in FALSE})
    verify_result(good)
    trials=[
        ("profiles",47),("negative_checks",10),("roundtrip_checks",96),
        ("original_frames",111),("maximum_rows",24),
        ("decision",FAILURE),("source_role","device"),
        ("physical_one_two_slots",False),
        ("original_apx3_codec_reused",False),
        *[(x,True) for x in FALSE]
    ]
    for name,value in trials:
        v=dict(good);v[name]=value
        try:verify_result(v)
        except NotAdmitted:pass
        else:raise NotAdmitted("FALSE_INDEX_POLICY_NOT_REJECTED_"+name)
    print("FE09_T3S2B0_SOURCE_FROZEN_POLICY_SELFTEST_PASS",len(trials))

def collect(out:Path,sha:str)->None:
    need(not out.exists() and not out.is_symlink(),
         "REFUSE_ORIGINAL_EVIDENCE_OVERWRITE")
    need(s2a.s1.s0.tools.source_head()==sha,
         "GIT_SOURCE_HEAD_NOT_EXACT_SHA")
    receipt=identity(sha)
    receipt.update(decision=FAILURE,actual_compiled_targets_complete=False)
    logs=[]
    out.mkdir(parents=True)
    try:
        results,versions,binaries={},{},{}
        with tempfile.TemporaryDirectory(prefix="fe09-t3s2b0-") as tmp:
            wd=Path(tmp)
            config=wd/"include/audio_pipeline/audio_pipeline_build.h"
            config.parent.mkdir(parents=True)
            config.write_text("#ifndef AUDIO_PIPELINE_AUDIO_PIPELINE_BUILD_H\n"
                "#define AUDIO_PIPELINE_AUDIO_PIPELINE_BUILD_H\n"
                "#define AP_BUILD_RESAMPLER_BANDLIMITED 1\n#endif\n",
                encoding="ascii")
            for target in TARGETS:
                cc="arm-linux-gnueabihf-gcc" if target=="arm" else "cc"
                need(shutil.which(cc) is not None,
                     "MISSING_COMPILER_"+target)
                versions[target]=s2a.s1.s0.tools.run(
                    [cc,"--version"],logs).splitlines()[0]
                flags=[cc,"-std=c11","-Wall","-Wextra","-Werror",
                       "-O2","-ffp-contract=off","-fno-fast-math",
                       "-pthread","-DAP_BUILD_RESAMPLER_BANDLIMITED=1",
                       "-I"+str(wd/"include"),"-I"+str(ROOT/"src"),
                       "-I"+str(HERE)]
                if target in ("sanitized","tsan"):
                    flags+=["-O1","-g",
                            "-fsanitize=thread" if target=="tsan"
                            else "-fsanitize=address,undefined",
                            "-fno-omit-frame-pointer"]
                if target=="arm":
                    flags+=["-march=armv7-a","-mfpu=neon-vfpv4",
                            "-mfloat-abi=hard"]
                objects=[]
                for ix,source in enumerate(SOURCES):
                    obj=wd/f"{target}-{ix}.o"
                    except_sources=(
                        s2a.s1.s0.c0.b1.b1.b0.b1.SOURCE_C,
                        s2a.s1.s0.c0.b1.b1.b0.b1.ARRAY_C)
                    strict=[] if source in except_sources else [
                        "-Wconversion","-Wshadow","-Wpedantic"]
                    s2a.s1.s0.tools.run(flags+strict+
                        ["-c",str(source),"-o",str(obj)],logs,timeout=120)
                    objects.append(str(obj))
                exe=wd/(target+".elf")
                cmd=[cc,*objects,"-pthread","-lm","-o",str(exe)]
                if target=="sanitized":cmd.append("-fsanitize=address,undefined")
                if target=="tsan":cmd.append("-fsanitize=thread")
                if target=="arm":
                    cmd+=["-march=armv7-a","-mfpu=neon-vfpv4",
                          "-mfloat-abi=hard"]
                s2a.s1.s0.tools.run(cmd,logs,timeout=120)
                binaries[target]=digest(exe)
                command=[str(exe)]
                if target=="arm":
                    need(shutil.which("qemu-arm") is not None and
                         Path("/usr/arm-linux-gnueabihf").is_dir(),
                         "ARM32_QEMU_REQUIRED")
                    command=["qemu-arm","-L",
                             "/usr/arm-linux-gnueabihf",str(exe)]
                env=dict(os.environ)
                if target=="sanitized":
                    env.update({"ASAN_OPTIONS":"detect_leaks=0:halt_on_error=1",
                                "UBSAN_OPTIONS":"halt_on_error=1"})
                if target=="tsan":
                    env.update({"TSAN_OPTIONS":"halt_on_error=1:exitcode=66"})
                first=s2a.s1.s0.tools.strict_json(
                    s2a.s1.s0.tools.run(command,logs,timeout=300,env=env))
                repeat=s2a.s1.s0.tools.strict_json(
                    s2a.s1.s0.tools.run(command,logs,timeout=300,env=env))
                need(first==repeat,"TWO_RUN_INDEX_DRIFT_"+target)
                verify_result(first)
                results[target]=first
        receipt.update(decision=DECISION,
                       actual_compiled_targets_complete=True,
                       target_order=list(TARGETS),
                       target_results=results,
                       compiler_versions=versions,
                       binary_sha256=binaries)
    except Exception as exc:
        receipt.update(decision=FAILURE,
                       actual_compiled_targets_complete=False,
                       failure_type=type(exc).__name__,
                       failure_code=str(exc)[:250])
        import sys
        print("FE09_T3S2B0_FAIL_CLOSED_COMPILER_LOG_BEGIN",file=sys.stderr)
        print("\n".join(logs[-14:])[-6000:],file=sys.stderr)
        print("FE09_T3S2B0_FAIL_CLOSED_COMPILER_LOG_END",file=sys.stderr)
        raise
    finally:
        (out/"receipt.json").write_text(json.dumps(receipt,
            sort_keys=True,separators=(",",":"),allow_nan=False)+"\n",
            encoding="utf-8")
        (out/"collect.log").write_text("\n".join(logs)+"\n",
            encoding="utf-8")
        (out/"verify.log").write_text(
            MARKER if receipt["decision"]==DECISION else FAILURE+"\n",
            encoding="ascii")
        (out/"SHA256SUMS").write_text(
            "".join(f"{digest(out/name)}  {name}\n" for name in
                ("receipt.json","collect.log","verify.log")),
            encoding="ascii")
    verify_output(out,sha)

def main()->None:
    p=argparse.ArgumentParser(description=__doc__)
    m=p.add_mutually_exclusive_group(required=True)
    for mode in ("self-test","collect","verify"):
        m.add_argument("--"+mode,action="store_true")
    p.add_argument("--execution-source")
    p.add_argument("--output",type=Path)
    args=p.parse_args()
    try:
        if args.self_test:self_test();return
        need(args.output is not None and
             type(args.execution_source) is str and
             re.fullmatch("[0-9a-f]{40}",args.execution_source),
             "SOURCE_COMMIT_OR_OUTPUT_MISSING")
        need(s2a.s1.s0.tools.source_head()==args.execution_source,
             "SOURCE_SHA_NOT_CHECKED_OUT_HEAD")
        if args.collect:collect(args.output,args.execution_source)
        else:
            verify_output(args.output,args.execution_source)
            print(MARKER.strip())
    except (NotAdmitted,s2a.NotAdmitted,s2a.s1.NotAdmitted,
            s2a.s1.s0.NotAdmitted,
            s2a.s1.s0.tools.GateFailure,OSError,
            subprocess.CalledProcessError,ValueError) as exc:
        raise SystemExit(FAILURE+": "+str(exc)) from None

if __name__=="__main__":
    main()
