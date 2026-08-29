#!/usr/bin/env python3
"""Build and evaluate compact test-performance history records."""

from __future__ import annotations

import argparse
import json
import math
import statistics
from pathlib import Path

LOWER_IS_BETTER = {"active_rtf", "active_p99_us", "active_max_us", "state_bytes"}
HIGHER_IS_BETTER = {"validation_pass_rate", "median_erle_db", "min_vad_f1"}


def parse_kv_line(text: str) -> dict[str, str]:
    values = {}
    for token in text.replace("\n", " ").split():
        if "=" in token:
            key, value = token.split("=", 1)
            values[key] = value
    return values


def collect(benchmark: Path, validation: Path | None, revision: str) -> dict:
    bench = parse_kv_line(benchmark.read_text(encoding="utf-8"))
    metrics = {
        "active_rtf": float(bench["rtf"]),
        "active_p99_us": float(bench["p99_us"]),
        "active_max_us": float(bench["max_us"]),
        "state_bytes": float(bench["state_bytes"]),
    }
    if validation:
        report = json.loads(validation.read_text(encoding="utf-8"))
        summary = report["summary"]
        metrics["validation_pass_rate"] = float(summary["pass_rate"])
        if summary.get("median_erle_db") is not None:
            metrics["median_erle_db"] = float(summary["median_erle_db"])
        if summary.get("min_vad_f1") is not None:
            metrics["min_vad_f1"] = float(summary["min_vad_f1"])
    return {"schema_version": 1, "source_revision": revision, "metrics": metrics}


def load_history(root: Path) -> list[dict]:
    records = []
    if not root.exists():
        return records
    for path in sorted(root.rglob("*.json")):
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if record.get("schema_version") == 1 and isinstance(record.get("metrics"), dict):
            records.append(record)
    return records


def robust_z(value: float, values: list[float]) -> float:
    if len(values) < 3:
        return 0.0
    median = statistics.median(values)
    deviations = [abs(x - median) for x in values]
    mad = statistics.median(deviations)
    if mad <= 1.0e-12:
        return 0.0 if abs(value - median) <= 1.0e-12 else math.inf
    return 0.67448975 * (value - median) / mad


def evaluate(current: dict, history: list[dict], min_samples: int, maturity_samples: int,
             z_limit: float, pct_limit: float) -> dict:
    findings = []
    metrics = current["metrics"]
    sample_counts: dict[str, int] = {}
    evaluated_metrics = 0
    for name, value_raw in sorted(metrics.items()):
        samples = [float(r["metrics"][name]) for r in history if name in r.get("metrics", {})]
        sample_counts[name] = len(samples)
        if len(samples) < min_samples:
            continue
        evaluated_metrics += 1
        value = float(value_raw)
        median = statistics.median(samples)
        pct = 0.0 if abs(median) <= 1.0e-12 else (value - median) / abs(median) * 100.0
        z = robust_z(value, samples)
        bad_direction = (name in LOWER_IS_BETTER and pct > 0) or (name in HIGHER_IS_BETTER and pct < 0)
        regressed = bad_direction and (abs(pct) > pct_limit or abs(z) > z_limit)
        if regressed:
            findings.append({
                "metric": name, "current": value, "median": median,
                "delta_pct": pct, "robust_z": z, "samples": len(samples),
            })
    mature = bool(metrics) and all(sample_counts.get(name, 0) >= maturity_samples for name in metrics)
    return {
        "schema_version": 2,
        "source_revision": current.get("source_revision"),
        "history_records": len(history),
        "min_samples": min_samples,
        "maturity_samples": maturity_samples,
        "maturity_status": "MATURE" if mature else "WARMING_UP",
        "sample_counts": sample_counts,
        "evaluated_metrics": evaluated_metrics,
        "z_limit": z_limit,
        "pct_limit": pct_limit,
        "result": "FAIL" if findings else "PASS",
        "findings": findings,
    }


def self_test() -> None:
    current = {"source_revision": "x", "metrics": {"active_p99_us": 130.0}}
    history = [{"metrics": {"active_p99_us": x}} for x in (99, 100, 101, 100, 99, 101)]
    failed = evaluate(current, history, 5, 30, 4.0, 15.0)
    assert failed["result"] == "FAIL"
    assert failed["maturity_status"] == "WARMING_UP"
    current["metrics"]["active_p99_us"] = 103.0
    assert evaluate(current, history, 5, 30, 4.0, 15.0)["result"] == "PASS"
    mature_history = [{"metrics": {"active_p99_us": 100.0}} for _ in range(30)]
    mature = evaluate(current, mature_history, 5, 30, 4.0, 15.0)
    assert mature["maturity_status"] == "MATURE"
    print("test history self-test: OK")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    sub = parser.add_subparsers(dest="command")
    c = sub.add_parser("collect")
    c.add_argument("--benchmark", type=Path, required=True)
    c.add_argument("--validation", type=Path)
    c.add_argument("--revision", required=True)
    c.add_argument("--output", type=Path, required=True)
    e = sub.add_parser("evaluate")
    e.add_argument("--current", type=Path, required=True)
    e.add_argument("--history-dir", type=Path, required=True)
    e.add_argument("--output", type=Path, required=True)
    e.add_argument("--min-samples", type=int, default=5)
    e.add_argument("--maturity-samples", type=int, default=30)
    e.add_argument("--z-limit", type=float, default=4.0)
    e.add_argument("--pct-limit", type=float, default=15.0)
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    if args.command == "collect":
        result = collect(args.benchmark, args.validation, args.revision)
    elif args.command == "evaluate":
        current = json.loads(args.current.read_text(encoding="utf-8"))
        result = evaluate(
            current,
            load_history(args.history_dir),
            args.min_samples,
            args.maturity_samples,
            args.z_limit,
            args.pct_limit,
        )
    else:
        parser.error("collect or evaluate is required")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, sort_keys=True))
    return 1 if args.command == "evaluate" and result["result"] == "FAIL" else 0


if __name__ == "__main__":
    raise SystemExit(main())
