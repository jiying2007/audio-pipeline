#!/usr/bin/env python3
"""Independent input-only audit for the frozen FE09-B3-F0 contract.

No DSP, project executable, subprocess, network, or project Python is loaded.
The literal integer construction is deliberately independent of the C harness.
Only hashes and a bounded per-frame control/input ledger are retained.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
from pathlib import Path
import struct

CONTRACT_SHA256 = "74e7294b1433207d222f9732326b68b33303c1ef63c8b6001283963419117284"
BASE = "81ee559848e1e30e3dd2eb4d03b0b479b9bd971e"
IDENTITY = "FE09-B3-F0-C4-16K-RENDER-PAP-V1"
DOCS = Path("docs/research/frontend-evolution-v1/FE09_B3_F0_PREREGISTRATION_20261024")
FRAMES, HOP, MICS = 600, 160, 4
SAMPLES = FRAMES * HOP
PUBLIC_ROLE = "unchanged_public_build_snapshot_superset"
PRIVATE_ROLE = "unchanged_private_compiled_dependency"
REFERENCE_ROLE = "authority_or_reference_snapshot_not_executed"


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def s16le(values: list[int]) -> bytes:
    return struct.pack("<" + str(len(values)) + "h", *values)


def advance(state: int) -> int:
    return (1664525 * state + 1013904223) & 0xFFFFFFFF


def c99_div4(value: int) -> int:
    # Python // floors negative values; C99 integer division truncates to zero.
    return value // 4 if value >= 0 else -((-value) // 4)


def describe(data: bytes, values: list[int], channels: int = 1) -> dict:
    return {
        "sha256": sha256(data), "bytes": len(data),
        "scalar_samples": len(values), "channels": channels,
        "sample_frames": len(values) // channels,
        "minimum": min(values), "maximum": max(values),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    contract_bytes = (args.repo / DOCS / "test-contract.json").read_bytes()
    if sha256(contract_bytes) != CONTRACT_SHA256:
        raise SystemExit("Frozen contract SHA256 mismatch: no input was generated")
    contract = json.loads(contract_bytes)
    assert contract["id"] == IDENTITY
    lock_bytes = (args.repo / DOCS / "source-lock.json").read_bytes()
    source_lock = json.loads(lock_bytes)
    assert source_lock["baseline_commit"] == BASE
    rows = source_lock["files"]
    assert len(rows) == len({row["path"] for row in rows}) == 77
    roles = {role: sum(row["role"] == role for row in rows)
             for role in (PUBLIC_ROLE, PRIVATE_ROLE, REFERENCE_ROLE)}
    assert roles == {PUBLIC_ROLE: 56, PRIVATE_ROLE: 10, REFERENCE_ROLE: 11}
    assert sum(roles.values()) == len(rows)
    unchanged = [row for row in rows if row["role"] in (PUBLIC_ROLE, PRIVATE_ROLE)]
    for row in unchanged:
        path = Path(row["path"])
        assert not path.is_absolute() and ".." not in path.parts
        data = (args.repo / path).read_bytes()
        blob = hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()
        assert (len(data), sha256(data), blob) == (
            row["bytes"], row["sha256"], row["git_blob_sha1"]), row["path"]

    render_state, near_state = 2654435769, 608135816
    mic_states = [286331153, 572662306, 858993459, 1145324612]
    render: list[int] = []
    near: list[int] = []
    echo: list[int] = []
    noise: list[list[int]] = [[] for _ in range(MICS)]
    capture: list[int] = []
    for n in range(SAMPLES):
        frame = n // HOP + 1
        render_state = advance(render_state)
        render.append(((render_state >> 16) & 8191) - 4096)
        near_state = advance(near_state)  # Also advances outside the near interval.
        z = ((near_state >> 16) & 32767) - 16384 if 161 <= frame <= 280 else 0
        e = 0 if n < 640 else c99_div4(render[n - 640])
        near.append(z)
        echo.append(e)
        for j in range(MICS):
            mic_states[j] = advance(mic_states[j])
            v = ((mic_states[j] >> 24) & 127) - 64
            noise[j].append(v)
            capture.append(e + z + v)
    assert all(-32768 <= value <= 32767 for value in capture + render)
    assert c99_div4(-1) == 0 and c99_div4(-4095) == -1023

    capture_bytes = s16le(capture)
    render_bytes = s16le(render)
    pap_render = render[:200 * HOP] + render[240 * HOP:]
    pap_render_bytes = s16le(pap_render)
    # This is the already registered future-suffix control, not a new fixture.
    future_capture = capture[:240 * HOP * MICS] + [-v for v in capture[240 * HOP * MICS:]]
    future_render = render[:240 * HOP] + [-v for v in render[240 * HOP:]]
    future_pap_render = future_render[:200 * HOP] + future_render[240 * HOP:]
    future_capture_bytes = s16le(future_capture)
    assert future_capture_bytes[:240 * HOP * MICS * 2] == capture_bytes[:240 * HOP * MICS * 2]
    assert s16le(future_pap_render)[:200 * HOP * 2] == pap_render_bytes[:200 * HOP * 2]

    args.output.mkdir(parents=True, exist_ok=True)
    ledgers: dict[str, dict] = {}
    fieldnames = ["capture_sequence", "capture_source_id", "render_source_id", "generation",
                  "render_event", "render_reason", "render_epoch", "render_gap_flag",
                  "actual_reference_ordinal", "reference_pcm_samples", "notify_flags",
                  "notify_lost_frames", "capture_s16le_sha256", "render_s16le_sha256"]
    for case in ("ALL_P", "PAP"):
        text = io.StringIO(newline="")
        writer = csv.DictWriter(text, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        present_count = absent_count = notify_count = 0
        for frame in range(1, FRAMES + 1):
            absent = case == "PAP" and 201 <= frame <= 240
            notify = case == "PAP" and frame in (201, 241)
            present_count += not absent
            absent_count += absent
            notify_count += notify
            begin = (frame - 1) * HOP * 2
            capture_begin = begin * MICS
            writer.writerow({
                "capture_sequence": frame, "capture_source_id": 104,
                "render_source_id": 204, "generation": 900001,
                "render_event": 2 if absent else 1,
                "render_reason": 1 if absent else 0,
                "render_epoch": 2 if case == "PAP" and frame >= 241 else 1,
                "render_gap_flag": 2 if case == "PAP" and frame == 241 else 0,
                "actual_reference_ordinal": 0 if absent else present_count,
                "reference_pcm_samples": 0 if absent else HOP,
                "notify_flags": 2 if notify else 0,
                "notify_lost_frames": 1 if notify else 0,
                "capture_s16le_sha256": sha256(capture_bytes[capture_begin:capture_begin + HOP * MICS * 2]),
                "render_s16le_sha256": "" if absent else sha256(render_bytes[begin:begin + HOP * 2]),
            })
        ledger = text.getvalue().encode("utf-8")
        filename = f"{case.lower()}_input_control.csv"
        (args.output / filename).write_bytes(ledger)
        ledgers[case] = {
            "path": filename, "sha256": sha256(ledger), "bytes": len(ledger),
            "capture_frames": FRAMES, "present_events": present_count,
            "absent_events": absent_count, "explicit_notifications": notify_count,
        }
    assert ledgers["PAP"]["present_events"] == 560
    assert ledgers["PAP"]["absent_events"] == 40
    assert ledgers["PAP"]["explicit_notifications"] == 2

    report = {
        "schema_version": 1, "id": IDENTITY,
        "role": "INDEPENDENT_INPUT_ONLY_PRE_DSP_FREEZE",
        "baseline_commit": BASE, "contract_sha256": CONTRACT_SHA256,
        "source_lock_sha256": sha256(lock_bytes),
        "generator_sha256": sha256(Path(__file__).read_bytes()),
        "encoding": "signed16 little-endian; Capture sample-major then physical mic0..3",
        "DSP_executed": False, "input_tuned": False,
        "streams": {
            "capture_all_p_and_pap": describe(capture_bytes, capture, MICS),
            "render_full_all_p": describe(render_bytes, render),
            "render_pap_delivered": describe(pap_render_bytes, pap_render),
            "capture_future_suffix_control": describe(future_capture_bytes, future_capture, MICS),
            "render_pap_future_suffix_control": describe(s16le(future_pap_render), future_pap_render),
        },
        "prefix_controls": {
            "capture_through_frame240_sha256": sha256(capture_bytes[:240 * HOP * MICS * 2]),
            "render_pap_delivered_through_frame240_sha256": sha256(render_bytes[:200 * HOP * 2]),
        },
        "bounds": {
            "capture_theoretical_inclusive": [-17472, 17469],
            "echo_observed": [min(echo), max(echo)],
            "near_observed": [min(near), max(near)],
            "noise_observed_by_mic": [[min(v), max(v)] for v in noise],
            "capture_observed_by_mic": [[min(capture[j::MICS]), max(capture[j::MICS])] for j in range(MICS)],
            "negative_nonmultiple4_echo_inputs": sum(x < 0 and x % 4 != 0 for x in render[:-640]),
            "clipping_count": 0,
        },
        "input_control_ledgers": ledgers,
        "notes": [
            "PAP delivered Render concatenates original frames1..200 and241..600; no absent PCM exists.",
            "Control ledger event values1/2, source-reported reason1 and both Render gap flags2 match frozen public/owner headers.",
            "The ALL_P/PAP Capture is one immutable byte stream. Future suffix inversion begins at frame241 only.",
            "No raw PCM files retained; no downstream output or acoustic result inspected.",
        ],
    }
    (args.output / "input-fixture-lock.independent.json").write_text(json.dumps(report, indent=2) + "\n")
    selection = {
        "id": IDENTITY, "baseline_commit": BASE,
        "source_lock_sha256": sha256(lock_bytes), "exact_role_counts": roles,
        "unchanged_gate_count": len(unchanged), "unchanged_gate": unchanged,
        "reference_only_paths": [r["path"] for r in rows if r["role"] == REFERENCE_ROLE],
        "enforcement": "Pin complete lock hash and exact77 role/path identities; byte-gate66 unchanged rows. Record11 reference-only rows as baseline provenance, not compiled execution. New implementation inputs have their own hashes.",
    }
    (args.output / "source-lock-gate-selection.json").write_text(json.dumps(selection, indent=2) + "\n")
    print(json.dumps({"streams": report["streams"], "bounds": report["bounds"],
                      "controls": ledgers, "source_lock_sha256": sha256(lock_bytes),
                      "unchanged_verified": len(unchanged)}, indent=2))


if __name__ == "__main__":
    main()
