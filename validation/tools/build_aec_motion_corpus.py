#!/usr/bin/env python3
"""Build a deterministic continuous-motion AEC development corpus.

The corpus is deliberately tier=regression and split=dev. It is suitable for
candidate discovery and regression testing, never for blind/release/shipping
authority. Echo paths change smoothly without calling the product's explicit
echo-path-change notification, so the cases exercise continuous tracking rather
than reset/recovery behavior.
"""

from __future__ import annotations

import argparse
import array
import hashlib
import json
import math
import os
import random
import tempfile
from pathlib import Path

RATE = 16000
FRAME = RATE // 100
DEFAULT_SECONDS = 8.0


def clamp16(value: float) -> int:
    return max(-32768, min(32767, int(round(value))))


def write_pcm(path: Path, values: list[int]) -> None:
    data = array.array("h", values)
    if os.sys.byteorder != "little":
        data.byteswap()
    path.write_bytes(data.tobytes())


def smoothstep(x: float) -> float:
    x = max(0.0, min(1.0, x))
    return x * x * (3.0 - 2.0 * x)


def interpolate(knots: list[float], position: float) -> float:
    if len(knots) == 1:
        return knots[0]
    scaled = max(0.0, min(0.999999999, position)) * (len(knots) - 1)
    index = int(scaled)
    frac = smoothstep(scaled - index)
    return knots[index] * (1.0 - frac) + knots[index + 1] * frac


def sample(signal: list[int], position: float) -> float:
    if position < 0.0:
        return 0.0
    base = int(position)
    if base + 1 >= len(signal):
        return 0.0
    frac = position - base
    return signal[base] * (1.0 - frac) + signal[base + 1] * frac


def render_signal(samples: int, seed: int) -> list[int]:
    rng = random.Random(seed)
    phases = [rng.random() * math.tau for _ in range(5)]
    freqs = [173.0, 277.0, 421.0, 683.0, 997.0]
    out: list[int] = []
    for n in range(samples):
        t = n / RATE
        envelope = 0.60 + 0.17 * math.sin(math.tau * 0.47 * t + phases[0])
        envelope += 0.09 * math.sin(math.tau * 1.31 * t + phases[1])
        value = 0.0
        for index, freq in enumerate(freqs):
            value += math.sin(math.tau * freq * t + phases[index]) / (1.0 + 0.55 * index)
        out.append(clamp16(8200.0 * envelope * value / 2.6))
    return out


def make_knots(rng: random.Random, count: int, center: float, span: float,
               floor: float | None = None, ceiling: float | None = None) -> list[float]:
    values = [center + rng.uniform(-span, span) for _ in range(count)]
    if floor is not None:
        values = [max(floor, value) for value in values]
    if ceiling is not None:
        values = [min(ceiling, value) for value in values]
    return values


def motion_path(seed: int, family: str, intensity: int) -> tuple[list[list[float]], list[list[float]]]:
    rng = random.Random(seed)
    knot_count = 4 + intensity * 2
    delay_span = 18.0 + intensity * 26.0
    gain_span = 0.025 + intensity * 0.025
    delays = [
        make_knots(rng, knot_count, 280.0, delay_span, 120.0, 520.0),
        make_knots(rng, knot_count, 760.0, delay_span * 1.35, 420.0, 1120.0),
        make_knots(rng, knot_count, 1340.0, delay_span * 1.7, 820.0, 1880.0),
    ]
    gains = [
        make_knots(rng, knot_count, 0.47, gain_span, 0.14, 0.68),
        make_knots(rng, knot_count, 0.23, gain_span, 0.05, 0.52),
        make_knots(rng, knot_count, 0.08, gain_span * 0.65, 0.01, 0.20),
    ]

    if family == "delay-wander":
        for tap in range(3):
            gains[tap] = [gains[tap][0]] * knot_count
    elif family == "gain-crossfade":
        for tap in range(3):
            delays[tap] = [delays[tap][0]] * knot_count
        for index in range(knot_count):
            x = index / (knot_count - 1)
            gains[0][index] = 0.58 - 0.36 * x
            gains[1][index] = 0.10 + 0.38 * x
    elif family == "reflection-birth-death":
        for index in range(knot_count):
            x = index / (knot_count - 1)
            gains[2][index] = 0.015 + 0.16 * math.sin(math.pi * x) ** 2
            gains[1][index] *= 0.80 + 0.20 * math.cos(math.tau * x) ** 2
    elif family == "compound":
        pass
    else:
        raise ValueError(family)
    return delays, gains


def moving_echo(render: list[int], delays: list[list[float]], gains: list[list[float]]) -> list[int]:
    samples = len(render)
    out: list[int] = []
    for n in range(samples):
        position = n / max(1, samples - 1)
        value = 0.0
        for tap in range(3):
            delay = interpolate(delays[tap], position)
            gain = interpolate(gains[tap], position)
            value += gain * sample(render, n - delay)
        out.append(clamp16(value))
    return out


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def tree_digest(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        digest.update(str(path.relative_to(root)).encode())
        digest.update(b"\0")
        digest.update(bytes.fromhex(file_sha256(path)))
    return digest.hexdigest()


def build(output: Path, seed: int, seconds: float) -> dict:
    samples = max(4 * RATE, int(round(seconds * RATE)))
    output.mkdir(parents=True, exist_ok=True)
    render = render_signal(samples, seed + 17)
    cases: list[dict] = []
    families = ("delay-wander", "gain-crossfade", "reflection-birth-death", "compound")

    for family_index, family in enumerate(families):
        for intensity in (1, 2, 3):
            case_seed = seed * 1009 + family_index * 101 + intensity * 17
            delays, gains = motion_path(case_seed, family, intensity)
            echo = moving_echo(render, delays, gains)
            case_id = f"motion-{family}-i{intensity}"
            case_dir = output / "cases" / case_id
            case_dir.mkdir(parents=True, exist_ok=True)
            mic_path = case_dir / "mic.pcm"
            render_path = case_dir / "render.pcm"
            echo_path = case_dir / "echo.pcm"
            write_pcm(mic_path, echo)
            write_pcm(render_path, render)
            write_pcm(echo_path, echo)
            cases.append({
                "case_id": case_id,
                "split": "dev",
                "scenario": "aec-continuous-motion",
                "sample_rate_hz": RATE,
                "mic_channels": 1,
                "mic_audio": str(mic_path.relative_to(output)),
                "render_audio": str(render_path.relative_to(output)),
                "clean_near_audio": None,
                "echo_audio": str(echo_path.relative_to(output)),
                "vad_labels": None,
                "control": {},
                "processor_profile": "default",
                "expected": {
                    "max_output_render_corr_ratio": 1.20,
                    "max_output_rms_delta_db": 0.0,
                    "min_erle_db": -6.0,
                },
                "source": {
                    "dataset_id": "deterministic-aec-motion-v1",
                    "source_id": case_id,
                    "generator_seed": case_seed,
                    "movement": True,
                    "motion_family": family,
                    "motion_intensity": intensity,
                },
            })

    corpus = {
        "schema_version": 1,
        "corpus_id": f"aec-motion-dev-v1-seed-{seed}",
        "tier": "regression",
        "generator": {
            "name": "build_aec_motion_corpus.py",
            "version": 1,
            "seed": seed,
            "seconds": seconds,
            "continuous_motion": True,
            "explicit_path_change_notifications": False,
        },
        "sources": ["deterministic-aec-motion-v1"],
        "sealed_data": False,
        "cases": cases,
    }
    corpus_path = output / "corpus.json"
    corpus_path.write_text(json.dumps(corpus, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    manifest = {
        "schema_version": 1,
        "authority": "development-only-non-shipping",
        "seed": seed,
        "cases": len(cases),
        "corpus_sha256": file_sha256(corpus_path),
        "files": {
            str(path.relative_to(output)): file_sha256(path)
            for path in sorted(item for item in output.rglob("*.pcm"))
        },
    }
    (output / "source-manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return corpus


def self_test() -> None:
    with tempfile.TemporaryDirectory(prefix="ap-aec-motion-selftest-") as raw:
        root = Path(raw)
        a = root / "a"
        b = root / "b"
        c = root / "c"
        ca = build(a, 4107, 4.0)
        cb = build(b, 4107, 4.0)
        cc = build(c, 4207, 4.0)
        assert len(ca["cases"]) == 12
        assert len(cb["cases"]) == 12
        assert len(cc["cases"]) == 12
        assert all(case["control"] == {} for case in ca["cases"])
        assert all(case["split"] == "dev" for case in ca["cases"])
        assert all(case["scenario"] == "aec-continuous-motion" for case in ca["cases"])
        assert tree_digest(a) == tree_digest(b)
        assert tree_digest(a) != tree_digest(c)
    print("AEC motion development corpus self-test: OK")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--seed", type=int, default=4107)
    parser.add_argument("--seconds", type=float, default=DEFAULT_SECONDS)
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    if args.output is None or args.seconds < 4.0:
        parser.error("--output is required and --seconds must be >= 4")
    corpus = build(args.output, args.seed, args.seconds)
    print(json.dumps({
        "corpus": str(args.output / "corpus.json"),
        "corpus_id": corpus["corpus_id"],
        "cases": len(corpus["cases"]),
        "seed": args.seed,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
