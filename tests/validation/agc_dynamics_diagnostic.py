#!/usr/bin/env python3
"""Evaluate dynamic AGC behavior with the standalone validation-only probe."""

from __future__ import annotations

import argparse
import json
import math
import statistics
import subprocess
from pathlib import Path

import run_validation_engine as engine


def percentile(values: list[float], q: float) -> float | None:
    ordered = sorted(value for value in values if math.isfinite(value))
    if not ordered:
        return None
    if len(ordered) == 1:
        return ordered[0]
    position = max(0.0, min(1.0, q)) * (len(ordered) - 1)
    low = int(math.floor(position))
    high = int(math.ceil(position))
    if low == high:
        return ordered[low]
    fraction = position - low
    return ordered[low] * (1.0 - fraction) + ordered[high] * fraction


def run_probe(probe: Path, pcm: Path, target: float, limiter: float) -> list[dict]:
    completed = subprocess.run(
        [str(probe), repr(float(target)), repr(float(limiter)), str(pcm)],
        check=True,
        text=True,
        capture_output=True,
    )
    rows = [json.loads(line) for line in completed.stdout.splitlines() if line.strip()]
    if not rows:
        raise ValueError(f"AGC probe produced no frames: {pcm}")
    return rows


def tail_median(rows: list[dict], start: int, end: int, width: int = 40) -> float:
    lo = max(start, end - width)
    values = [float(rows[index]["output_rms_dbfs"]) for index in range(lo, end)]
    return statistics.median(values)


def settling_frames(rows: list[dict], start: int, end: int, target: float,
                    tolerance_db: float = 1.5, consecutive: int = 5) -> int | None:
    streak = 0
    for index in range(start, min(end, len(rows))):
        value = float(rows[index]["output_rms_dbfs"])
        if abs(value - target) <= tolerance_db:
            streak += 1
            if streak >= consecutive:
                return index - start - consecutive + 1
        else:
            streak = 0
    return None


def summarize_case(case: dict, rows: list[dict], limiter_override: float | None = None) -> dict:
    dimensions = case.get("dimensions", {})
    gain = [float(row["gain_db"]) for row in rows]
    gain_steps = [abs(gain[index] - gain[index - 1]) for index in range(1, len(gain))]
    summary = {
        "case_id": case["case_id"],
        "scenario": case["scenario"],
        "frames": len(rows),
        "max_output_peak_dbfs": max(float(row["output_peak_dbfs"]) for row in rows),
        "max_gain_db": max(gain),
        "min_gain_db": min(gain),
        "p95_abs_gain_step_db": percentile(gain_steps, 0.95),
        "tail_output_rms_dbfs": tail_median(rows, 0, len(rows)),
        "violations": [],
    }
    violations = summary["violations"]
    limiter = float(
        limiter_override if limiter_override is not None
        else dimensions.get("limiter_dbfs", -2.0)
    )
    if summary["max_output_peak_dbfs"] > limiter + 0.20:
        violations.append({
            "gate": "limiter_peak",
            "actual": summary["max_output_peak_dbfs"],
            "expected_max": limiter + 0.20,
        })

    if case["case_id"] == "agc-steady-low":
        actual = summary["tail_output_rms_dbfs"]
        if not -21.5 <= actual <= -19.5:
            violations.append({
                "gate": "steady_low_output_level",
                "actual": actual,
                "expected_range": [-21.5, -19.5],
            })
    elif case["case_id"] == "agc-steady-hot":
        actual = summary["tail_output_rms_dbfs"]
        if not -20.8 <= actual <= -19.4:
            violations.append({
                "gate": "steady_hot_output_level",
                "actual": actual,
                "expected_range": [-20.8, -19.4],
            })
    elif case["case_id"] == "agc-level-step":
        low_to_hot = int(dimensions["low_to_hot_frame"])
        hot_to_low = int(dimensions["hot_to_low_frame"])
        hot_target = tail_median(rows, low_to_hot, hot_to_low)
        low_target = tail_median(rows, hot_to_low, len(rows))
        hot_settle = settling_frames(rows, low_to_hot, hot_to_low, hot_target)
        low_settle = settling_frames(rows, hot_to_low, len(rows), low_target)
        summary.update({
            "hot_segment_target_dbfs": hot_target,
            "low_segment_target_dbfs": low_target,
            "low_to_hot_settle_frames": hot_settle,
            "hot_to_low_settle_frames": low_settle,
        })
        if hot_settle is None or hot_settle > 25:
            violations.append({
                "gate": "low_to_hot_settle_frames",
                "actual": hot_settle,
                "expected_max": 25,
            })
        if low_settle is None or low_settle > 160:
            violations.append({
                "gate": "hot_to_low_settle_frames",
                "actual": low_settle,
                "expected_max": 160,
            })
        if summary["p95_abs_gain_step_db"] is not None and summary["p95_abs_gain_step_db"] > 0.75:
            violations.append({
                "gate": "level_step_gain_slew_p95_db",
                "actual": summary["p95_abs_gain_step_db"],
                "expected_max": 0.75,
            })

    summary["passed"] = not violations
    return summary


def diagnose(probe: Path, corpus_path: Path, target_override: float | None = None,
             limiter_override: float | None = None) -> dict:
    corpus = json.loads(corpus_path.read_text(encoding="utf-8"))
    cases = []
    effective = set()
    for case in corpus.get("cases", []):
        if case.get("processor_profile") != "agc-isolated":
            continue
        mic_path = engine.resolve(corpus_path, case["mic_audio"])
        if mic_path is None:
            raise ValueError("mic_audio is required")
        dimensions = case.get("dimensions", {})
        target = float(
            target_override if target_override is not None
            else dimensions.get("agc_target_dbfs", -20.0)
        )
        limiter = float(
            limiter_override if limiter_override is not None
            else dimensions.get("limiter_dbfs", -2.0)
        )
        if not math.isfinite(target) or not math.isfinite(limiter):
            raise ValueError("AGC tuning overrides must be finite")
        if not -60.0 <= target <= -1.0 or not -20.0 <= limiter <= -0.1 or target >= limiter:
            raise ValueError("AGC tuning overrides violate product tuning bounds")
        effective.add((target, limiter))
        rows = run_probe(probe, mic_path, target, limiter)
        cases.append(summarize_case(case, rows, limiter_override=limiter))
    violations = [
        {"case_id": case["case_id"], "violations": case["violations"]}
        for case in cases if case["violations"]
    ]
    return {
        "schema_version": 1,
        "authority": "diagnostic-regression-only",
        "corpus_id": corpus.get("corpus_id"),
        "processor_sha256": engine.sha256_file(probe),
        "corpus_sha256": engine.sha256_file(corpus_path),
        "effective_tuning": (
            {"agc_target_dbfs": next(iter(effective))[0], "limiter_dbfs": next(iter(effective))[1]}
            if len(effective) == 1 else None
        ),
        "validation_result": "PASS" if not violations else "FAIL",
        "cases": cases,
        "violations": violations,
    }


def self_test() -> None:
    rows = [
        {"output_rms_dbfs": -30.0 + min(index, 20) * 0.5,
         "output_peak_dbfs": -4.0, "gain_db": index * 0.1}
        for index in range(60)
    ]
    assert settling_frames(rows, 0, 60, -20.0, tolerance_db=0.6, consecutive=3) == 19
    assert abs(tail_median(rows, 0, 60) + 20.0) < 1.0e-9
    assert percentile([1.0, 2.0, 3.0], 0.5) == 2.0
    passing = summarize_case(
        {"case_id": "agc-steady-low", "scenario": "agc-steady-low", "dimensions": {"limiter_dbfs": -2.0}},
        [{"output_rms_dbfs": -20.7, "output_peak_dbfs": -15.0, "gain_db": 17.0}] * 50,
    )
    assert passing["passed"]
    tighter = summarize_case(
        {"case_id": "agc-transient", "scenario": "agc-transient", "dimensions": {"limiter_dbfs": -2.0}},
        [{"output_rms_dbfs": -20.0, "output_peak_dbfs": -3.7, "gain_db": 0.0}] * 50,
        limiter_override=-4.0,
    )
    assert not tighter["passed"] and tighter["violations"][0]["gate"] == "limiter_peak"
    print("AGC dynamics diagnostic self-test: OK")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--probe", type=Path)
    parser.add_argument("--corpus", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--agc-target-dbfs", type=float)
    parser.add_argument("--limiter-dbfs", type=float)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    for name in ("probe", "corpus", "output"):
        if getattr(args, name) is None:
            parser.error(f"--{name} is required")
    result = diagnose(
        args.probe.resolve(), args.corpus.resolve(),
        target_override=args.agc_target_dbfs,
        limiter_override=args.limiter_dbfs,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "result": result["validation_result"],
        "cases": len(result["cases"]),
        "effective_tuning": result["effective_tuning"],
        "output": str(args.output),
    }, sort_keys=True))
    return 1 if result["violations"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
