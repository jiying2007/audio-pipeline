#!/usr/bin/env python3
"""Build a deterministic multi-scenario regression corpus.

The generated corpus intentionally has tier=regression. It exercises the same
validation engine used by public validation-grade corpora but can never be used
as product or validation-grade evidence.

v3 expands the original smoke set with deterministic stress sweeps covering
non-stationary/impulsive noise, quiet speech, AEC delay and level envelopes,
double-talk balance, two-mic offset/noise variation, render gaps, near-end-only
full-duplex behavior and silence stability.
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


def speech_like(frames: int, seed: int, active: list[tuple[float, float]],
                amplitude: float = 9000.0) -> tuple[list[int], list[int]]:
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


def nonstationary_noise(samples: int, seed: int, amplitude: float) -> list[int]:
    base = noise(samples, seed, amplitude)
    out: list[int] = []
    for n, sample in enumerate(base):
        t = n / RATE
        slow = 0.18 + 0.82 * (0.5 + 0.5 * math.sin(math.tau * 0.73 * t + 0.31))
        phase = t % 1.1
        burst = 1.75 if 0.22 <= phase < 0.36 else 2.15 if 0.78 <= phase < 0.86 else 1.0
        out.append(clamp16(sample * slow * burst))
    return out


def impulsive_noise(samples: int, seed: int, amplitude: float) -> list[int]:
    rng = random.Random(seed)
    out = noise(samples, seed + 1, amplitude * 0.18)
    for frame in range(max(1, samples // FRAME)):
        if frame % 17 not in {3, 11}:
            continue
        offset = frame * FRAME + rng.randrange(max(1, FRAME - 12))
        polarity = -1.0 if rng.randrange(2) else 1.0
        for k in range(12):
            if offset + k < len(out):
                out[offset + k] = clamp16(
                    out[offset + k] + polarity * amplitude * math.exp(-0.38 * k)
                )
    return out


def scale(signal: list[int], gain: float) -> list[int]:
    return [clamp16(gain * sample) for sample in signal]


def rotate(signal: list[int], offset: int) -> list[int]:
    if not signal:
        return []
    offset %= len(signal)
    return signal[offset:] + signal[:offset]


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
    frames = max(400, int(round(seconds * 100.0)))
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

    ns_nonstationary = nonstationary_noise(samples, seed + 101, 6200.0)
    add_case(cases, output, "stress-ns-nonstationary", "ns-nonstationary",
             mix(clean, ns_nonstationary), 1, clean=clean, labels=labels,
             processor_profile="ns-isolated",
             expected={"min_near_si_sdr_improvement_db": -6.0,
                       "min_noise_only_attenuation_db": 0.25, "min_vad_f1": 0.15})

    quiet_clean, quiet_labels = speech_like(frames, seed + 102, active, amplitude=3600.0)
    quiet_noise = nonstationary_noise(samples, seed + 103, 2600.0)
    add_case(cases, output, "stress-ns-quiet-speech", "ns-quiet-speech",
             mix(quiet_clean, quiet_noise), 1, clean=quiet_clean, labels=quiet_labels,
             processor_profile="ns-isolated",
             expected={"min_near_si_sdr_db": -16.0,
                       "min_noise_only_attenuation_db": 0.15, "min_vad_f1": 0.08})

    clicks = impulsive_noise(samples, seed + 104, 12500.0)
    add_case(cases, output, "stress-ns-impulsive", "ns-impulsive",
             mix(clean, clicks), 1, clean=clean, labels=labels,
             processor_profile="ns-isolated",
             expected={"min_near_si_sdr_db": -18.0, "min_vad_f1": 0.10})

    for delay_ms in (10, 30, 60, 90):
        delay_samples = RATE * delay_ms // 1000
        echo = echo_from_render(
            render,
            [(delay_samples, 0.54), (delay_samples + 160, 0.20), (delay_samples + 400, 0.08)],
        )
        add_case(cases, output, f"stress-aec-delay-{delay_ms}ms", "aec-delay-sweep",
                 echo, 1, render=render, echo=echo,
                 expected={"max_output_render_corr_ratio": 1.40, "min_erle_db": -6.0})

    base_echo = echo_from_render(render, [(320, 0.50), (720, 0.18), (1280, 0.08)])
    for name, near_gain in (("quiet", 0.45), ("nominal", 0.90), ("strong", 1.25)):
        near = scale(clean, near_gain)
        add_case(cases, output, f"stress-doubletalk-{name}", "aec-doubletalk-balance",
                 mix(near, base_echo), 1, clean=near, render=render, labels=labels,
                 expected={"min_near_si_sdr_db": -18.0,
                           "max_output_render_corr_ratio": 1.55})

    bf_noise = noise(samples, seed + 105, 2600.0)
    for offset, noise_gain in ((1, 0.18), (3, 0.36), (5, 0.54)):
        left = mix(clean, scale(bf_noise, noise_gain))
        right = mix(delayed(clean, offset), scale(rotate(bf_noise, 137 + offset), noise_gain))
        add_case(cases, output, f"stress-bf-offset-{offset}", "bf-delay-noise-sweep",
                 interleave(left, right), 2, clean=clean, labels=labels,
                 expected={"min_near_si_sdr_db": -18.0, "min_vad_f1": 0.10})

    recovery_echo = echo_from_render(render, [(320, 0.52), (800, 0.21), (1360, 0.08)])
    for lost_frames in (1, 4, 12):
        stress_render = list(render)
        start = gap_start * FRAME
        end = min(samples, (gap_start + lost_frames) * FRAME)
        for index in range(start, end):
            stress_render[index] = 0
        add_case(cases, output, f"stress-render-gap-{lost_frames}", "aec-render-gap-sweep",
                 recovery_echo, 1, render=stress_render, echo=recovery_echo,
                 control={"discontinuity_frame": gap_start, "discontinuity_flags": 2,
                          "discontinuity_lost_frames": lost_frames},
                 expected={"max_output_render_corr_ratio": 1.55,
                           "min_output_rms_dbfs": -110.0})

    silent_render = [0] * samples
    add_case(cases, output, "stress-nearend-silent-render", "aec-nearend-only",
             clean, 1, clean=clean, render=silent_render, labels=labels,
             expected={"min_near_si_sdr_db": -12.0, "min_vad_f1": 0.15})

    low_echo = scale(echo_from_render(render, [(320, 0.34), (960, 0.10)]), 0.55)
    add_case(cases, output, "stress-aec-low-level", "aec-low-level-farend",
             low_echo, 1, render=render, echo=low_echo,
             expected={"max_output_render_corr_ratio": 1.60, "min_erle_db": -7.0})

    silence = [0] * samples
    add_case(cases, output, "stress-silence", "capture-silence",
             silence, 1, clean=silence, processor_profile="ns-isolated",
             expected={"max_output_rms_dbfs": -100.0})

    corpus = {
        "schema_version": 1,
        "corpus_id": f"validation-smoke-seed-{seed}",
        "tier": "regression",
        "generator": {"name": "build_validation_corpus.py", "version": 3, "seed": seed},
        "sources": ["deterministic-generator"],
        "sealed_data": True,
        "cases": cases,
    }
    (output / "corpus.json").write_text(
        json.dumps(corpus, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return corpus


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=1307)
    parser.add_argument("--seconds", type=float, default=4.0)
    args = parser.parse_args()
    if not 4.0 <= args.seconds <= 20.0:
        raise SystemExit("seconds must be 4..20")
    args.output.mkdir(parents=True, exist_ok=True)
    corpus = build(args.output, args.seed, args.seconds)
    if len(corpus["cases"]) < 24:
        raise SystemExit("regression corpus unexpectedly small")
    print(json.dumps({"corpus": str(args.output / "corpus.json"),
                      "cases": len(corpus["cases"])}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
