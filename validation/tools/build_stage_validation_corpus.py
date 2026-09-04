#!/usr/bin/env python3
"""Build deterministic stage-isolated regression corpora.

This corpus complements the full-pipeline regression corpus. It deliberately
routes capture-only cases through isolated VAD, NS, AGC and beamformer profiles
so a regression can be attributed to one stage before full-pipeline replay.
It is always tier=regression and is never shipping evidence.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from build_validation_corpus import (
    FRAME,
    RATE,
    add_case,
    delayed,
    impulsive_noise,
    interleave,
    mix,
    noise,
    nonstationary_noise,
    rotate,
    scale,
    speech_like,
)


def build(output: Path, seed: int, seconds: float) -> dict:
    frames = max(400, int(round(seconds * 100.0)))
    samples = frames * FRAME
    active = [(0.45, 1.55), (2.05, min(seconds - 0.25, 3.65))]
    clean, labels = speech_like(frames, seed + 1, active)
    quiet_clean, quiet_labels = speech_like(frames, seed + 2, active, amplitude=3600.0)
    stationary = noise(samples, seed + 3, 4800.0)
    nonstationary = nonstationary_noise(samples, seed + 4, 5600.0)
    hard_negative = impulsive_noise(samples, seed + 5, 12500.0)
    zeros = [0] * frames
    cases: list[dict] = []

    # VAD: measure speech decisions without NS/AGC/BF changing the input first.
    add_case(
        cases, output, "stage-vad-clean", "stage-vad-clean",
        clean, 1, clean=clean, labels=labels, processor_profile="vad-isolated",
        expected={
            "min_vad_f1": 0.25,
            "min_vad_recall": 0.20,
            "max_vad_false_positive_rate": 0.25,
        },
    )
    add_case(
        cases, output, "stage-vad-quiet", "stage-vad-quiet",
        quiet_clean, 1, clean=quiet_clean, labels=quiet_labels,
        processor_profile="vad-isolated",
        expected={"min_vad_f1": 0.10},
    )
    add_case(
        cases, output, "stage-vad-stationary-negative", "stage-vad-hard-negative",
        stationary, 1, labels=zeros, processor_profile="vad-isolated",
    )
    add_case(
        cases, output, "stage-vad-impulsive-negative", "stage-vad-hard-negative",
        hard_negative, 1, labels=zeros, processor_profile="vad-isolated",
    )

    # NS: preserve the existing NS+VAD profile because VAD consumes the NS speech
    # probability; clean reference and labels let the canonical evaluator score
    # both suppression and speech preservation.
    add_case(
        cases, output, "stage-ns-stationary", "stage-ns-stationary",
        mix(clean, stationary), 1, clean=clean, labels=labels,
        processor_profile="ns-isolated",
        expected={
            "min_near_si_sdr_improvement_db": -4.0,
            "min_noise_only_attenuation_db": 0.75,
            "min_vad_f1": 0.15,
        },
    )
    add_case(
        cases, output, "stage-ns-nonstationary", "stage-ns-nonstationary",
        mix(clean, nonstationary), 1, clean=clean, labels=labels,
        processor_profile="ns-isolated",
        expected={
            "min_near_si_sdr_improvement_db": -6.0,
            "min_noise_only_attenuation_db": 0.20,
            "min_vad_f1": 0.10,
        },
    )

    # AGC: low-level material must gain energy while hot material must stay below
    # the PCM clipping threshold. The cases are isolated so NS/BF cannot mask AGC.
    low = scale(clean, 0.22)
    hot = scale(clean, 2.8)
    add_case(
        cases, output, "stage-agc-low", "stage-agc-low-level",
        low, 1, clean=low, processor_profile="agc-isolated",
        expected={
            "min_output_rms_delta_db": 2.0,
            "max_output_clip_fraction": 0.001,
        },
    )
    add_case(
        cases, output, "stage-agc-hot", "stage-agc-hot-level",
        hot, 1, clean=hot, processor_profile="agc-isolated",
        expected={"max_output_clip_fraction": 0.001},
    )

    # Beamformer: two deterministic geometry/noise conditions with the clean left
    # channel as reference. Same-rate capture keeps resampler effects negligible.
    bf_noise = noise(samples, seed + 6, 2500.0)
    left = mix(clean, scale(bf_noise, 0.30))
    right = mix(delayed(clean, 2), scale(rotate(bf_noise, 137), 0.30))
    add_case(
        cases, output, "stage-bf-coherent", "stage-bf-coherent",
        interleave(left, right), 2, clean=clean, processor_profile="bf-isolated",
        expected={"min_near_si_sdr_db": -12.0},
    )
    left_hard = mix(clean, scale(bf_noise, 0.55))
    right_hard = mix(delayed(clean, 5), scale(rotate(bf_noise, 271), 0.70))
    add_case(
        cases, output, "stage-bf-mismatch", "stage-bf-mismatch",
        interleave(left_hard, right_hard), 2, clean=clean,
        processor_profile="bf-isolated",
        expected={"min_near_si_sdr_db": -18.0},
    )

    corpus = {
        "schema_version": 1,
        "corpus_id": f"stage-isolation-seed-{seed}",
        "tier": "regression",
        "generator": {
            "name": "build_stage_validation_corpus.py",
            "version": 1,
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
    if len(corpus["cases"]) < 10:
        raise SystemExit("stage-isolation corpus unexpectedly small")
    print(json.dumps({
        "corpus": str(args.output / "corpus.json"),
        "cases": len(corpus["cases"]),
        "seed": args.seed,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
