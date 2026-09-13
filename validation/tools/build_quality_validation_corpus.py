#!/usr/bin/env python3
"""Build a deterministic ground-truth corpus for AEC/RES, BF, NS and VAD quality.

This corpus is deliberately ``tier=regression``. It exists to make algorithm
quality measurable and tunable without confusing generated evidence with public
validation or product qualification. Independent seeds are used for
Development / Validation / Shadow replay by the caller.
"""

from __future__ import annotations

import argparse
import json
import math
import tempfile
from pathlib import Path

from build_validation_corpus import (
    FRAME,
    RATE,
    add_case,
    echo_from_render,
    interleave,
    mix,
    noise,
    nonstationary_noise,
    render_signal,
    scale,
    speech_like,
    write_pcm,
)

GENERATOR_VERSION = 2
PCR02_MIC_SPACING_MM = 35.0
SOUND_MM_S = 343000.0
BF_INTERFERER_ANGLE_DEG = 60.0


def _case(cases: list[dict], case_id: str) -> dict:
    return next(item for item in cases if item["case_id"] == case_id)


def _attach_audio(output: Path, cases: list[dict], case_id: str,
                  field: str, filename: str, samples: list[int]) -> None:
    case = _case(cases, case_id)
    directory = output / "cases" / case_id
    path = directory / filename
    write_pcm(path, samples)
    case[field] = str(path.relative_to(output))


def _mark(cases: list[dict], case_id: str, role: str, **extra) -> None:
    case = _case(cases, case_id)
    case["quality"] = {"role": role, "ground_truth": True, **extra}
    case.setdefault("dimensions", {})["quality_role"] = role


def physical_tdoa_samples(spacing_mm: float, angle_deg: float) -> float:
    return spacing_mm * RATE / SOUND_MM_S * math.sin(math.radians(angle_deg))


def fractional_delay(signal: list[int], delay_samples: float) -> list[int]:
    if delay_samples < 0.0:
        raise ValueError("fractional_delay expects non-negative delay")
    out: list[int] = []
    for index in range(len(signal)):
        source = index - delay_samples
        if source < 0.0:
            out.append(0)
            continue
        lower = int(math.floor(source))
        fraction = source - lower
        if lower >= len(signal) - 1:
            value = signal[-1]
        else:
            value = (1.0 - fraction) * signal[lower] + fraction * signal[lower + 1]
        out.append(max(-32768, min(32767, int(round(value)))))
    return out


def build(output: Path, seed: int, seconds: float) -> dict:
    if not 5.0 <= seconds <= 20.0:
        raise ValueError("quality corpus seconds must be 5..20")
    frames = int(round(seconds * 100.0))
    samples = frames * FRAME
    active = [(0.55, 1.80), (2.30, 3.90), (4.30, min(seconds - 0.20, 5.40))]
    clean, labels = speech_like(frames, seed + 1, active, amplitude=8500.0)
    quiet_clean, quiet_labels = speech_like(frames, seed + 2, active, amplitude=3600.0)
    interferer, _ = speech_like(frames, seed + 3, [(0.15, seconds - 0.15)], amplitude=7600.0)
    render = render_signal(samples, seed + 4)
    echo_a = echo_from_render(render, [(320, 0.52), (640, 0.21), (1120, 0.09)])
    echo_b = echo_from_render(render, [(160, 0.40), (720, 0.30), (1480, 0.10)])
    stationary = noise(samples, seed + 5, 5000.0)
    moving_noise = nonstationary_noise(samples, seed + 6, 5600.0)
    cases: list[dict] = []

    # AEC far-end: known render + known echo permits ERLE and convergence.
    add_case(
        cases, output, "quality-aec-farend", "quality-aec-farend",
        echo_a, 1, render=render, echo=echo_a,
        expected={
            "min_erle_db": -6.0,
            "max_output_render_corr_ratio": 1.35,
            "max_erle_convergence_ms": 3500.0,
        },
    )
    _mark(cases, "quality-aec-farend", "aec-farend")

    half_frame = frames // 2
    half = half_frame * FRAME
    changing_echo = echo_a[:half] + echo_b[half:]
    add_case(
        cases, output, "quality-aec-path-change", "quality-aec-path-change",
        changing_echo, 1, render=render, echo=changing_echo,
        control={"echo_path_change_frame": half_frame},
        expected={
            "min_erle_db": -7.0,
            "max_output_render_corr_ratio": 1.40,
            "max_erle_convergence_ms": 3500.0,
            "max_erle_recovery_ms": 3000.0,
        },
    )
    _mark(cases, "quality-aec-path-change", "aec-farend", event="path-change")

    delayed_echo = echo_from_render(render, [(640, 0.50), (960, 0.18), (1440, 0.08)])
    add_case(
        cases, output, "quality-aec-delay", "quality-aec-delay",
        delayed_echo, 1, render=render, echo=delayed_echo,
        expected={
            "min_erle_db": -7.0,
            "max_output_render_corr_ratio": 1.40,
            "max_erle_convergence_ms": 4000.0,
        },
    )
    _mark(cases, "quality-aec-delay", "aec-farend", delay_ms=40)

    # AEC + RES double-talk: clean-near projection protects user speech while
    # scale-sensitive interference projection proves echo is actually reduced.
    for name, near_gain in (("nominal", 1.0), ("weak-near", 0.55)):
        near = scale(clean, near_gain)
        case_id = f"quality-aec-res-{name}"
        add_case(
            cases, output, case_id, "quality-aec-res-doubletalk",
            mix(near, echo_a), 1, clean=near, render=render, labels=labels,
            expected={
                "min_near_si_sdr_db": -20.0,
                "min_near_projection_gain_db": -12.0,
                "min_interference_projection_attenuation_db": 0.0,
                "max_output_clip_fraction": 0.02,
            },
        )
        _attach_audio(output, cases, case_id, "interference_audio", "echo-truth.pcm", echo_a)
        _mark(cases, case_id, "aec-res-doubletalk", near_gain=near_gain)

    # NS: clean + explicit noise truth + VAD labels. SI-SDR measures waveform
    # quality; projection gain prevents scale-invariant SI-SDR from hiding speech
    # attenuation; noise-only attenuation proves the suppressor is not a no-op.
    for name, noise_signal, attenuation in (
        ("stationary", stationary, 0.50),
        ("nonstationary", moving_noise, 0.20),
    ):
        case_id = f"quality-ns-{name}"
        add_case(
            cases, output, case_id, f"quality-ns-{name}",
            mix(clean, noise_signal), 1, clean=clean, labels=labels,
            processor_profile="ns-isolated",
            expected={
                "min_near_si_sdr_improvement_db": -6.0,
                "min_near_projection_gain_db": -9.0,
                "min_noise_only_attenuation_db": attenuation,
                "min_vad_recall": 0.40,
                "max_vad_false_positive_rate": 0.60,
            },
        )
        _attach_audio(output, cases, case_id, "noise_audio", "noise-truth.pcm", noise_signal)
        _mark(cases, case_id, "ns", noise=name)

    # BF quality must match the shipping PCR02 steering contract. Shipping is
    # fixed broadside (zero integer delay), so the desired target stays at 0°.
    # A coherent competing source is placed at +/-60° using the physical 35 mm
    # fractional TDOA. Both directions are exercised without exceeding the real
    # 1.63265-sample endfire bound.
    max_tdoa = physical_tdoa_samples(PCR02_MIC_SPACING_MM, 90.0)
    interferer_tdoa = physical_tdoa_samples(PCR02_MIC_SPACING_MM, BF_INTERFERER_ANGLE_DEG)
    if not 0.0 < interferer_tdoa <= max_tdoa < 2.0:
        raise ValueError("PCR02 BF physical TDOA contract drifted")
    delayed_interferer = fractional_delay(interferer, interferer_tdoa)
    for name, angle, int_l, int_r in (
        ("left", -BF_INTERFERER_ANGLE_DEG, delayed_interferer, interferer),
        ("right", BF_INTERFERER_ANGLE_DEG, interferer, delayed_interferer),
    ):
        left = mix(clean, scale(int_l, 0.75))
        right = mix(clean, scale(int_r, 0.75))
        case_id = f"quality-bf-{name}"
        add_case(
            cases, output, case_id, "quality-bf-target-interferer",
            interleave(left, right), 2, clean=clean,
            processor_profile="bf-isolated",
            expected={
                "min_near_si_sdr_improvement_db": -0.25,
                "min_near_projection_gain_db": -6.0,
                "min_interference_projection_attenuation_db": 0.0,
                "max_output_clip_fraction": 0.02,
            },
        )
        _attach_audio(output, cases, case_id, "interference_audio", "interferer-truth.pcm", interferer)
        case = _case(cases, case_id)
        case.setdefault("dimensions", {}).update({
            "mic_spacing_mm": PCR02_MIC_SPACING_MM,
            "target_angle_deg": 0.0,
            "target_tdoa_samples": 0.0,
            "interferer_angle_deg": angle,
            "interferer_tdoa_samples": interferer_tdoa if angle > 0 else -interferer_tdoa,
            "max_physical_tdoa_samples": max_tdoa,
            "shipping_steering": "fixed-zero-integer-delay",
        })
        _mark(cases, case_id, "bf", target_angle_deg=0.0,
              interferer_angle_deg=angle, mic_spacing_mm=PCR02_MIC_SPACING_MM)

    # VAD: classification metrics alone do not catch unusably slow onset/release.
    add_case(
        cases, output, "quality-vad-clean", "quality-vad-clean",
        clean, 1, clean=clean, labels=labels, processor_profile="vad-isolated",
        expected={
            "min_vad_f1": 0.25,
            "min_vad_recall": 0.20,
            "max_vad_false_positive_rate": 0.25,
            "max_vad_onset_delay_ms": 500.0,
            "max_vad_release_delay_ms": 700.0,
        },
    )
    _mark(cases, "quality-vad-clean", "vad")

    add_case(
        cases, output, "quality-vad-quiet", "quality-vad-quiet",
        quiet_clean, 1, clean=quiet_clean, labels=quiet_labels,
        processor_profile="vad-isolated",
        expected={
            "min_vad_f1": 0.10,
            "max_vad_onset_delay_ms": 700.0,
            "max_vad_release_delay_ms": 900.0,
        },
    )
    _mark(cases, "quality-vad-quiet", "vad", level="quiet")

    zeros = [0] * frames
    add_case(
        cases, output, "quality-vad-negative", "quality-vad-negative",
        moving_noise, 1, labels=zeros, processor_profile="vad-isolated",
        expected={"max_vad_false_positive_rate": 0.30},
    )
    _attach_audio(output, cases, "quality-vad-negative", "noise_audio", "noise-truth.pcm", moving_noise)
    _mark(cases, "quality-vad-negative", "vad", negative=True)

    corpus = {
        "schema_version": 1,
        "corpus_id": f"audio-quality-ground-truth-v{GENERATOR_VERSION}-seed-{seed}",
        "tier": "regression",
        "generator": {
            "name": "build_quality_validation_corpus.py",
            "version": GENERATOR_VERSION,
            "seed": seed,
            "seconds": seconds,
            "bf_geometry": {
                "mic_spacing_mm": PCR02_MIC_SPACING_MM,
                "sound_mm_s": SOUND_MM_S,
                "shipping_steering": "fixed-zero-integer-delay",
                "target_angle_deg": 0.0,
                "interferer_angle_deg": [-BF_INTERFERER_ANGLE_DEG, BF_INTERFERER_ANGLE_DEG],
                "max_physical_tdoa_samples": max_tdoa,
            },
        },
        "sources": ["deterministic-quality-ground-truth"],
        "sealed_data": False,
        "cases": cases,
    }
    output.mkdir(parents=True, exist_ok=True)
    (output / "corpus.json").write_text(
        json.dumps(corpus, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return corpus


def self_test() -> None:
    assert abs(physical_tdoa_samples(35.0, 90.0) - 1.6326530612) < 1.0e-6
    with tempfile.TemporaryDirectory(prefix="ap-quality-corpus-") as temporary:
        root = Path(temporary)
        corpus = build(root, 5107, 6.0)
        roles = [case["quality"]["role"] for case in corpus["cases"]]
        assert len(corpus["cases"]) == 12
        assert set(roles) == {"aec-farend", "aec-res-doubletalk", "ns", "bf", "vad"}
        assert sum(role == "aec-farend" for role in roles) == 3
        assert sum(role == "aec-res-doubletalk" for role in roles) == 2
        assert sum(role == "ns" for role in roles) == 2
        assert sum(role == "bf" for role in roles) == 2
        assert sum(role == "vad" for role in roles) == 3
        assert all(case["split"] == "validation" for case in corpus["cases"])
        bf = [case for case in corpus["cases"] if case["quality"]["role"] == "bf"]
        assert all(case["dimensions"]["target_tdoa_samples"] == 0.0 for case in bf)
        assert all(abs(case["dimensions"]["interferer_tdoa_samples"]) <=
                   case["dimensions"]["max_physical_tdoa_samples"] for case in bf)
    print("quality validation corpus self-test: OK")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    parser.add_argument("--seed", type=int, default=5107)
    parser.add_argument("--seconds", type=float, default=6.0)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    if args.output is None:
        parser.error("--output is required")
    args.output.mkdir(parents=True, exist_ok=True)
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
