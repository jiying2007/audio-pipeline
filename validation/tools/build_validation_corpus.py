#!/usr/bin/env python3
"""Build a small deterministic multi-scenario regression corpus.

The generated corpus intentionally has tier=regression. It exercises the same
validation engine used by public validation-grade corpora but can never be used
as product or validation-grade evidence.
"""

from __future__ import annotations

import argparse
import array
import json
import math
import os
import random
from pathlib import Path

RATE = 16000
FRAME = RATE // 100


def clamp16(value: float) -> int:
    return max(-32768, min(32767, int(round(value))))


def write_pcm(path: Path, samples: list[int]) -> None:
    values = array.array("h", samples)
    if os.sys.byteorder != "little":
        values.byteswap()
    path.write_bytes(values.tobytes())


def speech_like(frames: int, seed: int, active: list[tuple[float, float]], amplitude: float = 9000.0) -> tuple[list[int], list[int]]:
    rng = random.Random(seed)
    samples = frames * FRAME
    phases = [rng.random() * math.tau for _ in range(4)]
    freqs = [173.0, 311.0, 487.0, 733.0]
    out: list[int] = []
    labels: list[int] = []
    for frame_index in range(frames):
        t0 = frame_index / 100.0
        active_frame = any(start <= t0 < end for start, end in active)
        labels.append(1 if active_frame else 0)
        for j in range(FRAME):
            n = frame_index * FRAME + j
            if not active_frame:
                out.append(0)
                continue
            envelope = 0.62 + 0.28 * math.sin(math.tau * 3.1 * n / RATE)
            value = 0.0
            for k, freq in enumerate(freqs):
                value += math.sin(math.tau * freq * n / RATE + phases[k]) / (k + 1)
            out.append(clamp16(amplitude * envelope * value / 1.75))
    assert len(out) == samples
    return out, labels


def render_signal(samples: int, seed: int) -> list[int]:
    rng = random.Random(seed)
    phases = [rng.random() * math.tau for _ in range(3)]
    freqs = [229.0, 421.0, 887.0]
    out = []
    for n in range(samples):
        envelope = 0.72 + 0.22 * math.sin(math.tau * 1.7 * n / RATE)
        value = sum(math.sin(math.tau * f * n / RATE + phases[i]) / (i + 1)
                    for i, f in enumerate(freqs))
        out.append(clamp16(10500.0 * envelope * value / 1.55))
    return out


def echo_from_render(render: list[int], taps: list[tuple[int, float]]) -> list[int]:
    out = [0] * len(render)
    for n in range(len(render)):
        value = 0.0
        for delay, gain in taps:
            if n >= delay:
                value += gain * render[n - delay]
        out[n] = clamp16(value)
    return out


def mix(*signals: list[int]) -> list[int]:
    count = min(len(x) for x in signals)
    return [clamp16(sum(signal[i] for signal in signals)) for i in range(count)]


def noise(samples: int, seed: int, amplitude: float) -> list[int]:
    rng = random.Random(seed)
    previous = 0.0
    out = []
    for _ in range(samples):
        white = rng.uniform(-amplitude, amplitude)
        previous = 0.88 * previous + 0.12 * white
        out.append(clamp16(previous))
    return out


def interleave(left: list[int], right: list[int]) -> list[int]:
    out: list[int] = []
    for a, b in zip(left, right):
        out.extend((a, b))
    return out


def delayed(signal: list[int], samples: int) -> list[int]:
    if samples <= 0:
        return list(signal)
    return [0] * samples + signal[:-samples]


def write_labels(path: Path, labels: list[int]) -> None:
    path.write_text("".join(f"{value}\n" for value in labels), encoding="utf-8")


def add_case(cases: list[dict], output: Path, case_id: str, scenario: str,
             mic: list[int], channels: int, clean: list[int] | None = None,
             render: list[int] | None = None, echo: list[int] | None = None,
             labels: list[int] | None = None, expected: dict | None = None,
             control: dict | None = None, processor_profile: str = "default") -> None:
    case_dir = output / "cases" / case_id
    case_dir.mkdir(parents=True, exist_ok=True)
    mic_path = case_dir / "mic.pcm"
    write_pcm(mic_path, mic)
    case = {
        "case_id": case_id,
        "split": "validation",
        "scenario": scenario,
        "sample_rate_hz": RATE,
        "mic_channels": channels,
        "mic_audio": str(mic_path.relative_to(output)),
        "render_audio": None,
        "clean_near_audio": None,
        "echo_audio": None,
        "vad_labels": None,
        "control": control or {},
        "processor_profile": processor_profile,
        "expected": expected or {},
        "source": {"dataset_id": "deterministic-generator", "source_id": case_id},
    }
    if clean is not None:
        path = case_dir / "clean-near.pcm"
        write_pcm(path, clean)
        case["clean_near_audio"] = str(path.relative_to(output))
    if render is not None:
        path = case_dir / "render.pcm"
        write_pcm(path, render)
        case["render_audio"] = str(path.relative_to(output))
    if echo is not None:
        path = case_dir / "echo.pcm"
        write_pcm(path, echo)
        case["echo_audio"] = str(path.relative_to(output))
    if labels is not None:
        path = case_dir / "vad.labels"
        write_labels(path, labels)
        case["vad_labels"] = str(path.relative_to(output))
    cases.append(case)


def build(output: Path, seed: int, seconds: float) -> dict:
    frames = max(300, int(round(seconds * 100.0)))
    samples = frames * FRAME
    active = [(0.45, 1.55), (2.05, min(seconds - 0.25, 3.65))]
    clean, labels = speech_like(frames, seed + 1, active)
    render = render_signal(samples, seed + 2)
    echo_a = echo_from_render(render, [(320, 0.55), (640, 0.22), (1120, 0.10)])
    echo_b = echo_from_render(render, [(160, 0.42), (800, 0.31), (1440, 0.09)])
    stationary = noise(samples, seed + 3, 5200.0)
    mild_noise = noise(samples, seed + 4, 2300.0)
    cases: list[dict] = []

    add_case(cases, output, "clean-capture", "capture-clean", clean, 1,
             clean=clean, labels=labels,
             expected={"min_near_si_sdr_db": -8.0, "min_output_rms_dbfs": -50.0, "min_vad_f1": 0.25})

    add_case(cases, output, "ns-stationary", "ns-stationary", mix(clean, stationary), 1,
             clean=clean, labels=labels, processor_profile="ns-isolated",
             expected={"min_near_si_sdr_improvement_db": -4.0, "min_noise_only_attenuation_db": 1.0, "min_vad_f1": 0.20})

    add_case(cases, output, "aec-farend", "aec-farend", echo_a, 1,
             render=render, echo=echo_a,
             expected={"max_output_render_corr_ratio": 1.10, "min_erle_db": -3.0})

    add_case(cases, output, "aec-doubletalk", "aec-doubletalk", mix(clean, echo_a), 1,
             clean=clean, render=render, labels=labels,
             expected={"min_near_si_sdr_db": -12.0, "max_output_render_corr_ratio": 1.25})

    right = mix(delayed(clean, 2), noise(samples, seed + 5, 2100.0))
    left = mix(clean, mild_noise)
    add_case(cases, output, "bf-offaxis", "bf-offaxis", interleave(left, right), 2,
             clean=clean, labels=labels,
             expected={"min_near_si_sdr_db": -12.0, "min_vad_f1": 0.20})

    add_case(cases, output, "vad-nearend", "vad-nearend", clean, 1,
             clean=clean, labels=labels,
             expected={"min_vad_f1": 0.25, "min_output_rms_dbfs": -50.0})

    half = (frames // 2) * FRAME
    changing_echo = echo_a[:half] + echo_b[half:]
    add_case(cases, output, "aec-path-change", "aec-echo-path-change", changing_echo, 1,
             render=render, echo=changing_echo,
             control={"echo_path_change_frame": frames // 2},
             expected={"max_output_render_corr_ratio": 1.20, "min_erle_db": -4.0})

    gap_render = list(render)
    gap_start = frames // 2
    for i in range(gap_start * FRAME, min(samples, (gap_start + 8) * FRAME)):
        gap_render[i] = 0
    add_case(cases, output, "aec-render-gap", "aec-render-gap", echo_a, 1,
             render=gap_render, echo=echo_a,
             control={"discontinuity_frame": gap_start, "discontinuity_flags": 2, "discontinuity_lost_frames": 8},
             expected={"min_output_rms_dbfs": -100.0, "max_output_render_corr_ratio": 1.25})

    corpus = {
        "schema_version": 1,
        "corpus_id": f"validation-smoke-seed-{seed}",
        "tier": "regression",
        "generator": {"name": "build_validation_corpus.py", "version": 1, "seed": seed},
        "sources": ["deterministic-generator"],
        "sealed_data": True,
        "cases": cases,
    }
    (output / "corpus.json").write_text(json.dumps(corpus, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return corpus


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=1307)
    parser.add_argument("--seconds", type=float, default=4.0)
    args = parser.parse_args()
    if not 3.0 <= args.seconds <= 20.0:
        raise SystemExit("seconds must be 3..20")
    args.output.mkdir(parents=True, exist_ok=True)
    corpus = build(args.output, args.seed, args.seconds)
    print(json.dumps({"corpus": str(args.output / "corpus.json"), "cases": len(corpus["cases"])}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
