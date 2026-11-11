#!/usr/bin/env python3
"""D7 exact-current full-pipeline build and bounded evidence primitives.

No historical builder is executed. All subprocesses have an independently
recorded min(30, phase remaining) limit. Phase work runs in this interpreter.
"""
from __future__ import annotations
import contextlib
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import shlex
import shutil
import signal
import subprocess
import sys
import tarfile
import time

import dualmic_gain_d2 as d2
import dualmic_zero_d3_source as admission

ROOT = d2.ROOT
EXPERIMENT = "FE-DUALMIC-UPSTREAM-D7"
FREEZE = "4b7f4496d9d9fef5589456f4ac377ddfa29e24e3"
BASE = "e348843a570503728930f06451633262b2546fa5"
BASE_TREE = "b420d795337483612bc02924e60f693166a5727f"
PREFIX = "tests/validation/frontend_evolution/"
C_PATH = PREFIX + "dualmic_upstream_d7.c"
PY_PATH = PREFIX + "dualmic_upstream_d7.py"
BUILD_PATH = PREFIX + "dualmic_upstream_d7_build.py"
TEST_PATH = PREFIX + "test_dualmic_upstream_d7.py"
PLAN = "docs/research/frontend-evolution-v1/DUALMIC_UPSTREAM_D7_PLAN.zh-CN.md"
LOCK = "docs/research/frontend-evolution-v1/dualmic-upstream-d7-input-lock.json"
PINS = {PLAN: "cfaccf4143263db3601be597f239d91472a33f3c",
        LOCK: "c34646ebf4210597a8d508134eadf0b0ab72a649"}
INPUT = Path("/tmp/ap-dualmic-d7/input")
OUTPUT = Path("/tmp/ap-dualmic-d7/result")
SOURCE_LIMIT = 16 * 1024 * 1024
OUTPUT_LIMIT = 512 * 1024 * 1024
SHA = re.compile(r"[0-9a-f]{40}\Z")
EXPLANATORY = {"tests/validation/build_dualmic_recorded_corpus.py",
               "validation/tools/hpf_aware_reference_oracle.py"}

def need(value, reason):
    if not value:
        raise ValueError(reason)

def read(path):
    return json.loads(Path(path).read_bytes())

def dump(path, value, *, replace=False, compact=False):
    with Path(path).open("w" if replace else "x", encoding="utf-8") as out:
        json.dump(value, out, indent=None if compact else 2, sort_keys=True, allow_nan=False)
        out.write("\n")

def digest(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for data in iter(lambda: f.read(1024 * 1024), b""):
            h.update(data)
    return h.hexdigest()

def desc(path):
    path = Path(path)
    need(path.is_file() and not path.is_symlink(), "D7_REGULAR_FILE")
    return {"bytes": path.stat().st_size, "sha256": digest(path)}

def blob(data):
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()

def directories(names):
    result = set()
    for name in names:
        p = PurePosixPath(name).parent
        while str(p) != ".":
            result.add(p.as_posix())
            p = p.parent
    return result

def inventory(root):
    files, dirs = {}, []
    need(root.is_dir() and not root.is_symlink(), "D7_OUTPUT_SYMLINK")
    for p in sorted(root.rglob("*")):
        need(not p.is_symlink(), "D7_OUTPUT_SYMLINK")
        name = p.relative_to(root).as_posix()
        if p.is_dir():
            dirs.append(name)
        else:
            need(p.is_file(), "D7_REGULAR_FILE")
            files[name] = desc(p)
    return {"files": files, "directories": dirs}

def exact_closure(root, files, reason, limit=SOURCE_LIMIT):
    actual = inventory(root)
    need(set(actual["files"]) == set(files) and set(actual["directories"]) == directories(files), reason)
    need(sum(x["bytes"] for x in actual["files"].values()) <= limit, "D7_SOURCE_BYTES_BOUND")
    return actual["files"]

def contract():
    for name, expected in PINS.items():
        need(blob((ROOT / name).read_bytes()) == expected, "D7_FROZEN_CONTRACT_CHANGED")
    lock = read(ROOT / LOCK)
    need(lock["experiment"] == EXPERIMENT and lock["base_sha"] == BASE and
         lock["base_tree"] == BASE_TREE and lock["candidates"] == 0, "D7_CONTRACT_IDENTITY")
    old = admission.frozen_lock()
    need(all(lock["original_admission"].get(k) == v for k, v in old.items()) and
         lock["original_d2_case_input_lock"] == d2.input_lock(), "D7_FULL_ORIGINAL_LOCK")
    for name, expected in lock["frozen_helper_files"].items():
        raw = (ROOT / name).read_bytes()
        need(blob(raw) == expected["git_blob"] and desc(ROOT / name) ==
             {k: expected[k] for k in ("bytes", "sha256")}, "D7_HELPER_IDENTITY")
    return lock

def environment(d1=None, d7=None):
    env = d2.d1.process_environment(d1)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    if d7 is not None:
        env["AP_D7_STAGE_DIR"] = str(d7)
    else:
        env.pop("AP_D7_STAGE_DIR", None)
    return env

class Phase:
    """Hard wall limit for in-process work; child commands are never 300s workers."""
    def __init__(self, name, root=OUTPUT):
        self.name, self.root = name, root
        self.started = None
        self.report = {"experiment": EXPERIMENT, "phase": name, "status": "FAIL",
                       "budget_seconds": 300, "commands": [], "first_failure": None}

    def remaining(self):
        left = 300.0 - (time.monotonic() - self.started)
        need(left > 0, "D7_PHASE_TIMEOUT:" + self.name)
        return left

    def _remember_failure(self, error, stage):
        self.report["status"] = "FAIL"
        if self.report["first_failure"] is None:
            self.report["first_failure"] = {
                "stage": stage, "type": type(error).__name__,
                "reason": str(error) if isinstance(error, (ValueError, TimeoutError)) else "phase failed"}
            if hasattr(error, "d7_build_flags"):
                self.report["first_failure"]["build_flags"] = error.d7_build_flags
            if hasattr(error, "d7_generated"):
                self.report["first_failure"]["generated"] = error.d7_generated
        # Carry the original failure to the root log even when later deadline
        # cleanup cannot safely perform any additional file writes.
        error.d7_first_failure = dict(self.report["first_failure"])
        error.d7_phase = self.name
        error.d7_target = str(self.path)

    def _preserve_failure(self):
        # Never extend the phase to hash/rewrite after hard expiry. The initial
        # incomplete receipt/partial logs survive; the original exception reaches
        # the job log. A successful prefix never qualifies a failed job. Cleanup
        # errors never replace the first failure.
        if not self.alarm_armed or time.monotonic() - self.started >= 300:
            return
        try:
            self.report["elapsed_seconds"] = time.monotonic() - self.started
            if self.owned_receipt:
                dump(self.path, self.report, replace=True)
                self.remaining()
            first_path = self.root / "first-failure.json"
            if not first_path.exists():
                dump(first_path, {"experiment": EXPERIMENT, "status": "MEASUREMENT_INVALID",
                     "phase": self.name, "target": str(self.path),
                     "first_failure": self.report["first_failure"], "promotion_allowed": False})
                self.remaining()
        except BaseException:
            pass

    def _restore_alarm(self):
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, self.old_handler)
        if self.old_timer[0] > 0:
            left = max(0.000001, self.old_timer[0] - (time.monotonic() - self.started))
            signal.setitimer(signal.ITIMER_REAL, left, self.old_timer[1])

    def __enter__(self):
        self.started = time.monotonic()
        self.path = self.root / (self.name + "-phase.json")
        self.logs = self.root / (self.name + "-logs")
        self.owned_receipt = False
        self.alarm_armed = False
        self.finalizer = None
        self.old_handler = signal.getsignal(signal.SIGALRM)
        self.old_timer = signal.getitimer(signal.ITIMER_REAL)
        try:
            signal.signal(signal.SIGALRM, self.alarm)
            # Arm before the first mkdir/open/write, not after the initial receipt.
            signal.setitimer(signal.ITIMER_REAL, self.remaining())
            self.alarm_armed = True
            self.root.mkdir(parents=True, exist_ok=True)
            need(not self.path.exists(), "D7_PHASE_ALREADY_EXISTS")
            self.logs.mkdir()
            with self.path.open("x", encoding="utf-8") as out:
                self.owned_receipt = True
                json.dump(self.report, out, indent=2, sort_keys=True, allow_nan=False)
                out.write("\n")
            self.remaining()
            return self
        except BaseException as error:
            self._remember_failure(error, "enter")
            try:
                self._preserve_failure()
            finally:
                with contextlib.suppress(BaseException):
                    self._restore_alarm()
            raise

    def alarm(self, signum, frame):
        raise TimeoutError("D7_PHASE_TIMEOUT:" + self.name)

    def __exit__(self, kind, error, tb):
        primary_error = error
        try:
            if error is not None:
                self._remember_failure(error, "body")
            self.remaining()
            if error is None:
                self.report["status"] = "PASS"
            self.report["elapsed_seconds"] = time.monotonic() - self.started
            self.report["elapsed_scope"] = (
                "through terminal receipt preparation; the same hard deadline "
                "also covers terminal receipt I/O and finalizer")
            dump(self.path, self.report, replace=True)
            self.remaining()
            # A terminal finalizer can bind the terminal phase receipt without
            # moving manifest/summary work outside this phase's hard deadline.
            if error is None and self.finalizer is not None:
                self.finalizer(self)
                self.remaining()
        except BaseException as terminal_error:
            primary_error = error if error is not None else terminal_error
            self._remember_failure(error if error is not None else terminal_error, "terminal")
            self._preserve_failure()
            if error is None:
                raise
            # Returning False below propagates the original body failure,
            # including a timeout, rather than a secondary cleanup exception.
        finally:
            try:
                self._restore_alarm()
            except BaseException as restore_error:
                if primary_error is None:
                    self._remember_failure(restore_error, "restore")
                    raise
                # The original body/terminal failure still propagates unchanged.
        return False

    def run(self, label, argv, *, cwd=ROOT, env=None):
        need(isinstance(argv, list) and all(type(x) is str for x in argv), "D7_ARGV_SCHEMA")
        prefix = self.logs / label
        stdout, stderr = Path(str(prefix) + ".stdout"), Path(str(prefix) + ".stderr")
        receipt_path = Path(str(prefix) + ".command.json")
        limit = min(30.0, self.remaining())
        begin = time.monotonic()
        receipt = {"argv": argv, "cwd": str(cwd), "timeout_seconds": limit,
                   "status": "FAIL", "returncode": None, "timed_out": False}
        effective_env = environment() if env is None else env
        receipt["environment"] = {"keys": sorted(effective_env), "LC_ALL": effective_env.get("LC_ALL"),
            "AP_D1_STAGE_DIR": effective_env.get("AP_D1_STAGE_DIR"),
            "AP_D7_STAGE_DIR": effective_env.get("AP_D7_STAGE_DIR")}
        receipt["lifecycle"] = "PENDING"
        dump(receipt_path, receipt)
        self.report["commands"].append(receipt_path.relative_to(self.root).as_posix())
        process = None
        try:
            with stdout.open("xb") as out, stderr.open("xb") as err:
                limit = min(30.0, self.remaining())
                receipt["timeout_seconds"] = limit
                process = subprocess.Popen(argv, cwd=cwd, env=effective_env,
                    stdout=out, stderr=err, start_new_session=True)
                try:
                    receipt["returncode"] = process.wait(timeout=limit)
                except subprocess.TimeoutExpired:
                    receipt["timed_out"] = True
                    raise TimeoutError("D7_COMMAND_TIMEOUT")
            need(receipt["returncode"] == 0, "D7_COMMAND_EXIT")
            receipt["status"] = "PASS"
        except BaseException as error:
            if process is not None and process.poll() is None:
                with contextlib.suppress(ProcessLookupError):
                    os.killpg(process.pid, signal.SIGKILL)
                process.wait(timeout=1)
            receipt["reason"] = str(error) if isinstance(error, (ValueError, TimeoutError)) else type(error).__name__
            if self.report["first_failure"] is None:
                self.report["first_failure"] = {"step": label, "type": type(error).__name__,
                                                "reason": receipt["reason"]}
            raise
        finally:
            # Keep the original FAIL/PENDING command receipt after phase expiry;
            # do not begin extra hashing or receipt I/O outside the hard budget.
            if time.monotonic() - self.started < 300:
                receipt["elapsed_seconds"] = time.monotonic() - begin
                receipt["lifecycle"] = "TERMINAL"
                receipt["stdout"] = desc(stdout) if stdout.is_file() else None
                receipt["stderr"] = desc(stderr) if stderr.is_file() else None
                dump(receipt_path, receipt, replace=True)
                self.remaining()
        self.remaining()
        return stdout.read_bytes()

def git(phase, label, *arguments):
    return phase.run(label, ["git", "-C", str(ROOT), *arguments])

def tree_entries(raw):
    result = {}
    for row in raw.split(b"\0"):
        if not row:
            continue
        meta, path = row.split(b"\t", 1)
        mode, kind, oid = meta.decode().split()
        name = path.decode()
        need(kind == "blob" and mode in ("100644", "100755") and
             name not in result, "D7_SOURCE_TREE")
        result[name] = {"git_mode": mode, "git_blob": oid}
    return result

def source_identity(phase):
    lock = contract()
    head = git(phase, "head", "rev-parse", "HEAD").decode().strip()
    tree = git(phase, "tree", "rev-parse", "HEAD^{tree}").decode().strip()
    need(SHA.fullmatch(head) and SHA.fullmatch(tree), "D7_SOURCE_TREE")
    need(git(phase, "base-tree", "rev-parse", BASE + "^{tree}").decode().strip() == BASE_TREE,
         "D7_SOURCE_TREE")
    need(not git(phase, "clean", "status", "--porcelain=v1", "--untracked-files=all").strip(),
         "D7_UNCOMMITTED_SOURCE")
    names = set(lock["production_files"]) | set(lock["frozen_helper_files"]) | set(lock["source_closure"]["D7_files"])
    current = tree_entries(git(phase, "selected-tree", "ls-tree", "-r", "-z", "--full-tree", head,
                              "--", *sorted(names)))
    need(set(current) == names, "D7_SOURCE_TREE")
    # Modes absent from the historical helper JSON are fixed by the immutable base tree.
    base = tree_entries(git(phase, "base-selected-tree", "ls-tree", "-r", "-z", "--full-tree", BASE,
                           "--", *sorted(set(lock["production_files"]) | set(lock["frozen_helper_files"]))))
    for name, record in lock["production_files"].items():
        need(current[name] == base[name] == {k: record[k] for k in ("git_mode", "git_blob")},
             "D7_PRODUCTION_CHANGED")
    for name, record in lock["frozen_helper_files"].items():
        need(current[name] == base[name] and base[name]["git_blob"] == record["git_blob"],
             "D7_HELPER_MODE_OR_BLOB")
    # Tree roots prove that no new production file was silently omitted.
    for i, (name, record) in enumerate(lock["unchanged_production_objects"].items()):
        need(git(phase, "production-root-" + str(i), "rev-parse", head + ":" + name).decode().strip()
             == record["git_object"], "D7_PRODUCTION_CHANGED")
    for name in names:
        need(blob((ROOT / name).read_bytes()) == current[name]["git_blob"], "D7_UNCOMMITTED_SOURCE")
        current[name].update(desc(ROOT / name))
    need(sum(x["bytes"] for x in current.values()) <= SOURCE_LIMIT, "D7_SOURCE_BYTES_BOUND")
    historical = git(phase, "historical-workflow", "show", BASE + ":.github/workflows/frontend-research.yml").decode()
    current_workflow = (ROOT / ".github/workflows/frontend-research.yml").read_text()
    marker = "\n  dualmic-upstream-d7:\n"
    need(current_workflow.count(marker) == 1 and historical.split("  matrix:\n", 1)[1] ==
         current_workflow.split("  matrix:\n", 1)[1].split(marker, 1)[0],
         "D7_HISTORICAL_JOBS_CHANGED")
    for module in list(sys.modules.values()):
        path = getattr(module, "__file__", None)
        if path:
            try:
                name = Path(path).resolve().relative_to(ROOT).as_posix()
            except ValueError:
                continue
            need(name in names and name not in EXPLANATORY, "D7_RUNTIME_IMPORT_CLOSURE:" + name)
    return {"revision": head, "tree": tree, "files": current}

def archive_members(path, identity, destination=None):
    names = set(identity["files"])
    seen_files, seen_dirs, total = set(), set(), 0
    with tarfile.open(path, "r:") as archive:
        need(archive.pax_headers.get("comment") == identity["revision"], "D7_SOURCE_ARCHIVE_REVISION")
        for member in archive:
            name = member.name.rstrip("/")
            pure = PurePosixPath(name)
            need(name and pure.as_posix() == name and not pure.is_absolute() and ".." not in pure.parts
                 and "\\" not in name and (member.isfile() or member.isdir()), "D7_SOURCE_ARCHIVE_PATH")
            if member.isdir():
                need(name not in seen_dirs, "D7_SOURCE_ARCHIVE_DUPLICATE")
                seen_dirs.add(name)
                if destination is not None:
                    (destination / name).mkdir(parents=True, exist_ok=True)
                continue
            need(name in names and name not in seen_files, "D7_SOURCE_CLOSURE")
            seen_files.add(name)
            spec = identity["files"][name]
            need(member.size == spec["bytes"] and member.mode & 0o777 == int(spec["git_mode"], 8) & 0o777,
                 "D7_SOURCE_ARCHIVE_MODE")
            total += member.size
            need(total <= SOURCE_LIMIT, "D7_SOURCE_BYTES_BOUND")
            f = archive.extractfile(member)
            need(f is not None, "D7_SOURCE_ARCHIVE_MEMBER")
            raw = f.read(member.size + 1)
            need(len(raw) == member.size and blob(raw) == spec["git_blob"] and
                 hashlib.sha256(raw).hexdigest() == spec["sha256"], "D7_SOURCE_RESEALED")
            if destination is not None:
                target = destination / name
                target.parent.mkdir(parents=True, exist_ok=True)
                with target.open("xb") as out:
                    out.write(raw)
                target.chmod(member.mode & 0o777)
    need(seen_files == names and seen_dirs == directories(names), "D7_SOURCE_CLOSURE")

def transformed(raw, spec):
    before, after = spec["before"].encode(), spec["after"].encode()
    need(raw.count(before) == 1 and after not in raw, "D7_TRANSFORM_SITE")
    changed = raw.replace(before, after, 1)
    need(changed.replace(after, before, 1) == raw, "D7_TRANSFORM_BODY")
    return changed

def check_sources(build_root, identity):
    names = identity["files"]
    plain, observer = build_root / "plain-source", build_root / "observer-source"
    exact_closure(plain, names, "D7_SOURCE_CLOSURE")
    exact_closure(observer, names, "D7_SOURCE_CLOSURE")
    specs = {s["path"]: s for s in contract()["observer"]["source_transforms"]}
    for name, spec in names.items():
        need((plain / name).stat().st_mode & 0o777 == int(spec["git_mode"], 8) & 0o777 and
             (observer / name).stat().st_mode & 0o777 == int(spec["git_mode"], 8) & 0o777,
             "D7_SOURCE_MODE")
        original = (plain / name).read_bytes()
        need(blob(original) == spec["git_blob"] and desc(plain / name) ==
             {k: spec[k] for k in ("bytes", "sha256")}, "D7_SOURCE_RESEALED")
        expected = transformed(original, specs[name]) if name in specs else original
        reason = "D7_OBSERVER_ENTRY" if name.endswith("dualmic_stages_d1.c") else "D7_TRANSFORM_BODY"
        need((observer / name).read_bytes() == expected, reason)
    return [{"path": name, "before_sha256": names[name]["sha256"],
             "after_sha256": digest(observer / name),
             "inverse_sha256": hashlib.sha256((observer / name).read_bytes().replace(
                 spec["after"].encode(), spec["before"].encode(), 1)).hexdigest()}
            for name, spec in specs.items()]

def tool_identity(name):
    lookup = shutil.which(name)
    need(lookup is not None, "D7_TOOL_MISSING")
    path = Path(lookup).absolute()
    real = path.resolve(strict=True)
    return {"lookup_path": str(path), "lookup_symlink_target": os.readlink(path) if path.is_symlink() else None,
            "resolved_path": str(real), "file": desc(real)}

def configure_argv(cmake, compiler, source, build, revision):
    return [cmake, "-S", str(source), "-B", str(build), "-G", "Unix Makefiles",
        "-DCMAKE_BUILD_TYPE=Release", "-DCMAKE_C_COMPILER=" + compiler, "-DCMAKE_C_FLAGS=",
        "-DCMAKE_C_FLAGS_RELEASE=-O3 -DNDEBUG", "-DCMAKE_EXPORT_COMPILE_COMMANDS=ON",
        "-DAP_BUILD_PIPELINE=ON", "-DAP_BUILD_TESTS=OFF", "-DAP_BUILD_BENCH=OFF",
        "-DAP_BUILD_EXAMPLES=ON", "-DAP_BUILD_ALSA_EXAMPLE=OFF", "-DAP_BUILD_FUZZ=OFF",
        "-DAP_STRICT_WARNINGS=ON", "-DAP_ENABLE_FAST_MATH=OFF", "-DAP_AEC_BACKEND=MDF",
        "-DAP_NS_ESTIMATOR=EMA", "-DAP_SIMD_BACKEND=SCALAR", "-DAP_RESAMPLER_MODE=BANDLIMITED",
        "-DAP_BUILD_SOURCE_REVISION=" + revision]

# Exact generator orderings, not set/subset acceptance. CMake 3.25.3 adds
# the standard in AddCompileOptions after target options; CMake 3.31.6 and
# 4.1.2 add it in AddLanguageFlags before target options. All seven tokens,
# multiplicities and each complete sequence are fixed; actual order is retained.
C_FLAG_SEQUENCES = (
    ("-O3", "-DNDEBUG", "-Wall", "-Wextra", "-Wpedantic", "-Werror", "-std=c11"),
    ("-O3", "-DNDEBUG", "-std=c11", "-Wall", "-Wextra", "-Wpedantic", "-Werror"),
)

def flags_error(category, observed, expected):
    detail = {"category": category, "observed": observed, "expected": expected}
    encoded = json.dumps(detail, ensure_ascii=True, sort_keys=True)
    if len(encoded) > 4096:
        detail = {"category": category, "detail_truncated": True,
                  "prefix": encoded[:3072], "full_observation": "retained flags.make"}
    error = ValueError("D7_BUILD_FLAGS")
    error.d7_build_flags = detail
    raise error

def parse_flags(text, build):
    result = {}
    for key in ("C_DEFINES", "C_INCLUDES", "C_FLAGS"):
        values = [line.split("=", 1)[1].strip() for line in text.splitlines() if line.startswith(key + " =")]
        if len(values) != 1:
            flags_error("parse", {"field": key, "assignments": values}, "exactly one assignment")
        try:
            result[key] = shlex.split(values[0])
        except ValueError:
            flags_error("parse", {"field": key, "assignment": values[0]}, "valid shell token quoting")
    required = {"-DAP_BUILD_STAGE_HPF=1", "-DAP_BUILD_STAGE_BF=1", "-DAP_BUILD_STAGE_SYNC=1",
                "-DAP_BUILD_BF_DIRECTION_TRACKING=1", "-DAP_BUILD_ACTIVITY=1",
                "-DAP_BUILD_STAGE_AEC=1", "-DAP_BUILD_STAGE_RES=1", "-DAP_BUILD_STAGE_NS=1",
                "-DAP_BUILD_STAGE_AGC=1", "-DAP_BUILD_AEC_MDF=1", "-DAP_BUILD_STAGE_VAD=1",
                "-DAP_BUILD_NS_EMA=1", "-DAP_BUILD_RESAMPLER_BANDLIMITED=1"}
    if required != set(result["C_DEFINES"]) or len(result["C_DEFINES"]) != len(required):
        flags_error("defines", result["C_DEFINES"], sorted(required))
    if tuple(result["C_FLAGS"]) not in C_FLAG_SEQUENCES:
        flags_error("flags", result["C_FLAGS"], C_FLAG_SEQUENCES)
    kind = build.name.removesuffix("-build")
    source = build.parent / (kind + "-source")
    includes = ["-I" + str(build / "generated"), "-I" + str(source / "include"),
                "-I" + str(source / "src")]
    if result["C_INCLUDES"] != includes:
        flags_error("includes", result["C_INCLUDES"], includes)
    return result

def flags(build):
    path = build / "CMakeFiles/audio_pipeline.dir/flags.make"
    try:
        return parse_flags(path.read_text(), build)
    except ValueError as error:
        if str(error) == "D7_BUILD_FLAGS":
            # No extra I/O here: the existing phase/root failure path persists
            # and prints this bounded detail without changing the first reason.
            error.d7_build_flags.update({
                "target": str(path),
                "cmake_version_receipt": str(OUTPUT / "plain-build-logs/cmake-version.command.json"),
                "cmake_version_stdout": str(OUTPUT / "plain-build-logs/cmake-version.stdout"),
                "configure_receipt": str(OUTPUT / (build.name + "-logs/configure.command.json")),
                "actual_argv": str(build / "compile_commands.json")})
        raise

def observer_argv(compiler, source, build, actual_flags):
    return [compiler, *actual_flags["C_DEFINES"], *actual_flags["C_INCLUDES"],
            *actual_flags["C_FLAGS"], "-MMD", "-MF", str(build / "observer.d"),
            str(source / C_PATH), str(build / "libaudio_pipeline.a"),
            "-lm", "-o", str(build / "ap_process_pcm_observer")]

def check_command(path, argv=None):
    receipt = read(path)
    need(receipt["status"] == "PASS" and receipt["lifecycle"] == "TERMINAL" and
         receipt["returncode"] == 0 and receipt["timed_out"] is False
         and 0 < receipt["timeout_seconds"] <= 30 and 0 <= receipt["elapsed_seconds"] <= 30,
         "D7_FAILED_COMMAND")
    if argv is not None:
        need(receipt["argv"] == argv, "D7_ARGV")
    prefix = str(path).removesuffix(".command.json")
    need(desc(Path(prefix + ".stdout")) == receipt["stdout"] and
         desc(Path(prefix + ".stderr")) == receipt["stderr"], "D7_COMMAND_LOG")
    return receipt

def check_phase_record(value, name):
    need(value["phase"] == name and value["status"] == "PASS" and value["budget_seconds"] == 300
         and value["first_failure"] is None and 0 <= value["elapsed_seconds"] <= 300,
         "D7_FAILED_PHASE:" + name)

def check_phase(root, name):
    value = read(root / (name + "-phase.json"))
    check_phase_record(value, name)
    for p in value["commands"]:
        check_command(root / p)
    return value

# Derived from the pinned CMakeLists.txt AP_SOURCES append order with all
# frozen modules enabled, MDF/EMA/SCALAR, batch32 and module SKIP_UNITY set.
UNITY_SOURCES = (
    "src/ap_build_info.c", "src/core/ap_pipeline.c", "src/core/ap_pipeline_query.c",
    "src/frontend/ap_resampler.c", "src/frontend/ap_hpf.c", "src/frontend/ap_beamformer.c",
    "src/sync/ap_sync.c", "src/activity/ap_activity.c", "src/enhance/ap_res.c",
    "src/enhance/ap_ns.c", "src/enhance/ap_noise_tracker.c", "src/enhance/ap_window.c",
    "src/enhance/ap_agc.c", "src/enhance/ap_vad.c", "src/aec/ap_aec_mdf.c",
    "src/arch/scalar/ap_kernels_scalar.c", "src/dsp/ap_fft.c",
)
UNITY_NAME = "CMakeFiles/audio_pipeline.dir/Unity/unity_0_c.c"
UNITY_COMMENTS = (
    "",
    "/* NOLINTNEXTLINE(bugprone-suspicious-include,misc-include-cleaner) */\n",
)

def generated_error(reason, category, target, observed, expected):
    detail = {"category": category, "target": str(target),
              "observed": observed, "expected": expected}
    encoded = json.dumps(detail, ensure_ascii=True, sort_keys=True)
    if len(encoded) > 4096:
        detail = {"category": category, "target": str(target),
                  "detail_truncated": True, "prefix": encoded[:2048]}
    detail["cmake_version_receipt"] = str(OUTPUT / "plain-build-logs/cmake-version.command.json")
    error = ValueError(reason)
    error.d7_generated = detail
    raise error

def generated_unity(path, source, identity):
    expected_path = source.parent / (source.name.removesuffix("-source") + "-build") / UNITY_NAME
    need(path == expected_path, "D7_COMPILED_SOURCE_CLOSURE")
    need(identity["files"]["CMakeLists.txt"]["git_blob"] == "a2bda471593f32fcd96470d828839aedf286273e" and
         all(name in identity["files"] for name in UNITY_SOURCES), "D7_COMPILED_SOURCE_CLOSURE")
    # Whole-document equality: no generic comment removal, regex remainder
    # stripping, arbitrary statements, reordered/duplicate/subset includes,
    # alternate paths, BOM or whitespace normalization.
    expected = [
        ("/* generated by CMake */\n\n" + "".join(
            comment + '#include "' + str(source / name) + '"\n\n'
            for name in UNITY_SOURCES)).encode()
        for comment in UNITY_COMMENTS]
    raw = path.read_bytes()
    if raw not in expected:
        generated_error("D7_GENERATED_UNITY", "unity", path,
            {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest(),
             "prefix": raw[:1024].decode("utf-8", errors="backslashreplace")},
            {"whole_document_sha256": [hashlib.sha256(v).hexdigest() for v in expected],
             "ordered_sources": UNITY_SOURCES, "comment_forms": UNITY_COMMENTS})
    return {"path": UNITY_NAME, **desc(path), "form": expected.index(raw),
            "ordered_sources": list(UNITY_SOURCES)}


def compiler_search_roots(stderr):
    lines = stderr.splitlines()
    start, end = "#include <...> search starts here:", "End of search list."
    if lines.count(start) != 1 or lines.count(end) != 1 or lines.index(start) >= lines.index(end):
        generated_error("D7_COMPILER_SEARCH", "compiler-search", "compiler-header-search.stderr",
                        lines[:12], "one complete GCC system include search section")
    entries = lines[lines.index(start)+1:lines.index(end)]
    result = []
    for line in entries:
        raw = line.strip()
        path = Path(raw)
        need(line.startswith(" ") and path.is_absolute() and path.is_dir(), "D7_COMPILER_SEARCH")
        real = path.resolve(strict=True)
        need(real.is_relative_to(Path("/usr")) and real != Path("/usr"), "D7_COMPILER_SEARCH")
        need(str(real) not in [row["canonical"] for row in result], "D7_COMPILER_SEARCH")
        result.append({"raw": raw, "canonical": str(real)})
    need(result, "D7_COMPILER_SEARCH")
    return result

def system_roots():
    # Receipt is validated here and again against the exact resolved compiler
    # argv by verify_build. No arbitrary external dependency is called "system".
    path = OUTPUT / "plain-build-logs/compiler-header-search.command.json"
    receipt = check_command(path)
    need(receipt["argv"][1:] == ["-E", "-x", "c", "/dev/null", "-v"], "D7_COMPILER_SEARCH")
    return compiler_search_roots(path.with_name("compiler-header-search.stderr").read_text())

def _dependency_path(word, source, build, identity, roots, cwd):
    raw = Path(word)
    path = raw if raw.is_absolute() else cwd / raw
    for scope, root in (("source", source), ("generated", build)):
        if not path.is_relative_to(root):
            continue
        # Process every original component in order, rejecting a symlink even
        # when followed by '..'. Never leave a frozen root and then re-enter.
        cursor = root
        if root.is_symlink() or root.resolve(strict=True) != root:
            generated_error("D7_DEPENDENCY_SYMLINK", "dependency", word, str(root), "ordinary root")
        for part in path.relative_to(root).parts:
            if part == "..":
                if cursor == root:
                    generated_error("D7_DEPENDENCY_ESCAPE", "dependency", word, str(path), str(root))
                need(cursor.is_dir(), "D7_DEPENDENCY_REGULAR")
                cursor = cursor.parent
            elif part != ".":
                need(cursor.is_dir(), "D7_DEPENDENCY_REGULAR")
                cursor = cursor / part
                if cursor.is_symlink():
                    generated_error("D7_DEPENDENCY_SYMLINK", "dependency", word, str(cursor), "no symlink")
        need(cursor.is_file() and cursor.resolve(strict=True) == cursor, "D7_DEPENDENCY_REGULAR")
        name = cursor.relative_to(root).as_posix()
        if scope == "source":
            need(name in identity["files"], "D7_COMPILED_SOURCE_CLOSURE")
        else:
            need(name in ("generated/audio_pipeline/audio_pipeline_build.h", UNITY_NAME),
                 "D7_GENERATED_HEADER_CLOSURE")
            if name == UNITY_NAME:
                generated_unity(cursor, source, identity)
        return {"raw": word, "scope": scope, "canonical": str(cursor), "member": name}
    # System headers are not claimed as part of the historical source closure.
    # GCC canonicalizes these separately; require both raw and canonical paths
    # to stay in its observed search roots. This cannot authorize repo escapes.
    allowed = [Path(row["canonical"]) for row in roots]
    if not any(path.is_relative_to(root) for root in allowed):
        generated_error("D7_DEPENDENCY_OUTSIDE", "dependency", word, str(path),
                        "frozen source/generated member or observed compiler system root")
    real = path.resolve(strict=True)
    need(real.is_file() and any(real.is_relative_to(root) for root in allowed),
         "D7_DEPENDENCY_OUTSIDE")
    return {"raw": word, "scope": "system", "canonical": str(real)}


def dependency_path(word, source, build, identity, roots, cwd):
    try:
        return _dependency_path(word, source, build, identity, roots, cwd)
    except ValueError as error:
        if str(error).startswith("D7_") and not hasattr(error, "d7_generated"):
            detail = {"category": "dependency", "raw": word, "source": str(source),
                      "build": str(build), "cwd": str(cwd), "system_roots": roots}
            encoded = json.dumps(detail, ensure_ascii=True, sort_keys=True)
            if len(encoded) > 4096:
                detail = {"category": "dependency", "detail_truncated": True, "prefix": encoded[:2048]}
            error.d7_generated = detail
        raise

def check_compile_closure(build_root, identity, kind):
    source, build = build_root / (kind + "-source"), build_root / (kind + "-build")
    commands = read(build / "compile_commands.json")
    need(commands and all(type(row) is dict for row in commands), "D7_COMPILE_COMMANDS")
    for row in commands:
        need(row["directory"] == str(build), "D7_COMPILED_SOURCE_CLOSURE")
        try:
            name = Path(row["file"]).relative_to(source).as_posix()
        except ValueError:
            name = Path(row["file"]).relative_to(build).as_posix()
            need(re.fullmatch(r"CMakeFiles/audio_pipeline.dir/Unity/unity_[0-9]+_c.c", name),
                 "D7_COMPILED_SOURCE_CLOSURE")
            generated_unity(Path(row["file"]), source, identity)
        else:
            need(name in identity["files"], "D7_COMPILED_SOURCE_CLOSURE")
        argv = shlex.split(row["command"])
        need("-ffast-math" not in argv, "D7_BUILD_FLAGS")
    # Make's generated dependency files explicitly retain every repository header.
    dependencies = list(build.rglob("*.o.d"))
    if kind == "observer":
        need((build / "observer.d").is_file(), "D7_HEADER_DEPENDENCIES")
        dependencies.append(build / "observer.d")
    need(dependencies, "D7_HEADER_DEPENDENCIES")
    roots = system_roots()
    dependency_members = {}
    for dep in dependencies:
        words = shlex.split(dep.read_text().replace("\\\n", " "))
        need(len(words) >= 2 and words[0].endswith(":"), "D7_HEADER_DEPENDENCIES")
        cwd = ROOT if dep.name == "observer.d" else build
        dependency_members[dep.relative_to(build).as_posix()] = [
            dependency_path(word, source, build, identity, roots, cwd) for word in words[1:]]
    return {"compile_commands": desc(build / "compile_commands.json"),
            "system_search_roots": roots, "dependency_members": dependency_members,
            "dependency_files": {p.relative_to(build).as_posix(): desc(p) for p in dependencies}}

def build(expected_revision):
    root = OUTPUT / "build"
    root.mkdir()
    report = {"experiment": EXPERIMENT, "status": "FAIL", "programs": {}, "commands": {}}
    with Phase("plain-build") as phase:
        identity = source_identity(phase)
        need(identity["revision"] == expected_revision, "D7_EXECUTION_HEAD")
        report["source"] = identity
        report["compiler"], report["cmake"] = tool_identity("cc"), tool_identity("cmake")
        compiler, cmake = report["compiler"]["resolved_path"], report["cmake"]["resolved_path"]
        version_text = phase.run("compiler-version", [compiler, "--version"]).decode()
        compiler_version = phase.run("compiler-full-version", [compiler, "-dumpfullversion"]).decode().strip()
        compiler_target = phase.run("compiler-target", [compiler, "-dumpmachine"]).decode().strip()
        need("Free Software Foundation" in version_text, "D7_COMPILER_FAMILY")
        phase.run("cmake-version", [cmake, "--version"])
        phase.run("compiler-header-search", [compiler, "-E", "-x", "c", "/dev/null", "-v"])
        report["system_search_roots"] = system_roots()
        import test_dualmic_upstream_d7 as tests
        report["engineering_flags"] = tests.engineering_flags(phase)
        report["engineering_generated"] = tests.engineering_generated(phase, identity)
        archive = root / "exact-source.tar"
        phase.run("archive", ["git", "-C", str(ROOT), "-c", "tar.umask=0022", "archive", "--format=tar", "--output=" + str(archive),
                              identity["revision"], "--", *sorted(identity["files"])])
        for kind in ("plain", "observer"):
            destination = root / (kind + "-source")
            destination.mkdir()
            archive_members(archive, identity, destination)
        report["source_archive"] = desc(archive)
        source, binary = root / "plain-source", root / "plain-build"
        argv = configure_argv(cmake, compiler, source, binary, identity["revision"])
        phase.run("configure", argv)
        phase.run("compile", [cmake, "--build", str(binary), "--target", "ap_process_pcm",
                              "ap_build_info_dump", "--parallel", "2", "--verbose"])
        info_rows = phase.run("build-info", [str(binary / "ap_build_info_dump")]).decode().splitlines()
        need(all("=" in s for s in info_rows), "D7_BUILD_INFO")
        info = dict(s.split("=", 1) for s in info_rows)
        expected = {"source_revision": identity["revision"], "version": "2.3.64", "module_mask": "1023",
                    "aec_backend": "MDF", "ns_estimator": "EMA", "simd_backend": "SCALAR",
                    "fast_math": "0", "resampler_mode": "BANDLIMITED", "build_type": "Release"}
        need(all(info.get(k) == v for k, v in expected.items()), "D7_BUILD_INFO")
        need(info["compiler_id"] == "GNU" and info["compiler_version"] == compiler_version and
             info["target_triple"] == compiler_target, "D7_COMPILER_IDENTITY")
        report["build_info"] = info
        report["plain_flags"] = flags(binary)
        report["plain_dependencies"] = check_compile_closure(root, identity, "plain")
        report["programs"]["plain"] = {"path": "build/plain-build/ap_process_pcm",
                                        **desc(binary / "ap_process_pcm")}
    with Phase("observer-build") as phase:
        source, binary = root / "observer-source", root / "observer-build"
        for spec in contract()["observer"]["source_transforms"]:
            p = source / spec["path"]
            p.write_bytes(transformed(p.read_bytes(), spec))
        revision = identity["revision"] + "-D7-observer"
        phase.run("configure", configure_argv(cmake, compiler, source, binary, revision))
        phase.run("compile", [cmake, "--build", str(binary), "--target", "audio_pipeline",
                              "--parallel", "2", "--verbose"])
        actual = flags(binary)
        need(actual["C_DEFINES"] == report["plain_flags"]["C_DEFINES"] and
             actual["C_FLAGS"] == report["plain_flags"]["C_FLAGS"], "D7_BUILD_FLAGS")
        report["observer_flags"] = actual
        phase.run("observer", observer_argv(compiler, source, binary, actual))
        engineering = json.loads(phase.run("engineering", [str(binary / "ap_process_pcm_observer"), "--d7-self-test"]))
        need(engineering == {"status": "PASS", "comparisons": 840, "layout_checked": True, "negative_checks": 8}, "D7_ENGINEERING")
        report["engineering"] = engineering
        import test_dualmic_upstream_d7 as tests
        report["engineering_supervisor"] = tests.engineering_supervisor(phase)
        report["observer_dependencies"] = check_compile_closure(root, identity, "observer")
        report["programs"]["observer"] = {"path": "build/observer-build/ap_process_pcm_observer",
                                           **desc(binary / "ap_process_pcm_observer")}
        report["transforms"] = check_sources(root, identity)
        report["status"] = "BUILT"
        report["artifact_inventory"] = inventory(root)
        dump(root / "build.json", report)
        check_headers(root, identity["revision"])
    return report

def header_expected(root, revision, info):
    modules = "RESAMPLER,HPF,BF,SYNC,ACTIVITY,AEC,RES,NS,AGC,VAD"
    config = [("version", "2.3.64"), ("modules", modules), ("pipeline", "ON"),
        ("linux_runtime", "ON"), ("fast_math", "OFF"), ("bf_direction_tracking", "1"),
        ("max_io_rate", "48000"), ("max_internal_rate", "16000"), ("max_mics", "2"),
        ("max_delay_ms", "300"), ("max_aec_tail_ms", "120"), ("runtime_queue_depth", "8"),
        ("aec_backend", "MDF"), ("ns_estimator", "EMA"), ("simd_backend", "SCALAR"),
        ("resampler_mode", "BANDLIMITED"), ("compiler_id", info["compiler_id"]),
        ("compiler_version", info["compiler_version"]), ("target", info["target_triple"]),
        ("build_type", "Release"), ("c_flags", ""), ("build_flags", "-O3 -DNDEBUG")]
    config_digest = hashlib.sha256("".join(k + "=" + v + "\n" for k, v in config).encode()).hexdigest()
    need(info["config_digest"] == config_digest, "D7_HEADER_RESEALED")
    values = {"PROJECT_VERSION_MAJOR": "2", "PROJECT_VERSION_MINOR": "3", "PROJECT_VERSION_PATCH": "64",
        "PROJECT_VERSION": "2.3.64", "AP_HAVE_PIPELINE": "1", "AP_HAVE_LINUX_RUNTIME": "1",
        "AP_HAVE_BF_DIRECTION_TRACKING": "1", "AP_HAVE_FAST_MATH": "0",
        "AP_BUILD_MAX_IO_RATE_HZ": "48000", "AP_BUILD_MAX_INTERNAL_RATE_HZ": "16000",
        "AP_BUILD_MAX_MIC_CHANNELS": "2", "AP_BUILD_MAX_DELAY_MS": "300",
        "AP_BUILD_MAX_AEC_TAIL_MS": "120", "AP_RUNTIME_QUEUE_DEPTH": "8",
        "AP_BUILD_IO_FRAME_MAX": "480", "AP_BUILD_INTERNAL_FRAME_MAX": "160",
        "AP_BUILD_RENDER_CAP": "8192", "AP_BUILD_AEC_CAP": "1920", "AP_BUILD_AEC_PARTITIONS_MAX": "60",
        "AP_AEC_BACKEND": "MDF", "AP_NS_ESTIMATOR": "EMA", "AP_SIMD_BACKEND": "SCALAR",
        "AP_RESAMPLER_MODE": "BANDLIMITED", "AP_BUILD_SOURCE_REVISION": revision,
        "CMAKE_C_COMPILER_ID": info["compiler_id"], "CMAKE_C_COMPILER_VERSION": info["compiler_version"],
        "AP_BUILD_TARGET_TRIPLE": info["target_triple"], "AP_BUILD_TYPE_NAME": "Release",
        "AP_BUILD_CONFIG_DIGEST": config_digest}
    values.update({"AP_HAVE_" + name: "1" for name in modules.split(",")})
    template = (root / "plain-source/cmake/audio_pipeline_build.h.in").read_text()
    names = re.findall(r"@([A-Z_a-z0-9]+)@", template)
    need(set(names) == set(values), "D7_HEADER_RESEALED")
    for name, value in values.items():
        template = template.replace("@" + name + "@", value)
    return template.encode()

def check_headers(root, revision):
    relative = "generated/audio_pipeline/audio_pipeline_build.h"
    left = (root / "plain-build" / relative).read_bytes()
    right = (root / "observer-build" / relative).read_bytes()
    info = read(root / "build.json")["build_info"]
    need(left == header_expected(root, revision, info) and right == header_expected(
         root, revision + "-D7-observer", info), "D7_HEADER_RESEALED")
    observer = (revision + "-D7-observer").encode()
    need(right.count(observer) == 1 and right.replace(observer, revision.encode(), 1) == left,
         "D7_HEADER_RESEALED")

def check_source_identity(saved, actual):
    need(saved == actual, "D7_SOURCE_TREE")

def check_compiler_identity(compiler, cmake):
    need(compiler == tool_identity("cc") and cmake == tool_identity("cmake"), "D7_COMPILER_IDENTITY")

def verify_build(phase):
    report = read(OUTPUT / "build/build.json")
    identity = source_identity(phase)
    check_source_identity(report["source"], identity)
    need(report["status"] == "BUILT", "D7_FAILED_BUILD")
    check_compiler_identity(report["compiler"], report["cmake"])
    flags_tests = read(OUTPUT / "plain-build-logs/flags-probes/receipt.json")
    need(flags_tests == report["engineering_flags"] and flags_tests["status"] == "PASS" and
         flags_tests["accepted_sequences"] == 2 and flags_tests["rejected_fixtures"] == 105 and
         flags_tests["first_failure_preserved"] is True, "D7_ENGINEERING_FLAGS")
    root = OUTPUT / "build"
    measured_inventory = inventory(root)
    del measured_inventory["files"]["build.json"]
    need(measured_inventory == report["artifact_inventory"], "D7_BUILD_CLOSURE")
    archive_members(root / "exact-source.tar", identity)
    check_command(OUTPUT / "plain-build-logs/archive.command.json",
        ["git", "-C", str(ROOT), "-c", "tar.umask=0022", "archive", "--format=tar",
         "--output=" + str(root / "exact-source.tar"), identity["revision"], "--", *sorted(identity["files"])])
    need(desc(root / "exact-source.tar") == report["source_archive"], "D7_SOURCE_ARCHIVE_HASH")
    need(check_sources(root, identity) == report["transforms"], "D7_TRANSFORM_BODY")
    check_headers(root, identity["revision"])
    compiler, cmake = report["compiler"]["resolved_path"], report["cmake"]["resolved_path"]
    for label, command in (("compiler-version", [compiler, "--version"]),
                           ("compiler-full-version", [compiler, "-dumpfullversion"]),
                           ("compiler-target", [compiler, "-dumpmachine"]),
                           ("cmake-version", [cmake, "--version"]),
                           ("compiler-header-search", [compiler, "-E", "-x", "c", "/dev/null", "-v"])):
        check_command(OUTPUT / ("plain-build-logs/" + label + ".command.json"), command)
    need(report["build_info"]["compiler_id"] == "GNU" and
         report["build_info"]["compiler_version"] == (OUTPUT / "plain-build-logs/compiler-full-version.stdout").read_text().strip() and
         report["build_info"]["target_triple"] == (OUTPUT / "plain-build-logs/compiler-target.stdout").read_text().strip(),
         "D7_COMPILER_IDENTITY")
    need(system_roots() == report["system_search_roots"], "D7_COMPILER_SEARCH")
    generated_tests = read(OUTPUT / "plain-build-logs/generated-probes/receipt.json")
    need(generated_tests == report["engineering_generated"] and generated_tests["status"] == "PASS" and
         generated_tests["fixture_count"] == 110 and generated_tests["compiler_search_fixture_count"] == 15 and
         generated_tests["first_failure_preserved"] is True,
         "D7_ENGINEERING_GENERATED")
    for kind in ("plain", "observer"):
        check_phase(OUTPUT, kind + "-build")
        binary, source = root / (kind + "-build"), root / (kind + "-source")
        revision = identity["revision"] + ("-D7-observer" if kind == "observer" else "")
        need(flags(binary) == report[kind + "_flags"], "D7_BUILD_FLAGS")
        check_command(OUTPUT / (kind + "-build-logs/configure.command.json"),
                      configure_argv(cmake, compiler, source, binary, revision))
        targets = ["ap_process_pcm", "ap_build_info_dump"] if kind == "plain" else ["audio_pipeline"]
        check_command(OUTPUT / (kind + "-build-logs/compile.command.json"),
                      [cmake, "--build", str(binary), "--target", *targets, "--parallel", "2", "--verbose"])
        need(check_compile_closure(root, identity, kind) == report[kind + "_dependencies"],
             "D7_COMPILED_SOURCE_CLOSURE")
        program = report["programs"][kind]
        need(desc(OUTPUT / program["path"]) == {k: program[k] for k in ("bytes", "sha256")},
             "D7_PROGRAM_IDENTITY")
    check_command(OUTPUT / "observer-build-logs/observer.command.json",
        observer_argv(compiler, root / "observer-source", root / "observer-build", report["observer_flags"]))
    need(read(OUTPUT / "observer-build-logs/engineering.command.json")["status"] == "PASS",
         "D7_ENGINEERING")
    return report