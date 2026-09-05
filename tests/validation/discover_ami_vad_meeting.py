#!/usr/bin/env python3
"""Run the existing hash-bound AMI VAD discovery for one explicit meeting.

This is a release-neutral research wrapper. It deliberately reuses the exact
ES2003a discovery implementation and only replaces the meeting token before any
network access, so the window-selection and hash-binding policy cannot drift.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import discover_ami_vad_microset as base

MEETING_RE = re.compile(r"^[A-Z]{2}[0-9]{4}[a-z]$")


def configure_meeting(meeting: str) -> None:
    if not MEETING_RE.fullmatch(meeting):
        raise ValueError(f"invalid AMI meeting token: {meeting!r}")
    base.MEETING = meeting
    base.OFFICIAL_AUDIO = (
        "https://groups.inf.ed.ac.uk/ami/AMICorpusMirror/amicorpus/"
        f"{meeting}/audio/{meeting}.Mix-Headset.wav"
    )


def run(meeting: str, output: Path) -> dict:
    configure_meeting(meeting)
    result = base.discover()
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
