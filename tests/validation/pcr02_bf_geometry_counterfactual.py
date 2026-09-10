#!/usr/bin/env python3
"""PCR02 two-mic geometry counterfactuals.

Runs the real C beamformer in shipping-fixed and integer-tracking builds, then
compares it with non-shipping fractional-delay references. This tool is
diagnostic only and cannot select or promote a shipping configuration.
"""
from __future__ import annotations

import argparse
import array
import json
import math
import os
import random
import statistics
import subprocess
import tempfile
from pathlib import Path

RATE = 16000
SOUND_MM_S = 343000.0
SPACINGS_MM = (25.0, 30.0, 35.0, 40.0, 45.0)
ANGLES_DEG = (0.0, 30.0, 60.0, 90.0)
GAIN_RATIOS = (1.0, 0.85)
SEEDS = (1701, 2701, 3701)
INCUMBENT_SPACING_MM = 35.0


def clamp16(value: float) -> int:
    return max(-32768, min(32767, int(round(value))))


def write_pcm(path: Path, samples: list[int]) -> None:
    values = array.array("h", samples)
    if os.sys.byteorder != "little":
        values.byteswap()
    path.write_bytes(values.tobytes())


def read_pcm(path: Path) -> list[int]:
    values = array.array("h")
    values.frombytes(path.read_bytes())
    if os.sys.byteorder != "little":
        values.byteswap()
    return list(values)


def speech_like(samples: int, seed: int) -> list[int]:
    rng = random.Random(seed)
    phases = [rng.random() * math.tau for _ in range(7)]
    freqs = [137.0, 223.0, 347.0, 509.0, 733.0, 1091.0, 1879.0]
    out = []
    for n in range(samples):
        t = n / RATE
        syllable = 0.55 + 0.45 * max(0.0, math.sin(math.tau * 3.7 * t))
        formant = sum(math.sin(math.tau * f * t + phases[i]) / (i + 1)
                      for i, f in enumerate(freqs))
        out.append(clamp16(7600.0 * syllable * formant / 1.95))
    return out


def sensor_noise(samples: int, seed: int, amplitude: float = 900.0) -> list[int]:
    rng = random.Random(seed)
    prev = 0.0
    out = []
    for _ in range(samples):
        white = rng.uniform(-amplitude, amplitude)
        prev = 0.72 * prev + 0.28 * white
        out.append(clamp16(prev))
    return out


def mix(a: list[int], b: list[int], gain_a: float = 1.0, gain_b: float = 1.0) -> list[int]:
    return [clamp16(gain_a * x + gain_b * y) for x, y in zip(a, b)]


def fractional_delay(signal: list[int], delay_samples: float) -> list[int]:
    if delay_samples < 0.0:
        raise ValueError("fractional_delay expects non-negative delay")
    out: list[int] = []
    for n in range(len(signal)):
        src = n - delay_samples
        if src < 0.0:
            out.append(0)
            continue
        lo = int(math.floor(src))
        frac = src - lo
        if lo >= len(signal) - 1:
            value = signal[-1]
        else:
            value = (1.0 - frac) * signal[lo] + frac * signal[lo + 1]
        out.append(clamp16(value))
    return out


def interleave(a: list[int], b: list[int]) -> list[int]:
    out: list[int] = []
    for x, y in zip(a, b):
        out.extend((x, y))
    return out


def normalized_corr(a: list[int], b: list[int], lag: int) -> float:
    if lag >= 0:
        x = a[lag:]
        y = b[:len(x)]
    else:
        y = b[-lag:]
        x = a[:len(y)]
    count = min(len(x), len(y))
    if count < 128:
        return 0.0
    x = x[:count:4]
    y = y[:count:4]
    xx = sum(float(v) * v for v in x)
    yy = sum(float(v) * v for v in y)
    xy = sum(float(p) * q for p, q in zip(x, y))
    return 0.0 if xx <= 1e-12 or yy <= 1e-12 else xy / math.sqrt(xx * yy)


def si_sdr(reference: list[int], estimate: list[int]) -> float:
    best_lag = max(range(-48, 49), key=lambda lag: abs(normalized_corr(reference, estimate, lag)))
    if best_lag >= 0:
        ref = reference[best_lag:]
        est = estimate[:len(ref)]
    else:
        est = estimate[-best_lag:]
        ref = reference[:len(est)]
    count = min(len(ref), len(est))
    ref = ref[:count]
    est = est[:count]
    ref_energy = sum(float(x) * x for x in ref)
    if ref_energy <= 1e-12:
        return -120.0
    scale = sum(float(r) * e for r, e in zip(ref, est)) / ref_energy
    target = sum((scale * r) ** 2 for r in ref)
    noise = sum((e - scale * r) ** 2 for r, e in zip(ref, est))
    return 10.0 * math.log10((target + 1e-12) / (noise + 1e-12))


def physical_tdoa_samples(spacing_mm: float, angle_deg: float) -> float:
    return spacing_mm * RATE / SOUND_MM_S * math.sin(math.radians(angle_deg))


def alias_free_hz(spacing_mm: float) -> float:
    return SOUND_MM_S / (2.0 * spacing_mm)


def run_processor(processor: Path, mic: list[int], spacing_mm: float, work: Path, tag: str) -> list[int]:
    mic_path = work / f"{tag}-mic.pcm"
    out_path = work / f"{tag}-out.pcm"
    write_pcm(mic_path, mic)
    env = dict(os.environ)
    env["AP_RESEARCH_MIC_SPACING_MM"] = f"{spacing_mm:.6f}"
    subprocess.run([
        str(processor), "--sample-rate", str(RATE), "--mic-channels", "2",
        "--capture-only", "--capture-profile", "bf-isolated",
        str(mic_path), str(out_path),
    ], check=True, env=env)
    return read_pcm(out_path)


def fractional_reference(left: list[int], right: list[int], tdoa: float,
                         right_gain: float, calibrate_gain: bool) -> list[int]:
    delayed_left = fractional_delay(left, tdoa)
    scale = 1.0 / right_gain if calibrate_gain else 1.0
    return [clamp16(0.5 * (a + scale * b)) for a, b in zip(delayed_left, right)]


def aggregate(rows: list[dict]) -> dict:
    result = {}
    for spacing in SPACINGS_MM:
        subset = [row for row in rows if row["spacing_mm"] == spacing]
        modes = {}
        for mode in ("shipping_fixed", "integer_tracking",
                     "fractional_reference", "calibrated_fractional_reference"):
            values = [float(row["si_sdr_improvement_db"][mode]) for row in subset]
            modes[mode] = {
                "min": min(values),
                "median": statistics.median(values),
                "max": max(values),
            }
        result[str(int(spacing))] = {
            "spacing_mm": spacing,
            "max_tdoa_samples": physical_tdoa_samples(spacing, 90.0),
            "alias_free_hz": alias_free_hz(spacing),
            "modes": modes,
        }
    return result


def run(fixed_processor: Path, tracking_processor: Path, output: Path) -> dict:
    rows: list[dict] = []
    samples = 4 * RATE
    with tempfile.TemporaryDirectory(prefix="pcr02-bf-geometry-") as tmp:
        work = Path(tmp)
        for seed in SEEDS:
            clean = speech_like(samples, seed)
            left = mix(clean, sensor_noise(samples, seed + 11))
            baseline = si_sdr(clean, left)
            for spacing in SPACINGS_MM:
                for angle in ANGLES_DEG:
                    tdoa = physical_tdoa_samples(spacing, angle)
                    delayed_clean = fractional_delay(clean, tdoa)
                    right_noise = sensor_noise(samples, seed + 23)
                    for gain in GAIN_RATIOS:
                        right = [clamp16(gain * (s + n))
                                 for s, n in zip(delayed_clean, right_noise)]
                        mic = interleave(left, right)
                        token = f"s{seed}-d{int(spacing)}-a{int(angle)}-g{int(round(gain*100))}"
                        fixed = run_processor(fixed_processor, mic, spacing, work, token + "-fixed")
                        tracking = run_processor(tracking_processor, mic, spacing, work, token + "-track")
                        frac = fractional_reference(left, right, tdoa, gain, False)
                        cal = fractional_reference(left, right, tdoa, gain, True)
                        scores = {
                            "shipping_fixed": si_sdr(clean, fixed) - baseline,
                            "integer_tracking": si_sdr(clean, tracking) - baseline,
                            "fractional_reference": si_sdr(clean, frac) - baseline,
                            "calibrated_fractional_reference": si_sdr(clean, cal) - baseline,
                        }
                        rows.append({
                            "seed": seed,
                            "spacing_mm": spacing,
                            "angle_deg": angle,
                            "right_global_gain": gain,
                            "physical_tdoa_samples": tdoa,
                            "input_mic0_si_sdr_db": baseline,
                            "si_sdr_improvement_db": scores,
                        })
    result = {
        "schema_version": 1,
        "authority": "diagnostic-regression-only",
        "promotion_allowed": False,
        "shipping_incumbent": {
            "mic_spacing_mm": INCUMBENT_SPACING_MM,
            "direction_tracking": False,
            "steering": "fixed-zero-integer-delay",
        },
        "reference_modes_are_nonshipping": [
            "fractional_reference", "calibrated_fractional_reference"
        ],
        "conditions": {
            "sample_rate_hz": RATE,
            "spacings_mm": list(SPACINGS_MM),
            "angles_deg": list(ANGLES_DEG),
            "right_global_gain": list(GAIN_RATIOS),
            "seeds": list(SEEDS),
        },
        "incumbent_geometry": {
            "max_tdoa_samples": physical_tdoa_samples(INCUMBENT_SPACING_MM, 90.0),
            "alias_free_hz": alias_free_hz(INCUMBENT_SPACING_MM),
        },
        "summary_by_spacing": aggregate(rows),
        "rows": rows,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result


def self_test() -> None:
    assert abs(physical_tdoa_samples(35.0, 90.0) - 1.6326530612) < 1e-6
    assert 4899.0 < alias_free_hz(35.0) < 4901.0
    impulse = [32767] + [0] * 31
    half = fractional_delay(impulse, 0.5)
    assert half[0] == 0 and 15000 < half[1] < 18000
    assert len(interleave([1, 2], [3, 4])) == 4
    print("PCR02 BF geometry counterfactual self-test: OK")


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--fixed-processor", type=Path)
    p.add_argument("--tracking-processor", type=Path)
    p.add_argument("--output", type=Path)
    p.add_argument("--self-test", action="store_true")
    args = p.parse_args()
    if args.self_test:
        self_test()
        return 0
    if not args.fixed_processor or not args.tracking_processor or not args.output:
        p.error("--fixed-processor, --tracking-processor and --output are required")
    result = run(args.fixed_processor, args.tracking_processor, args.output)
    inc = result["summary_by_spacing"]["35"]["modes"]
    print(json.dumps({
        "authority": result["authority"],
        "promotion_allowed": result["promotion_allowed"],
        "incumbent_35mm": inc,
        "max_tdoa_samples": result["incumbent_geometry"]["max_tdoa_samples"],
        "alias_free_hz": result["incumbent_geometry"]["alias_free_hz"],
        "rows": len(result["rows"]),
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
