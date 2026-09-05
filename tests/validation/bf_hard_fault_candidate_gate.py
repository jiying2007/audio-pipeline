#!/usr/bin/env python3
"""Gate the BF hard-fault product candidate without promoting synthetic authority.

The discovery corpus remains diagnostic. This gate only proves that a shipping
candidate satisfies predeclared deterministic regression bounds: one-sided
wind-like contamination must switch to the reliable microphone, while mute,
dropout, DC, clipping and worst-case soft gain/sensitivity controls must not be
misclassified as the low-frequency hard-contamination mode.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

FAULT_START_FRAME = 200
FAULT_END_FRAME = 500
WIND_MIN_DELTA_DB = -1.0
WIND_MIN_HARD_ACTIVE_FRACTION = 0.85
MIN_HARD_RELIABLE_SELECTED_FRACTION = 0.99
MAX_NON_WIND_HARD_ACTIVE_FRACTION = 0.01
MAX_RECOVERY_FRAMES = 40

MIN_DELTA_BY_TYPE = {
    "mute": -0.10,
    "dropout": -1.00,
    "stuck-dc": -0.10,
    "hard-clip": -1.00,
}
SOFT_CONTROL_TYPES = {"soft-global-gain", "soft-sensitivity-floor"}


def read_trace(path: Path) -> list[dict]:
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def hard_stats(trace: list[dict], reliable_channel: int) -> tuple[float, float | None]:
    rows = trace[FAULT_START_FRAME:FAULT_END_FRAME]
    if len(rows) != FAULT_END_FRAME - FAULT_START_FRAME:
        raise ValueError(f"trace too short for fault window: {len(trace)} frames")
    hard_rows = [row for row in rows if int(row.get("fallback_hard_fault", 0))]
    hard_fraction = len(hard_rows) / len(rows)
    if not hard_rows:
        return hard_fraction, None
    selected = sum(
        1 for row in hard_rows
        if int(row.get("fallback_strong_channel", -1)) == reliable_channel
    )
    return hard_fraction, selected / len(hard_rows)


def evaluate(report_paths: list[Path]) -> dict:
    if len(report_paths) != 3:
        raise ValueError(f"expected exactly three reports, got {len(report_paths)}")
    violations: list[dict] = []
    rows: list[dict] = []
    seen: set[tuple[str, int]] = set()

    for report_path in report_paths:
        report = json.loads(report_path.read_text(encoding="utf-8"))
        if report.get("frontend") != "hpf-bf":
            raise ValueError(f"candidate gate requires hpf-bf report: {report_path}")
        if report.get("authority") != "diagnostic-regression-only":
            raise ValueError(f"authority drift: {report_path}")
        corpus_id = str(report.get("corpus_id", report_path.parent.name))
        for case in report.get("cases", []):
            fault_type = str(case.get("fault_type"))
            faulty_channel = case.get("faulty_channel")
            if fault_type == "control" or faulty_channel is None:
                continue
            channel = int(faulty_channel)
            key = (str(case.get("case_id")), int(corpus_id.rsplit("-", 1)[-1]))
            if key in seen:
                raise ValueError(f"duplicate case evidence: {key}")
            seen.add(key)
            reliable_channel = int(case["reliable_channel"])
            trace_path = Path(str(case["artifacts"]["trace"]))
            if not trace_path.exists():
                # Reports may be moved as a directory after generation. Fall
                # back to the stable per-report artifact layout.
                trace_path = (
                    report_path.parent / "case-artifacts" /
                    str(case["case_id"]) / "trace.jsonl"
                )
            trace = read_trace(trace_path)
            hard_fraction, hard_reliable_fraction = hard_stats(trace, reliable_channel)
            delta = case.get("quality", {}).get("fault_current_minus_reliable_db")
            delta_value = None if delta is None else float(delta)
            recovery = case.get("dynamics", {}).get("stable_recovery_latency_frames")
            recovery_value = None if recovery is None else int(recovery)

            row = {
                "corpus_id": corpus_id,
                "case_id": case["case_id"],
                "fault_type": fault_type,
                "faulty_channel": channel,
                "fault_current_minus_reliable_db": delta_value,
                "hard_active_fraction": hard_fraction,
                "hard_reliable_selected_fraction": hard_reliable_fraction,
                "stable_recovery_latency_frames": recovery_value,
            }
            rows.append(row)

            if fault_type == "wind-burst":
                if delta_value is None or delta_value < WIND_MIN_DELTA_DB:
                    violations.append({
                        "case_id": case["case_id"],
                        "corpus_id": corpus_id,
                        "gate": "wind_quality_vs_reliable_mic",
                        "actual_db": delta_value,
                        "expected_min_db": WIND_MIN_DELTA_DB,
                    })
                if hard_fraction < WIND_MIN_HARD_ACTIVE_FRACTION:
                    violations.append({
                        "case_id": case["case_id"],
                        "corpus_id": corpus_id,
                        "gate": "wind_hard_mode_coverage",
                        "actual": hard_fraction,
                        "expected_min": WIND_MIN_HARD_ACTIVE_FRACTION,
                    })
                if (hard_reliable_fraction is None or
                        hard_reliable_fraction < MIN_HARD_RELIABLE_SELECTED_FRACTION):
                    violations.append({
                        "case_id": case["case_id"],
                        "corpus_id": corpus_id,
                        "gate": "wind_healthy_channel_selection",
                        "actual": hard_reliable_fraction,
                        "expected_min": MIN_HARD_RELIABLE_SELECTED_FRACTION,
                    })
            else:
                if hard_fraction > MAX_NON_WIND_HARD_ACTIVE_FRACTION:
                    violations.append({
                        "case_id": case["case_id"],
                        "corpus_id": corpus_id,
                        "gate": "non_wind_false_hard_mode",
                        "actual": hard_fraction,
                        "expected_max": MAX_NON_WIND_HARD_ACTIVE_FRACTION,
                    })
                minimum_delta = MIN_DELTA_BY_TYPE.get(fault_type)
                if minimum_delta is not None and (
                    delta_value is None or delta_value < minimum_delta
                ):
                    violations.append({
                        "case_id": case["case_id"],
                        "corpus_id": corpus_id,
                        "gate": "non_wind_quality_regression",
                        "actual_db": delta_value,
                        "expected_min_db": minimum_delta,
                    })
                if fault_type in SOFT_CONTROL_TYPES and hard_fraction != 0.0:
                    violations.append({
                        "case_id": case["case_id"],
                        "corpus_id": corpus_id,
                        "gate": "soft_degradation_must_remain_soft",
                        "actual": hard_fraction,
                        "expected": 0.0,
                    })

            if recovery_value is None or recovery_value > MAX_RECOVERY_FRAMES:
                violations.append({
                    "case_id": case["case_id"],
                    "corpus_id": corpus_id,
                    "gate": "bounded_recovery",
                    "actual_frames": recovery_value,
                    "expected_max_frames": MAX_RECOVERY_FRAMES,
                })

    expected_cases_per_report = 2 * (5 + len(SOFT_CONTROL_TYPES))
    if len(rows) != len(report_paths) * expected_cases_per_report:
        raise ValueError(
            f"incomplete candidate evidence: rows={len(rows)} "
            f"expected={len(report_paths) * expected_cases_per_report}"
        )

    return {
        "schema_version": 1,
        "authority": "deterministic-candidate-regression-only",
        "reports": [str(path) for path in report_paths],
        "rows": rows,
        "violations": violations,
        "validation_result": "PASS" if not violations else "FAIL",
    }


def self_test() -> None:
    trace = [
        {
            "frame": frame,
            "fallback_hard_fault": 1 if 210 <= frame < 490 else 0,
            "fallback_strong_channel": 1,
        }
        for frame in range(800)
    ]
    hard_fraction, selected = hard_stats(trace, 1)
    assert abs(hard_fraction - (280 / 300)) < 1.0e-12
    assert selected == 1.0
    trace[250]["fallback_strong_channel"] = 0
    _, selected = hard_stats(trace, 1)
    assert selected is not None and selected < 1.0
    print("BF hard-fault candidate gate self-test: OK")


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
    result = evaluate(args.report)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    for row in result["rows"]:
        print(
            f"{row['corpus_id']} {row['case_id']}: "
            f"delta={row['fault_current_minus_reliable_db']} dB "
            f"hard={row['hard_active_fraction']:.3f} "
            f"healthy-selected={row['hard_reliable_selected_fraction']} "
            f"recovery={row['stable_recovery_latency_frames']}f"
        )
    for violation in result["violations"]:
        print("CANDIDATE FAIL: " + json.dumps(violation, sort_keys=True))
    return 1 if result["violations"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
