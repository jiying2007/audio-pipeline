#!/usr/bin/env python3
"""Build a deterministic multi-dataset research-development corpus.

This corpus is selection-only (`research-validation` tier). It intentionally
uses sources disjoint from the validation-grade blind archive set.
"""
from __future__ import annotations

import argparse
import array
import hashlib
import json
import math
import os
import subprocess
from pathlib import Path

from build_public_corpus import clamp16, convolve_short, frame_labels, read_wav, resample_linear, write_pcm
from dataset_lock import sha256_file

RATE = 16000
EXPECTED_CATALOG = "audio-pipeline-public-development-v2"
SOURCES = ["openslr-slr31", "openslr-slr26", "demand"]


def load_json(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("JSON object required")
    return payload


def stable(paths: list[Path], root: Path, seed: int) -> list[Path]:
    def key(path: Path) -> str:
        rel = path.relative_to(root).as_posix()
        return hashlib.sha256(f"{seed}:{rel}".encode()).hexdigest()
    return sorted(paths, key=key)


def decode_flac(path: Path) -> list[int]:
    proc = subprocess.run(
        ["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-i", str(path),
         "-f", "s16le", "-ac", "1", "-ar", str(RATE), "pipe:1"],
        check=True, stdout=subprocess.PIPE,
    )
    values = array.array("h")
    values.frombytes(proc.stdout)
    if os.sys.byteorder != "little":
        values.byteswap()
    return list(values)


def rms(samples: list[int]) -> float:
    if not samples:
        return 0.0
    return math.sqrt(sum(float(x) * float(x) for x in samples) / len(samples))


def repeat_segment(samples: list[int], count: int, offset: int) -> list[int]:
    if not samples:
        raise ValueError("empty audio source")
    n = len(samples)
    return [samples[(offset + i) % n] for i in range(count)]


def mix_snr(target: list[int], noise: list[int], snr_db: float, offset: int) -> tuple[list[int], float]:
    n = repeat_segment(noise, len(target), offset)
    tr = max(rms(target), 1.0)
    nr = max(rms(n), 1.0)
    gain = tr / (nr * (10.0 ** (snr_db / 20.0)))
    mixed = [clamp16(target[i] + gain * n[i]) for i in range(len(target))]
    return mixed, gain


def zeros_labels(samples: list[int]) -> list[int]:
    frame = RATE // 100
    return [0] * (len(samples) // frame)


def write_labels(path: Path, labels: list[int]) -> None:
    path.write_text("".join(f"{x}\n" for x in labels), encoding="utf-8")


def source_record(path: Path, root: Path, dataset_id: str) -> dict:
    return {
        "dataset_id": dataset_id,
        "path": path.relative_to(root).as_posix(),
        "sha256": sha256_file(path),
    }


def select_audio(materialized_root: Path, seed: int) -> tuple[list[Path], list[Path], list[Path]]:
    extracted = materialized_root / "extracted"
    clean_root = extracted / "clean-speech"
    rir_root = extracted / "sim-rir"
    noise_roots = [extracted / "noise-kitchen", extracted / "noise-traffic"]
    clean = stable(sorted(clean_root.rglob("*.flac")), clean_root, seed)
    rirs = stable(sorted(rir_root.rglob("*.wav")), rir_root, seed + 11)
    noises: list[Path] = []
    for index, root in enumerate(noise_roots):
        noises.extend(stable(sorted(root.rglob("*.wav")), root, seed + 101 + index))
    if len(clean) < 8 or len(rirs) < 4 or len(noises) < 4:
        raise ValueError(f"insufficient development audio clean={len(clean)} rir={len(rirs)} noise={len(noises)}")
    return clean, rirs, noises


def build(lock_path: Path, materialization_path: Path, data_root: Path, output: Path,
          seed: int, mix_limit: int, noise_limit: int, clean_limit: int) -> dict:
    lock = load_json(lock_path)
    if lock.get("schema_version") != 1 or lock.get("catalog_id") != EXPECTED_CATALOG:
        raise ValueError("development lock identity mismatch")
    materialization = load_json(materialization_path)
    if materialization.get("catalog_id") != EXPECTED_CATALOG:
        raise ValueError("development materialization identity mismatch")
    if materialization.get("dataset_lock_sha256") != sha256_file(lock_path):
        raise ValueError("development materialization/lock digest mismatch")
    if min(mix_limit, noise_limit, clean_limit) < 1:
        raise ValueError("all case limits must be positive")
    clean_paths, rir_paths, noise_paths = select_audio(data_root, seed)
    output.mkdir(parents=True, exist_ok=True)
    cases: list[dict] = []

    clean_cache: list[tuple[list[int], Path]] = []
    for path in clean_paths:
        samples = decode_flac(path)
        if len(samples) < RATE * 2:
            continue
        samples = samples[: RATE * 4]
        clean_cache.append((samples, path))
        if len(clean_cache) >= max(12, min(32, mix_limit // 2 + clean_limit)):
            break
    if len(clean_cache) < 8:
        raise ValueError("insufficient decoded clean speech")

    rir_cache: list[tuple[list[int], Path]] = []
    for path in rir_paths:
        try:
            values, rate, _channels = read_wav(path)
        except Exception:
            continue
        values = resample_linear(values, rate, RATE)
        if values and max(abs(x) for x in values) > 0:
            rir_cache.append((values, path))
        if len(rir_cache) >= 24:
            break
    if len(rir_cache) < 4:
        raise ValueError("insufficient readable SLR26 RIRs")

    noise_cache: list[tuple[list[int], Path, str]] = []
    for path in noise_paths:
        try:
            values, rate, _channels = read_wav(path)
        except Exception:
            continue
        values = resample_linear(values, rate, RATE)
        if len(values) >= RATE and max(abs(x) for x in values) > 0:
            domain = "kitchen" if "noise-kitchen" in path.as_posix() else "traffic"
            noise_cache.append((values, path, domain))
    if len(noise_cache) < 4:
        raise ValueError("insufficient readable DEMAND noise")

    snrs = (-5.0, 0.0, 5.0, 10.0, 15.0)
    for index in range(mix_limit):
        clean, clean_path = clean_cache[index % len(clean_cache)]
        use_reverb = index % 2 == 1
        rir_path = None
        target = clean
        if use_reverb:
            rir, rir_path = rir_cache[(index * 5 + seed) % len(rir_cache)]
            target = convolve_short(clean, rir, taps=32)
        noise, noise_path, domain = noise_cache[(index * 7 + seed) % len(noise_cache)]
        snr_db = snrs[(index + seed) % len(snrs)]
        offset = (seed * 997 + index * 7919) % len(noise)
        mic, gain = mix_snr(target, noise, snr_db, offset)
        case_id = f"public-dev-mix-{index:03d}"
        case_dir = output / "cases" / case_id
        case_dir.mkdir(parents=True, exist_ok=True)
        write_pcm(case_dir / "mic.pcm", mic)
        write_pcm(case_dir / "clean.pcm", target)
        write_labels(case_dir / "vad.labels", frame_labels(target, RATE))
        cases.append({
            "case_id": case_id, "split": "dev",
            "scenario": "research-public-noisy-reverb" if use_reverb else "research-public-noisy-clean",
            "sample_rate_hz": RATE, "mic_channels": 1,
            "mic_audio": str((case_dir / "mic.pcm").relative_to(output)),
            "render_audio": None,
            "clean_near_audio": str((case_dir / "clean.pcm").relative_to(output)),
            "echo_audio": None,
            "vad_labels": str((case_dir / "vad.labels").relative_to(output)),
            "control": {}, "processor_profile": "ns-isolated", "expected": {},
            "dimensions": {"snr_db": snr_db, "reverb": use_reverb, "noise_domain": domain},
            "source": {
                "dataset_id": "openslr-slr31+openslr-slr26+demand" if use_reverb else "openslr-slr31+demand",
                "clean": source_record(clean_path, data_root, "openslr-slr31"),
                "noise": source_record(noise_path, data_root, "demand"),
                "rir": None if rir_path is None else source_record(rir_path, data_root, "openslr-slr26"),
                "noise_gain": gain,
            },
        })

    for index in range(noise_limit):
        noise, noise_path, domain = noise_cache[(index * 3 + seed) % len(noise_cache)]
        start = (seed * 577 + index * 4099) % len(noise)
        mic = repeat_segment(noise, RATE * 4, start)
        case_id = f"public-dev-noise-{index:03d}"
        case_dir = output / "cases" / case_id
        case_dir.mkdir(parents=True, exist_ok=True)
        write_pcm(case_dir / "mic.pcm", mic)
        write_labels(case_dir / "vad.labels", zeros_labels(mic))
        cases.append({
            "case_id": case_id, "split": "dev", "scenario": "research-public-noise-only",
            "sample_rate_hz": RATE, "mic_channels": 1,
            "mic_audio": str((case_dir / "mic.pcm").relative_to(output)),
            "render_audio": None, "clean_near_audio": None, "echo_audio": None,
            "vad_labels": str((case_dir / "vad.labels").relative_to(output)),
            "control": {}, "processor_profile": "ns-isolated", "expected": {},
            "dimensions": {"noise_domain": domain},
            "source": {"dataset_id": "demand", "noise": source_record(noise_path, data_root, "demand")},
        })

    for index in range(clean_limit):
        clean, clean_path = clean_cache[(index * 5 + seed) % len(clean_cache)]
        case_id = f"public-dev-clean-{index:03d}"
        case_dir = output / "cases" / case_id
        case_dir.mkdir(parents=True, exist_ok=True)
        write_pcm(case_dir / "mic.pcm", clean)
        write_pcm(case_dir / "clean.pcm", clean)
        write_labels(case_dir / "vad.labels", frame_labels(clean, RATE))
        cases.append({
            "case_id": case_id, "split": "dev", "scenario": "research-public-clean-preservation",
            "sample_rate_hz": RATE, "mic_channels": 1,
            "mic_audio": str((case_dir / "mic.pcm").relative_to(output)),
            "render_audio": None,
            "clean_near_audio": str((case_dir / "clean.pcm").relative_to(output)),
            "echo_audio": None,
            "vad_labels": str((case_dir / "vad.labels").relative_to(output)),
            "control": {}, "processor_profile": "ns-isolated", "expected": {},
            "dimensions": {"clean_only": True},
            "source": {"dataset_id": "openslr-slr31", "clean": source_record(clean_path, data_root, "openslr-slr31")},
        })

    expected = mix_limit + noise_limit + clean_limit
    if len(cases) != expected:
        raise ValueError(f"development corpus expected {expected} cases, built {len(cases)}")
    corpus = {
        "schema_version": 1,
        "corpus_id": f"public-development-diverse-v2-seed-{seed}",
        "tier": "research-validation",
        "generator": {"name": "development-v2/build_corpus.py", "version": 1, "seed": seed},
        "sources": SOURCES,
        "sealed_data": True,
        "dataset_lock_sha256": sha256_file(lock_path),
        "materialization_sha256": sha256_file(materialization_path),
        "cases": cases,
    }
    corpus_path = output / "corpus.json"
    corpus_path.write_text(json.dumps(corpus, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {"corpus": str(corpus_path), "cases": len(cases), "mix": mix_limit, "noise": noise_limit, "clean": clean_limit}


def self_test() -> None:
    assert len(stable([Path("a"), Path("b")], Path("."), 7)) == 2
    mixed, gain = mix_snr([1000] * 320, [100] * 320, 0.0, 0)
    assert len(mixed) == 320 and gain > 0
    assert zeros_labels([0] * 320) == [0, 0]
    print("research development corpus self-test: OK")


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--self-test", action="store_true")
    p.add_argument("--lock", type=Path)
    p.add_argument("--materialization", type=Path)
    p.add_argument("--data-root", type=Path)
    p.add_argument("--output", type=Path)
    p.add_argument("--seed", type=int, default=1507)
    p.add_argument("--mix-limit", type=int, default=48)
    p.add_argument("--noise-limit", type=int, default=16)
    p.add_argument("--clean-limit", type=int, default=16)
    a = p.parse_args()
    if a.self_test:
        self_test(); return 0
    if None in (a.lock, a.materialization, a.data_root, a.output):
        p.error("--lock, --materialization, --data-root and --output are required")
    result = build(a.lock, a.materialization, a.data_root, a.output, a.seed, a.mix_limit, a.noise_limit, a.clean_limit)
    print(json.dumps({"result": "PASS", **result}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
