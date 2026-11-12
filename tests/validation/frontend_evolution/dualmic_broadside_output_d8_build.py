#!/usr/bin/env python3
"""D8 exact-current four-form builder and fail-closed evidence primitives.

Derived parsers preserve the frozen D7 complete flag/Unity acceptance forms.
No historical builder or zero-candidate contract is changed or bypassed.
All actual execution remains a separately authorized GitHub Actions operation.
"""
from __future__ import annotations
import contextlib
import ctypes
import errno
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath
import platform
import resource
import re
import selectors
import shlex
import shutil
import signal
import stat
import struct
import subprocess
import sys
import tarfile
import time

sys.dont_write_bytecode = True
import dualmic_broadside_output_d8_supervise as supervision
import dualmic_gain_d2 as d2
import dualmic_zero_d3_source as admission

ROOT = d2.ROOT
EXPERIMENT = "FE-DUALMIC-BROADSIDE-OUTPUT-D8"
FREEZE = "8e3f92af6c4b0d3205a6903e8de31e55c0225a9e"
FREEZE_TREE = "8e60f7cc264a9ea2908b504549dd0a5a1bd46f74"
BASE = "1b5b01e0f2580ec9e05dfacff2ee1d292c438172"
BASE_TREE = "db25581db2ad683499ec2c7b2e22686787d39db2"
PREFIX = "tests/validation/frontend_evolution/"
C_PATH = PREFIX + "dualmic_broadside_output_d8.c"
PY_PATH = PREFIX + "dualmic_broadside_output_d8.py"
BUILD_PATH = PREFIX + "dualmic_broadside_output_d8_build.py"
TEST_PATH = PREFIX + "test_dualmic_broadside_output_d8.py"
PLAN = "docs/research/frontend-evolution-v1/DUALMIC_BROADSIDE_OUTPUT_D8_PLAN.zh-CN.md"
LOCK = "docs/research/frontend-evolution-v1/dualmic-broadside-output-d8-input-lock.json"
PINS = {PLAN: "71a0dea3a65029c23aced80238c791b98d6ec5fc",
        LOCK: "90f397672547abd0a02f87e0d428963d34e834c1"}
INPUT = Path("/tmp/ap-dualmic-d8/input")
OUTPUT = Path("/tmp/ap-dualmic-d8/result")
TOOL = Path("/tmp/ap-dualmic-d8/toolchain")
SEALED_PATH = "/usr/bin:/bin:/usr/local/bin"
SUPERVISOR_PATH = PREFIX + "dualmic_broadside_output_d8_supervise.py"
SOURCE_LIMIT = 16 * 1024 * 1024
OUTPUT_LIMIT = 512 * 1024 * 1024
PHASES = ("admission", "baseline-build", "candidate-build", "run", "analysis", "verify", "negative")
FORMS = ("baseline-plain", "baseline-observed", "candidate-plain", "candidate-observed")
SHA = re.compile(r"[0-9a-f]{40}\Z")
EXPLANATORY = {"tests/validation/build_dualmic_recorded_corpus.py",
               "validation/tools/hpf_aware_reference_oracle.py"}
CAPS = {
    "shared_hpf": 91944960,
    "candidate_unique_signals": 126670080,
    "paired_hpf_bf_state": 33904704,
    "paired_agc_state": 1723968,
    "candidate_s16": 11493120,
    "candidate_metrics_including_newlines": 73555968,
    "candidate_control_including_headers_newlines": 36777984,
    "all_source_archive_derived_build_provenance": 67108864,
    "all_reports_receipts_logs_negatives_seals_completion": 67108864,
    "all_current_case_transient_and_failure_prefix": 25165824,
}
CATEGORY_REASONS = {
    "candidate_metrics_including_newlines": "D8_METRIC_CATEGORY_OVERFLOW",
    "candidate_control_including_headers_newlines": "D8_CONTROL_HEADER_OVERFLOW",
    "all_source_archive_derived_build_provenance": "D8_SOURCE_BUILD_CATEGORY_OVERFLOW",
    "all_reports_receipts_logs_negatives_seals_completion": "D8_REPORT_FINALIZATION_OVERFLOW",
    "all_current_case_transient_and_failure_prefix": "D8_SCRATCH_OVERFLOW",
}
CASE_KEYS = ["A/pair-0-near-only-call","A/pair-0-near-only-assistant","A/pair-0-silent-render-call","A/pair-0-silent-render-assistant","A/pair-0-far-only-call","A/pair-0-far-only-assistant","A/pair-0-doubletalk-nominal-call","A/pair-0-doubletalk-nominal-assistant","A/pair-0-doubletalk-weak-call","A/pair-0-doubletalk-weak-assistant","A/pair-0-path-change-call","A/pair-0-path-change-assistant","A/pair-0-render-gap-call","A/pair-0-render-gap-assistant","A/pair-1-near-only-call","A/pair-1-near-only-assistant","A/pair-1-silent-render-call","A/pair-1-silent-render-assistant","A/pair-1-far-only-call","A/pair-1-far-only-assistant","A/pair-1-doubletalk-nominal-call","A/pair-1-doubletalk-nominal-assistant","A/pair-1-doubletalk-weak-call","A/pair-1-doubletalk-weak-assistant","A/pair-1-path-change-call","A/pair-1-path-change-assistant","A/pair-1-render-gap-call","A/pair-1-render-gap-assistant","A/pair-2-near-only-call","A/pair-2-near-only-assistant","A/pair-2-silent-render-call","A/pair-2-silent-render-assistant","A/pair-2-far-only-call","A/pair-2-far-only-assistant","A/pair-2-doubletalk-nominal-call","A/pair-2-doubletalk-nominal-assistant","A/pair-2-doubletalk-weak-call","A/pair-2-doubletalk-weak-assistant","A/pair-2-path-change-call","A/pair-2-path-change-assistant","A/pair-2-render-gap-call","A/pair-2-render-gap-assistant","A/pair-3-near-only-call","A/pair-3-near-only-assistant","A/pair-3-silent-render-call","A/pair-3-silent-render-assistant","A/pair-3-far-only-call","A/pair-3-far-only-assistant","A/pair-3-doubletalk-nominal-call","A/pair-3-doubletalk-nominal-assistant","A/pair-3-doubletalk-weak-call","A/pair-3-doubletalk-weak-assistant","A/pair-3-path-change-call","A/pair-3-path-change-assistant","A/pair-3-render-gap-call","A/pair-3-render-gap-assistant","C/call","C/assistant","C/call_duplex","C/assistant_duplex"]
JOB_STARTED = None
JOB_DEADLINE = None
BUDGET = None

def need(value, reason):
    if not value:
        raise ValueError(reason)

CLIENT = None
ACTIVE_PHASE = None
FINISHED = False

class Client:
    def __init__(self):
        self.read_fd = int(os.environ["AP_D8_CONTROL_READ"])
        self.write_fd = int(os.environ["AP_D8_CONTROL_WRITE"])
        need(os.getpid() == os.getpgrp() == os.getsid(0) and
             os.getppid() == int(os.environ["AP_D8_SUPERVISOR_PID"]), "D8_SUPERVISED_WORKER_REQUIRED")
        for fd in (self.read_fd, self.write_fd):
            os.set_inheritable(fd, False)
        self.sequence = 0
        self.current = None

    def ask(self, kind, **fields):
        if self.current is not None:
            self.remaining()
        self.sequence += 1
        raw = (json.dumps({"type": kind, "seq": self.sequence, "pid": os.getpid(), **fields},
                          separators=(",", ":"), allow_nan=False) + "\n").encode()
        need(len(raw) <= supervision.IPC_LIMIT, "D8_IPC_BYTES")
        need(os.write(self.write_fd, raw) == len(raw), "D8_IPC_WRITE")
        data = bytearray()
        while b"\n" not in data:
            block = os.read(self.read_fd, 1)
            need(block, "D8_IPC_EOF")
            data += block
            need(len(data) <= supervision.IPC_LIMIT, "D8_IPC_BYTES")
        answer = json.loads(data)
        need(answer.get("seq") == self.sequence and answer.get("ok") is True, "D8_IPC_ACK")
        self.current = answer
        self.remaining()
        return answer

    def remaining(self):
        need(self.current is not None, "D8_JOB_NOT_STARTED")
        deadline = min(value for key, value in self.current.items()
                       if key in ("root_deadline", "phase_deadline", "command_deadline", "fixture_deadline") and value is not None)
        left = deadline - time.monotonic()
        if left <= 0:
            # Worker does not write a timeout receipt. Supervisor owns fatal
            # termination; os._exit also prevents admission finally cleanup.
            os._exit(124)
        return left

def start_job(started=None):
    global CLIENT, JOB_STARTED, JOB_DEADLINE, BUDGET
    need(CLIENT is None and started is None, "D8_JOB_ALREADY_STARTED")
    CLIENT = Client()
    answer = CLIENT.ask("HELLO")
    JOB_STARTED, JOB_DEADLINE = answer["root_started"], answer["root_deadline"]
    BUDGET = ByteBudget(OUTPUT)
    BUDGET.check()
    free_space(4294967296)
    return answer

def job_remaining():
    need(CLIENT is not None, "D8_JOB_NOT_STARTED")
    return CLIENT.remaining()

def finish_job(completion_path=OUTPUT / "completion.json"):
    global FINISHED
    need(ACTIVE_PHASE is not None and ACTIVE_PHASE.name == "negative" and not FINISHED and
         FATAL_FIXTURES_DONE, "D8_FINISH")
    need(Path(completion_path) == OUTPUT / "completion.json" and Path(completion_path).is_file(), "D8_MISSING_FINALIZATION")
    budget().check()
    sys.stdout.flush()
    sys.stderr.flush()
    job_remaining()
    CLIENT.ask("FINISH", completion_checked=True, stdout_flushed=True)
    FINISHED = True

def free_space(minimum=2147483648):
    job_remaining()
    ancestor = TOOL.parent
    while not ancestor.exists():
        ancestor = ancestor.parent
    value = os.statvfs(ancestor)
    available = value.f_bavail * value.f_frsize
    need(available >= minimum, "D8_FREE_SPACE")
    return {"minimum": minimum, "observed": available, "reservation": False}

def read(path):
    return json.loads(Path(path).read_bytes())

def digest(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for data in iter(lambda: f.read(1024 * 1024), b""):
            h.update(data)
    return h.hexdigest()

def desc(path):
    path = Path(path)
    need(path.is_file() and not path.is_symlink() and path.absolute() == path.resolve(strict=True), "D8_REGULAR_FILE")
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

INVENTORY_DEPTH_LIMIT = 48
INVENTORY_STAT_FIELDS = ("dev", "ino", "mode", "nlink", "size", "mtime_ns", "ctime_ns")

def check_inventory_depth(depth):
    need(type(depth) is int and 1 <= depth <= INVENTORY_DEPTH_LIMIT, "D8_INVENTORY_DEPTH")
    return True

def check_inventory_kind(mode, nlink, *, single_link=False):
    need(type(mode) is int and type(nlink) is int and nlink >= 0 and
         type(single_link) is bool, "D8_REGULAR_FILE")
    need(not stat.S_ISLNK(mode), "D8_OUTPUT_SYMLINK")
    if stat.S_ISDIR(mode):
        return "directory"
    need(stat.S_ISREG(mode) and (not single_link or nlink == 1), "D8_REGULAR_FILE")
    return "file"

def inventory_stat(value):
    return {key: getattr(value, "st_" + key) for key in INVENTORY_STAT_FIELDS}

def check_inventory_identity(before, opened, after, named, bytes_read=None):
    records = (before, opened, after, named)
    need(all(type(row) is dict and set(row) == set(INVENTORY_STAT_FIELDS) and
             all(type(row[key]) is int for key in INVENTORY_STAT_FIELDS) for row in records) and
         before == opened == after == named and before["size"] >= 0,
         "D8_INVENTORY_CHANGED")
    if bytes_read is not None:
        need(type(bytes_read) is int and bytes_read == before["size"], "D8_INVENTORY_CHANGED")
    return True

def _inventory_binding(value):
    # An ancestor may have unrelated siblings changed by the hosted runner.
    return value.st_dev, value.st_ino, stat.S_IFMT(value.st_mode)

@contextlib.contextmanager
def _inventory_root(root):
    root = Path(root).absolute()
    need(root == root.resolve(strict=True), "D8_OUTPUT_SYMLINK")
    check_inventory_depth(len(root.parts))  # includes the '/' directory fd
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
    fds, bindings = [], []
    try:
        parent = os.open("/", flags)
        fds.append(parent)
        for depth, name in enumerate(root.parts[1:], 2):
            job_remaining()
            check_inventory_depth(depth)  # before opening another descriptor
            before = os.stat(name, dir_fd=parent, follow_symlinks=False)
            need(check_inventory_kind(before.st_mode, before.st_nlink) == "directory",
                 "D8_REGULAR_FILE")
            child = os.open(name, flags, dir_fd=parent)
            fds.append(child)
            opened = os.fstat(child)
            need(_inventory_binding(before) == _inventory_binding(opened), "D8_INVENTORY_CHANGED")
            bindings.append((parent, name, _inventory_binding(opened)))
            parent = child
        yield root, parent, len(root.parts)
        for parent, name, expected in reversed(bindings):
            job_remaining()
            need(_inventory_binding(os.stat(name, dir_fd=parent, follow_symlinks=False)) == expected,
                 "D8_INVENTORY_CHANGED")
    finally:
        for fd in reversed(fds):
            os.close(fd)

def walk_inventory(root, *, hash_files=True, single_link=False):
    """Fresh measurements, not a cache or an adversarial atomic snapshot.

    Hash mode opens each regular file and validates the named/opened/after
    identity and actual read count. Metadata mode preserves the budget's one
    no-follow stat per regular file; it does not open or hash regular files.
    Both modes use validated directory fds and reject changed directory bindings.
    """
    need(type(hash_files) is bool and type(single_link) is bool, "D8_INVENTORY_MODE")
    files, dirs = {}, []
    directory_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC

    def visit(fd, prefix, depth):
        job_remaining()
        check_inventory_depth(depth)
        initial = inventory_stat(os.fstat(fd))
        need(check_inventory_kind(initial["mode"], initial["nlink"]) == "directory",
             "D8_REGULAR_FILE")
        # scandir(fd) owns a temporary duplicate. Close it before descending.
        with os.scandir(fd) as entries:
            names = sorted(entry.name for entry in entries)
        need(len(names) == len(set(names)), "D8_INVENTORY_CHANGED")
        for name in names:
            job_remaining()
            need(name not in ("", ".", "..") and "/" not in name, "D8_INVENTORY_CHANGED")
            relative = name if not prefix else prefix + "/" + name
            observed = os.stat(name, dir_fd=fd, follow_symlinks=False)
            before = inventory_stat(observed)
            kind = check_inventory_kind(observed.st_mode, observed.st_nlink, single_link=single_link)
            if kind == "directory":
                check_inventory_depth(depth + 1)
                child = os.open(name, directory_flags, dir_fd=fd)
                try:
                    opened = inventory_stat(os.fstat(child))
                    check_inventory_identity(before, opened, opened, before)
                    dirs.append(relative)
                    visit(child, relative, depth + 1)
                    check_inventory_identity(before, opened, inventory_stat(os.fstat(child)),
                        inventory_stat(os.stat(name, dir_fd=fd, follow_symlinks=False)))
                finally:
                    os.close(child)
            elif hash_files:
                # O_NONBLOCK makes a raced FIFO replacement fail type checking
                # rather than blocking in open(). It has no effect on a regular file.
                handle = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK,
                                 dir_fd=fd)
                try:
                    opened = inventory_stat(os.fstat(handle))
                    check_inventory_kind(opened["mode"], opened["nlink"], single_link=single_link)
                    check_inventory_identity(before, opened, opened, before)
                    digest_value, count = hashlib.sha256(), 0
                    while True:
                        job_remaining()
                        data = os.read(handle, 1024 * 1024)
                        if not data:
                            break
                        count += len(data)
                        need(count <= before["size"], "D8_INVENTORY_CHANGED")
                        digest_value.update(data)
                    check_inventory_identity(before, opened, inventory_stat(os.fstat(handle)),
                        inventory_stat(os.stat(name, dir_fd=fd, follow_symlinks=False)), count)
                    files[relative] = {"bytes": count, "sha256": digest_value.hexdigest()}
                finally:
                    os.close(handle)
            else:
                files[relative] = {"bytes": before["size"]}
        # Directory mutation changes its membership metadata. This cannot make
        # concurrent adversarial writes into an atomic filesystem snapshot.
        final = inventory_stat(os.fstat(fd))
        check_inventory_identity(initial, initial, final, final)

    try:
        with _inventory_root(root) as (absolute, fd, depth):
            visit(fd, "", depth)
        order = lambda name: PurePosixPath(name).parts
        return {"files": {name: files[name] for name in sorted(files, key=order)},
                "directories": sorted(dirs, key=order)}
    except OSError as error:
        if error.errno in (errno.ENOENT, errno.ENOTDIR, errno.ELOOP, errno.ESTALE):
            raise ValueError("D8_INVENTORY_CHANGED") from None
        raise

def inventory(root):
    return walk_inventory(root)

def check_closure_record(actual, files, reason, limit=SOURCE_LIMIT):
    need(set(actual) == {"files", "directories"} and set(actual["files"]) == set(files) and
         len(actual["directories"]) == len(set(actual["directories"])) and
         set(actual["directories"]) == directories(files), reason)
    need(sum(x["bytes"] for x in actual["files"].values()) <= limit, "D8_SOURCE_BYTES_BOUND")
    return actual["files"]

def exact_closure(root, files, reason, limit=SOURCE_LIMIT):
    return check_closure_record(inventory(root), files, reason, limit)


def check_original_locks(original_admission, original_d2, expected_admission, expected_d2, admission_freeze):
    """Validate only the three D8 annotations, then compare both original objects whole."""
    need(type(original_admission) is dict and type(original_d2) is dict and
         type(expected_admission) is dict and type(expected_d2) is dict,
         "D8_FULL_ORIGINAL_LOCK")
    saved = dict(original_admission)
    need(saved.pop("admission_freeze", None) == admission_freeze and
         saved.pop("required_status", None) == "INPUT_ADMITTED_NO_DSP_EXECUTION" and
         saved.pop("fresh_full_original_D2_readback_required", None) is True and
         saved == expected_admission and original_d2 == expected_d2,
         "D8_FULL_ORIGINAL_LOCK")
    return True

def contract():
    for name, expected in PINS.items():
        need(blob((ROOT / name).read_bytes()) == expected, "D8_FROZEN_CONTRACT_CHANGED")
    lock = read(ROOT / LOCK)
    need(lock["experiment"] == EXPERIMENT and lock["base_sha"] == BASE and
         lock["base_tree"] == BASE_TREE and lock["candidates"] == 1, "D8_CONTRACT_IDENTITY")
    need(CASE_KEYS == [entry["catalog"]["key"] for entry in lock["original_d2_case_input_lock"]["cases"]],
         "D8_CASE_PATH")
    check_original_locks(lock["original_admission"], lock["original_d2_case_input_lock"],
                         admission.frozen_lock(), d2.input_lock(), admission.FREEZE)
    need(lock["budgets"]["categories"] == CAPS and sum(CAPS.values()) == 535454336 and
         lock["budgets"]["headroom"] == OUTPUT_LIMIT - sum(CAPS.values()),
         "D8_BYTE_BUDGET_CONTRACT")
    for name, expected in lock["frozen_helper_files"].items():
        raw = (ROOT / name).read_bytes()
        need(blob(raw) == expected["git_blob"] and desc(ROOT / name) ==
             {k: expected[k] for k in ("bytes", "sha256")}, "D8_HELPER_IDENTITY")
    return lock

def environment(d1=None, d8=None, frames=None):
    """Full allowlist; no ambient credentials, LD_*, XDG, cache or user config."""
    home, temporary = TOOL / "home", TOOL / "tmp"
    env = {"PATH": SEALED_PATH, "HOME": str(home), "TMPDIR": str(temporary),
           "TMP": str(temporary), "TEMP": str(temporary), "LC_ALL": "C", "LANG": "C",
           "TZ": "UTC", "PYTHONDONTWRITEBYTECODE": "1",
           "XDG_CONFIG_HOME": str(home / "config"), "XDG_CACHE_HOME": str(home / "cache"),
           "XDG_DATA_HOME": str(home / "data"),
           "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": "/dev/null",
           "GIT_ATTR_NOSYSTEM": "1", "GIT_NO_REPLACE_OBJECTS": "1", "GIT_TERMINAL_PROMPT": "0",
           "GIT_OPTIONAL_LOCKS": "0"}
    if d1 is not None:
        env["AP_D1_STAGE_DIR"] = str(d1)
    if d8 is not None:
        env["AP_D8_STAGE_DIR"] = str(d8)
    if frames is not None:
        need(type(frames) is int and 529 <= frames <= 629, "D8_FRAME_BOUND")
        env["AP_D8_EXPECTED_FRAMES"] = str(frames)
    return env

def prepare_tool_environment():
    for path in (TOOL, TOOL / "home", TOOL / "tmp", TOOL / "home/config",
                 TOOL / "home/cache", TOOL / "home/data"):
        need(not path.is_symlink(), "D8_TOOL_SYMLINK")
        path.mkdir(parents=True, exist_ok=True)
    return tool_inventory()

def tool_inventory():
    job_remaining()
    actual = inventory(TOOL)
    need(sum(d["bytes"] for d in actual["files"].values()) <= 134217728,
         "D8_TOOL_POSTHOC_BYTES")
    need(all(d["bytes"] <= 16777216 for d in actual["files"].values()), "D8_TOOL_FILE_BOUND")
    return actual

def inventory_reference(value):
    raw = (json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)+"\n").encode()
    digest_value = hashlib.sha256(raw).hexdigest()
    relative = "build/tool-inventories/" + digest_value + ".json"
    path = OUTPUT / relative
    if path.exists():
        need(path.read_bytes() == raw, "D8_TOOL_INVENTORY_RESEALED")
    else:
        bounded_write(path, raw)
    return {"path": relative, "bytes": len(raw), "sha256": digest_value}

def check_inventory_reference(value):
    need(type(value) is dict and set(value) == {"path", "bytes", "sha256"} and
         value["path"] == "build/tool-inventories/" + value["sha256"] + ".json" and
         re.fullmatch(r"[0-9a-f]{64}", value["sha256"]) is not None, "D8_TOOL_INVENTORY_REFERENCE")
    need(desc(OUTPUT / value["path"]) == {k: value[k] for k in ("bytes", "sha256")},
         "D8_TOOL_INVENTORY_RESEALED")
    actual = read(OUTPUT / value["path"])
    need(set(actual) == {"files", "directories"} and sum(x["bytes"] for x in actual["files"].values()) <=
         134217728 and all(0 <= x["bytes"] <= 16777216 for x in actual["files"].values()),
         "D8_TOOL_POSTHOC_BYTES")
    return actual

# Offsets share the Phase.run-entry origin. Samples occur after, in order:
# argument/environment checks + environment mkdir + fresh pre-tool inventory;
# free-space/scientific/argv checks; COMMAND_BEGIN ACK; pending receipt write;
# log reservation/open + pipe setup (immediately before Popen); Popen/rlimits +
# child wait/pipe drain; log close + reservation-exit accounting; quiescent ACK;
# fresh post-tool inventory; inventory reference + scientific/budget/log checks.
# The final receipt/phase writes, stdout-return read and END ACK stay under the
# existing deadline but cannot be self-measured by this terminal payload.
SUBTIMING_STAGES = ("preparation_inventory", "prelease_validation", "begin_ack",
    "pending_receipt", "child_setup", "child_and_pipe_drain", "child_accounting",
    "quiescent_ack", "after_inventory", "postchild_accounting")
SUBTIMING_SCOPE = ("cumulative wall seconds from Phase.run entry; final capture excludes "
    "terminal/phase receipt writes, stdout-return read and COMMAND_END ACK; "
    "stages are composite, not pure DSP")
SUBTIMING_LIMIT = 2048

def _finite_number(value):
    if type(value) not in (int, float):
        return False
    try:
        return math.isfinite(value)
    except OverflowError:
        return False

def new_subtimings(now):
    need(_finite_number(now) and now >= 0, "D8_COMMAND_TIMINGS")
    return {"version": 1, "clock": "monotonic", "scope": SUBTIMING_SCOPE,
            "origin": now, "offsets": dict.fromkeys(SUBTIMING_STAGES)}

def mark_subtiming(value, stage, now):
    need(type(value) is dict and type(value.get("offsets")) is dict and
         set(value["offsets"]) == set(SUBTIMING_STAGES) and
         _finite_number(value.get("origin")) and _finite_number(now), "D8_COMMAND_TIMINGS")
    offsets = value["offsets"]
    unfilled = [name for name in SUBTIMING_STAGES if offsets[name] is None]
    need(unfilled and stage == unfilled[0], "D8_COMMAND_TIMINGS")
    elapsed = now - value["origin"]
    previous = [offsets[name] for name in SUBTIMING_STAGES if offsets[name] is not None]
    need(0 <= elapsed <= 300 and (not previous or elapsed >= previous[-1]), "D8_COMMAND_TIMINGS")
    offsets[stage] = elapsed
    return value

def check_subtimings(value, *, lifecycle="TERMINAL", status="PASS"):
    reason = "D8_COMMAND_TIMINGS"
    need(type(value) is dict and set(value) == {"version", "clock", "scope", "origin", "offsets"} and
         type(value["version"]) is int and value["version"] == 1 and value["clock"] == "monotonic" and
         value["scope"] == SUBTIMING_SCOPE and _finite_number(value["origin"]) and value["origin"] >= 0 and
         type(value["offsets"]) is dict and set(value["offsets"]) == set(SUBTIMING_STAGES), reason)
    need((lifecycle, status) in (("PENDING", "FAIL"), ("TERMINAL", "FAIL"), ("TERMINAL", "PASS")), reason)
    count, previous, empty = 0, 0.0, False
    for name in SUBTIMING_STAGES:
        item = value["offsets"][name]
        if item is None:
            empty = True
        else:
            need(not empty and _finite_number(item) and previous <= item <= 300, reason)
            count += 1
            previous = item
    need((count == 3 if lifecycle == "PENDING" else count == 10 if status == "PASS" else count >= 3), reason)
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    need(len(raw) <= SUBTIMING_LIMIT, reason)
    return value

def command_dump(path, receipt, *, replace=False):
    check_subtimings(receipt["subtimings"], lifecycle=receipt["lifecycle"], status=receipt["status"])
    raw = (json.dumps(receipt, sort_keys=True, indent=2, allow_nan=False)+"\n").encode()
    if receipt.get("scientific") is not None:
        need(len(raw) <= 65536, "D8_SCIENTIFIC_RECEIPT_BOUND")
    return bounded_write(path, raw, replace=replace)


def category(path):
    """Disjoint classes; a new unregistered path is never free storage."""
    path = Path(path).absolute()
    need(path.is_relative_to(OUTPUT) and path != OUTPUT, "D8_WRITE_ESCAPE")
    need(path.resolve(strict=False) == path, "D8_WRITE_ESCAPE")
    name = path.relative_to(OUTPUT).as_posix()
    for parent in [path, *path.parents]:
        if parent == OUTPUT.parent:
            break
        need(not parent.is_symlink(), "D8_OUTPUT_SYMLINK")
    return _category_name(name)

# Static contract names only. No measured sizes, identities or hashes are cached.
CASE_PREFIXES = frozenset("cases/" + key + "/" for key in CASE_KEYS)
need(len(CASE_PREFIXES) == len(CASE_KEYS) == 60 and
     all(len(key.split("/")) == 2 and key.split("/")[0] in ("A", "C") and
         all(part not in ("", ".", "..") for part in key.split("/")) for key in CASE_KEYS),
     "D8_CASE_PATH")
CASE_TAIL_CATEGORIES = {
    **{"shared/" + lane + ".f32le": "shared_hpf" for lane in
       ("hpf_input_l", "hpf_input_r", "hpf_output_l", "hpf_output_r")},
    **{"candidate/" + lane + ".f32le": "candidate_unique_signals" for lane in
       ("bf_output", "reference", "echo", "aec_residual", "ns_output", "agc_output")},
    **{arm + "/state.bin": "paired_hpf_bf_state" for arm in ("baseline", "candidate")},
    **{arm + "/agc-state.bin": "paired_agc_state" for arm in ("baseline", "candidate")},
    "candidate/out.pcm": "candidate_s16",
    "candidate/metrics.jsonl": "candidate_metrics_including_newlines",
    "candidate/control.csv": "candidate_control_including_headers_newlines",
    "retention.json": "all_reports_receipts_logs_negatives_seals_completion",
    **{"receipts/" + arm + "-" + observer + "-observer.json":
       "all_reports_receipts_logs_negatives_seals_completion"
       for arm in ("baseline", "candidate") for observer in ("d1", "upstream")},
}
REPORT_NAMES = frozenset({"input-binding.json", "run-index.json", "report.json", "seal.json",
    "readback.json", "negative-tests.json", "summary.json", "completion.json",
    "first-failure.json"} | {phase + "-phase.json" for phase in PHASES})
REPORT_ROOTS = frozenset({phase + "-logs" for phase in PHASES} | {"negatives"})

def _category_name(name):
    """Pure exact-name classifier after target or no-follow walk validation."""
    parts = PurePosixPath(name).parts
    need(bool(parts), "D8_UNREGISTERED_FILE")
    if parts[0] == "build":
        return "all_source_archive_derived_build_provenance"
    if len(parts) >= 3 and parts[:2] == ("scratch", "current"):
        return "all_current_case_transient_and_failure_prefix"
    if len(parts) >= 4 and parts[0] == "cases":
        prefix = "/".join(parts[:3]) + "/"
        need(prefix in CASE_PREFIXES and name.startswith(prefix), "D8_CASE_PATH")
        tail = name[len(prefix):]
        need(tail in CASE_TAIL_CATEGORIES, "D8_UNREGISTERED_FILE")
        return CASE_TAIL_CATEGORIES[tail]
    if name in REPORT_NAMES or parts[0] in REPORT_ROOTS:
        return "all_reports_receipts_logs_negatives_seals_completion"
    raise ValueError("D8_UNREGISTERED_FILE")

class ByteBudget:
    """Reservations are logical byte bounds, not compressed or allocated sizes.

    Parent writes reserve their complete final size before opening. Reservations
    stay live through failed/partial writes. No concurrent unchecked writer is
    permitted. Arbitrary compiler writes are deliberately NOT admitted by this
    class: a per-file rlimit does not imply a directory aggregate limit.
    """
    def __init__(self, root):
        need(Path(root) == OUTPUT, "D8_BUDGET_ROOT")
        self.root = Path(root)
        self.prefix = str(self.root) + "/"
        self.reservations = {}
        self.next_token = 0
        self.case_state = None
        self.next_case = 0
        self.retiring = None

    def measured(self):
        totals = dict.fromkeys(CAPS, 0)
        files = {}
        if self.root.exists() or self.root.is_symlink():
            actual = walk_inventory(self.root, hash_files=False, single_link=True)
            for name, descriptor in actual["files"].items():
                size = descriptor["bytes"]
                files[self.prefix + name] = size
                totals[_category_name(name)] += size
                if name == "build/exact-source.tar":
                    need(size <= SOURCE_LIMIT, "D8_SOURCE_ARCHIVE_BOUND")
        return totals, files

    def _relative_name(self, path):
        # All callers supply a fresh measured path or an already validated
        # retirement destination. Still reject a lookalike root boundary.
        need(type(path) is str and path.startswith(self.prefix) and len(path) > len(self.prefix),
             "D8_WRITE_ESCAPE")
        return path[len(self.prefix):]

    def check(self):
        job_remaining()
        if self.retiring is not None:
            return self._retirement_check()
        totals, files = self.measured()
        return self._check_snapshot(totals, files)

    def _check_snapshot(self, totals, files):
        totals = dict(totals)
        # max final size per path avoids counting the same already-written prefix
        # twice, while concurrent reservations for distinct files remain additive.
        planned = {}
        for bounds in self.reservations.values():
            for path, size in bounds.items():
                planned[path] = max(planned.get(path, 0), size)
        for path, size in planned.items():
            totals[category(path)] += max(0, size - files.get(path, 0))
        if self.case_state is not None:
            state = self.case_state
            ancillary = sum(max(0, size - state["initial"].get(path, 0)) for path, size in files.items()
                            if path not in state["scientific"] and
                            _category_name(self._relative_name(path)) in (
                            "all_current_case_transient_and_failure_prefix",
                            "all_reports_receipts_logs_negatives_seals_completion"))
            for path, maximum in planned.items():
                if path not in state["scientific"] and category(path) in (
                        "all_current_case_transient_and_failure_prefix",
                        "all_reports_receipts_logs_negatives_seals_completion"):
                    ancillary += max(0, maximum - files.get(path, 0))
            need(ancillary <= 8388608, "D8_SCRATCH_ANCILLARY_OVERFLOW")
            key = "all_current_case_transient_and_failure_prefix"
            totals[key] = max(totals[key], 25600 * state["frames"] + 8388608)
        check_category_totals(totals)
        job_remaining()
        return {"categories": totals, "total": sum(totals.values()),
                "ceiling": sum(CAPS.values()), "headroom": OUTPUT_LIMIT - sum(CAPS.values())}

    @contextlib.contextmanager
    def reserve(self, bounds):
        need(self.retiring is None, "D8_RETIREMENT_WRITE")
        checked = {}
        for path, maximum in bounds.items():
            p = Path(path).absolute()
            category(p)
            need(type(maximum) is int and maximum >= 0, "D8_RESERVATION_SCHEMA")
            if p == OUTPUT / "build/exact-source.tar":
                need(maximum <= SOURCE_LIMIT, "D8_SOURCE_ARCHIVE_BOUND")
            checked[str(p)] = maximum
        token = self.next_token
        self.next_token += 1
        self.reservations[token] = checked
        try:
            self.check()  # before mkdir/open/truncate/write
            yield
            for path, maximum in checked.items():
                if Path(path).exists():
                    need(Path(path).stat().st_size <= maximum, "D8_RESERVED_FILE_OVERFLOW")
            self.check()
        finally:
            del self.reservations[token]
            # Failure prefixes remain in the counted root. Never delete, hash,
            # or start fresh I/O merely because an existing deadline has expired.

    @contextlib.contextmanager
    def case(self, frames):
        need(self.case_state is None and type(frames) is int and 529 <= frames <= 629 and
             self.next_case < 60 and frames == contract()["original_d2_case_input_lock"]["cases"][self.next_case]["catalog"]["frames"],
             "D8_FRAME_BOUND")
        scratch = OUTPUT / "scratch/current"
        need(not scratch.exists() or not any(scratch.rglob("*")), "D8_SCRATCH_NOT_EMPTY")
        _, files = self.measured()
        self.case_state = {"frames": frames, "index": self.next_case, "initial": files, "scientific": set(), "forms": set()}
        success = False
        try:
            self.check()
            scratch.mkdir(parents=True, exist_ok=True)
            yield self
            need(self.case_state["forms"] == set(FORMS), "D8_RUN_MATRIX")
            need(not any(p.is_file() for p in scratch.rglob("*")), "D8_SCRATCH_NOT_RETIRED")
            for directory in sorted((p for p in scratch.rglob("*") if p.is_dir()),
                                    key=lambda p: len(p.parts), reverse=True):
                job_remaining()
                directory.rmdir()  # only proven-empty directories; never failed files
            scratch.rmdir()
            scratch.parent.rmdir()
            self.check()
            success = True
        finally:
            if success:
                self.next_case += 1
                self.case_state = None  # failed-case reservation remains through failure reporting

    def register_scientific(self, spec):
        state = self.case_state
        need(state is not None and spec["frames"] == state["frames"] and
             spec["form"] in FORMS and spec["form"] not in state["forms"] and
             spec["form"] == FORMS[len(state["forms"])], "D8_SCIENTIFIC_CAP")
        frame_count, form = spec["frames"], spec["form"]
        arm, mode = form.split("-")
        root = OUTPUT / "scratch/current"
        expected = {root / form / name for name in ("out.pcm", "metrics.jsonl")}
        if mode == "observed":
            expected |= {root / (arm + "-d1") / name for name in (
                *(lane + ".f32le" for lane in d2.d1.LANES), "control.csv", "observer.json")}
            expected |= {root / (arm + "-upstream") / name for name in (
                "hpf_input_l.f32le", "hpf_input_r.f32le", "hpf_output_l.f32le",
                "hpf_output_r.f32le", "bf_output.f32le", "state.bin", "agc-state.bin", "observer.json")}
        need(set(map(Path, spec["files"])) == expected and len(expected) == (2 if mode == "plain" else 19),
             "D8_SCIENTIFIC_FILE_SET")
        need(all(not p.exists() and not p.is_symlink() for p in expected), "D8_SCIENTIFIC_NEW_PREFIX")
        need(all(p.parent.is_dir() and not any(p.parent.iterdir()) for p in expected), "D8_SCIENTIFIC_NEW_PREFIX")
        for p in expected:
            category(p)
        state["scientific"].update(map(str, expected))
        state["forms"].add(form)
        self.check()
        return expected, frame_count * (320 if mode == "plain" else 640)

    @contextlib.contextmanager
    def retirement(self, receipt_path):
        """Only the recorded atomic moves/unlinks may occur inside this scope."""
        state = self.case_state
        need(self.retiring is None and not self.reservations and state is not None and
             state["forms"] == set(FORMS) and ACTIVE_PHASE is not None and ACTIVE_PHASE.name == "run" and
             CLIENT.current["command_deadline"] is None, "D8_RETIREMENT_STATE")
        job_remaining()
        receipt_path = Path(receipt_path).absolute()
        need(receipt_path.is_relative_to(OUTPUT / "cases") and receipt_path.name == "retention.json",
             "D8_FORGED_DEDUP")
        category(receipt_path)
        receipt_identity = desc(receipt_path)
        receipt = read(receipt_path)
        operations, measured = receipt.get("operations", []), receipt.get("measured_files", {})
        scientific = set(state["scientific"])
        need(len(scientific) == 42 and set(measured) == scientific and len(operations) == 42 and
             {x.get("source") for x in operations} == scientific and
             sum(x.get("action") == "move" for x in operations) == 21 and
             sum(x.get("action") == "discard_equal" for x in operations) == 21, "D8_FORGED_DEDUP")
        for operation in operations:
            action = operation["action"]
            expected = {"action", "source", "identity", "destination" if action == "move" else "equal_to"}
            need(set(operation) == expected and operation["identity"] == measured[operation["source"]] and
                 set(operation["identity"]) == {"bytes", "sha256"} and
                 type(operation["identity"]["bytes"]) is int and operation["identity"]["bytes"] >= 0 and
                 re.fullmatch(r"[0-9a-f]{64}", operation["identity"]["sha256"]) is not None,
                 "D8_FORGED_DEDUP")
            source = Path(operation["source"])
            need(source.is_relative_to(OUTPUT / "scratch/current") and str(source.absolute()) == str(source),
                 "D8_RETENTION_SOURCE")
            category(source)
        totals, files = self.measured()
        self._check_snapshot(totals, files)
        scratch_files = {name for name in files if Path(name).is_relative_to(OUTPUT / "scratch/current")}
        need(scratch_files == scientific and
             all(files[name] == measured[name]["bytes"] for name in scientific), "D8_RETENTION_SOURCE")
        self.retiring = {"receipt": str(receipt_path), "receipt_identity": receipt_identity,
                         "operations": operations, "index": 0, "totals": totals, "files": files}
        try:
            yield self
            job_remaining()
            ledger = self.retiring
            need(ledger["index"] == 42 and not self.reservations, "D8_RETIREMENT_SEQUENCE")
            need(desc(receipt_path) == receipt_identity, "D8_FORGED_DEDUP")
            actual_totals, actual_files = self.measured()
            need(actual_files == ledger["files"] and actual_totals == ledger["totals"],
                 "D8_RETIREMENT_RECONCILIATION")
            self._check_snapshot(actual_totals, actual_files)
        finally:
            # Reset before an ordinary failure receipt can be written. Never
            # perform reconciliation, hashing or cleanup merely due to expiry.
            self.retiring = None

    def _retirement_check(self, totals=None):
        job_remaining()
        need(self.retiring is not None and self.case_state is not None and not self.reservations,
             "D8_RETIREMENT_STATE")
        values = dict(self.retiring["totals"] if totals is None else totals)
        # Only registered scientific files move/disappear. Their destinations
        # join scientific immediately after a successful rename. The ancillary
        # byte set is therefore unchanged from the full entry check.
        key = "all_current_case_transient_and_failure_prefix"
        values[key] = max(values[key], 25600 * self.case_state["frames"] + 8388608)
        check_category_totals(values)
        job_remaining()
        return {"categories": values, "total": sum(values.values()),
                "ceiling": sum(CAPS.values()), "headroom": OUTPUT_LIMIT - sum(CAPS.values())}

    def _retirement_operation(self, receipt_path, operation):
        if self.retiring is None:
            return
        ledger = self.retiring
        need(str(Path(receipt_path).absolute()) == ledger["receipt"] and ledger["index"] < 42 and
             operation == ledger["operations"][ledger["index"]], "D8_RETIREMENT_SEQUENCE")
        need(ledger["files"].get(operation["source"]) == operation["identity"]["bytes"],
             "D8_RETENTION_SOURCE")

    def _retirement_commit(self, source, destination, size):
        if self.retiring is None:
            return
        ledger = self.retiring
        need(ledger["files"].pop(str(source), None) == size, "D8_RETENTION_SOURCE")
        ledger["totals"][category(source)] -= size
        if destination is not None:
            need(str(destination) not in ledger["files"], "D8_RETENTION_DESTINATION")
            ledger["files"][str(destination)] = size
            ledger["totals"][category(destination)] += size
        ledger["index"] += 1
        self._retirement_check()

    def transfer(self, source, destination, size):
        if self.retiring is None:
            totals, files = self.measured()
        else:
            totals, files = dict(self.retiring["totals"]), self.retiring["files"]
        need(files.get(str(source)) == size and str(destination) not in files, "D8_RETENTION_SOURCE")
        totals[category(source)] -= size
        totals[category(destination)] += size
        if self.retiring is None:
            check_category_totals(totals)
        else:
            self._retirement_check(totals)

def _recorded_operation(source, receipt_path, operation):
    receipt_path = Path(receipt_path).absolute()
    need(receipt_path.is_relative_to(OUTPUT / "cases") and receipt_path.name == "retention.json", "D8_FORGED_DEDUP")
    category(receipt_path)
    budget()._retirement_operation(receipt_path, operation)
    value = read(receipt_path)
    identity = operation["identity"]
    need(value.get("measured_files", {}).get(str(source)) == identity and
         value.get("operations", []).count(operation) == 1, "D8_FORGED_DEDUP")
    need(desc(source) == identity, "D8_RETENTION_SOURCE")
    return identity

def equal_files(left, right):
    need(desc(left) == desc(right), "D8_DEDUP_BYTES")
    with Path(left).open("rb") as a, Path(right).open("rb") as b:
        while True:
            job_remaining()
            x, y = a.read(65536), b.read(65536)
            need(x == y, "D8_DEDUP_BYTES")
            if not x:
                break

def retain_move(source, destination, descriptor, receipt_path):
    source, destination = Path(source).absolute(), Path(destination).absolute()
    operation = {"action": "move", "source": str(source), "destination": str(destination),
                 "identity": descriptor}
    _recorded_operation(source, receipt_path, operation)
    need(source.is_relative_to(OUTPUT / "scratch/current") and budget().case_state is not None and
         str(source) in budget().case_state["scientific"], "D8_RETENTION_SOURCE")
    need(not destination.exists(), "D8_RETENTION_DESTINATION")
    category(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    need(source.stat().st_dev == destination.parent.stat().st_dev, "D8_ATOMIC_MOVE_REQUIRED")
    budget().transfer(source, destination, descriptor["bytes"])
    job_remaining()
    os.rename(source, destination)  # no copy fallback
    budget()._retirement_commit(source, destination, descriptor["bytes"])
    if budget().case_state is not None:
        budget().case_state["scientific"].add(str(destination))
    need(desc(destination) == descriptor, "D8_RETENTION_SOURCE")
    budget().check()
    return descriptor

def discard_equal(source, other, receipt_path):
    source, other = Path(source).absolute(), Path(other).absolute()
    identity = desc(source)
    operation = {"action": "discard_equal", "source": str(source), "equal_to": str(other),
                 "identity": identity}
    _recorded_operation(source, receipt_path, operation)
    need(source != other and source.is_relative_to(OUTPUT / "scratch/current") and
         budget().case_state is not None and str(source) in budget().case_state["scientific"], "D8_RETENTION_SOURCE")
    equal_files(source, other)
    need(desc(source) == identity == desc(other), "D8_RETENTION_SOURCE")
    job_remaining()
    source.unlink()
    budget()._retirement_commit(source, None, identity["bytes"])
    budget().check()
    return identity

def budget():
    need(BUDGET is not None, "D8_JOB_NOT_STARTED")
    return BUDGET

def bounded_write(path, data, *, replace=False):
    path = Path(path)
    need(isinstance(data, bytes), "D8_WRITE_BYTES")
    with budget().reserve({path: len(data)}):
        path.parent.mkdir(parents=True, exist_ok=True)
        job_remaining()
        with path.open("wb" if replace else "xb", buffering=0) as out:
            view = memoryview(data)
            while view:
                job_remaining()
                count = out.write(view[:65536])
                need(count is not None and count > 0, "D8_SHORT_WRITE")
                view = view[count:]
        job_remaining()
    return desc(path)

def bounded_copy(source, destination):
    # Source and destination are both charged while the second physical copy
    # exists; no move/dedup assumption is smuggled into this helper.
    source, destination = Path(source), Path(destination)
    need(not source.is_relative_to(OUTPUT / "scratch") and not destination.is_relative_to(OUTPUT / "scratch"),
         "D8_NO_SCIENTIFIC_COPY")
    free_space()
    identity = desc(source)
    with budget().reserve({destination: identity["bytes"]}):
        destination.parent.mkdir(parents=True, exist_ok=True)
        with source.open("rb") as src, destination.open("xb", buffering=0) as dst:
            copied = 0
            while True:
                job_remaining()
                block = src.read(65536)
                if not block:
                    break
                copied += len(block)
                need(copied <= identity["bytes"], "D8_COPY_SOURCE_CHANGED")
                need(dst.write(block) == len(block), "D8_SHORT_WRITE")
        need(desc(destination) == identity == desc(source), "D8_COPY_SOURCE_CHANGED")
    return identity

def dump(path, value, *, replace=False, compact=False):
    raw = (json.dumps(value, indent=None if compact else 2, sort_keys=True, allow_nan=False) + "\n").encode()
    return bounded_write(path, raw, replace=replace)

def check_text_limits(path, frames, *, control=False):
    need(type(frames) is int and 1 <= frames <= 629, "D8_FRAME_BOUND")
    cap = 1024 if control else 2048
    raw = Path(path).read_bytes()
    reason = "D8_CONTROL_HEADER_OVERFLOW" if control else "D8_METRIC_CATEGORY_OVERFLOW"
    need(len(raw) <= frames * cap and all(len(line) <= cap for line in raw.splitlines(keepends=True)),
         reason)
    need(raw.endswith(b"\n"), reason)
    return desc(path)

def check_category_totals(totals):
    need(set(totals) == set(CAPS) and all(type(value) is int and value >= 0 for value in totals.values()),
         "D8_BUDGET_SCHEMA")
    for key, cap in CAPS.items():
        need(totals[key] <= cap, CATEGORY_REASONS.get(key, "D8_CATEGORY_OVERFLOW:" + key))
    check_total_bytes(sum(totals.values()))
    return True

def check_total_bytes(value):
    need(type(value) is int and 0 <= value <= sum(CAPS.values()) < OUTPUT_LIMIT, "D8_OUTPUT_BYTES_BOUND")
    return True

check_budget_counts = check_category_totals


class Phase:
    def __init__(self, name, root=OUTPUT):
        need(name in PHASES and Path(root) == OUTPUT, "D8_PHASE_IDENTITY")
        self.name, self.root = name, Path(root)
        self.started = None
        self.report = {"experiment": EXPERIMENT, "phase": name, "status": "FAIL",
                       "budget_seconds": 300, "commands": [], "first_failure": None}
        self.finalizer = None

    def remaining(self):
        return job_remaining()

    def _remember_failure(self, error, stage):
        self.report["status"] = "FAIL"
        if self.report["first_failure"] is None:
            self.report["first_failure"] = {
                "stage": stage, "type": type(error).__name__,
                "reason": str(error) if isinstance(error, (ValueError, TimeoutError)) else "phase failed"}
            for field in ("build_flags", "generated", "tool_lookup"):
                if hasattr(error, "d8_" + field):
                    self.report["first_failure"][field] = getattr(error, "d8_" + field)
            if "tool_lookup" in self.report["first_failure"]:
                diagnostic = json.dumps({"reason": "D8_TOOL_MISSING",
                    "tool_lookup": self.report["first_failure"]["tool_lookup"]},
                    sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n"
                need(len(diagnostic.encode("ascii")) <= 1024, "D8_TOOL_DIAGNOSTIC_BOUND")
                self.remaining()
                try:
                    sys.stderr.write(diagnostic)
                    sys.stderr.flush()
                except OSError:
                    pass  # preserve the first error; existing supervisor owns the pipe/deadline
        error.d8_first_failure = dict(self.report["first_failure"])
        error.d8_phase = self.name
        error.d8_target = str(self.path)

    def _preserve_failure(self):
        # remaining() exits without running finally blocks if the local copy of
        # the existing deadline has expired. The external supervisor is primary.
        self.remaining()
        try:
            self.report["elapsed_seconds"] = time.monotonic() - self.started
            if self.owned_receipt:
                dump(self.path, self.report, replace=True)
            first = self.root / "first-failure.json"
            if not first.exists():
                dump(first, {"experiment": EXPERIMENT, "status": "MEASUREMENT_INVALID",
                     "phase": self.name, "target": str(self.path),
                     "first_failure": self.report["first_failure"], "promotion_allowed": False})
            self.remaining()
        except Exception:
            pass  # never replace the first exception

    def __enter__(self):
        global ACTIVE_PHASE
        need(ACTIVE_PHASE is None and not FINISHED, "D8_PHASE_STATE")
        self.lease = CLIENT.ask("PHASE_BEGIN", name=self.name)
        self.started = time.monotonic()
        ACTIVE_PHASE = self
        self.path = self.root / (self.name + "-phase.json")
        self.logs = self.root / (self.name + "-logs")
        self.owned_receipt = False
        self.report.update(root_started=JOB_STARTED, root_deadline=JOB_DEADLINE,
                           phase_deadline=self.lease["phase_deadline"],
                           supervisor_limits=self.lease["supervisor_limits"],
                           worker_limits=self.lease["worker_limits"])
        try:
            need(not self.path.exists(), "D8_PHASE_ALREADY_EXISTS")
            dump(self.path, self.report)
            self.owned_receipt = True
            self.remaining()
            return self
        except BaseException as error:
            self._remember_failure(error, "enter")
            self._preserve_failure()
            raise

    def __exit__(self, kind, error, tb):
        global ACTIVE_PHASE
        try:
            if error is not None:
                self._remember_failure(error, "body")
                self._preserve_failure()
                return False
            self.remaining()
            self.report["status"] = "PASS"
            self.report["elapsed_seconds"] = time.monotonic() - self.started
            self.report["elapsed_scope"] = "terminal receipt; original deadline remains armed through finalizer and supervisor completion"
            dump(self.path, self.report, replace=True)
            budget().check()
            if self.finalizer is not None:
                self.finalizer(self)
                self.remaining()
            if self.name == "negative":
                need(FINISHED, "D8_MISSING_FINALIZATION")
            else:
                need(not FINISHED, "D8_FINISH")
                CLIENT.ask("PHASE_END", name=self.name)
        except BaseException as terminal:
            if error is None:
                self._remember_failure(terminal, "terminal")
                if not FINISHED:
                    self._preserve_failure()
                raise
        finally:
            ACTIVE_PHASE = None
        return False

    def run(self, label, argv, *, cwd=ROOT, env=None, scientific=None,
            stdout_limit=1048576, stderr_limit=1048576):
        timings = new_subtimings(time.monotonic())
        mark = lambda stage: mark_subtiming(timings, stage, time.monotonic())
        need(ACTIVE_PHASE is self and not FINISHED, "D8_COMMAND_STATE")
        need(budget().retiring is None, "D8_RETIREMENT_WRITE")
        need(isinstance(argv, list) and all(type(x) is str for x in argv), "D8_ARGV_SCHEMA")
        need(re.fullmatch(r"[A-Za-z0-9_.-]+", label) is not None, "D8_COMMAND_LABEL")
        need(type(stdout_limit) is int and type(stderr_limit) is int and
             0 < stdout_limit <= SOURCE_LIMIT and 0 < stderr_limit <= SOURCE_LIMIT, "D8_LOG_BOUND")
        effective_env = environment() if env is None else env
        expected_env = environment(effective_env.get("AP_D1_STAGE_DIR"),
                                   effective_env.get("AP_D8_STAGE_DIR"),
                                   int(effective_env["AP_D8_EXPECTED_FRAMES"]) if
                                   "AP_D8_EXPECTED_FRAMES" in effective_env else None)
        need(effective_env == expected_env, "D8_EXECUTION_ENVIRONMENT")
        before_tool = prepare_tool_environment()
        mark("preparation_inventory")
        free = free_space()
        expected_files = None
        limits = dict(supervision.TOOL_LIMITS)
        if scientific is not None:
            need(self.name == "run", "D8_SCIENTIFIC_PHASE")
            expected_files, limits["FSIZE"] = budget().register_scientific(scientific)
            if scientific["form"].endswith("observed"):
                arm = scientific["form"].split("-")[0]
                expected_scientific_env = environment(OUTPUT / "scratch/current" / (arm + "-d1"),
                    OUTPUT / "scratch/current" / (arm + "-upstream"), scientific["frames"])
            else:
                expected_scientific_env = environment()
            need(effective_env == expected_scientific_env, "D8_EXECUTION_ENVIRONMENT")
            index = budget().case_state["index"]
            need(label == "%03d-%s" % (index, scientific["form"]), "D8_EXECUTION_ARGV")
            case = contract()["original_d2_case_input_lock"]["cases"][index]["catalog"]
            executable = "ap_process_pcm_observer" if scientific["form"].endswith("observed") else "ap_process_pcm"
            program = OUTPUT / "build" / (scientific["form"] + "-build") / executable
            expected_argv = d2.d1.mapped_argv(case, program, OUTPUT / "scratch/current" / scientific["form"],
                                            INPUT / "original/result/originals" / case["group"])
            need(argv == expected_argv and str(cwd) == str(ROOT), "D8_EXECUTION_ARGV")
        prefix = self.logs / label
        stdout, stderr = Path(str(prefix) + ".stdout"), Path(str(prefix) + ".stderr")
        receipt_path = Path(str(prefix) + ".command.json")
        mark("prelease_validation")
        lease = CLIENT.ask("COMMAND_BEGIN", label=label)
        begin = time.monotonic()
        mark_subtiming(timings, "begin_ack", begin)
        receipt = {"argv": argv, "cwd": str(cwd), "timeout_seconds": lease["command_deadline"] - begin,
                   "deadline": lease["command_deadline"], "phase_deadline": lease["phase_deadline"],
                   "root_deadline": lease["root_deadline"], "status": "FAIL", "returncode": None,
                   "timed_out": False, "lifecycle": "PENDING", "environment": effective_env,
                   "stdout_limit": stdout_limit, "stderr_limit": stderr_limit,
                   "requested_limits": limits, "scientific": None if scientific is None else {
                       **scientific, "files": sorted(map(str, expected_files))},
                   "free_space": free, "worker_pgid": os.getpgrp(),
                   "tool_inventory_before": inventory_reference(before_tool), "subtimings": timings}
        self.report["commands"].append(receipt_path.relative_to(self.root).as_posix())
        command_dump(receipt_path, receipt)
        mark("pending_receipt")
        process = None
        limit_read = limit_write = None
        try:
            with budget().reserve({stdout: stdout_limit, stderr: stderr_limit}):
                with stdout.open("xb", buffering=0) as out, stderr.open("xb", buffering=0) as err:
                    limit_read, limit_write = os.pipe()
                    def child_limits():
                        need(os.getpgrp() == os.getppid() and os.getsid(0) == os.getppid(),
                             "D8_CHILD_GROUP")
                        actual = supervision.lower_limits(limits)
                        raw = json.dumps(actual, separators=(",", ":")).encode()
                        need(len(raw) <= 4096 and os.write(limit_write, raw) == len(raw), "D8_RLIMIT_PIPE")
                        os.close(limit_write)
                    self.remaining()
                    mark("child_setup")
                    process = subprocess.Popen(argv, cwd=cwd, env=effective_env,
                        stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, close_fds=True,
                        pass_fds=(limit_write,), preexec_fn=child_limits)
                    os.close(limit_write)
                    limit_write = None
                    raw_limits = os.read(limit_read, 4097)
                    os.close(limit_read)
                    limit_read = None
                    need(0 < len(raw_limits) <= 4096, "D8_RLIMIT_PIPE")
                    receipt["effective_limits"] = json.loads(raw_limits)
                    need(os.getpgid(process.pid) == os.getpgrp(), "D8_CHILD_GROUP")
                    with selectors.DefaultSelector() as selector:
                        for stream, file, bound in ((process.stdout, out, stdout_limit),
                                                     (process.stderr, err, stderr_limit)):
                            os.set_blocking(stream.fileno(), False)
                            selector.register(stream, selectors.EVENT_READ,
                                              {"file": file, "limit": bound, "written": 0})
                        while selector.get_map() or process.poll() is None:
                            left = self.remaining()
                            for key, _ in selector.select(min(left, 0.05)):
                                block = os.read(key.fd, 65536)
                                if not block:
                                    selector.unregister(key.fileobj)
                                    key.fileobj.close()
                                    continue
                                state = key.data
                                need(state["written"] + len(block) <= state["limit"], "D8_COMMAND_LOG_BOUND")
                                self.remaining()
                                need(state["file"].write(block) == len(block), "D8_SHORT_WRITE")
                                state["written"] += len(block)
                        receipt["returncode"] = process.wait()
                        mark("child_and_pipe_drain")
            mark("child_accounting")
            need(receipt["returncode"] == 0, "D8_COMMAND_EXIT")
            CLIENT.ask("COMMAND_QUIESCENT", label=label)
            mark("quiescent_ack")
            after_tool = tool_inventory()
            mark("after_inventory")
            receipt["tool_inventory_after"] = inventory_reference(after_tool)
            if expected_files is not None:
                scratch = OUTPUT / "scratch/current"
                actual = {p for p in scratch.rglob("*") if p.is_file()}
                need(actual <= {Path(p) for p in budget().case_state["scientific"]} and
                     all(p.is_file() and p.stat().st_size <= limits["FSIZE"] for p in expected_files),
                     "D8_SCIENTIFIC_FILE_SET")
                need(before_tool == after_tool, "D8_SCIENTIFIC_TOOL_WRITE")
            budget().check()
            receipt.update(stdout=desc(stdout), stderr=desc(stderr))
            mark("postchild_accounting")
            receipt.update(status="PASS", lifecycle="TERMINAL", elapsed_seconds=time.monotonic()-begin)
            command_dump(receipt_path, receipt, replace=True)
            dump(self.path, self.report, replace=True)
            self.remaining()
            # ACK requires the complete descendant set to be gone. The command
            # deadline is still armed during pipe drain, receipt I/O and waiting.
            captured = stdout.read_bytes()
            self.remaining()
            CLIENT.ask("COMMAND_END", label=label, terminal=True)
            return captured
        except BaseException as error:
            self._remember_failure(error, label)
            receipt["reason"] = str(error) if isinstance(error, (ValueError, TimeoutError)) else type(error).__name__
            self.remaining()
            try:
                receipt.update(lifecycle="TERMINAL", elapsed_seconds=time.monotonic()-begin,
                               stdout=desc(stdout) if stdout.is_file() else None,
                               stderr=desc(stderr) if stderr.is_file() else None)
                command_dump(receipt_path, receipt, replace=True)
                self._preserve_failure()
            except Exception:
                pass
            if process is not None and process.poll() is None:
                CLIENT.ask("ABORT", label=label)  # unknown/fatal request kills whole group, not a graceful timeout
            raise
        finally:
            for fd in (limit_read, limit_write):
                if fd is not None:
                    os.close(fd)

def git(phase, label, *arguments, **options):
    return phase.run(label, ["git", "-c", "core.fsmonitor=false", "-c", "core.untrackedCache=false", "-C", str(ROOT), *arguments], **options)

def tree_entries(raw):
    result = {}
    for row in raw.split(b"\0"):
        if not row:
            continue
        meta, path = row.split(b"\t", 1)
        mode, kind, oid = meta.decode().split()
        name = path.decode()
        need(kind == "blob" and mode in ("100644", "100755") and
             name not in result, "D8_SOURCE_TREE")
        result[name] = {"git_mode": mode, "git_blob": oid}
    return result

def source_identity(phase):
    lock = contract()
    head = git(phase, "head", "rev-parse", "HEAD").decode().strip()
    tree = git(phase, "tree", "rev-parse", "HEAD^{tree}").decode().strip()
    need(SHA.fullmatch(head) and SHA.fullmatch(tree), "D8_SOURCE_TREE")
    need(git(phase, "freeze-tree", "rev-parse", FREEZE + "^{tree}").decode().strip() == FREEZE_TREE,
         "D8_FROZEN_CONTRACT_CHANGED")
    need(git(phase, "base-tree", "rev-parse", BASE + "^{tree}").decode().strip() == BASE_TREE,
         "D8_SOURCE_TREE")
    need(not git(phase, "clean", "status", "--porcelain=v1", "--untracked-files=all").strip(),
         "D8_UNCOMMITTED_SOURCE")
    names = set(lock["production_files"]) | set(lock["frozen_helper_files"]) | set(lock["source_closure"]["D8_files"])
    current = tree_entries(git(phase, "selected-tree", "ls-tree", "-r", "-z", "--full-tree", head,
                              "--", *sorted(names)))
    need(set(current) == names, "D8_SOURCE_TREE")
    # Modes absent from the historical helper JSON are fixed by the immutable base tree.
    base = tree_entries(git(phase, "base-selected-tree", "ls-tree", "-r", "-z", "--full-tree", BASE,
                           "--", *sorted(set(lock["production_files"]) | set(lock["frozen_helper_files"]))))
    for name, record in lock["production_files"].items():
        need(current[name] == base[name] == {k: record[k] for k in ("git_mode", "git_blob")},
             "D8_PRODUCTION_CHANGED")
    for name, record in lock["frozen_helper_files"].items():
        need(current[name] == base[name] and base[name]["git_blob"] == record["git_blob"],
             "D8_HELPER_MODE_OR_BLOB")
    # Tree roots prove that no new production file was silently omitted.
    for i, (name, record) in enumerate(lock["unchanged_production_objects"].items()):
        need(git(phase, "production-root-" + str(i), "rev-parse", head + ":" + name).decode().strip()
             == record["git_object"], "D8_PRODUCTION_CHANGED")
    for name in names:
        need(blob((ROOT / name).read_bytes()) == current[name]["git_blob"], "D8_UNCOMMITTED_SOURCE")
        current[name].update(desc(ROOT / name))
    need(sum(x["bytes"] for x in current.values()) <= SOURCE_LIMIT, "D8_SOURCE_BYTES_BOUND")
    historical = git(phase, "historical-workflow", "show", BASE + ":.github/workflows/frontend-research.yml").decode()
    current_workflow = (ROOT / ".github/workflows/frontend-research.yml").read_text()
    marker = "\n  dualmic-broadside-output-d8:\n"
    need(current_workflow.count(marker) == 1 and historical.split("  matrix:\n", 1)[1] ==
         current_workflow.split("  matrix:\n", 1)[1].split(marker, 1)[0],
         "D8_HISTORICAL_JOBS_CHANGED")
    for module in list(sys.modules.values()):
        path = getattr(module, "__file__", None)
        if path:
            try:
                name = Path(path).resolve().relative_to(ROOT).as_posix()
            except ValueError:
                continue
            need(name in names and name not in EXPLANATORY, "D8_RUNTIME_IMPORT_CLOSURE:" + name)
    return {"revision": head, "tree": tree, "files": current}

def archive_members(path, identity, destination=None):
    names = set(identity["files"])
    seen_files, seen_dirs, total = set(), set(), 0
    need(Path(path).stat().st_size <= SOURCE_LIMIT, "D8_SOURCE_ARCHIVE_BOUND")
    with tarfile.open(path, "r:") as archive:
        need(archive.pax_headers.get("comment") == identity["revision"], "D8_SOURCE_ARCHIVE_REVISION")
        for member in archive:
            name = member.name.rstrip("/")
            pure = PurePosixPath(name)
            need(name and pure.as_posix() == name and not pure.is_absolute() and ".." not in pure.parts
                 and "\\" not in name and (member.isfile() or member.isdir()), "D8_SOURCE_ARCHIVE_PATH")
            if member.isdir():
                need(name not in seen_dirs, "D8_SOURCE_ARCHIVE_DUPLICATE")
                seen_dirs.add(name)
                if destination is not None:
                    (destination / name).mkdir(parents=True, exist_ok=True)
                continue
            need(name in names and name not in seen_files, "D8_SOURCE_CLOSURE")
            seen_files.add(name)
            spec = identity["files"][name]
            need(member.size == spec["bytes"] and member.mode & 0o777 == int(spec["git_mode"], 8) & 0o777,
                 "D8_SOURCE_ARCHIVE_MODE")
            total += member.size
            need(total <= SOURCE_LIMIT, "D8_SOURCE_BYTES_BOUND")
            f = archive.extractfile(member)
            need(f is not None, "D8_SOURCE_ARCHIVE_MEMBER")
            raw = f.read(member.size + 1)
            need(len(raw) == member.size and blob(raw) == spec["git_blob"] and
                 hashlib.sha256(raw).hexdigest() == spec["sha256"], "D8_SOURCE_RESEALED")
            if destination is not None:
                target = destination / name
                target.parent.mkdir(parents=True, exist_ok=True)
                tool_write(target, raw)
                target.chmod(member.mode & 0o777)
    need(seen_files == names and seen_dirs == directories(names), "D8_SOURCE_CLOSURE")


def select_tool_lookup(name, executable_paths):
    """Pure ordered selection from explicit candidates, never from ambient PATH."""
    need(type(name) is str and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.+-]{0,63}", name) is not None,
         "D8_TOOL_NAME")
    candidates = [directory + "/" + name for directory in SEALED_PATH.split(":")]
    available = set(executable_paths)
    for path in candidates:
        if path in available:
            return path
    error = ValueError("D8_TOOL_MISSING")
    error.d8_tool_lookup = {"tool": name, "path": SEALED_PATH, "candidates": candidates}
    raise error

def tool_identity(name):
    # Actual executability comes from shutil.which. The shared selector then
    # preserves the original /usr/bin, /bin precedence before local fallback.
    executable_paths = [shutil.which(name, path=directory) for directory in SEALED_PATH.split(":")]
    lookup = select_tool_lookup(name, executable_paths)
    path = Path(lookup).absolute()
    real = path.resolve(strict=True)
    need(real.is_file() and not (real.stat().st_mode & (stat.S_ISUID | stat.S_ISGID)), "D8_TOOL_PRIVILEGE")
    return {"lookup_path": str(path), "lookup_symlink_target": os.readlink(path) if path.is_symlink() else None,
            "resolved_path": str(real), "file": desc(real)}

def configure_argv(cmake, compiler, source, build, revision):
    return [cmake, "-S", str(source), "-B", str(build), "-G", "Unix Makefiles",
        "-DCMAKE_BUILD_TYPE=Release", "-DCMAKE_C_COMPILER=" + compiler, "-DCMAKE_C_FLAGS=",
        "-DCMAKE_C_FLAGS_RELEASE=-O3 -DNDEBUG", "-DCMAKE_EXPORT_COMPILE_COMMANDS=ON",
        "-DCMAKE_FIND_USE_PACKAGE_REGISTRY=OFF", "-DCMAKE_FIND_USE_SYSTEM_PACKAGE_REGISTRY=OFF",
        "-DCMAKE_EXPORT_PACKAGE_REGISTRY=OFF",
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
    error = ValueError("D8_BUILD_FLAGS")
    error.d8_build_flags = detail
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
        return parse_flags(path.read_text(), TOOL / build.name if build.parent == OUTPUT / "build" else build)
    except ValueError as error:
        if str(error) == "D8_BUILD_FLAGS":
            # No extra I/O here: the existing phase/root failure path persists
            # and prints this bounded detail without changing the first reason.
            error.d8_build_flags.update({
                "target": str(path),
                "cmake_version_receipt": str(OUTPUT / "baseline-build-logs/cmake-version.command.json"),
                "cmake_version_stdout": str(OUTPUT / "baseline-build-logs/cmake-version.stdout"),
                "configure_receipt": str(OUTPUT / (build.name.split("-")[0] + "-build-logs") /
                    (build.name.removesuffix("-build") + "-configure.command.json")),
                "actual_argv": str(build / "compile_commands.json")})
        raise

def observer_argv(compiler, source, build, actual_flags):
    return [compiler, *actual_flags["C_DEFINES"], *actual_flags["C_INCLUDES"],
            *actual_flags["C_FLAGS"], "-MMD", "-MF", str(build / "observer.d"),
            str(source / C_PATH), str(build / "libaudio_pipeline.a"),
            "-lm", "-o", str(build / "ap_process_pcm_observer")]

def check_command_record(receipt, argv=None):
    need(receipt["status"] == "PASS" and receipt["lifecycle"] == "TERMINAL" and
         type(receipt["returncode"]) is int and
         type(receipt["timeout_seconds"]) in (int, float) and type(receipt["elapsed_seconds"]) in (int, float) and
         receipt["returncode"] == 0 and receipt["timed_out"] is False
         and 0 < receipt["timeout_seconds"] <= 30 and 0 <= receipt["elapsed_seconds"] <= 30,
         "D8_FAILED_COMMAND")
    timing = check_subtimings(receipt["subtimings"])
    offsets = timing["offsets"]
    need(abs(timing["origin"] + offsets["begin_ack"] -
             (receipt["deadline"] - receipt["timeout_seconds"])) <= 0.000001 and
         offsets["postchild_accounting"] - offsets["begin_ack"] <= receipt["elapsed_seconds"] + 0.000001,
         "D8_COMMAND_TIMINGS")
    if argv is not None:
        need(receipt["argv"] == argv, "D8_ARGV")
    expected = environment(receipt["environment"].get("AP_D1_STAGE_DIR"),
                           receipt["environment"].get("AP_D8_STAGE_DIR"),
                           int(receipt["environment"]["AP_D8_EXPECTED_FRAMES"]) if
                           "AP_D8_EXPECTED_FRAMES" in receipt["environment"] else None)
    check_execution_environment(receipt, expected)
    expected_limits = dict(supervision.TOOL_LIMITS)
    scientific = receipt.get("scientific")
    if scientific is not None:
        need(type(scientific["frames"]) is int and 529 <= scientific["frames"] <= 629 and
             scientific["form"] in FORMS, "D8_COMMAND_LIMITS")
        expected_limits["FSIZE"] = scientific["frames"] * (640 if scientific["form"].endswith("observed") else 320)
    need(receipt["requested_limits"] == expected_limits and
         receipt["deadline"] <= receipt["phase_deadline"] <= receipt["root_deadline"] and
         set(receipt["effective_limits"]) == set(expected_limits), "D8_COMMAND_LIMITS")
    for name, row in receipt["effective_limits"].items():
        need(row["requested"] == expected_limits[name] and
             all(type(row[k]) is int and (row[k] >= 0 or row[k] == resource.RLIM_INFINITY)
                 for k in ("inherited_soft", "inherited_hard")), "D8_COMMAND_LIMITS")
        expected = min(v for v in (row["inherited_soft"], row["inherited_hard"], expected_limits[name])
                       if v != resource.RLIM_INFINITY)
        need(type(row["soft"]) is int and type(row["hard"]) is int and
             row["soft"] == row["hard"] == expected, "D8_COMMAND_LIMITS")
    return receipt

def check_command(path, argv=None):
    receipt = check_command_record(read(path), argv)
    before = check_inventory_reference(receipt["tool_inventory_before"])
    after = check_inventory_reference(receipt["tool_inventory_after"])
    if receipt.get("scientific") is not None:
        need(Path(path).stat().st_size <= 65536 and before == after, "D8_SCIENTIFIC_RECEIPT_BOUND")
    prefix = str(path).removesuffix(".command.json")
    need(desc(Path(prefix + ".stdout")) == receipt["stdout"] and
         desc(Path(prefix + ".stderr")) == receipt["stderr"], "D8_COMMAND_LOG")
    return receipt

def check_phase_record(value, name):
    need(value["phase"] == name and value["status"] == "PASS" and value["budget_seconds"] == 300
         and value["first_failure"] is None and 0 <= value["elapsed_seconds"] <= 300,
         "D8_FAILED_PHASE:" + name)

def check_execution_environment(receipt, env):
    need(receipt["environment"] == env, "D8_EXECUTION_ENVIRONMENT")
    return True

def check_phase(root, name):
    value = read(root / (name + "-phase.json"))
    check_phase_record(value, name)
    need(len(value["commands"]) == len(set(value["commands"])), "D8_PHASE_COMMAND_SET")
    for p in value["commands"]:
        need(re.fullmatch(re.escape(name) + r"-logs/[A-Za-z0-9_.-]+\.command\.json", p) is not None,
             "D8_PHASE_COMMAND_SET")
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
    detail["cmake_version_receipt"] = str(OUTPUT / "baseline-build-logs/cmake-version.command.json")
    error = ValueError(reason)
    error.d8_generated = detail
    raise error

def parse_generated_unity(raw, source, identity):
    need(identity["files"]["CMakeLists.txt"]["git_blob"] == "a2bda471593f32fcd96470d828839aedf286273e" and
         all(name in identity["files"] for name in UNITY_SOURCES), "D8_COMPILED_SOURCE_CLOSURE")
    origin = TOOL / source.name if source.parent == OUTPUT / "build" else source
    expected = [
        ("/* generated by CMake */\n\n" + "".join(
            comment + '#include "' + str(origin / name) + '"\n\n'
            for name in UNITY_SOURCES)).encode()
        for comment in UNITY_COMMENTS]
    if raw not in expected:
        generated_error("D8_GENERATED_UNITY", "unity", UNITY_NAME,
            {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest(),
             "prefix": raw[:1024].decode("utf-8", errors="backslashreplace")},
            {"whole_document_sha256": [hashlib.sha256(v).hexdigest() for v in expected],
             "ordered_sources": UNITY_SOURCES, "comment_forms": UNITY_COMMENTS})
    return {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest(),
            "form": expected.index(raw), "ordered_sources": list(UNITY_SOURCES)}

def generated_unity(path, source, identity):
    expected_path = source.parent / (source.name.removesuffix("-source") + "-build") / UNITY_NAME
    need(path == expected_path, "D8_COMPILED_SOURCE_CLOSURE")
    return {"path": UNITY_NAME, **parse_generated_unity(path.read_bytes(), source, identity)}


def compiler_search_roots(stderr):
    lines = stderr.splitlines()
    start, end = "#include <...> search starts here:", "End of search list."
    if lines.count(start) != 1 or lines.count(end) != 1 or lines.index(start) >= lines.index(end):
        generated_error("D8_COMPILER_SEARCH", "compiler-search", "compiler-header-search.stderr",
                        lines[:12], "one complete GCC system include search section")
    entries = lines[lines.index(start)+1:lines.index(end)]
    result = []
    for line in entries:
        raw = line.strip()
        path = Path(raw)
        need(line.startswith(" ") and path.is_absolute() and path.is_dir(), "D8_COMPILER_SEARCH")
        real = path.resolve(strict=True)
        need(real.is_relative_to(Path("/usr")) and real != Path("/usr"), "D8_COMPILER_SEARCH")
        need(str(real) not in [row["canonical"] for row in result], "D8_COMPILER_SEARCH")
        result.append({"raw": raw, "canonical": str(real)})
    need(result, "D8_COMPILER_SEARCH")
    return result

def system_roots():
    # Receipt is validated here and again against the exact resolved compiler
    # argv by verify_build. No arbitrary external dependency is called "system".
    path = OUTPUT / "baseline-build-logs/compiler-header-search.command.json"
    receipt = check_command(path)
    need(receipt["argv"][1:] == ["-E", "-x", "c", "/dev/null", "-v"], "D8_COMPILER_SEARCH")
    return compiler_search_roots(path.with_name("compiler-header-search.stderr").read_text())

def _dependency_path(word, source, build, identity, roots, cwd):
    raw = Path(word)
    path = raw if raw.is_absolute() else cwd / raw
    if source.parent == OUTPUT / "build" and path.is_relative_to(TOOL):
        path = source.parent / path.relative_to(TOOL)
    for scope, root in (("source", source), ("generated", build)):
        if not path.is_relative_to(root):
            continue
        # Process every original component in order, rejecting a symlink even
        # when followed by '..'. Never leave a frozen root and then re-enter.
        cursor = root
        if root.is_symlink() or root.resolve(strict=True) != root:
            generated_error("D8_DEPENDENCY_SYMLINK", "dependency", word, str(root), "ordinary root")
        for part in path.relative_to(root).parts:
            if part == "..":
                if cursor == root:
                    generated_error("D8_DEPENDENCY_ESCAPE", "dependency", word, str(path), str(root))
                need(cursor.is_dir(), "D8_DEPENDENCY_REGULAR")
                cursor = cursor.parent
            elif part != ".":
                need(cursor.is_dir(), "D8_DEPENDENCY_REGULAR")
                cursor = cursor / part
                if cursor.is_symlink():
                    generated_error("D8_DEPENDENCY_SYMLINK", "dependency", word, str(cursor), "no symlink")
        need(cursor.is_file() and cursor.resolve(strict=True) == cursor, "D8_DEPENDENCY_REGULAR")
        name = cursor.relative_to(root).as_posix()
        if scope == "source":
            need(name in identity["files"], "D8_COMPILED_SOURCE_CLOSURE")
        else:
            need(name in ("generated/audio_pipeline/audio_pipeline_build.h", UNITY_NAME),
                 "D8_GENERATED_HEADER_CLOSURE")
            if name == UNITY_NAME:
                generated_unity(cursor, source, identity)
        return {"raw": word, "scope": scope, "canonical": str(cursor), "member": name}
    # System headers are not claimed as part of the historical source closure.
    # GCC canonicalizes these separately; require both raw and canonical paths
    # to stay in its observed search roots. This cannot authorize repo escapes.
    allowed = [Path(row["canonical"]) for row in roots]
    if not any(path.is_relative_to(root) for root in allowed):
        generated_error("D8_DEPENDENCY_OUTSIDE", "dependency", word, str(path),
                        "frozen source/generated member or observed compiler system root")
    real = path.resolve(strict=True)
    need(real.is_file() and any(real.is_relative_to(root) for root in allowed),
         "D8_DEPENDENCY_OUTSIDE")
    return {"raw": word, "scope": "system", "canonical": str(real)}


def dependency_path(word, source, build, identity, roots, cwd):
    try:
        return _dependency_path(word, source, build, identity, roots, cwd)
    except ValueError as error:
        if str(error).startswith("D8_") and not hasattr(error, "d8_generated"):
            detail = {"category": "dependency", "raw": word, "source": str(source),
                      "build": str(build), "cwd": str(cwd), "system_roots": roots}
            encoded = json.dumps(detail, ensure_ascii=True, sort_keys=True)
            if len(encoded) > 4096:
                detail = {"category": "dependency", "detail_truncated": True, "prefix": encoded[:2048]}
            error.d8_generated = detail
        raise

def check_compile_closure(build_root, identity, kind):
    source, build = build_root / (kind + "-source"), build_root / (kind + "-build")
    commands = read(build / "compile_commands.json")
    need(commands and all(type(row) is dict for row in commands), "D8_COMPILE_COMMANDS")
    for row in commands:
        origin_build = TOOL / build.name if build.parent == OUTPUT / "build" else build
        need(row["directory"] == str(origin_build), "D8_COMPILED_SOURCE_CLOSURE")
        actual_file = Path(row["file"])
        if build.parent == OUTPUT / "build" and actual_file.is_relative_to(TOOL):
            actual_file = build.parent / actual_file.relative_to(TOOL)
        try:
            name = actual_file.relative_to(source).as_posix()
        except ValueError:
            name = actual_file.relative_to(build).as_posix()
            need(re.fullmatch(r"CMakeFiles/audio_pipeline.dir/Unity/unity_[0-9]+_c.c", name),
                 "D8_COMPILED_SOURCE_CLOSURE")
            generated_unity(actual_file, source, identity)
        else:
            need(name in identity["files"], "D8_COMPILED_SOURCE_CLOSURE")
        argv = shlex.split(row["command"])
        need("-ffast-math" not in argv and argv[0] == tool_identity("cc")["resolved_path"], "D8_BUILD_FLAGS")
    # Make's generated dependency files explicitly retain every repository header.
    dependencies = list(build.rglob("*.o.d"))
    if kind.endswith("observed"):
        need((build / "observer.d").is_file(), "D8_HEADER_DEPENDENCIES")
        dependencies.append(build / "observer.d")
    need(dependencies, "D8_HEADER_DEPENDENCIES")
    roots = system_roots()
    dependency_members = {}
    for dep in dependencies:
        words = shlex.split(dep.read_text().replace("\\\n", " "))
        need(len(words) >= 2 and words[0].endswith(":"), "D8_HEADER_DEPENDENCIES")
        cwd = ROOT if dep.name == "observer.d" else (TOOL / build.name if build.parent == OUTPUT / "build" else build)
        dependency_members[dep.relative_to(build).as_posix()] = [
            dependency_path(word, source, build, identity, roots, cwd) for word in words[1:]]
    return {"compile_commands": desc(build / "compile_commands.json"),
            "system_search_roots": roots, "dependency_members": dependency_members,
            "dependency_files": {p.relative_to(build).as_posix(): desc(p) for p in dependencies}}


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
    need(info["config_digest"] == config_digest, "D8_HEADER_RESEALED")
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
    template = (root / "baseline-plain-source/cmake/audio_pipeline_build.h.in").read_text()
    names = re.findall(r"@([A-Z_a-z0-9]+)@", template)
    need(set(names) == set(values), "D8_HEADER_RESEALED")
    for name, value in values.items():
        template = template.replace("@" + name + "@", value)
    return template.encode()



def tool_write(path, raw, *, replace=False):
    need(budget().retiring is None, "D8_RETIREMENT_WRITE")
    path = Path(path)
    need(path.is_relative_to(TOOL) and len(raw) <= 16777216, "D8_TOOL_FILE_BOUND")
    actual = tool_inventory()
    previous = path.stat().st_size if path.exists() else 0
    need(sum(v["bytes"] for v in actual["files"].values()) - previous + len(raw) <= 134217728,
         "D8_TOOL_POSTHOC_BYTES")
    need(not path.is_symlink(), "D8_TOOL_SYMLINK")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb" if replace else "xb", buffering=0) as stream:
        view = memoryview(raw)
        while view:
            job_remaining()
            size = stream.write(view[:65536])
            need(size is not None and size > 0, "D8_SHORT_WRITE")
            view = view[size:]
    return desc(path)

def transformed(raw, spec):
    before, after = spec["before"].encode(), spec["after"].encode()
    need(raw.count(before) == 1 and after not in raw and spec["occurrences"] == 1,
         "D8_TRANSFORM_SITE")
    result = raw.replace(before, after, 1)
    need(inverse(result, spec) == raw, "D8_TRANSFORM_BODY")
    return result

def inverse(raw, spec):
    before, after = spec["before"].encode(), spec["after"].encode()
    need(raw.count(after) == 1 and before not in raw, "D8_TRANSFORM_SITE")
    return raw.replace(after, before, 1)

def form_specs(form, lock=None):
    lock = contract() if lock is None else lock
    need(form in FORMS, "D8_BUILD_FORM")
    result = []
    if form.startswith("candidate"):
        result.append(("mathematical", lock["intervention"]))
    if form.endswith("observed"):
        result += [("observer-%02d" % i, spec) for i, spec in
                   enumerate(lock["observer"]["source_transforms"])]
    return result

def member_specs(form, name, lock=None):
    return [(kind, spec) for kind, spec in form_specs(form, lock) if spec["path"] == name]

def apply_form(source, form, identity, lock):
    records = []
    # Preserve the whole frozen order, including the two consecutive D1 edits.
    for kind, change in form_specs(form, lock):
        path = source / change["path"]
        before = path.read_bytes()
        after = transformed(before, change)
        tool_write(path, after, replace=True)
        records.append({"kind": kind, "path": change["path"],
            "before_sha256": hashlib.sha256(before).hexdigest(),
            "after_sha256": hashlib.sha256(after).hexdigest(),
            "inverse_sha256": hashlib.sha256(inverse(after, change)).hexdigest()})
    return records


def expected_member(form, name, identity, lock=None):
    spec = identity["files"][name]
    original = (ROOT / name).read_bytes()
    need(blob(original) == spec["git_blob"] and
         {"bytes": len(original), "sha256": hashlib.sha256(original).hexdigest()} ==
         {k: spec[k] for k in ("bytes", "sha256")}, "D8_SOURCE_RESEALED")
    value = original
    records = []
    for transform_kind, change in member_specs(form, name, lock):
        changed = transformed(value, change)
        records.append({"kind": transform_kind, "path": name,
            "before_sha256": hashlib.sha256(value).hexdigest(),
            "after_sha256": hashlib.sha256(changed).hexdigest(),
            "inverse_sha256": hashlib.sha256(inverse(changed, change)).hexdigest()})
        value = changed
    undone = value
    for _, change in reversed(member_specs(form, name, lock)):
        undone = inverse(undone, change)
    need(undone == original, "D8_TRANSFORM_BODY")
    return value, records

def check_source_member(form, name, raw, identity, *, lock=None):
    expected, records = expected_member(form, name, identity, lock)
    reason = ("D8_SOURCE_RESEALED" if form == "baseline-plain" else
              "D8_OBSERVER_ENTRY" if name.endswith("dualmic_stages_d1.c") else "D8_TRANSFORM_BODY")
    need(raw == expected, reason)
    return records

def sourcecheck(build_root, identity):
    lock = contract()
    result = {}
    for form in FORMS:
        source = build_root / (form + "-source")
        exact_closure(source, identity["files"], "D8_SOURCE_CLOSURE")
        records, changed = [], []
        for name, spec in identity["files"].items():
            path = source / name
            need(path.stat().st_mode & 0o777 == int(spec["git_mode"], 8) & 0o777, "D8_SOURCE_MODE")
            transformations = check_source_member(form, name, path.read_bytes(), identity, lock=lock)
            records.extend(transformations)
            if transformations:
                changed.append(name)
        need(set(changed) == {spec["path"] for _, spec in
             sum([member_specs(form, name, lock) for name in identity["files"]], [])}, "D8_CHANGED_FILE_SET")
        order = {kind: index for index, (kind, _) in enumerate(form_specs(form, lock))}
        records.sort(key=lambda row: order[row["kind"]])
        result[form] = {"changed_files": sorted(changed), "transforms": records}
    return result

check_sources = sourcecheck

def check_source_identity(saved, actual):
    need(saved == actual, "D8_SOURCE_TREE")

def check_compiler_identity(compiler, cmake):
    need(compiler == tool_identity("cc") and cmake == tool_identity("cmake"), "D8_COMPILER_IDENTITY")

def check_header_member(raw, root, revision, info):
    need(raw == header_expected(root, revision, info), "D8_HEADER_RESEALED")
    return True

def check_headers(root, revision, infos):
    headers = {}
    for form in FORMS:
        info = infos[form.split("-")[0] + "-plain"]
        suffix = contract()["build"]["source_revision_suffixes"][form]
        path = root / (form + "-build/generated/audio_pipeline/audio_pipeline_build.h")
        check_header_member(path.read_bytes(), root, revision + suffix, info)
        headers[form] = desc(path)
    return headers

def retain_tool_outputs(identity):
    complete = tool_inventory()
    allowed_roots = {"exact-source.tar"} | {form + ending for form in FORMS for ending in ("-source", "-build")}
    selected = {name: record for name, record in complete["files"].items()
                if PurePosixPath(name).parts[0] in allowed_roots}
    need(set(complete["files"]) == set(selected), "D8_UNEXPECTED_TOOL_OUTPUT")
    root = OUTPUT / "build"
    root.mkdir(parents=True, exist_ok=True)
    for name, expected in selected.items():
        source, destination = TOOL / name, root / name
        if destination.exists():
            equal_files(source, destination)
        else:
            bounded_copy(source, destination)
            destination.chmod(source.stat().st_mode & 0o777)
        need(desc(destination) == expected, "D8_RETAINED_BUILD_COPY")
    need(sum(record["bytes"] for record in selected.values()) <= CAPS[
         "all_source_archive_derived_build_provenance"], "D8_SOURCE_BUILD_CATEGORY_OVERFLOW")
    return {"complete_tool_inventory": complete, "selected_files": selected}

def build(expected_revision):
    report = {"experiment": EXPERIMENT, "freeze": FREEZE, "status": "FAIL", "programs": {},
              "forms": {}, "build_infos": {}, "source_transforms": {},
              "toolchain_aggregate_prewrite_guarantee": False}
    with Phase("baseline-build") as phase:
        # Setup inventory and immutable contract/helper readback are protected
        # work, so the phase lease must be acknowledged before their first I/O.
        need(not (OUTPUT / "build").exists() and (not TOOL.exists() or not tool_inventory()["files"]),
             "D8_NEW_BUILD_REQUIRED")
        lock = contract()
        prepare_tool_environment()
        identity = source_identity(phase)
        need(identity["revision"] == expected_revision, "D8_EXECUTION_HEAD")
        report["source"] = identity
        report["compiler"], report["cmake"] = tool_identity("cc"), tool_identity("cmake")
        compiler, cmake = report["compiler"]["resolved_path"], report["cmake"]["resolved_path"]
        version = phase.run("compiler-version", [compiler, "--version"]).decode()
        compiler_version = phase.run("compiler-full-version", [compiler, "-dumpfullversion"]).decode().strip()
        compiler_target = phase.run("compiler-target", [compiler, "-dumpmachine"]).decode().strip()
        need("Free Software Foundation" in version, "D8_COMPILER_FAMILY")
        phase.run("cmake-version", [cmake, "--version"])
        phase.run("compiler-header-search", [compiler, "-E", "-x", "c", "/dev/null", "-v"])
        report["system_search_roots"] = system_roots()
        archive = TOOL / "exact-source.tar"
        phase.run("archive", ["git", "-C", str(ROOT), "-c", "tar.umask=0022", "archive", "--format=tar",
            "--output=" + str(archive), identity["revision"], "--", *sorted(identity["files"])])
        report["source_archive"] = desc(archive)
        for form in FORMS:
            destination = TOOL / (form + "-source")
            destination.mkdir()
            archive_members(archive, identity, destination)
            report.setdefault("applied_transforms", {})[form] = apply_form(destination, form, identity, lock)
        report["source_transforms"] = sourcecheck(TOOL, identity)
        need(all(report["applied_transforms"][form] == report["source_transforms"][form]["transforms"]
                 for form in FORMS), "D8_TRANSFORM_BODY")
        _build_arm(phase, "baseline", report, compiler, cmake, compiler_version, compiler_target)
        report["baseline_retention"] = retain_tool_outputs(identity)
    with Phase("candidate-build") as phase:
        _build_arm(phase, "candidate", report, compiler, cmake, compiler_version, compiler_target)
        report["final_retention"] = retain_tool_outputs(identity)
        root = OUTPUT / "build"
        need(sourcecheck(root, identity) == report["source_transforms"] and
         all(report["applied_transforms"][form] == report["source_transforms"][form]["transforms"]
             for form in FORMS), "D8_TRANSFORM_BODY")
        for form in FORMS:
            report["forms"][form]["dependencies"] = check_compile_closure(root, identity, form)
            executable = "ap_process_pcm_observer" if form.endswith("observed") else "ap_process_pcm"
            relative = (Path("build") / (form + "-build") / executable).as_posix()
            report["programs"][form] = {"path": relative, **desc(OUTPUT / relative),
                "source_revision": identity["revision"] + lock["build"]["source_revision_suffixes"][form]}
        report["build_info"] = report["build_infos"]["baseline-plain"]
        report["headers"] = check_headers(root, identity["revision"], report["build_infos"])
        report["status"] = "BUILT"
        report["artifact_inventory"] = inventory(root)
        dump(root / "build.json", report)
    return report

def _build_arm(phase, arm, report, compiler, cmake, compiler_version, compiler_target):
    identity, lock = report["source"], contract()
    for mode in ("plain", "observed"):
        form = arm + "-" + mode
        source, binary = TOOL / (form + "-source"), TOOL / (form + "-build")
        revision = identity["revision"] + lock["build"]["source_revision_suffixes"][form]
        phase.run(form + "-configure", configure_argv(cmake, compiler, source, binary, revision))
        targets = ["ap_process_pcm", "ap_build_info_dump"] if mode == "plain" else ["audio_pipeline"]
        phase.run(form + "-compile", [cmake, "--build", str(binary), "--target", *targets,
                                      "--parallel", "2", "--verbose"])
        actual = flags(binary)
        if report["forms"]:
            common = next(iter(report["forms"].values()))["flags"]
            need(actual["C_DEFINES"] == common["C_DEFINES"] and
                 actual["C_FLAGS"] == common["C_FLAGS"], "D8_BUILD_FLAGS")
        report["forms"][form] = {"flags": actual, "source_revision": revision,
                                 "actual_source": str(source), "actual_build": str(binary)}
        if mode == "plain":
            rows = phase.run(form + "-build-info", [str(binary / "ap_build_info_dump")]).decode().splitlines()
            need(rows and all("=" in s for s in rows) and len({s.split("=", 1)[0] for s in rows}) == len(rows),
                 "D8_BUILD_INFO")
            info = dict(s.split("=", 1) for s in rows)
            expected = {"source_revision": revision, "version": "2.3.64", "module_mask": "1023",
                "aec_backend": "MDF", "ns_estimator": "EMA", "simd_backend": "SCALAR",
                "fast_math": "0", "resampler_mode": "BANDLIMITED", "build_type": "Release"}
            need(all(info.get(k) == v for k, v in expected.items()), "D8_BUILD_INFO")
            need(info["compiler_id"] == "GNU" and info["compiler_version"] == compiler_version and
                 info["target_triple"] == compiler_target, "D8_COMPILER_IDENTITY")
            report["build_infos"][form] = info
        else:
            phase.run(form + "-observer", observer_argv(compiler, source, binary, actual))
            engineering = json.loads(phase.run(form + "-engineering", [
                str(binary / "ap_process_pcm_observer"), "--d8-self-test", arm]))
            expected = {"status": "PASS", "arm": arm, "comparisons": 10584,
                "equation_comparisons": 10584, "equation_samples": 1693440, "agc_comparisons": 32,
                "record_comparisons": 4, "layout_checked": True, "negative_checks": 21}
            need(engineering == expected, "D8_ENGINEERING")
            report["forms"][form]["engineering"] = engineering

VERIFIED_CONTEXT = None

def verify_build(phase):
    global VERIFIED_CONTEXT
    root = OUTPUT / "build"
    report = read(root / "build.json")
    identity = source_identity(phase)
    check_source_identity(report["source"], identity)
    need(report["status"] == "BUILT" and report["freeze"] == FREEZE and
         report["toolchain_aggregate_prewrite_guarantee"] is False, "D8_FAILED_BUILD")
    check_compiler_identity(report["compiler"], report["cmake"])
    actual = inventory(root)
    del actual["files"]["build.json"]
    need(actual == report["artifact_inventory"], "D8_BUILD_CLOSURE")
    archive_members(root / "exact-source.tar", identity)
    need(desc(root / "exact-source.tar") == report["source_archive"], "D8_SOURCE_ARCHIVE_HASH")
    need(sourcecheck(root, identity) == report["source_transforms"], "D8_TRANSFORM_BODY")
    need(check_headers(root, identity["revision"], report["build_infos"]) == report["headers"], "D8_HEADER_RESEALED")
    compiler, cmake = report["compiler"]["resolved_path"], report["cmake"]["resolved_path"]
    check_command(OUTPUT / "baseline-build-logs/archive.command.json", [
        "git", "-C", str(ROOT), "-c", "tar.umask=0022", "archive", "--format=tar",
        "--output=" + str(TOOL / "exact-source.tar"), identity["revision"], "--", *sorted(identity["files"])])
    for label, command in (("compiler-version", [compiler, "--version"]),
                          ("compiler-full-version", [compiler, "-dumpfullversion"]),
                          ("compiler-target", [compiler, "-dumpmachine"]),
                          ("cmake-version", [cmake, "--version"]),
                          ("compiler-header-search", [compiler, "-E", "-x", "c", "/dev/null", "-v"])):
        check_command(OUTPUT / ("baseline-build-logs/" + label + ".command.json"), command)
    need(system_roots() == report["system_search_roots"], "D8_COMPILER_SEARCH")
    for arm in ("baseline", "candidate"):
        check_managed_command_labels(arm + "-build", check_phase(OUTPUT, arm + "-build"))
        info = report["build_infos"][arm + "-plain"]
        need(info["compiler_id"] == "GNU" and info["compiler_version"] ==
             (OUTPUT / "baseline-build-logs/compiler-full-version.stdout").read_text().strip() and
             info["target_triple"] == (OUTPUT / "baseline-build-logs/compiler-target.stdout").read_text().strip(),
             "D8_COMPILER_IDENTITY")
        for mode in ("plain", "observed"):
            form = arm + "-" + mode
            source, binary = TOOL / (form + "-source"), TOOL / (form + "-build")
            saved = report["forms"][form]
            revision = identity["revision"] + contract()["build"]["source_revision_suffixes"][form]
            need(saved["source_revision"] == revision and flags(root / (form + "-build")) == saved["flags"],
                 "D8_BUILD_FLAGS")
            prefix = OUTPUT / (arm + "-build-logs")
            check_command(prefix / (form + "-configure.command.json"),
                          configure_argv(cmake, compiler, source, binary, revision))
            targets = ["ap_process_pcm", "ap_build_info_dump"] if mode == "plain" else ["audio_pipeline"]
            check_command(prefix / (form + "-compile.command.json"),
                          [cmake, "--build", str(binary), "--target", *targets, "--parallel", "2", "--verbose"])
            need(check_compile_closure(root, identity, form) == saved["dependencies"], "D8_COMPILED_SOURCE_CLOSURE")
            program = report["programs"][form]
            executable = "ap_process_pcm_observer" if mode == "observed" else "ap_process_pcm"
            need(program["path"] == "build/" + form + "-build/" + executable and
                 desc(OUTPUT / program["path"]) == {k: program[k] for k in ("bytes", "sha256")} and
                 program["source_revision"] == revision, "D8_PROGRAM_IDENTITY")
            if mode == "observed":
                check_command(prefix / (form + "-observer.command.json"),
                              observer_argv(compiler, source, binary, saved["flags"]))
                check_command(prefix / (form + "-engineering.command.json"),
                              [str(binary / "ap_process_pcm_observer"), "--d8-self-test", arm])
                need(read(prefix / (form + "-engineering.stdout")) == saved["engineering"], "D8_ENGINEERING")
            else:
                check_command(prefix / (form + "-build-info.command.json"), [str(binary / "ap_build_info_dump")])
    budget().check()
    VERIFIED_CONTEXT = {"source": json.loads(json.dumps(identity)), "report": report}
    return report

def managed_files(built, include_late=True):
    """Exact retained build + phase/log files; caller separately checks run matrix."""
    names = {"build/" + name for name in built["artifact_inventory"]["files"]}
    names.add("build/build.json")
    for name in PHASES:
        if not include_late and name in ("verify", "negative"):
            continue
        path = OUTPUT / (name + "-phase.json")
        if not path.exists():
            continue
        value = read(path)
        check_managed_command_labels(name, value)
        need(value["phase"] == name and len(value["commands"]) == len(set(value["commands"])),
             "D8_PHASE_COMMAND_SET")
        names.add(path.relative_to(OUTPUT).as_posix())
        for relative in value["commands"]:
            need(re.fullmatch(re.escape(name) + r"-logs/[A-Za-z0-9_.-]+\.command\.json", relative) is not None,
                 "D8_PHASE_COMMAND_SET")
            check_command(OUTPUT / relative)
            prefix = relative.removesuffix(".command.json")
            names.update((relative, prefix + ".stdout", prefix + ".stderr"))
    return names

FATAL_FIXTURES_DONE = False

def supervisor_fixtures(phase):
    global FATAL_FIXTURES_DONE
    need(ACTIVE_PHASE is phase and phase.name == "negative" and not FATAL_FIXTURES_DONE, "D8_FIXTURE_STATE")
    names = tuple(contract()["budgets"]["supervision"]["fatal_fixtures"]["names"])
    need(names == supervision.FIXTURE_NAMES, "D8_FIXTURE_NAME")
    root = OUTPUT / "negatives/supervisor-fatal"
    need(not root.exists(), "D8_FIXTURE_NEW_PREFIX")
    claims = {}
    for name in names:
        for leaf, cap in (("pending.json", 4096), ("stdout.bin", 65536),
                          ("stderr.bin", 65536), ("receipt.json", 8192)):
            claims[root / name / leaf] = cap
    for leaf in ("except-marker", "finally-marker"):
        claims[root / "exception_finally_timeout" / leaf] = 4096
    need(sum(claims.values()) == 581632, "D8_FIXTURE_RESERVATION")
    # Reserve the complete frozen1MiB jointly, without creating a dummy file.
    claims[root / "reservation-not-a-file"] = 1048576 - sum(claims.values())
    receipts, files = {}, {}
    with budget().reserve(claims):
        for name in names:
            phase.remaining()
            current = root / name
            pending = (json.dumps({"fixture": name, "status": "PENDING",
                "budget_seconds": 2, "joint_reserved_bytes": 1048576,
                "production_timeout_exercised": False}, separators=(",", ":"), allow_nan=False)+"\n").encode()
            need(len(pending) <= 4096, "D8_FIXTURE_FILE_BOUND")
            bounded_write(current / "pending.json", pending)
            answer = CLIENT.ask("FIXTURE", name=name)
            returned = answer["fixture"]
            path = current / "receipt.json"
            need(returned["name"] == name and returned["path"] == str(path) and
                 desc(path) == {k: returned[k] for k in ("bytes", "sha256")}, "D8_FIXTURE_RECEIPT")
            value = read(path)
            need(value["fixture"] == name and value["status"] == "PASS" and
                 value["actual_exit_signal"] == signal.SIGKILL and value["body_ready"] is True and
                 value["all_pids_absent"] is True and value["markers_absent"] is True and
                 value["production_timeout_exercised"] is False and value["no_DSP_models_network"] is True and
                 0 <= value["elapsed_seconds"] <= 2 and value["budget_seconds"] == 2,
                 "D8_FIXTURE_RECEIPT")
            for label in ("stdout", "stderr"):
                need(desc(current / (label + ".bin")) == value["streams"][label], "D8_FIXTURE_RECEIPT")
            need({p.name for p in current.iterdir()} == {"pending.json", "stdout.bin", "stderr.bin", "receipt.json"},
                 "D8_FIXTURE_CLOSURE")
            receipts[name] = value
            for leaf in ("pending.json", "stdout.bin", "stderr.bin", "receipt.json"):
                path = current / leaf
                files[path.relative_to(OUTPUT).as_posix()] = desc(path)
                need(files[path.relative_to(OUTPUT).as_posix()]["bytes"] <= claims[path], "D8_FIXTURE_FILE_BOUND")
        budget().check()
    FATAL_FIXTURES_DONE = True
    return {"status": "PASS", "scope": "four fixed supervisor-owned fatal fixtures; not actual production deadline expiry",
            "receipts": receipts, "fixture_files": files}

def run_fatal_fixtures():
    return supervisor_fixtures(ACTIVE_PHASE)

def _material(raw, origin, scope, name, guard, mutation):
    return {"raw": raw, "origin": str(origin), "scope": scope,
            "guard_name": "dualmic_broadside_output_d8_build." + name,
            "guard": guard, "mutation": mutation}

def negative_material(category_name, phase):
    phase.remaining()
    need(VERIFIED_CONTEXT is not None, "D8_NEGATIVE_NOT_QUALIFIED")
    identity, report = VERIFIED_CONTEXT["source"], VERIFIED_CONTEXT["report"]
    root = OUTPUT / "build"
    encoded = lambda value: (json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)+"\n").encode()
    members = {
        "source_resealed": ("baseline-plain", "src/frontend/ap_hpf.c"),
        "transform_body_change": ("baseline-observed", "src/frontend/ap_hpf.c"),
        "observer_entry_change": ("baseline-observed", PREFIX + "dualmic_stages_d1.c"),
        "second_mathematical_change": ("candidate-observed", "src/frontend/ap_beamformer.c"),
        "fallback_weight_or_gain_change": ("candidate-observed", "src/frontend/ap_beamformer.c"),
        "history_or_state_change": ("candidate-observed", "src/frontend/ap_beamformer.c")}
    if category_name in members:
        form, name = members[category_name]
        path = root / (form + "-source") / name
        return _material(path.read_bytes(), path, "actual_source", "check_source_member",
            lambda fixture: check_source_member(form, name, fixture.read_bytes(), identity), {})
    if category_name == "source_tree":
        return _material(encoded(report["source"]), str(root / "build.json") + "#source",
            "actual_report", "check_source_identity", lambda p: check_source_identity(read(p), identity),
            {"path": ["tree"]})
    if category_name in ("source_extra_file", "source_extra_dir"):
        source = root / "baseline-plain-source"
        actual = inventory(source)
        return _material(encoded(actual), source, "actual_inventory", "check_closure_record",
            lambda p: check_closure_record(read(p), identity["files"], "D8_SOURCE_CLOSURE"),
            {"path": ["files" if category_name == "source_extra_file" else "directories"]})
    if category_name == "header_resealed":
        form = "baseline-observed"
        path = root / (form + "-build/generated/audio_pipeline/audio_pipeline_build.h")
        revision = identity["revision"] + contract()["build"]["source_revision_suffixes"][form]
        info = report["build_infos"]["baseline-plain"]
        return _material(path.read_bytes(), path, "actual_source", "check_header_member",
            lambda p: check_header_member(p.read_bytes(), root, revision, info), {})
    if category_name == "compiler_identity":
        values = {k: report[k] for k in ("compiler", "cmake")}
        return _material(encoded(values), str(root / "build.json") + "#compiler,cmake",
            "actual_report", "check_compiler_identity",
            lambda p: check_compiler_identity(read(p)["compiler"], read(p)["cmake"]),
            {"path": ["compiler", "file", "sha256"]})
    if category_name == "argv":
        path = OUTPUT / "baseline-build-logs/baseline-plain-configure.command.json"
        expected = configure_argv(report["cmake"]["resolved_path"], report["compiler"]["resolved_path"],
                                 TOOL / "baseline-plain-source", TOOL / "baseline-plain-build", identity["revision"])
        check_command(path, expected)
        return _material(path.read_bytes(), path, "actual_report", "check_command_record",
            lambda p: check_command_record(read(p), expected), {"path": ["argv"]})
    budget_keys = {"metric_category_overflow": "candidate_metrics_including_newlines",
                   "source_build_category_overflow": "all_source_archive_derived_build_provenance",
                   "report_finalization_overflow": "all_reports_receipts_logs_negatives_seals_completion",
                   "scratch_overflow": "all_current_case_transient_and_failure_prefix"}
    if category_name in budget_keys:
        totals = budget().check()["categories"]
        return _material(encoded(totals), "current retained result logical-byte inventory",
            "actual_budget_snapshot", "check_category_totals",
            lambda p: check_category_totals(read(p)), {"path": [budget_keys[category_name]]})
    raise ValueError("D8_UNSUPPORTED_BUILD_NEGATIVE:" + category_name)

def engineering_material(kind, phase):
    phase.remaining()
    need(VERIFIED_CONTEXT is not None, "D8_NEGATIVE_NOT_QUALIFIED")
    if kind == "flags":
        path = OUTPUT / "build/baseline-plain-build/CMakeFiles/audio_pipeline.dir/flags.make"
        return _material(path.read_bytes(), path, "actual_source", "parse_flags",
            lambda p: parse_flags(p.read_text(), TOOL / "baseline-plain-build"), {})
    if kind == "unity":
        path = OUTPUT / "build/baseline-plain-build" / UNITY_NAME
        source = OUTPUT / "build/baseline-plain-source"
        return _material(path.read_bytes(), path, "actual_source", "parse_generated_unity",
            lambda p: parse_generated_unity(p.read_bytes(), source, VERIFIED_CONTEXT["source"]), {})
    raise ValueError("D8_UNSUPPORTED_ENGINEERING_MATERIAL")

def source_command_labels():
    return ["head", "tree", "freeze-tree", "base-tree", "clean", "selected-tree", "base-selected-tree",
            *["production-root-" + str(i) for i in range(len(contract()["unchanged_production_objects"]))],
            "historical-workflow"]

def check_managed_command_labels(name, value):
    suffixes = ("plain-configure", "plain-compile", "plain-build-info",
                "observed-configure", "observed-compile", "observed-observer", "observed-engineering")
    if name == "baseline-build":
        labels = source_command_labels() + ["compiler-version", "compiler-full-version", "compiler-target",
            "cmake-version", "compiler-header-search", "archive"] + ["baseline-" + s for s in suffixes]
    elif name == "candidate-build":
        labels = ["candidate-" + s for s in suffixes]
    elif name == "verify":
        labels = source_command_labels()
    elif name == "negative":
        labels = source_command_labels()
    elif name == "analysis":
        labels = source_command_labels()
    elif name == "admission":
        labels = []
    elif name == "run":
        labels = ["%03d-%s" % (index, form) for index in range(60) for form in FORMS]
    else:
        raise ValueError("D8_PHASE_COMMAND_SET")
    expected = [name + "-logs/" + label + ".command.json" for label in labels]
    if value["status"] != "PASS":
        expected = expected[:len(value["commands"])]
    need(value["commands"] == expected, "D8_PHASE_COMMAND_SET")
    return True
