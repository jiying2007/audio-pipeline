#!/usr/bin/env python3
"""Validate the PCR02 35 mm real-capture plan contract.

The plan intentionally creates no real evidence. Completed captures must be
materialized separately through the existing PCR02 self-noise manifest contract.
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

EXPECTED_GROUPS = {"bf-geometry": 16, "self-noise": 14, "aec-product-path": 12}
REQUIRED_SIGNALS = {
    "timestamp_ns", "left_motor_rpm", "right_motor_rpm",
    "left_foc_iq", "right_foc_iq", "left_pwm", "right_pwm",
    "servo_state", "motion_state",
}


def validate(value: dict) -> None:
    if value.get("schema_version") != 1 or value.get("product") != "PCR02":
        raise ValueError("PCR02 capture plan identity mismatch")
    if value.get("authority") != "capture-plan-only":
        raise ValueError("capture plan authority drifted")
    if value.get("real_evidence_created") is not False:
        raise ValueError("capture plan must not claim real evidence")
    if value.get("promotion_allowed") is not False:
        raise ValueError("capture plan cannot promote shipping")
    geometry = value.get("geometry", {})
    if geometry != {"mic_channels": 2, "mic_spacing_mm": 35.0, "sample_rate_hz": 16000}:
        raise ValueError(f"PCR02 geometry drifted: {geometry}")
    if set(value.get("required_files", [])) != {"mic_raw", "render_reference", "telemetry"}:
        raise ValueError("required capture files drifted")
    if not REQUIRED_SIGNALS.issubset(set(value.get("required_telemetry_signals", []))):
        raise ValueError("required telemetry signals incomplete")
    slots = value.get("slots", [])
    if len(slots) != 42:
        raise ValueError(f"expected 42 capture slots, got {len(slots)}")
    ids = [slot.get("slot_id") for slot in slots]
    if len(set(ids)) != len(ids) or any(not item for item in ids):
        raise ValueError("slot ids must be unique and non-empty")
    counts = Counter(slot.get("track") for slot in slots)
    if dict(counts) != EXPECTED_GROUPS:
        raise ValueError(f"capture group counts drifted: {dict(counts)}")
    if value.get("groups") != EXPECTED_GROUPS:
        raise ValueError("declared capture group counts drifted")

    bf = [slot for slot in slots if slot["track"] == "bf-geometry"]
    if {slot["angle_deg"] for slot in bf} != {0, 30, 60, 90}:
        raise ValueError("BF angle coverage incomplete")
    if {float(slot["distance_m"]) for slot in bf} != {0.5, 1.0, 2.0, 3.0}:
        raise ValueError("BF distance coverage incomplete")

    self_noise = [slot for slot in slots if slot["track"] == "self-noise"]
    if {slot["motion_class"] for slot in self_noise} != {"idle", "straight", "turning", "acceleration", "braking", "servo", "floor-transition"}:
        raise ValueError("self-noise motion coverage incomplete")
    if {slot["floor_surface"] for slot in self_noise} != {"hard-floor", "carpet"}:
        raise ValueError("self-noise floor coverage incomplete")

    aec = [slot for slot in slots if slot["track"] == "aec-product-path"]
    if {slot["speech_state"] for slot in aec} != {"speaker-only", "double-talk"}:
        raise ValueError("AEC speech-state coverage incomplete")
    if {slot["motion_class"] for slot in aec} != {"idle", "straight", "turning"}:
        raise ValueError("AEC motion coverage incomplete")
    if {slot["floor_surface"] for slot in aec} != {"hard-floor", "carpet"}:
        raise ValueError("AEC floor coverage incomplete")


def self_test() -> None:
    assert sum(EXPECTED_GROUPS.values()) == 42
    assert REQUIRED_SIGNALS >= {"left_foc_iq", "right_foc_iq", "left_pwm", "right_pwm"}
    print("PCR02 capture plan validator self-test: OK")


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--plan", type=Path)
    p.add_argument("--self-test", action="store_true")
    args = p.parse_args()
    if args.self_test:
        self_test()
        return 0
    if args.plan is None:
        p.error("--plan is required")
    value = json.loads(args.plan.read_text(encoding="utf-8"))
    validate(value)
    print(json.dumps({"result": "PASS", "authority": value["authority"], "real_evidence_created": value["real_evidence_created"], "slots": len(value["slots"]), "groups": value["groups"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
