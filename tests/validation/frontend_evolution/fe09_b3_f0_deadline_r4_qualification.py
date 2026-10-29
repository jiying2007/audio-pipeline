#!/usr/bin/env python3
"""R4 exact 2.3.60 audit-source execution derived from protected R2, no promotion.

The original collector and all frozen science inputs remain byte-identical.
This derived entry owns a new receipt identity and stores its effective duration
directly; no runtime rewriting, monkeypatch or relaxed acceptance is used.

The contract/input/source bytes were frozen before any DSP execution.  One
invocation builds each requested target once and runs exactly its eleven
registered trajectories.  Metadata is checked against independent literal
controls and actual PCM before successful PCM is omitted from the artifact.
No executable, archive or network download is performed by this runner.
"""
from __future__ import annotations

import argparse
from collections import Counter
import copy
import csv
import datetime as dt
import gzip
import hashlib
import io
import json
import math
import os
from pathlib import Path
import re
import shutil
import shlex
import signal
import struct
import subprocess
import sys
import tempfile
import time

import fe09_b3_f0_r4_source_admission as forward_source

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
DOCS = ROOT / "docs/research/frontend-evolution-v1/FE09_B3_F0_PREREGISTRATION_20261024"
IDENTITY = "FE09-B3-F0-C4-16K-RENDER-PAP-V1"
COLLECTOR_IDENTITY = "FE09-B3-F0-C4-16K-RENDER-PAP-FORWARD-SOURCE-R4"
REPAIR_DOCS = ROOT / "docs/research/frontend-evolution-v1/FE09_B3_F0_DEADLINE_ACCOUNTING_R1_20261025"
REPAIR_CONTRACT_SHA = "fc06a4da0db4cf5f79a90cfdb0da67c42f8b7c7eccb9dffc6b5e78cb92b44038"
IDENTITY_CONTROL_SHA = "3a9c6dd787111c82efb4157da77694047e50a05e89c7cb65dd045579d2173c38"
ORIGINAL_COLLECTOR_SHA = "f782660590731e73f43c2fab638e84d277c11d36119560dfb8878b28e2456f6c"
CONTRACT_SHA = "74e7294b1433207d222f9732326b68b33303c1ef63c8b6001283963419117284"
LOCK_SHA = "32bd625ee640bf60310bcdc9980a5f8a41711300aee66f029fbf65c98a9bb49d"
INPUT_LOCK_SHA = "9e8cdd3c2889cd071ccfa92e8358de9f15fa371f1e4fc136e6be566ab0765d27"
SELECTION_SHA = "cca7a798ad09f2b272d73409067cbecc57f6225d90890e492066a1e077dd1dca"
FREEZE_BASE = "81ee559848e1e30e3dd2eb4d03b0b479b9bd971e"
TARGETS = ("native", "sanitized", "arm")
CAP = 32 * 1024 * 1024
FRAMES = 600
ROLE = "D0_FIRST_PARTY_DISCLOSED_SYNTHETIC_ENGINEERING"
QUALIFIED = "FE09_B3_F0_FORWARD_SOURCE_R4_C4_16K_RENDER_PAP_FINITE_RESEARCH_NO_PROMOTION"
LOCAL = "FE09_B3_F0_FORWARD_SOURCE_R4_LOCAL_PARTIAL_TARGETS_NO_FULL_QUALIFICATION"
INCONCLUSIVE = "FE09_B3_F0_FORWARD_SOURCE_R4_FIXED_COVERAGE_INCONCLUSIVE"
FAILED = "FE09_B3_F0_FORWARD_SOURCE_R4_COMPOSITION_REJECTED_WITH_EVIDENCE"
BLOCKED = "FE09_B3_F0_FORWARD_SOURCE_R4_EXECUTION_BLOCKED"
PROMOTIONS = {k: False for k in (
    "public_sdk", "acoustic_superiority", "physical_clock", "ssc305",
    "full_resource_budget", "shipping")}
OWN_FILES = [HERE / n for n in (
    "fe09_b3_f0_composition.c", "fe09_b3_f0_composition.h",
    "fe09_b3_f0_composition_test.c", "fe09_b3_f0_observer.c",
    "fe09_b3_f0_qualification.py", "fe09_b3_f0_build/CMakeLists.txt",
    "fe09_b3_f0_deadline_r1_qualification.py",
    "test_fe09_b3_f0_deadline_r1.py")] + [
        REPAIR_DOCS / "PREREGISTRATION.json", REPAIR_DOCS / "README.md",
        REPAIR_DOCS / "IDENTITY_CONTROL.json"] + [HERE / "fe09_b3_f0_deadline_r2_qualification.py",
                      HERE / "fe09_b3_f0_r2_source_admission.py"] + [HERE / name for name in (
    "fe09_b3_f0_deadline_r4_qualification.py", "fe09_b3_f0_r4_source_admission.py",
    "fe09_b3_f0_r4_source_delta_2_3_60.patch.b64")]
HEX64 = re.compile(r"[0-9a-f]{64}\Z")
HEX16 = re.compile(r"[0-9a-f]{16}\Z")
ACTIVE_BUDGET = None


class Rejected(RuntimeError):
    pass


class ExecutionBlocked(Rejected):
    pass


def need(condition: bool, reason: str) -> None:
    if not condition:
        raise Rejected(reason)


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"),
                       ensure_ascii=False, allow_nan=False) + "\n").encode()


def reject_constant(value: str) -> None:
    raise Rejected("NONFINITE_JSON:" + value)


def unique_pairs(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        need(key not in result, "DUPLICATE_JSON_KEY:" + key)
        result[key] = value
    return result


def loads(data: bytes | str) -> object:
    return json.loads(data, object_pairs_hook=unique_pairs,
                      parse_constant=reject_constant)


def read_json(path: Path, limit: int = CAP) -> object:
    need(path.is_file() and not path.is_symlink(), "MISSING_OR_UNSAFE_FILE:" + str(path))
    need(0 < path.stat().st_size <= limit, "FILE_SIZE:" + str(path))
    return loads(path.read_bytes())


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical(value))


def integer(value: object, low: int = 0, high: int = 2**64 - 1) -> bool:
    return type(value) is int and low <= value <= high


def f32_bits(value: float) -> int:
    return struct.unpack("<I", struct.pack("<f", value))[0]


def finite_bits(value: object) -> bool:
    return integer(value, 0, 2**32 - 1) and math.isfinite(
        struct.unpack("<f", struct.pack("<I", value))[0])


def fnv(data: bytes) -> str:
    state = 14695981039346656037
    for byte in data:
        state = ((state ^ byte) * 1099511628211) & 0xFFFFFFFFFFFFFFFF
    return f"{state:016x}"


def git(*args: str) -> str:
    return read_command(["git", "-c", f"safe.directory={ROOT}", *args]).decode().strip()


def check_budget() -> None:
    if ACTIVE_BUDGET is not None:
        ACTIVE_BUDGET.remaining()


def read_command(argv: list[str]) -> bytes:
    cap = ACTIVE_BUDGET.remaining(10) if ACTIVE_BUDGET else 10
    started = time.monotonic()
    row = {"argv": argv, "timeout_seconds": cap,
           "started_offset_seconds": started - ACTIVE_BUDGET.started if ACTIVE_BUDGET else 0}
    if ACTIVE_BUDGET:
        ACTIVE_BUDGET.commands.append(row)
    try:
        result = subprocess.run(argv, cwd=ROOT, check=True, capture_output=True, timeout=cap)
        row.update(returncode=result.returncode, elapsed_seconds=time.monotonic() - started,
                   stdout_sha256=digest(result.stdout))
        check_budget()
        return result.stdout
    except subprocess.TimeoutExpired as exc:
        row.update(timeout=True, elapsed_seconds=time.monotonic() - started)
        raise ExecutionBlocked("SOURCE_METADATA_CHILD_TIMEOUT") from exc
    except subprocess.CalledProcessError as exc:
        row.update(returncode=exc.returncode, elapsed_seconds=time.monotonic() - started)
        raise


def file_identity(path: Path) -> dict:
    data = path.read_bytes()
    return {"path": str(path.relative_to(ROOT)), "bytes": len(data),
            "sha256": digest(data)}


def source_preflight(execution_source: str, require_committed: bool = True) -> dict:
    """Admit only the independently protected exact 2.3.60 source profile.

    All 77 historical R1 members remain locked. The independent R4 gate checks
    66 current executable members with exactly nine reviewed exceptions and
    57 unchanged members. Neither an R1 nor an R2 result is inherited.
    """
    need(bool(re.fullmatch(r"[0-9a-f]{40}", execution_source)), "R4_SOURCE_SHA_FORMAT")
    need(git("rev-parse", "HEAD") == execution_source,
         "R4_EXECUTION_SOURCE_NOT_CURRENT_HEAD")
    need(digest((HERE / "fe09_b3_f0_qualification.py").read_bytes()) ==
         ORIGINAL_COLLECTOR_SHA, "ORIGINAL_COLLECTOR_CHANGED")
    need(digest((REPAIR_DOCS / "PREREGISTRATION.json").read_bytes()) ==
         REPAIR_CONTRACT_SHA and
         digest((REPAIR_DOCS / "IDENTITY_CONTROL.json").read_bytes()) ==
         IDENTITY_CONTROL_SHA, "R1_DEADLINE_SOURCE_OR_IDENTITY_DRIFT")
    need(digest((DOCS / "source-lock.json").read_bytes()) == LOCK_SHA and
         digest((DOCS / "test-contract.json").read_bytes()) == CONTRACT_SHA and
         digest((DOCS / "input-fixture-lock.independent.json").read_bytes()) ==
         INPUT_LOCK_SHA and
         digest((DOCS / "source-lock-gate-selection.json").read_bytes()) ==
         SELECTION_SHA, "R1_FROZEN_SOURCE_OR_INPUT_CHANGED")
    import fe09_b3_f0_r4_derivation_contract as source_review
    source_review.verify_sources()
    admit = forward_source.source_check(execution_source)
    need(admit["status"] == "R4_T1_EXACT_SOURCE_IDENTITY_VERIFIED_NO_DSP_EXECUTION"
         and admit["candidate_version"] == "2.3.60" and
         admit["immutable_source_members"] == 77 and
         admit["source_gated_members"] == 66 and
         admit["source_gated_exceptions"] == 9 and
         admit["source_gated_baseline_members"] == 57 and
         admit["science_executed"] is False and
         admit["shipping_authority"] is False, "R4_FORWARD_SOURCE_NOT_ADMITTED")
    frozen = read_json(DOCS / "INPUT_FIXTURE_FREEZE.json")
    need(frozen["status"] == "FROZEN_BEFORE_FIRST_DSP_EXECUTION" and
         frozen["research_executed"] is False, "R1_INPUT_FREEZE_SCOPE")
    for row in frozen["files"]:
        check_budget()
        data = (DOCS / row["path"]).read_bytes()
        need(len(data) == row["bytes"] and digest(data) == row["sha256"],
             "R1_INPUT_FREEZE_MEMBER:" + row["path"])
    paths = OWN_FILES + sorted(p for p in DOCS.iterdir() if p.is_file()) + [
        ROOT / ".github/workflows/quality.yml",
        ROOT / ".github/research/evidence-index.json",
        ROOT / "docs/research/frontend-evolution-v1/FE09_B3_F0_FORWARD_SOURCE_R2_20261025/PREREGISTRATION.json",
        ROOT / "docs/research/frontend-evolution-v1/FE09_B3_F0_FORWARD_SOURCE_R2_20261025/T2_EXECUTOR_SOURCE_REVIEW.json",
        HERE / "fe09_b3_f0_r2_t2_derivation_contract.py",
        HERE / "fe09_t3s3_f0_r2_t3_timing_identity_contract.py",
        ROOT / "docs/research/frontend-evolution-v1/FE09_B3_F0_FORWARD_SOURCE_R2_20261025/T3_TIMING_IDENTITY_SOURCE_REVIEW.json",
        ROOT / "docs/research/frontend-evolution-v1/FE09_B3_F0_IO_SOURCE_R4_20261029/PREREGISTRATION.json",
        ROOT / "docs/research/frontend-evolution-v1/FE09_B3_F0_IO_SOURCE_R4_20261029/README.md",
        HERE / "fe09_b3_f0_r4_derivation_contract.py"]
    if require_committed:
        need(not git("diff", "--name-only", "HEAD"),
             "R4_TRACKED_WORKTREE_NOT_IMMUTABLE")
        for path in paths:
            rel = str(path.relative_to(ROOT))
            committed = read_command(
                ["git", "-c", f"safe.directory={ROOT}", "show", f"HEAD:{rel}"])
            need(committed == path.read_bytes(),
                 "R4_UNCOMMITTED_EXECUTION_INPUT:" + rel)
    return {"execution_source": execution_source,
            "execution_tree": git("rev-parse", "HEAD^{tree}"),
            "freeze_baseline": FREEZE_BASE,
            "contract_sha256": CONTRACT_SHA,
            "source_lock_sha256": LOCK_SHA,
            "input_lock_sha256": INPUT_LOCK_SHA,
            "full_lock_member_count": 77,
            "source_gated_compiled_member_count": 66,
            "unchanged_compiled_member_count":
                admit["source_gated_baseline_members"],
            "forward_exception_count": admit["source_gated_exceptions"],
            "forward_source_admission": admit,
            "r1_result_inherited": False,
            "r2_result_inherited": False,
            "r3_result_inherited": False,
            "implementation_and_registration": [file_identity(p) for p in paths]}

def baseline_preflight(execution_source: str) -> dict:
    # The qualified predecessor is distinct from this execution.  A pushed main
    # never waits for its own unfinished Verify/Release inside that Verify.
    p = DOCS / "EXECUTION_BASELINE.json"
    if not p.is_file():
        raise ExecutionBlocked("QUALIFIED_EXECUTION_BASELINE_RECEIPT_MISSING")
    data = read_json(p)
    need(data["freeze_baseline"] == FREEZE_BASE and
         data["source_lock_sha256"] == LOCK_SHA and
         data["unchanged_compiled_member_count"] == 66 and
         data["source_equivalent"] is True, "EXECUTION_BASELINE_SOURCE_EQUIVALENCE")
    base = data["qualified_baseline"]
    need(bool(re.fullmatch(r"[0-9a-f]{40}", base)) and base != execution_source,
         "BASELINE_CANNOT_SELF_QUALIFY")
    git("merge-base", "--is-ancestor", base, execution_source)
    for key in ("verify", "release"):
        run = data[key]
        need(run["head_sha"] == base and run["conclusion"] == "success" and
             integer(run["run_id"], 1) and integer(run["attempt"], 1),
             "BASELINE_INDEPENDENT_GATE:" + key)
    need(data["verify"]["summary_app_id"] == 15368 and
         data["live_governance_audit"] == "PASS", "BASELINE_GOVERNANCE_OR_SUMMARY")
    convergence = data["post_release_convergence"]
    need(convergence["head_sha"] == base and convergence["conclusion"] == "success" and
         convergence["run_id"] == data["release"]["run_id"] and
         convergence["attempt"] == data["release"]["attempt"] and integer(convergence["job_id"], 1),
         "BASELINE_POST_RELEASE_CONVERGENCE")
    return data


def event_context() -> dict:
    result = {"kind": "local", "run_id": None, "run_attempt": None,
              "event_name": None, "event_head": None, "event_base": None}
    if os.environ.get("GITHUB_ACTIONS") != "true":
        return result
    result.update(kind="github_actions", run_id=int(os.environ["GITHUB_RUN_ID"]),
                  run_attempt=int(os.environ["GITHUB_RUN_ATTEMPT"]),
                  event_name=os.environ["GITHUB_EVENT_NAME"])
    event = read_json(Path(os.environ["GITHUB_EVENT_PATH"]), 8 * 1024 * 1024)
    if result["event_name"] == "pull_request":
        result.update(event_head=event["pull_request"]["head"]["sha"],
                      event_base=event["pull_request"]["base"]["sha"],
                      pr_number=event["number"])
    elif result["event_name"] == "push":
        result.update(event_head=event["after"], event_base=event["before"])
    else:
        raise ExecutionBlocked("UNREGISTERED_EXECUTION_EVENT")
    return result


class Budget:
    def __init__(self, deadline_file: str | None):
        self.started = time.monotonic()
        self.started_epoch = time.time()
        self.effective_limit_seconds = 300.0
        self.job = None
        if os.environ.get("GITHUB_ACTIONS") == "true":
            if not deadline_file:
                raise ExecutionBlocked("ORIGINAL_JOB_DEADLINE_MISSING")
            self.job = read_json(Path(deadline_file), 16384)
            need(self.job.get("status") == "OBSERVED_ACTUAL_JOB_START" and
                 self.job.get("run_id") == int(os.environ["GITHUB_RUN_ID"]) and
                 self.job.get("run_attempt") == int(os.environ["GITHUB_RUN_ATTEMPT"]),
                 "ORIGINAL_JOB_DEADLINE_UNPROVEN")
            need(self.job["timeout_minutes"] == 15 and
                 self.job["archive_reserve_seconds"] == 60 and
                 self.job["deadline_epoch"] == self.job["started_at_epoch"] + 900,
                 "ORIGINAL_JOB_TIMEOUT_CHANGED")
            self.effective_limit_seconds = min(
                self.effective_limit_seconds,
                self.job["deadline_epoch"] - self.started_epoch - 60)
        self.commands = []

    def remaining(self, cap: float = 300) -> float:
        elapsed = time.monotonic() - self.started
        left = min(cap, self.effective_limit_seconds - elapsed)
        if left <= 0:
            raise ExecutionBlocked("FROZEN_OUTER_OR_ORIGINAL_JOB_BUDGET_EXHAUSTED")
        return left

    def command(self, argv: list[str], log: Path, cap: float = 240,
                env: dict | None = None, allowed: tuple[int, ...] = (0,)) -> int:
        timeout = self.remaining(cap)
        log.parent.mkdir(parents=True, exist_ok=True)
        started = time.monotonic()
        row = {"argv": argv, "timeout_seconds": timeout,
               "started_offset_seconds": started - self.started}
        self.commands.append(row)
        with log.open("xb") as output:
            process = subprocess.Popen(argv, cwd=ROOT, env=env, stdout=output,
                                       stderr=subprocess.STDOUT, start_new_session=True)
            try:
                status = process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
                row.update(returncode=process.returncode, timeout=True,
                           elapsed_seconds=time.monotonic() - started)
                raise ExecutionBlocked("CHILD_TIMEOUT:" + log.name)
        row.update(returncode=status, elapsed_seconds=time.monotonic() - started)
        need(log.stat().st_size <= 4 * 1024 * 1024, "CHILD_LOG_CAP:" + log.name)
        need(status in allowed, "CHILD_FAILURE:" + log.name + ":" + str(status))
        self.remaining()
        return status

    def record(self) -> dict:
        return {"outer_seconds": 300, "existing_job": self.job,
                "archive_reserve_seconds": 60, "started_epoch": self.started_epoch,
                "elapsed_seconds": time.monotonic() - self.started,
                "effective_deadline_offset_seconds": self.effective_limit_seconds,
                "commands": self.commands}


def validate_retained_budget(b: dict) -> None:
    # Exact original bounds remain; the saved duration also has one source.
    expected = (300.0 if b["existing_job"] is None else
                min(300.0, b["existing_job"]["deadline_epoch"] -
                    b["started_epoch"] - 60))
    need(b["outer_seconds"] == 300 and b["archive_reserve_seconds"] == 60 and
         b["effective_deadline_offset_seconds"] == expected and
         0 < b["elapsed_seconds"] <= b["effective_deadline_offset_seconds"] <= 300,
         "RETAINED_FROZEN_WALL_BUDGET")
    for cmd in b["commands"]:
        need(cmd.get("timeout") is not True and cmd["elapsed_seconds"] <= cmd["timeout_seconds"] + 1 and
             cmd["started_offset_seconds"] + cmd["timeout_seconds"] <= b["effective_deadline_offset_seconds"] + .01,
             "RETAINED_CHILD_DEADLINE")


def schedule() -> list[dict]:
    result = []
    for observed in (False, True):
        for case in ("ALL_P", "PAP"):
            for repeat in range(2):
                variant = "observed" if observed else "plain"
                result.append({"name": f"{variant}-{case}-{repeat}", "case": case,
                               "mode": "adapter", "observed": observed,
                               "future": False, "repeat": repeat,
                               "negatives": not observed and case == "PAP" and repeat == 0})
    for case in ("ALL_P", "PAP"):
        result.append({"name": "direct-" + case, "case": case, "mode": "direct",
                       "observed": False, "future": False, "repeat": 0, "negatives": False})
    result.append({"name": "future-PAP", "case": "PAP", "mode": "adapter",
                   "observed": True, "future": True, "repeat": 0, "negatives": False})
    return result


def fixed_inputs(raw: Path) -> dict:
    return fixed_input_bytes({name: (raw / name).read_bytes() for name in
                              ("capture.s16le", "render.s16le", "render-pap.s16le")})


def literal_inputs() -> dict:
    """Independent fixed integer construction for retained-artifact verification.

    No project executable or C adapter is loaded.  The pre-DSP SHA256 lock is
    the authority; this cannot select a new fixture from observed outcomes.
    """
    render_state, near_state = 2654435769, 608135816
    mic_states = [286331153, 572662306, 858993459, 1145324612]
    render, capture = [], []
    for n in range(96000):
        render_state = (1664525 * render_state + 1013904223) & 0xFFFFFFFF
        render.append(((render_state >> 16) & 8191) - 4096)
        near_state = (1664525 * near_state + 1013904223) & 0xFFFFFFFF
        near = ((near_state >> 16) & 32767) - 16384 if 160 <= n // 160 < 280 else 0
        delayed = render[n - 640] if n >= 640 else 0
        echo = delayed // 4 if delayed >= 0 else -((-delayed) // 4)
        for channel in range(4):
            mic_states[channel] = (1664525 * mic_states[channel] + 1013904223) & 0xFFFFFFFF
            capture.append(echo + near + ((mic_states[channel] >> 24) & 127) - 64)
    capture_bytes = struct.pack("<384000h", *capture)
    render_bytes = struct.pack("<96000h", *render)
    return fixed_input_bytes({"capture.s16le": capture_bytes, "render.s16le": render_bytes,
                              "render-pap.s16le": render_bytes[:200 * 320] + render_bytes[240 * 320:]})


def fixed_input_bytes(streams: dict[str, bytes]) -> dict:
    lock = read_json(DOCS / "input-fixture-lock.independent.json")
    names = {"capture.s16le": "capture_all_p_and_pap",
             "render.s16le": "render_full_all_p", "render-pap.s16le": "render_pap_delivered"}
    for name, key in names.items():
        data = streams[name]
        truth = lock["streams"][key]
        need(len(data) == truth["bytes"] and digest(data) == truth["sha256"],
             "C_FIXTURE_DIFFERS_FROM_PRE_DSP_INDEPENDENT_TRUTH:" + name)
    capture, render = streams["capture.s16le"], streams["render.s16le"]
    def invert_suffix(data: bytes, scalar_prefix: int) -> bytes:
        at = scalar_prefix * 2
        values = struct.unpack("<" + str((len(data) - at) // 2) + "h", data[at:])
        return data[:at] + struct.pack("<" + str(len(values)) + "h", *[-v for v in values])
    future_capture = invert_suffix(capture, 240 * 160 * 4)
    future_render = invert_suffix(render, 240 * 160)
    need(digest(future_capture) == lock["streams"]["capture_future_suffix_control"]["sha256"],
         "FUTURE_CAPTURE_INPUT_TRUTH")
    need(digest(future_render[:200 * 320] + future_render[240 * 320:]) ==
         lock["streams"]["render_pap_future_suffix_control"]["sha256"], "FUTURE_RENDER_INPUT_TRUTH")
    ledgers = {}
    for case, row in lock["input_control_ledgers"].items():
        data = (DOCS / row["path"]).read_bytes()
        need(digest(data) == row["sha256"] and len(data) == row["bytes"], "INPUT_LEDGER_HASH")
        lines = list(csv.DictReader(io.StringIO(data.decode())))
        need(len(lines) == 600, "INPUT_LEDGER_COUNT")
        for seq, line in enumerate(lines, 1):
            absent = case == "PAP" and 201 <= seq <= 240
            cap = capture[(seq - 1) * 1280:seq * 1280]
            ref = render[(seq - 1) * 320:seq * 320]
            need(line["capture_s16le_sha256"] == digest(cap) and
                 line["render_s16le_sha256"] == ("" if absent else digest(ref)),
                 "INDEPENDENT_PER_FRAME_INPUT:" + case + ":" + str(seq))
        ledgers[case] = lines
    result = {"capture": capture, "render": render, "future_capture": future_capture,
              "future_render": future_render, "ledgers": ledgers,
              "capture_fnv": fnv(capture), "render_fnv": fnv(render)}
    result["frame_hashes"] = {}
    for name, width in (("capture", 1280), ("render", 320),
                        ("future_capture", 1280), ("future_render", 320)):
        result["frame_hashes"][name] = [fnv(result[name][i * width:(i + 1) * width])
                                        for i in range(600)]
    return result


def expected_config() -> dict:
    return {"io_rate_hz": 16000, "internal_rate_hz": 16000, "physical_mics": 4,
            "mono_mics": 1, "stage_mask": 253, "compiled_stage_mask": 255,
            "aec_filter_ms": 96, "aec_mu_bits": f32_bits(.22), "aec_adapt_stride": 2,
            "max_delay_ms": 180, "initial_delay_ms": 40, "ns_floor_bits": f32_bits(.12),
            "agc_target_dbfs_bits": f32_bits(-20), "limiter_dbfs_bits": f32_bits(-2),
            "resource_class": 2, "enable_delay_tracking": 1,
            "enable_clock_drift_compensation": 1, "quality": 2,
            "aec_backend": "MDF", "simd": "SCALAR", "ns_estimator": "EMA"}


def validate_observer(o: dict, m: dict, present: bool, notify: bool,
                      previous: dict | None) -> None:
    need(type(o) is dict and o["violations"] == 0, "ACTUAL_OBSERVER_VIOLATION")
    need(all(integer(v, -(2**31) if k == "notify_status" else 0)
             for k, v in o.items() if k not in ("calls", "order")), "OBSERVER_INTEGER_SCHEMA")
    need(type(o["order"]) is list and all(integer(v, 0, 13) for v in o["order"]),
         "OBSERVER_ORDER_SCHEMA")
    calls = o["calls"]
    need(type(calls) is list and len(calls) == 14 and all(integer(v, 0, 4) for v in calls),
         "OBSERVED_CALL_SCHEMA")
    need(calls[:8] == [1] * 8 and calls[8] == int(present) and
         calls[9] == int(notify) and calls[11:13] == [0, 0] and calls[13] == int(notify),
         "ACTUAL_STAGE_COUNTS")
    need(o["route_jump"] in (0, 1) and calls[10] == int(notify) + o["route_jump"] and
         o["explicit_aec_resets"] == int(notify) and
         o["automatic_aec_resets"] == o["route_jump"], "CLASSIFIED_AEC_RESETS")
    order = ([13, 9, 10] if notify else []) + ([8] if present else []) + [0, 1]
    if o["route_jump"]:
        order.append(10)
    order += [2, 3, 4, 5, 6, 7]
    need(o["order"] == order, "ACTUAL_STAGE_ORDER")
    need(all(o[k] in (0, 1) for k in ("far", "dt", "aec_far", "aec_dt", "ns_far",
                                     "ns_dt", "frequency_res_active", "agc_allow")),
         "ACTUAL_GATE_DOMAIN")
    need(o["far"] == o["aec_far"] == o["ns_far"] == m["far_end_active"] and
         o["dt"] == o["aec_dt"] == o["ns_dt"] == m["double_talk_active"],
         "ACTIVITY_GATE_ARGUMENT_LINEAGE")
    need(o["ns_enable"] == o["ns_echo_present"] == 1 and o["ns_mode"] == 2,
         "FULL_NS_FREQUENCY_RES_PATH")
    need(o["frequency_res_active"] == int(bool(o["far"] and not o["dt"])) ==
         m["frequency_res_active"] and
         o["agc_allow"] == int(not (o["far"] and not o["dt"])), "ACTUAL_RES_AGC_PREDICATES")
    need(o["vad_active"] == m["vad_active"] and
         o["vad_probability_bits"] == m["float_bits"][5] and
         o["residual_gain_bits"] == m["float_bits"][4], "NS_VAD_METRIC_LINEAGE")
    need(finite_bits(o["agc_gain_before_bits"]) and finite_bits(o["agc_gain_after_bits"]),
         "NONFINITE_ACTUAL_AGC")
    need(integer(o["sync_delay_samples"], 0, 2880) and
         m["estimated_delay_ms"] == o["sync_delay_samples"] * 1000 // 16000,
         "ACTUAL_SYNC_PRECISION_LEDGER")
    if notify:
        need((o["notify_flags"], o["notify_lost_frames"], o["notify_status"],
              o["notify_capture_preserved"], o["notify_processed_preserved"],
              o["notify_reset_state_mask"]) == (2, 1, 0, 1, 1, 511),
             "ACTUAL_NOTIFY_OR_EXTERNAL_CAPTURE_RESET")
    else:
        need(all(o[k] == 0 for k in ("notify_flags", "notify_lost_frames", "notify_status",
                 "notify_capture_preserved", "notify_processed_preserved", "notify_reset_state_mask")),
             "UNREGISTERED_NOTIFY")
    previous_resets = previous["aec_resets"] if previous else 0
    previous_jumps = previous["delay_jumps"] if previous else 0
    need(m["aec_resets"] - previous_resets == calls[10] and
         m["delay_jumps"] - previous_jumps == o["route_jump"], "PUBLIC_RESET_LEDGER")


def validate_case_identity(r: dict) -> None:
    # The frozen C executable keeps the original scientific experiment ID.
    need(r["schema_version"] == 1 and r["id"] == IDENTITY and r["source_role"] == ROLE,
         "CASE_IDENTITY_OR_SOURCE_ROLE")


def validate_collector_identity(r: dict, execution_source: str) -> None:
    # The derived collector has a separate receipt namespace, not a new C ID.
    need(r["id"] == COLLECTOR_IDENTITY and r["execution_source"] == execution_source and
         r["source_role"] == ROLE and r["promotion"] == PROMOTIONS,
         "RETAINED_SOURCE_OR_AUTHORITY")


def validate_case(case: dict, spec: dict, inputs: dict | None) -> bool:
    check_budget()
    r, frames, streams = case["result"], case["frames"], case["streams"]
    validate_case_identity(r)
    need(r["case"] == spec["case"] and r["mode"] == spec["mode"] and
         r["observed"] is spec["observed"] and r["future"] is spec["future"] and
         r["negatives_requested"] is spec["negatives"], "UNREGISTERED_CASE")
    need(r["failure"] is None and r["status"] in ("OK", "INCONCLUSIVE") and
         r["frames"] == len(frames) == FRAMES, "CASE_FAILED_OR_INCOMPLETE")
    need(r["attempted_frame"] == 600 and r["failed_frame"] == r["failed_negative"] == 0 and
         all(r[k] is None for k in ("failure_phase", "failure_state", "failed_observation")),
         "COMPLETE_CASE_CONTAINS_FAILURE_EVIDENCE")
    need(r["config"] == expected_config(), "EFFECTIVE_CONFIG_IDENTITY")
    need(all(type(r["config"][k]) is type(v) for k, v in expected_config().items()),
         "EFFECTIVE_CONFIG_TYPES")
    need(r["latency"] == {"input_src_samples": 0, "bf_samples": 22, "mono_ms": 10,
                          "declared_sum_samples": 182}, "DECLARED_LATENCY_LEDGER")
    need(r["promotion"] == PROMOTIONS, "FORBIDDEN_PROMOTION")
    c = r["counters"]
    pap = spec["case"] == "PAP"
    expected = {"accepted": 600, "present": 560 if pap else 600,
                "absent": 40 if pap else 0, "notify": 2 if pap else 0,
                "negative_mask": 65535 if spec["negatives"] else 0,
                "negative_count": 16 if spec["negatives"] else 0,
                "setup_source_publications": 5 if spec["negatives"] else 0}
    need(all(c.get(k) == v and type(c.get(k)) is int for k, v in expected.items()),
         "ACTUAL_CASE_COUNTS_OR_NEGATIVE_BUDGET")
    resource = r["resource"]
    need(type(resource) is dict and all(integer(v) for v in resource.values()), "RESOURCE_SCHEMA")
    need(0 < resource["observer_record_bytes"] <= 384 and
         resource["observer_storage_bytes"] <= 262144, "OBSERVER_RAM_CAP")
    if spec["observed"]:
        need(resource["observer_record_bytes"] * 600 <= resource["observer_storage_bytes"] <=
             resource["observer_record_bytes"] * 600 + 8192, "OBSERVER_ACTUAL_ALLOCATION")
    else:
        need(resource["observer_storage_bytes"] == 0, "PLAIN_HAS_OBSERVER_STORAGE")
    for name, per_frame in (("output", 320), ("beam", 640)):
        s = streams[name]
        need(s["bytes"] == 600 * per_frame and bool(HEX64.fullmatch(s["sha256"])) and
             bool(HEX64.fullmatch(s["prefix240_sha256"])) and len(s["frame_sha256"]) == 600 and
             all(HEX64.fullmatch(x) for x in s["frame_sha256"]), "ACTUAL_PCM_STREAM_LEDGER")
    need(streams["actual_raw_bytes_checked"] is True, "RAW_OUTPUT_WAS_NOT_CHECKED")
    if inputs:
        need(r["capture_source_fnv64"] == inputs["capture_fnv"] and
             r["render_source_fnv64"] == inputs["render_fnv"], "SOURCE_PCM_IDENTITY")
    counts = [0] * 14
    frequency = double_talk = allow_gain = beam_clips = ref_clips = 0
    previous = None
    for seq, f in enumerate(frames, 1):
        if seq % 100 == 0:
            check_budget()
        absent = pap and 201 <= seq <= 240
        notify = pap and seq in (201, 241)
        need(all(integer(value) for key, value in f.items()
                 if key not in ("metrics", "observer") and not key.endswith("_fnv64")),
             "FRAME_INTEGER_SCHEMA")
        need(f["seq"] == seq and f["event"] == (2 if absent else 1) and
             f["epoch"] == (2 if pap and seq >= 241 else 1) and
             f["reason"] == int(absent), "FROZEN_LITERAL_RENDER_EVENT")
        need((f["source_generation"], f["capture_source_id"], f["render_source_id"]) ==
             (900001, 104, 204), "SOURCE_OWNER_IDENTITY")
        need(f["capture_accepted"] == seq and f["capture_epoch"] == f["clock_epoch"] == 0 and
             f["render_src_epoch"] == f["epoch"], "CAPTURE_OR_RENDER_HISTORY_EPOCH")
        need(f["reference_actual_pcm"] == int(not absent) and f["explicit_notify"] == int(notify),
             "SOURCE_ABSENCE_IS_NOT_ZERO_PCM")
        need(not absent or f["absent_reference_untouched"] == 1, "ABSENT_REFERENCE_WAS_WRITTEN")
        need(not notify or f["notify_capture_preserved"] == 1, "CAPTURE_RESET_ON_RENDER_EVENT")
        for k in ("capture_fnv64", "render_fnv64", "beam_fnv64", "output_fnv64", "capture_arena_fnv64"):
            need(type(f[k]) is str and bool(HEX16.fullmatch(f[k])), "FRAME_HASH_SCHEMA")
        need(not absent or f["render_fnv64"] == "0000000000000000", "ABSENT_HAS_PCM_HASH")
        if inputs:
            suffix = "future_" if spec["future"] else ""
            cap_hash = inputs["frame_hashes"][suffix + "capture"][seq - 1]
            ref_hash = inputs["frame_hashes"][suffix + "render"][seq - 1]
            need(f["capture_fnv64"] == cap_hash and
                 f["render_fnv64"] == ("0000000000000000" if absent else ref_hash),
                 "ACTUAL_FRAME_INPUT_BYTES")
        m = f["metrics"]
        need(type(m["float_bits"]) is list and len(m["float_bits"]) == 7 and
             all(finite_bits(v) for v in m["float_bits"]), "NONFINITE_PUBLIC_METRIC")
        need(m["processed_frames"] == seq and m["quality"] == 2 and m["aec_backend"] == 0 and
             m["timestamp_observations"] == 0, "PUBLIC_METRIC_CONFIG_OR_CLOCK_AUTHORITY")
        for k, v in m.items():
            if k != "float_bits":
                need(integer(v, -(2**31) if k == "delay_error_samples" else 0), "PUBLIC_METRIC_TYPE")
        for k in ("vad_active", "far_end_active", "double_talk_active", "frequency_res_active",
                  "erle_valid", "aec_converged"):
            need(m[k] in (0, 1), "PUBLIC_METRIC_FLAG")
        if spec["observed"]:
            validate_observer(f["observer"], m, not absent, notify, previous)
            counts = [a + b for a, b in zip(counts, f["observer"]["calls"])]
        else:
            need(f["observer"] is None, "PLAIN_INSTRUMENTATION_DRIFT")
        frequency += m["frequency_res_active"]
        double_talk += m["double_talk_active"]
        allow_gain += int(not (m["far_end_active"] and not m["double_talk_active"]))
        need(integer(f["beam_clips"]) and integer(f["reference_clips"]), "CLIP_COUNTER_SCHEMA")
        beam_clips += f["beam_clips"]
        ref_clips += f["reference_clips"]
        previous = m
    reached = 0 < frequency < 600 and double_talk > 0 and 0 < allow_gain < 600
    need(r["coverage"] == {"frequency_on_frames": frequency, "frequency_off_frames": 600 - frequency,
         "double_talk_frames": double_talk, "agc_allow_frames": allow_gain,
         "agc_disallow_frames": 600 - allow_gain, "required_reached": reached}, "COVERAGE_RECOMPUTATION")
    need(r["coverage"]["required_reached"] is reached and
         all(integer(value) for key, value in r["coverage"].items() if key != "required_reached"),
         "COVERAGE_TYPES")
    need(r["status"] == ("OK" if reached else "INCONCLUSIVE"), "UNREACHED_BRANCH_FALSE_PASS")
    need(r["observed_calls"] == counts and r["observed_violations"] == 0 and
         c["beam_clips"] == beam_clips and c["reference_clips"] == ref_clips,
         "OBSERVED_TOTAL_OR_CLIP_LEDGER")
    return reached


def canonical_frame(frame: dict) -> dict:
    return {k: v for k, v in frame.items() if k != "observer"}


def validate_suite(cases: dict, inputs: dict | None) -> dict:
    specs = schedule()
    need(set(cases) == {s["name"] for s in specs}, "EXACT_ELEVEN_CASE_BUDGET")
    coverage = []
    for spec in specs:
        coverage.append(validate_case(cases[spec["name"]], spec, inputs))
    comparisons = {}
    for case in ("ALL_P", "PAP"):
        reference = cases[f"plain-{case}-0"]
        for name in (f"plain-{case}-1", f"observed-{case}-0", f"observed-{case}-1", f"direct-{case}"):
            other = cases[name]
            need(reference["streams"] == other["streams"], "ACTUAL_PCM_EQUIVALENCE:" + name)
            need([canonical_frame(f) for f in reference["frames"]] ==
                 [canonical_frame(f) for f in other["frames"]], "PER_FRAME_INDEPENDENT_EQUIVALENCE:" + name)
            comparisons[name] = "BITWISE_PCM_PUBLIC_METRICS_EVENT_CAPTURE_HISTORY_MATCH"
        need(cases[f"observed-{case}-0"]["frames"] == cases[f"observed-{case}-1"]["frames"],
             "REPEATED_ACTUAL_OBSERVER_TRACE:" + case)
    all_p, pap = cases["plain-ALL_P-0"], cases["plain-PAP-0"]
    need(all_p["streams"]["beam"] == pap["streams"]["beam"], "CAPTURE_BF_CHANGED_WITH_REFERENCE_AVAILABILITY")
    capture_keys = ("capture_fnv64", "beam_fnv64", "capture_arena_fnv64", "capture_accepted",
                    "capture_epoch", "clock_epoch")
    need(all(all(a[k] == p[k] for k in capture_keys) for a, p in zip(all_p["frames"], pap["frames"])),
         "EXTERNAL_CAPTURE_STATE_CHANGED_WITH_RENDER_GAP")
    future, original = cases["future-PAP"], cases["observed-PAP-0"]
    need(future["frames"][:240] == original["frames"][:240], "FUTURE_CAUSAL_PREFIX_FRAMES")
    for name in ("beam", "output"):
        need(future["streams"][name]["prefix240_sha256"] == original["streams"][name]["prefix240_sha256"] and
             future["streams"][name]["frame_sha256"][:240] == original["streams"][name]["frame_sha256"][:240],
             "FUTURE_CAUSAL_PCM_PREFIX")
    return {"all_fixed_coverage_reached": all(coverage), "comparisons": comparisons,
            "capture_all_p_equals_pap": True, "future_prefix240_equal": True,
            "accepted_frames": 6600, "negative_cases": 16, "extra_setup_publications": 5}


def eight_semantic_negatives(cases: dict, inputs: dict | None) -> list[dict]:
    # All mutations operate on real complete evidence, never fabricated passes.
    # Canonical reserialization below deliberately removes a mere byte-seal as
    # an explanation for rejection.  The semantic verifier must reject each.
    def mutate01(x): x["observed-PAP-0"]["frames"][200]["event"] = 1
    def mutate02(x): x["observed-PAP-0"]["frames"][0]["observer"]["calls"][11] = 1
    def mutate03(x): x["observed-PAP-0"]["frames"][0]["observer"]["order"][-1] = 6
    def mutate04(x): x["plain-ALL_P-0"]["result"]["config"]["stage_mask"] = 125
    def mutate05(x): x["plain-ALL_P-0"]["frames"].pop()
    def mutate06(x): x["observed-PAP-0"]["frames"][200]["observer"]["notify_flags"] = 0
    def mutate07(x): x["direct-PAP"]["streams"]["output"]["sha256"] = "0" * 64
    def mutate08(x): x["plain-ALL_P-0"]["result"]["promotion"]["shipping"] = True
    results = []
    for index, mutate in enumerate((mutate01, mutate02, mutate03, mutate04,
                                     mutate05, mutate06, mutate07, mutate08), 1):
        check_budget()
        changed = copy.deepcopy(cases)
        mutate(changed)
        changed = loads(canonical(changed))
        try:
            validate_suite(changed, inputs)
        except Rejected as exc:
            results.append({"id": f"S{index:02d}", "rejected": True, "reason": str(exc),
                            "resealed_canonical_evidence": True, "additional_DSP_frames": 0})
        else:
            raise Rejected(f"SEMANTIC_MUTATION_ACCEPTED:S{index:02d}")
    return results


def load_case(raw: Path, spec: dict) -> dict:
    r = read_json(raw / "result.json", 65536)
    data = (raw / "frames.jsonl").read_bytes()
    need(len(data) <= 4 * 1024 * 1024, "FRAME_METADATA_CAP")
    frames = [loads(line) for line in data.splitlines()]
    streams = {"actual_raw_bytes_checked": True}
    for key, filename, per_frame in (("output", "output.s16le", 320), ("beam", "beam.f32le", 640)):
        pcm = (raw / filename).read_bytes()
        need(len(pcm) == len(frames) * per_frame, "ACTUAL_PCM_LENGTH:" + filename)
        if key == "beam":
            need(all(math.isfinite(v[0]) for v in struct.iter_unpack("<f", pcm)), "NONFINITE_BF_PCM")
        hashes = []
        for index, frame in enumerate(frames):
            chunk = pcm[index * per_frame:(index + 1) * per_frame]
            need(fnv(chunk) == frame[key + "_fnv64"], "ACTUAL_PCM_FRAME_HASH:" + filename)
            hashes.append(digest(chunk))
        streams[key] = {"bytes": len(pcm), "sha256": digest(pcm),
                        "frame_sha256": hashes, "prefix240_sha256": digest(pcm[:240 * per_frame])}
    return {"result": r, "frames": frames, "streams": streams}


def retain_case(destination: Path, case: dict) -> None:
    destination.mkdir(parents=True, exist_ok=False)
    write_json(destination / "result.json", case["result"])
    write_json(destination / "streams.json", case["streams"])
    raw = b"".join(canonical(row) for row in case["frames"])
    (destination / "frames.jsonl.gz").write_bytes(gzip.compress(raw, mtime=0))


def build_target(target: str, temp: Path, output: Path, budget: Budget, cmake: str) -> tuple[Path, dict]:
    compiler_name = "arm-linux-gnueabihf-gcc" if target == "arm" else "cc"
    compiler_path = shutil.which(compiler_name)
    if compiler_path is None or (target == "arm" and shutil.which("qemu-arm") is None):
        raise ExecutionBlocked("REQUIRED_TARGET_TOOL_MISSING:" + target)
    # The unchanged toolchain types this cache entry as FILEPATH. An untyped
    # basename from -D is then made relative to cwd before compiler discovery.
    # Keep the PATH-selected alias (including compiler wrappers) and use its
    # absolute path for both identity and build, without dereferencing symlinks.
    compiler = str(Path(compiler_path).absolute())
    build = temp / ("build-" + target)
    logs = output / target / "build"
    logs.mkdir(parents=True)
    budget.command([compiler, "--version"], logs / "compiler.log", 10)
    configure = [cmake, "-S", str(HERE / "fe09_b3_f0_build"), "-B", str(build),
                 f"-DAP_REPO_ROOT={ROOT}", "-DCMAKE_BUILD_TYPE=Release",
                 f"-DCMAKE_C_COMPILER={compiler}",
                 "-DCMAKE_C_FLAGS_RELEASE=" + ("-O1 -g -DNDEBUG" if target == "sanitized" else "-O2 -DNDEBUG"),
                 "-DB3_F0_SANITIZE=" + ("ON" if target == "sanitized" else "OFF")]
    if target == "arm":
        configure += ["-DCMAKE_TOOLCHAIN_FILE=" + str(ROOT / "cmake/toolchains/arm-linux-gnueabihf.cmake")]
    budget.command(configure, logs / "configure.log")
    budget.command([cmake, "--build", str(build), "--parallel", "2", "--target",
                    "fe09_b3_f0_plain", "fe09_b3_f0_observed"], logs / "build.log")
    artifacts = {}
    for rel in ("fe09_b3_f0_plain", "fe09_b3_f0_observed", "public_sdk/libaudio_pipeline.a",
                "public_sdk/generated/audio_pipeline/audio_pipeline_build.h", "compile_commands.json", "CMakeCache.txt"):
        path = build / rel
        need(path.is_file(), "BUILT_ARTIFACT_MISSING:" + rel)
        artifacts[rel] = {"bytes": path.stat().st_size, "sha256": digest(path.read_bytes())}
    commands = read_json(build / "compile_commands.json")
    need(not any("Unity/" in row["file"] for row in commands), "ACTUAL_LIBRARY_UNITY_STILL_ON")
    for row in commands:
        command = row.get("command", " ".join(row.get("arguments", [])))
        need("-ffp-contract=off" in command and "-fno-fast-math" in command and
             "-fno-lto" in command and "-ffast-math" not in command,
             "ACTUAL_COMPILE_FP_RECIPE_DRIFT")
    (logs / "compile_commands.json").write_bytes((build / "compile_commands.json").read_bytes())
    (logs / "audio_pipeline_build.h").write_bytes((build / "public_sdk/generated/audio_pipeline/audio_pipeline_build.h").read_bytes())
    (logs / "CMakeCache.txt").write_bytes((build / "CMakeCache.txt").read_bytes())
    link_recipes = {}
    for variant in ("plain", "observed"):
        rel = f"CMakeFiles/fe09_b3_f0_{variant}.dir/link.txt"
        link = (build / rel).read_text()
        need("public_sdk/libaudio_pipeline.a" in link and "-fno-lto" in link, "SAME_ORIGINAL_LIBRARY_LINK")
        link_recipes[variant] = link
        budget.command(["readelf", "-h", "-SW", str(build / ("fe09_b3_f0_" + variant))],
                       logs / (variant + "-elf.log"), 10)
    write_json(logs / "link-recipes.json", link_recipes)
    symbols_log = logs / "observed-symbols.log"
    budget.command(["nm", "--defined-only", str(build / "fe09_b3_f0_observed")], symbols_log, 10)
    symbols = symbols_log.read_text()
    for name in read_json(DOCS / "test-contract.json")["observation"]["wrapped_functions"]:
        need(re.search(r"\b__wrap_" + re.escape(name) + r"$", symbols, re.M), "ACTUAL_WRAPPER_NOT_LINKED:" + name)
    stack_rows = []
    for path in sorted(build.rglob("*.su")):
        for line in path.read_text().splitlines():
            fields = line.rsplit("\t", 2)
            need(len(fields) == 3 and fields[1].isdigit(), "COMPILER_STACK_LEDGER_SCHEMA")
            stack_rows.append({"object": str(path.relative_to(build)), "function": fields[0],
                               "bytes": int(fields[1]), "kind": fields[2]})
    need(bool(stack_rows), "COMPILER_STACK_LEDGER_MISSING")
    write_json(logs / "stack-usage.json", stack_rows)
    identity = {"target": target, "artifacts": artifacts, "repository_source_root": str(ROOT),
                   "compiler_version_sha256": digest((logs / "compiler.log").read_bytes()),
                   "link_recipes_sha256": digest((logs / "link-recipes.json").read_bytes()),
                   "stack_usage_sha256": digest((logs / "stack-usage.json").read_bytes()),
                   "maximum_single_compiler_frame_bytes": max(r["bytes"] for r in stack_rows),
                   "stack_scope": "Per-function compiler reports; not cumulative stack, full RSS, or DUT budget",
                   "observed_symbols_sha256": digest(symbols_log.read_bytes()),
                   "unity": False, "ipo": False, "same_library_for_plain_and_observed": True}
    validate_build_evidence(logs, identity)
    return build, identity


def validate_build_evidence(directory: Path, identity: dict) -> None:
    """Pure metadata validation reused during original collection and readback."""
    for retained, artifact in (("compile_commands.json", "compile_commands.json"),
            ("audio_pipeline_build.h", "public_sdk/generated/audio_pipeline/audio_pipeline_build.h"),
            ("CMakeCache.txt", "CMakeCache.txt")):
        data = (directory / retained).read_bytes()
        need(identity["artifacts"][artifact] == {"bytes": len(data), "sha256": digest(data)},
             "ACTUAL_RETAINED_BUILD_BYTES:" + retained)
    for name, key in (("compiler.log", "compiler_version_sha256"),
                      ("link-recipes.json", "link_recipes_sha256"), ("stack-usage.json", "stack_usage_sha256"),
                      ("observed-symbols.log", "observed_symbols_sha256")):
        need(digest((directory / name).read_bytes()) == identity[key], "RETAINED_BUILD_IDENTITY:" + name)
    rows = read_json(directory / "compile_commands.json")
    need(type(rows) is list and rows, "ACTUAL_COMPILE_COMMANDS_EMPTY")
    observed_root = Path(identity["repository_source_root"])
    need(observed_root.is_absolute(), "BUILD_SOURCE_ROOT_IDENTITY")
    allowed = {str(observed_root / row["path"]) for row in read_json(DOCS / "source-lock.json")["files"]
               if row["role"] != "authority_or_reference_snapshot_not_executed"}
    allowed.update(str(observed_root / p.relative_to(ROOT)) for p in OWN_FILES)
    definitions = {"library": set(), "plain": set(), "observed": set()}
    variant_files = {"library": set(), "plain": set(), "observed": set()}
    for row in rows:
        need(row["file"] in allowed and "Unity/" not in row["file"], "UNLOCKED_COMPILED_SOURCE")
        tokens = shlex.split(row["command"]) if "command" in row else row["arguments"]
        need(all(flag in tokens for flag in ("-std=c11", "-ffp-contract=off", "-fno-fast-math", "-fno-lto")) and
             "-ffast-math" not in tokens and "-flto" not in tokens, "ACTUAL_FP_OR_C11_BUILD_RECIPE")
        opts = [token for token in tokens if re.fullmatch(r"-O(?:[0-3sgz]|fast)", token)]
        need(bool(opts) and opts[-1] == ("-O1" if identity["target"] == "sanitized" else "-O2"),
             "FROZEN_FINAL_OPTIMIZATION")
        if identity["target"] == "sanitized":
            need("-fsanitize=address,undefined" in tokens and "-fno-omit-frame-pointer" in tokens,
                 "SANITIZER_BUILD_RECIPE")
        object_path = tokens[tokens.index("-o") + 1]
        variant = ("library" if "CMakeFiles/audio_pipeline.dir/" in object_path else
                   "observed" if "CMakeFiles/fe09_b3_f0_observed.dir/" in object_path else
                   "plain" if "CMakeFiles/fe09_b3_f0_plain.dir/" in object_path else None)
        need(variant is not None, "UNREGISTERED_COMPILE_TARGET")
        macros = tuple(sorted(token for token in tokens if token.startswith("-D") and
                              not token.startswith("-DFE_B3_F0_OBSERVED=")))
        definitions[variant].add(macros)
        variant_files[variant].add(row["file"])
    need(all(len(v) == 1 for v in definitions.values()) and
         definitions["library"] == definitions["plain"] == definitions["observed"],
         "ACTUAL_PRIVATE_LAYOUT_DEFINITIONS_NOT_EQUAL")
    need(variant_files["plain"] == variant_files["observed"] and
         str(observed_root / HERE.relative_to(ROOT) / "fe09_b3_f0_composition.c") in variant_files["plain"] and
         str(observed_root / HERE.relative_to(ROOT) / "fe09_b3_f0_observer.c") in variant_files["plain"] and
         str(observed_root / "src/core/ap_pipeline.c") in variant_files["library"], "ACTUAL_TARGET_SOURCE_TOPOLOGY")
    links = read_json(directory / "link-recipes.json")
    wrapped = set(read_json(DOCS / "test-contract.json")["observation"]["wrapped_functions"])
    for variant in ("plain", "observed"):
        tokens = shlex.split(links[variant])
        need(tokens.count("public_sdk/libaudio_pipeline.a") == 1 and "-fno-lto" in tokens,
             "ACTUAL_IDENTICAL_STATIC_LIBRARY_LINK")
        actual = {t.split("=", 1)[1] for t in tokens if t.startswith("-Wl,--wrap=")}
        need(actual == (wrapped if variant == "observed" else set()), "ACTUAL_LINK_WRAPPER_SET")
    symbols = (directory / "observed-symbols.log").read_text()
    actual = set(re.findall(r"\b__wrap_(\w+)$", symbols, re.M))
    need(actual == wrapped, "ACTUAL_ELF_WRAPPER_SET")
    need(identity["unity"] is False and identity["ipo"] is False and
         identity["same_library_for_plain_and_observed"] is True, "ACTUAL_BUILD_TOPOLOGY")


def seal(output: Path) -> None:
    members = sorted(p for p in output.rglob("*") if p.is_file() and p.name != "SHA256SUMS")
    need(not any(p.is_symlink() for p in output.rglob("*")), "ARTIFACT_SYMLINK")
    total = sum(p.stat().st_size for p in members)
    need(total <= CAP - 65536, "METADATA_OUTPUT_CAP")
    (output / "SHA256SUMS").write_text("".join(
        f"{digest(p.read_bytes())}  {p.relative_to(output)}\n" for p in members))
    need(sum(p.stat().st_size for p in output.rglob("*") if p.is_file()) <= CAP,
         "SEALED_METADATA_OUTPUT_CAP")


def safe_closeout(output: Path, receipt: dict) -> bool:
    """Retain a bounded failure index if the complete evidence cannot be sealed.

    Overflow is moved intact to an explicitly reported local directory, never
    silently dropped or called a complete artifact.  A write failure propagates
    nonzero; a provisional/successful verdict is first revoked in memory.
    """
    try:
        write_json(output / "receipt.json", receipt)
        seal(output)
        return True
    except Exception as exc:
        original = receipt.get("failure")
        receipt.update(decision=FAILED, qualification=False,
                       complete_artifact_available=False,
                       failure={"type": type(exc).__name__, "reason": str(exc),
                                "phase": "bounded_artifact_closeout", "original_failure": original})
        overflow = Path(tempfile.mkdtemp(prefix="fe09-b3-f0-closeout-failure-"))
        index = []
        for path in sorted(output.rglob("*")):
            if path.is_file() and not path.is_symlink() and path.name != "receipt.json":
                relative = path.relative_to(output)
                destination = overflow / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                data = path.read_bytes()
                index.append({"member": str(relative), "bytes": len(data), "sha256": digest(data),
                              "retained_at": str(destination)})
                shutil.move(str(path), str(destination))
        receipt["retained_overflow_directory"] = str(overflow)
        write_json(output / "failure-member-index.json", index)
        write_json(output / "receipt.json", receipt)
        seal(output)
        return False


def collect(args: argparse.Namespace) -> int:
    global ACTIVE_BUDGET
    output = args.output.resolve()
    need(not output.exists(), "OUTPUT_EXISTS_NO_OVERWRITE_OR_AUTOMATIC_RETRY")
    output.mkdir(parents=True)
    receipt = {"schema_version": 1, "id": COLLECTOR_IDENTITY, "execution_source": args.execution_source,
               "source_role": ROLE, "decision": BLOCKED, "qualification": False,
               "requested_targets": args.targets, "target_order": [], "targets": {},
               "accepted_frames": 0, "setup_source_publications": 0,
               "promotion": PROMOTIONS, "failure": None,
               "recorded_at": dt.datetime.now(dt.timezone.utc).isoformat()}
    budget = None
    temporary = None
    current_raw = None
    current_attempt = None
    current_counted = False
    intended_decision = None
    try:
        budget = Budget(args.job_deadline_file)
        ACTIVE_BUDGET = budget
        receipt["source"] = source_preflight(args.execution_source)
        receipt["qualified_predecessor"] = baseline_preflight(args.execution_source)
        receipt["context"] = event_context()
        cmake = shutil.which(args.cmake)
        if not cmake:
            raise ExecutionBlocked("CMAKE_REQUIRED_TOOL_MISSING")
        for tool in ("readelf", "nm"):
            if not shutil.which(tool):
                raise ExecutionBlocked("REQUIRED_BUILD_INSPECTION_TOOL:" + tool)
        temporary = Path(tempfile.mkdtemp(prefix="fe09-b3-f0-"))
        # Preflight all requested execution tools before starting any DSP.
        for target in args.targets:
            tools = ("arm-linux-gnueabihf-gcc", "qemu-arm") if target == "arm" else ("cc",)
            if any(shutil.which(tool) is None for tool in tools):
                raise ExecutionBlocked("REQUIRED_TARGET_TOOL_MISSING:" + target)
        budget.command([cmake, "--version"], output / "cmake.log", 10)
        all_coverage = True
        semantics = None
        for target in args.targets:
            build, identity = build_target(target, temporary, output, budget, cmake)
            execution_started = time.monotonic()
            cap = {"native": 120, "sanitized": 180, "arm": 300}[target]
            prefix = ["qemu-arm", "-L", "/usr/arm-linux-gnueabihf"] if target == "arm" else []
            env = os.environ.copy()
            if target == "sanitized":
                env.update(ASAN_OPTIONS="detect_leaks=1:abort_on_error=1", UBSAN_OPTIONS="halt_on_error=1")
            fixture = temporary / (target + "-fixture")
            budget.command(prefix + [str(build / "fe09_b3_f0_plain"), "--fixture-only", str(fixture)],
                           output / target / "fixture.log", min(10, cap), env)
            inputs = fixed_inputs(fixture)
            cases = {}
            target_receipt = {"build": identity, "completed_cases": [], "status": "IN_PROGRESS"}
            target_receipt["execution_budget"] = {"limit_seconds": cap,
                "started_offset_seconds": execution_started - budget.started, "elapsed_seconds": None}
            receipt["targets"][target] = target_receipt
            receipt["target_order"].append(target)
            for spec in schedule():
                current_raw = temporary / (target + "-" + spec["name"])
                current_attempt = {"target": target, "spec": spec}
                current_counted = False
                binary = build / ("fe09_b3_f0_observed" if spec["observed"] else "fe09_b3_f0_plain")
                command = prefix + [str(binary), "--case", spec["case"], "--mode", spec["mode"],
                                   "--future", str(int(spec["future"])), "--negatives", str(int(spec["negatives"])),
                                   "--output", str(current_raw)]
                remaining_target = cap - (time.monotonic() - execution_started)
                status = budget.command(command, output / target / (spec["name"] + ".log"),
                                        remaining_target, env, (0, 3))
                case = load_case(current_raw, spec)
                # Preserve complete actual evidence before evaluating acceptance.
                retain_case(output / target / spec["name"], case)
                receipt["accepted_frames"] += case["result"]["frames"]
                receipt["setup_source_publications"] += case["result"]["counters"]["setup_source_publications"]
                current_counted = True
                reached = validate_case(case, spec, inputs)
                need(status == (0 if reached else 3), "EXIT_STATUS_COVERAGE_MISMATCH")
                cases[spec["name"]] = case
                target_receipt["completed_cases"].append(spec["name"])
                current_raw = None
                current_attempt = None
                budget.remaining()
            witness = validate_suite(cases, inputs)
            target_elapsed = time.monotonic() - execution_started
            if target_elapsed > cap:
                raise ExecutionBlocked("FROZEN_TARGET_TOTAL_EXECUTION_BUDGET:" + target)
            target_receipt["execution_budget"]["elapsed_seconds"] = target_elapsed
            target_receipt.update(status="COMPLETE", witness=witness,
                                  case_members={name: digest(canonical({"result": c["result"], "streams": c["streams"]}))
                                                for name, c in cases.items()})
            all_coverage = all_coverage and witness["all_fixed_coverage_reached"]
            if semantics is None:
                semantics = eight_semantic_negatives(cases, inputs)
                write_json(output / "semantic-negatives.json", semantics)
            budget.remaining()
        need(receipt["accepted_frames"] == 6600 * len(args.targets) and
             receipt["setup_source_publications"] == 5 * len(args.targets), "INVOCATION_ACTUAL_BUDGET")
        intended_decision = (QUALIFIED if args.targets == list(TARGETS) else LOCAL) if all_coverage else INCONCLUSIVE
        receipt["decision"] = "FINAL_VALIDATION_PENDING"
        receipt["qualification"] = False
        receipt["semantic_mutation_count"] = len(semantics or [])
        receipt["actual_api_rejections"] = 16 * len(args.targets)
        budget.remaining()
    except Exception as exc:  # Preserve original failure and completed work; never retry.
        receipt["decision"] = BLOCKED if isinstance(exc, ExecutionBlocked) else FAILED
        receipt["failure"] = {"type": type(exc).__name__, "reason": str(exc)}
        if current_attempt:
            receipt["failed_attempt"] = current_attempt
            receipt["failed_attempt_already_counted"] = current_counted
            receipt["failed_attempt_consumed_registered_slot"] = True
            receipt["failed_attempt_count_status"] = "UNKNOWN_NO_VALID_RESULT"
        if current_raw and current_raw.exists():
            failure_dir = output / "failure-current-attempt"
            failure_dir.mkdir()
            for path in sorted(current_raw.iterdir()):
                if path.is_file() and not path.is_symlink():
                    need(path.stat().st_size <= 4 * 1024 * 1024, "FAILURE_WITNESS_SIZE")
                    shutil.copyfile(path, failure_dir / path.name)
            if (current_raw / "result.json").is_file():
                failed = read_json(current_raw / "result.json", 65536)
                receipt["failed_attempt_actual_counts"] = failed.get("counters")
                receipt["failed_attempt_observed_state"] = {
                    k: failed.get(k) for k in ("attempted_frame", "failed_frame", "failed_negative",
                                                "failure_phase", "failure_state", "failed_observation")}
                receipt["failed_attempt"] = current_attempt
                receipt["failed_attempt_already_counted"] = current_counted
                if not current_counted:
                    frames_path = current_raw / "frames.jsonl"
                    prefix = len(frames_path.read_bytes().splitlines()) if frames_path.is_file() else 0
                    actual = failed.get("counters", {})
                    if (integer(actual.get("accepted"), 0, 600) and actual["accepted"] == prefix and
                            integer(actual.get("setup_source_publications"), 0, 5)):
                        receipt["accepted_frames"] += actual["accepted"]
                        receipt["setup_source_publications"] += actual["setup_source_publications"]
                        receipt["failed_attempt_prefix_counted"] = True
                        receipt["failed_attempt_count_status"] = "REPORTED_COMPLETED_PREFIX_MATCHES_RETAINED_ROWS"
                elif current_counted:
                    receipt["failed_attempt_count_status"] = "ALREADY_COUNTED_COMPLETE_RAW_CASE"
        receipt["qualification"] = False
    finally:
        if budget:
            receipt["budget"] = budget.record()
        if temporary:
            receipt["local_scratch_for_reproduction"] = str(temporary)
        safe_closeout(output, receipt)
    # This metadata readback is part of the same monotonic 300s stage.  A late
    # verification or timeout failure MUST replace the provisional verdict.
    if receipt["failure"] is None:
        try:
            verify(output, args.execution_source, require_full=args.targets == list(TARGETS), finalizing=True)
            if budget:
                budget.remaining()
                receipt["budget"] = budget.record()
            receipt["decision"] = intended_decision
            receipt["qualification"] = intended_decision == QUALIFIED
        except Exception as exc:
            receipt["decision"] = BLOCKED if isinstance(exc, ExecutionBlocked) else FAILED
            receipt["qualification"] = False
            receipt["failure"] = {"type": type(exc).__name__, "reason": str(exc),
                                  "phase": "final_readback_and_frozen_deadline"}
            if budget:
                receipt["budget"] = budget.record()
        finally:
            safe_closeout(output, receipt)
        # Include the successful seal itself in the deadline decision. Failure
        # closeout uses the already reserved archive time and can never promote.
        if receipt["failure"] is None and budget:
            try:
                budget.remaining()
                receipt["budget"] = budget.record()
            except Exception as exc:
                receipt.update(decision=BLOCKED, qualification=False,
                    failure={"type": type(exc).__name__, "reason": str(exc),
                             "phase": "post_seal_total_deadline"}, budget=budget.record())
            safe_closeout(output, receipt)
    ACTIVE_BUDGET = None
    print(receipt["decision"], "accepted_frames=" + str(receipt["accepted_frames"]))
    return 0 if receipt["decision"] in (QUALIFIED, LOCAL) else (3 if receipt["decision"] == INCONCLUSIVE else 2)


def verify(output: Path, execution_source: str, require_full: bool = True,
           finalizing: bool = False) -> dict:
    need(output.is_dir() and not output.is_symlink(), "ARTIFACT_DIRECTORY")
    files = sorted(p for p in output.rglob("*") if p.is_file())
    need(not any(p.is_symlink() for p in output.rglob("*")), "ARTIFACT_SYMLINK")
    need(sum(p.stat().st_size for p in files) <= CAP, "ARTIFACT_CAP")
    expected = {str(p.relative_to(output)): digest(p.read_bytes()) for p in files if p.name != "SHA256SUMS"}
    manifest = {}
    for line in (output / "SHA256SUMS").read_text().splitlines():
        need(len(line) > 66 and line[64:66] == "  ", "MANIFEST_SCHEMA")
        sha, name = line[:64], line[66:]
        need(name not in manifest and not Path(name).is_absolute() and ".." not in Path(name).parts,
             "MANIFEST_PATH_OR_DUPLICATE")
        manifest[name] = sha
    need(manifest == expected, "RETAINED_MEMBER_SET_OR_BYTES")
    r = read_json(output / "receipt.json")
    validate_collector_identity(r, execution_source)
    source = source_preflight(execution_source)
    need(r["source"] == source and r["qualified_predecessor"] == baseline_preflight(execution_source),
         "RETAINED_ACTUAL_SOURCE_BINDING")
    targets = r["requested_targets"]
    need(type(targets) is list and targets and len(set(targets)) == len(targets) and
         targets == [t for t in TARGETS if t in targets] and r["target_order"] == targets,
         "RETAINED_TARGET_ORDER")
    need(not require_full or targets == list(TARGETS), "PARTIAL_TARGETS_CANNOT_QUALIFY")
    need(r["failure"] is None and set(r["targets"]) == set(targets), "RETAINED_INCOMPLETE_INVOCATION")
    inputs = literal_inputs()
    recomputed_negatives = None
    all_coverage = True
    for target in targets:
        cases = {}
        for spec in schedule():
            directory = output / target / spec["name"]
            compressed = (directory / "frames.jsonl.gz").read_bytes()
            with gzip.GzipFile(fileobj=io.BytesIO(compressed)) as stream:
                data = stream.read(4 * 1024 * 1024 + 1)
            need(len(data) <= 4 * 1024 * 1024, "DECOMPRESSED_METADATA_CAP")
            cases[spec["name"]] = {"result": read_json(directory / "result.json", 65536),
                                   "frames": [loads(line) for line in data.splitlines()],
                                   "streams": read_json(directory / "streams.json", 256 * 1024)}
        witness = validate_suite(cases, inputs)
        target_record = r["targets"][target]
        need(target_record["witness"] == witness and target_record["status"] == "COMPLETE" and
             target_record["completed_cases"] == [s["name"] for s in schedule()], "RETAINED_RECOMPUTED_WITNESS")
        target_budget = target_record["execution_budget"]
        need(target_budget["limit_seconds"] == {"native": 120, "sanitized": 180, "arm": 300}[target] and
             0 < target_budget["elapsed_seconds"] <= target_budget["limit_seconds"] and
             target_budget["started_offset_seconds"] >= 0, "RETAINED_TARGET_TOTAL_BUDGET")
        need(target_record["case_members"] == {name: digest(canonical({"result": c["result"], "streams": c["streams"]}))
                                              for name, c in cases.items()}, "RETAINED_CASE_IDENTITY")
        b = target_record["build"]
        validate_build_evidence(output / target / "build", b)
        if recomputed_negatives is None:
            recomputed_negatives = eight_semantic_negatives(cases, inputs)
        all_coverage = all_coverage and witness["all_fixed_coverage_reached"]
    negatives = read_json(output / "semantic-negatives.json", 65536)
    need([n["id"] for n in negatives] == [f"S{i:02d}" for i in range(1, 9)] and
         all(n["rejected"] is True and n["resealed_canonical_evidence"] is True and
             n["additional_DSP_frames"] == 0 for n in negatives), "RETAINED_SEMANTIC_NEGATIVES")
    need(negatives == recomputed_negatives, "RECOMPUTED_SEMANTIC_NEGATIVE_RESULTS")
    expected_decision = (QUALIFIED if targets == list(TARGETS) else LOCAL) if all_coverage else INCONCLUSIVE
    need(r["decision"] == ("FINAL_VALIDATION_PENDING" if finalizing else expected_decision) and
         r["qualification"] is (False if finalizing else expected_decision == QUALIFIED) and
         r["accepted_frames"] == len(targets) * 6600 and r["setup_source_publications"] == len(targets) * 5 and
         r["actual_api_rejections"] == len(targets) * 16 and r["semantic_mutation_count"] == 8,
         "RETAINED_VERDICT_OR_BUDGET")
    validate_retained_budget(r["budget"])
    return r


def self_test() -> None:
    # Parser/admission tests only: no compilation or DSP and no fake success evidence.
    for bad in ('{"x":1,"x":2}', '{"x":NaN}', '{"x":Infinity}'):
        try:
            loads(bad)
        except Rejected:
            pass
        else:
            raise Rejected("STRICT_JSON_NEGATIVE_ACCEPTED")
    need(len(schedule()) == 11 and sum(x["negatives"] for x in schedule()) == 1,
         "REGISTERED_SCHEDULE")
    need(fnv(b"") == "cbf29ce484222325" and not integer(True), "PRIMITIVE_TYPE_OR_HASH")
    need(digest((DOCS / "test-contract.json").read_bytes()) == CONTRACT_SHA and
         digest((DOCS / "source-lock.json").read_bytes()) == LOCK_SHA, "PREREGISTRATION_DRIFT")
    need(digest((HERE / "fe09_b3_f0_qualification.py").read_bytes()) ==
         ORIGINAL_COLLECTOR_SHA and
         digest((REPAIR_DOCS / "PREREGISTRATION.json").read_bytes()) ==
         REPAIR_CONTRACT_SHA, "REPAIR_SOURCE_OR_REGISTRATION_DRIFT")
    forward_source.self_test()
    print("FE09_B3_F0_FORWARD_SOURCE_R4_PARSER_AND_FROZEN_SCHEDULE_SELF_TEST_NO_DSP")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--collect", action="store_true")
    action.add_argument("--verify", action="store_true")
    action.add_argument("--self-test", action="store_true")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--execution-source")
    parser.add_argument("--targets", default="native,sanitized,arm")
    parser.add_argument("--cmake", default="cmake")
    parser.add_argument("--job-deadline-file", default=os.environ.get("FE_FRONTEND_JOB_DEADLINE_FILE"))
    args = parser.parse_args()
    try:
        if args.self_test:
            self_test()
            return 0
        need(args.output is not None and args.execution_source is not None, "OUTPUT_AND_SOURCE_REQUIRED")
        args.targets = args.targets.split(",")
        need(args.targets and args.targets == [t for t in TARGETS if t in args.targets], "TARGET_SELECTION")
        if args.collect:
            return collect(args)
        result = verify(args.output, args.execution_source, require_full=args.targets == list(TARGETS))
        print("FE09_B3_F0_R4_RETAINED_SOURCE_SEMANTICS_VERIFIED", result["decision"])
        return 0 if result["decision"] in (QUALIFIED, LOCAL) else 3
    except Exception as exc:
        print(type(exc).__name__ + ": " + str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
