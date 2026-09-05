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
    frontends = {report.get("frontend") for report in reports}
    if len(frontends) != 1 or None in frontends:
        raise ValueError(f"reports must use one explicit frontend: {sorted(str(x) for x in frontends)}")
    frontend = str(next(iter(frontends)))
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
            raw_faulty_energy = optional_metric(
                matched, "dynamics", "faulty_channel_raw_energy_dominant_fraction"
            )
            pre_bf_faulty_energy = optional_metric(
                matched, "dynamics", "faulty_channel_pre_bf_energy_dominant_fraction"
            )
            output_dc = optional_metric(matched, "quality", "fault_output_dc_offset_dbfs")
            output_clipping = optional_metric(matched, "quality", "fault_output_clip_fraction")
            input_rms = optional_metric(matched, "input_health", "faulty_input_rms_dbfs")
            input_dc = optional_metric(matched, "input_health", "faulty_input_dc_offset_dbfs")
            input_clipping = optional_metric(matched, "input_health", "faulty_input_clip_fraction")
            input_near_zero = optional_metric(
                matched, "input_health", "faulty_input_near_zero_fraction"
            )

            consistently_harmful = (
                delta["max"] is not None and float(delta["max"]) <= -1.0
            )
            severe_output_pollution = (
                (output_dc["median"] is not None and float(output_dc["median"]) > -30.0) or
                (output_clipping["median"] is not None and float(output_clipping["median"]) > 0.01)
            )
            # This answers a narrower design question than current fallback behavior:
            # if a future hard-fault mode simply bypasses to the larger-energy channel,
            # would that channel actually be healthy?  A consistently energy-dominant
            # faulty channel disproves that selector regardless of whether the current
            # soft fallback happened to enter.
            pure_energy_selector_wrong = (
                pre_bf_faulty_energy["min"] is not None and
                float(pre_bf_faulty_energy["min"]) > 0.5
            )
            if consistently_harmful or severe_output_pollution:
                hard_fault_isolation_needed = True
            if pure_energy_selector_wrong:
                pure_energy_strong_bypass_safe = False

            rows.append({
                "fault_type": fault_type,
                "faulty_channel": channel,
                "fault_current_minus_reliable_db": delta,
                "fault_fallback_active_fraction": fallback,
                "fallback_entry_latency_frames": entry,
                "stable_recovery_latency_frames": recovery,
                "reliable_selected_fraction_when_fallback": reliable_selected,
                "faulty_channel_raw_energy_dominant_fraction": raw_faulty_energy,
                "faulty_channel_pre_bf_energy_dominant_fraction": pre_bf_faulty_energy,
                "fault_output_dc_offset_dbfs": output_dc,
                "fault_output_clip_fraction": output_clipping,
                "faulty_input_rms_dbfs": input_rms,
                "faulty_input_dc_offset_dbfs": input_dc,
                "faulty_input_clip_fraction": input_clipping,
                "faulty_input_near_zero_fraction": input_near_zero,
                "classification": {
                    "consistently_harmful_vs_frontend_equivalent_reliable_single_mic": consistently_harmful,
                    "severe_output_pollution": severe_output_pollution,
                    "pure_energy_selector_consistently_chooses_faulty_channel": pure_energy_selector_wrong,
                },
            })

    if hard_fault_isolation_needed and not pure_energy_strong_bypass_safe:
        next_step = (
            "hard-fault isolation is justified, but pure current energy-strong bypass is unsafe; "
            "add fault-type health evidence and healthy-channel selection before bypass"
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
        "schema_version": 2,
        "authority": "diagnostic-regression-only",
        "frontend": frontend,
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
    print(f"frontend={result['frontend']}")
    for row in result["rows"]:
        delta = row["fault_current_minus_reliable_db"]
        selected = row["reliable_selected_fraction_when_fallback"]
        pre_bf_energy = row["faulty_channel_pre_bf_energy_dominant_fraction"]
        print(
            f"{row['fault_type']} ch{row['faulty_channel']}: "
            f"delta min/med/max={delta['min']}/{delta['median']}/{delta['max']} dB; "
            f"reliable-selected med={selected['median']}; "
            f"faulty-pre-BF-energy-dominant med={pre_bf_energy['median']}; "
            f"class={json.dumps(row['classification'], sort_keys=True)}"
        )
    print("DECISION: " + json.dumps(result["decision"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
