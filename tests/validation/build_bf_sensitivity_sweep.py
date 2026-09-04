#!/usr/bin/env python3
"""Build deterministic two-mic beamformer sensitivity mismatch sweeps.

Two different physical models are deliberately separated:

1. global-channel-gain: coherent speech and that microphone's sensor noise are
   scaled together. This models a channel gain/calibration offset.
2. sensitivity-floor: coherent speech is attenuated while the sensor-noise floor
   is held approximately constant. This models reduced microphone sensitivity /
   SNR on one microphone and is the harder case for equal-weight averaging.

The corpus is regression/discovery authority only and never changes shipping
beamformer configuration.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from build_validation_corpus import (
    RATE,
    add_case,
    delayed,
    interleave,
    mix,
    noise,
    rotate,
    scale,
    speech_like,
)

RATIOS = (1.0, 0.8, 0.55, 0.35)


def ratio_token(ratio: float) -> str:
    return f"{int(round(ratio * 100)):03d}"


def build(output: Path, seed: int) -> dict:
    frames = 600
    samples = frames * (RATE // 100)
    clean, _ = speech_like(frames, seed + 1, [(0.0, 6.0)], amplitude=9000.0)
    noise_left = scale(noise(samples, seed + 2, 3000.0), 0.55)
    noise_right = scale(rotate(noise(samples, seed + 3, 3000.0), 173), 0.55)
    delayed_clean = delayed(clean, 2)
    left = mix(clean, noise_left)
    cases: list[dict] = []

    for ratio in RATIOS:
        token = ratio_token(ratio)

        # Global channel gain mismatch: speech and noise scale together.
        right_global = scale(mix(delayed_clean, noise_right), ratio)
        case_id = f"bf-global-gain-r{token}"
        add_case(
            cases,
            output,
            case_id,
            "bf-global-channel-gain-mismatch",
            interleave(left, right_global),
            2,
            clean=clean,
            processor_profile="bf-isolated",
            expected={},
        )
        case = next(item for item in cases if item["case_id"] == case_id)
        case["dimensions"] = {
            "mismatch_model": "global-channel-gain",
            "weak_channel_ratio": ratio,
            "tdoa_samples": 2,
        }

        # Sensitivity/SNR mismatch: speech weakens but the sensor-noise floor does
        # not. This is intentionally not equivalent to a simple channel gain.
        right_sensitivity = mix(scale(delayed_clean, ratio), noise_right)
        case_id = f"bf-sensitivity-floor-r{token}"
        add_case(
            cases,
            output,
            case_id,
            "bf-microphone-sensitivity-floor-mismatch",
            interleave(left, right_sensitivity),
            2,
            clean=clean,
            processor_profile="bf-isolated",
            expected={},
        )
        case = next(item for item in cases if item["case_id"] == case_id)
        case["dimensions"] = {
            "mismatch_model": "sensitivity-floor",
            "weak_channel_ratio": ratio,
            "tdoa_samples": 2,
        }

    corpus = {
        "schema_version": 1,
        "corpus_id": f"bf-sensitivity-sweep-seed-{seed}",
        "tier": "regression",
        "generator": {
            "name": "build_bf_sensitivity_sweep.py",
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


def self_test() -> None:
    import tempfile

    with tempfile.TemporaryDirectory(prefix="ap-bf-sensitivity-") as temporary:
        corpus = build(Path(temporary), 1307)
        assert len(corpus["cases"]) == 8
        by_model: dict[str, set[float]] = {}
        for case in corpus["cases"]:
            dimensions = case["dimensions"]
            by_model.setdefault(dimensions["mismatch_model"], set()).add(
                float(dimensions["weak_channel_ratio"])
            )
            assert case["processor_profile"] == "bf-isolated"
            assert case["clean_near_audio"]
        assert by_model == {
            "global-channel-gain": set(RATIOS),
            "sensitivity-floor": set(RATIOS),
        }
    print("BF sensitivity sweep corpus self-test: OK")


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
