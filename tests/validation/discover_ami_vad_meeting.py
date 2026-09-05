#!/usr/bin/env python3
"""Run the existing hash-bound AMI VAD discovery for one explicit meeting.

This is a release-neutral research wrapper. It deliberately reuses the exact
ES2003a discovery implementation and only replaces the meeting token before any
network access, so the window-selection and hash-binding policy cannot drift.
Transient mirror throttling is handled with bounded retries; integrity failures
remain fail-closed.
"""

from __future__ import annotations

import argparse
import json
import re
import time
import urllib.error
from pathlib import Path

import discover_ami_vad_microset as base

MEETING_RE = re.compile(r"^[A-Z]{2}[0-9]{4}[a-z]$")
RETRYABLE_HTTP_STATUS = {429, 500, 502, 503, 504}
MAX_ATTEMPTS = 5
_BASE_REQUEST_BYTES = base.request_bytes


def configure_meeting(meeting: str) -> None:
    if not MEETING_RE.fullmatch(meeting):
        raise ValueError(f"invalid AMI meeting token: {meeting!r}")
    base.MEETING = meeting
    base.OFFICIAL_AUDIO = (
        "https://groups.inf.ed.ac.uk/ami/AMICorpusMirror/amicorpus/"
        f"{meeting}/audio/{meeting}.Mix-Headset.wav"
    )


def _retry_delay_seconds(error: urllib.error.HTTPError, attempt: int) -> float:
    raw = error.headers.get("Retry-After") if error.headers is not None else None
    if raw:
        try:
            value = float(raw)
            if value >= 0.0:
                return min(max(value, 0.25), 8.0)
        except ValueError:
            pass
    return min(float(1 << attempt), 8.0)


def retrying_request_bytes(url: str, *, max_bytes: int,
                           headers: dict[str, str] | None = None):
    last_error: urllib.error.HTTPError | None = None
    for attempt in range(MAX_ATTEMPTS):
        try:
            return _BASE_REQUEST_BYTES(url, max_bytes=max_bytes, headers=headers)
        except urllib.error.HTTPError as error:
            last_error = error
            if error.code not in RETRYABLE_HTTP_STATUS or attempt + 1 >= MAX_ATTEMPTS:
                raise
            time.sleep(_retry_delay_seconds(error, attempt))
    assert last_error is not None
    raise last_error


def run(meeting: str, output: Path) -> dict:
    configure_meeting(meeting)
    original_request = base.request_bytes
    base.request_bytes = retrying_request_bytes
    try:
        result = base.discover()
    finally:
        base.request_bytes = original_request
    if result["dataset"]["meeting"] != meeting:
        raise ValueError("discovery meeting mismatch")
    if not all(item["window_id"].startswith(meeting + "-w") for item in result["window_plan"]):
        raise ValueError("window ids are not bound to requested meeting")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result


def self_test() -> None:
    original_meeting = base.MEETING
    original_audio = base.OFFICIAL_AUDIO
    try:
        configure_meeting("ES2004a")
        assert base.MEETING == "ES2004a"
        assert base.OFFICIAL_AUDIO.endswith("/ES2004a/audio/ES2004a.Mix-Headset.wav")
        try:
            configure_meeting("../bad")
            raise AssertionError("invalid meeting token was accepted")
        except ValueError:
            pass
        fake = urllib.error.HTTPError(
            "https://example.invalid", 429, "rate limited", {"Retry-After": "0.5"}, None
        )
        assert abs(_retry_delay_seconds(fake, 0) - 0.5) < 1.0e-9
        fake_no_header = urllib.error.HTTPError(
            "https://example.invalid", 503, "busy", {}, None
        )
        assert _retry_delay_seconds(fake_no_header, 0) == 1.0
        assert _retry_delay_seconds(fake_no_header, 4) == 8.0
    finally:
        base.MEETING = original_meeting
        base.OFFICIAL_AUDIO = original_audio
    print("AMI meeting discovery wrapper self-test: OK")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--meeting", required=False, default="ES2003a")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    if args.output is None:
        parser.error("--output is required")
    result = run(args.meeting, args.output)
    print(json.dumps({
        "meeting": result["dataset"]["meeting"],
        "audio_object": {
            "lfs_sha256": result["audio"]["lfs_sha256"],
            "tree_object_id": result["audio"]["tree_object_id"],
            "xet_hash": result["audio"]["xet_hash"],
        },
        "duration_s": result["audio"]["duration_s"],
        "annotation_files": len(result["annotations"]["files"]),
        "windows": [
            {
                "window_id": item["window_id"],
                "start_s": item["start_s"],
                "activity_fraction": item["activity_fraction"],
                "sha256": item["audio_range"]["sha256"],
            }
            for item in result["window_plan"]
        ],
        "range_supported": result["audio"]["range_supported"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
