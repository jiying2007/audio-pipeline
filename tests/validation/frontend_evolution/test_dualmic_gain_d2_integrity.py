#!/usr/bin/env python3
"""Small D2 structural/diagnostic corruption tests; no C, DSP or audio scoring."""
from __future__ import annotations

import argparse
import copy
import csv
import json
from pathlib import Path
import struct
import tempfile
import time

import dualmic_gain_d2 as d2


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    started = time.monotonic()
    checks = []

    def rejected(name, action):
        try:
            action()
        except (ValueError, KeyError, OverflowError) as exc:
            checks.append({"case": name, "status": "REJECTED_AS_REQUIRED", "error": str(exc)})
        else:
            raise AssertionError("corruption accepted: " + name)

    lock = d2.input_lock()
    catalog = [entry["catalog"] for entry in lock["cases"]]
    index = {"status": "RUN_COMPLETE_BYTES_IDENTICAL", "cases": copy.deepcopy(catalog),
             "completed_cases": [case["key"] for case in catalog]}
    report = {"cases": [{"key": case["key"]} for case in catalog]}
    d2.parent_catalog(index, report, catalog)
    missing = copy.deepcopy(index)
    missing["cases"].pop()
    missing["completed_cases"].pop()
    rejected("drop_parent_case_and_completion", lambda: d2.parent_catalog(missing, report, catalog))
    reordered = copy.deepcopy(index)
    reordered["cases"].reverse()
    reordered["completed_cases"].reverse()
    rejected("reorder_parent_catalog", lambda: d2.parent_catalog(reordered, report, catalog))
    wrong_report = copy.deepcopy(report)
    wrong_report["cases"][-1] = wrong_report["cases"][0]
    rejected("duplicate_parent_report_case", lambda: d2.parent_catalog(index, wrong_report, catalog))

    # Explicit structural fixture: gain values encode state continuity, not
    # simulated AGC output. No waveform or acoustic score is generated.
    case = copy.deepcopy(next(c for c in catalog if c["scenario"] == "render-gap"))
    rows = []
    for frame in range(case["frames"]):
        row = {name: "0" for name in d2.d1.CONTROL_FIELDS}
        row.update(frame=str(frame), agc_allow="0" if frame == 151 else "1",
                   far="1" if frame == 151 else "0", dt="0",
                   gain_before="1" if frame in (0, 300) else "2", gain_after="2")
        rows.append(row)
    with tempfile.TemporaryDirectory(prefix="dualmic-d2-integrity-") as temporary:
        path = Path(temporary) / "control.csv"

        def write_rows(data):
            with path.open("w", newline="", encoding="ascii") as stream:
                writer = csv.DictWriter(stream, fieldnames=d2.d1.CONTROL_FIELDS)
                writer.writeheader()
                writer.writerows(data)

        write_rows(rows)
        encoded = d2.control_bytes(path, case)
        records = list(struct.iter_unpack("<IIff", encoded))
        assert len(records) == 600 and len(encoded) == 9600
        assert [records[i][0] for i in (150, 151, 152)] == [1, 0, 1]
        assert [i for i, record in enumerate(records) if record[1]] == [300]
        no_reset = copy.deepcopy(case)
        no_reset["input_events"] = []
        rejected("omit_original_discontinuity", lambda: d2.control_bytes(path, no_reset))
        echo = copy.deepcopy(case)
        echo["input_events"] = [{"frame": 300, "sample": 48000, "kind": "cli_echo_path_change"}]
        rejected("reset_state_on_echo_path_change", lambda: d2.control_bytes(path, echo))
        malformed = copy.deepcopy(rows)
        malformed[151]["agc_allow"] = "2"
        write_rows(malformed)
        rejected("illegal_allow_flag", lambda: d2.control_bytes(path, case))
        malformed = copy.deepcopy(rows)
        malformed[400]["gain_before"] = "1"
        write_rows(malformed)
        rejected("gain_state_continuity_corruption", lambda: d2.control_bytes(path, case))
        no_reset_rows = copy.deepcopy(rows)
        no_reset_rows[300]["gain_before"] = "2"
        write_rows(no_reset_rows)
        assert all(record[1] == 0 for record in struct.iter_unpack("<IIff", d2.control_bytes(path, echo)))

    # This fixture checks tamper rejection for the previously missing diagnostic
    # columns. It is not an independent numerical-accuracy or DSP result.
    signal = [d2.f32(0.25)] * d2.HOP
    operands, flags = d2.gain_observation(signal, 1.0, 1, d2.f32(0.1), d2.f32(0.794328212))
    operands.update(target_linear=d2.f32(0.1), limiter_linear=d2.f32(0.794328212))
    after = operands["expected_state_gain_after"]
    d2.audit_gain_observation(signal, 1.0, after, 1, operands, flags)
    for field in ("input_rms", "target_gain_raw", "target_gain_bounded", "target_gain", "alpha",
                  "expected_state_gain_after", "peak_limit_gain"):
        corrupted = dict(operands)
        integer = struct.unpack("<I", d2.bits(corrupted[field]))[0]
        corrupted[field] = struct.unpack("<f", struct.pack("<I", integer + 1))[0]
        rejected("altered_saved_diagnostic_" + field,
                 lambda corrupted=corrupted: d2.audit_gain_observation(signal, 1.0, after, 1, corrupted, flags))
    wrong_flags = dict(flags, target_gate_cap_active=1)
    rejected("altered_saved_target_gate_flag",
             lambda: d2.audit_gain_observation(signal, 1.0, after, 1, operands, wrong_flags))
    assert d2.differences(struct.pack("<ff", 0.0, -0.0), struct.pack("<ff", 0.0, 0.0)) == (
        1, {"frame": 0, "sample_in_frame": 1, "global_sample": 1,
            "before_bits": "0x80000000", "after_bits": "0x00000000"})
    receipt = {"schema_version": 1, "experiment": d2.EXPERIMENT, "status": "PASS",
               "test_kind": "structural_and_saved_diagnostic_corruption_only",
               "DSP_executed": False, "models_executed": False, "audio_scores_computed": False,
               "frozen_input_lock": d2.descriptor(d2.ROOT / d2.LOCK_NAME), "negative_cases": checks,
               "case_count": len(checks), "native_control_frame_shift": 0,
               "elapsed_seconds": time.monotonic() - started, "budget_seconds": 300}
    if args.output:
        d2.require(not args.output.exists() and not args.output.is_symlink(), "absent test receipt path required")
        d2.write_json(args.output, receipt)
    d2.require(time.monotonic() - started <= 300, "integrity test budget exceeded")
    print(json.dumps(receipt, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
