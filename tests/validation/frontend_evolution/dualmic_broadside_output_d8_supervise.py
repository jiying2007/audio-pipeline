#!/usr/bin/env python3
"""D8 revision-3 external fail-stop supervisor; no DSP or repository imports.

Limits control known tools, not arbitrary-code confinement. Temporary aggregate
bytes are checked by the worker after commands, never advertised as a write quota.
"""
import time
ROOT_STARTED = time.monotonic()  # before repository imports or experimental I/O
import sys
sys.dont_write_bytecode = True
import argparse
import collections
import errno
import json
import math
import os
from pathlib import Path
import resource
import select
import signal

PHASES = ("admission", "baseline-build", "candidate-build", "run", "analysis", "verify", "negative")
WORKER_LIMITS = {"AS": 1073741824, "NOFILE": 128, "NPROC": 128, "FSIZE": 536870912, "CORE": 0}
TOOL_LIMITS = {"AS": 536870912, "NOFILE": 128, "NPROC": 128, "FSIZE": 16777216, "CORE": 0}
SUPERVISOR_LIMITS = {"AS": 134217728, "NOFILE": 128, "CORE": 0}
IPC_LIMIT = 4096
STDOUT_LIMIT = 4194304

def need(value, reason):
    if not value:
        raise ValueError(reason)

LIVE_MARKER_LIMIT = 16384
LIVE_MARKER_LINE_LIMIT = 512
LIVE_MARKER_EVENTS = frozenset(("PHASE_BEGIN", "PHASE_END", "FINISH",
    "PHASE_DEADLINE_APPROACHING", "ROOT_DEADLINE_APPROACHING"))

def _live_number(value):
    if type(value) not in (int, float):
        return False
    try:
        return math.isfinite(value)
    except OverflowError:
        return False

def check_live_marker_budget(marker_bytes, total_output):
    need(type(marker_bytes) is int and type(total_output) is int and
         0 <= marker_bytes <= LIVE_MARKER_LIMIT, "D8_LIVE_MARKER_BOUND")
    need(marker_bytes <= total_output <= STDOUT_LIMIT, "D8_STDOUT_BOUND")
    return True

def live_marker(event, *, phase, command, started, now, root_deadline,
                phase_deadline=None, command_deadline=None, transport_deadline=None,
                fixture_deadline=None):
    """Best-effort accepted-transition/warning record, never a completion claim."""
    need(type(event) is str and event in LIVE_MARKER_EVENTS and phase in (*PHASES, None) and
         (command is None or (type(command) is str and 0 < len(command) <= 128 and
          all(c in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_.-" for c in command))),
         "D8_LIVE_MARKER")
    need((event not in ("PHASE_BEGIN", "PHASE_END", "PHASE_DEADLINE_APPROACHING") or phase in PHASES) and
         (event != "FINISH" or phase == "negative"), "D8_LIVE_MARKER")
    deadlines = {"root": root_deadline, "phase": phase_deadline, "command": command_deadline,
                 "transport": transport_deadline, "fixture": fixture_deadline}
    need(_live_number(started) and _live_number(now) and 0 <= started <= now and
         _live_number(root_deadline) and root_deadline > started and
         all(value is None or (_live_number(value) and value <= root_deadline)
             for value in deadlines.values()), "D8_LIVE_MARKER")
    need(now < min(value for value in deadlines.values() if value is not None), "D8_SUPERVISOR_TIMEOUT")
    record = {"d8_live": {"event": event, "phase": phase, "command": command,
        "elapsed_seconds": round(now - started, 6),
        "remaining_seconds": {name: None if value is None else round(value - now, 6)
                              for name, value in deadlines.items()}}}
    raw = (json.dumps(record, sort_keys=True, separators=(",", ":"), allow_nan=False)+"\n").encode("ascii")
    need(len(raw) <= LIVE_MARKER_LINE_LIMIT, "D8_LIVE_MARKER")
    return raw

def lower_limits(requested):
    """Lower independently after fork. Existing stricter soft/hard limits win."""
    result = {}
    for name, requested_value in requested.items():
        key = getattr(resource, "RLIMIT_" + name)
        soft, hard = resource.getrlimit(key)
        finite = [v for v in (soft, hard, requested_value) if v != resource.RLIM_INFINITY]
        effective = min(finite)
        resource.setrlimit(key, (effective, effective))
        need(resource.getrlimit(key) == (effective, effective), "D8_RLIMIT_INSTALL")
        result[name] = {"inherited_soft": soft, "inherited_hard": hard,
                        "requested": requested_value, "soft": effective, "hard": effective}
    return result

def unprivileged():
    need(sys.platform == "linux" and os.getuid() != 0 and
         os.getuid() == os.geteuid() and os.getgid() == os.getegid(), "D8_UNPRIVILEGED_REQUIRED")
    fields = dict(line.split(":", 1) for line in Path("/proc/self/status").read_text().splitlines()
                  if ":" in line)
    need(all(int(fields[name].strip(), 16) == 0 for name in ("CapInh", "CapPrm", "CapEff", "CapAmb")),
         "D8_CAPABILITY_ELEVATION")

class Protocol:
    """Pure state machine. Tests use a supplied monotonic clock, never test groups."""
    def __init__(self, started, worker):
        self.started, self.worker = started, worker
        self.root_deadline = started + 1200.0
        self.phase = None
        self.phase_deadline = None
        self.command = None
        self.command_deadline = None
        self.next_phase = 0
        self.sequence = 0
        self.hello = False
        self.finished = False
        self.first_failure = None
        self.fixture = None
        self.fixture_started = None
        self.fixture_deadline = None
        self.fixture_index = 0

    def deadline(self):
        return min(x for x in (self.root_deadline, self.phase_deadline, self.command_deadline, self.fixture_deadline)
                   if x is not None)

    def fail(self, reason):
        if self.first_failure is None:
            self.first_failure = reason
        raise ValueError(self.first_failure)

    def live(self, now):
        if now >= self.deadline():
            self.fail("D8_SUPERVISOR_TIMEOUT")

    def request(self, value, now, *, alone):
        if self.first_failure is not None:
            raise ValueError(self.first_failure)
        try:
            return self._request(value, now, alone=alone)
        except ValueError as error:
            if self.first_failure is None:
                self.first_failure = str(error)
            raise

    def _request(self, value, now, *, alone):
        self.live(now)
        need(type(value) is dict and type(value.get("seq")) is int and type(value.get("pid")) is int and
             value.get("seq") == self.sequence + 1 and
             value.get("pid") == self.worker, "D8_IPC_SEQUENCE")
        kind = value.get("type")
        if kind == "HELLO":
            need(not self.hello and self.sequence == 0 and alone, "D8_IPC_STATE")
            self.hello = True
        else:
            need(self.hello and not self.finished, "D8_IPC_STATE")
            need(self.fixture is None, "D8_FIXTURE_STATE")
            if kind == "PHASE_BEGIN":
                need(self.phase is None and self.command is None and alone and
                     self.next_phase < len(PHASES) and value.get("name") == PHASES[self.next_phase],
                     "D8_PHASE_ORDER")
                self.phase = value["name"]
                self.phase_deadline = min(now + 300.0, self.root_deadline)
            elif kind == "COMMAND_BEGIN":
                need(self.phase is not None and self.command is None and alone and
                     type(value.get("label")) is str and 0 < len(value["label"]) <= 128,
                     "D8_COMMAND_STATE")
                self.command = value["label"]
                self.command_deadline = min(now + 30.0, self.phase_deadline, self.root_deadline)
            elif kind == "COMMAND_QUIESCENT":
                need(self.command is not None and self.command == value.get("label") and alone, "D8_COMMAND_QUIESCENT")
                # Keep every existing deadline armed through inventory and receipts.
            elif kind == "COMMAND_END":
                need(self.command is not None and self.command == value.get("label") and alone and value.get("terminal") is True,
                     "D8_COMMAND_END")
                self.command = None
                self.command_deadline = None
            elif kind == "PHASE_END":
                need(self.phase is not None and self.phase == value.get("name") and self.phase != "negative" and
                     self.command is None and alone, "D8_PHASE_END")
                self.next_phase += 1
                self.phase, self.phase_deadline = None, None
            elif kind == "FIXTURE":
                need(self.phase == "negative" and self.command is None and alone and
                     self.fixture_index < len(FIXTURE_NAMES) and value.get("name") == FIXTURE_NAMES[self.fixture_index],
                     "D8_FIXTURE_STATE")
                self.fixture = value["name"]
                self.fixture_started = now
                self.fixture_deadline = min(now + 2.0, self.phase_deadline, self.root_deadline)
            elif kind == "FINISH":
                need(self.phase == "negative" and self.next_phase == 6 and
                     self.command is None and alone and self.fixture_index == len(FIXTURE_NAMES) and
                     value.get("completion_checked") is True and
                     value.get("stdout_flushed") is True, "D8_FINISH")
                # Do not disarm the final phase. Pipes, final writes and worker
                # exit must still finish before its existing absolute deadline.
                self.finished = True
            elif kind == "ABORT":
                self.fail("D8_WORKER_ABORT")
            else:
                self.fail("D8_IPC_UNKNOWN")
        self.sequence = value["seq"]
        return {"seq": self.sequence, "ok": True, "root_started": self.started,
                "root_deadline": self.root_deadline, "phase_deadline": self.phase_deadline,
                "command_deadline": self.command_deadline, "fixture_deadline": self.fixture_deadline}

    def fixture_complete(self, name, now):
        if self.first_failure is not None:
            raise ValueError(self.first_failure)
        try:
            self.live(now)
            need(self.fixture is not None and type(name) is str and
                 self.fixture_index < len(FIXTURE_NAMES) and name == FIXTURE_NAMES[self.fixture_index] and
                 self.fixture == name and self.phase == "negative" and self.command is None,
                 "D8_FIXTURE_STATE")
            self.fixture_index += 1
            self.fixture = self.fixture_started = self.fixture_deadline = None
            return {"seq": self.sequence, "ok": True, "root_started": self.started,
                    "root_deadline": self.root_deadline, "phase_deadline": self.phase_deadline,
                    "command_deadline": self.command_deadline, "fixture_deadline": None}
        except ValueError as error:
            if self.first_failure is None:
                self.first_failure = str(error)
            raise


def process_table():
    records = {}
    for directory in Path("/proc").iterdir():
        if not directory.name.isdigit():
            continue
        try:
            raw = (directory / "stat").read_text()
        except (FileNotFoundError, ProcessLookupError):
            continue
        end = raw.rfind(")")
        need(end >= 0, "D8_PROC_STAT")
        fields = raw[end + 2:].split()
        records[int(directory.name)] = {"state": fields[0], "ppid": int(fields[1]),
            "group": int(fields[2]), "session": int(fields[3]), "start": int(fields[19])}
    return records

def descendants(worker, seen):
    table = process_table()
    current = set()
    pending = {worker}
    while pending:
        parent = pending.pop()
        children = {pid for pid, record in table.items() if record["ppid"] == parent}
        children -= current
        current |= children
        pending |= children
    for pid, start in list(seen.items()):
        if pid in table and table[pid]["start"] == start:
            current.add(pid)
        else:
            del seen[pid]
    # Include orphaned members of the worker group even when a parent vanished
    # between snapshots. This is observation, not a syscall confinement claim.
    current |= {pid for pid, record in table.items() if record["group"] == worker and pid != worker}
    for pid in current:
        record = table[pid]
        seen[pid] = record["start"]
        need(record["group"] == worker and record["session"] == worker, "D8_ESCAPED_DESCENDANT")
    if worker in table:
        need(table[worker]["group"] == worker and table[worker]["session"] == worker, "D8_WORKER_GROUP")
    return current

def kill_worker(worker):
    # The PID can exist before setsid succeeds. Never accidentally target the
    # supervisor's group; kill the intended fresh group AND actual worker PID.
    for operation in (lambda: os.killpg(worker, signal.SIGKILL),
                      lambda: os.kill(worker, signal.SIGKILL)):
        try:
            operation()
        except ProcessLookupError:
            pass

def bootstrap_write(fd, value):
    raw = (json.dumps(value, separators=(",", ":"), allow_nan=False) + "\n").encode()
    need(len(raw) <= IPC_LIMIT, "D8_IPC_BYTES")
    need(os.write(fd, raw) == len(raw), "D8_IPC_WRITE")

def bootstrap_read(fd):
    raw = bytearray()
    while b"\n" not in raw:
        data = os.read(fd, 1)
        need(data, "D8_IPC_EOF")
        raw += data
        need(len(raw) <= IPC_LIMIT, "D8_IPC_BYTES")
    return json.loads(raw)

def supervise(expected_head):
    unprivileged()
    need(len(expected_head) == 40 and all(c in "0123456789abcdef" for c in expected_head),
         "D8_EXECUTION_HEAD")
    request_read, request_write = os.pipe()
    response_read, response_write = os.pipe()
    out_read, out_write = os.pipe()
    err_read, err_write = os.pipe()
    worker = os.fork()  # parent limits MUST NOT be lowered before this fork
    if worker == 0:
        try:
            for fd in (request_read, response_write, out_read, err_read):
                os.close(fd)
            os.setsid()
            need(os.getpid() == os.getpgrp() == os.getsid(0), "D8_WORKER_GROUP")
            actual = lower_limits(WORKER_LIMITS)
            os.dup2(out_write, 1)
            os.dup2(err_write, 2)
            for fd in (out_write, err_write):
                if fd not in (1, 2):
                    os.close(fd)
            bootstrap_write(request_write, {"type": "READY", "pid": os.getpid(),
                "pgid": os.getpgrp(), "limits": actual})
            need(bootstrap_read(response_read) == {"ready": True}, "D8_BOOTSTRAP_ACK")
            for fd in (request_write, response_read):
                os.set_inheritable(fd, True)
            env = dict(os.environ)
            env.update(PYTHONDONTWRITEBYTECODE="1", AP_D8_CONTROL_READ=str(response_read),
                AP_D8_CONTROL_WRITE=str(request_write), AP_D8_SUPERVISOR_PID=str(os.getppid()),
                AP_D8_WORKER_LIMITS=json.dumps(actual, separators=(",", ":")))
            driver = str(Path(__file__).with_name("dualmic_broadside_output_d8.py"))
            os.execve(sys.executable, [sys.executable, "-B", "-u", driver, "--expected-head", expected_head], env)
        except BaseException:
            os._exit(125)
    for fd in (request_write, response_read, out_write, err_write):
        os.close(fd)
    worker_reaped = False
    registry = {}
    def interrupted(signum, frame):
        if not worker_reaped:
            kill_registered(worker, registry)
        os._exit(128 + signum)
    for signum in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
        signal.signal(signum, interrupted)
    try:
        parent_limits = lower_limits(SUPERVISOR_LIMITS)
        for fd in (request_read, response_write, out_read, err_read, 1, 2):
            os.set_blocking(fd, False)
        poller = select.poll()
        for fd in (request_read, out_read, err_read):
            poller.register(fd, select.POLLIN | select.POLLHUP)
        protocol = Protocol(ROOT_STARTED, worker)
        pending = bytearray()
        responses = bytearray()
        forwarding = {1: bytearray(), 2: bytearray()}
        pipes = {out_read: 1, err_read: 2}
        total_output = 0
        marker_bytes = 0
        phase_warned = set()
        root_warned = False
        ready = False
        status = None
        seen = {}
        deferred = None
        transport_deadline = None
        def supervisor_live(now):
            protocol.live(now)
            if transport_deadline is not None and now >= transport_deadline:
                protocol.fail("D8_SUPERVISOR_TIMEOUT")
        def queue_marker(event, *, phase=None, phase_deadline=None):
            nonlocal total_output, marker_bytes
            now = time.monotonic()
            supervisor_live(now)
            raw = live_marker(event, phase=protocol.phase if phase is None else phase,
                command=protocol.command, started=protocol.started, now=now,
                root_deadline=protocol.root_deadline,
                phase_deadline=protocol.phase_deadline if phase_deadline is None else phase_deadline,
                command_deadline=protocol.command_deadline, transport_deadline=transport_deadline,
                fixture_deadline=protocol.fixture_deadline)
            check_live_marker_budget(marker_bytes + len(raw), total_output + len(raw))
            supervisor_live(time.monotonic())
            forwarding[2] += raw
            marker_bytes += len(raw)
            total_output += len(raw)

        def transition_marker(kind, previous_phase, previous_deadline):
            if kind == "PHASE_END":
                queue_marker(kind, phase=previous_phase, phase_deadline=previous_deadline)
            elif kind in ("PHASE_BEGIN", "FINISH"):
                queue_marker(kind)

        while True:
            now = time.monotonic()
            supervisor_live(now)
            # Warnings are best effort, at most once per phase and once per job.
            # No warning is emitted from the fatal path or after any live lease.
            if protocol.phase is not None and protocol.phase not in phase_warned and \
                    protocol.phase_deadline - now <= 5.0:
                queue_marker("PHASE_DEADLINE_APPROACHING")
                phase_warned.add(protocol.phase)
            if not root_warned and protocol.root_deadline - now <= 5.0:
                queue_marker("ROOT_DEADLINE_APPROACHING")
                root_warned = True
            if ready:
                current = descendants(worker, seen)
                need(protocol.command is not None or not current, "D8_UNEXPECTED_DESCENDANT")
            else:
                current = set()
            if status is None:
                observed = os.waitid(os.P_PID, worker, os.WEXITED | os.WNOHANG | os.WNOWAIT)
                if observed is not None:
                    status = (observed.si_status << 8) if observed.si_code == os.CLD_EXITED else observed.si_status
                    if observed.si_code == os.CLD_DUMPED:
                        status |= 0x80
            if status is not None:
                need(ready and protocol.finished and os.WIFEXITED(status) and os.WEXITSTATUS(status) == 0,
                     "D8_WORKER_FAILED")
                need(not current, "D8_LEFTOVER_DESCENDANT")
                if not pipes and not any(forwarding.values()) and not responses:
                    protocol.live(time.monotonic())
                    waited, terminal = os.waitpid(worker, os.WNOHANG)
                    need(waited == worker and terminal == status, "D8_WORKER_REAP")
                    worker_reaped = True
                    protocol.live(time.monotonic())
                    os._exit(0)  # no implicit interpreter flush outside the deadline
            if deferred is not None and not current:
                transport_deadline = protocol.deadline()
                previous_phase, previous_deadline = protocol.phase, protocol.phase_deadline
                response = protocol.request(deferred, time.monotonic(), alone=True)
                transition_marker(deferred["type"], previous_phase, previous_deadline)
                deferred = None
                responses += (json.dumps(response, separators=(",", ":")) + "\n").encode()
            if responses:
                poller.register(response_write, select.POLLOUT)
            for fd, data in forwarding.items():
                if data:
                    poller.register(fd, select.POLLOUT)
            earliest = min(protocol.deadline(), transport_deadline if transport_deadline is not None else protocol.deadline())
            timeout = min(0.05, max(0.0, earliest - time.monotonic()))
            for fd, event in poller.poll(max(0, int(timeout * 1000))):
                supervisor_live(time.monotonic())
                if fd == response_write:
                    try:
                        sent = os.write(fd, responses)
                    except BlockingIOError:
                        continue
                    del responses[:sent]
                    if not responses:
                        supervisor_live(time.monotonic())
                        transport_deadline = None
                        poller.unregister(fd)
                elif fd in forwarding:
                    try:
                        sent = os.write(fd, forwarding[fd][:65536])
                    except BlockingIOError:
                        continue
                    del forwarding[fd][:sent]
                    if not forwarding[fd]:
                        poller.unregister(fd)
                elif fd in pipes:
                    try:
                        data = os.read(fd, 65536)
                    except BlockingIOError:
                        continue
                    if not data:
                        poller.unregister(fd)
                        os.close(fd)
                        del pipes[fd]
                    else:
                        total_output += len(data)
                        need(total_output <= STDOUT_LIMIT, "D8_STDOUT_BOUND")
                        forwarding[pipes[fd]] += data
                elif fd == request_read:
                    try:
                        data = os.read(fd, IPC_LIMIT + 1)
                    except BlockingIOError:
                        continue
                    if not data:
                        poller.unregister(fd)
                        os.close(fd)
                        continue
                    pending += data
                    need(len(pending) <= IPC_LIMIT, "D8_IPC_BYTES")
                    if b"\n" not in pending:
                        continue
                    raw, extra = pending.split(b"\n", 1)
                    need(not extra and deferred is None and not responses, "D8_IPC_SERIAL")
                    pending.clear()
                    value = json.loads(raw)
                    if not ready:
                        need(value.get("type") == "READY" and value.get("pid") == worker and
                             value.get("pgid") == worker and os.getpgid(worker) == worker,
                             "D8_WORKER_GROUP")
                        ready = True
                        protocol.worker_limits = value["limits"]
                        responses += b'{"ready":true}\n'
                    else:
                        current = descendants(worker, seen)
                        if value.get("type") in ("COMMAND_QUIESCENT", "COMMAND_END", "PHASE_END", "FINISH") and current:
                            deferred = value  # leave old deadline armed while descendants exit
                        else:
                            transport_deadline = protocol.deadline()
                            previous_phase, previous_deadline = protocol.phase, protocol.phase_deadline
                            response = protocol.request(value, time.monotonic(), alone=not current)
                            transition_marker(value["type"], previous_phase, previous_deadline)
                            if value.get("type") == "FIXTURE":
                                fixture_result = run_fixture(value["name"], worker, protocol, registry, seen)
                                transport_deadline = protocol.deadline()
                                response = protocol.fixture_complete(value["name"], time.monotonic())
                                response["fixture"] = fixture_result
                            response["supervisor_limits"] = parent_limits
                            response["worker_limits"] = protocol.worker_limits
                            responses += (json.dumps(response, separators=(",", ":")) + "\n").encode()
            need(len(responses) <= IPC_LIMIT, "D8_IPC_BYTES")
            need(sum(map(len, forwarding.values())) <= STDOUT_LIMIT, "D8_STDOUT_BOUND")
    except BaseException as error:
        # Earliest failure is not replaced by cleanup. Do not hash, write a
        # receipt, flush, or grant a post-deadline cleanup allowance.
        if not worker_reaped:
            kill_registered(worker, registry)
        os._exit(124 if isinstance(error, ValueError) and str(error) == "D8_SUPERVISOR_TIMEOUT" else 125)


FIXTURE_NAMES = ("startup_before_group", "child_tree_timeout", "exception_finally_timeout", "pipe_drain_timeout")
FIXTURE_LIMITS = {"AS": 67108864, "FSIZE": 4096, "NOFILE": 16, "NPROC": 128, "CORE": 0}
FIXTURE_ROOT = Path("/tmp/ap-dualmic-d8/result/negatives/supervisor-fatal")

def kill_registered(worker, registry):
    kill_worker(worker)
    for item in registry.values():
        if not item["reaped"]:
            kill_worker(item["pid"])

def fixture_event(fd, kind, **fields):
    bootstrap_write(fd, {"event": kind, "pid": os.getpid(), **fields})

def hang():
    while True:
        time.sleep(3600)

def fixture_body(name, events, gate, out_fd, err_fd):
    """Fixed no-DSP/no-network source. Only the marker fixture may open files."""
    for signum in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
        signal.signal(signum, signal.SIG_DFL)
    os.dup2(out_fd, 1)
    os.dup2(err_fd, 2)
    keep = {0, 1, 2, events, gate}
    for text_fd in os.listdir("/proc/self/fd"):
        fd = int(text_fd)
        if fd not in keep:
            try:
                os.close(fd)
            except OSError:
                pass
    actual = lower_limits(FIXTURE_LIMITS)
    if name != "startup_before_group":
        os.setsid()
    fixture_event(events, "GROUP", group=os.getpgrp(), session=os.getsid(0), limits=actual)
    need(os.read(gate, 1) == b"S", "D8_FIXTURE_BARRIER")
    if name == "exception_finally_timeout":
        try:
            fixture_event(events, "BODY", scope="inside_try")
            hang()
        except BaseException:
            with (FIXTURE_ROOT / name / "except-marker").open("xb", buffering=0) as file:
                file.write(b"except reached\n")
            raise
        finally:
            with (FIXTURE_ROOT / name / "finally-marker").open("xb", buffering=0) as file:
                file.write(b"finally reached\n")
    elif name == "pipe_drain_timeout":
        for fd, byte in ((1, b"O"), (2, b"E")):
            view = memoryview(byte * 65536)
            while view:
                count = os.write(fd, view)
                need(count > 0, "D8_FIXTURE_PIPE")
                view = view[count:]
        fixture_event(events, "BODY", scope="payload_emitted")
        hang()
    elif name == "child_tree_timeout":
        descendant_read, descendant_write = os.pipe()
        child = os.fork()
        if child == 0:
            os.close(descendant_write)
            os.close(gate)
            need(os.read(descendant_read, 1) == b"D", "D8_FIXTURE_BARRIER")
            os.close(descendant_read)
            fixture_event(events, "CHILD_BODY", group=os.getpgrp(), session=os.getsid(0))
            hang()
        os.close(descendant_read)
        fixture_event(events, "DESCENDANT", descendant=child)
        need(os.read(gate, 1) == b"D", "D8_FIXTURE_BARRIER")
        need(os.write(descendant_write, b"D") == 1, "D8_FIXTURE_BARRIER")
        os.close(descendant_write)
        fixture_event(events, "BODY", scope="leader_with_descendant")
        hang()
    else:
        need(name == "startup_before_group", "D8_FIXTURE_NAME")
        fixture_event(events, "BODY", scope="before_setsid")
        hang()

def run_fixture(name, worker, protocol, registry, worker_seen):
    """All work, including receipt bytes and reaping, stays in the existing lease."""
    import hashlib
    deadline = protocol.fixture_deadline
    need(protocol.fixture == name and name in FIXTURE_NAMES, "D8_FIXTURE_STATE")
    root = FIXTURE_ROOT / name
    protocol.live(time.monotonic())
    need(root.resolve(strict=True) == root and root.is_dir() and
         {p.name for p in root.iterdir()} == {"pending.json"}, "D8_FIXTURE_PATH")
    outputs = {}
    for label in ("stdout", "stderr"):
        protocol.live(time.monotonic())
        path = root / (label + ".bin")
        outputs[label] = {"path": path, "file": path.open("xb", buffering=0),
                          "bytes": 0, "hash": hashlib.sha256()}
    event_read, event_write = os.pipe()
    gate_read, gate_write = os.pipe()
    stdout_read, stdout_write = os.pipe()
    stderr_read, stderr_write = os.pipe()
    blocked = {signal.SIGINT, signal.SIGTERM, signal.SIGHUP}
    protocol.live(time.monotonic())
    old_mask = signal.pthread_sigmask(signal.SIG_BLOCK, blocked)
    pid = os.fork()
    if pid == 0:
        try:
            # Close inherited controller and experiment FDs before lowered16-FD
            # limit. No production IPC descriptor survives into a fixture body.
            for signum in blocked:
                signal.signal(signum, signal.SIG_DFL)
            signal.pthread_sigmask(signal.SIG_SETMASK, old_mask)
            fixture_body(name, event_write, gate_read, stdout_write, stderr_write)
        except BaseException:
            os._exit(125)
        os._exit(126)
    registry[name] = {"pid": pid, "intended_pgid": pid, "actual_pgid": None,
                      "actual_session": None, "descendant": None, "reaped": False}
    signal.pthread_sigmask(signal.SIG_SETMASK, old_mask)
    for fd in (event_write, gate_read, stdout_write, stderr_write):
        os.close(fd)
    for fd in (event_read, gate_write, stdout_read, stderr_read):
        os.set_blocking(fd, False)
    poller = select.poll()
    for fd in (event_read, stdout_read, stderr_read):
        poller.register(fd, select.POLLIN | select.POLLHUP)
    streams = {stdout_read: "stdout", stderr_read: "stderr"}
    event_buffer = bytearray()
    gate_bytes = bytearray()
    group_ready = False
    body_ready = False
    descendant_ready = False
    actual_limits = None
    leader_status = None
    trigger_delay = 0.5 if name == "pipe_drain_timeout" else 0.25
    # The absolute lease includes startup. Only established groups measure the
    # intentional trigger from successful start-barrier transmission (PLAN7.2).
    trigger = protocol.fixture_started + trigger_delay if name == "startup_before_group" else None
    barrier_released = None
    killed = False
    signal_time = None
    event_open = True
    events = []
    completed = False
    def live():
        protocol.live(time.monotonic())
        need(not descendants(worker, worker_seen), "D8_UNEXPECTED_DESCENDANT")
        need(os.waitid(os.P_PID, worker, os.WEXITED | os.WNOHANG | os.WNOWAIT) is None,
             "D8_WORKER_FAILED")
    try:
        while True:
            live()
            now = time.monotonic()
            if not killed and trigger is not None and now >= trigger:
                need(group_ready and body_ready and (name != "child_tree_timeout" or descendant_ready),
                     "D8_FIXTURE_NOT_READY")
                if name == "pipe_drain_timeout":
                    need(all(item["bytes"] == 65536 for item in outputs.values()), "D8_FIXTURE_PAYLOAD")
                kill_worker(pid)
                killed = True
                signal_time = now
            if leader_status is None:
                result = os.waitid(os.P_PID, pid, os.WEXITED | os.WNOHANG | os.WNOWAIT)
                if result is not None:
                    need(killed and result.si_code == os.CLD_KILLED and result.si_status == signal.SIGKILL,
                         "D8_FIXTURE_EXIT")
                    leader_status = result.si_status
            child = registry[name]["descendant"]
            child_gone = child is None or not Path("/proc/" + str(child)).exists()
            if killed and leader_status == signal.SIGKILL and child_gone and not streams and not event_open:
                live()
                waited, status = os.waitpid(pid, os.WNOHANG)
                need(waited == pid and os.WIFSIGNALED(status) and os.WTERMSIG(status) == signal.SIGKILL,
                     "D8_FIXTURE_REAP")
                registry[name]["reaped"] = True
                need(not Path("/proc/" + str(pid)).exists() and child_gone, "D8_FIXTURE_LEFTOVER")
                break
            if gate_bytes:
                poller.register(gate_write, select.POLLOUT)
            next_wake = min(deadline, trigger if not killed and trigger is not None else deadline)
            for fd, flags in poller.poll(max(0, int(min(0.01, max(0.0, next_wake-time.monotonic())) * 1000))):
                live()
                if fd == gate_write:
                    try:
                        count = os.write(fd, gate_bytes)
                    except BlockingIOError:
                        continue
                    need(count > 0, "D8_FIXTURE_BARRIER")
                    if b"S" in gate_bytes[:count]:
                        need(barrier_released is None and group_ready, "D8_FIXTURE_BARRIER")
                        barrier_released = time.monotonic()
                        if name != "startup_before_group":
                            trigger = barrier_released + trigger_delay
                    del gate_bytes[:count]
                    if not gate_bytes:
                        poller.unregister(fd)
                elif fd in streams:
                    try:
                        data = os.read(fd, 65536)
                    except BlockingIOError:
                        continue
                    if not data:
                        poller.unregister(fd)
                        os.close(fd)
                        del streams[fd]
                    else:
                        item = outputs[streams[fd]]
                        need(item["bytes"] + len(data) <= 65536, "D8_FIXTURE_FILE_BOUND")
                        expected_byte = b"O" if streams[fd] == "stdout" else b"E"
                        need(name == "pipe_drain_timeout" and data == expected_byte * len(data), "D8_FIXTURE_PAYLOAD")
                        live()
                        need(item["file"].write(data) == len(data), "D8_FIXTURE_SHORT_WRITE")
                        item["hash"].update(data)
                        item["bytes"] += len(data)
                elif fd == event_read:
                    try:
                        data = os.read(fd, 4096)
                    except BlockingIOError:
                        continue
                    if not data:
                        need(not event_buffer, "D8_FIXTURE_EVENT")
                        poller.unregister(fd)
                        os.close(fd)
                        event_open = False
                        continue
                    event_buffer += data
                    need(len(event_buffer) <= 8192, "D8_FIXTURE_EVENT")
                    while b"\n" in event_buffer:
                        raw, extra = event_buffer.split(b"\n", 1)
                        event_buffer[:] = extra
                        value = json.loads(raw)
                        event = value.get("event")
                        need(len(events) < 4 and type(value.get("pid")) is int, "D8_FIXTURE_EVENT")
                        events.append({"event": event, "pid": value["pid"],
                                       "elapsed_seconds": time.monotonic()-protocol.fixture_started})
                        if event == "GROUP":
                            need(not group_ready and value["pid"] == pid, "D8_FIXTURE_GROUP")
                            actual = process_table()[pid]
                            need(type(value.get("group")) is int and type(value.get("session")) is int and
                                 value["group"] == actual["group"] and value["session"] == actual["session"],
                                 "D8_FIXTURE_GROUP")
                            registry[name]["actual_pgid"] = actual["group"]
                            registry[name]["actual_session"] = actual["session"]
                            events[-1].update({"actual_pgid": actual["group"],
                                               "actual_session": actual["session"], "intended_pgid": pid})
                            if name == "startup_before_group":
                                need(actual["group"] != pid and actual["group"] == os.getpgrp(), "D8_FIXTURE_GROUP")
                            else:
                                need(actual["group"] == pid and actual["session"] == pid and
                                     value.get("group") == pid and value.get("session") == pid, "D8_FIXTURE_GROUP")
                            actual_limits = value["limits"]
                            need(set(actual_limits) == set(FIXTURE_LIMITS) and
                                 all(0 <= row["soft"] == row["hard"] <= FIXTURE_LIMITS[key]
                                     for key, row in actual_limits.items()), "D8_FIXTURE_LIMITS")
                            group_ready = True
                            gate_bytes += b"S"
                        elif event == "DESCENDANT":
                            child = value.get("descendant")
                            need(name == "child_tree_timeout" and group_ready and value["pid"] == pid and
                                 registry[name]["descendant"] is None and type(child) is int, "D8_FIXTURE_DESCENDANT")
                            actual = process_table()[child]
                            need(actual["ppid"] == pid and actual["group"] == pid and actual["session"] == pid,
                                 "D8_FIXTURE_DESCENDANT")
                            registry[name]["descendant"] = child
                            gate_bytes += b"D"  # register BEFORE releasing its body barrier
                        elif event == "CHILD_BODY":
                            need(name == "child_tree_timeout" and not descendant_ready and
                                 value["pid"] == registry[name]["descendant"] and
                                 value.get("group") == pid and value.get("session") == pid, "D8_FIXTURE_DESCENDANT")
                            descendant_ready = True
                        elif event == "BODY":
                            scopes = {"startup_before_group": "before_setsid",
                                      "child_tree_timeout": "leader_with_descendant",
                                      "exception_finally_timeout": "inside_try",
                                      "pipe_drain_timeout": "payload_emitted"}
                            need(group_ready and not body_ready and value["pid"] == pid and
                                 value.get("scope") == scopes[name], "D8_FIXTURE_BODY")
                            body_ready = True
                        else:
                            raise ValueError("D8_FIXTURE_EVENT")
        live()
        for item in outputs.values():
            item["file"].close()
        if name != "pipe_drain_timeout":
            need(all(item["bytes"] == 0 for item in outputs.values()), "D8_FIXTURE_PAYLOAD")
        markers_absent = not (root / "except-marker").exists() and not (root / "finally-marker").exists()
        need(markers_absent, "D8_FIXTURE_FINALLY_WRITE")
        receipt = {"status": "PASS", "fixture": name, "pid": pid,
            "pgid": registry[name]["actual_pgid"], "session": registry[name]["actual_session"],
            "intended_pgid": pid,
            "descendant_pid": registry[name]["descendant"], "all_pids_absent": True,
            "actual_exit_signal": int(signal.SIGKILL), "body_ready": True,
            "events": events, "limits": actual_limits, "markers_absent": markers_absent,
            "root_deadline": protocol.root_deadline, "phase_deadline": protocol.phase_deadline,
            "fixture_started": protocol.fixture_started, "fixture_deadline": deadline,
            "start_barrier_released": barrier_released,
            "intentional_timer_origin": "fixture_started" if name == "startup_before_group" else "start_barrier_released",
            "intentional_delay_seconds": trigger_delay,
            "intentional_deadline": trigger, "signal_elapsed_seconds": signal_time-protocol.fixture_started,
            "elapsed_seconds": time.monotonic()-protocol.fixture_started, "budget_seconds": 2,
            "elapsed_scope": "receipt preparation; existing deadline also covers receipt write and ACK",
            "production_timeout_exercised": False, "no_DSP_models_network": True,
            "streams": {label: {"bytes": item["bytes"], "sha256": item["hash"].hexdigest()}
                        for label, item in outputs.items()}}
        raw = (json.dumps(receipt, sort_keys=True, separators=(",", ":"), allow_nan=False)+"\n").encode()
        need(len(raw) <= 8192, "D8_FIXTURE_FILE_BOUND")
        live()
        with (root / "receipt.json").open("xb", buffering=0) as file:
            view = memoryview(raw)
            while view:
                live()
                count = file.write(view[:4096])
                need(count is not None and count > 0, "D8_FIXTURE_SHORT_WRITE")
                view = view[count:]
        live()
        completed = True
        return {"name": name, "path": str(root / "receipt.json"), "bytes": len(raw),
                "sha256": hashlib.sha256(raw).hexdigest()}
    finally:
        # No after-expiry file cleanup. The outer controller owns killing every
        # registered group and PID on any unexpected failure.
        if completed and time.monotonic() < protocol.deadline():
            for fd in (gate_write,):
                try:
                    os.close(fd)
                except OSError:
                    pass

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-head", required=True)
    arguments = parser.parse_args()
    supervise(arguments.expected_head)
