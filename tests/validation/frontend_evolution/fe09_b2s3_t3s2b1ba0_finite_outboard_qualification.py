#!/usr/bin/env python3
"""#803: finite nonrolling APX3/FBS1 original-source outboard, Linux hosted ONLY.

Independent original protected-main SHA pins; actual Native/ASan+UBSan/
ARM32-QEMU/TSan test ELFs twice each. Strict 4-member exact-run receipt,
same-run upload/readback, external ZIP+inner hash confirmation required.
No source deletion, hardware power-loss claim or public SDK promotion.
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

import fe09_b2s3_t3s2b1bf0_seq17_qualification as f0

ROOT=f0.ROOT
HERE=f0.HERE
BASE="899ea11b50d58ee36837c81b30a358ad32daabd6"
DECISION="FE09_B1B_A0_ORIGINAL_SEQ17_PLUS_FINITE_NONROLLING_OUTBOARD_HOSTED_ONLY"
FAILURE="FE09_B1B_A0_FINITE_NOT_ADMITTED"
MARKER="FE09_B1B_A0_FINITE_ORIGINAL_SOURCE_FOUR_ISA_READBACK_PASS\n"
TARGETS=("native","sanitized","arm","tsan")
MEMBERS=("SHA256SUMS","receipt.json","collect.log","verify.log")
SOURCE_C=HERE/"fe09_b2s3_t3s2b1ba0_finite_outboard.c"
SOURCE_H=HERE/"fe09_b2s3_t3s2b1ba0_finite_outboard.h"
TEST=HERE/"fe09_b2s3_t3s2b1ba0_finite_outboard_test.c"
DOC=HERE/"FE09_T3S2B1B_A0_FINITE_OUTBOARD.md"
OWN=(SOURCE_C,SOURCE_H,TEST,Path(__file__).resolve(),DOC)
FROZEN=tuple(dict.fromkeys((*f0.FROZEN,*f0.OWN)))
SOURCES=(*f0.SOURCES[:-1],SOURCE_C,TEST)
FALSE=("real_rolling_retention_qualified","original_source_deleted",
       "physical_powerloss_qualified","ssc305_hardware_qualified",
       "whole_device_memory_qualified","public_sdk_installed")
TRUE=("global_17_to_32_continuity_verified",)

class NotAdmitted(ValueError):
    pass

def need(ok:object,code:str)->None:
    if not ok:raise NotAdmitted(code)

def digest(path:Path)->str:
    need(path.is_file() and not path.is_symlink() and
         0<path.stat().st_size<16*1024*1024,
         "MISSING_OR_OVERSIZED_"+path.name)
    return hashlib.sha256(path.read_bytes()).hexdigest()

def pins()->dict[str,str]:
    need(f0.BASE=="4192847eebb0196fe11364ad234fb3b5519364e8",
         "FROZEN_F0_PREDECESSOR_SHA_DRIFT")
    f0.pins()
    answer={}
    for path in FROZEN:
        relative=path.relative_to(ROOT).as_posix()
        data=subprocess.check_output(
            ["git","-c","safe.directory="+str(ROOT),
             "show",BASE+":"+relative],cwd=ROOT,timeout=30)
        need(0<len(data)<16*1024*1024 and
             hashlib.sha256(data).hexdigest()==digest(path),
             "FROZEN_ORIGINAL_SOURCE_CHANGED_"+relative)
        answer[relative]=hashlib.sha256(data).hexdigest()
    return answer

def verify_result(obj:dict)->None:
    expected={"decision","source_role","profiles",
              "actual_original_apx3_frames",
              "actually_acked_original_frames",
              "bounded_original_source_files",
              "capacity_plus_one_refused",
              "negative_checks","restart_verified",
              "host_faults_rejected","original_source_disk_bytes",*TRUE,*FALSE}
    need(type(obj) is dict and set(obj)==expected and
         obj["decision"]==DECISION and
         obj["source_role"]=="first-party-synthetic" and
         all(obj[k] is True for k in TRUE) and
         all(obj[k] is False for k in FALSE) and
         type(obj["profiles"]) is int and obj["profiles"]==48 and
         type(obj["actual_original_apx3_frames"]) is int and
         obj["actual_original_apx3_frames"]==1536 and
         type(obj["actually_acked_original_frames"]) is int and
         obj["actually_acked_original_frames"]==1536 and
         type(obj["bounded_original_source_files"]) is int and
         obj["bounded_original_source_files"]==1536 and
         type(obj["capacity_plus_one_refused"]) is int and
         obj["capacity_plus_one_refused"]==48 and
         type(obj["negative_checks"]) is int and
         obj["negative_checks"]>=216 and
         type(obj["restart_verified"]) is int and
         obj["restart_verified"]>=96 and
         type(obj["host_faults_rejected"]) is int and
         obj["host_faults_rejected"]==8 and
         type(obj["original_source_disk_bytes"]) is int and
         2000000<obj["original_source_disk_bytes"]<12000000,
         "INCOMPLETE_OR_FALSE_ORIGINAL_FINITE_A0_HOSTED_FLOOR")

def identity(sha:str)->dict:
    need(type(sha) is str and re.fullmatch(r"[0-9a-f]{40}",sha),
         "NOT_EXACT_GIT_SOURCE_SHA")
    return {
        "schema_version":1,
        "stage":"FE09_T3_S2_B1B_A0_NONROLLING_FINITE_SOURCE",
        "preregistration":"https://github.com/jiying2007/audio-pipeline/issues/803",
        "source_commit":sha,
        "protected_predecessor_main":BASE,
        "protected_predecessor_verify":39245811212,
        "protected_predecessor_release":39250589348,
        "source_role":"first-party-synthetic",
        "immutable_predecessor_sha256":pins(),
        "own_source_sha256":{
            p.relative_to(ROOT).as_posix():digest(p) for p in OWN},
        "original_S2_APX3_codec_rewritten":False,
        "original_S1_S2A_B0_B1a_F0_source_modified":False,
        "original_source_deleted":False,
        "rolling_root_checkpoint_or_gc_implemented":False,
        "physical_NAND_UBIFS_powerloss_qualified":False,
        "entire_ssc305_192k_memory_qualified":False,
        "public_sdk_installed":False,
    }

def verify_output(root:Path,sha:str)->None:
    caps={"SHA256SUMS":512,"receipt.json":300000,
          "collect.log":5*1024*1024,"verify.log":256}
    need(root.is_dir() and not root.is_symlink() and
         {p.name for p in root.iterdir()}==set(MEMBERS),
         "MISSING_OR_EXTRA_ORIGINAL_A0_EVIDENCE")
    for name in MEMBERS:
        file=root/name
        need(file.is_file() and not file.is_symlink() and
             0<file.stat().st_size<=caps[name],"BAD_MEMBER_"+name)
    want="".join(f"{digest(root/n)}  {n}\n" for n in
                 ("receipt.json","collect.log","verify.log"))
    need((root/"SHA256SUMS").read_text("ascii")==want,
         "A0_SHA256SUMS_MISMATCH")
    receipt=f0.b0.s2a.s1.s0.tools.strict_json(
        (root/"receipt.json").read_text("utf-8"))
    for key,value in identity(sha).items():
        need(receipt.get(key)==value,"A0_SOURCE_PIN_DRIFT_"+key)
    need(receipt.get("decision")==DECISION and
         receipt.get("actual_compiled_targets_complete") is True and
         receipt.get("target_order")==list(TARGETS),
         "FOUR_REAL_A0_TARGETS_REQUIRED")
    targets=receipt.get("target_results")
    versions=receipt.get("compiler_versions")
    binaries=receipt.get("binary_sha256")
    need(type(targets) is dict and set(targets)==set(TARGETS) and
         type(versions) is dict and set(versions)==set(TARGETS) and
         type(binaries) is dict and set(binaries)==set(TARGETS) and
         all(type(x) is str and len(x)>3 for x in versions.values()) and
         all(type(x) is str and re.fullmatch("[0-9a-f]{64}",x)
             for x in binaries.values()),
         "UNPROVEN_A0_COMPILER_OR_BINARY")
    for target in TARGETS:
        verify_result(targets[target])
        need(targets[target]==targets["native"],
             "A0_CROSS_ISA_RESULT_MISMATCH_"+target)
    need((root/"verify.log").read_text("ascii")==MARKER,
         "A0_READBACK_MARKER_MISSING")

def self_test()->None:
    pins()
    good=dict(decision=DECISION,source_role="first-party-synthetic",
              profiles=48,actual_original_apx3_frames=1536,
              actually_acked_original_frames=1536,
              bounded_original_source_files=1536,
              global_17_to_32_continuity_verified=True,
              capacity_plus_one_refused=48,negative_checks=259,
              restart_verified=144,host_faults_rejected=8,
              original_source_disk_bytes=4000000,
              **{key:False for key in FALSE})
    verify_result(good)
    mutants=[("decision",FAILURE),("source_role","real-array"),
             ("profiles",47),("actual_original_apx3_frames",816),
             ("actually_acked_original_frames",1535),
             ("bounded_original_source_files",1535),
             ("global_17_to_32_continuity_verified",False),
             ("capacity_plus_one_refused",47),
             ("negative_checks",215),("restart_verified",95),
             ("host_faults_rejected",7),
             ("original_source_disk_bytes",0),
             *[(key,True) for key in FALSE]]
    for key,value in mutants:
        changed=dict(good);changed[key]=value
        try:verify_result(changed)
        except NotAdmitted:pass
        else:raise NotAdmitted("FALSE_A0_AUTHORITY_"+key)
    print("FE09_A0_NONROLLING_FOUR_TARGET_CONTRACT_SELF_TEST_PASS",len(mutants))

def collect(output:Path,sha:str)->None:
    need(not output.exists() and not output.is_symlink(),
         "REFUSE_EXISTING_A0_EVIDENCE_ROOT")
    need(f0.b0.s2a.s1.s0.tools.source_head()==sha,
         "EXACT_GIT_SOURCE_HEAD_REQUIRED")
    receipt=identity(sha)
    receipt.update(decision=FAILURE,actual_compiled_targets_complete=False)
    logs=[]
    output.mkdir(parents=True)
    try:
        results={};versions={};binaries={}
        with tempfile.TemporaryDirectory(prefix="fe09-t3s2b1ba0-") as tmp:
            wd=Path(tmp)
            cfg=wd/"include/audio_pipeline/audio_pipeline_build.h"
            cfg.parent.mkdir(parents=True)
            cfg.write_text("#ifndef AUDIO_PIPELINE_AUDIO_PIPELINE_BUILD_H\n"
                "#define AUDIO_PIPELINE_AUDIO_PIPELINE_BUILD_H\n"
                "#define AP_BUILD_RESAMPLER_BANDLIMITED 1\n#endif\n",
                encoding="ascii")
            for target in TARGETS:
                compiler="arm-linux-gnueabihf-gcc" if target=="arm" else "cc"
                need(shutil.which(compiler) is not None,
                     "ACTUAL_COMPILER_MISSING_"+target)
                versions[target]=f0.b0.s2a.s1.s0.tools.run(
                    [compiler,"--version"],logs).splitlines()[0]
                flags=[compiler,"-std=c11","-Wall","-Wextra","-Werror",
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
                objs=[]
                for i,source in enumerate(SOURCES):
                    obj=wd/f"{target}-{i}.o"
                    exceptions=(
                        f0.b0.s2a.s1.s0.c0.b1.b1.b0.b1.SOURCE_C,
                        f0.b0.s2a.s1.s0.c0.b1.b1.b0.b1.ARRAY_C)
                    warnings=[] if source in exceptions else [
                        "-Wconversion","-Wshadow","-Wpedantic"]
                    f0.b0.s2a.s1.s0.tools.run(flags+warnings+
                        ["-c",str(source),"-o",str(obj)],logs,timeout=120)
                    objs.append(str(obj))
                exe=wd/(target+".elf")
                link=[compiler,*objs,"-pthread","-lm","-o",str(exe)]
                if target=="sanitized":link.append("-fsanitize=address,undefined")
                if target=="tsan":link.append("-fsanitize=thread")
                if target=="arm":
                    link+=["-march=armv7-a","-mfpu=neon-vfpv4",
                           "-mfloat-abi=hard"]
                f0.b0.s2a.s1.s0.tools.run(link,logs,timeout=120)
                binaries[target]=digest(exe)
                cmd=[str(exe)]
                if target=="arm":
                    need(shutil.which("qemu-arm") is not None and
                         Path("/usr/arm-linux-gnueabihf").is_dir(),
                         "ACTUAL_ARM32_QEMU_MISSING")
                    cmd=["qemu-arm","-L","/usr/arm-linux-gnueabihf",
                         str(exe)]
                env=dict(os.environ)
                if target=="sanitized":
                    env.update({"ASAN_OPTIONS":"detect_leaks=0:halt_on_error=1",
                                "UBSAN_OPTIONS":"halt_on_error=1"})
                if target=="tsan":
                    env.update({"TSAN_OPTIONS":"halt_on_error=1:exitcode=66"})
                first=f0.b0.s2a.s1.s0.tools.strict_json(
                    f0.b0.s2a.s1.s0.tools.run(cmd,logs,timeout=540,env=env))
                second=f0.b0.s2a.s1.s0.tools.strict_json(
                    f0.b0.s2a.s1.s0.tools.run(cmd,logs,timeout=540,env=env))
                need(first==second,"A0_NONDETERMINISTIC_"+target)
                verify_result(first)
                results[target]=first
        receipt.update(decision=DECISION,
                       actual_compiled_targets_complete=True,
                       target_order=list(TARGETS),
                       target_results=results,
                       compiler_versions=versions,binary_sha256=binaries)
    except Exception as exc:
        receipt.update(decision=FAILURE,
                       actual_compiled_targets_complete=False,
                       failure_type=type(exc).__name__,
                       failure_code=str(exc)[:260])
        import sys
        print("FE09_A0_FAILURE_LOG_BEGIN",file=sys.stderr)
        print("\n".join(logs[-18:])[-7500:],file=sys.stderr)
        print("FE09_A0_FAILURE_LOG_END",file=sys.stderr)
        raise
    finally:
        (output/"receipt.json").write_text(json.dumps(
            receipt,sort_keys=True,separators=(",",":"),allow_nan=False)+"\n",
            encoding="utf-8")
        (output/"collect.log").write_text("\n".join(logs)+"\n",encoding="utf-8")
        (output/"verify.log").write_text(
            MARKER if receipt["decision"]==DECISION else FAILURE+"\n",
            encoding="ascii")
        (output/"SHA256SUMS").write_text("".join(
            f"{digest(output/name)}  {name}\n" for name in
             ("receipt.json","collect.log","verify.log")),
             encoding="ascii")
    verify_output(output,sha)

def main()->None:
    parser=argparse.ArgumentParser(description=__doc__)
    modes=parser.add_mutually_exclusive_group(required=True)
    for mode in ("self-test","collect","verify"):
        modes.add_argument("--"+mode,action="store_true")
    parser.add_argument("--execution-source")
    parser.add_argument("--output",type=Path)
    args=parser.parse_args()
    try:
        if args.self_test:self_test();return
        need(args.output is not None and
             type(args.execution_source) is str and
             re.fullmatch("[0-9a-f]{40}",args.execution_source),
             "OUTPUT_AND_EXACT_SOURCE_REQUIRED")
        need(f0.b0.s2a.s1.s0.tools.source_head()==args.execution_source,
             "GIT_CHECKOUT_SOURCE_CHANGED")
        if args.collect:collect(args.output,args.execution_source)
        else:
            verify_output(args.output,args.execution_source)
            print(MARKER.strip())
    except (NotAdmitted,f0.NotAdmitted,
            f0.b0.NotAdmitted,f0.b0.s2a.NotAdmitted,
            f0.b0.s2a.s1.NotAdmitted,
            f0.b0.s2a.s1.s0.NotAdmitted,
            f0.b0.s2a.s1.s0.tools.GateFailure,
            OSError,subprocess.CalledProcessError,ValueError) as exc:
        raise SystemExit(FAILURE+": "+str(exc)) from None

if __name__=="__main__":
    main()
