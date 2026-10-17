#!/usr/bin/env python3
"""#789: exact-C original S2/BF/SPSC two-slot evidence, not SSC305 or durable I/O.

Four real compiler/sanitizer/ARM32-QEMU executions twice each, pinned frozen
first-party source, canonical run-specific four-member GitHub Artifact.
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

import fe09_b2s3_t3s0_resource_census_qualification as s0

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
BASE = "e85a14540f2c49456508387fe3f815a90308c1ba"
DECISION = "FE09_T3S1_TWO_SLOT_SOURCE_BF_HANDOFF_RESEARCH_ONLY"
FAILURE = "FE09_T3S1_COMPACT_HANDOFF_EVIDENCE_NOT_ADMITTED"
MARKER = "FE09_T3S1_EXACT_SOURCE_COMPACT_OUTBOARD_HANDOFF_VERIFIED\n"
TARGETS = ("native", "sanitized", "arm", "tsan")
MEMBERS = ("SHA256SUMS", "receipt.json", "collect.log", "verify.log")
IMPL_C = HERE / "fe09_b2s3_t3s1_compact_handoff.c"
IMPL_H = HERE / "fe09_b2s3_t3s1_compact_handoff.h"
TEST_C = HERE / "fe09_b2s3_t3s1_compact_handoff_test.c"
OWN = (IMPL_C, IMPL_H, TEST_C, Path(__file__).resolve())
FROZEN = tuple(dict.fromkeys((*s0.FROZEN, *s0.OWN,
                 HERE / "FE09_T3S0_COMPILED_MEMORY_CENSUS.md")))
SOURCES = (*s0.SOURCES[:-1], IMPL_C, TEST_C)
FALSE = ("complete_device_memory_qualified", "physical_ssc305_qualified",
         "durable_rolling_recorder_qualified", "public_sdk_installed",
         "archive_power_loss_safe")
SCENES = ("C1_BASELINE", "C2_ULA", "C4_ULA", "C4_UCA")
KEYS = ("scene", "rate", "render", "slots", "source_depth", "control_bytes",
        "slot_bytes", "stage_owned_bytes", "dual_stage_owned_bytes",
        "outboard_accounted_bytes", "stack_scratch_min",
        "apx3_one_frame", "source_processed", "negative_checks")

class NotAdmitted(ValueError):
    pass

def need(ok: object, why: str) -> None:
    if not ok:
        raise NotAdmitted(why)

def digest(p: Path) -> str:
    need(p.is_file() and not p.is_symlink() and
         0 < p.stat().st_size < 16*1024*1024,
         "MISSING_OR_OVERSIZED_" + p.name)
    return hashlib.sha256(p.read_bytes()).hexdigest()

def pins() -> dict[str, str]:
    need(s0.BASE == "40581c71c07d4a9de8073c2f73a5d0f2293a3e1f",
         "S0_PREDECESSOR_REWRITTEN")
    s0.pins()
    result: dict[str, str] = {}
    for p in FROZEN:
        rel = p.relative_to(ROOT).as_posix()
        exact = subprocess.check_output([
            "git", "-c", "safe.directory=" + str(ROOT),
            "show", BASE + ":" + rel], cwd=ROOT, timeout=30)
        need(0 < len(exact) < 16*1024*1024 and
             hashlib.sha256(exact).hexdigest() == digest(p),
             "IMMUTABLE_PREDECESSOR_CHANGED_" + rel)
        result[rel] = hashlib.sha256(exact).hexdigest()
    return result

def verify_result(obj: dict) -> None:
    need(type(obj) is dict and set(obj) ==
         {"schema_version", "decision", "source_role", *FALSE,
          "profile_rows", "profile_count", "negative_checks"},
         "SCHEMA_OR_EXTRA_PRODUCT_CLAIM")
    need(obj["schema_version"] == 1 and obj["decision"] == DECISION and
         obj["source_role"] == "first-party-synthetic" and
         all(obj[k] is False for k in FALSE) and
         type(obj["profile_count"]) is int and obj["profile_count"] == 48 and
         type(obj["negative_checks"]) is int and
         obj["negative_checks"] >= 500,
         "FALSE_DEVICE_OR_MISSING_INDEPENDENT_EXECUTIONS")
    rows = obj["profile_rows"]
    need(type(rows) is list and len(rows) == 48, "MISSING_PROFILE_ROWS")
    expected = [(sc, rate, render, slots) for sc in SCENES
                for rate in (16000, 32000, 48000)
                for render in (0, 1) for slots in (1, 2)]
    total = 0
    seen: dict[tuple, dict] = {}
    for row, (sc, rate, render, slots) in zip(rows, expected):
        need(type(row) is dict and set(row) == set(KEYS) and
             row["scene"] == sc and row["rate"] == rate and
             row["render"] == render and row["slots"] == slots and
             all(type(row[k]) is int for k in KEYS if k != "scene"),
             "SOURCE_GEOMETRY_OR_INTEGER_TYPE_DRIFT")
        need(row["source_depth"] == (2 if slots == 1 else 4) and
             row["slot_bytes"] == 5324 and
             100 <= row["control_bytes"] <= 2048 and
             row["stage_owned_bytes"] ==
               row["control_bytes"] + slots*row["slot_bytes"] and
             row["dual_stage_owned_bytes"] == 2*row["stage_owned_bytes"] and
             row["outboard_accounted_bytes"] > 0 and
             row["stack_scratch_min"] == 5120 and
             160 < row["apx3_one_frame"] <= 5120 and
             row["source_processed"] == 8+slots and
             row["negative_checks"] >= 10,
             "INVENTED_COMPACT_MEMORY_OR_LOST_SOURCE_FRAME")
        total += row["negative_checks"]
        key = (sc, rate, render)
        if key in seen:
            prev = seen[key]
            need(row["stage_owned_bytes"]-prev["stage_owned_bytes"] == 5324
                 and row["control_bytes"] == prev["control_bytes"]
                 and row["apx3_one_frame"] == prev["apx3_one_frame"],
                 "HIDDEN_SECOND_PHYSICAL_BUFFER")
        else:
            seen[key] = row
    need(total == obj["negative_checks"], "NEGATIVE_ACCOUNTING_FAKE")

def check_targets(results: dict) -> None:
    need(type(results) is dict and set(results) == set(TARGETS),
         "NATIVE_ASAN_ARM_TSAN_NOT_COMPLETE")
    for target, x in results.items():
        verify_result(x)
        n = results["native"]
        need(x["decision"] == n["decision"] and
             x["source_role"] == n["source_role"] and
             x["profile_count"] == n["profile_count"] and
             all(x[k] is False for k in FALSE), "CROSS_TARGET_POLICY_DRIFT")
        for row, original in zip(x["profile_rows"], n["profile_rows"]):
            for key in ("scene", "rate", "render", "slots", "source_depth",
                        "slot_bytes", "stack_scratch_min", "apx3_one_frame",
                        "source_processed"):
                need(row[key] == original[key],
                     "CROSS_ISA_PROTOCOL_DRIFT_" + target + "_" + key)
        # Compiled control padding and ABI sizes can differ across ISAs.

def self_test() -> None:
    pins()
    rows = []
    for sc in SCENES:
        for rate in (16000, 32000, 48000):
            for render in (0, 1):
                for slots in (1, 2):
                    rows.append(dict(scene=sc, rate=rate, render=render,
                         slots=slots, source_depth=2 if slots == 1 else 4,
                         control_bytes=176, slot_bytes=5324,
                         stage_owned_bytes=176+slots*5324,
                         dual_stage_owned_bytes=2*(176+slots*5324),
                         outboard_accounted_bytes=20000,
                         stack_scratch_min=5120, apx3_one_frame=500,
                         source_processed=8+slots, negative_checks=20))
    good = {"schema_version": 1, "decision": DECISION,
            "source_role": "first-party-synthetic",
            **{k: False for k in FALSE}, "profile_rows": rows,
            "profile_count": 48, "negative_checks": 960}
    check_targets({target: good for target in TARGETS})
    mutations = [("decision", FAILURE), ("source_role", "hardware"),
                 ("profile_count", 47), ("negative_checks", 1),
                 *[(x, True) for x in FALSE]]
    failures = 0
    for key, bad in mutations:
        trial = json.loads(json.dumps(good))
        trial[key] = bad
        try:
            verify_result(trial)
        except NotAdmitted:
            failures += 1
        else:
            raise NotAdmitted("FALSE_AUTHORITY_SELFTEST_" + key)
    for key, bad in (("scene", "C3"), ("rate", 24000),
                     ("render", 2), ("slots", 24), ("slot_bytes", 999),
                     ("control_bytes", 0), ("stage_owned_bytes", 1),
                     ("dual_stage_owned_bytes", 1),
                     ("outboard_accounted_bytes", 0),
                     ("source_depth", 4), ("stack_scratch_min", 0),
                     ("source_processed", 0), ("apx3_one_frame", 6000),
                     ("negative_checks", 0)):
        trial = json.loads(json.dumps(good))
        trial["profile_rows"][0][key] = bad
        try:
            verify_result(trial)
        except NotAdmitted:
            failures += 1
        else:
            raise NotAdmitted("FALSE_SLOT_SELFTEST_" + key)
    need(failures == len(mutations)+14, "NEGATIVE_SELFTEST_SKIPPED")
    print("FE09_T3S1_SELFTEST_PASS", failures)

def identity(sha: str) -> dict:
    need(type(sha) is str and re.fullmatch(r"[a-f0-9]{40}", sha),
         "NOT_AN_IMMUTABLE_SOURCE_COMMIT")
    return {
        "schema_version": 1,
        "stage": "FE09_S3_T3_S1_NONINSTALLED_EXACT_TWO_SLOT_HANDOFF",
        "preregistration": "https://github.com/jiying2007/audio-pipeline/issues/789",
        "source_commit": sha,
        "protected_predecessor_main": BASE,
        "protected_predecessor_verify": 39052067322,
        "protected_predecessor_release": 39054626943,
        "source_role": "first-party-synthetic",
        "immutable_predecessor_sha256": pins(),
        "own_source_sha256": {
            p.relative_to(ROOT).as_posix(): digest(p) for p in OWN},
        "device_memory_admitted": False,
        "process_rss_measured": False,
        "stack_highwater_measured": False,
        "physical_adc_dac_clocks_measured": False,
        "powerloss_safe": False,
        "outboard_sink_bytes_excluded_from_stage": True,
        "public_sdk_installed": False,
        "shipping_dsp_changed": False,
    }

def verify_output(output: Path, sha: str) -> None:
    caps = {"SHA256SUMS": 512, "receipt.json": 262144,
            "collect.log": 4194304, "verify.log": 256}
    need(output.is_dir() and not output.is_symlink() and
         {p.name for p in output.iterdir()} == set(MEMBERS),
         "MISSING_OR_EXTRA_ARTIFACT_MEMBER")
    for name in MEMBERS:
        p = output/name
        need(p.is_file() and not p.is_symlink() and
             0 < p.stat().st_size <= caps[name], "ARTIFACT_SIZE_" + name)
    manifest = "".join(f"{digest(output/n)}  {n}\n"
        for n in ("receipt.json", "collect.log", "verify.log"))
    need((output/"SHA256SUMS").read_text("ascii") == manifest,
         "MEMBER_SHA256_MISMATCH")
    receipt = s0.tools.strict_json((output/"receipt.json").read_text("utf-8"))
    for key,value in identity(sha).items():
        need(receipt.get(key) == value, "SOURCE_PIN_OR_SHA_DRIFT_" + key)
    need(receipt.get("decision") == DECISION and
         receipt.get("actual_compiled_targets_complete") is True and
         receipt.get("target_order") == list(TARGETS),
         "FALSE_OUTBOARD_SOURCE_QUALIFICATION")
    hashes=receipt.get("binary_sha256")
    versions=receipt.get("compiler_versions")
    need(type(hashes) is dict and set(hashes) == set(TARGETS) and
         all(type(v) is str and re.fullmatch(r"[0-9a-f]{64}", v)
             for v in hashes.values()) and
         type(versions) is dict and set(versions) == set(TARGETS) and
         all(type(v) is str and len(v)>3 for v in versions.values()),
         "REAL_COMPILER_AND_ELF_DIGEST_MISSING")
    check_targets(receipt.get("target_results"))
    need((output/"verify.log").read_text("ascii") == MARKER,
         "INDEPENDENT_READBACK_MARKER_WRONG")

def collect(output: Path, sha: str) -> None:
    need(not output.exists() and not output.is_symlink(),
         "REFUSE_EXISTING_ARTIFACT_OVERWRITE")
    need(s0.tools.source_head() == sha, "HEAD_OR_SOURCE_NOT_PINNED")
    receipt = identity(sha)
    receipt.update(decision=FAILURE, actual_compiled_targets_complete=False)
    logs: list[str] = []
    output.mkdir(parents=True)
    try:
        targets,versions,binaries = {},{},{}
        with tempfile.TemporaryDirectory(prefix="fe09-t3s1-") as tmp:
            wd=Path(tmp)
            header=wd/"include/audio_pipeline/audio_pipeline_build.h"
            header.parent.mkdir(parents=True)
            header.write_text("#ifndef AUDIO_PIPELINE_AUDIO_PIPELINE_BUILD_H\n"
                "#define AUDIO_PIPELINE_AUDIO_PIPELINE_BUILD_H\n"
                "#define AP_BUILD_RESAMPLER_BANDLIMITED 1\n#endif\n",
                encoding="ascii")
            for target in TARGETS:
                compiler=("arm-linux-gnueabihf-gcc" if target=="arm" else "cc")
                need(shutil.which(compiler) is not None,
                     "MISSING_TARGET_" + target)
                versions[target]=s0.tools.run([compiler,"--version"],logs
                    ).splitlines()[0]
                flags=[compiler,"-std=c11","-Wall","-Wextra","-Werror",
                       "-O2","-ffp-contract=off","-fno-fast-math","-pthread",
                       "-DAP_BUILD_RESAMPLER_BANDLIMITED=1",
                       "-I"+str(wd/"include"),"-I"+str(ROOT/"src"),
                       "-I"+str(HERE)]
                if target in ("sanitized","tsan"):
                    flags+=["-O1","-g","-fsanitize=thread" if target=="tsan"
                            else "-fsanitize=address,undefined",
                            "-fno-omit-frame-pointer"]
                if target=="arm":
                    flags+=["-march=armv7-a","-mfpu=neon-vfpv4",
                            "-mfloat-abi=hard"]
                objs=[]
                for i,source in enumerate(SOURCES):
                    obj=wd/f"{target}-{i}.o"
                    exempt=(s0.c0.b1.b1.b0.b1.SOURCE_C,
                            s0.c0.b1.b1.b0.b1.ARRAY_C)
                    warnings=([] if source in exempt else
                              ["-Wconversion","-Wshadow","-Wpedantic"])
                    s0.tools.run(flags+warnings+
                          ["-c",str(source),"-o",str(obj)],logs,timeout=120)
                    objs.append(str(obj))
                binary=wd/(target+".elf")
                link=[compiler,*objs,"-pthread","-lm","-o",str(binary)]
                if target=="sanitized":link.append("-fsanitize=address,undefined")
                if target=="tsan":link.append("-fsanitize=thread")
                if target=="arm":
                    link+=["-march=armv7-a","-mfpu=neon-vfpv4",
                           "-mfloat-abi=hard"]
                s0.tools.run(link,logs,timeout=120)
                binaries[target]=digest(binary)
                command=[str(binary)]
                if target=="arm":
                    need(shutil.which("qemu-arm") is not None and
                         Path("/usr/arm-linux-gnueabihf").is_dir(),
                         "ARM32_QEMU_NOT_PRESENT")
                    command=["qemu-arm","-L","/usr/arm-linux-gnueabihf",
                             str(binary)]
                env=dict(os.environ)
                if target=="sanitized":
                    env.update({"ASAN_OPTIONS":"detect_leaks=0:halt_on_error=1",
                                "UBSAN_OPTIONS":"halt_on_error=1"})
                if target=="tsan":
                    env.update({"TSAN_OPTIONS":"halt_on_error=1:exitcode=66"})
                first=s0.tools.strict_json(s0.tools.run(
                    command,logs,timeout=180,env=env))
                repeat=s0.tools.strict_json(s0.tools.run(
                    command,logs,timeout=180,env=env))
                need(first==repeat,"SOURCE_EXACT_TWO_RUN_DRIFT_"+target)
                verify_result(first)
                targets[target]=first
        check_targets(targets)
        receipt.update(decision=DECISION, actual_compiled_targets_complete=True,
                       target_order=list(TARGETS),target_results=targets,
                       compiler_versions=versions,binary_sha256=binaries)
    except Exception as exc:
        receipt.update(decision=FAILURE,actual_compiled_targets_complete=False,
                       failure_type=type(exc).__name__,
                       failure_code=str(exc)[:250])
        import sys
        print("FE09_T3S1_ORIGINAL_FAILURE_LOG_BEGIN",file=sys.stderr)
        print("\n".join(logs[-10:])[-5000:],file=sys.stderr)
        print("FE09_T3S1_ORIGINAL_FAILURE_LOG_END",file=sys.stderr)
        raise
    finally:
        (output/"receipt.json").write_text(json.dumps(
            receipt,sort_keys=True,separators=(",",":"),allow_nan=False)+"\n",
            encoding="utf-8")
        (output/"collect.log").write_text("\n".join(logs)+"\n",
                                          encoding="utf-8")
        (output/"verify.log").write_text(
            MARKER if receipt.get("decision")==DECISION else FAILURE+"\n",
            encoding="ascii")
        (output/"SHA256SUMS").write_text(
            "".join(f"{digest(output/name)}  {name}\n" for name in
                ("receipt.json","collect.log","verify.log")),encoding="ascii")
    verify_output(output,sha)

def main() -> None:
    p=argparse.ArgumentParser(description=__doc__)
    modes=p.add_mutually_exclusive_group(required=True)
    for mode in ("self-test","collect","verify"):
        modes.add_argument("--"+mode,action="store_true")
    p.add_argument("--output",type=Path)
    p.add_argument("--execution-source")
    args=p.parse_args()
    try:
        if args.self_test:
            self_test()
        else:
            need(args.output is not None and type(args.execution_source) is str
                 and re.fullmatch(r"[0-9a-f]{40}",args.execution_source),
                 "MISSING_EXACT_SHA_AND_OUTPUT")
            need(s0.tools.source_head()==args.execution_source,
                 "SOURCE_COMMIT_CHANGED")
            if args.collect:collect(args.output,args.execution_source)
            else:
                verify_output(args.output,args.execution_source)
                print(MARKER.strip())
    except (NotAdmitted,s0.NotAdmitted,s0.tools.GateFailure,OSError,
            subprocess.CalledProcessError,ValueError) as exc:
        raise SystemExit(FAILURE+": "+str(exc)) from None

if __name__=="__main__":
    main()
