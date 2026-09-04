#!/usr/bin/env python3
"""Measure standalone NS speech-probability separation on labelled stage cases."""

from __future__ import annotations

import argparse
import json
import math
import subprocess
import tempfile
from pathlib import Path
from typing import Sequence

import run_validation_engine as engine


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


def stable_sets(labels: list[int], trace: list[dict]) -> tuple[list[float], list[float]]:
    count = min(len(labels), len(trace))
    positive: list[float] = []
    negative: list[float] = []
    for index in range(1, count - 1):
        if not (labels[index - 1] == labels[index] == labels[index + 1]):
            continue
        value = float(trace[index].get("ns_speech_probability", 0.0))
        if not math.isfinite(value):
            continue
        (positive if labels[index] else negative).append(value)
    return positive, negative


def summarize(labels: list[int], trace: list[dict]) -> dict:
    positive, negative = stable_sets(labels, trace)
    p10 = percentile(positive, 0.10)
    n90 = percentile(negative, 0.90)
    return {
        "stable_positive_frames": len(positive),
        "stable_negative_frames": len(negative),
        "positive_probability_p10": p10,
        "positive_probability_p25": percentile(positive, 0.25),
        "positive_probability_p50": percentile(positive, 0.50),
        "negative_probability_p50": percentile(negative, 0.50),
        "negative_probability_p90": n90,
        "negative_probability_p95": percentile(negative, 0.95),
        "p10_p90_probability_margin": None if p10 is None or n90 is None else p10 - n90,
    }


def run_probe(probe: Path, pcm: Path) -> list[dict]:
    with tempfile.TemporaryDirectory(prefix="ap-ns-prob-") as temporary:
        trace_path = Path(temporary) / "trace.jsonl"
        subprocess.run([str(probe), str(pcm), str(trace_path)], check=True)
        return [json.loads(line) for line in trace_path.read_text(encoding="utf-8").splitlines() if line.strip()]


def diagnose(probe: Path, corpus_path: Path) -> dict:
    corpus = json.loads(corpus_path.read_text(encoding="utf-8"))
    cases = []
    for case in corpus.get("cases", []):
        if case.get("processor_profile") != "ns-isolated":
            continue
        labels_path = engine.resolve(corpus_path, case.get("vad_labels"))
        mic_path = engine.resolve(corpus_path, case.get("mic_audio"))
        if labels_path is None or mic_path is None:
            continue
        if int(case.get("sample_rate_hz", 0)) != 16000 or int(case.get("mic_channels", 0)) != 1:
            raise ValueError("NS probability probe currently requires 16 kHz mono stage cases")
        labels = engine.load_labels(labels_path)
        trace = run_probe(probe, mic_path)
        cases.append({
            "case_id": case["case_id"],
            "scenario": case["scenario"],
            **summarize(labels, trace),
        })
    return {
        "schema_version": 1,
        "authority": "diagnostic-only",
        "corpus_id": corpus.get("corpus_id"),
        "probe_sha256": engine.sha256_file(probe),
        "corpus_sha256": engine.sha256_file(corpus_path),
        "cases": cases,
    }


def self_test() -> None:
    labels = [0, 0, 0, 1, 1, 1, 0, 0, 0]
    trace = [
        {"ns_speech_probability": value}
        for value in (0.1, 0.2, 0.3, 0.4, 0.7, 0.8, 0.4, 0.2, 0.1)
    ]
    summary = summarize(labels, trace)
    assert summary["stable_positive_frames"] == 1
    assert summary["stable_negative_frames"] == 2
    assert abs(float(summary["positive_probability_p50"]) - 0.7) < 1.0e-9
    assert abs(float(summary["negative_probability_p50"]) - 0.2) < 1.0e-9
    print("NS probability diagnostic self-test: OK")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--probe", type=Path)
    parser.add_argument("--corpus", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    for name in ("probe", "corpus", "output"):
        if getattr(args, name) is None:
            parser.error(f"--{name} is required")
    result = diagnose(args.probe.resolve(), args.corpus.resolve())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"cases": len(result["cases"]), "output": str(args.output)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
