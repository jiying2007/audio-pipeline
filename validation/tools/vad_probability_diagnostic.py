#!/usr/bin/env python3
"""Emit non-authoritative VAD probability-distribution diagnostics.

This tool deliberately sits beside the canonical validation metrics rather than
changing shipping acceptance. It reuses the canonical processor invocation and
stage-profile routing, then reports stable-frame speech/noise probability
quantiles and fixed operating-point sweeps so VAD/NS->VAD tuning can be
evidence-driven instead of inferred from binary F1/FPR/recall alone.
"""

from __future__ import annotations

import argparse
import json
import math
import tempfile
from pathlib import Path
from typing import Sequence

import run_validation_engine as engine
import stage_profile_support

stage_profile_support.install(engine)

DECISION_THRESHOLD = 0.45
OPERATING_THRESHOLDS = (0.35, 0.40, 0.42, 0.45, 0.50)


def percentile(values: Sequence[float], q: float) -> float | None:
    ordered = sorted(float(value) for value in values if math.isfinite(float(value)))
    if not ordered:
        return None
    if len(ordered) == 1:
        return ordered[0]
    position = max(0.0, min(1.0, q)) * (len(ordered) - 1)
    lower = int(math.floor(position))
    upper = int(math.ceil(position))
    if lower == upper:
        return ordered[lower]
    fraction = position - lower
    return ordered[lower] * (1.0 - fraction) + ordered[upper] * fraction


def stable_probability_sets(labels: list[int], trace: list[dict]) -> tuple[list[float], list[float]]:
    count = min(len(labels), len(trace))
    positive: list[float] = []
    negative: list[float] = []
    for index in range(1, count - 1):
        if not (labels[index - 1] == labels[index] == labels[index + 1]):
            continue
        probability = float(trace[index].get("vad_probability", 0.0))
        if not math.isfinite(probability):
            continue
        (positive if labels[index] else negative).append(probability)
    return positive, negative


def fraction(values: Sequence[float], predicate) -> float | None:
    if not values:
        return None
    return sum(1 for value in values if predicate(value)) / len(values)


def operating_points(positive: Sequence[float], negative: Sequence[float]) -> list[dict]:
    return [
        {
            "threshold": threshold,
            "positive_above_fraction": fraction(
                positive, lambda value, t=threshold: value > t
            ),
            "negative_above_fraction": fraction(
                negative, lambda value, t=threshold: value > t
            ),
        }
        for threshold in OPERATING_THRESHOLDS
    ]


def summarize(labels: list[int], trace: list[dict]) -> dict:
    positive, negative = stable_probability_sets(labels, trace)
    positive_p10 = percentile(positive, 0.10)
    negative_p90 = percentile(negative, 0.90)
    return {
        "decision_threshold": DECISION_THRESHOLD,
        "stable_positive_frames": len(positive),
        "stable_negative_frames": len(negative),
        "positive_probability_p10": positive_p10,
        "positive_probability_p25": percentile(positive, 0.25),
        "positive_probability_p50": percentile(positive, 0.50),
        "negative_probability_p50": percentile(negative, 0.50),
        "negative_probability_p90": negative_p90,
        "negative_probability_p95": percentile(negative, 0.95),
        "positive_below_threshold_fraction": fraction(
            positive, lambda value: value <= DECISION_THRESHOLD
        ),
        "negative_above_threshold_fraction": fraction(
            negative, lambda value: value > DECISION_THRESHOLD
        ),
        "p10_p90_probability_margin": (
            None if positive_p10 is None or negative_p90 is None
            else positive_p10 - negative_p90
        ),
        "operating_points": operating_points(positive, negative),
    }


def diagnose(processor: Path, corpus_path: Path) -> dict:
    corpus = json.loads(corpus_path.read_text(encoding="utf-8"))
    cases = []
    for case in corpus.get("cases", []):
        labels_path = engine.resolve(corpus_path, case.get("vad_labels"))
        if labels_path is None:
            continue
        labels = engine.load_labels(labels_path)
        with tempfile.TemporaryDirectory(prefix="ap-vad-prob-") as temporary:
            _, trace, _ = engine.invoke(processor, case, corpus_path, Path(temporary))
        cases.append({
            "case_id": case["case_id"],
            "scenario": case["scenario"],
            "processor_profile": case.get("processor_profile", "default"),
            **summarize(labels, trace),
        })
    return {
        "schema_version": 1,
        "authority": "diagnostic-only",
        "corpus_id": corpus.get("corpus_id"),
        "processor_sha256": engine.sha256_file(processor),
        "corpus_sha256": engine.sha256_file(corpus_path),
        "cases": cases,
    }


def self_test() -> None:
    labels = [0, 0, 0, 1, 1, 1, 0, 0, 0]
    probabilities = [0.1, 0.2, 0.3, 0.4, 0.6, 0.8, 0.5, 0.2, 0.1]
    trace = [{"vad_probability": value} for value in probabilities]
    summary = summarize(labels, trace)
    assert summary["stable_positive_frames"] == 1
    assert summary["stable_negative_frames"] == 2
    assert abs(float(summary["positive_probability_p50"]) - 0.6) < 1.0e-9
    assert abs(float(summary["negative_probability_p50"]) - 0.2) < 1.0e-9
    assert summary["p10_p90_probability_margin"] is not None
    points = {item["threshold"]: item for item in summary["operating_points"]}
    assert points[0.45]["positive_above_fraction"] == 1.0
    assert points[0.45]["negative_above_fraction"] == 0.0
    print("VAD probability diagnostic self-test: OK")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--processor", type=Path)
    parser.add_argument("--corpus", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    for name in ("processor", "corpus", "output"):
        if getattr(args, name) is None:
            parser.error(f"--{name} is required")
    result = diagnose(args.processor.resolve(), args.corpus.resolve())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"cases": len(result["cases"]), "output": str(args.output)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
