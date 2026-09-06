#!/usr/bin/env python3
"""I005 AMI source-admission wrapper around the existing hash/range discovery tool.

This performs source identity discovery only. It does not build or execute the
shipping VAD, compare thresholds, tune hangover, select a candidate, consume
confirmation data, or create promotion authority.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import discover_ami_vad_microset as discovery

PROHIBITED_MEETINGS = {"ES2003a", "ES2004a"}
MEETING_RE = re.compile(r"^[A-Z]{2}[0-9]{4}[a-z]$")


def require(ok: bool, message: str) -> None:
    if not ok:
        raise ValueError(message)


def validate_meeting(meeting: str) -> str:
    require(MEETING_RE.fullmatch(meeting) is not None, "invalid AMI meeting id")
    require(meeting not in PROHIBITED_MEETINGS, "meeting is already exposed/retired")
    return meeting


def configure_discovery(meeting: str) -> None:
    meeting = validate_meeting(meeting)
    discovery.MEETING = meeting
    discovery.OFFICIAL_AUDIO = (
        "https://groups.inf.ed.ac.uk/ami/AMICorpusMirror/amicorpus/"
        f"{meeting}/audio/{meeting}.Mix-Headset.wav"
    )


def discover_source(meeting: str) -> dict:
    configure_discovery(meeting)
    result = discovery.discover()
    require(result["dataset"]["meeting"] == meeting, "discovery meeting drift")
    return {
        "schema_version": 1,
        "iteration_id": "I005",
        "authority": "public-source-admission-discovery-only",
        "candidate_limit": 0,
        "confirmation_limit": 0,
        "promotion_allowed": False,
        "selected_role": "development",
        "prohibited_meetings": sorted(PROHIBITED_MEETINGS),
        "discovery": result,
        "candidate_decision": "NOT_AN_ACOUSTIC_CANDIDATE",
        "product_qualification": "DEFERRED_BY_SCOPE",
    }


def self_test() -> None:
    assert validate_meeting("ES2005b") == "ES2005b"
    for bad in ("ES2003a", "ES2004a", "ES2005", "es2005b", "../ES2005b"):
        try:
            validate_meeting(bad)
        except ValueError:
            pass
        else:
            raise AssertionError(f"invalid/prohibited meeting accepted: {bad}")
    old_meeting = discovery.MEETING
    old_audio = discovery.OFFICIAL_AUDIO
    try:
        configure_discovery("ES2005b")
        assert discovery.MEETING == "ES2005b"
        assert "/ES2005b/audio/ES2005b.Mix-Headset.wav" in discovery.OFFICIAL_AUDIO
    finally:
        discovery.MEETING = old_meeting
        discovery.OFFICIAL_AUDIO = old_audio
    print("I005 AMI source-admission wrapper self-test: OK")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--meeting", default="ES2005b")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    if args.output is None:
        parser.error("--output is required")
    result = discover_source(args.meeting)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    d = result["discovery"]
    print(json.dumps({
        "meeting": d["dataset"]["meeting"],
        "license": d["dataset"]["license"],
        "audio_lfs_sha256": d["audio"]["lfs_sha256"],
        "annotation_files": len(d["annotations"]["files"]),
        "duration_s": d["audio"]["duration_s"],
        "windows": [
            {
                "window_id": item["window_id"],
                "start_s": item["start_s"],
                "activity_fraction": item["activity_fraction"],
                "sha256": item["audio_range"]["sha256"],
            }
            for item in d["window_plan"]
        ],
        "candidate_limit": 0,
        "confirmation_limit": 0,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, OSError) as exc:
        raise SystemExit(f"I005 AMI source admission error: {exc}")
