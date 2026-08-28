#!/usr/bin/env python3
"""Dependency-free offline acoustic evaluation for audio-pipeline.

Private/product corpora stay outside the repository. Manifests can describe
1/2-mic capture-only or full-duplex cases and optional per-case acceptance
thresholds. Results are deterministic JSON suitable for SKU certification.
"""

from __future__ import annotations

import argparse
import array
import json
import math
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Sequence


SUPPORTED_RATES = {8000, 16000, 24000, 32000, 48000}


def read_s16le(path: Path) -> list[int]:
    data = path.read_bytes()
    if len(data) % 2:
        raise ValueError(f"odd S16LE byte count: {path}")
    values = array.array("h")
    values.frombytes(data)
    if values.itemsize != 2:
        raise RuntimeError("unexpected host short size")
    if os.sys.byteorder != "little":
        values.byteswap()
    return list(values)


def rms_dbfs(samples: Sequence[int]) -> float:
    if not samples:
        return -120.0
    energy = sum(float(x) * float(x) for x in samples) / len(samples)
    if energy <= 1.0e-18:
        return -120.0
    return 10.0 * math.log10(energy / (32768.0 * 32768.0))


def mono_channel(interleaved: Sequence[int], channels: int, channel: int) -> list[int]:
    if channels <= 0 or channel < 0 or channel >= channels:
        raise ValueError("invalid channel geometry")
    if len(interleaved) % channels:
        raise ValueError("microphone PCM is not aligned to complete interleaved frames")
    return list(interleaved[channel::channels])


def si_sdr_db(reference: Sequence[int], estimate: Sequence[int]) -> float | None:
    count = min(len(reference), len(estimate))
    if count < 8:
        return None
    ref = [float(x) for x in reference[:count]]
    est = [float(x) for x in estimate[:count]]
    ref_energy = sum(x * x for x in ref)
    if ref_energy <= 1.0e-12:
        return None
    scale = sum(r * e for r, e in zip(ref, est)) / ref_energy
    target = [scale * r for r in ref]
    target_energy = sum(x * x for x in target)
    noise_energy = sum((e - t) * (e - t) for e, t in zip(est, target))
    return 10.0 * math.log10((target_energy + 1.0e-12) /
                             (noise_energy + 1.0e-12))


def max_abs_corr(a: Sequence[int], b: Sequence[int], max_lag: int) -> float:
    if not a or not b:
        return 0.0
    best = 0.0
    count = min(len(a), len(b))
    for lag in range(-max_lag, max_lag + 1):
        if lag >= 0:
            aa = a[lag:count]
            bb = b[: count - lag]
        else:
            aa = a[: count + lag]
            bb = b[-lag:count]
        if len(aa) < 16:
            continue
        xy = sum(float(x) * float(y) for x, y in zip(aa, bb))
        xx = sum(float(x) * float(x) for x in aa)
        yy = sum(float(y) * float(y) for y in bb)
        if xx > 1.0e-12 and yy > 1.0e-12:
            best = max(best, abs(xy / math.sqrt(xx * yy)))
    return best


def resolve_path(manifest_path: Path, value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else manifest_path.parent / path


def validate_manifest(manifest: dict) -> None:
    rate = int(manifest.get("sample_rate_hz", 0))
    channels = int(manifest.get("mic_channels", 2))
    if rate not in SUPPORTED_RATES:
        raise ValueError(f"unsupported sample_rate_hz: {rate}")
    if channels not in (1, 2):
        raise ValueError(f"mic_channels must be 1 or 2, got {channels}")
    if not manifest.get("mic_pcm"):
        raise ValueError("mic_pcm is required")
    expected = manifest.get("expected", {})
    known = {
        "min_near_si_sdr_db",
        "min_output_rms_dbfs",
        "max_output_rms_dbfs",
        "max_output_render_abs_corr",
        "max_output_render_corr_ratio",
        "min_output_render_corr_reduction",
    }
    unknown = set(expected) - known
    if unknown:
        raise ValueError(f"unknown expected thresholds: {sorted(unknown)}")
    render_only = {
        "max_output_render_abs_corr",
        "max_output_render_corr_ratio",
        "min_output_render_corr_reduction",
    }
    if not manifest.get("render_pcm") and render_only.intersection(expected):
        raise ValueError("render correlation thresholds require render_pcm")
    if "min_near_si_sdr_db" in expected and not manifest.get("clean_near_pcm"):
        raise ValueError("min_near_si_sdr_db requires clean_near_pcm")


def invoke_processor(processor: Path,
                     sample_rate: int,
                     channels: int,
                     mic_path: Path,
                     render_path: Path | None,
                     output_path: Path) -> None:
    command = [
        str(processor),
        "--sample-rate", str(sample_rate),
        "--mic-channels", str(channels),
    ]
    if render_path is None:
        command.append("--capture-only")
        command.extend([str(mic_path), str(output_path)])
    else:
        command.extend([str(mic_path), str(render_path), str(output_path)])
    subprocess.run(command, check=True)


def apply_thresholds(result: dict, expected: dict) -> list[dict]:
    violations: list[dict] = []

    def minimum(name: str, metric: str) -> None:
        if name in expected:
            value = result.get(metric)
            limit = float(expected[name])
            if value is None or float(value) < limit:
                violations.append({"gate": name, "metric": metric,
                                   "actual": value, "expected_min": limit})

    def maximum(name: str, metric: str) -> None:
        if name in expected:
            value = result.get(metric)
            limit = float(expected[name])
            if value is None or float(value) > limit:
                violations.append({"gate": name, "metric": metric,
                                   "actual": value, "expected_max": limit})

    minimum("min_near_si_sdr_db", "near_si_sdr_db")
    minimum("min_output_rms_dbfs", "output_rms_dbfs")
    maximum("max_output_rms_dbfs", "output_rms_dbfs")
    maximum("max_output_render_abs_corr", "output_render_max_abs_corr")
    maximum("max_output_render_corr_ratio", "output_render_corr_ratio")
    minimum("min_output_render_corr_reduction", "output_render_corr_reduction")
    return violations


def evaluate(manifest_path: Path, processor: Path | None) -> dict:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    validate_manifest(manifest)
    sample_rate = int(manifest["sample_rate_hz"])
    channels = int(manifest.get("mic_channels", 2))
    mic_path = resolve_path(manifest_path, manifest["mic_pcm"])
    render_path = (resolve_path(manifest_path, manifest["render_pcm"])
                   if manifest.get("render_pcm") else None)

    temporary = None
    if "output_pcm" in manifest:
        output_path = resolve_path(manifest_path, manifest["output_pcm"])
    else:
        temporary = tempfile.TemporaryDirectory(prefix="ap-eval-")
        output_path = Path(temporary.name) / "out.pcm"

    if processor is not None:
        invoke_processor(processor,
                         sample_rate,
                         channels,
                         mic_path,
                         render_path,
                         output_path)
    if not output_path.exists():
        raise FileNotFoundError(f"output PCM does not exist: {output_path}")

    mic = read_s16le(mic_path)
    output = read_s16le(output_path)
    mic0 = mono_channel(mic, channels, 0)
    result = {
        "case_id": manifest.get("case_id", manifest_path.stem),
        "sample_rate_hz": sample_rate,
        "mic_channels": channels,
        "capture_only": render_path is None,
        "frames": min(len(output), len(mic0)),
        "input_rms_dbfs": rms_dbfs(mic0),
        "output_rms_dbfs": rms_dbfs(output),
        "metadata": manifest.get("metadata", {}),
    }

    if render_path is not None:
        render = read_s16le(render_path)
        max_lag = max(1, sample_rate // 10)
        input_corr = max_abs_corr(mic0, render, max_lag)
        output_corr = max_abs_corr(output, render, max_lag)
        result.update({
            "frames": min(result["frames"], len(render)),
            "render_rms_dbfs": rms_dbfs(render),
            "input_render_max_abs_corr": input_corr,
            "output_render_max_abs_corr": output_corr,
            "output_render_corr_ratio": output_corr / max(input_corr, 1.0e-9),
            "output_render_corr_reduction": max(0.0, input_corr - output_corr),
        })

    if "clean_near_pcm" in manifest:
        clean = read_s16le(resolve_path(manifest_path, manifest["clean_near_pcm"]))
        result["near_si_sdr_db"] = si_sdr_db(clean, output)

    expected = manifest.get("expected", {})
    violations = apply_thresholds(result, expected)
    result["expected"] = expected
    result["violations"] = violations
    result["passed"] = not violations

    if temporary is not None:
        temporary.cleanup()
    return result


def self_test() -> None:
    rate = 16000
    ref = [int(12000 * math.sin(2.0 * math.pi * 440.0 * n / rate))
           for n in range(rate // 2)]
    exact = list(ref)
    degraded = [x + (1200 if n % 2 else -1200)
                for n, x in enumerate(ref)]
    assert rms_dbfs([0] * 100) <= -119.0
    exact_score = si_sdr_db(ref, exact)
    degraded_score = si_sdr_db(ref, degraded)
    assert exact_score is not None and exact_score > 100.0
    assert degraded_score is not None and degraded_score < exact_score - 20.0
    assert max_abs_corr(ref, ref, 8) > 0.999
    synthetic = {
        "near_si_sdr_db": 12.0,
        "output_rms_dbfs": -18.0,
        "output_render_corr_ratio": 0.2,
        "output_render_corr_reduction": 0.6,
        "output_render_max_abs_corr": 0.2,
    }
    assert not apply_thresholds(synthetic, {
        "min_near_si_sdr_db": 10.0,
        "max_output_render_corr_ratio": 0.5,
    })
    assert apply_thresholds(synthetic, {"min_near_si_sdr_db": 20.0})
    print("audio-pipeline eval self-test: OK")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--processor", type=Path)
    parser.add_argument("--output-json", type=Path)
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--enforce-thresholds", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        self_test()
        return 0
    if args.manifest is None:
        parser.error("--manifest is required unless --self-test is used")
    result = evaluate(args.manifest, args.processor)
    encoded = json.dumps(result, indent=2, sort_keys=True)
    if args.output_json:
        args.output_json.write_text(encoded + "\n", encoding="utf-8")
    else:
        print(encoded)
    return 0 if (result["passed"] or not args.enforce_thresholds) else 1


if __name__ == "__main__":
    raise SystemExit(main())
