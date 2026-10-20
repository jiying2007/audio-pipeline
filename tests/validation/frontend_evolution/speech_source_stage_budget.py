#!/usr/bin/env python3
"""Bounded FIRST-PARTY official speech-source stage with durable failure marker.

No alternate speech URL, source substitution, synthetic fallback or quality gate
waiver. The job's outer timeout must exceed this stage's hard budget enough for
real acoustic evaluation AND failure Artifact upload.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

import speech_source

HERE = Path(__file__).resolve().parent
SOURCE_PROGRAM = HERE / "speech_source.py"
DEADLINE_SECONDS = 30 * 60  # Below quality.yml frontend-speech job: 45m.
REASON_TIMEOUT = "OFFICIAL_SPEECH_STAGE_WALL_DEADLINE"
REASON_CHILD = "OFFICIAL_SPEECH_STAGE_CHILD_FAILURE"
REASON_MISSING = "OFFICIAL_SPEECH_SOURCE_RECEIPT_MISSING"


def preserve_failure(output: Path, *, reason: str, deadline: float,
                     elapsed: float, exit_code: int | None) -> bool:
    """Write only a small *negative* receipt. Never replace source's own one."""
    if output.is_symlink():
        return False
    try:
        output.mkdir(parents=True, exist_ok=True)
        marker = output / "source-failure.json"
        if marker.is_symlink():
            return False
        if marker.exists():
            return marker.is_file() and 0 < marker.stat().st_size <= 65536
        receipt = {
            "schema_version": 1,
            "status": "DATA_OR_INFRASTRUCTURE_FAILURE",
            "reason_code": reason,
            "source_url": speech_source.URL,
            "expected_archive_md5": speech_source.MD5,
            "transport_attempt_ceiling": speech_source.MAX_TRANSPORT_ATTEMPTS,
            "stage_wall_seconds_ceiling": int(deadline),
            "elapsed_seconds_ceiling_observed": int(elapsed) + 1,
            "worker_exit_code": exit_code,
            "source_substitution": False,
            "shipping_authority": False,
            "acoustic_validation_qualified": False,
        }
        # Strictly create-only; never overwrite real data/previous failure.
        with marker.open("x", encoding="utf-8") as stream:
            json.dump(receipt, stream, sort_keys=True, separators=(",", ":"),
                      allow_nan=False)
            stream.write("\n")
        return marker.stat().st_size <= 65536
    except (OSError, ValueError):
        return False


def _terminate_process_group(proc: subprocess.Popen) -> None:
    """Source downloader and any FFmpeg subprocess share the new process group."""
    try:
        os.killpg(proc.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    try:
        proc.wait(timeout=5)
        return
    except subprocess.TimeoutExpired:
        pass
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        raise RuntimeError("source worker could not be reaped after SIGKILL")


def run_bounded(argv: list[str], output: Path, deadline: float, *,
                cwd: Path | None = None,
                env: dict[str, str] | None = None) -> bool:
    """Execute exact command with bounded wait and fail-closed artifact marker.

    argv injection exists only for offline unit testing: CLI calls the
    hard-coded first-party source program with the single pinned official URL.
    """
    if output.exists() or output.is_symlink():
        raise ValueError("speech source output must be fresh, no overwrite")
    if not 0 < deadline <= 2400:
        raise ValueError("speech source stage deadline outside finite budget")
    started = time.monotonic()
    proc = subprocess.Popen(argv, cwd=cwd, env=env, start_new_session=True)
    try:
        code = proc.wait(timeout=deadline)
    except subprocess.TimeoutExpired:
        _terminate_process_group(proc)
        elapsed = time.monotonic() - started
        saved = preserve_failure(output, reason=REASON_TIMEOUT,
                                 deadline=deadline, elapsed=elapsed,
                                 exit_code=None)
        print("OFFICIAL_SPEECH_STAGE_TIMEOUT_FAIL_CLOSED "
              f"failure_marker={int(saved)}", file=sys.stderr)
        return False
    elapsed = time.monotonic() - started
    if code:
        saved = preserve_failure(output, reason=REASON_CHILD,
                                 deadline=deadline, elapsed=elapsed,
                                 exit_code=code)
        print("OFFICIAL_SPEECH_STAGE_CHILD_FAILED "
              f"exit={code} failure_marker={int(saved)}", file=sys.stderr)
        return False
    receipt = output / "source-receipt.json"
    failure = output / "source-failure.json"
    if (not receipt.is_file() or receipt.is_symlink() or
        not 0 < receipt.stat().st_size <= 1048576 or
        failure.exists() or failure.is_symlink()):
        saved = preserve_failure(output, reason=REASON_MISSING,
                                 deadline=deadline, elapsed=elapsed,
                                 exit_code=code)
        print("OFFICIAL_SPEECH_STAGE_MISSING_SUCCESS_RECEIPT "
              f"failure_marker={int(saved)}", file=sys.stderr)
        return False
    print("OFFICIAL_SPEECH_STAGE_SUCCESS_SOURCE_RECEIPT_RETAINED")
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--stage-budget-seconds", type=int,
                        default=DEADLINE_SECONDS)
    args = parser.parse_args()
    if not 60 <= args.stage_budget_seconds <= DEADLINE_SECONDS:
        raise SystemExit("SOURCE_STAGE_BUDGET_OUT_OF_PREREGISTERED_BOUNDS")
    cmd = [sys.executable, str(SOURCE_PROGRAM), "--output", str(args.output)]
    if not run_bounded(cmd, args.output, float(args.stage_budget_seconds),
                       cwd=HERE.parents[2]):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
