#!/usr/bin/env python3
"""Bind the exact DUT soak to observed monotonic duration and frame count.

This is protected-main workflow control evidence, not code shipped in the
immutable product release or a substitute for real target execution.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sys

MAX_BYTES = 1048576
MAX_RAW = 131072
OID = re.compile(r"[0-9a-f]{40}\Z")
STATUS = "PRODUCT_SOAK_OBSERVED_REAL_DURATION_BOUND"
SOURCE = "protected-main-control-plane-not-original-release-collector"


class Rejected(ValueError):
    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


def need(ok: bool, reason: str) -> None:
    if not ok:
        raise Rejected(reason)


def pairs(rows):
    values = {}
    for key, value in rows:
        need(key not in values, "SOAK_DUPLICATE_JSON_KEY")
        values[key] = value
    return values


def finite_number(token):
    number = float(token)
    need(math.isfinite(number), "SOAK_NONFINITE_JSON")
    return number


def constant(_token):
    raise Rejected("SOAK_NONFINITE_JSON")


def decode(raw: bytes) -> dict:
    need(type(raw) is bytes and 0 < len(raw) <= MAX_BYTES, "SOAK_INPUT_BYTES_BOUND")
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=pairs,
                           parse_constant=constant, parse_float=finite_number)
    except (UnicodeError, json.JSONDecodeError, RecursionError, OverflowError,
            ValueError) as exc:
        if isinstance(exc, Rejected):
            raise
        raise Rejected("SOAK_INVALID_JSON") from exc
    need(type(value) is dict, "SOAK_INVALID_ROOT")
    return value


def counter(raw: str, name: str) -> int:
    need(type(raw) is str and len(raw) <= MAX_RAW, "SOAK_RAW_COUNTER_BOUND")
    pattern = r"(?<![A-Za-z0-9_])" + re.escape(name) + r"=([0-9]+)(?![A-Za-z0-9_])"
    found = re.findall(pattern, raw)
    need(len(found) == 1 and len(found[0]) <= 16,
         "SOAK_COUNTER_MISSING_DUPLICATE_OR_INVALID")
    return int(found[0])


def observe(raw: bytes, seconds: int, start_ns: int, end_ns: int,
            control_sha: str, release_source_sha: str) -> dict:
    need(type(seconds) is int and 0 < seconds <= 42949672,
         "SOAK_INVALID_REQUESTED_SECONDS")
    need(type(start_ns) is int and type(end_ns) is int and
         0 < start_ns < end_ns, "SOAK_INVALID_MONOTONIC_CLOCK")
    need(type(control_sha) is str and OID.fullmatch(control_sha) is not None and
         type(release_source_sha) is str and
         OID.fullmatch(release_source_sha) is not None,
         "SOAK_SOURCE_IDENTITY_INVALID")
    document = decode(raw)
    need(document.get("schema_version") == 1 and
         document.get("kind") == "alsa-route-soak" and
         document.get("collector_version") == "2.1" and
         type(document.get("returncode")) is int and
         document["returncode"] == 0, "SOAK_ORIGINAL_COLLECTOR_IDENTITY_OR_RESULT")
    soak = document.get("soak")
    need(type(soak) is dict and soak.get("passed") is True,
         "SOAK_ORIGINAL_RESULT_NOT_PASS")
    need("duration_observation" not in document and
         "requested_hours" not in soak and "requested_seconds" not in soak,
         "SOAK_OBSERVATION_ALREADY_PRESENT")
    requested_hours = soak.get("hours")
    need(type(requested_hours) in (int, float) and
         math.isfinite(requested_hours) and
         abs(float(requested_hours) - seconds / 3600.0) <= 1e-9,
         "SOAK_ORIGINAL_REQUESTED_DURATION_DRIFT")
    observation_ns = end_ns - start_ns
    need(observation_ns >= seconds * 1000000000,
         "SOAK_OBSERVED_DURATION_TOO_SHORT")
    raw_text = document.get("raw")
    produced = counter(raw_text, "produced")
    received = counter(raw_text, "received")
    expected_frames = seconds * 100
    need(produced == expected_frames and received == expected_frames,
         "SOAK_FRAME_COUNT_INCOMPLETE_OR_DRIFT")
    profile = document.get("fault_injection")
    need(type(profile) is dict and profile.get("profile") == "none",
         "SOAK_NOMINAL_FAULT_PROFILE_REQUIRED")
    observation = {
        "schema_version": 1,
        "status": STATUS,
        "source": SOURCE,
        "control_plane_sha": control_sha,
        "release_source_sha": release_source_sha,
        "original_collector_json_sha256": hashlib.sha256(raw).hexdigest(),
        "requested_seconds": seconds,
        "requested_hours": float(requested_hours),
        "monotonic_start_ns": start_ns,
        "monotonic_end_ns": end_ns,
        "observed_elapsed_ns": observation_ns,
        "observed_elapsed_seconds": observation_ns / 1000000000.0,
        "expected_frames": expected_frames,
        "produced_frames": produced,
        "received_frames": received,
        "real_hardware_run_claimed_by_this_helper": False,
    }
    document["duration_observation"] = observation
    soak["requested_seconds"] = seconds
    soak["requested_hours"] = float(requested_hours)
    soak["hours"] = observation_ns / 3600000000000.0
    return document


def write_observation(path: Path, seconds: int, start_ns: int, end_ns: int,
                      control_sha: str, release_source_sha: str) -> dict:
    need(not path.is_symlink() and path.is_file() and
         0 < path.stat().st_size <= MAX_BYTES,
         "SOAK_ORIGINAL_FILE_UNAVAILABLE_OR_OVERSIZE")
    raw = path.read_bytes()
    document = observe(raw, seconds, start_ns, end_ns,
                       control_sha, release_source_sha)
    encoded = (json.dumps(document, sort_keys=True, indent=2,
                          allow_nan=False, ensure_ascii=False) + "\n").encode("utf-8")
    need(len(encoded) <= MAX_BYTES + 8192, "SOAK_ENRICHED_EVIDENCE_OVERSIZE")
    temp = path.with_name(path.name + ".duration-guard-" + str(os.getpid()))
    fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(encoded)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp, path)
    finally:
        if temp.exists():
            temp.unlink()
    need(path.read_bytes() == encoded, "SOAK_WRITE_READBACK_FAILED")
    return document["duration_observation"]


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--soak-json", type=Path, required=True)
    parser.add_argument("--requested-seconds", type=int, required=True)
    parser.add_argument("--start-ns", type=int, required=True)
    parser.add_argument("--end-ns", type=int, required=True)
    parser.add_argument("--control-sha", required=True)
    parser.add_argument("--release-source-sha", required=True)
    args = parser.parse_args(argv)
    try:
        observed = write_observation(args.soak_json, args.requested_seconds,
                                     args.start_ns, args.end_ns,
                                     args.control_sha, args.release_source_sha)
    except (Rejected, OSError, OverflowError, TypeError) as exc:
        print("SOAK_DURATION_GUARD_REJECTED:" +
              (exc.reason if isinstance(exc, Rejected) else type(exc).__name__),
              file=sys.stderr)
        return 2
    print(json.dumps(observed, sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
