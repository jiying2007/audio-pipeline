#!/usr/bin/env python3
"""Build a canonical validation-grade corpus from pinned public data caches."""

from __future__ import annotations

import argparse
import array
import bz2
import csv
import hashlib
import io
import json
import math
import os
import re
import tempfile
import wave
import zipfile
from pathlib import Path

from dataset_lock import load_json, sha256_file, validate_lock, verify_local


def sha1_file(path: Path) -> str:
    digest = hashlib.sha1()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def wav_info(path: Path) -> tuple[int, int, int]:
    with wave.open(str(path), "rb") as handle:
        if handle.getsampwidth() != 2 or handle.getcomptype() != "NONE":
            raise ValueError(f"only PCM16 WAV is supported: {path}")
        return handle.getframerate(), handle.getnchannels(), handle.getnframes()


def read_wav_bytes(data: bytes) -> tuple[list[int], int, int]:
    with wave.open(io.BytesIO(data), "rb") as handle:
        if handle.getsampwidth() != 2 or handle.getcomptype() != "NONE":
            raise ValueError("only PCM16 WAV is supported")
        rate = handle.getframerate()
        channels = handle.getnchannels()
        raw = handle.readframes(handle.getnframes())
    values = array.array("h")
    values.frombytes(raw)
    if os.sys.byteorder != "little":
        values.byteswap()
    if channels > 1:
        values = array.array("h", values[::channels])
    return list(values), rate, 1


def read_wav(path: Path) -> tuple[list[int], int, int]:
    return read_wav_bytes(path.read_bytes())


def write_pcm(path: Path, samples: list[int]) -> None:
    values = array.array("h", samples)
    if os.sys.byteorder != "little":
        values.byteswap()
    path.write_bytes(values.tobytes())


def clamp16(value: float) -> int:
    return max(-32768, min(32767, int(round(value))))


def resample_linear(samples: list[int], source_rate: int, target_rate: int) -> list[int]:
    if source_rate == target_rate:
        return list(samples)
    if not samples:
        return []
    target_count = max(1, int(round(len(samples) * target_rate / source_rate)))
    scale = source_rate / target_rate
    output = []
    for i in range(target_count):
        pos = i * scale
        left = min(len(samples) - 1, int(pos))
        right = min(len(samples) - 1, left + 1)
        fraction = pos - left
        output.append(clamp16((1.0 - fraction) * samples[left] + fraction * samples[right]))
    return output


def normalize_pair_key(path: Path) -> str:
    stem = path.stem.lower()
    stem = re.sub(r"(?:^|[_-])(noisy|clean|noise)(?:[_-]|$)", "_", stem)
    stem = stem.replace("noisy", "").replace("clean", "")
    return re.sub(r"[^a-z0-9]+", "", stem)


def load_dns_checksum_index(path: Path) -> dict[str, tuple[int, str]]:
    index: dict[str, tuple[int, str]] = {}
    with bz2.open(path, "rt", encoding="utf-8", errors="replace") as handle:
        for row in csv.reader(handle):
            if len(row) < 3:
                continue
            try:
                size = int(row[0])
            except ValueError:
                continue
            digest = row[1].strip().lower()
            rel = row[2].strip().replace("\\", "/").lstrip("./")
            index[rel] = (size, digest)
    if not index:
        raise ValueError("DNS checksum index is empty")
    return index


def verify_dns_file(path: Path, dns_repo: Path, dns_data_root: Path,
                    index: dict[str, tuple[int, str]]) -> tuple[str, str]:
    candidates = []
    for base in (dns_repo, dns_data_root):
        try:
            candidates.append(path.relative_to(base).as_posix())
        except ValueError:
            pass
    try:
        rel = path.relative_to(dns_data_root).as_posix()
        candidates.append("datasets_fullband/" + rel)
    except ValueError:
        pass
    for candidate in candidates:
        if candidate in index:
            expected_size, expected_sha1 = index[candidate]
            if path.stat().st_size != expected_size:
                raise ValueError(f"DNS file size mismatch: {path}")
            actual = sha1_file(path)
            if actual != expected_sha1:
                raise ValueError(f"DNS SHA1 mismatch: {path}")
            return candidate, actual
    raise ValueError(f"DNS file is not present in the pinned upstream checksum index: {path}")


def pair_dns(dns_data_root: Path) -> list[tuple[Path, Path]]:
    wavs = sorted(dns_data_root.rglob("*.wav"))
    clean: dict[str, list[Path]] = {}
    noisy: dict[str, list[Path]] = {}
    for path in wavs:
        text = (path.name + "/" + path.parent.name).lower()
        key = normalize_pair_key(path)
        if not key:
            continue
        if "noisy" in text:
            noisy.setdefault(key, []).append(path)
        elif "clean" in text:
            clean.setdefault(key, []).append(path)
    pairs = []
    for key in sorted(set(clean) & set(noisy)):
        pairs.append((sorted(noisy[key])[0], sorted(clean[key])[0]))
    return pairs


def pair_aec(aec_root: Path) -> list[tuple[str, Path, Path]]:
    base = aec_root / "datasets" / "test_set_icassp2022"
    pairs = []
    for scenario in ("farend-singletalk", "doubletalk", "nearend-singletalk"):
        directory = base / scenario
        for mic in sorted(directory.glob("*_mic.wav")):
            lpb = mic.with_name(mic.name[:-8] + "_lpb.wav")
            if lpb.exists():
                pairs.append((scenario, mic, lpb))
    return pairs


def interleave(left: list[int], right: list[int]) -> list[int]:
    count = min(len(left), len(right))
    out = []
    for i in range(count):
        out.extend((left[i], right[i]))
    return out


def convolve_short(signal: list[int], rir: list[int], taps: int = 96) -> list[int]:
    impulse = rir[:min(taps, len(rir))]
    scale = max(1.0, max(abs(x) for x in impulse))
    h = [x / scale for x in impulse]
    norm = sum(abs(x) for x in h) or 1.0
    h = [x / norm for x in h]
    out = [0] * len(signal)
    for n in range(len(signal)):
        value = 0.0
        for k, coeff in enumerate(h):
            if k > n:
                break
            value += coeff * signal[n - k]
        out[n] = clamp16(value)
    return out


def frame_labels(signal: list[int], rate: int) -> list[int]:
    frame = rate // 100
    energies = []
    for start in range(0, len(signal) - frame + 1, frame):
        window = signal[start:start + frame]
        energies.append(sum(float(x) * float(x) for x in window) / frame)
    if not energies:
        return []
    peak = max(energies)
    threshold = peak * 0.008
    return [1 if e > threshold else 0 for e in energies]


def select_zip_members(archive: Path) -> tuple[list[str], list[str]]:
    with zipfile.ZipFile(archive) as zf:
        names = sorted(name for name in zf.namelist() if name.lower().endswith(".wav"))
    rirs = [name for name in names if "rir" in name.lower()]
    noises = [name for name in names if "noise" in name.lower()]
    if not rirs or not noises:
        raise ValueError("could not find RIR/noise WAV members in SLR28 archive")
    return rirs, noises


def write_robot_sim(output: Path, clean_candidates: list[tuple[Path, dict]], archive: Path,
                    count: int, cases: list[dict]) -> None:
    prepared: list[tuple[list[int], dict]] = []
    for clean_path, dns_source in clean_candidates:
        clean, clean_rate, _ = read_wav(clean_path)
        clean16 = resample_linear(clean, clean_rate, 16000)
        clean16 = clean16[:min(len(clean16), 16000 * 8)]
        if len(clean16) >= 16000 * 2:
            prepared.append((clean16, dns_source))
        if len(prepared) >= min(max(count, 1), 12):
            break
    if not prepared:
        return

    rir_names, noise_names = select_zip_members(archive)
    archive_sha = sha256_file(archive)
    with zipfile.ZipFile(archive) as zf:
        for index in range(count):
            clean16, dns_source = prepared[index % len(prepared)]
            rir_name = rir_names[index % len(rir_names)]
            noise_name = noise_names[(index * 3 + index // max(1, len(rir_names))) % len(noise_names)]
            rir, rir_rate, _ = read_wav_bytes(zf.read(rir_name))
            noise, noise_rate, _ = read_wav_bytes(zf.read(noise_name))
            rir = resample_linear(rir, rir_rate, 16000)
            noise = resample_linear(noise, noise_rate, 16000)
            target = convolve_short(clean16, rir)
            if not target or not noise:
                continue
            repeated_noise = [noise[i % len(noise)] for i in range(len(target))]
            peak_target = max(1, max(abs(x) for x in target))
            peak_noise = max(1, max(abs(x) for x in repeated_noise))
            delay = 1 + index % 5
            noise_gain = [0.16, 0.24, 0.35, 0.50, 0.70][index % 5] * peak_target / peak_noise
            left = [clamp16(target[i] + noise_gain * repeated_noise[i]) for i in range(len(target))]
            delayed = [0] * delay + target[:-delay]
            decorrelation = 97 + (index * 137) % max(1, len(repeated_noise))
            right = [clamp16(delayed[i] + noise_gain * repeated_noise[(i + decorrelation) % len(repeated_noise)])
                     for i in range(len(target))]
            case_id = f"robot-sim-bf-{index:03d}"
            case_dir = output / "cases" / case_id
            case_dir.mkdir(parents=True, exist_ok=True)
            write_pcm(case_dir / "mic.pcm", interleave(left, right))
            write_pcm(case_dir / "clean.pcm", target)
            labels = frame_labels(target, 16000)
            (case_dir / "vad.labels").write_text("".join(f"{x}\n" for x in labels), encoding="utf-8")
            cases.append({
                "case_id": case_id, "split": "validation", "scenario": "bf-offaxis",
                "sample_rate_hz": 16000, "mic_channels": 2,
                "mic_audio": str((case_dir / "mic.pcm").relative_to(output)),
                "render_audio": None, "clean_near_audio": str((case_dir / "clean.pcm").relative_to(output)),
                "echo_audio": None, "vad_labels": str((case_dir / "vad.labels").relative_to(output)),
                "control": {}, "expected": {},
                "source": {
                    "dataset_id": "openslr-slr28+microsoft-dns-challenge",
                    "source_id": case_id, "clean": dns_source,
                    "rir_member": rir_name, "noise_member": noise_name,
                    "slr28_archive_sha256": archive_sha
                }
            })


def self_test() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        archive = Path(tmp) / "members.zip"
        with zipfile.ZipFile(archive, "w") as zf:
            for name in (
                "room-b/noise-z.wav", "room-a/rir-2.wav", "room-a/rir-1.wav",
                "room-b/noise-a.wav", "room-c/ambient.wav",
            ):
                zf.writestr(name, b"")
        rirs, noises = select_zip_members(archive)
        assert rirs == ["room-a/rir-1.wav", "room-a/rir-2.wav"]
        assert noises == ["room-b/noise-a.wav", "room-b/noise-z.wav"]
    print("public corpus diversity self-test: OK")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--lock", type=Path, default=Path("validation/datasets.lock.json"))
    parser.add_argument("--seal", type=Path)
    parser.add_argument("--data-root", type=Path)
    parser.add_argument("--dns-data-root", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--aec-limit", type=int, default=60)
    parser.add_argument("--dns-limit", type=int, default=60)
    parser.add_argument("--robot-sim-limit", type=int, default=20)
    args = parser.parse_args()

    if args.self_test:
        self_test()
        return 0
    if args.seal is None or args.data_root is None or args.output is None:
        parser.error("--seal, --data-root and --output are required unless --self-test is used")

    lock = load_json(args.lock)
    validate_lock(lock)
    verify_local(args.lock, args.data_root, args.seal, validation_grade=True, require_materialized=True)
    seal = json.loads(args.seal.read_text(encoding="utf-8"))
    aec_root = args.data_root / "AEC-Challenge"
    dns_repo = args.data_root / "DNS-Challenge"
    dns_data_root = args.dns_data_root or (dns_repo / "datasets_fullband")
    if not dns_data_root.exists():
        raise FileNotFoundError(f"DNS data root does not exist: {dns_data_root}")
    dns_seal = seal["datasets"]["microsoft-dns-challenge"]
    index_path = Path(dns_seal["checksum_index_path"])
    if not index_path.is_absolute():
        index_path = args.data_root / index_path
    dns_index = load_dns_checksum_index(index_path)
    slr_seal = seal["datasets"]["openslr-slr28"]
    slr_archive = Path(slr_seal["path"])
    if not slr_archive.is_absolute():
        slr_archive = args.data_root / slr_archive
    if sha256_file(slr_archive) != slr_seal["sha256"]:
        raise ValueError("SLR28 archive does not match local seal")

    args.output.mkdir(parents=True, exist_ok=True)
    cases: list[dict] = []

    for scenario, mic, render in pair_aec(aec_root)[:max(0, args.aec_limit)]:
        rate, channels, _ = wav_info(mic)
        render_rate, render_channels, _ = wav_info(render)
        if channels != 1 or render_channels != 1 or rate != render_rate:
            continue
        source_id = mic.stem[:-4]
        cases.append({
            "case_id": "aec-" + hashlib.sha256(source_id.encode()).hexdigest()[:16],
            "split": "validation", "scenario": "aec-" + scenario,
            "sample_rate_hz": rate, "mic_channels": 1,
            "mic_audio": str(mic.resolve()), "render_audio": str(render.resolve()),
            "clean_near_audio": None, "echo_audio": None, "vad_labels": None,
            "control": {}, "expected": {},
            "source": {"dataset_id": "microsoft-aec-challenge", "source_id": source_id,
                       "mic_sha256": sha256_file(mic), "render_sha256": sha256_file(render)}
        })

    dns_pairs = pair_dns(dns_data_root)
    robot_clean_candidates: list[tuple[Path, dict]] = []
    for noisy, clean in dns_pairs[:max(0, args.dns_limit)]:
        noisy_rel, noisy_sha1 = verify_dns_file(noisy, dns_repo, dns_data_root, dns_index)
        clean_rel, clean_sha1 = verify_dns_file(clean, dns_repo, dns_data_root, dns_index)
        rate, channels, _ = wav_info(noisy)
        clean_rate, clean_channels, _ = wav_info(clean)
        if channels != 1 or clean_channels != 1 or rate != clean_rate or rate not in {8000, 16000, 24000, 32000, 48000}:
            continue
        source_id = normalize_pair_key(noisy)
        source = {"dataset_id": "microsoft-dns-challenge", "source_id": source_id,
                  "noisy_path": noisy_rel, "noisy_sha1": noisy_sha1,
                  "clean_path": clean_rel, "clean_sha1": clean_sha1}
        cases.append({
            "case_id": "dns-" + hashlib.sha256((noisy_rel + clean_rel).encode()).hexdigest()[:16],
            "split": "validation", "scenario": "ns-public-real",
            "sample_rate_hz": rate, "mic_channels": 1,
            "mic_audio": str(noisy.resolve()), "render_audio": None,
            "clean_near_audio": str(clean.resolve()), "echo_audio": None, "vad_labels": None,
            "control": {}, "processor_profile": "ns-isolated", "expected": {}, "source": source
        })
        robot_clean_candidates.append((clean, source))

    if args.robot_sim_limit and robot_clean_candidates:
        write_robot_sim(args.output, robot_clean_candidates, slr_archive,
                        args.robot_sim_limit, cases)

    if not cases:
        raise SystemExit("no public validation cases were built")
    corpus = {
        "schema_version": 1,
        "corpus_id": "public-validation-v1",
        "tier": "validation-grade",
        "generator": {"name": "build_public_corpus.py", "version": 2},
        "sources": ["microsoft-aec-challenge", "microsoft-dns-challenge", "openslr-slr28"],
        "sealed_data": True,
        "dataset_lock_sha256": sha256_file(args.lock),
        "local_seal_sha256": sha256_file(args.seal),
        "cases": cases,
    }
    path = args.output / "corpus.json"
    path.write_text(json.dumps(corpus, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"corpus": str(path), "cases": len(cases),
                      "aec": sum(1 for c in cases if c["scenario"].startswith("aec-")),
                      "dns": sum(1 for c in cases if c["scenario"] == "ns-public-real"),
                      "robot_sim": sum(1 for c in cases if c["scenario"] == "bf-offaxis")}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
