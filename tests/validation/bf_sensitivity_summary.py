#!/usr/bin/env python3
"""Aggregate multi-seed BF sensitivity reports and enforce product reliability gates."""

from __future__ import annotations

import argparse
import json
import math
import statistics
from pathlib import Path

MODELS = ("global-channel-gain", "sensitivity-floor")
RATIOS = (1.0, 0.8, 0.55, 0.35)
QUALITY_GATES = {
    ("global-channel-gain", 0.35): 1.0,
    ("sensitivity-floor", 0.55): 0.5,
    ("sensitivity-floor", 0.35): 0.0,
}


def case_key(case_id: str) -> tuple[str, float] | None:
    prefixes = {
        "bf-global-gain-r": "global-channel-gain",
        "bf-sensitivity-floor-r": "sensitivity-floor",
    }
    for prefix, model in prefixes.items():
        if case_id.startswith(prefix):
            token = case_id[len(prefix):]
            return model, int(token) / 100.0
    return None


def metric(case: dict) -> float:
    value = case.get("metrics", {}).get("near_si_sdr_improvement_db")
    if value is None:
        raise ValueError(f"missing near_si_sdr_improvement_db: {case.get('case_id')}")
    value = float(value)
    if not math.isfinite(value):
        raise ValueError(f"non-finite SI-SDR improvement: {case.get('case_id')}")
    return value


def aggregate(report_paths: list[Path]) -> dict:
    if len(report_paths) != 3:
        raise ValueError(f"expected exactly three independent reports, got {len(report_paths)}")
    values: dict[tuple[str, float], list[float]] = {
        (model, ratio): [] for model in MODELS for ratio in RATIOS
    }
    report_ids: list[str] = []
    for path in report_paths:
        report = json.loads(path.read_text(encoding="utf-8"))
        report_ids.append(report.get("corpus_id") or path.parent.name)
        seen: set[tuple[str, float]] = set()
        for case in report.get("cases", []):
            key = case_key(str(case.get("case_id", "")))
            if key is None:
                continue
            if key in seen:
                raise ValueError(f"duplicate BF sensitivity case in {path}: {key}")
            seen.add(key)
            values[key].append(metric(case))
        expected = set(values)
        if seen != expected:
            missing = sorted(expected - seen)
            raise ValueError(f"incomplete BF sensitivity report {path}: missing={missing}")

    rows = []
    structural_violations = []
    quality_violations = []
    for model in MODELS:
        for ratio in RATIOS:
            samples = values[(model, ratio)]
            if len(samples) != 3:
                raise ValueError(f"expected three samples for {(model, ratio)}, got {len(samples)}")
            minimum = min(samples)
            median = statistics.median(samples)
            maximum = max(samples)
            classification = (
                "stable-positive" if minimum >= 0.0
                else "mixed-or-negative" if maximum >= 0.0
                else "consistently-negative"
            )
            row = {
                "model": model,
                "weak_channel_ratio": ratio,
                "si_sdr_improvement_db": {
                    "min": minimum,
                    "median": median,
                    "max": maximum,
                    "samples": samples,
                },
                "classification": classification,
            }
            rows.append(row)
            # Ratio 1.0 is a corpus/evaluator sanity anchor, not a tuning target.
            if ratio == 1.0 and minimum < 0.5:
                structural_violations.append({
                    "model": model,
                    "gate": "unity_ratio_sanity",
                    "actual_min_db": minimum,
                    "expected_min_db": 0.5,
                })
            expected_minimum = QUALITY_GATES.get((model, ratio))
            if expected_minimum is not None and minimum < expected_minimum:
                quality_violations.append({
                    "model": model,
                    "weak_channel_ratio": ratio,
                    "gate": "weak_channel_min_si_sdr_improvement_db",
                    "actual_min_db": minimum,
                    "expected_min_db": expected_minimum,
                })

    passed = not structural_violations and not quality_violations
    return {
        "schema_version": 2,
        "authority": "regression-quality-gate",
        "reports": report_ids,
        "rows": rows,
        "quality_gates": [
            {
                "model": model,
                "weak_channel_ratio": ratio,
                "min_si_sdr_improvement_db": minimum,
            }
            for (model, ratio), minimum in sorted(QUALITY_GATES.items())
        ],
        "structural_violations": structural_violations,
        "quality_violations": quality_violations,
        "validation_result": "PASS" if passed else "FAIL",
    }


def self_test() -> None:
    assert case_key("bf-global-gain-r055") == ("global-channel-gain", 0.55)
    assert case_key("bf-sensitivity-floor-r035") == ("sensitivity-floor", 0.35)
    assert case_key("other") is None
    assert QUALITY_GATES[("global-channel-gain", 0.35)] == 1.0
    assert QUALITY_GATES[("sensitivity-floor", 0.55)] == 0.5
    assert QUALITY_GATES[("sensitivity-floor", 0.35)] == 0.0
    print("BF sensitivity summary self-test: OK")


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
        stats = row["si_sdr_improvement_db"]
        print(
            f"{row['model']} ratio={row['weak_channel_ratio']:.2f} "
            f"min/median/max={stats['min']:.3f}/{stats['median']:.3f}/{stats['max']:.3f} dB "
            f"{row['classification']}"
        )
    for violation in result["quality_violations"]:
        print(
            "QUALITY FAIL "
            f"{violation['model']} ratio={violation['weak_channel_ratio']:.2f}: "
            f"min={violation['actual_min_db']:.3f} dB < "
            f"required={violation['expected_min_db']:.3f} dB"
        )
    return 0 if result["validation_result"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
