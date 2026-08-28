#!/usr/bin/env python3
"""Small dependency-free offline evaluation harness for audio-pipeline.

Private/product corpora stay outside the repository. This tool consumes S16LE
PCM files described by a manifest, optionally invokes ap_process_pcm, and emits
machine-readable metrics suitable for SKU certification records.
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
from typing import Iterable, Sequence


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
    return 20.0 * math.log10(math.sqrt(energy) / 32768.0)


def mono_channel(interleaved: Sequence[int], channels: int, channel: int) -> list[int]:
    if channels <= 0 or channel < 0 or channel >= channels:
        raise ValueError("invalid channel geometry")
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
    return 10.0 * math.log10((target_energy + 1.0e-12) / (noise_energy + 1.0e-12))


def max_abs_corr(a: Sequence[int], b: Sequence[int], max_lag: int) -> float:
    if not a or not b:
        return 0.0
    best = 0.0
    n = min(len(a), len(b))
    for lag in range(-max_lag, max_lag + 1):
        if lag >= 0:
            aa = a[lag:n]
            bb = b[: n - lag]
        else:
            aa = a[: n + lag]
            bb = b[-lag:n]
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


def evaluate(manifest_path: Path, processor: Path | None) -> dict:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    sample_rate = int(manifest["sample_rate_hz"])
    channels = int(manifest.get("mic_channels", 2))
    mic_path = resolve_path(manifest_path, manifest["mic_pcm"])
    render_path = resolve_path(manifest_path, manifest["render_pcm"])

    temporary = None
    if "output_pcm" in manifest:
        output_path = resolve_path(manifest_path, manifest["output_pcm"])
    else:
        temporary = tempfile.TemporaryDirectory(prefix="ap-eval-")
        output_path = Path(temporary.name) / "out.pcm"

    if processor is not None:
        subprocess.run(
            [str(processor), "--sample-rate", str(sample_rate),
             str(mic_path), str(render_path), str(output_path)],
            check=True,
        )
    if not output_path.exists():
        raise FileNotFoundError(f"output PCM does not exist: {output_path}")

    mic = read_s16le(mic_path)
    render = read_s16le(render_path)
    output = read_s16le(output_path)
    mic0 = mono_channel(mic, channels, 0)
    max_lag = max(1, sample_rate // 10)

    result = {
        "sample_rate_hz": sample_rate,
        "frames": min(len(output), len(render), len(mic0)),
        "input_rms_dbfs": rms_dbfs(mic0),
        "render_rms_dbfs": rms_dbfs(render),
        "output_rms_dbfs": rms_dbfs(output),
        "input_render_max_abs_corr": max_abs_corr(mic0, render, max_lag),
        "output_render_max_abs_corr": max_abs_corr(output, render, max_lag),
        "metadata": manifest.get("metadata", {}),
    }

    if "clean_near_pcm" in manifest:
        clean = read_s16le(resolve_path(manifest_path, manifest["clean_near_pcm"]))
        value = si_sdr_db(clean, output)
        result["near_si_sdr_db"] = value

    if temporary is not None:
        temporary.cleanup()
    return result


def self_test() -> None:
    rate = 16000
    ref = [int(12000 * math.sin(2.0 * math.pi * 440.0 * n / rate)) for n in range(rate // 2)]
    exact = list(ref)
    degraded = [x + (1200 if n % 2 else -1200) for n, x in enumerate(ref)]
    assert rms_dbfs([0] * 100) <= -119.0
    exact_score = si_sdr_db(ref, exact)
    degraded_score = si_sdr_db(ref, degraded)
    assert exact_score is not None and exact_score > 100.0
    assert degraded_score is not None and degraded_score < exact_score - 20.0
    assert max_abs_corr(ref, ref, 8) > 0.999
    print("audio-pipeline eval self-test: OK")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--processor", type=Path)
    parser.add_argument("--output-json", type=Path)
    parser.add_argument("--self-test", action="store_true")
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
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
