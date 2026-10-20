#!/usr/bin/env python3
"""FE09 B1-S0: true source-owner pthread SPSC + first-party mic BF.

Noninstalled research ONLY: no APX3 recorder, no physical ADC/DAC clock,
no real hardware/SSC305 memory/performance or shipping/public SDK admission.
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

import fe09_array_sdk_draft_qualification_r2a as tools
import fe09_b2s3_t2b_b0_capture_only_qualification as b0

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
BASE = "58c9c77567998839c38bf1d8a6da72bdbead1620"
DECISION = "FE09_T2B_B1S0_OWNER_WITNESS_SPSC_CAPTURE_BF_NO_RECORDER"
FAILURE = "FE09_T2B_B1S0_OWNER_WITNESS_SPSC_NOT_ADMITTED"
TARGETS = ("native", "sanitized", "arm", "tsan")
MEMBERS = ("SHA256SUMS", "receipt.json", "collect.log", "verify.log")
SOURCE_C = HERE / "fe09_b2s3_t2b_b1s0_owner_spsc.c"
SOURCE_H = HERE / "fe09_b2s3_t2b_b1s0_owner_spsc.h"
TEST_C = HERE / "fe09_b2s3_t2b_b1s0_owner_spsc_test.c"
OWN = (SOURCE_C, SOURCE_H, TEST_C, Path(__file__).resolve())
FROZEN = tuple(dict.fromkeys((*b0.FROZEN, *b0.OWN)))
SOURCES = (*b0.SOURCES[:-1], SOURCE_C, TEST_C)


class Denied(ValueError):
    pass


def need(predicate: bool, code: str) -> None:
    if not predicate:
        raise Denied(code)


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def file_sha(path: Path) -> str:
    need(path.is_file() and not path.is_symlink() and
         0 < path.stat().st_size <= 16 * 1024 * 1024,
         "MISSING_OR_OVERSIZE_SOURCE_" + path.name)
    return sha(path.read_bytes())


def frozen() -> dict:
    need(b0.BASE == "46a29d288f4b58a940400e1f0a50195863631d18",
         "FROZEN_B0_CONTRACT_CHANGED")
    pins = {}
    for file in FROZEN:
        rel = str(file.relative_to(ROOT))
        raw = subprocess.check_output(
            ["git", "-c", "safe.directory=" + str(ROOT),
             "show", BASE + ":" + rel], cwd=ROOT, timeout=30)
        need(0 < len(raw) <= 16 * 1024 * 1024 and
             sha(raw) == file_sha(file), "FROZEN_B0_SOURCE_CHANGED_" + rel)
        pins[rel] = sha(raw)
    return pins


def identity(commit: str) -> dict:
    need(re.fullmatch(r"[a-f0-9]{40}", commit) is not None,
         "NOT_IMMUTABLE_GIT_SOURCE")
    return {
        "schema_version": 1,
        "stage": "FE09-R2B2-T2B-B1S0-REAL-OWNER-SPSC-NO-RECORDER",
        "source_commit": commit,
        "preregistration": "https://github.com/jiying2007/audio-pipeline/issues/776",
        "predecessor_main": BASE,
        "predecessor_verify": 38900258289,
        "predecessor_release": 38904105405,
        "source_role": "first-party-synthetic",
        "own_sha256": {str(p.relative_to(ROOT)): file_sha(p) for p in OWN},
        "frozen_predecessor_sha256": frozen(),
        "physical_absence_or_clock_qualified": False,
        "apx3_recorder_qualified": False,
        "ssc305_device_qualified": False,
        "public_sdk_installed": False,
        "shipping_dsp_modified": False,
        "legacy_apd2_modified": False,
        "no_cryptographic_source_auth": True,
    }


def check_result(row: dict) -> None:
    keys = {
        "schema_version", "decision", "source_role",
        "real_pthread_source_owners", "capture_bf_continuity_software",
        "source_absence_physical_verified", "apx3_recording_qualified",
        "device_qualified", "public_sdk_installed",
        "profiles", "profile_count", "negative_checks", "control_digest",
    }
    need(type(row) is dict and set(row) == keys, "TARGET_SCHEMA_CHANGED")
    need(type(row["schema_version"]) is int and row["schema_version"] == 1 and
         row["decision"] == DECISION and
         row["source_role"] == "first-party-synthetic" and
         row["real_pthread_source_owners"] is True and
         row["capture_bf_continuity_software"] is True and
         all(row[k] is False for k in (
             "source_absence_physical_verified", "apx3_recording_qualified",
             "device_qualified", "public_sdk_installed")) and
         type(row["profile_count"]) is int and row["profile_count"] == 48 and
         type(row["negative_checks"]) is int and
         row["negative_checks"] >= 600 and
         type(row["control_digest"]) is str and
         re.fullmatch(r"[a-f0-9]{16}", row["control_digest"]) is not None,
         "NO_REAL_OWNER_SPSC_OR_FALSE_PRODUCT_AUTHORITY")
    expected = [(name, rate, depth, render)
                for name in ("C1_BASELINE","C2_ULA","C4_ULA","C4_UCA")
                for rate in (16000,32000,48000)
                for depth in (2,4)
                for render in (0,1)]
    profiles = row["profiles"]
    need(type(profiles) is list and len(profiles) == len(expected),
         "MISSING_ACTUAL_OWNER_CONCURRENCY_MATRIX")
    for item, (name, rate, depth, render) in zip(profiles, expected):
        need(type(item) is dict and set(item) == {
            "scene", "rate", "render_enabled", "depth", "frames",
            "control_hash", "bf_hash"
        } and item["scene"] == name and
             type(item["rate"]) is int and item["rate"] == rate and
             type(item["render_enabled"]) is int and
             item["render_enabled"] == render and
             type(item["depth"]) is int and item["depth"] == depth and
             type(item["frames"]) is int and item["frames"] == 24 and
             type(item["control_hash"]) is str and
             re.fullmatch(r"[a-f0-9]{16}", item["control_hash"]) is not None and
             type(item["bf_hash"]) is str and
             re.fullmatch(r"[a-f0-9]{16}", item["bf_hash"]) is not None,
             "FAKE_SOURCE_SCENE_OR_OUTPUT_" + name)


def check_targets(targets: dict) -> None:
    need(type(targets) is dict and set(targets) == set(TARGETS),
         "MISSING_NATIVE_ASAN_ARM_TSAN")
    for row in targets.values():
        check_result(row)
    first = targets["native"]
    for target in TARGETS[1:]:
        other = targets[target]
        for key in ("schema_version", "decision", "source_role",
                    "real_pthread_source_owners",
                    "capture_bf_continuity_software",
                    "source_absence_physical_verified",
                    "apx3_recording_qualified",
                    "device_qualified", "public_sdk_installed",
                    "profile_count", "negative_checks", "control_digest"):
            need(first[key] == other[key],
                 "TARGET_INTEGER_VERDICT_MISMATCH_" + key + "_" + target)
        for row, prior in zip(other["profiles"],first["profiles"]):
            for key in ("scene","rate","render_enabled","depth",
                        "frames","control_hash"):
                need(row[key] == prior[key],
                     "SOURCE_CONTROL_DRIFT_" + target + "_" + key)
    # Compare Float32 beam hashes ONLY within target via the executable
    # direct oracle, never require an ARM32 vs x86 Float32 bitwise match.


def self_test() -> None:
    frozen()
    rows=[{"scene": scene, "rate": rate, "depth": depth,
           "render_enabled": render, "frames": 24,
           "control_hash": "0123456789abcdef", "bf_hash": "fedcba9876543210"}
          for scene in ("C1_BASELINE","C2_ULA","C4_ULA","C4_UCA")
          for rate in (16000,32000,48000) for depth in (2,4)
          for render in (0,1)]
    valid = {
        "schema_version": 1, "decision": DECISION,
        "source_role": "first-party-synthetic",
        "real_pthread_source_owners": True,
        "capture_bf_continuity_software": True,
        "source_absence_physical_verified": False,
        "apx3_recording_qualified": False,
        "device_qualified": False,
        "public_sdk_installed": False,
        "profiles": rows, "profile_count": 48, "negative_checks": 600,
        "control_digest": "0123456789abcdef",
    }
    check_targets({target: valid for target in TARGETS})
    n = 0
    for field, invalid in (
        ("schema_version",2), ("decision",FAILURE),
        ("source_role","genuine-device-source"),
        ("real_pthread_source_owners",False),
        ("capture_bf_continuity_software",False),
        ("source_absence_physical_verified",True),
        ("apx3_recording_qualified",True),
        ("device_qualified",True), ("public_sdk_installed",True),
        ("profile_count",47), ("negative_checks",599),
        ("control_digest","bad"),
    ):
        bad=json.loads(json.dumps(valid))
        bad[field]=invalid
        try: check_result(bad)
        except Denied: n+=1
        else: raise Denied("FALSE_SPSC_ADMISSION_"+field)
    for field, invalid in (
        ("scene","C3"),("rate",24000),("render_enabled",2),
        ("depth",8),("frames",23),("control_hash","bad"),
        ("bf_hash","bad")
    ):
        bad=json.loads(json.dumps(valid))
        bad["profiles"][0][field]=invalid
        try: check_result(bad)
        except Denied: n+=1
        else: raise Denied("INVALID_OWNER_MATRIX_ACCEPTED_"+field)
    need(n==19, "NEGATIVE_SELF_TEST_NOT_ACTUAL")
    other=json.loads(json.dumps(valid))
    other["profiles"][0]["bf_hash"]="abcdef0123456789"
    check_targets({"native":valid,"sanitized":other,"arm":other,"tsan":other})
    print("FE09_B1S0_SOURCE_OWNER_CONTRACT_SELFTEST_OK controls=19")


def verify_output(output: Path, commit: str) -> None:
    need(output.is_dir() and {x.name for x in output.iterdir()} ==
         set(MEMBERS), "ARTIFACT_SCHEMA_CHANGED")
    for name in MEMBERS:
        file=output/name
        cap=(1024 if name=="SHA256SUMS" else
             262144 if name=="receipt.json" else
             2097152 if name=="collect.log" else 256)
        need(file.is_file() and not file.is_symlink() and
             0<file.stat().st_size<=cap,"OVERSIZE_OR_MISSING_"+name)
    manifest="".join(f"{file_sha(output / name)}  {name}\n"
                     for name in ("receipt.json","collect.log","verify.log"))
    need((output/"SHA256SUMS").read_text("ascii")==manifest,
         "ARTIFACT_MEMBER_SHA256_MISMATCH")
    receipt=tools.strict_json((output/"receipt.json").read_text("utf-8"))
    for key,value in identity(commit).items():
        need(receipt.get(key)==value,
             "IMMUTABLE_SOURCE_IDENTITY_CHANGED_"+key)
    need(receipt.get("decision")==DECISION and
         receipt.get("qualified_after_actual_four_target_execution") is True and
         receipt.get("target_order")==list(TARGETS) and
         receipt.get("source_clock_known") is False and
         receipt.get("real_source_absence_physical_qualified") is False and
         receipt.get("apx3_recorder_qualified") is False and
         receipt.get("no_cryptographic_source_auth") is True and
         receipt.get("ssc305_device_qualified") is False and
         receipt.get("public_sdk_installed") is False,
         "FALSE_PHYSICAL_OR_APX3_AUTHORITY")
    binary=receipt.get("binary_sha256")
    compiler=receipt.get("compiler_versions")
    need(type(binary) is dict and set(binary)==set(TARGETS) and
         all(type(x) is str and re.fullmatch(r"[0-9a-f]{64}",x)
             for x in binary.values()) and
         type(compiler) is dict and set(compiler)==set(TARGETS) and
         all(type(x) is str and bool(x) for x in compiler.values()),
         "COMPILER_OR_ELF_IDENTITY_NOT_ATTESTED")
    check_targets(receipt.get("target_results"))
    need((output/"verify.log").read_text("ascii") ==
         "FE09_T2B_B1S0_FIRST_PARTY_SOURCE_QUALIFIED\n",
         "SOURCE_VERIFY_MARKER_DRIFT")


def collect(output: Path, commit: str) -> None:
    need(not output.exists(), "REFUSE_OVERWRITE_PREVIOUS_EVIDENCE")
    need(tools.source_head()==commit, "EXECUTING_SOURCE_DIFFERS")
    receipt=identity(commit)
    receipt["decision"]=FAILURE
    receipt["qualified_after_actual_four_target_execution"]=False
    logs: list[str] = []
    output.mkdir(parents=True)
    try:
        targets,versions,binaries={}, {}, {}
        with tempfile.TemporaryDirectory(prefix="fe09-b1s0-") as temp:
            work=Path(temp)
            hdr=work/"include/audio_pipeline/audio_pipeline_build.h"
            hdr.parent.mkdir(parents=True)
            hdr.write_text(
                "#ifndef AUDIO_PIPELINE_AUDIO_PIPELINE_BUILD_H\n"
                "#define AUDIO_PIPELINE_AUDIO_PIPELINE_BUILD_H\n"
                "#define AP_BUILD_RESAMPLER_BANDLIMITED 1\n"
                "#endif\n",encoding="ascii")
            for target in TARGETS:
                compiler="arm-linux-gnueabihf-gcc" if target=="arm" else "cc"
                need(shutil.which(compiler) is not None,
                     "COMPILER_NOT_AVAILABLE_"+target)
                versions[target]=tools.run([compiler,"--version"],logs).splitlines()[0]
                flags=[compiler,"-std=c11","-Wall","-Wextra","-Werror",
                       "-O2","-ffp-contract=off","-fno-fast-math","-pthread",
                       "-DAP_BUILD_RESAMPLER_BANDLIMITED=1",
                       "-I"+str(work/"include"),"-I"+str(ROOT/"src"),
                       "-I"+str(HERE)]
                if target=="sanitized":
                    flags+=["-O1","-g","-fsanitize=address,undefined",
                            "-fno-omit-frame-pointer"]
                if target=="tsan":
                    flags+=["-O1","-g","-fsanitize=thread",
                            "-fno-omit-frame-pointer"]
                if target=="arm":
                    flags+=["-march=armv7-a","-mfpu=neon-vfpv4",
                            "-mfloat-abi=hard"]
                objects=[]
                for idx,src in enumerate(SOURCES):
                    obj=work/f"{target}-{idx}.o"
                    warns=([] if src in (b0.b1.SOURCE_C,b0.b1.ARRAY_C)
                           else ["-Wconversion","-Wshadow","-Wpedantic"])
                    tools.run(flags+warns+["-c",str(src),"-o",str(obj)],
                              logs,timeout=120)
                    objects.append(str(obj))
                elf=work/(target+".elf")
                link=[compiler,*objects,"-pthread","-lm","-o",str(elf)]
                if target=="sanitized": link+=["-fsanitize=address,undefined"]
                if target=="tsan": link+=["-fsanitize=thread"]
                if target=="arm":
                    link+=["-march=armv7-a","-mfpu=neon-vfpv4",
                           "-mfloat-abi=hard"]
                tools.run(link,logs,timeout=120)
                binaries[target]=file_sha(elf)
                command=[str(elf)]
                if target=="arm":
                    need(shutil.which("qemu-arm") is not None and
                         Path("/usr/arm-linux-gnueabihf").is_dir(),
                         "ARM32_CROSS_TOOLCHAIN_OR_QEMU_MISSING")
                    command=["qemu-arm","-L","/usr/arm-linux-gnueabihf",str(elf)]
                env=dict(os.environ)
                if target=="sanitized":
                    env.update({"ASAN_OPTIONS":"detect_leaks=0:halt_on_error=1",
                                "UBSAN_OPTIONS":"halt_on_error=1"})
                if target=="tsan":
                    env.update({"TSAN_OPTIONS":"halt_on_error=1:exitcode=66"})
                first=tools.strict_json(tools.run(command,logs,timeout=180,env=env))
                second=tools.strict_json(tools.run(command,logs,timeout=180,env=env))
                need(first==second,"REEXECUTION_NONDETERMINISTIC_"+target)
                check_result(first)
                targets[target]=first
        check_targets(targets)
        receipt.update({
            "decision": DECISION,
            "qualified_after_actual_four_target_execution": True,
            "target_order":list(TARGETS),
            "target_results":targets,
            "compiler_versions":versions,
            "binary_sha256":binaries,
            "source_clock_known": False,
            "real_source_absence_physical_qualified": False,
        })
    except Exception as error:
        receipt["decision"]=FAILURE
        receipt["qualified_after_actual_four_target_execution"]=False
        receipt["failure_type"]=type(error).__name__
        receipt["failure_code"]=str(error)[:200]
        import sys
        print("FE09_B1S0_FAILURE_LOG_TAIL_BEGIN",file=sys.stderr)
        print("\n".join(logs[-8:])[-5000:],file=sys.stderr)
        print("FE09_B1S0_FAILURE_LOG_TAIL_END",file=sys.stderr)
        raise
    finally:
        (output/"receipt.json").write_text(
            json.dumps(receipt,sort_keys=True,separators=(",",":"),
                       allow_nan=False)+"\n",encoding="utf-8")
        (output/"collect.log").write_text("\n".join(logs)+"\n",
                                           encoding="utf-8")
        (output/"verify.log").write_text(
            ("FE09_T2B_B1S0_FIRST_PARTY_SOURCE_QUALIFIED\n"
             if receipt.get("decision")==DECISION else FAILURE+"\n"),
            encoding="ascii")
        (output/"SHA256SUMS").write_text(
            "".join(f"{file_sha(output/n)}  {n}\n" for n in (
                "receipt.json","collect.log","verify.log")),encoding="ascii")
    verify_output(output,commit)


def main() -> None:
    parser=argparse.ArgumentParser(description=__doc__)
    mode=parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--self-test",action="store_true")
    mode.add_argument("--collect",action="store_true")
    mode.add_argument("--verify",action="store_true")
    parser.add_argument("--output",type=Path)
    parser.add_argument("--execution-source")
    args=parser.parse_args()
    try:
        if args.self_test: self_test()
        else:
            need(args.output is not None and
                 re.fullmatch(r"[a-f0-9]{40}",args.execution_source or "")
                 is not None,"EXACT_SOURCE_OR_OUTPUT_MISSING")
            need(tools.source_head()==args.execution_source,
                 "RUNNING_SOURCE_HEAD_MISMATCH")
            if args.collect: collect(args.output,args.execution_source)
            else:
                verify_output(args.output,args.execution_source)
                print("FE09_T2B_B1S0_FIRST_PARTY_SOURCE_QUALIFIED")
    except (Denied,tools.GateFailure,ValueError,OSError,
            subprocess.CalledProcessError) as error:
        raise SystemExit(FAILURE+": "+str(error)) from None


if __name__=="__main__":
    main()
