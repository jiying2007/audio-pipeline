#!/usr/bin/env python3
"""Build full public validation from compact coverage plus verified DNS raw sources."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from build_compact_public_corpus import (
    RATE,
    add_aec_cases,
    add_derived_cases,
    balanced_aec_pairs,
    prepare_clean_candidates,
)
from build_public_corpus import (
    clamp16,
    frame_labels,
    load_dns_checksum_index,
    pair_aec,
    read_wav,
    resample_linear,
    verify_dns_file,
    write_pcm,
)
from dataset_lock import load_json, sha256_file, validate_lock
from prepare_public_validation import verify as verify_cache


def classify_dns_wavs(root: Path) -> tuple[list[Path], list[Path]]:
    clean: list[Path] = []
    noise: list[Path] = []
    for path in root.rglob("*.wav"):
        rel = path.relative_to(root).as_posix().lower()
        if "noisy" in rel:
            continue
        if "clean" in rel:
            clean.append(path)
        elif "noise" in rel:
            noise.append(path)
    return sorted(clean), sorted(noise)


def stable_spread(paths: list[Path], root: Path) -> list[Path]:
    return sorted(paths, key=lambda path: hashlib.sha256(path.relative_to(root).as_posix().encode()).hexdigest())


def prepare_dns_audio(paths: list[Path], dns_repo: Path, dns_root: Path,
                      checksum_index: dict[str, tuple[int, str]], limit: int,
                      kind: str) -> list[tuple[list[int], dict]]:
    prepared: list[tuple[list[int], dict]] = []
    for path in stable_spread(paths, dns_root):
        rel, sha1 = verify_dns_file(path, dns_repo, dns_root, checksum_index)
        samples, rate, _ = read_wav(path)
        samples16 = resample_linear(samples, rate, RATE)
        samples16 = samples16[:min(len(samples16), RATE * 8)]
        if kind == "clean" and len(samples16) < RATE * 2:
            continue
        if not samples16 or max(abs(value) for value in samples16) == 0:
            continue
        prepared.append((samples16, {
            "path": rel,
            "sha1": sha1,
            "kind": kind,
            "source_rate_hz": rate,
        }))
        if len(prepared) >= limit:
            break
    return prepared


def add_dns_derived_cases(output: Path, dns_repo: Path, dns_root: Path,
                          checksum_index: dict[str, tuple[int, str]], count: int,
                          cases: list[dict]) -> None:
    clean_paths, noise_paths = classify_dns_wavs(dns_root)
    if len(clean_paths) < 2 or len(noise_paths) < 2:
        raise ValueError(
            f"DNS full profile requires official indexed clean and noise WAVs; "
            f"found clean={len(clean_paths)} noise={len(noise_paths)} under {dns_root}"
        )
    source_budget = min(max(count, 12), 32)
    cleans = prepare_dns_audio(clean_paths, dns_repo, dns_root, checksum_index,
                               source_budget, "clean")
    noises = prepare_dns_audio(noise_paths, dns_repo, dns_root, checksum_index,
                               source_budget, "noise")
    if len(cleans) < 2 or len(noises) < 2:
        raise ValueError(
            f"DNS full profile has insufficient verified PCM16 material: clean={len(cleans)} noise={len(noises)}"
        )

    for index in range(count):
        clean, clean_source = cleans[index % len(cleans)]
        noise, noise_source = noises[(index * 7 + index // max(1, len(cleans))) % len(noises)]
        repeated_noise = [noise[i % len(noise)] for i in range(len(clean))]
        peak_clean = max(1, max(abs(value) for value in clean))
        peak_noise = max(1, max(abs(value) for value in repeated_noise))
        noise_gain = [0.12, 0.20, 0.32, 0.50, 0.80][index % 5] * peak_clean / peak_noise
        noisy = [clamp16(clean[i] + noise_gain * repeated_noise[i]) for i in range(len(clean))]
        labels = frame_labels(clean, RATE)
        case_id = f"dns-derived-{index:03d}"
        case_dir = output / "cases" / case_id
        case_dir.mkdir(parents=True, exist_ok=True)
        write_pcm(case_dir / "mic.pcm", noisy)
        write_pcm(case_dir / "clean.pcm", clean)
        (case_dir / "vad.labels").write_text("".join(f"{value}\n" for value in labels), encoding="utf-8")
        cases.append({
            "case_id": case_id,
            "split": "validation",
            "scenario": "ns-public-derived-dns",
            "sample_rate_hz": RATE,
            "mic_channels": 1,
            "mic_audio": str((case_dir / "mic.pcm").relative_to(output)),
            "render_audio": None,
            "clean_near_audio": str((case_dir / "clean.pcm").relative_to(output)),
            "echo_audio": None,
            "vad_labels": str((case_dir / "vad.labels").relative_to(output)),
            "control": {},
            "processor_profile": "ns-isolated",
            "expected": {},
            "source": {
                "dataset_id": "microsoft-dns-challenge",
                "source_id": case_id,
                "clean": clean_source,
                "noise": noise_source,
                "mix_noise_gain": noise_gain,
            },
        })


def self_test() -> None:
    root = Path("/tmp/dns-self-test")
    paths = [
        root / "clean_fullband/en/a.wav",
        root / "clean_fullband/de/b.wav",
        root / "noise_fullband/x/c.wav",
        root / "noise_fullband/y/d.wav",
        root / "noisy/e.wav",
    ]
    # Classification logic is path based; avoid touching filesystem in the self-test.
    clean = [path for path in paths if "clean" in path.relative_to(root).as_posix().lower() and "noisy" not in path.as_posix().lower()]
    noise = [path for path in paths if "noise" in path.relative_to(root).as_posix().lower() and "noisy" not in path.as_posix().lower()]
    assert len(clean) == 2 and len(noise) == 2
    spread_a = [path.as_posix() for path in stable_spread(clean, root)]
    spread_b = [path.as_posix() for path in stable_spread(list(reversed(clean)), root)]
    assert spread_a == spread_b
    print("full public corpus self-test: OK")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--lock", type=Path, default=Path("validation/datasets.lock.json"))
    parser.add_argument("--seal", type=Path)
    parser.add_argument("--data-root", type=Path)
    parser.add_argument("--dns-data-root", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--aec-limit", type=int, default=60)
    parser.add_argument("--derived-limit", type=int, default=20,
                        help="AEC+SLR28 acoustic combinations; each emits NS + BF")
    parser.add_argument("--dns-limit", type=int, default=60,
                        help="verified DNS clean+noise derived NS cases")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    if args.seal is None or args.data_root is None or args.output is None:
        parser.error("--seal, --data-root and --output are required unless --self-test is used")
    if args.aec_limit < 3 or args.derived_limit < 4 or args.dns_limit < 2:
        parser.error("aec-limit >=3, derived-limit >=4 and dns-limit >=2 are required")

    lock = load_json(args.lock)
    validate_lock(lock)
    cache = verify_cache(args.lock, args.data_root, args.seal, "full", args.dns_data_root)
    by_id = {entry["id"]: entry for entry in cache["datasets"]}
    slr_archive = Path(by_id["openslr-slr28"]["path"])
    dns_entry = by_id["microsoft-dns-challenge"]
    dns_root = Path(dns_entry["data_root"])
    dns_repo = args.data_root / "DNS-Challenge"
    checksum_index = load_dns_checksum_index(Path(dns_entry["checksum_index"]))

    aec_root = args.data_root / "AEC-Challenge"
    all_pairs = pair_aec(aec_root)
    selected = balanced_aec_pairs(all_pairs, args.aec_limit)
    if len(selected) < args.aec_limit:
        raise ValueError(f"requested {args.aec_limit} AEC cases but only {len(selected)} balanced cases are available")
    clean_candidates = prepare_clean_candidates(all_pairs)

    args.output.mkdir(parents=True, exist_ok=True)
    cases: list[dict] = []
    add_aec_cases(args.output, selected, cases)
    add_derived_cases(args.output, clean_candidates, slr_archive, args.derived_limit, cases)
    add_dns_derived_cases(args.output, dns_repo, dns_root, checksum_index, args.dns_limit, cases)
    expected = args.aec_limit + 2 * args.derived_limit + args.dns_limit
    if len(cases) != expected:
        raise ValueError(f"full public corpus expected {expected} cases, built {len(cases)}")

    corpus = {
        "schema_version": 1,
        "corpus_id": "public-validation-full-v2",
        "tier": "validation-grade",
        "generator": {"name": "build_full_public_corpus.py", "version": 1},
        "sources": ["microsoft-aec-challenge", "microsoft-dns-challenge", "openslr-slr28"],
        "sealed_data": True,
        "dataset_lock_sha256": sha256_file(args.lock),
        "local_seal_sha256": sha256_file(args.seal),
        "cases": cases,
    }
    path = args.output / "corpus.json"
    path.write_text(json.dumps(corpus, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "corpus": str(path), "cases": len(cases), "aec": args.aec_limit,
        "aec_slr_ns": args.derived_limit, "aec_slr_bf": args.derived_limit,
        "dns_derived_ns": args.dns_limit,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
