#!/usr/bin/env python3
"""Build deterministic two-microphone hard-fault discovery corpora.

This corpus is deliberately release-neutral. It creates physically distinct
hard-fault families and preserves an oracle reliable single-microphone
reference. Worst-case soft gain/sensitivity mismatches are included as negative
controls so a microphone-health classifier cannot make hard-fault gains by
silently converting normal weak-microphone degradation into a bypass.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from build_validation_corpus import (
    FRAME,
    RATE,
    clamp16,
    delayed,
    interleave,
    mix,
    noise,
    rotate,
    scale,
    speech_like,
    write_pcm,
)

FRAMES = 800
FAULT_START_FRAME = 200
FAULT_END_FRAME = 500
FAULT_TYPES = ("mute", "dropout", "stuck-dc", "hard-clip", "wind-burst")
SOFT_CONTROL_TYPES = ("soft-global-gain", "soft-sensitivity-floor")
SOFT_CONTROL_RATIO = 0.35


def inject_fault(signal: list[int], fault_type: str, seed: int) -> list[int]:
    out = list(signal)
    start = FAULT_START_FRAME * FRAME
    end = FAULT_END_FRAME * FRAME
    for index in range(start, end):
        local_frame = index // FRAME - FAULT_START_FRAME
        if fault_type == "mute":
            out[index] = 0
        elif fault_type == "dropout":
            # Deterministic 30-40 ms holes inside a 100 ms cadence. This is
            # intentionally intermittent rather than one long mute.
            if local_frame % 10 in {2, 3, 4, 7}:
                out[index] = 0
        elif fault_type == "stuck-dc":
            out[index] = 24000 if seed % 2 else -24000
        elif fault_type == "hard-clip":
            out[index] = clamp16(6.5 * signal[index])
        elif fault_type == "wind-burst":
            t = index / RATE
            phase = (local_frame % 80) / 80.0
            envelope = 0.20 + 0.80 * math.sin(math.pi * phase) ** 2
            wind = 22000.0 * envelope * (
                math.sin(math.tau * 67.0 * t + 0.31) +
                0.45 * math.sin(math.tau * 113.0 * t + 1.17)
            )
            out[index] = clamp16(signal[index] + wind)
        else:
            raise ValueError(f"unsupported fault type: {fault_type}")
    return out


def splice_fault_window(base: list[int], degraded: list[int]) -> list[int]:
    if len(base) != len(degraded):
        raise ValueError("soft-degradation signals must have identical lengths")
    out = list(base)
    start = FAULT_START_FRAME * FRAME
    end = FAULT_END_FRAME * FRAME
    out[start:end] = degraded[start:end]
    return out


def add_case(output: Path, cases: list[dict], case_id: str, fault_type: str,
             mic0: list[int], mic1: list[int], clean: list[int],
             faulty_channel: int | None) -> None:
    case_dir = output / "cases" / case_id
    case_dir.mkdir(parents=True, exist_ok=True)
    mic_path = case_dir / "mic.pcm"
    clean_path = case_dir / "clean.pcm"
    reliable_path = case_dir / "reliable.pcm"
    write_pcm(mic_path, interleave(mic0, mic1))
    write_pcm(clean_path, clean)
    reliable_channel = 0 if faulty_channel in (None, 1) else 1
    reliable = mic0 if reliable_channel == 0 else mic1
    write_pcm(reliable_path, reliable)
    cases.append({
        "case_id": case_id,
        "fault_type": fault_type,
        "faulty_channel": faulty_channel,
        "reliable_channel": reliable_channel,
        "sample_rate_hz": RATE,
        "frame_samples": FRAME,
        "frames": FRAMES,
        "fault_start_frame": FAULT_START_FRAME,
        "fault_end_frame": FAULT_END_FRAME,
        "mic_audio": str(mic_path.relative_to(output)),
        "clean_audio": str(clean_path.relative_to(output)),
        "reliable_audio": str(reliable_path.relative_to(output)),
        "dimensions": {
            "tdoa_samples": 2,
            "fault_duration_ms": (FAULT_END_FRAME - FAULT_START_FRAME) * 10,
            "faulty_channel": faulty_channel,
        },
    })


def build(output: Path, seed: int) -> dict:
    samples = FRAMES * FRAME
    clean, _ = speech_like(FRAMES, seed + 1, [(0.0, FRAMES / 100.0)], amplitude=9000.0)
    delayed_clean = delayed(clean, 2)
    left_noise = noise(samples, seed + 2, 1700.0)
    right_noise = rotate(noise(samples, seed + 3, 1700.0), 173)
    mic0_base = mix(clean, left_noise)
    mic1_base = mix(delayed_clean, right_noise)
    cases: list[dict] = []

    add_case(output, cases, "bf-hard-control", "control",
             mic0_base, mic1_base, clean, None)
    for fault_type in FAULT_TYPES:
        for faulty_channel in (0, 1):
            if faulty_channel == 0:
                mic0 = inject_fault(mic0_base, fault_type, seed + 11)
                mic1 = list(mic1_base)
            else:
                mic0 = list(mic0_base)
                mic1 = inject_fault(mic1_base, fault_type, seed + 17)
            add_case(
                output,
                cases,
                f"bf-hard-{fault_type}-ch{faulty_channel}",
                fault_type,
                mic0,
                mic1,
                clean,
                faulty_channel,
            )

    for weak_channel in (0, 1):
        if weak_channel == 0:
            global_weak = splice_fault_window(mic0_base, scale(mic0_base, SOFT_CONTROL_RATIO))
            sensitivity_weak = splice_fault_window(
                mic0_base,
                mix(scale(clean, SOFT_CONTROL_RATIO), left_noise),
            )
            controls = (
                ("soft-global-gain", global_weak, list(mic1_base)),
                ("soft-sensitivity-floor", sensitivity_weak, list(mic1_base)),
            )
        else:
            global_weak = splice_fault_window(mic1_base, scale(mic1_base, SOFT_CONTROL_RATIO))
            sensitivity_weak = splice_fault_window(
                mic1_base,
                mix(scale(delayed_clean, SOFT_CONTROL_RATIO), right_noise),
            )
            controls = (
                ("soft-global-gain", list(mic0_base), global_weak),
                ("soft-sensitivity-floor", list(mic0_base), sensitivity_weak),
            )
        for control_type, mic0, mic1 in controls:
            add_case(
                output,
                cases,
                f"bf-health-control-{control_type}-ch{weak_channel}",
                control_type,
                mic0,
                mic1,
                clean,
                weak_channel,
            )
            cases[-1]["dimensions"].update({
                "control_class": "soft-degradation-negative-control",
                "weak_channel_ratio": SOFT_CONTROL_RATIO,
                "hard_fault_expected": False,
            })

    corpus = {
        "schema_version": 2,
        "corpus_id": f"bf-hard-mic-fault-seed-{seed}",
        "tier": "regression",
        "authority": "diagnostic-regression-only",
        "generator": {
            "name": "build_bf_hard_fault_sweep.py",
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

    with tempfile.TemporaryDirectory(prefix="ap-bf-hard-fault-") as temporary:
        root = Path(temporary)
        corpus = build(root, 1307)
        assert corpus["authority"] == "diagnostic-regression-only"
        assert len(corpus["cases"]) == 1 + 2 * len(FAULT_TYPES) + 2 * len(SOFT_CONTROL_TYPES)
        ids = {case["case_id"] for case in corpus["cases"]}
        assert "bf-hard-control" in ids
        for fault_type in FAULT_TYPES:
            for channel in (0, 1):
                assert f"bf-hard-{fault_type}-ch{channel}" in ids
        for control_type in SOFT_CONTROL_TYPES:
            for channel in (0, 1):
                case_id = f"bf-health-control-{control_type}-ch{channel}"
                assert case_id in ids
                case = next(item for item in corpus["cases"] if item["case_id"] == case_id)
                assert case["dimensions"]["hard_fault_expected"] is False
                assert case["dimensions"]["weak_channel_ratio"] == SOFT_CONTROL_RATIO
        for case in corpus["cases"]:
            assert case["frames"] == FRAMES
            assert case["fault_start_frame"] < case["fault_end_frame"]
            assert (root / case["mic_audio"]).stat().st_size == FRAMES * FRAME * 2 * 2
            assert (root / case["clean_audio"]).stat().st_size == FRAMES * FRAME * 2
            assert (root / case["reliable_audio"]).stat().st_size == FRAMES * FRAME * 2
    print("BF hard-fault corpus self-test: OK")


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
