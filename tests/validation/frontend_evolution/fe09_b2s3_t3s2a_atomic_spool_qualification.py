#!/usr/bin/env python3
"""#794: first-party original APX3/FBS1 POSIX transaction, fail-closed host only.

A real compiled C source exact/native/sanitizer/ARM-QEMU/TSan matrix, two
executions each. No source substitution or synthetic software "durability"
claim for actual NAND/UBIFS/SSC305; original parent S1 remains frozen.
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

import fe09_b2s3_t3s1_compact_handoff_qualification as s1

ROOT=s1.ROOT
HERE=s1.HERE
BASE="da4254b7de46b4b5e61a723c9d0ca170d19cd6d0"
DECISION="FE09_T3S2A_ATOMIC_ORIGINAL_SPOOL_RESEARCH_ONLY"
FAILURE="FE09_T3S2A_ORIGINAL_SPOOL_NOT_ADMITTED"
MARKER="FE09_T3S2A_ORIGINAL_APX3_FBS1_POSIX_SPOOL_SOURCE_VERIFIED\n"
TARGETS=("native","sanitized","arm","tsan")
MEMBERS=("SHA256SUMS","receipt.json","collect.log","verify.log")
C=HERE/"fe09_b2s3_t3s2a_atomic_spool.c"
H=HERE/"fe09_b2s3_t3s2a_atomic_spool.h"
TEST=HERE/"fe09_b2s3_t3s2a_atomic_spool_test.c"
OWN=(C,H,TEST,Path(__file__).resolve())
FROZEN=tuple(dict.fromkeys((*s1.FROZEN,*s1.OWN,
                        HERE/"FE09_T3S1_COMPACT_HANDOFF.md")))
SOURCES=(*s1.SOURCES[:-1],C,TEST)
FALSE=("hardware_qualified","durable_powerloss_qualified",
       "rolling_recorder_qualified","complete_ssc305_device_memory_qualified",
       "public_sdk_installed")

class NotAdmitted(ValueError):
    pass

def need(ok: object,why: str)->None:
    if not ok:raise NotAdmitted(why)

def digest(p: Path)->str:
    need(p.is_file() and not p.is_symlink() and
         0<p.stat().st_size<16*1024*1024,"MISSING_OR_OVERSIZED_"+p.name)
    return hashlib.sha256(p.read_bytes()).hexdigest()

def pins()->dict[str,str]:
    need(s1.BASE=="e85a14540f2c49456508387fe3f815a90308c1ba",
         "PREDECESSOR_S1_BASE_CHANGED")
    s1.pins()
    result={}
    for p in FROZEN:
        rel=p.relative_to(ROOT).as_posix()
        source=subprocess.check_output(["git","-c","safe.directory="+str(ROOT),
                "show",BASE+":"+rel],cwd=ROOT,timeout=30)
        need(0<len(source)<16*1024*1024 and
             hashlib.sha256(source).hexdigest()==digest(p),
             "FROZEN_FIRST_PARTY_PREDECESSOR_CHANGED_"+rel)
        result[rel]=hashlib.sha256(source).hexdigest()
    return result

def verify_result(obj: dict)->None:
    need(type(obj) is dict and set(obj)=={
        "decision","source_role","profiles","fault_injections",
        "negative_checks","restart_idempotence","completed_original_frames",
        "max_files",*FALSE},"UNTRUSTED_RESULT_SCHEMA")
    need(obj["decision"]==DECISION and
         obj["source_role"]=="first-party-synthetic" and
         all(obj[k] is False for k in FALSE) and
         type(obj["profiles"]) is int and obj["profiles"]==336 and
         type(obj["fault_injections"]) is int and obj["fault_injections"]==336 and
         type(obj["negative_checks"]) is int and obj["negative_checks"]>=680 and
         type(obj["restart_idempotence"]) is int and
         obj["restart_idempotence"]==672 and
         type(obj["completed_original_frames"]) is int and
         obj["completed_original_frames"]>=672 and
         type(obj["max_files"]) is int and obj["max_files"]==16,
         "FALSE_SPOOL_NEGATIVE_OR_DEVICE_ADMISSION")

def identity(sha:str)->dict:
    need(type(sha) is str and re.fullmatch("[0-9a-f]{40}",sha),
         "NOT_AN_IMMUTABLE_SOURCE_SHA")
    return {
        "schema_version":1,
        "stage":"FE09_S3_T3_S2_A_NONINSTALLED_POSIX_OUTBOARD_ATOMIC_SPOOL",
        "preregistration":"https://github.com/jiying2007/audio-pipeline/issues/794",
        "source_commit":sha,
        "protected_predecessor_main":BASE,
        "protected_predecessor_verify":39098115944,
        "protected_predecessor_release":39100235812,
        "source_role":"first-party-synthetic",
        "immutable_predecessor_sha256":pins(),
        "own_source_sha256":{p.relative_to(ROOT).as_posix():digest(p) for p in OWN},
        "original_s2_serializer_rewritten":False,
        "origin_s1_source_worker_changed":False,
        "durability_device_claim":False,
        "physical_adc_dac_clocks_measured":False,
        "process_rss_measured":False,
        "public_sdk_installed":False,
    }

def verify_output(output:Path,sha:str)->None:
    caps={"SHA256SUMS":512,"receipt.json":300000,
          "collect.log":4*1024*1024,"verify.log":256}
    need(output.is_dir() and not output.is_symlink() and
         {p.name for p in output.iterdir()}==set(MEMBERS),
         "EXACT_FOUR_MEMBER_MANIFEST_REQUIRED")
    for name in MEMBERS:
        p=output/name
        need(p.is_file() and not p.is_symlink() and
             0<p.stat().st_size<=caps[name],
             "MISSING_OR_UNBOUNDED_"+name)
    expected="".join(f"{digest(output/name)}  {name}\n" for name in
                     ("receipt.json","collect.log","verify.log"))
    need((output/"SHA256SUMS").read_text("ascii")==expected,
         "UNBOUND_ARTIFACT_MEMBER_SHA256")
    j=s1.s0.tools.strict_json((output/"receipt.json").read_text("utf-8"))
    for key,value in identity(sha).items():
        need(j.get(key)==value,"EXACT_SOURCE_IDENTITY_"+key)
    need(j.get("decision")==DECISION and
         j.get("actual_compiled_targets_complete") is True and
         j.get("target_order")==list(TARGETS),
         "COMPILER_EXECUTION_INCOMPLETE")
    tests=j.get("target_results")
    binary=j.get("binary_sha256")
    version=j.get("compiler_versions")
    need(type(tests) is dict and set(tests)==set(TARGETS) and
         type(binary) is dict and set(binary)==set(TARGETS) and
         type(version) is dict and set(version)==set(TARGETS) and
         all(type(z) is str and re.fullmatch("[0-9a-f]{64}",z)
             for z in binary.values()) and
         all(type(z) is str and len(z)>3 for z in version.values()),
         "NOT_ALL_ACTUAL_COMPILER_ELFS")
    for target in TARGETS:
        verify_result(tests[target])
        need(tests[target]==tests["native"],
             "CROSS_ISA_OR_SCHEDULER_NEGATIVE_EVIDENCE_DRIFT_"+target)
    need((output/"verify.log").read_text("ascii")==MARKER,
         "NO_SOURCE_STANDALONE_VERIFY_MARKER")

def self_test()->None:
    pins()
    obj=dict(decision=DECISION,source_role="first-party-synthetic",
             profiles=336,fault_injections=336,negative_checks=1020,
             restart_idempotence=672,completed_original_frames=672,
             max_files=16,**{k:False for k in FALSE})
    verify_result(obj)
    failures=0
    for key,val in [("profiles",335),("fault_injections",335),
                    ("negative_checks",679),("restart_idempotence",671),
                    ("completed_original_frames",671),("max_files",17),
                    ("decision",FAILURE),("source_role","hardware"),
                    *[(k,True) for k in FALSE]]:
        bad=dict(obj);bad[key]=val
        try:verify_result(bad)
        except NotAdmitted:failures+=1
        else:raise NotAdmitted("FALSE_SPOOL_QUALIFICATION_"+key)
    need(failures==13,"NEGATIVE_POLICY_SELFTEST_INCOMPLETE")
    print("FE09_T3S2A_SOURCE_PIN_AND_FALSE_DURABILITY_SELFTEST_PASS",failures)

def collect(out:Path,sha:str)->None:
    need(not out.exists() and not out.is_symlink(),
         "EXISTING_ARTIFACT_MUST_NEVER_BE_OVERWRITTEN")
    need(s1.s0.tools.source_head()==sha,"SOURCE_HEAD_MOVED")
    report=identity(sha)
    report.update(decision=FAILURE,actual_compiled_targets_complete=False)
    logs=[]
    out.mkdir(parents=True)
    try:
        targets={};versions={};binary_hashes={}
        with tempfile.TemporaryDirectory(prefix="fe09-t3s2a-") as temp:
            wd=Path(temp)
            header=wd/"include/audio_pipeline/audio_pipeline_build.h"
            header.parent.mkdir(parents=True)
            header.write_text("#ifndef AUDIO_PIPELINE_AUDIO_PIPELINE_BUILD_H\n"
                "#define AUDIO_PIPELINE_AUDIO_PIPELINE_BUILD_H\n"
                "#define AP_BUILD_RESAMPLER_BANDLIMITED 1\n#endif\n",
                encoding="ascii")
            for target in TARGETS:
                compiler="arm-linux-gnueabihf-gcc" if target=="arm" else "cc"
                need(shutil.which(compiler) is not None,
                     "MISSING_ACTUAL_COMPILER_"+target)
                versions[target]=s1.s0.tools.run(
                    [compiler,"--version"],logs).splitlines()[0]
                flags=[compiler,"-std=c11","-Wall","-Wextra","-Werror",
                    "-O2","-ffp-contract=off","-fno-fast-math",
                    "-pthread","-DAP_BUILD_RESAMPLER_BANDLIMITED=1",
                    "-I"+str(wd/"include"),"-I"+str(ROOT/"src"),
                    "-I"+str(HERE)]
                if target in ("sanitized","tsan"):
                    flags+=["-O1","-g","-fsanitize=thread" if target=="tsan"
                            else "-fsanitize=address,undefined",
                            "-fno-omit-frame-pointer"]
                if target=="arm":
                    flags+=["-march=armv7-a","-mfpu=neon-vfpv4",
                            "-mfloat-abi=hard"]
                objects=[]
                for i,source in enumerate(SOURCES):
                    obj=wd/f"{target}-{i}.o"
                    exempt=(s1.s0.c0.b1.b1.b0.b1.SOURCE_C,
                            s1.s0.c0.b1.b1.b0.b1.ARRAY_C)
                    warnings=[] if source in exempt else [
                        "-Wconversion","-Wshadow","-Wpedantic"]
                    s1.s0.tools.run(flags+warnings+[
                        "-c",str(source),"-o",str(obj)],logs,timeout=120)
                    objects.append(str(obj))
                exe=wd/(target+".elf")
                cmd=[compiler,*objects,"-pthread","-lm","-o",str(exe)]
                if target=="sanitized":cmd.append("-fsanitize=address,undefined")
                if target=="tsan":cmd.append("-fsanitize=thread")
                if target=="arm":cmd+=["-march=armv7-a","-mfpu=neon-vfpv4",
                                       "-mfloat-abi=hard"]
                s1.s0.tools.run(cmd,logs,timeout=120)
                binary_hashes[target]=digest(exe)
                actual=[str(exe)]
                if target=="arm":
                    need(shutil.which("qemu-arm") is not None and
                         Path("/usr/arm-linux-gnueabihf").is_dir(),
                         "REAL_ARM32_QEMU_REQUIRED")
                    actual=["qemu-arm","-L","/usr/arm-linux-gnueabihf",
                            str(exe)]
                env=dict(os.environ)
                if target=="sanitized":env.update({
                    "ASAN_OPTIONS":"detect_leaks=0:halt_on_error=1",
                    "UBSAN_OPTIONS":"halt_on_error=1"})
                if target=="tsan":
                    env.update({"TSAN_OPTIONS":"halt_on_error=1:exitcode=66"})
                result=s1.s0.tools.strict_json(s1.s0.tools.run(
                    actual,logs,timeout=240,env=env))
                repeat=s1.s0.tools.strict_json(s1.s0.tools.run(
                    actual,logs,timeout=240,env=env))
                need(result==repeat,"NONDETERMINISTIC_POSIX_EVIDENCE_"+target)
                verify_result(result)
                targets[target]=result
        need(set(targets)==set(TARGETS),"MISSING_ACTUAL_TARGET")
        report.update(decision=DECISION,actual_compiled_targets_complete=True,
                      target_order=list(TARGETS),target_results=targets,
                      compiler_versions=versions,binary_sha256=binary_hashes)
    except Exception as exc:
        report.update(decision=FAILURE,actual_compiled_targets_complete=False,
                      failure_type=type(exc).__name__,
                      failure_code=str(exc)[:280])
        import sys
        print("FE09_T3S2A_FAILURE_LOG_BEGIN",file=sys.stderr)
        print("\n".join(logs[-15:])[-6500:],file=sys.stderr)
        print("FE09_T3S2A_FAILURE_LOG_END",file=sys.stderr)
        raise
    finally:
        (out/"receipt.json").write_text(json.dumps(report,
            sort_keys=True,separators=(",",":"),allow_nan=False)+"\n",
            encoding="utf-8")
        (out/"collect.log").write_text("\n".join(logs)+"\n",
            encoding="utf-8")
        (out/"verify.log").write_text(
            MARKER if report["decision"]==DECISION else FAILURE+"\n",
            encoding="ascii")
        (out/"SHA256SUMS").write_text("".join(
            f"{digest(out/name)}  {name}\n" for name in
             ("receipt.json","collect.log","verify.log")),encoding="ascii")
    verify_output(out,sha)

def main()->None:
    ap=argparse.ArgumentParser(description=__doc__)
    group=ap.add_mutually_exclusive_group(required=True)
    for mode in ("self-test","collect","verify"):
        group.add_argument("--"+mode,action="store_true")
    ap.add_argument("--execution-source")
    ap.add_argument("--output",type=Path)
    args=ap.parse_args()
    try:
        if args.self_test:self_test();return
        need(args.output is not None and
             type(args.execution_source) is str and
             re.fullmatch("[0-9a-f]{40}",args.execution_source),
             "SOURCE_COMMIT_AND_OUTPUT_REQUIRED")
        need(s1.s0.tools.source_head()==args.execution_source,
             "HEAD_AND_SOURCE_SHA_DIFFER")
        if args.collect:collect(args.output,args.execution_source)
        else:
            verify_output(args.output,args.execution_source)
            print(MARKER.strip())
    except (NotAdmitted,s1.NotAdmitted,s1.s0.NotAdmitted,
            s1.s0.tools.GateFailure,OSError,
            subprocess.CalledProcessError,ValueError) as exc:
        raise SystemExit(FAILURE+": "+str(exc)) from None

if __name__=="__main__":
    main()
