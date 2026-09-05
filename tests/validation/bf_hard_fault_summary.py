#!/usr/bin/env python3
"""Aggregate three-seed BF hard-microphone-fault discovery evidence."""

from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path

FAULT_TYPES = ("mute", "dropout", "stuck-dc", "hard-clip", "wind-burst")


def numeric_stats(values: list[float]) -> dict:
    if not values:
        return {"min": None, "median": None, "max": None, "samples": []}
    return {
        "min": min(values),
        "median": statistics.median(values),
        "max": max(values),
        "samples": values,
    }


def optional_metric(cases: list[dict], section: str, key: str) -> dict:
    values = []
    for case in cases:
        value = case[section].get(key)
        if value is not None:
            values.append(float(value))
    return numeric_stats(values)


def aggregate(report_paths: list[Path]) -> dict:
    if len(report_paths) != 3:
        raise ValueError(f"expected exactly three independent reports, got {len(report_paths)}")
    reports = [json.loads(path.read_text(encoding="utf-8")) for path in report_paths]
    for report in reports:
        if report.get("authority") != "diagnostic-regression-only":
            raise ValueError("report authority drifted from diagnostic-regression-only")
        if report.get("structural_violations"):
            raise ValueError(f"input report has structural violations: {report['corpus_id']}")

    rows = []
    hard_fault_isolation_needed = False
    pure_energy_strong_bypass_safe = True
    for fault_type in FAULT_TYPES:
        for channel in (0, 1):
            matched = []
            for report in reports:
                candidates = [
                    case for case in report["cases"]
                    if case["fault_type"] == fault_type and case["faulty_channel"] == channel
                ]
                if len(candidates) != 1:
                    raise ValueError(
                        f"expected one {fault_type}/ch{channel} case in {report['corpus_id']}"
                    )
                matched.append(candidates[0])

            delta = optional_metric(matched, "quality", "fault_current_minus_reliable_db")
            fallback = optional_metric(matched, "dynamics", "fault_fallback_active_fraction")
            entry = optional_metric(matched, "dynamics", "fallback_entry_latency_frames")
            recovery = optional_metric(matched, "dynamics", "stable_recovery_latency_frames")
            reliable_selected = optional_metric(
                matched, "dynamics", "reliable_selected_fraction_when_fallback"
            )
            faulty_energy = optional_metric(
                matched, "dynamics", "faulty_channel_energy_dominant_fraction"
            )
            dc = optional_metric(matched, "quality", "fault_output_dc_offset_dbfs")
            clipping = optional_metric(matched, "quality", "fault_output_clip_fraction")

            consistently_harmful = (
                delta["max"] is not None and float(delta["max"]) <= -1.0
            )
            severe_output_pollution = (
                (dc["median"] is not None and float(dc["median"]) > -30.0) or
                (clipping["median"] is not None and float(clipping["median"]) > 0.01)
            )
            energy_selector_wrong = (
                reliable_selected["max"] is not None and
                float(reliable_selected["max"]) < 0.5 and
                faulty_energy["min"] is not None and
                float(faulty_energy["min"]) > 0.5
            )
            if consistently_harmful or severe_output_pollution:
                hard_fault_isolation_needed = True
            if energy_selector_wrong:
                pure_energy_strong_bypass_safe = False

            rows.append({
                "fault_type": fault_type,
                "faulty_channel": channel,
                "fault_current_minus_reliable_db": delta,
                "fault_fallback_active_fraction": fallback,
                "fallback_entry_latency_frames": entry,
                "stable_recovery_latency_frames": recovery,
                "reliable_selected_fraction_when_fallback": reliable_selected,
                "faulty_channel_energy_dominant_fraction": faulty_energy,
                "fault_output_dc_offset_dbfs": dc,
                "fault_output_clip_fraction": clipping,
                "classification": {
                    "consistently_harmful_vs_reliable_single_mic": consistently_harmful,
                    "severe_output_pollution": severe_output_pollution,
                    "energy_selector_consistently_chooses_faulty_channel": energy_selector_wrong,
                },
            })

    if hard_fault_isolation_needed and not pure_energy_strong_bypass_safe:
        next_step = (
            "hard-fault isolation is justified, but pure current energy-strong bypass is unsafe; "
            "add fault-type evidence and healthy-channel selection before bypass"
        )
    elif hard_fault_isolation_needed:
        next_step = (
            "hard-fault isolation is justified; evaluate a bounded pure-selected-channel bypass "
            "against the same corpus before changing shipping DSP"
        )
    else:
        next_step = (
            "current corpus does not yet justify a shipping hard-fault bypass; keep product DSP "
            "unchanged and expand hard-fault coverage"
        )

    return {
        "schema_version": 1,
        "authority": "diagnostic-regression-only",
        "reports": [report["corpus_id"] for report in reports],
        "rows": rows,
        "decision": {
            "hard_fault_isolation_needed": hard_fault_isolation_needed,
            "pure_energy_strong_bypass_safe": pure_energy_strong_bypass_safe,
            "recommended_next_step": next_step,
        },
        "validation_result": "PASS",
    }


def self_test() -> None:
    stats = numeric_stats([3.0, 1.0, 2.0])
    assert stats["min"] == 1.0
    assert stats["median"] == 2.0
    assert stats["max"] == 3.0
    assert numeric_stats([])["median"] is None
    print("BF hard-fault summary self-test: OK")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", action="append", type=Path, default=[])
    parser.add_argument("--output", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    if args.output is None:
        parser.error("--output is required")
    result = aggregate(args.report)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    for row in result["rows"]:
        delta = row["fault_current_minus_reliable_db"]
        selected = row["reliable_selected_fraction_when_fallback"]
        energy = row["faulty_channel_energy_dominant_fraction"]
        print(
            f"{row['fault_type']} ch{row['faulty_channel']}: "
            f"delta min/med/max={delta['min']}/{delta['median']}/{delta['max']} dB; "
            f"reliable-selected med={selected['median']}; faulty-energy-dominant med={energy['median']}; "
            f"class={json.dumps(row['classification'], sort_keys=True)}"
        )
    print("DECISION: " + json.dumps(result["decision"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
