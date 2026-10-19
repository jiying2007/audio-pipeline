#!/usr/bin/env python3
"""#799: first-party ORIGINAL B0 FRM1 immutable POSIX roots, no pruning.

Full four real compiler/sanitizer/ARM32-QEMU targets, deterministic twice,
pinned prior protected source, original source-only research evidence.
Host fsync/recovery is not NAND/UBIFS powercut or whole SSC305 qualification.
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

import fe09_b2s3_t3s2b0_manifest_qualification as b0

ROOT=b0.ROOT
HERE=b0.HERE
BASE="a825cd56080bae59dfb71071315a047dc144f714"
DECISION="FE09_T3S2B1A_IMMUTABLE_FRM1_ROOT_RESEARCH_ONLY"
FAILURE="FE09_T3S2B1A_FRM1_ROOT_NOT_ADMITTED"
MARKER="FE09_T3S2B1A_ORIGINAL_FRM1_IMMUTABLE_ROOT_REPLAY_VERIFIED\n"
TARGETS=("native","sanitized","arm","tsan")
MEMBERS=("SHA256SUMS","receipt.json","collect.log","verify.log")
C=HERE/"fe09_b2s3_t3s2b1a_immutable_root.c"
H=HERE/"fe09_b2s3_t3s2b1a_immutable_root.h"
TEST=HERE/"fe09_b2s3_t3s2b1a_immutable_root_test.c"
OWN=(C,H,TEST,Path(__file__).resolve())
FROZEN=tuple(dict.fromkeys((*b0.FROZEN,*b0.OWN,
              HERE/"FE09_T3S2B0_FBS1_ROLLING_INDEX.md")))
SOURCES=(*b0.SOURCES[:-1],C,TEST)
FALSE=("rolling_retention_qualified","original_source_deleted",
       "physical_powerloss_qualified","ssc305_hardware_qualified",
       "whole_device_memory_qualified","public_sdk_installed")
TRUE=("original_apx3_codec_reused","immutable_root_published")

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
    need(b0.BASE=="2dba395fd7d86b1e5b395f142fde15fdcd884f99",
         "ORIGINAL_PREDECESSOR_B0_BASE_MOVED")
    b0.pins()
    answer={}
    for path in FROZEN:
        rel=path.relative_to(ROOT).as_posix()
        data=subprocess.check_output(
            ["git","-c","safe.directory="+str(ROOT),
             "show",BASE+":"+rel],
            cwd=ROOT,timeout=30)
        need(0<len(data)<16*1024*1024 and
             hashlib.sha256(data).hexdigest()==digest(path),
             "FROZEN_FIRST_PARTY_SOURCE_CHANGED_"+rel)
        answer[rel]=hashlib.sha256(data).hexdigest()
    return answer

def verify_result(obj:dict)->None:
    need(type(obj) is dict and set(obj)=={
        "decision","source_role","profiles","fault_injections",
        "negative_checks","restart_recoveries",
        "original_frames","link_retry_cases",
        "root_file_bytes_accounted",*FALSE,*TRUE},
        "FALSE_OR_EXTRA_ROOT_AUTHORITY_FIELDS")
    need(obj["decision"]==DECISION and
         obj["source_role"]=="first-party-synthetic" and
         all(obj[key] is False for key in FALSE) and
         all(obj[key] is True for key in TRUE) and
         type(obj["profiles"]) is int and obj["profiles"]==336 and
         type(obj["fault_injections"]) is int and
         obj["fault_injections"]==336 and
         type(obj["negative_checks"]) is int and
         obj["negative_checks"]>=2000 and
         type(obj["restart_recoveries"]) is int and
         obj["restart_recoveries"]==673 and
         type(obj["original_frames"]) is int and
         obj["original_frames"]==688 and
         type(obj["link_retry_cases"]) is int and
         obj["link_retry_cases"]==192 and
         type(obj["root_file_bytes_accounted"]) is int and
         obj["root_file_bytes_accounted"]==
             336*(2*160+3*200)+(16*160+(16*17//2)*200),
         "UNOBSERVED_IMMUTABLE_ROOT_RESTART_OR_HOSTED_BYTES")

def identity(sha:str)->dict:
    need(type(sha) is str and re.fullmatch("[0-9a-f]{40}",sha),
         "NOT_AN_EXACT_GIT_SOURCE_SHA")
    return {
        "schema_version":1,
        "stage":"FE09_T3_S2_B1A_NONINSTALLED_FRM1_IMMUTABLE_POSIX_INDEX_ROOT",
        "preregistration":"https://github.com/jiying2007/audio-pipeline/issues/799",
        "source_commit":sha,
        "protected_predecessor_main":BASE,
        "protected_predecessor_verify":39183972743,
        "protected_predecessor_release":39186861185,
        "source_role":"first-party-synthetic",
        "immutable_predecessor_sha256":pins(),
        "own_source_sha256":{
            x.relative_to(ROOT).as_posix():digest(x) for x in OWN},
        "original_first_party_S2_APX3_rewritten":False,
        "original_S1_S2A_B0_source_modified":False,
        "root_gc_or_old_source_deletion":False,
        "physical_NAND_UBIFS_powerloss_qualified":False,
        "entire_ssc305_192k_memory_qualified":False,
        "public_sdk_installed":False,
    }

def verify_output(root:Path,sha:str)->None:
    caps={"SHA256SUMS":512,"receipt.json":300000,
          "collect.log":4*1024*1024,"verify.log":256}
    need(root.is_dir() and not root.is_symlink() and
         {p.name for p in root.iterdir()}==set(MEMBERS),
         "MISSING_OR_EXTRA_ORIGINAL_FOUR_MEMBER_EVIDENCE")
    for name in MEMBERS:
        p=root/name
        need(p.is_file() and not p.is_symlink() and
             0<p.stat().st_size<=caps[name],
             "OVERLARGE_OR_MISSING_"+name)
    manifest="".join(f"{digest(root/n)}  {n}\n" for n in
                     ("receipt.json","collect.log","verify.log"))
    need((root/"SHA256SUMS").read_text("ascii")==manifest,
         "ORIGINAL_SHA256SUMS_MEMBER_TAMPER")
    receipt=b0.s2a.s1.s0.tools.strict_json(
        (root/"receipt.json").read_text("utf-8"))
    for key,value in identity(sha).items():
        need(receipt.get(key)==value,"FROZEN_PREDECESSOR_DRIFT_"+key)
    need(receipt.get("decision")==DECISION and
         receipt.get("actual_compiled_targets_complete") is True and
         receipt.get("target_order")==list(TARGETS),
         "INCOMPLETE_ORIGINAL_S2_B1A_COMPILERS")
    targets=receipt.get("target_results")
    versions=receipt.get("compiler_versions")
    binary=receipt.get("binary_sha256")
    need(type(targets) is dict and set(targets)==set(TARGETS) and
         type(versions) is dict and set(versions)==set(TARGETS) and
         type(binary) is dict and set(binary)==set(TARGETS) and
         all(type(x) is str and len(x)>3 for x in versions.values()) and
         all(type(x) is str and re.fullmatch("[0-9a-f]{64}",x)
             for x in binary.values()),
         "FOUR_REAL_COMPILERS_AND_ELF_DIGESTS_REQUIRED")
    for target in TARGETS:
        verify_result(targets[target])
        need(targets[target]==targets["native"],
             "CROSS_ISA_ROOT_CONTRACT_DRIFT_"+target)
    need((root/"verify.log").read_text("ascii")==MARKER,
         "INDEPENDENT_ROOT_BYTE_READBACK_MARKER_MISSING")

def self_test()->None:
    pins()
    correct=dict(
        decision=DECISION,source_role="first-party-synthetic",
        profiles=336,fault_injections=336,
        negative_checks=2355,restart_recoveries=673,
        original_frames=688,link_retry_cases=192,
        root_file_bytes_accounted=336*920+29760,
        **{name:False for name in FALSE},
        **{name:True for name in TRUE})
    verify_result(correct)
    cases=[("decision",FAILURE),("source_role","hardware"),
           ("profiles",335),("fault_injections",335),
           ("negative_checks",1),("restart_recoveries",672),
           ("original_frames",687),("link_retry_cases",191),
           ("root_file_bytes_accounted",0),
           *[(n,True) for n in FALSE],
           *[(n,False) for n in TRUE]]
    for field,value in cases:
        mutant=dict(correct);mutant[field]=value
        try:verify_result(mutant)
        except NotAdmitted:pass
        else:raise NotAdmitted("FALSE_ROOT_CLAIM_"+field)
    print("FE09_T3S2B1A_FROZEN_SOURCE_FALSE_DURABILITY_SELFTEST_PASS",
          len(cases))

def collect(output:Path,sha:str)->None:
    need(not output.exists() and not output.is_symlink(),
         "REFUSE_EXISTING_ROOT_ARTIFACT_OVERWRITE")
    need(b0.s2a.s1.s0.tools.source_head()==sha,
         "EXACT_GIT_SOURCE_HEAD_REQUIRED")
    receipt=identity(sha)
    receipt.update(decision=FAILURE,actual_compiled_targets_complete=False)
    logs=[]
    output.mkdir(parents=True)
    try:
        results={};compilers={};binaries={}
        with tempfile.TemporaryDirectory(prefix="fe09-t3s2b1a-") as tmp:
            wd=Path(tmp)
            config=wd/"include/audio_pipeline/audio_pipeline_build.h"
            config.parent.mkdir(parents=True)
            config.write_text("#ifndef AUDIO_PIPELINE_AUDIO_PIPELINE_BUILD_H\n"
                "#define AUDIO_PIPELINE_AUDIO_PIPELINE_BUILD_H\n"
                "#define AP_BUILD_RESAMPLER_BANDLIMITED 1\n#endif\n",
                encoding="ascii")
            for target in TARGETS:
                compiler="arm-linux-gnueabihf-gcc" if target=="arm" else "cc"
                need(shutil.which(compiler) is not None,
                     "ACTUAL_COMPILER_MISSING_"+target)
                compilers[target]=b0.s2a.s1.s0.tools.run(
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
                for ix,source in enumerate(SOURCES):
                    obj=wd/f"{target}-{ix}.o"
                    except_sources=(
                        b0.s2a.s1.s0.c0.b1.b1.b0.b1.SOURCE_C,
                        b0.s2a.s1.s0.c0.b1.b1.b0.b1.ARRAY_C)
                    warnings=[] if source in except_sources else [
                        "-Wconversion","-Wshadow","-Wpedantic"]
                    b0.s2a.s1.s0.tools.run(flags+warnings+
                        ["-c",str(source),"-o",str(obj)],logs,timeout=120)
                    objs.append(str(obj))
                exe=wd/(target+".elf")
                link=[compiler,*objs,"-pthread","-lm","-o",str(exe)]
                if target=="sanitized":link.append("-fsanitize=address,undefined")
                if target=="tsan":link.append("-fsanitize=thread")
                if target=="arm":link+=["-march=armv7-a",
                                        "-mfpu=neon-vfpv4",
                                        "-mfloat-abi=hard"]
                b0.s2a.s1.s0.tools.run(link,logs,timeout=120)
                binaries[target]=digest(exe)
                cmd=[str(exe)]
                if target=="arm":
                    need(shutil.which("qemu-arm") is not None and
                         Path("/usr/arm-linux-gnueabihf").is_dir(),
                         "ACTUAL_ARM32_QEMU_NOT_PRESENT")
                    cmd=["qemu-arm","-L","/usr/arm-linux-gnueabihf",
                         str(exe)]
                env=dict(os.environ)
                if target=="sanitized":
                    env.update({"ASAN_OPTIONS":"detect_leaks=0:halt_on_error=1",
                                "UBSAN_OPTIONS":"halt_on_error=1"})
                if target=="tsan":
                    env.update({"TSAN_OPTIONS":"halt_on_error=1:exitcode=66"})
                first=b0.s2a.s1.s0.tools.strict_json(
                    b0.s2a.s1.s0.tools.run(cmd,logs,timeout=360,env=env))
                repeat=b0.s2a.s1.s0.tools.strict_json(
                    b0.s2a.s1.s0.tools.run(cmd,logs,timeout=360,env=env))
                need(first==repeat,
                     "NONDETERMINISTIC_ROOT_RESTART_RESULT_"+target)
                verify_result(first)
                results[target]=first
        receipt.update(decision=DECISION,
                       actual_compiled_targets_complete=True,
                       target_order=list(TARGETS),
                       target_results=results,
                       compiler_versions=compilers,
                       binary_sha256=binaries)
    except Exception as exc:
        receipt.update(decision=FAILURE,
                       actual_compiled_targets_complete=False,
                       failure_type=type(exc).__name__,
                       failure_code=str(exc)[:260])
        import sys
        print("FE09_T3S2B1A_ORIGINAL_FAILURE_LOG_BEGIN",file=sys.stderr)
        print("\n".join(logs[-15:])[-6500:],file=sys.stderr)
        print("FE09_T3S2B1A_ORIGINAL_FAILURE_LOG_END",file=sys.stderr)
        raise
    finally:
        (output/"receipt.json").write_text(json.dumps(
            receipt,sort_keys=True,separators=(",",":"),allow_nan=False)+"\n",
            encoding="utf-8")
        (output/"collect.log").write_text("\n".join(logs)+"\n",
                                           encoding="utf-8")
        (output/"verify.log").write_text(
            MARKER if receipt["decision"]==DECISION else FAILURE+"\n",
            encoding="ascii")
        (output/"SHA256SUMS").write_text("".join(
            f"{digest(output/name)}  {name}\n" for name in
             ("receipt.json","collect.log","verify.log")),
            encoding="ascii")
    verify_output(output,sha)

def main()->None:
    p=argparse.ArgumentParser(description=__doc__)
    opts=p.add_mutually_exclusive_group(required=True)
    for mode in ("self-test","collect","verify"):
        opts.add_argument("--"+mode,action="store_true")
    p.add_argument("--execution-source")
    p.add_argument("--output",type=Path)
    args=p.parse_args()
    try:
        if args.self_test:self_test();return
        need(args.output is not None and
             type(args.execution_source) is str and
             re.fullmatch("[0-9a-f]{40}",args.execution_source),
             "OUTPUT_AND_EXACT_SOURCE_REQUIRED")
        need(b0.s2a.s1.s0.tools.source_head()==args.execution_source,
             "GIT_CHECKOUT_SOURCE_CHANGED")
        if args.collect:collect(args.output,args.execution_source)
        else:
            verify_output(args.output,args.execution_source)
            print(MARKER.strip())
    except (NotAdmitted,b0.NotAdmitted,b0.s2a.NotAdmitted,
            b0.s2a.s1.NotAdmitted,b0.s2a.s1.s0.NotAdmitted,
            b0.s2a.s1.s0.tools.GateFailure,OSError,
            subprocess.CalledProcessError,ValueError) as exc:
        raise SystemExit(FAILURE+": "+str(exc)) from None

if __name__=="__main__":
    main()
