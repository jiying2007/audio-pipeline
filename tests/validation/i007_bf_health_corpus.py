#!/usr/bin/env python3
"""Build deterministic I007 soft beamformer-health development cases.

The corpus is candidate-zero measurement data. It exercises current-main BF
behavior under wind, motion, phase mismatch and asymmetric reverberation and
preserves reliable-channel/clean references without importing any stale BF
candidate implementation.
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
    speech_like,
    write_pcm,
)


def require(ok: bool, message: str) -> None:
    if not ok:
        raise ValueError(message)


def load_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    require(isinstance(value, dict), "contract object required")
    return value


def validate_contract(c: dict) -> None:
    require(c.get("schema_version") == 1 and c.get("iteration_id") == "I007", "I007 identity")
    require(c.get("phase") == "bf-health-baseline-measurement", "I007 phase")
    require(c.get("measurement_revision") == 2, "I007 authoritative measurement revision")
    require(c.get("candidate_limit") == 0 and c.get("confirmation_limit") == 0, "candidate-zero")
    require(c.get("promotion_allowed") is False and c.get("shipping_source_change_allowed") is False,
            "measurement cannot ship")
    require(c.get("sample_rate_hz") == RATE and c.get("frame_samples") == FRAME, "frontend rate/frame")
    require(c.get("seeds") == [1707, 2707, 3707], "I007 development seeds")
    require(c.get("frontends") == ["bf-only", "hpf-bf"], "I007 frontend partitions")
    require(c.get("product_qualification") == "DEFERRED_BY_SCOPE", "product boundary")
    require(all(value is False for value in c["authority"].values()), "I007 authority must be false")


def add_scaled(a: list[int], b: list[int], b_gain: float) -> list[int]:
    require(len(a) == len(b), "signal length")
    return [clamp16(float(x) + b_gain * float(y)) for x, y in zip(a, b)]


def replace_window(base: list[int], replacement: list[int], start: int, end: int) -> list[int]:
    require(len(base) == len(replacement) and 0 <= start < end <= len(base), "replace window")
    out = list(base)
    out[start:end] = replacement[start:end]
    return out


def phase_mismatch(signal: list[int], delayed_mix: float, delay_samples: int,
                   start: int, end: int) -> list[int]:
    shifted = delayed(signal, delay_samples)
    transformed = [clamp16((1.0 - delayed_mix) * float(x) + delayed_mix * float(y))
                   for x, y in zip(signal, shifted)]
    return replace_window(signal, transformed, start, end)


def asymmetric_reverb(signal: list[int], delays: list[int], gains: list[float],
                       start: int, end: int) -> list[int]:
    require(len(delays) == len(gains), "reverb taps")
    wet = list(signal)
    for delay_samples, gain in zip(delays, gains):
        wet = add_scaled(wet, delayed(signal, int(delay_samples)), float(gain))
    return replace_window(signal, wet, start, end)


def wind_signal(samples: int, seed: int, rms_target: float, freqs: list[float],
                colored_fraction: float) -> list[int]:
    require(0.0 <= colored_fraction <= 1.0, "wind colored fraction")
    white = noise(samples, seed, 12000.0)
    colored: list[float] = []
    slow_state = 0.0
    slower_state = 0.0
    for value in white:
        slow_state = 0.965 * slow_state + 0.035 * float(value)
        slower_state = 0.88 * slower_state + 0.12 * slow_state
        colored.append(slower_state)
    colored_energy = math.sqrt(sum(v * v for v in colored) / max(1, len(colored)))
    if colored_energy > 1.0e-12:
        colored = [v / colored_energy for v in colored]

    raw: list[float] = []
    for n in range(samples):
        t = n / RATE
        pressure = (math.sin(math.tau * freqs[0] * t + 0.17) +
                    0.55 * math.sin(math.tau * freqs[1] * t + 0.91) +
                    0.30 * math.sin(math.tau * freqs[2] * t + 1.71))
        raw.append((1.0 - colored_fraction) * pressure + colored_fraction * colored[n])
    energy = sum(value * value for value in raw) / max(1, len(raw))
    scale = rms_target / math.sqrt(max(energy, 1.0e-12))
    return [clamp16(scale * value) for value in raw]


def soft_wind(signal: list[int], seed: int, rms_target: float, freqs: list[float],
              colored_fraction: float, start: int, end: int) -> list[int]:
    wind = wind_signal(len(signal), seed, rms_target, freqs, colored_fraction)
    out = list(signal)
    fade = RATE // 5
    for n in range(start, end):
        edge = min(n - start, end - 1 - n)
        envelope = min(1.0, max(0.0, edge / max(1.0, float(fade))))
        out[n] = clamp16(float(signal[n]) + envelope * float(wind[n]))
    return out


def motion_pair(clean: list[int], noise0: list[int], noise1: list[int],
                tdoa_values: list[int]) -> tuple[list[int], list[int], list[dict]]:
    samples = len(clean)
    frames = samples // FRAME
    require(frames >= len(tdoa_values), "motion frames")
    segment = frames // len(tdoa_values)
    a = [0] * samples
    b = [0] * samples
    segments: list[dict] = []
    for index, tdoa in enumerate(tdoa_values):
        start_frame = index * segment
        end_frame = frames if index + 1 == len(tdoa_values) else (index + 1) * segment
        segments.append({
            "start_frame": start_frame,
            "end_frame": end_frame,
            "tdoa_samples": int(tdoa),
            "expected_bf_lag_samples": int(-tdoa),
        })
        for frame in range(start_frame, end_frame):
            for offset in range(FRAME):
                n = frame * FRAME + offset
                if tdoa >= 0:
                    ai = n
                    bi = n - tdoa
                else:
                    ai = n + tdoa
                    bi = n
                clean_a = clean[ai] if 0 <= ai < samples else 0
                clean_b = clean[bi] if 0 <= bi < samples else 0
                a[n] = clamp16(float(clean_a) + float(noise0[n]))
                b[n] = clamp16(float(clean_b) + float(noise1[n]))
    return a, b, segments


def add_case(root: Path, cases: list[dict], case_id: str, scenario: str,
             mic0: list[int], mic1: list[int], clean: list[int],
             reliable_channel: int | None, start_frame: int, end_frame: int,
             dimensions: dict | None = None) -> None:
    case_dir = root / "cases" / case_id
    case_dir.mkdir(parents=True, exist_ok=True)
    mic_path = case_dir / "mic.pcm"
    clean_path = case_dir / "clean.pcm"
    write_pcm(mic_path, interleave(mic0, mic1))
    write_pcm(clean_path, clean)
    reliable_path = None
    if reliable_channel is not None:
        reliable_path = case_dir / "reliable.pcm"
        write_pcm(reliable_path, mic0 if reliable_channel == 0 else mic1)
    cases.append({
        "case_id": case_id,
        "scenario": scenario,
        "sample_rate_hz": RATE,
        "frame_samples": FRAME,
        "frames": len(clean) // FRAME,
        "window_start_frame": start_frame,
        "window_end_frame": end_frame,
        "reliable_channel": reliable_channel,
        "mic_audio": str(mic_path.relative_to(root)),
        "clean_audio": str(clean_path.relative_to(root)),
        "reliable_audio": str(reliable_path.relative_to(root)) if reliable_path else None,
        "dimensions": dimensions or {},
    })


def build(root: Path, contract: dict, seed: int) -> dict:
    validate_contract(contract)
    require(seed in contract["seeds"], "unregistered I007 seed")
    frames = int(float(contract["seconds"]) * 100)
    samples = frames * FRAME
    start_frame, end_frame = [int(value) for value in contract["fault_window_frames"]]
    start, end = start_frame * FRAME, end_frame * FRAME
    g = contract["generator"]

    clean, _ = speech_like(frames, seed + 1, [(0.0, frames / 100.0)],
                           amplitude=float(g["clean_amplitude"]))
    n0 = noise(samples, seed + 2, float(g["noise_rms"]))
    n1 = rotate(noise(samples, seed + 3, float(g["noise_rms"])), 173)
    base0 = mix(clean, n0)
    base1 = mix(delayed(clean, int(g["fixed_tdoa_samples"])), n1)
    cases: list[dict] = []

    add_case(root, cases, "healthy-control", "healthy-control",
             base0, base1, clean, None, start_frame, end_frame,
             {"tdoa_samples": int(g["fixed_tdoa_samples"])})

    freqs = [float(value) for value in g["wind_frequencies_hz"]]
    colored_fraction = float(g["wind_colored_noise_fraction"])
    for channel in (0, 1):
        wind0, wind1 = list(base0), list(base1)
        if channel == 0:
            wind0 = soft_wind(wind0, seed + 100, float(g["wind_rms"]), freqs,
                              colored_fraction, start, end)
        else:
            wind1 = soft_wind(wind1, seed + 200, float(g["wind_rms"]), freqs,
                              colored_fraction, start, end)
        add_case(root, cases, f"soft-wind-ch{channel}", f"soft-wind-ch{channel}",
                 wind0, wind1, clean, 1 - channel, start_frame, end_frame)

    for channel in (0, 1):
        p0, p1 = list(base0), list(base1)
        if channel == 0:
            p0 = phase_mismatch(p0, float(g["phase_mismatch_delayed_mix"]),
                                int(g["phase_mismatch_delay_samples"]), start, end)
        else:
            p1 = phase_mismatch(p1, float(g["phase_mismatch_delayed_mix"]),
                                int(g["phase_mismatch_delay_samples"]), start, end)
        add_case(root, cases, f"phase-mismatch-ch{channel}", f"phase-mismatch-ch{channel}",
                 p0, p1, clean, 1 - channel, start_frame, end_frame)

    delays = [int(value) for value in g["reverb_delays_samples"]]
    gains = [float(value) for value in g["reverb_gains"]]
    for channel in (0, 1):
        r0, r1 = list(base0), list(base1)
        if channel == 0:
            r0 = asymmetric_reverb(r0, delays, gains, start, end)
        else:
            r1 = asymmetric_reverb(r1, delays, gains, start, end)
        add_case(root, cases, f"asymmetric-reverb-ch{channel}",
                 f"asymmetric-reverb-ch{channel}", r0, r1, clean, 1 - channel,
                 start_frame, end_frame, {"delays_samples": delays, "gains": gains})

    motion0, motion1, segments = motion_pair(
        clean, n0, n1, [int(value) for value in g["motion_tdoa_samples"]])
    add_case(root, cases, "motion-tdoa-sweep", "motion-tdoa-sweep",
             motion0, motion1, clean, None, 0, frames, {"segments": segments})

    corpus = {
        "schema_version": 1,
        "iteration_id": "I007",
        "measurement_revision": 2,
        "corpus_id": f"i007-bf-health-seed-{seed}",
        "authority": "fresh-development-candidate-zero",
        "sealed_data": True,
        "seed": seed,
        "cases": cases,
    }
    root.mkdir(parents=True, exist_ok=True)
    (root / "corpus.json").write_text(json.dumps(corpus, indent=2, sort_keys=True) + "\n",
                                      encoding="utf-8")
    return corpus


def self_test() -> None:
    import tempfile
    contract = {
        "schema_version": 1, "iteration_id": "I007", "measurement_revision": 2,
        "phase": "bf-health-baseline-measurement", "candidate_limit": 0,
        "confirmation_limit": 0, "promotion_allowed": False,
        "shipping_source_change_allowed": False, "seeds": [1707, 2707, 3707],
        "sample_rate_hz": RATE, "frame_samples": FRAME,
        "frontends": ["bf-only", "hpf-bf"], "product_qualification": "DEFERRED_BY_SCOPE",
        "authority": {"a": False}, "seconds": 8.0, "fault_window_frames": [200, 500],
        "generator": {
            "clean_amplitude": 9000.0, "noise_rms": 1200.0, "fixed_tdoa_samples": 2,
            "wind_rms": 5200.0, "wind_frequencies_hz": [61.0, 97.0, 137.0],
            "wind_colored_noise_fraction": 0.45,
            "phase_mismatch_delayed_mix": 0.24, "phase_mismatch_delay_samples": 1,
            "reverb_delays_samples": [48, 123, 241], "reverb_gains": [0.24, -0.13, 0.08],
            "motion_tdoa_samples": [-2, -1, 0, 1, 2],
        },
    }
    with tempfile.TemporaryDirectory(prefix="i007-bf-health-") as temporary:
        root = Path(temporary)
        corpus = build(root, contract, 1707)
        assert len(corpus["cases"]) == 8 and corpus["measurement_revision"] == 2
        assert {case["scenario"] for case in corpus["cases"]} == {
            "healthy-control", "soft-wind-ch0", "soft-wind-ch1",
            "phase-mismatch-ch0", "phase-mismatch-ch1",
            "asymmetric-reverb-ch0", "asymmetric-reverb-ch1", "motion-tdoa-sweep",
        }
        for case in corpus["cases"]:
            assert (root / case["mic_audio"]).stat().st_size == 800 * FRAME * 4
            assert (root / case["clean_audio"]).stat().st_size == 800 * FRAME * 2
    print(json.dumps({"result": "PASS", "cases": 8, "measurement_revision": 2,
                      "candidate_limit": 0}, sort_keys=True))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--contract", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--seed", type=int)
    args = parser.parse_args()
    if args.self_test:
        self_test(); return 0
    require(args.contract is not None and args.output is not None and args.seed is not None,
            "contract/output/seed required")
    contract = load_json(args.contract)
    corpus = build(args.output, contract, args.seed)
    print(json.dumps({"result": "PASS", "cases": len(corpus["cases"]), "seed": args.seed,
                      "measurement_revision": 2,
                      "corpus": str(args.output / "corpus.json")}, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, OSError, KeyError, TypeError) as exc:
        raise SystemExit(f"I007 corpus error: {exc}")
