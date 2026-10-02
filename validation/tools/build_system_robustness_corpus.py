#!/usr/bin/env python3
"""Build deterministic candidate-zero S001 system-robustness corpus."""

from __future__ import annotations

import argparse
import json
import math
import tempfile
from pathlib import Path

from build_validation_corpus import (
    FRAME, RATE, add_case, clamp16, delayed, echo_from_render, interleave,
    mix, noise, nonstationary_noise, render_signal, rotate, scale, speech_like,
)

GENERATOR_VERSION = 1


def rms(x: list[int]) -> float:
    return math.sqrt(sum(float(v) * v for v in x) / max(1, len(x)))


def mix_at_snr(clean: list[int], n: list[int], snr_db: float) -> list[int]:
    cr, nr = rms(clean), rms(n)
    gain = 0.0 if nr == 0.0 else cr / (nr * (10.0 ** (snr_db / 20.0)))
    return mix(clean, scale(n, gain))


def hard_clip(x: list[int], limit: int) -> list[int]:
    return [max(-limit, min(limit, v)) for v in x]


def dc_offset(x: list[int], offset: int) -> list[int]:
    return [clamp16(v + offset) for v in x]


def sample_slip(x: list[int], period: int, duplicate: bool) -> list[int]:
    out: list[int] = []
    for i, value in enumerate(x):
        if i and i % period == 0:
            if duplicate and out:
                out.append(out[-1])
            elif not duplicate:
                continue
        out.append(value)
    if len(out) < len(x):
        out.extend([out[-1] if out else 0] * (len(x) - len(out)))
    return out[:len(x)]


def frame_glitch(x: list[int], frame_index: int, duplicate: bool) -> list[int]:
    out = list(x)
    start = frame_index * FRAME
    end = min(len(out), start + FRAME)
    if start >= len(out):
        return out
    if duplicate and start >= FRAME:
        out[start:end] = out[start-FRAME:start-FRAME+(end-start)]
    else:
        out[start:end] = [0] * (end - start)
    return out


def motor_noise(samples: int, transient: bool) -> list[int]:
    out: list[int] = []
    for n in range(samples):
        t = n / RATE
        env = 0.20 + 0.80 * min(1.0, t / 0.35)
        value = env * (
            2600.0 * math.sin(math.tau * 120.0 * t)
            + 1500.0 * math.sin(math.tau * 240.0 * t + 0.3)
            + 800.0 * math.sin(math.tau * 360.0 * t + 0.7)
        )
        if transient:
            phase = t % 1.4
            if phase < 0.035:
                value += 9000.0 * math.exp(-70.0 * phase)
        out.append(clamp16(value))
    return out


def annotate(cases: list[dict], dimensions: dict) -> None:
    cases[-1]["dimensions"] = dimensions


def build(output: Path, seed: int, seconds: float) -> dict:
    frames = max(500, int(round(seconds * 100.0)))
    samples = frames * FRAME
    active = [(0.45, 1.65), (2.15, min(seconds - 0.25, 4.25))]
    clean, labels = speech_like(frames, seed + 1, active)
    base_noise = nonstationary_noise(samples, seed + 2, 6000.0)
    render = render_signal(samples, seed + 3)
    echo_a = echo_from_render(render, [(320, 0.52), (704, 0.20), (1248, 0.08)])
    echo_b = echo_from_render(render, [(176, 0.45), (864, 0.28), (1488, 0.07)])
    cases: list[dict] = []

    for snr_db in (-5.0, 0.0, 10.0):
        add_case(
            cases, output, f"snr-{int(snr_db)}", "system-snr",
            mix_at_snr(clean, base_noise, snr_db), 1, clean=clean, labels=labels,
        )
        annotate(cases, {"family": "snr", "snr_db": snr_db})

    half = (frames // 2) * FRAME
    changing = echo_a[:half] + echo_b[half:]
    add_case(
        cases, output, "echo-path-change", "system-aec-echo-path-change",
        changing, 1, render=render, echo=changing,
        control={"echo_path_change_frame": frames // 2},
    )
    annotate(cases, {"family": "aec", "transition": "echo_path_change"})

    near = scale(clean, 0.9)
    add_case(
        cases, output, "double-talk", "system-aec-double-talk",
        mix(near, echo_a), 1, clean=near, render=render, labels=labels,
    )
    annotate(cases, {"family": "aec", "talk_state": "double_talk"})

    stereo_noise = noise(samples, seed + 4, 2200.0)
    left = mix(clean, scale(stereo_noise, 0.25))
    right = mix(scale(delayed(clean, 3), 0.72), scale(rotate(stereo_noise, 137), 0.38))
    add_case(
        cases, output, "mic-gain-delay-mismatch", "system-mic-mismatch",
        interleave(left, right), 2, clean=clean, labels=labels,
    )
    annotate(cases, {"family": "mic_mismatch", "right_gain": 0.72, "delay_samples": 3})

    clipped = hard_clip(mix(clean, scale(base_noise, 0.35)), 7000)
    add_case(
        cases, output, "capture-clipping", "system-capture-clipping",
        clipped, 1, clean=clean, labels=labels,
    )
    annotate(cases, {"family": "capture", "clip_limit": 7000})

    biased = dc_offset(mix(clean, scale(base_noise, 0.18)), 1200)
    add_case(
        cases, output, "capture-dc-offset", "system-capture-dc-offset",
        biased, 1, clean=clean, labels=labels,
    )
    annotate(cases, {"family": "capture", "dc_offset_lsb": 1200})

    for duplicate in (False, True):
        name = "duplicate" if duplicate else "drop"
        slipped = sample_slip(clean, 997, duplicate)
        add_case(
            cases, output, f"clock-slip-{name}", "system-clock-drift-proxy",
            slipped, 1, clean=clean, labels=labels,
        )
        annotate(
            cases,
            {"family": "clock_drift_proxy", "sample_slip_period": 997, "mode": name},
        )

    glitch_frame = frames // 2
    for duplicate in (False, True):
        name = "duplicate" if duplicate else "drop"
        glitched = frame_glitch(clean, glitch_frame, duplicate)
        add_case(
            cases, output, f"frame-{name}", "system-frame-timing",
            glitched, 1, clean=clean, labels=labels,
            control={
                "discontinuity_frame": glitch_frame,
                "discontinuity_flags": 2,
                "discontinuity_lost_frames": 1,
            },
        )
        annotate(cases, {"family": "frame_timing", "mode": name, "frame": glitch_frame})

    for transient in (False, True):
        tag = "transient" if transient else "steady"
        m = motor_noise(samples, transient)
        add_case(
            cases, output, f"robot-motor-{tag}", "system-robot-motion-noise",
            mix(clean, m), 1, clean=clean, labels=labels,
        )
        annotate(
            cases,
            {"family": "robot_motion_noise", "kind": tag, "harmonics_hz": "120,240,360"},
        )

    room = echo_from_render(clean, [(0, 0.72), (83, 0.16), (211, 0.08), (397, 0.04)])
    add_case(
        cases, output, "tapped-room-proxy", "system-room-proxy",
        room, 1, clean=clean, labels=labels,
    )
    annotate(cases, {"family": "room_proxy", "taps_samples": "0,83,211,397"})

    corpus = {
        "schema_version": 1,
        "corpus_id": f"system-robustness-s001-seed-{seed}",
        "tier": "regression",
        "generator": {
            "name": "build_system_robustness_corpus.py",
            "version": GENERATOR_VERSION,
            "seed": seed,
        },
        "sources": ["deterministic-generator"],
        "sealed_data": True,
        "candidate_limit": 0,
        "confirmation_limit": 0,
        "cases": cases,
    }
    output.mkdir(parents=True, exist_ok=True)
    (output / "corpus.json").write_text(
        json.dumps(corpus, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return corpus


def self_test() -> None:
    with tempfile.TemporaryDirectory() as td:
        c = build(Path(td), 5107, 5.0)
        assert c["candidate_limit"] == c["confirmation_limit"] == 0
        assert len(c["cases"]) >= 14
        families = {x["dimensions"]["family"] for x in c["cases"]}
        required = {
            "snr", "aec", "mic_mismatch", "capture", "clock_drift_proxy",
            "frame_timing", "robot_motion_noise", "room_proxy",
        }
        assert required <= families
        assert len({x["case_id"] for x in c["cases"]}) == len(c["cases"])
    print("S001 system robustness corpus self-test: OK")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    parser.add_argument("--seed", type=int, default=5107)
    parser.add_argument("--seconds", type=float, default=5.0)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    if args.output is None:
        parser.error("--output is required")
    if not 5.0 <= args.seconds <= 20.0:
        raise SystemExit("seconds must be 5..20")
    corpus = build(args.output, args.seed, args.seconds)
    print(json.dumps({
        "corpus": str(args.output / "corpus.json"),
        "cases": len(corpus["cases"]),
        "seed": args.seed,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
