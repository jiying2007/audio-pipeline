#!/usr/bin/env python3
"""Independent R2 forward-source B3 CALL resource measurements. No device qualification."""
from __future__ import annotations

import argparse
from collections import Counter
import copy
import datetime as dt
import gzip
import io
import json
import math
import os
from pathlib import Path
import re
import shlex
import shutil
import signal
import struct
import subprocess
import sys
import tempfile
import time

import fe09_b3_f0_qualification as original
import fe09_b3_f0_r2_source_admission as forward_source

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
DOCS = ROOT / "docs/research/frontend-evolution-v1/FE09_T3S3_F0_RESOURCE_PREREGISTRATION_20261024"
IDENTITY = "FE09-T3S3-F0-ACTUAL-CALL-RESOURCE-FORWARD-SOURCE-R2"
BASE = "5187c5e59526d4047b3965b44c770ab21edbde9f"
CONTRACT_SHA = "42496ab0f6f01d5b36f03d23f670f585a5f57c120ecf9fc0237a27d5aa2f34f2"
LOCK_SHA = "16cd84381647bef1015fc8ef338bb9b10dd09ce4669248355ac4f48745d8a4ff"
IMAGE = "ghcr.io/jiying2007/audio-pipeline-ci@sha256:69d38c66e09885b78eb3abba3f8b7dcc92363b71430dc39fc7f74978ffae2e57"
DECISION = "FE09_T3S3_F0_FORWARD_SOURCE_R2_ACTUAL_CALL_RESOURCE_NO_DEVICE_PROMOTION"
PARTIAL = "FE09_T3S3_F0_FORWARD_SOURCE_R2_LOCAL_PARTIAL_NO_PROMOTION"
FAILED = "FE09_T3S3_F0_FORWARD_SOURCE_R2_RESOURCE_REJECTED_WITH_EVIDENCE"
TARGETS = ["native", "sanitized", "arm"]
WRAPS = {"fe_b3_f0_bind", "fe_b3_f0_process_one", "fe_b1s0_capture_submit",
         "fe_b1s0_render_present", "fe_b1s0_render_absent"}
BUILD_ENV_INPUTS = ("CFLAGS", "CPPFLAGS", "CXXFLAGS", "LDFLAGS", "ARFLAGS", "ASFLAGS",
                    "LIBRARY_PATH", "LD_LIBRARY_PATH", "LD_PRELOAD", "CPATH", "C_INCLUDE_PATH",
                    "CPLUS_INCLUDE_PATH", "OBJC_INCLUDE_PATH", "CMAKE_PREFIX_PATH",
                    "CMAKE_TOOLCHAIN_FILE", "CMAKE_GENERATOR", "CMAKE_ARGS", "CC", "CXX", "AR",
                    "NM", "RANLIB", "SDKROOT", "COMPILER_PATH", "GCC_EXEC_PREFIX")
PRIVATE_ENV_INPUTS = ("GH_READ_TOKEN", "GITHUB_TOKEN", "GH_TOKEN")
RUNTIME_ENV = {"ASAN_OPTIONS": "detect_leaks=1:abort_on_error=1",
               "UBSAN_OPTIONS": "halt_on_error=1:print_stacktrace=1"}
LIBRARY_SOURCES = ["src/" + p for p in (
    "ap_build_info.c", "core/ap_pipeline.c", "core/ap_pipeline_query.c",
    "frontend/ap_resampler.c", "frontend/ap_hpf.c", "frontend/ap_beamformer.c",
    "sync/ap_sync.c", "activity/ap_activity.c", "enhance/ap_res.c", "enhance/ap_ns.c",
    "enhance/ap_noise_tracker.c", "enhance/ap_window.c", "enhance/ap_agc.c", "enhance/ap_vad.c",
    "aec/ap_aec_mdf.c", "arch/scalar/ap_kernels_scalar.c", "dsp/ap_fft.c",
    "modules/ap_resampler_module.c", "modules/ap_hpf_module.c", "modules/ap_beamformer_module.c",
    "modules/ap_sync_module.c", "modules/ap_activity_module.c", "modules/ap_res_module.c",
    "modules/ap_ns_module.c", "modules/ap_agc_module.c", "modules/ap_vad_module.c", "modules/ap_aec_module.c")]
SHARED_SOURCES = ["tests/validation/frontend_evolution/" + p for p in (
    "array_native.c", "fe09_b1b0_src.c", "fe09_b2s3_t2b_b0_capture_only.c",
    "fe09_b2s3_t2b_b1s0_owner_spsc.c", "fe09_b3_f0_composition.c", "fe09_b3_f0_observer.c")]
DEFINITIONS = ["-D" + p + "=1" for p in (
    "AP_BUILD_ACTIVITY", "AP_BUILD_AEC_MDF", "AP_BUILD_BF_DIRECTION_TRACKING",
    "AP_BUILD_NS_EMA", "AP_BUILD_RESAMPLER_BANDLIMITED", "AP_BUILD_STAGE_AEC", "AP_BUILD_STAGE_AGC",
    "AP_BUILD_STAGE_BF", "AP_BUILD_STAGE_HPF", "AP_BUILD_STAGE_NS", "AP_BUILD_STAGE_RES",
    "AP_BUILD_STAGE_SYNC", "AP_BUILD_STAGE_VAD")]
OWN = [HERE / name for name in ("fe09_t3s3_f0_call_resource_probe.c",
       "fe09_t3s3_f0_call_resource_qualification.py", "fe09_t3s3_f0_build/CMakeLists.txt",
       "fe09_t3s3_f0_call_resource_r2_qualification.py",
       "fe09_b3_f0_r2_source_admission.py")]
need, digest, loads = original.need, original.digest, original.loads
read_json, write_json = original.read_json, original.write_json
Rejected = original.Rejected


def contract() -> dict:
    data = (DOCS / "test-contract.json").read_bytes()
    need(digest(data) == CONTRACT_SHA, "FROZEN_RESOURCE_CONTRACT_DRIFT")
    need(digest((DOCS / "source-lock.json").read_bytes()) == LOCK_SHA,
         "FROZEN_RESOURCE_SOURCE_LOCK_DRIFT")
    return loads(data)


def schedule() -> list[dict]:
    return [{"name": f"{case}-{repeat}-{variant}", "case": case, "repeat": repeat,
             "variant": variant, "mode": "adapter", "observed": False,
             "future": False, "negatives": False}
            for case in ("ALL_P", "PAP") for repeat in range(1, 4)
            for variant in ("reference", "measured")]


def file_identity(path: Path) -> dict:
    need(path.is_file() and not path.is_symlink(), "REGULAR_SOURCE_REQUIRED:" + str(path))
    data = path.read_bytes()
    return {"path": str(path.relative_to(ROOT)), "bytes": len(data), "sha256": digest(data)}


def check_locked_rows(rows: list[dict], exceptions: dict[str, str]) -> None:
    """Strict F0 88-member historical lock plus the exact R2 forward delta.

    Source preflight already verified the entire independent 77-member R1
    predecessor. The extra F0-only inputs must remain byte-for-byte original;
    none may self-authorize a new candidate. Every changed build member must
    appear explicitly in the frozen version-specific source list.
    """
    expected = read_json(DOCS / "source-lock.json")["files"]
    need(rows == expected and len(rows) == 88, "F0_R2_ORIGINAL_SOURCE_LOCK_MEMBER_IDENTITY")
    names = {row["path"] for row in rows}
    need(set(exceptions).issubset(names), "F0_R2_FORWARD_MEMBER_MISSING")
    for row in rows:
        original.check_budget()
        path = Path(row["path"])
        need(not path.is_absolute() and ".." not in path.parts, "F0_R2_UNSAFE_LOCK_PATH")
        current = file_identity(ROOT / path)
        if row["path"] in exceptions:
            actual = forward_source.git_blob((ROOT / path).read_bytes())
            need(actual == exceptions[row["path"]],
                 "F0_R2_UNREGISTERED_SOURCE_DRIFT:" + str(path))
        else:
            need(all(current[k] == row[k] for k in current),
                 "F0_R2_ORIGINAL_SOURCE_DRIFT:" + str(path))


def source_record(source: str, require_committed: bool = True) -> dict:
    contract()
    need(bool(re.fullmatch(r"[0-9a-f]{40}", source)) and original.git("rev-parse", "HEAD") == source,
         "F0_R2_EXECUTION_SOURCE_NOT_CURRENT_HEAD")
    original.git("merge-base", "--is-ancestor", BASE, source)
    admitted = forward_source.source_check(source)
    version = admitted["candidate_version"]
    need(admitted["status"] == "R2_T1_EXACT_SOURCE_IDENTITY_VERIFIED_NO_DSP_EXECUTION" and
         version in ("2.3.57", "2.3.58") and admitted["source_gated_members"] == 66 and
         admitted["source_gated_exceptions"] == (2 if version == "2.3.57" else 4),
         "F0_R2_FORWARD_SOURCE_NOT_ADMITTED")
    lock = read_json(DOCS / "source-lock.json")
    need(lock["baseline"] == BASE and lock["file_count"] == len(lock["files"]) == 88,
         "F0_R2_FROZEN_SOURCE_MEMBERS")
    exceptions = forward_source.SOURCE_PROFILES[version]
    check_locked_rows(lock["files"], exceptions)
    paths = OWN + sorted(p for p in DOCS.iterdir() if p.is_file()) + [
        ROOT / ".github/workflows/quality.yml",
        ROOT / ".github/scripts/verify-docs-gate.sh",
        ROOT / "docs/research/frontend-evolution-v1/FE09_B3_F0_FORWARD_SOURCE_R2_20261025/PREREGISTRATION.json",
        ROOT / "docs/research/frontend-evolution-v1/FE09_B3_F0_FORWARD_SOURCE_R2_20261025/T2_EXECUTOR_SOURCE_REVIEW.json",
        HERE / "fe09_b3_f0_r2_t2_derivation_contract.py"]
    if require_committed:
        need(not original.git("diff", "--name-only", "HEAD"), "F0_R2_DIRTY_EXECUTION_WORKTREE")
        for path in paths:
            committed = original.read_command(["git", "-c", f"safe.directory={ROOT}",
                                      "show", source + ":" + str(path.relative_to(ROOT))])
            need(committed == path.read_bytes(), "F0_R2_UNCOMMITTED_EXECUTION_INPUT:" + str(path))
    return {"execution_source": source,
            "execution_tree": original.git("rev-parse", "HEAD^{tree}"),
            "baseline": BASE, "source_lock_sha256": LOCK_SHA,
            "contract_sha256": CONTRACT_SHA, "original_files": lock["files"],
            "forward_source_admission": admitted,
            "forward_exception_members": exceptions,
            "historical_f0_lock_member_count": 88,
            "r1_f0_result_inherited": False,
            "measurement_files": [file_identity(p) for p in paths]}

def predecessor() -> dict:
    p = DOCS / "EXECUTION_BASELINE.json"
    need(p.is_file(), "QUALIFIED_BASELINE_RECEIPT_REQUIRED")
    data = read_json(p)
    need(data["baseline"] == BASE and data["toolchain_image"] == IMAGE,
         "BASELINE_OR_IMAGE_IDENTITY")
    for kind in ("verify", "release"):
        row = data[kind]
        need(row["head_sha"] == BASE and row["conclusion"] == "success" and
             type(row["run_id"]) is int and row["run_id"] > 0 and
             type(row["attempt"]) is int and row["attempt"] > 0,
             "INDEPENDENT_BASELINE_GATE:" + kind)
    need(data["verify"]["summary_app_id"] == 15368 and
         data["release"]["convergence_conclusion"] == "success", "BASELINE_GATE_AUTHORITY")
    return data


def finite(value: object, low: float = 0) -> bool:
    return type(value) in (int, float) and math.isfinite(value) and value >= low


def expected_job(metadata: dict, response: dict, context: dict, stage_started: float) -> dict:
    need(context["kind"] == "github_actions" and
         type(context["run_id"]) is int and context["run_id"] > 0 and
         type(context["run_attempt"]) is int and context["run_attempt"] > 0 and
         bool(re.fullmatch(r"[0-9a-f]{40}", context["event_head"])), "JOB_API_CONTEXT")
    endpoint = ("https://api.github.com/repos/jiying2007/audio-pipeline/actions/runs/"
                f"{context['run_id']}/attempts/{context['run_attempt']}/jobs?per_page=100")
    need(type(metadata["schema_version"]) is int and metadata["schema_version"] == 1 and
         metadata["repository"] == "jiying2007/audio-pipeline" and
         type(metadata["run_id"]) is int and type(metadata["run_attempt"]) is int and
         metadata["run_id"] == context["run_id"] and metadata["run_attempt"] == context["run_attempt"] and
         metadata["endpoint"] == endpoint and metadata["response_status"] == 200 and
         metadata["api_version"] == "2022-11-28" and
         all(finite(metadata[k]) for k in ("request_started_epoch", "response_observed_epoch")) and
         0 < metadata["request_started_epoch"] <= metadata["response_observed_epoch"] <= stage_started,
         "ORIGINAL_JOB_API_OBSERVATION")
    need(type(response["total_count"]) is int and type(response["jobs"]) is list and
         0 < len(response["jobs"]) == response["total_count"] <= 100,
         "JOB_API_RESPONSE_SHAPE")
    matches = [j for j in response["jobs"] if j.get("name") in
               ("frontend-reference", "quality / frontend-reference") and j.get("status") == "in_progress"]
    need(len(matches) == 1, "ORIGINAL_JOB_API_IDENTITY_NOT_UNIQUE")
    job = matches[0]
    need(type(job["id"]) is int and job["id"] > 0 and
         type(job["run_id"]) is int and type(job["run_attempt"]) is int and
         job["run_id"] == context["run_id"] and job["run_attempt"] == context["run_attempt"] and
         job["head_sha"] == context["event_head"], "ORIGINAL_JOB_API_RUN_IDENTITY")
    started = dt.datetime.fromisoformat(job["started_at"].replace("Z", "+00:00"))
    need(started.tzinfo is not None and 0 < started.timestamp() <= metadata["request_started_epoch"],
         "ORIGINAL_JOB_API_STARTED_AT")
    return {"job_id": job["id"], "job_name": job["name"], "run_id": job["run_id"],
            "run_attempt": job["run_attempt"], "head_sha": job["head_sha"],
            "started_at": job["started_at"], "started_at_epoch": started.timestamp(),
            "observed_at_epoch": metadata["request_started_epoch"], "endpoint": endpoint}


def job_observation(directory: Path, context: dict, stage_started: float) -> dict:
    metadata = read_json(directory / "request.json", 65536)
    path = directory / "jobs.json"
    response = read_json(path, 2097152)
    need(metadata["body_bytes"] == path.stat().st_size and
         metadata["body_sha256"] == digest(path.read_bytes()), "ORIGINAL_JOB_API_BODY_BYTES")
    return expected_job(metadata, response, context, stage_started)


def validate_job_tuple(job: dict, context: dict, expected: dict | None) -> None:
    need(type(job) is dict and job["status"] == "OBSERVED_ACTUAL_JOB_START" and
         type(expected) is dict and
         all(job[k] == expected[k] for k in ("job_id", "job_name", "run_id", "run_attempt",
                                             "started_at", "started_at_epoch", "observed_at_epoch")) and
         job["run_id"] == context["run_id"] and job["run_attempt"] == context["run_attempt"] and
         all(type(job[k]) is int and job[k] > 0 for k in ("job_id", "run_id", "run_attempt")) and
         job["timeout_minutes"] == 15 and job["archive_reserve_seconds"] == 60,
         "RETAINED_ORIGINAL_JOB_CONTEXT")
    need(all(finite(job[k]) for k in ("started_at_epoch", "observed_at_epoch", "deadline_epoch")) and
         job["deadline_epoch"] == job["started_at_epoch"] + 900, "ORIGINAL_JOB_EPOCH_TYPE_OR_DEADLINE")


class Budget:
    def __init__(self):
        self.started = time.monotonic()
        self.started_epoch = time.time()
        self.limit = 180.0
        self.job = None
        self.expected_job = None
        self.commands: list[dict] = []

    def bind_job(self, job_file: Path | None, observation_dir: Path | None,
                 context: dict, output: Path) -> None:
        if context["kind"] == "github_actions":
            need(job_file is not None and observation_dir is not None, "ORIGINAL_JOB_OBSERVATION_REQUIRED")
            retained = output / "job-observation"
            retained.mkdir()
            for src, name, cap in ((job_file, "deadline.json", 65536),
                                   (observation_dir / "request.json", "request.json", 65536),
                                   (observation_dir / "jobs.json", "jobs.json", 2097152)):
                need(src.is_file() and not src.is_symlink() and 0 < src.stat().st_size <= cap + 1,
                     "MISSING_OR_OVERSIZED_JOB_OBSERVATION:" + name)
                shutil.copyfile(src, retained / name)
            self.expected_job = job_observation(retained, context, self.started_epoch)
            self.job = read_json(retained / "deadline.json", 65536)
            validate_job_tuple(self.job, context, self.expected_job)
            self.limit = min(self.limit, self.job["deadline_epoch"] - self.started_epoch - 60)
        need(self.limit > 0, "NO_REMAINING_RESEARCH_BUDGET")
        validate_budget(self.record(), context, [], self.expected_job)

    def remaining(self, limit: float | None = None) -> float:
        remaining = self.limit - (time.monotonic() - self.started)
        need(remaining > 0, "STAGE_DEADLINE")
        return min(remaining, limit) if limit is not None else remaining

    def run(self, argv: list[str], log: Path, seconds: int = 60,
            env: dict | None = None, target_process: bool = False) -> dict:
        self.remaining()
        log.parent.mkdir(parents=True, exist_ok=True)
        started = time.monotonic()
        limit = min(float(seconds), self.limit - (started - self.started))
        need(limit > 0, "NO_CHILD_EXECUTION_BUDGET")
        row = {"argv": argv, "target_process": target_process,
               "started_offset_seconds": started - self.started, "timeout_seconds": limit,
               "returncode": None, "failure": None}
        self.commands.append(row)
        with log.open("xb") as stream:
            process = subprocess.Popen(argv, cwd=ROOT, env=env, stdout=stream,
                                       stderr=subprocess.STDOUT, start_new_session=True)
            row["pid"] = process.pid
            while True:
                pid, status, usage = os.wait4(process.pid, os.WNOHANG)
                if pid:
                    break
                if time.monotonic() - started >= limit or log.stat().st_size > 1048576:
                    row["failure"] = "CHILD_DEADLINE_OR_LOG_CAP"
                    try:
                        os.killpg(process.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    _, status, usage = os.wait4(process.pid, 0)
                    break
                time.sleep(.01)
            process.returncode = os.waitstatus_to_exitcode(status)
            row.update(returncode=process.returncode, elapsed_seconds=time.monotonic() - started,
                       user_cpu_seconds=usage.ru_utime, system_cpu_seconds=usage.ru_stime,
                       peak_rss_bytes=int(usage.ru_maxrss) * 1024)
        need(row["failure"] is None and row["returncode"] == 0,
             "CHILD_EXECUTION_FAILED:" + str(log))
        need(row["elapsed_seconds"] <= limit, "CHILD_TOTAL_WALL_BUDGET")
        need(log.stat().st_size <= 1048576, "CHILD_LOG_CAP")
        self.remaining()
        return row

    def record(self) -> dict:
        commands = copy.deepcopy(self.commands)
        for row in commands:
            row.setdefault("target_process", False)
            row.setdefault("failure", "METADATA_COMMAND_TIMEOUT" if row.get("timeout") else None)
        return {"stage_limit_seconds": 180, "effective_limit_seconds": self.limit,
                "stage_started_epoch": self.started_epoch,
                "elapsed_seconds": time.monotonic() - self.started,
                "archive_reserve_seconds": 60, "original_job": self.job,
                "commands": commands}


def elf_sections(path: Path) -> dict:
    data = path.read_bytes()
    need(len(data) > 64 and data[:4] == b"\x7fELF" and data[5] == 1, "ELF_LITTLE_ENDIAN")
    bits = {1: 32, 2: 64}.get(data[4])
    need(bits in (32, 64), "ELF_CLASS")
    header = struct.unpack_from("<HHIQQQIHHHHHH" if bits == 64 else "<HHIIIIIHHHHHH", data, 16)
    offset, stride, count, names_index = header[5], header[10], header[11], header[12]
    fmt = "<IIQQQQIIQQ" if bits == 64 else "<IIIIIIIIII"
    need(0 < count < 4096 and stride == struct.calcsize(fmt) and
         names_index < count and offset + count * stride <= len(data), "ELF_SECTION_TABLE")
    rows = [struct.unpack_from(fmt, data, offset + i * stride) for i in range(count)]
    strings = rows[names_index]
    need(strings[4] + strings[5] <= len(data), "ELF_STRING_TABLE")
    names = data[strings[4]:strings[4] + strings[5]]
    result = {}
    for row in rows:
        need(row[0] < len(names) and b"\0" in names[row[0]:], "ELF_SECTION_NAME")
        name = names[row[0]:].split(b"\0", 1)[0].decode("ascii")
        if name in (".text", ".rodata", ".data", ".bss"):
            need(name not in result, "ELF_DUPLICATE_SECTION")
            result[name] = row[5]
    need(set(result) == {".text", ".rodata", ".data", ".bss"}, "ELF_RESOURCE_SECTIONS")
    return {"class_bits": bits, "machine": header[1], "file_bytes": len(data), "sections": result}


def clean_environment() -> dict:
    env = os.environ.copy()
    for key in BUILD_ENV_INPUTS + PRIVATE_ENV_INPUTS:
        env.pop(key, None)
    return env


def build_target(target: str, scratch: Path, output: Path, budget: Budget, cmake: str) -> tuple[dict, dict]:
    compiler = shutil.which("arm-linux-gnueabihf-gcc" if target == "arm" else "cc")
    need(compiler is not None, "COMPILER_MISSING:" + target)
    compiler = str(Path(compiler).absolute())
    build, evidence = scratch / target, output / target / "build"
    evidence.mkdir(parents=True)
    env = clean_environment()
    budget.run([compiler, "--version"], evidence / "compiler.log", 10, env)
    budget.run([cmake, "--version"], evidence / "cmake-version.log", 10, env)
    argv = [cmake, "-S", str(HERE / "fe09_t3s3_f0_build"), "-B", str(build),
            "-DAP_REPO_ROOT=" + str(ROOT), "-DCMAKE_BUILD_TYPE=Release",
            "-DCMAKE_C_COMPILER=" + compiler,
            "-DCMAKE_C_FLAGS=", "-DCMAKE_EXE_LINKER_FLAGS=", "-DCMAKE_STATIC_LINKER_FLAGS=",
            "-DCMAKE_C_COMPILER_LAUNCHER=", "-DCMAKE_C_LINKER_LAUNCHER=",
            "-DCMAKE_C_FLAGS_RELEASE=" + ("-O1 -g -DNDEBUG" if target == "sanitized" else "-O2 -DNDEBUG"),
            "-DB3_F0_SANITIZE=" + ("ON" if target == "sanitized" else "OFF")]
    if target == "arm":
        argv += ["-DCMAKE_TOOLCHAIN_FILE=" + str(ROOT / "cmake/toolchains/arm-linux-gnueabihf.cmake")]
    budget.run(argv, evidence / "configure.log", env=env)
    budget.run([cmake, "--build", str(build), "--parallel", "2", "--target",
                "fe09_b3_f0_plain", "fe09_t3s3_f0_probe"], evidence / "build.log", env=env)
    binaries = {"reference": build / "b3/fe09_b3_f0_plain", "measured": build / "fe09_t3s3_f0_probe"}
    copies = {"reference.elf": binaries["reference"], "measured.elf": binaries["measured"],
              "libaudio_pipeline.a": build / "b3/public_sdk/libaudio_pipeline.a",
              "compile_commands.json": build / "compile_commands.json",
              "CMakeCache.txt": build / "CMakeCache.txt",
              "audio_pipeline_build.h": build / "b3/public_sdk/generated/audio_pipeline/audio_pipeline_build.h",
              "reference-link.txt": build / "b3/CMakeFiles/fe09_b3_f0_plain.dir/link.txt",
              "measured-link.txt": build / "CMakeFiles/fe09_t3s3_f0_probe.dir/link.txt"}
    for name, path in copies.items():
        shutil.copyfile(path, evidence / name)
    stack = []
    for path in sorted(build.rglob("*.su")):
        for line in path.read_text().splitlines():
            fields = line.rsplit("\t", 2)
            need(len(fields) == 3 and fields[1].isdigit(), "STACK_USAGE_ROW")
            stack.append({"object": str(path.relative_to(build)), "function": fields[0],
                          "bytes": int(fields[1]), "kind": fields[2]})
    need(stack, "COMPILER_STACK_REPORTS_REQUIRED")
    write_json(evidence / "stack-usage.json", stack)
    budget.run(["nm", "--defined-only", str(binaries["measured"])], evidence / "symbols.log", 10, env)
    qemu = None
    if target == "arm":
        qemu_path = str(Path(shutil.which("qemu-arm")).absolute())
        budget.run([qemu_path, "--version"], evidence / "qemu-version.log", 10, env)
        qemu = {"path": qemu_path, "sha256": digest(Path(qemu_path).read_bytes()),
                "sysroot": "/usr/arm-linux-gnueabihf"}
    record = {"target": target, "source_root": str(ROOT), "build_root": str(build),
              "executables": {k: str(v) for k, v in binaries.items()}, "qemu": qemu, "compiler": compiler,
              "compiler_binary_sha256": digest(Path(compiler).read_bytes()),
              "sanitized_build_environment": list(BUILD_ENV_INPUTS),
              "binaries": {k: digest(v.read_bytes()) for k, v in binaries.items()},
              "archive_sha256": digest(copies["libaudio_pipeline.a"].read_bytes()),
              "elf": {k: elf_sections(v) for k, v in binaries.items()},
              "maximum_single_compiler_frame_bytes": max(x["bytes"] for x in stack),
              "stack_scope": "per-function compiler reports, no cumulative or high-water claim"}
    validate_build(evidence, record)
    return binaries, record


def source_groups() -> dict:
    reference = SHARED_SOURCES + ["tests/validation/frontend_evolution/fe09_b3_f0_composition_test.c"]
    return {"library": LIBRARY_SOURCES, "reference": reference, "unbuilt": reference,
            "measured": SHARED_SOURCES + ["tests/validation/frontend_evolution/fe09_t3s3_f0_call_resource_probe.c"]}


def object_name(group: str, source: str, source_root: Path) -> str:
    if group == "library":
        return "CMakeFiles/audio_pipeline.dir/" + source + ".o"
    target = {"reference": "fe09_b3_f0_plain", "measured": "fe09_t3s3_f0_probe",
              "unbuilt": "fe09_b3_f0_observed"}[group]
    return "CMakeFiles/" + target + ".dir/" + str(source_root / source).lstrip("/") + ".o"


def validate_compile_recipe(rows: list[dict], cache_text: str, record: dict) -> None:
    root, build = Path(record["source_root"]), Path(record["build_root"])
    need(root.is_absolute() and build.is_absolute() and Path(record["compiler"]).is_absolute() and
         ".." not in root.parts and ".." not in build.parts, "BUILD_PATH_IDENTITY")
    cache = {}
    for line in cache_text.splitlines():
        match = re.fullmatch(r"([A-Za-z_][A-Za-z_0-9]*):[^=]+=(.*)", line)
        if match:
            need(match[1] not in cache, "DUPLICATE_CMAKE_CACHE_KEY")
            cache[match[1]] = match[2]
    target = record["target"]
    release = "-O1 -g -DNDEBUG" if target == "sanitized" else "-O2 -DNDEBUG"
    expected_cache = {"CMAKE_C_COMPILER": record["compiler"], "CMAKE_BUILD_TYPE": "Release",
                      "CMAKE_C_FLAGS": "", "CMAKE_C_FLAGS_RELEASE": release,
                      "CMAKE_EXE_LINKER_FLAGS": "", "CMAKE_EXE_LINKER_FLAGS_RELEASE": "",
                      "CMAKE_STATIC_LINKER_FLAGS": "", "CMAKE_STATIC_LINKER_FLAGS_RELEASE": "",
                      "CMAKE_C_COMPILER_LAUNCHER": "", "CMAKE_C_LINKER_LAUNCHER": "",
                      "CMAKE_HOME_DIRECTORY": str(root / "tests/validation/frontend_evolution/fe09_t3s3_f0_build"),
                      "AP_REPO_ROOT": str(root), "AP_SIMD_BACKEND": "SCALAR", "AP_AEC_BACKEND": "MDF",
                      "AP_RESAMPLER_MODE": "BANDLIMITED", "AP_NS_ESTIMATOR": "EMA",
                      "AP_ENABLE_FAST_MATH": "OFF", "AP_ENABLE_LINUX_RUNTIME": "OFF"}
    need(all(cache.get(k) == v for k, v in expected_cache.items()), "EXPLICIT_EFFECTIVE_BUILD_CACHE")
    need(record["sanitized_build_environment"] == list(BUILD_ENV_INPUTS), "BUILD_ENVIRONMENT_CLOSURE")
    if target == "arm":
        need(cache.get("CMAKE_TOOLCHAIN_FILE") == str(root / "cmake/toolchains/arm-linux-gnueabihf.cmake"),
             "ARM_TOOLCHAIN_FILE_IDENTITY")
    else:
        need(not cache.get("CMAKE_TOOLCHAIN_FILE"), "UNREGISTERED_NATIVE_TOOLCHAIN_FILE")
    groups = source_groups()
    seen = {group: [] for group in groups}
    for row in rows:
        tokens = shlex.split(row["command"]) if "command" in row else row["arguments"]
        need(len(tokens) >= 6 and tokens[0] == record["compiler"] and
             tokens[-4] == "-o" and tokens[-2] == "-c" and tokens[-1] == row["file"],
             "EXACT_COMPILER_AND_COMPILE_FORM")
        output = tokens[-3]
        group = next((g for g, marker in (
            ("library", "CMakeFiles/audio_pipeline.dir/"),
            ("reference", "CMakeFiles/fe09_b3_f0_plain.dir/"),
            ("measured", "CMakeFiles/fe09_t3s3_f0_probe.dir/"),
            ("unbuilt", "CMakeFiles/fe09_b3_f0_observed.dir/")) if output.startswith(marker)), None)
        need(group is not None and Path(row["file"]).is_relative_to(root), "COMPILED_SOURCE_GROUP")
        source = str(Path(row["file"]).relative_to(root))
        need(source in groups[group] and output == object_name(group, source, root), "EXACT_SOURCE_OBJECT_IDENTITY")
        directory = build / ("b3/public_sdk" if group == "library" else "" if group == "measured" else "b3")
        need(Path(row["directory"]) == directory, "COMPILE_WORKING_DIRECTORY")
        includes = ([build / "b3/public_sdk/generated", root / "include", root / "src"] if group == "library" else
                    [root / "tests/validation/frontend_evolution", root / "src", root / "include", build / "b3/public_sdk/generated"])
        need([t for t in tokens[1:-4] if t.startswith("-I")] == ["-I" + str(p) for p in includes],
             "EXACT_INCLUDE_ROOTS_AND_ORDER")
        definitions = DEFINITIONS + ["-DNDEBUG"] + (["-DFE_B3_F0_OBSERVED=1"] if group == "unbuilt" else [])
        flags = ["-std=c11", "-ffp-contract=off", "-fno-fast-math", "-fno-lto", "-fstack-usage",
                 "-Wall", "-Wextra", "-Wpedantic"]
        if group != "library":
            flags.append("-Werror")
        flags += (["-O1", "-g", "-O1", "-g", "-fsanitize=address,undefined", "-fno-omit-frame-pointer"]
                  if target == "sanitized" else ["-O2", "-O2"])
        actual = [t for t in tokens[1:-4] if not t.startswith("-I")]
        need(Counter(actual) == Counter(definitions + flags), "EXACT_EFFECTIVE_COMPILE_RECIPE")
        seen[group].append(source)
    need(all(Counter(seen[g]) == Counter(groups[g]) for g in groups), "COMPLETE_SOURCE_MULTISET")


def validate_link_recipe(tokens: list[str], record: dict, variant: str) -> None:
    root = Path(record["source_root"])
    sources = source_groups()[variant]
    expected = [record["compiler"]] + (["-O1", "-g", "-DNDEBUG", "-fsanitize=address,undefined"]
                  if record["target"] == "sanitized" else ["-O2", "-DNDEBUG"]) + ["-fno-lto"]
    if variant == "measured":
        expected += ["-Wl,--wrap=" + symbol for symbol in WRAPS]
    expected += [object_name(variant, path, root) for path in sources]
    executable = "fe09_t3s3_f0_probe" if variant == "measured" else "fe09_b3_f0_plain"
    expected += ["-o", executable, ("b3/" if variant == "measured" else "") + "public_sdk/libaudio_pipeline.a", "-lm"]
    dependency_flag = "-Wl,--dependency-file=CMakeFiles/" + executable + ".dir/link.d"
    # CMake 4 emits one dependency-file option; CMake 3 does not.
    need(tokens.count(dependency_flag) <= 1, "LINK_DEPENDENCY_OPTION_COUNT")
    actual = [t for t in tokens if t != dependency_flag]
    need(tokens[0] == record["compiler"] and Counter(actual) == Counter(expected), "EXACT_LINK_RECIPE_AND_OBJECTS")


def validate_build(directory: Path, record: dict) -> None:
    target = record["target"]
    need(target in TARGETS, "BUILD_TARGET")
    build = Path(record["build_root"])
    need(record["executables"] == {"reference": str(build / "b3/fe09_b3_f0_plain"),
                                    "measured": str(build / "fe09_t3s3_f0_probe")} and
         bool(re.fullmatch(r"[0-9a-f]{64}", record["compiler_binary_sha256"])), "BUILT_EXECUTABLE_AND_COMPILER_IDENTITY")
    if target == "arm":
        qemu = record["qemu"]
        need(type(qemu) is dict and Path(qemu["path"]).is_absolute() and
             qemu["sysroot"] == "/usr/arm-linux-gnueabihf" and
             bool(re.fullmatch(r"[0-9a-f]{64}", qemu["sha256"])) and
             (directory / "qemu-version.log").is_file(), "QEMU_HOST_TOOL_IDENTITY")
    else:
        need(record["qemu"] is None, "NATIVE_CANNOT_USE_EMULATOR")
    for variant in ("reference", "measured"):
        path = directory / (variant + ".elf")
        need(digest(path.read_bytes()) == record["binaries"][variant] and
             elf_sections(path) == record["elf"][variant], "ORIGINAL_ELF_BYTES_OR_SECTIONS")
        need(record["elf"][variant]["machine"] == (40 if target == "arm" else 62), "ACTUAL_ELF_ISA")
        link = shlex.split((directory / (variant + "-link.txt")).read_text())
        validate_link_recipe(link, record, variant)
        wrappers = {token.split("=", 1)[1] for token in link if token.startswith("-Wl,--wrap=")}
        need(wrappers == (WRAPS if variant == "measured" else set()) and "-fno-lto" in link,
             "ACTUAL_LINK_WRAPPERS")
        library = [token for token in link if token.endswith("/libaudio_pipeline.a")]
        need(len(library) == 1 and library[0] in ("public_sdk/libaudio_pipeline.a", "b3/public_sdk/libaudio_pipeline.a"),
             "SAME_ORIGINAL_LIBRARY_LINK")
    need(digest((directory / "libaudio_pipeline.a").read_bytes()) == record["archive_sha256"], "LIBRARY_BYTES")
    expected_symbols = set(re.findall(r"\b__wrap_(\w+)$", (directory / "symbols.log").read_text(), re.M))
    need(expected_symbols == WRAPS, "ACTUAL_WRAPPER_SYMBOLS")
    validate_compile_recipe(read_json(directory / "compile_commands.json"),
                            (directory / "CMakeCache.txt").read_text(), record)
    stack = read_json(directory / "stack-usage.json")
    need(stack and all(type(x["bytes"]) is int and 0 <= x["bytes"] < 1048576 for x in stack) and
         max(x["bytes"] for x in stack) == record["maximum_single_compiler_frame_bytes"], "STATIC_STACK_LEDGER")


def build_negatives(directory: Path, record: dict) -> list[dict]:
    """Mutate actual build metadata before any DSP, without executing commands."""
    rows = read_json(directory / "compile_commands.json")
    cache = (directory / "CMakeCache.txt").read_text()
    def omit_shared(changed):
        changed[:] = [x for x in changed if not (
            x["file"].endswith("/array_native.c") and "fe09_b3_f0_observed" not in x["command"])]
    def omit_library(changed):
        changed[:] = [x for x in changed if "CMakeFiles/audio_pipeline.dir/" not in x["command"] or
                      x["file"].endswith("/ap_pipeline.c")]
    def inject(changed, flag):
        tokens = shlex.split(changed[0]["command"])
        tokens[-4:-4] = shlex.split(flag)
        changed[0]["command"] = shlex.join(tokens)
    def compiler(changed):
        tokens = shlex.split(changed[0]["command"])
        tokens[0] = "/unregistered/compiler"
        changed[0]["command"] = shlex.join(tokens)
    mutations = [("shared-TU-omission", omit_shared), ("library-TU-omission", omit_library),
                 ("duplicate-TU", lambda x: x.append(copy.deepcopy(x[0]))), ("compiler-path", compiler),
                 ("forced-header", lambda x: inject(x, "-include /unregistered/header.h")),
                 ("response-file", lambda x: inject(x, "@/unregistered/flags")),
                 ("compiler-plugin", lambda x: inject(x, "-fplugin=/unregistered/plugin.so")),
                 ("FP-order-override", lambda x: inject(x, "-ffp-contract=fast")),
                 ("external-include", lambda x: inject(x, "-I/unregistered/include"))]
    results = []
    for label, mutate in mutations:
        changed = copy.deepcopy(rows)
        mutate(changed)
        try:
            validate_compile_recipe(changed, cache, record)
        except Rejected as error:
            results.append({"id": label, "rejected": True, "reason": str(error), "additional_DSP_frames": 0})
        else:
            raise Rejected("BUILD_METADATA_MUTATION_ACCEPTED:" + label)
    return results


def duration(row: dict) -> None:
    need(type(row) is dict and set(row) == {"calls", "status", "cpu_ns", "wall_ns"} and
         type(row["calls"]) is int and row["calls"] == 1 and
         type(row["status"]) is int and row["status"] == 0,
         "EXACTLY_ONE_SUCCESSFUL_MEASURED_CALL")
    for key in ("cpu_ns", "wall_ns"):
        need(type(row[key]) is int and 0 <= row[key] <= 30_000_000_000, "NONNEGATIVE_INTEGER_DURATION")


def statistics(values: list[int]) -> dict:
    need(len(values) == 600 and all(type(x) is int and x >= 0 for x in values), "ALL_600_FRAMES_REQUIRED")
    ordered = sorted(values)
    return {"count": len(values), "sum_ns": sum(values), "p50_ns": ordered[299],
            "p95_ns": ordered[569], "p99_ns": ordered[593], "max_ns": ordered[-1],
            "milliseconds_per_audio_second": sum(values) / 1_000_000 / 6,
            "frame201_ns": values[200], "frame241_ns": values[240]}


def validate_timing(data: dict, case: str) -> dict:
    need(data["schema_version"] == 1 and data["id"] == IDENTITY and data["case"] == case and
         type(data["failed"]) is int and data["failed"] == 0 and data["completed_frames"] == 600,
         "TIMING_RUN_IDENTITY_OR_COMPLETENESS")
    need(data["clock_cpu"] == "CLOCK_THREAD_CPUTIME_ID" and data["clock_wall"] == "CLOCK_MONOTONIC",
         "TIMING_CLOCK_AUTHORITY")
    need(all(type(data[k]) is int and 0 < data[k] < 1_000_000_000
             for k in ("cpu_resolution_ns", "wall_resolution_ns")) and
         type(data["timing_storage_bytes"]) is int and 0 < data["timing_storage_bytes"] <= 65536,
         "CLOCK_RESOLUTION_OR_TIMING_STORAGE")
    duration(data["bind"])
    frames = data["frames"]
    need(type(frames) is list and len(frames) == 600, "TIMING_FRAME_COUNT")
    for seq, row in enumerate(frames, 1):
        need(type(row["seq"]) is int and row["seq"] == seq and
             type(row["event"]) is int and row["event"] == (2 if case == "PAP" and 201 <= seq <= 240 else 1),
             "TIMING_FRAME_OR_RENDER_ORDER")
        for role in ("capture", "render", "worker"):
            duration(row[role])
    result = {}
    for clock in ("cpu_ns", "wall_ns"):
        for role in ("capture", "render", "worker", "combined"):
            values = [sum(row[x][clock] for x in ("capture", "render", "worker")) if role == "combined"
                      else row[role][clock] for row in frames]
            result[role + "_" + clock] = statistics(values)
    return result


def validate_usage(row: dict) -> None:
    need(type(row["pid"]) is int and row["pid"] > 0 and row["target_process"] is True and
         type(row["returncode"]) is int and row["returncode"] == 0 and row["failure"] is None,
         "ACTUAL_SUCCESSFUL_CHILD_REQUIRED")
    need(type(row["peak_rss_bytes"]) is int and row["peak_rss_bytes"] > 0 and
         row["peak_rss_bytes"] % 1024 == 0, "ACTUAL_LINUX_WAIT4_RSS_REQUIRED")
    for key in ("user_cpu_seconds", "system_cpu_seconds", "elapsed_seconds", "timeout_seconds"):
        need(type(row[key]) in (int, float) and math.isfinite(row[key]) and row[key] >= 0,
             "PROCESS_USAGE_FINITE")
    need(0 < row["elapsed_seconds"] <= row["timeout_seconds"] and
         0 < row["timeout_seconds"] <= 30, "TARGET_PROCESS_BUDGET")


def canonical(case: dict) -> dict:
    return {"streams": case["streams"], "frames": [original.canonical_frame(x) for x in case["frames"]]}


def validate_invocation(usage: dict, bundle: dict, spec: dict) -> None:
    target, built, name = bundle["target"], bundle["build"], spec["name"]
    output_root = Path(bundle["output_root"])
    need(output_root.is_absolute() and ".." not in output_root.parts, "EXECUTION_OUTPUT_ROOT")
    argv = [built["executables"][spec["variant"]], "--case", spec["case"], "--mode", "adapter",
            "--future", "0", "--negatives", "0", "--output", str(output_root / ("incomplete-" + target + "-" + name))]
    if target == "arm":
        argv = [built["qemu"]["path"], "-L", built["qemu"]["sysroot"]] + argv
    need(usage["executed_elf_sha256"] == built["binaries"][spec["variant"]] and
         usage["target"] == target and usage["case_name"] == name and usage["argv"] == argv and
         usage["runtime_env"] == RUNTIME_ENV and usage["sanitized_environment"] == list(BUILD_ENV_INPUTS),
         "ACTUAL_TARGET_PROCESS_BINDING")


def invocation_negatives(bundle: dict) -> list[dict]:
    spec = schedule()[0]
    original_usage = bundle["usage"][spec["name"]]
    mutations = [("wrong-executable", lambda x: x["argv"].__setitem__(0, "/wrong/executable")),
                 ("wrong-output", lambda x: x["argv"].__setitem__(-1, "/wrong/case-output")),
                 ("sanitizer-disabled", lambda x: x["runtime_env"].update(ASAN_OPTIONS="detect_leaks=0")),
                 ("wrong-executed-ELF", lambda x: x.update(executed_elf_sha256="0" * 64))]
    if bundle["target"] == "arm":
        mutations.append(("wrong-guest-executable", lambda x: x["argv"].__setitem__(3, "/wrong/arm-executable")))
    results = []
    for label, mutate in mutations:
        changed = copy.deepcopy(original_usage)
        mutate(changed)
        try:
            validate_invocation(changed, bundle, spec)
        except Rejected as error:
            results.append({"id": label, "rejected": True, "reason": str(error), "additional_DSP_frames": 0})
        else:
            raise Rejected("INVOCATION_MUTATION_ACCEPTED:" + label)
    return results


def validate_target(bundle: dict, inputs: dict) -> dict:
    plan = contract()
    target = bundle["target"]
    need(target in TARGETS and bundle["execution_kind"] in ("local", "github_actions") and
         bundle["toolchain_image"] == (IMAGE if bundle["execution_kind"] == "github_actions" else None) and
         bundle["required_ci_toolchain_image"] == IMAGE and bundle["source_lock_sha256"] == LOCK_SHA and
         bundle["promotion"] == plan["promotion"], "MEASUREMENT_AUTHORITY_DRIFT")
    need(bundle["rss_scope"] == ("QEMU_AND_GUEST_HOST_PROCESS" if target == "arm" else "EXACT_HOST_PROCESS_WITH_TEST_HARNESS") and
         bundle["timing_scope"] == ("HOSTED_NATIVE_DESCRIPTIVE" if target == "native" else "INSTRUMENTED_OR_EMULATED_DESCRIPTIVE_ONLY"),
         "HOST_AND_EMULATOR_SCOPE")
    need(bundle["completed_cases"] == [s["name"] for s in schedule()] and
         set(bundle["cases"]) == set(bundle["completed_cases"]) and
         set(bundle["usage"]) == set(bundle["completed_cases"]) and
         set(bundle["timings"]) == {s["name"] for s in schedule() if s["variant"] == "measured"},
         "EXACT_REPEATS_AND_PROCESS_MATRIX")
    summaries, baseline = {}, {}
    for spec in schedule():
        name, case = spec["name"], bundle["cases"][spec["name"]]
        need(original.validate_case(case, spec, inputs), "ORIGINAL_FIXED_COVERAGE_REQUIRED")
        usage = bundle["usage"][name]
        validate_usage(usage)
        validate_invocation(usage, bundle, spec)
        content = canonical(case)
        if spec["case"] not in baseline:
            baseline[spec["case"]] = content
        need(content == baseline[spec["case"]], "EXACT_PCM_OR_PUBLIC_METRIC_EQUIVALENCE")
        if spec["variant"] == "measured":
            summaries[name] = validate_timing(bundle["timings"][name], spec["case"])
            timing = bundle["timings"][name]
            cpu_ns = summaries[name]["combined_cpu_ns"]["sum_ns"] + timing["bind"]["cpu_ns"]
            wall_ns = summaries[name]["combined_wall_ns"]["sum_ns"] + timing["bind"]["wall_ns"]
            # These disjoint intervals must fit inside their complete child.
            # wait4's user/system timeval fields each quantize to microseconds;
            # two microseconds cover that representation, not extra work time.
            need(cpu_ns <= math.ceil((usage["user_cpu_seconds"] + usage["system_cpu_seconds"]) * 1e9) + 2000 and
                 wall_ns <= math.ceil(usage["elapsed_seconds"] * 1e9), "API_INTERVALS_OUTSIDE_COMPLETE_PROCESS")
    return summaries


def semantic_negatives(bundle: dict, inputs: dict) -> list[dict]:
    name = "PAP-1-measured"
    mutations = [
        ("missing-frame", lambda x: x["timings"][name]["frames"].pop()),
        ("duplicate-frame", lambda x: x["timings"][name]["frames"][1].update(seq=1)),
        ("negative-duration", lambda x: x["timings"][name]["frames"][0]["worker"].update(cpu_ns=-1)),
        ("bool-duration", lambda x: x["timings"][name]["frames"][0]["worker"].update(cpu_ns=True)),
        ("missing-call", lambda x: x["timings"][name]["frames"][0]["capture"].update(calls=0)),
        ("wrong-render-event", lambda x: x["timings"][name]["frames"][200].update(event=1)),
        ("missing-repeat", lambda x: x["completed_cases"].pop()),
        ("pcm-hash-mismatch", lambda x: x["cases"][name]["streams"]["output"].update(sha256="0" * 64)),
        ("public-metric-mismatch", lambda x: x["cases"][name]["frames"][0]["metrics"].update(estimated_delay_ms=999)),
        ("rss-missing", lambda x: x["usage"][name].update(peak_rss_bytes=0)),
        ("toolchain-drift", lambda x: x.update(required_ci_toolchain_image="unqualified-image")),
        ("source-drift", lambda x: x.update(source_lock_sha256="0" * 64)),
        ("promotion", lambda x: x["promotion"].update(ssc305=True)),
    ]
    results = []
    for label, mutate in mutations:
        changed = copy.deepcopy(bundle)
        mutate(changed)
        try:
            validate_target(changed, inputs)
        except Rejected as exc:
            results.append({"id": label, "rejected": True, "reason": str(exc), "additional_DSP_frames": 0})
        else:
            raise Rejected("SEMANTIC_MUTATION_ACCEPTED:" + label)
    need([x["id"] for x in results] == contract()["negatives"], "FROZEN_NEGATIVE_MATRIX")
    return results


def read_case(path: Path) -> dict:
    with gzip.GzipFile(fileobj=io.BytesIO((path / "frames.jsonl.gz").read_bytes())) as stream:
        data = stream.read(4 * 1024 * 1024 + 1)
    need(len(data) <= 4 * 1024 * 1024, "FRAME_EXPANSION_CAP")
    return {"result": read_json(path / "result.json", 65536),
            "streams": read_json(path / "streams.json", 256 * 1024),
            "frames": [loads(line) for line in data.splitlines()]}


def bundle_from_disk(output: Path, target: str) -> dict:
    row = read_json(output / target / "record.json")
    row["cases"] = {s["name"]: read_case(output / target / s["name"]) for s in schedule()}
    row["timings"] = {s["name"]: read_json(output / target / s["name"] / "timing.json", 1048576)
                      for s in schedule() if s["variant"] == "measured"}
    row["usage"] = {s["name"]: read_json(output / target / s["name"] / "usage.json", 65536) for s in schedule()}
    return row


def seal(output: Path) -> None:
    files = [p for p in sorted(output.rglob("*")) if p.is_file() and p.name != "SHA256SUMS"]
    need(not any(p.is_symlink() for p in output.rglob("*")), "ARTIFACT_SYMLINK")
    need(sum(p.stat().st_size for p in files) < 33554432 - 65536, "ARTIFACT_CAP")
    (output / "SHA256SUMS").write_text("".join(f"{digest(p.read_bytes())}  {p.relative_to(output)}\n" for p in files))


def validate_budget(budget: dict, context: dict, processes: list[dict], expected: dict | None) -> None:
    need(budget["stage_limit_seconds"] == 180 and budget["archive_reserve_seconds"] == 60 and
         all(finite(budget[k]) for k in ("stage_started_epoch", "elapsed_seconds", "effective_limit_seconds")) and
         budget["stage_started_epoch"] > 0 and
         0 < budget["elapsed_seconds"] <= budget["effective_limit_seconds"] <= 180, "STAGE_WALL_BUDGET")
    need(context["kind"] in ("local", "github_actions"), "EXECUTION_CONTEXT_KIND")
    job = budget["original_job"]
    if context["kind"] == "github_actions":
        validate_job_tuple(job, context, expected)
        need(0 < job["started_at_epoch"] <= job["observed_at_epoch"] <= budget["stage_started_epoch"] and
             budget["effective_limit_seconds"] == min(180, job["deadline_epoch"] - budget["stage_started_epoch"] - 60) and
             budget["stage_started_epoch"] + budget["elapsed_seconds"] <= job["deadline_epoch"] - 60,
             "ORIGINAL_JOB_REMAINING_TIME_AND_ARCHIVE_RESERVE")
    else:
        need(job is None and expected is None and budget["effective_limit_seconds"] == 180,
             "LOCAL_BUDGET_CANNOT_IMPERSONATE_HOSTED_JOB")
    cmds = budget["commands"]
    need([x for x in cmds if x["target_process"]] == processes, "WAIT4_PROCESS_LEDGER_BINDING")
    for command in cmds:
        need(all(finite(command[k]) for k in ("elapsed_seconds", "timeout_seconds", "started_offset_seconds")) and
             type(command["target_process"]) is bool and command["returncode"] == 0 and
             command["failure"] is None and command["elapsed_seconds"] <= command["timeout_seconds"] and
             command["started_offset_seconds"] + command["elapsed_seconds"] <= budget["elapsed_seconds"] and
             command["started_offset_seconds"] + command["timeout_seconds"] <= budget["effective_limit_seconds"] + .01,
             "CHILD_AND_OUTER_BUDGET")


def verify(output: Path, source: str, require_full: bool = True) -> dict:
    files = [p for p in output.rglob("*") if p.is_file()]
    need(not any(p.is_symlink() for p in output.rglob("*")) and
         sum(p.stat().st_size for p in files) <= 33554432, "ARTIFACT_MEMBER_TYPE_OR_CAP")
    manifest = {}
    for line in (output / "SHA256SUMS").read_text().splitlines():
        need(len(line) > 66 and line[64:66] == "  ", "MEMBER_MANIFEST_FORMAT")
        sha, name = line[:64], line[66:]
        need(bool(re.fullmatch(r"[0-9a-f]{64}", sha)) and name not in manifest and
             not Path(name).is_absolute() and ".." not in Path(name).parts, "MEMBER_MANIFEST_PATH")
        manifest[name] = sha
    need(manifest == {str(p.relative_to(output)): digest(p.read_bytes()) for p in files if p.name != "SHA256SUMS"},
         "ORIGINAL_MEMBER_BYTES_OR_SET")
    r = read_json(output / "receipt.json")
    plan = contract()
    need(r["id"] == IDENTITY and r["source"] == source_record(source) and
         r["predecessor"] == predecessor() and r["promotion"] == plan["promotion"] and
         r["unmeasured"] == plan["unmeasured"] and r["failure"] is None, "RETAINED_SOURCE_OR_AUTHORITY")
    targets = r["targets"]
    need(targets and targets == [t for t in TARGETS if t in targets] and len(set(targets)) == len(targets),
         "ORDERED_UNIQUE_TARGETS")
    need(not require_full or targets == TARGETS, "PARTIAL_TARGETS_NOT_FULL_QUALIFICATION")
    full = targets == TARGETS and r["context"]["kind"] == "github_actions"
    need(r["decision"] == (DECISION if full else PARTIAL) and r["full_hosted_characterization"] is full and
         r["target_processes"] == len(targets) * 12 and r["processed_frames"] == len(targets) * 7200,
         "CHARACTERIZATION_SCOPE_OR_COUNTS")
    need(r["toolchain_image"] == (IMAGE if r["context"]["kind"] == "github_actions" else None),
         "LOCAL_TOOLCHAIN_CANNOT_IMPERSONATE_IMAGE")
    inputs = original.literal_inputs()
    process_records = []
    for target in targets:
        bundle = bundle_from_disk(output, target)
        need(bundle["target"] == target and bundle["execution_kind"] == r["context"]["kind"],
             "RETAINED_EXECUTION_CONTEXT")
        process_records.extend(bundle["usage"][s["name"]] for s in schedule())
        summaries = validate_target(bundle, inputs)
        need(read_json(output / target / "summary.json") == summaries, "RECOMPUTED_TIMING_SUMMARY")
        validate_build(output / target / "build", bundle["build"])
        need(read_json(output / target / "build-negatives.json") == build_negatives(output / target / "build", bundle["build"]),
             "RECOMPUTED_BUILD_NEGATIVES")
        need(read_json(output / target / "semantic-negatives.json") == semantic_negatives(bundle, inputs),
             "RECOMPUTED_SEMANTIC_NEGATIVES")
        need(read_json(output / target / "invocation-negatives.json") == invocation_negatives(bundle),
             "RECOMPUTED_INVOCATION_NEGATIVES")
    need(len(process_records) == r["target_processes"], "ACTUAL_PROCESS_START_COUNT")
    observed = None
    if r["context"]["kind"] == "github_actions":
        observed = job_observation(output / "job-observation", r["context"], r["budget"]["stage_started_epoch"])
        need(read_json(output / "job-observation/deadline.json", 65536) == r["budget"]["original_job"],
             "ORIGINAL_DEADLINE_FILE_BINDING")
    need(r["job_observation"] == observed, "EXPECTED_ORIGINAL_JOB_IDENTITY")
    validate_budget(r["budget"], r["context"], process_records, observed)
    return r


def collect(args: argparse.Namespace) -> int:
    need(sys.platform.startswith("linux") and hasattr(os, "wait4"), "LINUX_WAIT4_REQUIRED")
    output = args.output.resolve()
    need(not output.exists(), "OUTPUT_EXISTS_NO_OVERWRITE_OR_RETRY")
    output.mkdir(parents=True)
    plan = contract()
    receipt = {"schema_version": 1, "id": IDENTITY, "decision": FAILED,
               "targets": args.targets, "failure": None, "target_processes": 0,
               "processed_frames": 0, "full_hosted_characterization": False,
               "promotion": plan["promotion"], "unmeasured": plan["unmeasured"]}
    budget, raw, scratch = None, None, None
    try:
        budget = Budget()
        original.ACTIVE_BUDGET = budget
        receipt["context"] = original.event_context()
        budget.bind_job(args.job_deadline_file, args.job_observation_dir, receipt["context"], output)
        receipt["job_observation"] = budget.expected_job
        self_test()
        budget.remaining()
        receipt["source"] = source_record(args.execution_source)
        receipt["predecessor"] = predecessor()
        receipt["toolchain_image"] = IMAGE if os.environ.get("GITHUB_ACTIONS") == "true" else None
        if receipt["context"]["kind"] == "github_actions":
            need(args.toolchain_image == IMAGE and args.targets == TARGETS, "HOSTED_IMAGE_AND_ALL_TARGETS_REQUIRED")
        else:
            need(args.toolchain_image is None, "LOCAL_IMAGE_CLAIM_FORBIDDEN")
        cmake = shutil.which(args.cmake)
        need(cmake is not None and shutil.which("nm"), "BUILD_TOOLS_REQUIRED")
        for target in args.targets:
            for tool in (("arm-linux-gnueabihf-gcc", "qemu-arm") if target == "arm" else ("cc",)):
                need(shutil.which(tool) is not None, "TARGET_TOOL_MISSING:" + tool)
        inputs = original.literal_inputs()
        scratch = Path(tempfile.mkdtemp(prefix="fe09-t3s3-build-"))
        for target in args.targets:
            binaries, built = build_target(target, scratch, output, budget, cmake)
            write_json(output / target / "build-negatives.json", build_negatives(output / target / "build", built))
            row = {"target": target, "toolchain_image": receipt["toolchain_image"],
                   "required_ci_toolchain_image": IMAGE, "execution_kind": receipt["context"]["kind"],
                   "source_lock_sha256": LOCK_SHA, "output_root": str(output),
                   "promotion": plan["promotion"], "build": built, "completed_cases": [],
                   "rss_scope": "QEMU_AND_GUEST_HOST_PROCESS" if target == "arm" else "EXACT_HOST_PROCESS_WITH_TEST_HARNESS",
                   "timing_scope": "HOSTED_NATIVE_DESCRIPTIVE" if target == "native" else "INSTRUMENTED_OR_EMULATED_DESCRIPTIVE_ONLY"}
            for spec in schedule():
                budget.remaining()
                raw = output / ("incomplete-" + target + "-" + spec["name"])
                binary = binaries[spec["variant"]]
                need(digest(binary.read_bytes()) == built["binaries"][spec["variant"]], "EXECUTED_ELF_IDENTITY")
                argv = [str(binary), "--case", spec["case"], "--mode", "adapter", "--future", "0",
                        "--negatives", "0", "--output", str(raw)]
                if target == "arm":
                    argv = [built["qemu"]["path"], "-L", built["qemu"]["sysroot"]] + argv
                env = clean_environment()
                env.update(RUNTIME_ENV)
                log = output / target / (spec["name"] + ".log")
                receipt["target_processes"] += 1
                usage = budget.run(argv, log, 30, env, target_process=True)
                usage.update(target=target, case_name=spec["name"],
                             executed_elf_sha256=built["binaries"][spec["variant"]],
                             runtime_env=RUNTIME_ENV, sanitized_environment=list(BUILD_ENV_INPUTS))
                need(sum(p.stat().st_size for p in raw.rglob("*") if p.is_file()) <= 8388608, "RAW_CASE_CAP")
                case = original.load_case(raw, spec)
                need(original.validate_case(case, spec, inputs), "ORIGINAL_FIXED_COVERAGE_REQUIRED")
                destination = output / target / spec["name"]
                original.retain_case(destination, case)
                write_json(destination / "usage.json", usage)
                if spec["variant"] == "measured":
                    timing = read_json(raw / "timing.json", 1048576)
                    validate_timing(timing, spec["case"])
                    shutil.copyfile(raw / "timing.json", destination / "timing.json")
                row["completed_cases"].append(spec["name"])
                receipt["processed_frames"] += 600
                write_json(output / target / "record.json", row)
                shutil.rmtree(raw)
                raw = None
            bundle = bundle_from_disk(output, target)
            write_json(output / target / "summary.json", validate_target(bundle, inputs))
            write_json(output / target / "semantic-negatives.json", semantic_negatives(bundle, inputs))
            write_json(output / target / "invocation-negatives.json", invocation_negatives(bundle))
            budget.remaining()
        receipt["full_hosted_characterization"] = args.targets == TARGETS and receipt["context"]["kind"] == "github_actions"
        receipt["decision"] = DECISION if receipt["full_hosted_characterization"] else PARTIAL
        receipt["budget"] = budget.record()
        write_json(output / "receipt.json", receipt)
        seal(output)
        verify(output, args.execution_source, require_full=receipt["full_hosted_characterization"])
        budget.remaining()
        shutil.rmtree(scratch)
        scratch = None
        budget.remaining()
        receipt["budget"] = budget.record()
        write_json(output / "receipt.json", receipt)
        seal(output)
        budget.remaining()
        print(receipt["decision"], "processes=" + str(receipt["target_processes"]))
        return 0
    except Exception as error:
        receipt.update(decision=FAILED, full_hosted_characterization=False,
                       failure={"type": type(error).__name__, "reason": str(error),
                                "retained_partial_case": str(raw) if raw else None})
        if budget:
            receipt["budget"] = budget.record()
            receipt["target_processes"] = sum(x.get("target_process", False) and "pid" in x
                                               for x in budget.commands)
        write_json(output / "receipt.json", receipt)
        try:
            seal(output)
        except Exception as closeout:
            # Keep original bytes intact. No false complete/success artifact on overflow.
            print("INCOMPLETE_FAILURE_ARCHIVE", str(closeout), file=sys.stderr)
        print(FAILED, str(error), file=sys.stderr)
        return 2
    finally:
        original.ACTIVE_BUDGET = None
        if scratch is not None:
            shutil.rmtree(scratch)


def self_test() -> None:
    plan = contract()
    need(plan["source_baseline"] == BASE and plan["toolchain_image"] == IMAGE and
         len(schedule()) == 12 and plan["maximum_processes"] == 36, "FROZEN_EXECUTION_MATRIX")
    need(statistics(list(range(600)))["p99_ns"] == 593 and
         statistics([0] * 600)["sum_ns"] == 0, "NEAREST_RANK_DEFINITION")
    controls = [lambda: statistics([0] * 599), lambda: statistics([True] * 600),
                lambda: duration({"calls": 1, "status": 0, "cpu_ns": -1, "wall_ns": 1}),
                lambda: duration({"calls": 0, "status": 0, "cpu_ns": 1, "wall_ns": 1}),
                lambda: loads('{"x":1,"x":2}'), lambda: loads('{"x":NaN}')]
    for control in controls:
        try:
            control()
        except Rejected:
            continue
        raise Rejected("METADATA_NEGATIVE_ACCEPTED")
    # Metadata-only fixed schema controls. They are not execution evidence and
    # are never written to the scientific artifact as an observed Actions job.
    context = {"kind": "github_actions", "run_id": 1, "run_attempt": 1, "event_head": "1" * 40}
    budget = {"stage_limit_seconds": 180, "archive_reserve_seconds": 60,
              "stage_started_epoch": 1577837500, "elapsed_seconds": 10,
              "effective_limit_seconds": 140, "commands": [],
              "original_job": {"status": "OBSERVED_ACTUAL_JOB_START", "job_id": 1,
                  "job_name": "quality / frontend-reference", "run_id": 1, "run_attempt": 1,
                  "timeout_minutes": 15, "archive_reserve_seconds": 60,
                  "started_at": "2020-01-01T00:00:00Z", "started_at_epoch": 1577836800,
                  "observed_at_epoch": 1577836801, "deadline_epoch": 1577837700}}
    metadata = {"schema_version": 1, "repository": "jiying2007/audio-pipeline", "run_id": 1,
                "run_attempt": 1, "api_version": "2022-11-28", "response_status": 200,
                "endpoint": "https://api.github.com/repos/jiying2007/audio-pipeline/actions/runs/1/attempts/1/jobs?per_page=100",
                "request_started_epoch": 1577836801, "response_observed_epoch": 1577836802}
    response = {"total_count": 1, "jobs": [{"id": 1, "name": "quality / frontend-reference",
                "run_id": 1, "run_attempt": 1, "head_sha": "1" * 40,
                "status": "in_progress", "started_at": "2020-01-01T00:00:00Z"}]}
    expected = expected_job(metadata, response, context, budget["stage_started_epoch"])
    validate_budget(budget, context, [], expected)
    for mutate in (lambda b: b.update(original_job=None),
                   lambda b: b["original_job"].update(job_id=999999),
                   lambda b: b["original_job"].update(job_name="frontend-reference"),
                   lambda b: b["original_job"].update(run_id=2),
                   lambda b: b["original_job"].update(run_attempt=2),
                   lambda b: b["original_job"].update(started_at="2020-01-01T00:00:01Z"),
                   lambda b: b["original_job"].update(observed_at_epoch=1577836802),
                   lambda b: b["original_job"].update(deadline_epoch=1577837701),
                   lambda b: b.update(effective_limit_seconds=180),
                   lambda b: b.update(stage_started_epoch=1577837501)):
        changed = copy.deepcopy(budget)
        mutate(changed)
        try:
            validate_budget(changed, context, [], expected)
        except Rejected:
            continue
        raise Rejected("ORIGINAL_JOB_BUDGET_MUTATION_ACCEPTED")
    for mutate in (lambda r: r["jobs"][0].update(run_id=2),
                   lambda r: r["jobs"][0].update(run_attempt=2),
                   lambda r: r["jobs"][0].update(head_sha="2" * 40),
                   lambda r: r["jobs"][0].update(status="completed"),
                   lambda r: r.update(total_count=2),
                   lambda r: r["jobs"].append(copy.deepcopy(r["jobs"][0]))):
        changed = copy.deepcopy(response)
        mutate(changed)
        try:
            expected_job(metadata, changed, context, budget["stage_started_epoch"])
        except Rejected:
            continue
        raise Rejected("ORIGINAL_JOB_API_MUTATION_ACCEPTED")
    forward_source.self_test()
    print("FE09_T3S3_F0_FORWARD_SOURCE_R2_METADATA_SELF_TEST_PASS_NO_DSP")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--self-test", action="store_true")
    mode.add_argument("--collect", action="store_true")
    mode.add_argument("--verify", action="store_true")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--execution-source")
    parser.add_argument("--targets", default=",".join(TARGETS))
    parser.add_argument("--cmake", default="cmake")
    parser.add_argument("--toolchain-image")
    parser.add_argument("--job-deadline-file", type=Path,
                        default=os.environ.get("FE_FRONTEND_JOB_DEADLINE_FILE"))
    parser.add_argument("--job-observation-dir", type=Path,
                        default=os.environ.get("FE_FRONTEND_JOB_API_OBSERVATION_DIR"))
    parser.add_argument("--allow-partial", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    need(args.output is not None and args.execution_source is not None, "OUTPUT_AND_SOURCE_REQUIRED")
    args.targets = args.targets.split(",")
    need(args.targets and args.targets == [t for t in TARGETS if t in args.targets] and
         len(set(args.targets)) == len(args.targets), "TARGET_ORDER")
    if args.collect:
        return collect(args)
    result = verify(args.output, args.execution_source, not args.allow_partial)
    print("FE09_T3S3_F0_R2_ARTIFACT_VERIFIED", result["decision"])
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (Rejected, OSError, KeyError, ValueError, TypeError) as exc:
        print("FE09_T3S3_F0_REJECTED", str(exc), file=sys.stderr)
        raise SystemExit(2)
