#!/usr/bin/env python3
"""Diagnostic-only probe for large AEC route correlation ambiguity.

It intentionally mirrors the product SYNC squared-normalized-correlation idea but
never changes shipping thresholds or returns a promotion decision.
"""
from __future__ import annotations

import argparse
import array
import json
import math
import wave
from pathlib import Path

PEAK_RATIO = 1.01


def read_mono16(path: Path, max_seconds: float = 3.0) -> tuple[int, list[int]]:
    with wave.open(str(path), "rb") as w:
        if w.getnchannels() != 1 or w.getsampwidth() != 2 or w.getcomptype() != "NONE":
            raise ValueError(f"unsupported WAV geometry: {path}")
        rate = w.getframerate(); frames = min(w.getnframes(), int(rate * max_seconds)); raw = w.readframes(frames)
    values = array.array("h"); values.frombytes(raw)
    return rate, list(values)


def score(mic: list[int], render: list[int], delay: int, stride: int = 4) -> float:
    start = max(delay, 0); end = min(len(mic), len(render) + delay)
    xy = 0.0; xx = 1e-12; yy = 1e-12
    for i in range(start, end, stride):
        x = float(render[i - delay]); y = float(mic[i])
        xy += x * y; xx += x * x; yy += y * y
    return (xy * xy) / (xx * yy)


def analyze_samples(mic: list[int], render: list[int], rate: int, max_delay_ms: int, initial_delay_ms: float) -> dict:
    max_delay = max(1, max_delay_ms * rate // 1000); coarse = max(1, rate // 500)
    candidates = [(score(mic, render, d), d) for d in range(0, max_delay + 1, coarse)]
    best_score, best_delay = max(candidates)
    lo, hi = max(0, best_delay - coarse), min(max_delay, best_delay + coarse)
    for d in range(lo, hi + 1):
        value = score(mic, render, d)
        if value > best_score: best_score, best_delay = value, d
    guard = coarse
    runner = max((value for value, d in candidates if abs(d - best_delay) > guard), default=0.0)
    ratio = math.inf if runner <= 1e-12 else best_score / runner
    initial = int(round(initial_delay_ms * rate / 1000.0))
    large = abs(best_delay - initial) > rate // 50
    return {
        "best_delay_samples": best_delay,
        "best_delay_ms": 1000.0 * best_delay / rate,
        "initial_delay_samples": initial,
        "best_score_squared": best_score,
        "runner_up_score_squared": runner,
        "peak_ratio": None if math.isinf(ratio) else ratio,
        "large_route_candidate": large,
        "large_route_ambiguous": bool(large and ratio < PEAK_RATIO),
        "diagnostic_only": True,
    }


def analyze_case(mic_path: Path, render_path: Path, max_delay_ms: int, initial_delay_ms: float) -> dict:
    mic_rate, mic = read_mono16(mic_path); render_rate, render = read_mono16(render_path)
    if mic_rate != render_rate: raise ValueError("mic/render sample rate mismatch")
    return analyze_samples(mic, render, mic_rate, max_delay_ms, initial_delay_ms)


def self_test() -> None:
    rate = 16000
    state = 1
    render = []
    for _ in range(rate):
        state = (1664525 * state + 1013904223) & 0xffffffff
        render.append((((state >> 16) & 0xffff) - 32768) // 2)
    delay = 640
    mic = [0] * delay + render[:-delay]
    result = analyze_samples(mic, render, rate, 60, 40.0)
    assert abs(result["best_delay_samples"] - delay) <= 1
    assert result["best_score_squared"] > 0.99
    assert result["diagnostic_only"] is True
    print("AEC route ambiguity probe self-test: OK")


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--self-test", action="store_true")
    p.add_argument("--selection", type=Path); p.add_argument("--source-root", type=Path)
    p.add_argument("--max-delay-ms", type=int, default=60); p.add_argument("--initial-delay-ms", type=float, default=40.0)
    p.add_argument("--output", type=Path)
    args = p.parse_args()
    if args.self_test: self_test(); return 0
    if not args.selection or not args.source_root or not args.output: p.error("selection/source-root/output are required")
    selection = json.loads(args.selection.read_text(encoding="utf-8")); rows = []
    for item in selection["cases"]:
        result = analyze_case(args.source_root / item["mic"], args.source_root / item["render"], args.max_delay_ms, args.initial_delay_ms)
        result.update({"case_id": item["id"], "scenario": item["scenario"]}); rows.append(result)
    payload = {"schema_version": 1, "diagnostic_only": True, "cases": rows, "large_route_candidates": sum(x["large_route_candidate"] for x in rows), "ambiguous_large_route_candidates": sum(x["large_route_ambiguous"] for x in rows)}
    args.output.parent.mkdir(parents=True, exist_ok=True); args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "cases": len(rows), "ambiguous_large_route_candidates": payload["ambiguous_large_route_candidates"]}, sort_keys=True)); return 0


if __name__ == "__main__": raise SystemExit(main())
