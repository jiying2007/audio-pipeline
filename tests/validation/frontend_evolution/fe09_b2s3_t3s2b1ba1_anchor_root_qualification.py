#!/usr/bin/env python3
"""#809 FRM2 original-source left-anchor qualification, hosted and no pruning.

The actual native/ASan+UBSan+LSan/ARM32-QEMU/TSan binaries run twice each.
Scientific source results are deterministic; real host process RSS and elapsed
time remain separate attribution. Four exact members preserve every failure.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

import fe09_b2s3_t3s2b1ba0_finite_outboard_qualification as a0

ROOT=a0.ROOT
HERE=a0.HERE
BASE="e3672ffe16e4c9d42a100e7712b9bbd3d8338545"
DECISION="FE09_B1B_A1_FRM2_NONZERO_ORIGINAL_LEFT_ANCHOR_HOSTED_NO_PRUNE"
FAILURE="FE09_B1B_A1_ORIGINAL_ANCHOR_ROOT_NOT_ADMITTED"
MARKER="FE09_B1B_A1_ORIGINAL_SOURCE_FOUR_TARGET_LOCAL_READBACK_PASS\n"
TARGETS=("native","sanitized","arm","tsan")
MEMBERS=("SHA256SUMS","receipt.json","collect.log","verify.log")
SANITIZER_ENVIRONMENT={"ASAN_OPTIONS":"detect_leaks=1:halt_on_error=1",
                       "UBSAN_OPTIONS":"halt_on_error=1",
                       "TSAN_OPTIONS":"halt_on_error=1:exitcode=66"}
MANIFEST=HERE/"fe09_b2s3_t3s2b1ba1_frozen_inputs.json"
MANIFEST_SHA256="babeac353b527cf2b342fa386f550c6ffcd542c47d32e44bc56b263a6dd10f08"
SOURCE_C=HERE/"fe09_b2s3_t3s2b1ba1_anchor_root.c"
SOURCE_H=HERE/"fe09_b2s3_t3s2b1ba1_anchor_root.h"
TEST=HERE/"fe09_b2s3_t3s2b1ba1_anchor_root_test.c"
DOC=HERE/"FE09_T3S2B1B_A1_FRM2_ANCHOR_ROOT.md"
OWN=(SOURCE_C,SOURCE_H,TEST,Path(__file__).resolve(),DOC,MANIFEST)
SOURCES=(*a0.SOURCES[:-1],SOURCE_C,TEST)
TOOLS=a0.f0.b0.s2a.s1.s0.tools
FALSE=("original_ack_created_by_a1","original_source_deleted",
       "real_rolling_retention_qualified","physical_powerloss_qualified",
       "ssc305_hardware_qualified","whole_device_memory_qualified",
       "public_sdk_installed")


class NotAdmitted(ValueError):
    pass


def need(value:object,reason:str)->None:
    if not value:raise NotAdmitted(reason)


def raw(path:Path,cap:int=16*1024*1024)->bytes:
    need(path.is_file() and not path.is_symlink() and 0<path.stat().st_size<=cap,
         "MISSING_OR_OVERSIZED_"+path.name)
    return path.read_bytes()


def sha(data:bytes)->str:
    return hashlib.sha256(data).hexdigest()


def digest(path:Path)->str:
    return sha(raw(path))


def blob(data:bytes)->str:
    return hashlib.sha1(b"blob "+str(len(data)).encode("ascii")+b"\0"+data).hexdigest()


def pins()->dict:
    need(digest(MANIFEST)==MANIFEST_SHA256,"PREIMPLEMENTATION_INPUT_MANIFEST_CHANGED")
    manifest=TOOLS.strict_json(raw(MANIFEST).decode("utf-8"))
    need(manifest["protected_a0_main"]==BASE and len(manifest["inputs"])==75 and
         manifest["a0_issue_completed_at"]=="2026-10-20T05:09:00Z" and
         manifest["a0_verify_run"]==39274232480 and
         manifest["a0_release_convergence_run"]==39284587954,
         "A0_COMPLETED_PREREQUISITE_IDENTITY_DRIFT")
    a0.pins()
    for relative,expected in manifest["inputs"].items():
        path=ROOT/relative
        original=subprocess.check_output(
            ["git","-c","safe.directory="+str(ROOT),"show",BASE+":"+relative],
            cwd=ROOT,timeout=30)
        current=raw(path)
        need(current==original and expected=={
             "git_blob_sha1":blob(original),"sha256":sha(original),"bytes":len(original)},
             "FROZEN_ORIGINAL_INPUT_CHANGED_"+relative)
    return manifest["inputs"]


def exact_head(source:str)->None:
    need(type(source) is str and re.fullmatch(r"[0-9a-f]{40}",source) and
         TOOLS.source_head()==source,"ACTUAL_EXECUTION_GIT_HEAD_REQUIRED")
    if os.environ.get("GITHUB_SHA"):
        need(os.environ["GITHUB_SHA"]==source,"GITHUB_CHECKOUT_IDENTITY_MISMATCH")


def identity(source:str)->dict:
    exact_head(source)
    frozen=pins()
    for path in (*OWN,*(ROOT/p for p in frozen)):
        relative=path.relative_to(ROOT).as_posix()
        committed=subprocess.check_output(
            ["git","-c","safe.directory="+str(ROOT),"show",source+":"+relative],
            cwd=ROOT,timeout=30)
        need(committed==raw(path),"UNCOMMITTED_EXECUTION_INPUT_"+relative)
    return {
        "schema_version":1,"stage":"FE09_T3_S2_B1B_A1_FRM2_LEFT_ANCHOR_NO_PRUNE",
        "preregistration":"https://github.com/jiying2007/audio-pipeline/issues/809",
        "source_commit":source,"protected_a0_main":BASE,
        "a0_completed_at":"2026-10-20T05:09:00Z",
        "protected_a0_verify":39274232480,"protected_a0_release_convergence":39284587954,
        "protected_a0_original_artifact":12197835183,
        "protected_a0_original_artifact_zip_sha256":
            "3c42f7a64c596c20ac0b321a2bcc3bd5b55cae63d12c5c8bfcc0b1f50eb6f958",
        "input_manifest_sha256":MANIFEST_SHA256,"frozen_original_inputs":frozen,
        "own_source_sha256":{p.relative_to(ROOT).as_posix():digest(p) for p in OWN},
        "source_role":"first-party-synthetic",
        "original_A0_S1_S2_S2A_B0_B1a_source_changed":False,
        "original_APX3_writer_CRC_parser_reimplemented":False,
        "FRM1_reinterpreted":False,"original_source_deleted":False,
        "atomic_root_and_source_ACK_qualified":False,
        "physical_NAND_UBIFS_powerloss_qualified":False,
        "entire_ssc305_192k_memory_or_10ms_qualified":False,
        "public_sdk_installed":False,
    }


def is_sha(value:object)->bool:
    return type(value) is str and re.fullmatch(r"[0-9a-f]{64}",value) is not None and value!="0"*64


def verify_result(result:dict)->None:
    fixed={"profiles":48,"matrix_original_frames":1536,"matrix_original_acks":1536,
           "additional_negative_fixture_frames":17,"logical_first":17,"logical_last":32,
           "physical_original_files":1536,"hosted_roots":48,"restart_verified":51,
           "host_faults_rejected":10,"valid_resealed_source_rejected":1,"root_disk_bytes":66048}
    need(type(result) is dict and set(result)=={
         "decision","source_role","negative_checks","original_source_disk_bytes","cases",*fixed,*FALSE},
         "SCIENTIFIC_RESULT_SCHEMA_DRIFT")
    need(result["decision"]==DECISION and result["source_role"]=="first-party-synthetic" and
         all(result[k] is False for k in FALSE) and
         all(type(result[k]) is int and result[k]==v for k,v in fixed.items()) and
         type(result["negative_checks"]) is int and result["negative_checks"]>100 and
         type(result["original_source_disk_bytes"]) is int and
         0<result["original_source_disk_bytes"]<16*1024*1024,
         "INCOMPLETE_OR_PROMOTED_ANCHOR_ROOT_RESULT")
    cases=result["cases"]
    expected=[(scene,rate,(1,2,4,4)[scene],render,k) for scene in range(4)
              for rate in (16000,32000,48000) for render in (0,1) for k in (1,2)]
    need(type(cases) is list and len(cases)==48,"INCOMPLETE_ORIGINAL_SOURCE_MATRIX")
    for case,values in zip(cases,expected):
        need(type(case) is dict and set(case)=={
             "scene","rate","mics","render","k","anchor_sha256","root_sha256","original_files_sha256"},
             "CASE_SCHEMA_DRIFT")
        need(all(type(case[k]) is int and case[k]==v for k,v in
             zip(("scene","rate","mics","render","k"),values)) and
             all(is_sha(case[k]) for k in ("anchor_sha256","root_sha256","original_files_sha256")),
             "UNOBSERVED_OR_DUPLICATED_SOURCE_PROFILE")
    need(len({c["root_sha256"] for c in cases})==48,"ROOT_OWNER_DEPTH_OR_SLOT_IDENTITY_LOST")
    for index in range(0,48,2):
        need(all(cases[index][key]==cases[index+1][key] for key in
                 ("anchor_sha256","original_files_sha256")),
             "K1_K2_CHANGED_ORIGINAL_AUDIO_OR_CHAIN")


def host_metrics(stderr:str)->dict:
    prefix="FE09_A1_HOST_ATTRIBUTION "
    lines=stderr.splitlines()
    need(len(lines)==1 and lines[0].startswith(prefix),"MISSING_OR_EXTRA_HOST_ATTRIBUTION")
    values=TOOLS.strict_json(lines[0][len(prefix):])
    need(set(values)=={"elapsed_ns","max_rss_kib","root_owner_bytes","fixture_bytes"} and
         all(type(v) is int and 0<v<2**63 for v in values.values()),
         "INVALID_HOST_ATTRIBUTION_NOT_A_DEVICE_BUDGET")
    return values


def compile_plan(target:str,execution_root:Path,directory:Path)->tuple[list[list[str]],list[str],list[str]]:
    compiler="arm-linux-gnueabihf-gcc" if target=="arm" else "cc"
    flags=[compiler,"-std=c11","-Wall","-Wextra","-Werror","-O2",
           "-ffp-contract=off","-fno-fast-math","-pthread",
           "-DAP_BUILD_RESAMPLER_BANDLIMITED=1","-I"+str(directory/"include"),
           "-I"+str(execution_root/"src"),
           "-I"+str(execution_root/HERE.relative_to(ROOT))]
    if target in ("sanitized","tsan"):
        flags+=["-O1","-g","-fsanitize=thread" if target=="tsan" else "-fsanitize=address,undefined",
                "-fno-omit-frame-pointer"]
    arm_flags=["-march=armv7-a","-mfpu=neon-vfpv4","-mfloat-abi=hard"]
    if target=="arm":flags+=arm_flags
    commands=[];objects=[]
    exceptions=(a0.f0.b0.s2a.s1.s0.c0.b1.b1.b0.b1.SOURCE_C,
                a0.f0.b0.s2a.s1.s0.c0.b1.b1.b0.b1.ARRAY_C)
    for index,path in enumerate(SOURCES):
        obj=directory/f"{target}-{index}.o"
        warnings=[] if path in exceptions else ["-Wconversion","-Wshadow","-Wpedantic"]
        commands.append(flags+warnings+["-c",str(execution_root/path.relative_to(ROOT)),"-o",str(obj)])
        objects.append(str(obj))
    executable=directory/(target+".elf")
    link=[compiler,*objects,"-pthread","-lm","-o",str(executable)]
    if target=="sanitized":link+=["-fsanitize=address,undefined"]
    if target=="tsan":link+=["-fsanitize=thread"]
    if target=="arm":link+=arm_flags
    invoke=(["qemu-arm","-L","/usr/arm-linux-gnueabihf",str(executable)]
            if target=="arm" else [str(executable)])
    return commands,link,invoke


def target_environment(target:str)->dict:
    if target=="sanitized":return {k:SANITIZER_ENVIRONMENT[k] for k in ("ASAN_OPTIONS","UBSAN_OPTIONS")}
    if target=="tsan":return {"TSAN_OPTIONS":SANITIZER_ENVIRONMENT["TSAN_OPTIONS"]}
    return {}


def run(command:list[str],logs:list[dict],timeout:int=120,
        env:dict|None=None)->subprocess.CompletedProcess:
    overrides={} if env is None else env
    event={"kind":"invocation","command":command,"cwd":str(ROOT),
           "timeout_seconds":timeout,"environment":overrides,"status":"started"}
    logs.append(event)
    environment=dict(os.environ);environment.update(overrides)
    try:
        completed=subprocess.run(command,cwd=ROOT,env=environment,capture_output=True,text=True,
                                 encoding="utf-8",errors="replace",timeout=timeout,check=False)
    except subprocess.TimeoutExpired as error:
        event.update(status="timeout",exit_code=None)
        for kind,data in (("stdout",error.stdout),("stderr",error.stderr)):
            event[kind]=(data.decode("utf-8",errors="replace") if isinstance(data,bytes) else data) or ""
        raise NotAdmitted("ACTUAL_TARGET_OR_TOOL_TIMEOUT") from None
    event.update(status="completed",exit_code=completed.returncode,
                 stdout=completed.stdout,stderr=completed.stderr)
    need(completed.returncode==0,"ACTUAL_TOOL_OR_TARGET_FAILED_"+str(completed.returncode))
    return completed


def verify_execution_log(data:bytes,receipt:dict,source:str)->None:
    """Recompute each observed replay from the complete original invocation log.

    Inner hashes alone cannot associate an arbitrary receipt with a real replay.
    Require the exact target-specific compile/link/ELF/two-execution sequence,
    then derive scientific output hashes and host observations from raw stdout.
    This consistency check still requires a trusted run/ZIP outside this file.
    """
    events=[TOOLS.strict_json(line) for line in data.decode("utf-8").splitlines()]
    cursor=0
    def event(kind:str,keys:set[str])->dict:
        nonlocal cursor
        need(cursor<len(events),"INCOMPLETE_ORIGINAL_EXECUTION_LOG")
        value=events[cursor];cursor+=1
        need(type(value) is dict and set(value)==keys|{"kind"} and value["kind"]==kind,
             "EXECUTION_EVENT_SCHEMA_OR_ORDER_DRIFT_"+kind)
        return value
    header=event("collection",{"schema_version","source_commit"})
    need(header=={"kind":"collection","schema_version":1,"source_commit":source},
         "EXECUTION_LOG_CURRENT_SOURCE_MISMATCH")
    build=event("build_directory",{"execution_root","directory"})
    for key in ("execution_root","directory"):
        need(type(build[key]) is str and Path(build[key]).is_absolute() and
             ".." not in Path(build[key]).parts,"INVALID_ACTUAL_BUILD_PATH")
    execution_root=Path(build["execution_root"]);directory=Path(build["directory"])
    need(execution_root!=directory,"BUILD_DIRECTORY_IS_SOURCE_ROOT")
    def invocation(command:list[str],timeout:int=120,env:dict|None=None)->dict:
        value=event("invocation",{"command","cwd","timeout_seconds","environment",
                                  "status","exit_code","stdout","stderr"})
        need(value["command"]==command and value["cwd"]==str(execution_root) and
             type(value["timeout_seconds"]) is int and value["timeout_seconds"]==timeout and
             value["environment"]==({} if env is None else env) and
             value["status"]=="completed" and type(value["exit_code"]) is int and
             value["exit_code"]==0 and type(value["stdout"]) is str and type(value["stderr"]) is str,
             "MISSING_SUCCESSFUL_EXACT_TARGET_INVOCATION")
        return value
    for target in TARGETS:
        compiler="arm-linux-gnueabihf-gcc" if target=="arm" else "cc"
        version=invocation([compiler,"--version"])
        observed_compiler=event("compiler_identity",{"target","identity"})
        need(observed_compiler["target"]==target and
             observed_compiler["identity"]==receipt["compiler_identity"][target] and
             version["stdout"].splitlines() and
             observed_compiler["identity"]["version"]==version["stdout"].splitlines()[0],
             "COMPILER_RECEIPT_DOES_NOT_MATCH_ACTUAL_LOG")
        commands,link,command=compile_plan(target,execution_root,directory)
        for compile_command in commands:invocation(compile_command)
        invocation(link)
        binary=event("built_elf",{"target","path","sha256"})
        need(binary=={"kind":"built_elf","target":target,
             "path":str(directory/(target+".elf")),"sha256":receipt["binary_sha256"][target]},
             "TARGET_ELF_IDENTITY_NOT_FROM_BUILD")
        if target=="arm":
            qemu=invocation(["qemu-arm","--version"])
            observed_qemu=event("qemu_identity",{"identity"})
            need(observed_qemu["identity"]==receipt["qemu_identity"] and qemu["stdout"].splitlines() and
                 observed_qemu["identity"]["version"]==qemu["stdout"].splitlines()[0],
                 "QEMU_IDENTITY_NOT_FROM_ACTUAL_INVOCATION")
        for repetition in range(2):
            executed=invocation(command,540,target_environment(target))
            decoded=TOOLS.strict_json(executed["stdout"]);verify_result(decoded)
            need(decoded==receipt["target_results"][target] and
                 sha(executed["stdout"].encode("utf-8"))==receipt["replay_stdout_sha256"][target][repetition] and
                 host_metrics(executed["stderr"])==receipt["host_attribution"][target][repetition],
                 "RECEIPT_REPLAY_NOT_OBSERVED_IN_ORIGINAL_EXECUTION_LOG")
    completion=event("completion",{"decision"})
    need(completion["decision"]==DECISION and cursor==len(events),
         "EXTRA_OR_INCOMPLETE_ORIGINAL_TARGET_EXECUTIONS")


def verify_output(output:Path,source:str)->None:
    limits={"SHA256SUMS":512,"receipt.json":300000,"collect.log":5*1024*1024,"verify.log":256}
    need(output.is_dir() and not output.is_symlink() and
         {p.name for p in output.iterdir()}==set(MEMBERS),"ORIGINAL_A1_ARTIFACT_MEMBER_SET_DRIFT")
    for name,limit in limits.items():raw(output/name,limit)
    need(raw(output/"SHA256SUMS").decode("ascii")=="".join(
         f"{digest(output/name)}  {name}\n" for name in ("receipt.json","collect.log","verify.log")),
         "ORIGINAL_A1_INNER_SHA256_MISMATCH")
    receipt=TOOLS.strict_json(raw(output/"receipt.json").decode("utf-8"))
    current_identity=identity(source)
    need(type(receipt) is dict and set(receipt)==set(current_identity)|{
         "decision","actual_targets_complete","target_order","repetitions_per_target",
         "target_results","compiler_identity","binary_sha256","host_attribution",
         "replay_stdout_sha256","host_resource_scope","sanitizer_environment","qemu_identity"},
         "A1_RECEIPT_SCHEMA_DRIFT")
    for key,value in current_identity.items():
        need(receipt.get(key)==value,"EXACT_A1_SOURCE_IDENTITY_CHANGED_"+key)
    need(receipt.get("decision")==DECISION and receipt.get("actual_targets_complete") is True and
         receipt.get("target_order")==list(TARGETS) and
         type(receipt.get("repetitions_per_target")) is int and receipt["repetitions_per_target"]==2 and
         receipt.get("host_resource_scope")=="attribution-only-process-including-fixtures-or-QEMU-not-SSC305",
         "FOUR_ACTUAL_REPEATED_TARGETS_REQUIRED")
    for key in ("target_results","compiler_identity","binary_sha256","host_attribution","replay_stdout_sha256"):
        need(type(receipt.get(key)) is dict and set(receipt[key])==set(TARGETS),"MISSING_ACTUAL_TARGET_"+key)
    for target in TARGETS:
        verify_result(receipt["target_results"][target])
        need(receipt["target_results"][target]==receipt["target_results"]["native"],"CROSS_TARGET_ORIGINAL_SOURCE_WITNESS_DRIFT")
        compiler=receipt["compiler_identity"][target]
        need(type(compiler) is dict and set(compiler)=={"command","version","executable_sha256"} and
             compiler["command"]==("arm-linux-gnueabihf-gcc" if target=="arm" else "cc") and
             type(compiler["version"]) is str and len(compiler["version"])>5 and is_sha(compiler["executable_sha256"]) and
             is_sha(receipt["binary_sha256"][target]),"MISSING_REAL_COMPILER_OR_ELF_IDENTITY")
        replays=receipt["replay_stdout_sha256"][target]
        need(type(replays) is list and len(replays)==2 and all(is_sha(x) for x in replays) and replays[0]==replays[1],
             "MISSING_TWO_REAL_DETERMINISTIC_REPLAYS")
        observed=receipt["host_attribution"][target]
        need(type(observed) is list and len(observed)==2,"MISSING_TWO_HOST_OBSERVATIONS")
        for measurement in observed:host_metrics("FE09_A1_HOST_ATTRIBUTION "+json.dumps(measurement))
    need(len(set(receipt["binary_sha256"].values()))==4,"ONE_ELF_RELABELED_AS_MULTIPLE_TARGETS")
    qemu=receipt["qemu_identity"]
    need(type(qemu) is dict and set(qemu)=={"command","version","executable_sha256","sysroot","cpu_scope"} and
         qemu["command"]=="qemu-arm" and qemu["sysroot"]=="/usr/arm-linux-gnueabihf" and
         qemu["cpu_scope"]=="generic-AArch32-armv7-a-neon-vfpv4-not-Cortex-A32-hardware" and
         type(qemu["version"]) is str and len(qemu["version"])>5 and is_sha(qemu["executable_sha256"]),
         "MISSING_ACTUAL_QEMU_IDENTITY_OR_HARDWARE_PROMOTION")
    need(receipt.get("sanitizer_environment")==SANITIZER_ENVIRONMENT,
         "SANITIZER_DETECTION_DISABLED_OR_CHANGED")
    verify_execution_log(raw(output/"collect.log"),receipt,source)
    need(raw(output/"verify.log").decode("ascii")==MARKER,"A1_LOCAL_READBACK_MARKER_MISSING")


def self_test()->None:
    pins()
    fixture={"decision":DECISION,"source_role":"first-party-synthetic","profiles":48,
             "matrix_original_frames":1536,"matrix_original_acks":1536,"additional_negative_fixture_frames":17,
             "logical_first":17,"logical_last":32,"physical_original_files":1536,"hosted_roots":48,
             "negative_checks":101,"restart_verified":51,"host_faults_rejected":10,
             "valid_resealed_source_rejected":1,"original_source_disk_bytes":3508224,"root_disk_bytes":66048,
             **{key:False for key in FALSE},"cases":[]}
    for scene in range(4):
        for rate in (16000,32000,48000):
            for render in (0,1):
                for k in (1,2):
                    owner=f"CONTRACT_FIXTURE_ONLY_{scene}_{rate}_{render}"
                    fixture["cases"].append(dict(scene=scene,rate=rate,mics=(1,2,4,4)[scene],render=render,k=k,
                        anchor_sha256=sha((owner+"anchor").encode()),root_sha256=sha((owner+str(k)).encode()),
                        original_files_sha256=sha(owner.encode())))
    verify_result(fixture)
    mutants=[("decision",FAILURE),("profiles",47),("matrix_original_frames",1535),
             ("matrix_original_acks",1537),("physical_original_files",768),("logical_first",1),
             ("negative_checks",100),("restart_verified",50),("host_faults_rejected",9),
             ("valid_resealed_source_rejected",0),("root_disk_bytes",66047),
             *[(key,True) for key in FALSE]]
    count=0
    for key,value in mutants:
        changed=copy.deepcopy(fixture);changed[key]=value
        try:verify_result(changed)
        except NotAdmitted:count+=1
        else:raise NotAdmitted("FALSE_CONTRACT_PROMOTION_"+key)
    for key,value in (("scene",False),("k",2),("anchor_sha256","0"*64),("root_sha256","unproven")):
        changed=copy.deepcopy(fixture);changed["cases"][0][key]=value
        try:verify_result(changed)
        except NotAdmitted:count+=1
        else:raise NotAdmitted("FALSE_CASE_ADMISSION_"+key)
    print("FE09_A1_FRM2_CONTRACT_SELF_TEST_ONLY_PASS negatives="+str(count))


def collect(output:Path,source:str)->None:
    need(not output.exists() and not output.is_symlink(),"REFUSE_OVERWRITE_ORIGINAL_A1_EVIDENCE")
    exact_head(source)
    output.mkdir(parents=True)
    logs=[{"kind":"collection","schema_version":1,"source_commit":source}]
    receipt={"schema_version":1,"source_commit":source,"decision":FAILURE,"actual_targets_complete":False}
    try:
        receipt.update(identity(source))
        results={};compilers={};binaries={};attribution={};replay_hashes={}
        # Attach live evidence immediately: later target failure must preserve
        # every compiler/ELF/replay actually obtained before that failure.
        receipt.update(target_order=list(TARGETS),repetitions_per_target=2,
            target_results=results,compiler_identity=compilers,binary_sha256=binaries,
            host_attribution=attribution,replay_stdout_sha256=replay_hashes,
            host_resource_scope="attribution-only-process-including-fixtures-or-QEMU-not-SSC305",
            sanitizer_environment=dict(SANITIZER_ENVIRONMENT))
        with tempfile.TemporaryDirectory(prefix="fe09-t3s2b1ba1-") as directory:
            wd=Path(directory)
            logs.append({"kind":"build_directory","execution_root":str(ROOT),"directory":str(wd)})
            generated=wd/"include/audio_pipeline/audio_pipeline_build.h"
            generated.parent.mkdir(parents=True)
            generated.write_text("#ifndef AUDIO_PIPELINE_AUDIO_PIPELINE_BUILD_H\n"
                "#define AUDIO_PIPELINE_AUDIO_PIPELINE_BUILD_H\n"
                "#define AP_BUILD_RESAMPLER_BANDLIMITED 1\n#endif\n",encoding="ascii")
            for target in TARGETS:
                compiler="arm-linux-gnueabihf-gcc" if target=="arm" else "cc"
                command_path=shutil.which(compiler)
                need(command_path is not None,"ACTUAL_COMPILER_MISSING_"+target)
                compilers[target]={"command":compiler,
                    "version":run([compiler,"--version"],logs).stdout.splitlines()[0],
                    "executable_sha256":digest(Path(command_path).resolve())}
                logs.append({"kind":"compiler_identity","target":target,"identity":compilers[target]})
                commands,link,command=compile_plan(target,ROOT,wd)
                for compile_command in commands:run(compile_command,logs)
                executable=wd/(target+".elf")
                run(link,logs);binaries[target]=digest(executable)
                logs.append({"kind":"built_elf","target":target,"path":str(executable),"sha256":binaries[target]})
                if target=="arm":
                    qemu=shutil.which("qemu-arm")
                    need(qemu is not None and Path("/usr/arm-linux-gnueabihf").is_dir(),
                         "ACTUAL_ARM32_QEMU_ENVIRONMENT_MISSING")
                    receipt["qemu_identity"]={"command":"qemu-arm",
                        "version":run(["qemu-arm","--version"],logs).stdout.splitlines()[0],
                        "executable_sha256":digest(Path(qemu).resolve()),"sysroot":"/usr/arm-linux-gnueabihf",
                        "cpu_scope":"generic-AArch32-armv7-a-neon-vfpv4-not-Cortex-A32-hardware"}
                    logs.append({"kind":"qemu_identity","identity":receipt["qemu_identity"]})
                actual=[];observed=[];hashes=[]
                attribution[target]=observed;replay_hashes[target]=hashes
                for _ in range(2):
                    completed=run(command,logs,timeout=540,env=target_environment(target))
                    decoded=TOOLS.strict_json(completed.stdout);verify_result(decoded)
                    actual.append(decoded);observed.append(host_metrics(completed.stderr));hashes.append(sha(completed.stdout.encode()))
                    results[target]=decoded
                need(actual[0]==actual[1],"NONDETERMINISTIC_ORIGINAL_SOURCE_"+target)
                print("FE09_A1_ACTUAL_TARGET_TWICE_PASS "+target,flush=True)
        need(all(value==results["native"] for value in results.values()),"CROSS_TARGET_ORIGINAL_SOURCE_WITNESS_DRIFT")
        logs.append({"kind":"completion","decision":DECISION})
        verify_execution_log("\n".join(json.dumps(e,separators=(",",":")) for e in logs).encode(),receipt,source)
        receipt.update(decision=DECISION,actual_targets_complete=True)
    except Exception as error:
        receipt.update(decision=FAILURE,actual_targets_complete=False,
                       failure_type=type(error).__name__,failure_code=str(error)[:300])
        print("FE09_A1_FAILURE_LOG_BEGIN\n"+"\n".join(json.dumps(e) for e in logs[-12:])[-10000:]+
              "\nFE09_A1_FAILURE_LOG_END",file=sys.stderr)
        raise
    finally:
        (output/"receipt.json").write_text(json.dumps(receipt,sort_keys=True,separators=(",",":"),allow_nan=False)+"\n")
        (output/"collect.log").write_text("\n".join(json.dumps(e,separators=(",",":"),allow_nan=False) for e in logs)+"\n")
        (output/"verify.log").write_text(MARKER if receipt["decision"]==DECISION else FAILURE+"\n",encoding="ascii")
        (output/"SHA256SUMS").write_text("".join(f"{digest(output/name)}  {name}\n" for name in
            ("receipt.json","collect.log","verify.log")),encoding="ascii")
    verify_output(output,source)


def main()->None:
    parser=argparse.ArgumentParser(description=__doc__)
    mode=parser.add_mutually_exclusive_group(required=True)
    for name in ("self-test","collect","verify"):mode.add_argument("--"+name,action="store_true")
    parser.add_argument("--output",type=Path)
    parser.add_argument("--execution-source")
    args=parser.parse_args()
    try:
        if args.self_test:self_test();return
        need(args.output is not None and args.execution_source is not None,"OUTPUT_AND_EXACT_SOURCE_REQUIRED")
        exact_head(args.execution_source)
        if args.collect:collect(args.output,args.execution_source)
        else:verify_output(args.output,args.execution_source);print(MARKER.strip())
    except (ValueError,OSError,subprocess.CalledProcessError) as error:
        raise SystemExit(FAILURE+": "+str(error)) from None


if __name__=="__main__":main()
