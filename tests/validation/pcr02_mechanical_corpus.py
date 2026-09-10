#!/usr/bin/env python3
"""Build deterministic PCR02-like mechanical NS/VAD counterfactual corpus.

The signals are synthetic development stress only. They model tonal/harmonic and
transient structure but are not PCR02 real evidence and cannot promote shipping.
"""
from __future__ import annotations

import argparse
import json
import math
import random
from pathlib import Path

from build_validation_corpus import RATE, FRAME, add_case, clamp16, mix, noise, speech_like

SECONDS = 6
FRAMES = SECONDS * 100
SAMPLES = FRAMES * FRAME
CLASSES = (
    "motor-tonal",
    "pwm-harmonic",
    "acceleration-chirp",
    "braking-chirp",
    "servo-burst",
    "floor-impact",
)


def harmonic(samples: int, fundamental: float, amplitude: float,
             harmonics: tuple[float, ...], modulation_hz: float = 0.0) -> list[int]:
    out = []
    for n in range(samples):
        t = n / RATE
        mod = 0.72 + 0.28 * math.sin(math.tau * modulation_hz * t) if modulation_hz else 1.0
        value = 0.0
        for index, weight in enumerate(harmonics, start=1):
            value += weight * math.sin(math.tau * fundamental * index * t + 0.17 * index)
        out.append(clamp16(amplitude * mod * value))
    return out


def chirp(samples: int, start_hz: float, end_hz: float, amplitude: float) -> list[int]:
    out = []
    duration = samples / RATE
    slope = (end_hz - start_hz) / max(duration, 1e-9)
    for n in range(samples):
        t = n / RATE
        phase = math.tau * (start_hz * t + 0.5 * slope * t * t)
        carrier = math.sin(phase) + 0.42 * math.sin(2.0 * phase + 0.3)
        out.append(clamp16(amplitude * carrier))
    return out


def servo_burst(samples: int) -> list[int]:
    out = []
    for n in range(samples):
        t = n / RATE
        phase = t % 1.25
        active = 0.12 <= phase < 0.38
        envelope = math.sin(math.pi * (phase - 0.12) / 0.26) ** 2 if active else 0.0
        value = math.sin(math.tau * 430.0 * t) + 0.45 * math.sin(math.tau * 860.0 * t + 0.2)
        out.append(clamp16(5200.0 * envelope * value))
    return out


def floor_impact(samples: int, seed: int) -> list[int]:
    rng = random.Random(seed)
    out = noise(samples, seed + 1, 650.0)
    for frame in range(FRAMES):
        if frame % 37 not in {5, 19}:
            continue
        offset = frame * FRAME + rng.randrange(max(1, FRAME - 40))
        polarity = -1.0 if rng.randrange(2) else 1.0
        for k in range(40):
            if offset + k >= samples:
                break
            ring = math.exp(-0.09 * k) * math.cos(0.43 * k)
            out[offset + k] = clamp16(out[offset + k] + polarity * 12500.0 * ring)
    return out


def mechanical(kind: str, seed: int) -> list[int]:
    if kind == "motor-tonal":
        return harmonic(SAMPLES, 185.0, 3600.0, (1.0, 0.55, 0.32, 0.18), 1.7)
    if kind == "pwm-harmonic":
        return harmonic(SAMPLES, 960.0, 2200.0, (1.0, 0.48, 0.22), 0.91)
    if kind == "acceleration-chirp":
        return chirp(SAMPLES, 120.0, 520.0, 3200.0)
    if kind == "braking-chirp":
        return chirp(SAMPLES, 520.0, 95.0, 3600.0)
    if kind == "servo-burst":
        return servo_burst(SAMPLES)
    if kind == "floor-impact":
        return floor_impact(SAMPLES, seed)
    raise ValueError(kind)


def build(output: Path, seed: int) -> dict:
    output.mkdir(parents=True, exist_ok=True)
    clean, labels = speech_like(
        FRAMES, seed + 101,
        [(0.55, 1.55), (2.25, 3.55), (4.25, 5.55)],
        amplitude=7200.0,
    )
    cases: list[dict] = []
    for index, kind in enumerate(CLASSES):
        mech = mechanical(kind, seed + 1000 + index)
        add_case(
            cases, output, f"{kind}-noise-only", "pcr02-like-mechanical-noise-only",
            mech, 1, labels=[0] * FRAMES, processor_profile="ns-isolated",
            expected={},
        )
        cases[-1]["dimensions"] = {
            "mechanical_class": kind,
            "speech_present": False,
            "synthetic_product_proxy": True,
        }

        speech_mix = mix(clean, mech)
        add_case(
            cases, output, f"{kind}-speech-mix", "pcr02-like-mechanical-speech-mix",
            speech_mix, 1, clean=clean, labels=labels,
            processor_profile="ns-isolated", expected={},
        )
        cases[-1]["dimensions"] = {
            "mechanical_class": kind,
            "speech_present": True,
            "synthetic_product_proxy": True,
        }

    corpus = {
        "schema_version": 1,
        "corpus_id": f"pcr02-mechanical-counterfactual-seed-{seed}",
        "tier": "regression",
        "generator": {"name": "pcr02_mechanical_corpus.py", "version": 1, "seed": seed},
        "sources": ["deterministic-generator"],
        "sealed_data": True,
        "authority": "diagnostic-regression-only",
        "real_pcr02_evidence": False,
        "promotion_allowed": False,
        "cases": cases,
    }
    (output / "corpus.json").write_text(json.dumps(corpus, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return corpus


def self_test() -> None:
    import tempfile
    with tempfile.TemporaryDirectory(prefix="pcr02-mechanical-") as tmp:
        corpus = build(Path(tmp), 5107)
        assert len(corpus["cases"]) == 2 * len(CLASSES) == 12
        assert {case["dimensions"]["mechanical_class"] for case in corpus["cases"]} == set(CLASSES)
        assert sum(bool(case["dimensions"]["speech_present"]) for case in corpus["cases"]) == len(CLASSES)
        assert all(case["processor_profile"] == "ns-isolated" for case in corpus["cases"])
        assert corpus["real_pcr02_evidence"] is False
        assert corpus["promotion_allowed"] is False
    print("PCR02 mechanical counterfactual corpus self-test: OK")


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--output", type=Path)
    p.add_argument("--seed", type=int, default=5107)
    p.add_argument("--self-test", action="store_true")
    args = p.parse_args()
    if args.self_test:
        self_test()
        return 0
    if args.output is None:
        p.error("--output is required")
    corpus = build(args.output, args.seed)
    print(json.dumps({
        "corpus": str(args.output / "corpus.json"),
        "cases": len(corpus["cases"]),
        "classes": list(CLASSES),
        "real_pcr02_evidence": False,
        "promotion_allowed": False,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
