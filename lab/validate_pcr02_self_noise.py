#!/usr/bin/env python3
"""Validate PCR02 self-noise capture manifests and bind referenced files by SHA-256.

Example manifests are documentation only and are rejected by default. Real evidence
must use monotonic nanosecond timestamps, dual-mic audio, render reference, telemetry,
and the minimum motor/FOC/PWM signal set required to correlate robot motion with audio.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import tempfile
from pathlib import Path

MOTION_CLASSES = {
    "idle", "speaker-only", "near-speech", "double-talk", "straight",
    "turning", "acceleration", "braking", "servo", "floor-transition",
}
REQUIRED_SIGNALS = {
    "timestamp_ns", "left_motor_rpm", "right_motor_rpm", "left_foc_iq",
    "right_foc_iq", "left_pwm", "right_pwm", "servo_state", "motion_state",
}
FILE_ROLES = {"mic_raw", "render_reference", "telemetry"}
HEX64 = re.compile(r"^[0-9a-f]{64}$")


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def safe_rel(value: str) -> bool:
    p = Path(value)
    return bool(value) and not p.is_absolute() and ".." not in p.parts


def validate_structure(value: dict, *, allow_example: bool = False) -> None:
    required = {
        "schema_version", "example_only", "capture_id", "product", "sample_rate_hz",
        "mic_channels", "duration_seconds", "motion_class", "clock", "files",
        "telemetry_signals", "context",
    }
    if set(value) != required:
        raise ValueError(f"PCR02 manifest keys drifted: missing={sorted(required-set(value))} unexpected={sorted(set(value)-required)}")
    if value["schema_version"] != 1 or value["product"] != "PCR02" or value["mic_channels"] != 2:
        raise ValueError("PCR02 manifest identity/geometry mismatch")
    if value["example_only"] is True and not allow_example:
        raise ValueError("example_only manifest is documentation, not real evidence")
    if not isinstance(value["example_only"], bool):
        raise ValueError("example_only must be boolean")
    if not isinstance(value["capture_id"], str) or not value["capture_id"]:
        raise ValueError("capture_id is required")
    if int(value["sample_rate_hz"]) not in {8000, 16000, 24000, 32000, 48000}:
        raise ValueError("unsupported PCR02 sample rate")
    if float(value["duration_seconds"]) <= 0.0:
        raise ValueError("duration_seconds must be positive")
    if value["motion_class"] not in MOTION_CLASSES:
        raise ValueError("unknown PCR02 motion_class")
    if value["clock"] != {"domain": "monotonic", "timestamp_unit": "ns"}:
        raise ValueError("PCR02 clock must be monotonic nanoseconds")
    files = value["files"]
    if not isinstance(files, dict) or set(files) != FILE_ROLES:
        raise ValueError("PCR02 files must contain mic_raw/render_reference/telemetry")
    for role, item in files.items():
        if not isinstance(item, dict) or set(item) != {"path", "sha256"}:
            raise ValueError(f"invalid PCR02 file descriptor: {role}")
        if not safe_rel(str(item["path"])) or HEX64.fullmatch(str(item["sha256"])) is None:
            raise ValueError(f"invalid PCR02 path/hash: {role}")
    signals = value["telemetry_signals"]
    if not isinstance(signals, list) or len(signals) != len(set(signals)):
        raise ValueError("telemetry_signals must be a unique list")
    missing = REQUIRED_SIGNALS - set(signals)
    if missing:
        raise ValueError(f"PCR02 telemetry missing required signals: {sorted(missing)}")
    context = value["context"]
    if not isinstance(context, dict) or not {"floor_surface", "battery_mv", "load_state"} <= set(context):
        raise ValueError("PCR02 context is incomplete")
    if not str(context["floor_surface"]) or int(context["battery_mv"]) <= 0 or not str(context["load_state"]):
        raise ValueError("PCR02 context contains invalid values")


def verify_files(value: dict, root: Path) -> dict:
    checked = []
    for role, item in sorted(value["files"].items()):
        path = root / item["path"]
        if not path.is_file():
            raise FileNotFoundError(path)
        actual = sha256(path)
        if actual != item["sha256"]:
            raise ValueError(f"PCR02 SHA-256 mismatch for {role}: {actual} != {item['sha256']}")
        checked.append({"role": role, "path": item["path"], "sha256": actual, "size": path.stat().st_size})
    return {"capture_id": value["capture_id"], "motion_class": value["motion_class"], "files": checked}


def self_test() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        files = {}
        for role, name in (("mic_raw", "mic.pcm"), ("render_reference", "render.pcm"), ("telemetry", "telemetry.jsonl")):
            path = root / name
            path.write_bytes((role + "\n").encode())
            files[role] = {"path": name, "sha256": sha256(path)}
        good = {
            "schema_version": 1, "example_only": False, "capture_id": "self-test",
            "product": "PCR02", "sample_rate_hz": 16000, "mic_channels": 2,
            "duration_seconds": 1.0, "motion_class": "turning",
            "clock": {"domain": "monotonic", "timestamp_unit": "ns"},
            "files": files, "telemetry_signals": sorted(REQUIRED_SIGNALS),
            "context": {"floor_surface": "fixture", "battery_mv": 7600, "load_state": "nominal"},
        }
        validate_structure(good)
        result = verify_files(good, root)
        assert len(result["files"]) == 3
        bad = json.loads(json.dumps(good)); bad["example_only"] = True
        try: validate_structure(bad)
        except ValueError: pass
        else: raise AssertionError("example manifest was accepted as real evidence")
        validate_structure(bad, allow_example=True)
        bad = json.loads(json.dumps(good)); bad["telemetry_signals"].remove("left_foc_iq")
        try: validate_structure(bad)
        except ValueError: pass
        else: raise AssertionError("missing FOC telemetry was accepted")
        bad = json.loads(json.dumps(good)); bad["files"]["mic_raw"]["sha256"] = "0" * 64
        try: verify_files(bad, root)
        except ValueError: pass
        else: raise AssertionError("wrong PCR02 file hash was accepted")
    print("PCR02 self-noise validator self-test: OK")


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--self-test", action="store_true")
    p.add_argument("--manifest", type=Path)
    p.add_argument("--root", type=Path, default=Path("."))
    p.add_argument("--allow-example", action="store_true")
    p.add_argument("--skip-files", action="store_true")
    args = p.parse_args()
    if args.self_test:
        self_test(); return 0
    if args.manifest is None:
        p.error("--manifest is required")
    value = json.loads(args.manifest.read_text(encoding="utf-8"))
    validate_structure(value, allow_example=args.allow_example)
    result = {"result": "PASS", "capture_id": value["capture_id"], "example_only": value["example_only"]}
    if not args.skip_files:
        result["evidence"] = verify_files(value, args.root)
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
