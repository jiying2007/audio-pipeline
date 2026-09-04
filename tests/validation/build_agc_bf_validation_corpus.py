#!/usr/bin/env python3
"""Build deterministic AGC dynamics and two-mic beamformer stress cases.

This corpus is regression authority only. It deliberately extends the broad
stage corpus with dynamic AGC envelopes and harder two-mic geometry so future
parameter/algorithm candidates can be attributed to AGC or BF before they are
replayed through the complete product pipeline.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from build_validation_corpus import (
    FRAME,
    RATE,
    add_case,
    clamp16,
    delayed,
    interleave,
    mix,
    noise,
    rotate,
    scale,
    speech_like,
)


def sine_frames(frames: int, amplitude_by_frame) -> list[int]:
    out: list[int] = []
    for frame_index in range(frames):
        amplitude = float(amplitude_by_frame(frame_index)) * 32767.0
        for offset in range(FRAME):
            sample = frame_index * FRAME + offset
            carrier = 0.78 * math.sin(math.tau * 431.0 * sample / RATE)
            carrier += 0.22 * math.sin(math.tau * 887.0 * sample / RATE + 0.37)
            out.append(clamp16(amplitude * carrier))
    return out


def transient_signal(frames: int) -> list[int]:
    out = sine_frames(frames, lambda _: 0.045)
    for frame_index in range(20, frames, 37):
        base = frame_index * FRAME + 23
        for offset in range(8):
            if base + offset >= len(out):
                break
            impulse = 0.95 * 32767.0 * math.exp(-0.52 * offset)
            out[base + offset] = clamp16(out[base + offset] + impulse)
    return out


def add_dimensions(cases: list[dict], case_id: str, **dimensions) -> None:
    case = next(item for item in cases if item["case_id"] == case_id)
    case["dimensions"] = dimensions


def switched_delay(clean: list[int], delay_samples: int) -> tuple[list[int], list[int]]:
    half = len(clean) // 2
    delayed_clean = delayed(clean, delay_samples)
    left = clean[:half] + delayed_clean[half:]
    right = delayed_clean[:half] + clean[half:]
    return left, right


def build(output: Path, seed: int) -> dict:
    frames = 600
    samples = frames * FRAME
    cases: list[dict] = []

    low = sine_frames(frames, lambda _: 0.020)
    hot = sine_frames(frames, lambda _: 0.650)
    step = sine_frames(
        frames,
        lambda frame: 0.020 if frame < 200 or frame >= 300 else 0.650,
    )
    transients = transient_signal(frames)

    add_case(
        cases, output, "agc-steady-low", "agc-steady-low",
        low, 1, processor_profile="agc-isolated",
        expected={
            "min_output_rms_delta_db": 10.0,
            "max_output_clip_fraction": 0.001,
        },
    )
    add_dimensions(cases, "agc-steady-low", agc_target_dbfs=-20.0, limiter_dbfs=-2.0)

    add_case(
        cases, output, "agc-steady-hot", "agc-steady-hot",
        hot, 1, processor_profile="agc-isolated",
        expected={
            "max_output_rms_dbfs": -15.0,
            "max_output_clip_fraction": 0.001,
        },
    )
    add_dimensions(cases, "agc-steady-hot", agc_target_dbfs=-20.0, limiter_dbfs=-2.0)

    add_case(
        cases, output, "agc-level-step", "agc-level-step",
        step, 1, processor_profile="agc-isolated",
        expected={"max_output_clip_fraction": 0.001},
    )
    add_dimensions(
        cases, "agc-level-step",
        agc_target_dbfs=-20.0,
        limiter_dbfs=-2.0,
        low_to_hot_frame=200,
        hot_to_low_frame=300,
    )

    add_case(
        cases, output, "agc-transient", "agc-transient",
        transients, 1, processor_profile="agc-isolated",
        expected={"max_output_clip_fraction": 0.001},
    )
    add_dimensions(cases, "agc-transient", agc_target_dbfs=-20.0, limiter_dbfs=-2.0)

    clean, _ = speech_like(frames, seed + 1, [(0.0, 6.0)], amplitude=9000.0)
    n0 = noise(samples, seed + 2, 2800.0)
    n1 = rotate(noise(samples, seed + 3, 2800.0), 173)

    left = mix(clean, scale(n0, 0.45))
    right = mix(delayed(clean, 3), scale(n1, 0.45))
    add_case(
        cases, output, "bf-edge-positive", "bf-edge-positive",
        interleave(left, right), 2, clean=clean, processor_profile="bf-isolated",
        expected={"min_near_si_sdr_improvement_db": 1.5},
    )
    add_dimensions(cases, "bf-edge-positive", tdoa_samples=3, mic_gain_ratio=1.0)

    left = mix(delayed(clean, 3), scale(n0, 0.45))
    right = mix(clean, scale(n1, 0.45))
    add_case(
        cases, output, "bf-edge-negative", "bf-edge-negative",
        interleave(left, right), 2, clean=clean, processor_profile="bf-isolated",
        expected={"min_near_si_sdr_improvement_db": 1.5},
    )
    add_dimensions(cases, "bf-edge-negative", tdoa_samples=-3, mic_gain_ratio=1.0)

    switched_left, switched_right = switched_delay(clean, 2)
    left = mix(switched_left, scale(n0, 0.40))
    right = mix(switched_right, scale(n1, 0.40))
    add_case(
        cases, output, "bf-direction-switch", "bf-direction-switch",
        interleave(left, right), 2, clean=clean, processor_profile="bf-isolated",
        expected={"min_near_si_sdr_improvement_db": 7.0},
    )
    add_dimensions(cases, "bf-direction-switch", tdoa_samples=2, direction_switch_frame=300)

    left = mix(clean, scale(n0, 0.55))
    right = mix(scale(delayed(clean, 2), 0.55), scale(n1, 0.55))
    add_case(
        cases, output, "bf-gain-mismatch", "bf-gain-mismatch",
        interleave(left, right), 2, clean=clean, processor_profile="bf-isolated",
        expected={"min_near_si_sdr_improvement_db": 0.0},
    )
    add_dimensions(cases, "bf-gain-mismatch", tdoa_samples=2, mic_gain_ratio=0.55)

    strong0 = noise(samples, seed + 4, 5200.0)
    strong1 = rotate(noise(samples, seed + 5, 5200.0), 311)
    left = mix(clean, strong0)
    right = mix(delayed(clean, 2), strong1)
    add_case(
        cases, output, "bf-diffuse-noise", "bf-diffuse-noise",
        interleave(left, right), 2, clean=clean, processor_profile="bf-isolated",
        expected={"min_near_si_sdr_improvement_db": 2.0},
    )
    add_dimensions(cases, "bf-diffuse-noise", tdoa_samples=2, mic_gain_ratio=1.0)

    corpus = {
        "schema_version": 1,
        "corpus_id": f"agc-bf-stage-seed-{seed}",
        "tier": "regression",
        "generator": {
            "name": "build_agc_bf_validation_corpus.py",
            "version": 2,
            "seed": seed,
        },
        "sources": ["deterministic-generator"],
        "sealed_data": True,
        "cases": cases,
    }
    output.mkdir(parents=True, exist_ok=True)
    (output / "corpus.json").write_text(
        json.dumps(corpus, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return corpus


def self_test() -> None:
    import tempfile
    with tempfile.TemporaryDirectory(prefix="ap-agc-bf-corpus-") as temporary:
        corpus = build(Path(temporary), 1307)
        assert len(corpus["cases"]) == 9
        assert sum(case["processor_profile"] == "agc-isolated" for case in corpus["cases"]) == 4
        assert sum(case["processor_profile"] == "bf-isolated" for case in corpus["cases"]) == 5
        by_id = {case["case_id"]: case for case in corpus["cases"]}
        assert by_id["bf-edge-positive"]["expected"]["min_near_si_sdr_improvement_db"] == 1.5
        assert by_id["bf-direction-switch"]["expected"]["min_near_si_sdr_improvement_db"] == 7.0
        assert by_id["bf-gain-mismatch"]["expected"]["min_near_si_sdr_improvement_db"] == 0.0
        assert by_id["bf-diffuse-noise"]["expected"]["min_near_si_sdr_improvement_db"] == 2.0
    print("AGC/BF validation corpus self-test: OK")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    parser.add_argument("--seed", type=int, default=1307)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    if args.output is None:
        parser.error("--output is required")
    corpus = build(args.output, args.seed)
    print(json.dumps({
        "corpus": str(args.output / "corpus.json"),
        "cases": len(corpus["cases"]),
        "seed": args.seed,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
