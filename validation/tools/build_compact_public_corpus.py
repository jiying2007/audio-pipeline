#!/usr/bin/env python3
"""Build a lower-footprint validation-grade corpus from AEC Challenge + SLR28.

This profile is intended for frequent public-data validation on a self-hosted
runner without requiring the roughly 1 TB unpacked DNS5 training corpus. It
combines real AEC Challenge captures with sealed SLR28 RIR/noise-derived NS and
2-mic robot scenarios. It remains validation-grade, never product-certified.
"""

from __future__ import annotations

import argparse
import json
import tempfile
import zipfile
from pathlib import Path

from build_public_corpus import (
    clamp16,
    convolve_short,
    frame_labels,
    interleave,
    pair_aec,
    read_wav,
    read_wav_bytes,
    resample_linear,
    select_zip_members,
    write_pcm,
)
from dataset_lock import load_json, sha256_file, validate_lock
from prepare_public_validation import verify as verify_cache

RATE = 16000


def balanced_aec_pairs(pairs: list[tuple[str, Path, Path]], limit: int) -> list[tuple[str, Path, Path]]:
    order = ("farend-singletalk", "doubletalk", "nearend-singletalk")
    buckets = {name: [item for item in pairs if item[0] == name] for name in order}
    selected: list[tuple[str, Path, Path]] = []
    index = 0
    while len(selected) < max(0, limit):
        progressed = False
        for name in order:
            if index < len(buckets[name]) and len(selected) < limit:
                selected.append(buckets[name][index])
                progressed = True
        if not progressed:
            break
        index += 1
    return selected


def prepare_clean_candidates(pairs: list[tuple[str, Path, Path]], limit: int = 12) -> list[tuple[list[int], dict]]:
    prepared: list[tuple[list[int], dict]] = []
    for scenario, mic, _render in pairs:
        if scenario != "nearend-singletalk":
            continue
        samples, rate, _ = read_wav(mic)
        clean = resample_linear(samples, rate, RATE)
        clean = clean[:min(len(clean), RATE * 8)]
        if len(clean) < RATE * 2:
            continue
        source_id = mic.stem[:-4]
        prepared.append((clean, {
            "dataset_id": "microsoft-aec-challenge",
            "source_id": source_id,
            "mic_sha256": sha256_file(mic),
            "scenario": scenario,
        }))
        if len(prepared) >= limit:
            break
    return prepared


def add_aec_cases(output: Path, pairs: list[tuple[str, Path, Path]], cases: list[dict]) -> None:
    for scenario, mic, render in pairs:
        rate, channels = read_wav(mic)[1:]
        render_rate, render_channels = read_wav(render)[1:]
        if channels != 1 or render_channels != 1 or rate != render_rate:
            continue
        source_id = mic.stem[:-4]
        cases.append({
            "case_id": "aec-compact-" + sha256_file(mic)[:16],
            "split": "validation",
            "scenario": "aec-" + scenario,
            "sample_rate_hz": rate,
            "mic_channels": 1,
            "mic_audio": str(mic.resolve()),
            "render_audio": str(render.resolve()),
            "clean_near_audio": None,
            "echo_audio": None,
            "vad_labels": None,
            "control": {},
            "expected": {},
            "source": {
                "dataset_id": "microsoft-aec-challenge",
                "source_id": source_id,
                "mic_sha256": sha256_file(mic),
                "render_sha256": sha256_file(render),
            },
        })


def add_derived_cases(output: Path, clean_candidates: list[tuple[list[int], dict]],
                      archive: Path, count: int, cases: list[dict]) -> None:
    if not clean_candidates:
        raise ValueError("compact public corpus needs materialized AEC nearend-singletalk clean candidates")
    rir_names, noise_names = select_zip_members(archive)
    if len(rir_names) < 2 or len(noise_names) < 2:
        raise ValueError("compact public corpus requires at least two SLR28 RIRs and two noises")
    archive_sha = sha256_file(archive)
    with zipfile.ZipFile(archive) as zf:
        for index in range(count):
            clean, clean_source = clean_candidates[index % len(clean_candidates)]
            rir_name = rir_names[index % len(rir_names)]
            noise_name = noise_names[(index * 5 + index // max(1, len(rir_names))) % len(noise_names)]
            rir, rir_rate, _ = read_wav_bytes(zf.read(rir_name))
            noise, noise_rate, _ = read_wav_bytes(zf.read(noise_name))
            rir = resample_linear(rir, rir_rate, RATE)
            noise = resample_linear(noise, noise_rate, RATE)
            target = convolve_short(clean, rir)
            if not target or not noise:
                continue
            repeated_noise = [noise[i % len(noise)] for i in range(len(target))]
            peak_target = max(1, max(abs(x) for x in target))
            peak_noise = max(1, max(abs(x) for x in repeated_noise))
            noise_gain = [0.16, 0.24, 0.35, 0.50, 0.70][index % 5] * peak_target / peak_noise
            noisy = [clamp16(target[i] + noise_gain * repeated_noise[i]) for i in range(len(target))]
            labels = frame_labels(target, RATE)
            provenance = {
                "dataset_id": "microsoft-aec-challenge+openslr-slr28",
                "source_id": f"compact-derived-{index:03d}",
                "clean": clean_source,
                "rir_member": rir_name,
                "noise_member": noise_name,
                "slr28_archive_sha256": archive_sha,
            }

            ns_id = f"compact-ns-{index:03d}"
            ns_dir = output / "cases" / ns_id
            ns_dir.mkdir(parents=True, exist_ok=True)
            write_pcm(ns_dir / "mic.pcm", noisy)
            write_pcm(ns_dir / "clean.pcm", target)
            (ns_dir / "vad.labels").write_text("".join(f"{value}\n" for value in labels), encoding="utf-8")
            cases.append({
                "case_id": ns_id,
                "split": "validation",
                "scenario": "ns-public-derived",
                "sample_rate_hz": RATE,
                "mic_channels": 1,
                "mic_audio": str((ns_dir / "mic.pcm").relative_to(output)),
                "render_audio": None,
                "clean_near_audio": str((ns_dir / "clean.pcm").relative_to(output)),
                "echo_audio": None,
                "vad_labels": str((ns_dir / "vad.labels").relative_to(output)),
                "control": {},
                "processor_profile": "ns-isolated",
                "expected": {},
                "source": provenance,
            })

            delay = 1 + index % 5
            delayed = [0] * delay + target[:-delay]
            decorrelation = 131 + (index * 173) % max(1, len(repeated_noise))
            right = [clamp16(delayed[i] + noise_gain * repeated_noise[(i + decorrelation) % len(repeated_noise)])
                     for i in range(len(target))]
            bf_id = f"compact-bf-{index:03d}"
            bf_dir = output / "cases" / bf_id
            bf_dir.mkdir(parents=True, exist_ok=True)
            write_pcm(bf_dir / "mic.pcm", interleave(noisy, right))
            write_pcm(bf_dir / "clean.pcm", target)
            (bf_dir / "vad.labels").write_text("".join(f"{value}\n" for value in labels), encoding="utf-8")
            cases.append({
                "case_id": bf_id,
                "split": "validation",
                "scenario": "bf-offaxis",
                "sample_rate_hz": RATE,
                "mic_channels": 2,
                "mic_audio": str((bf_dir / "mic.pcm").relative_to(output)),
                "render_audio": None,
                "clean_near_audio": str((bf_dir / "clean.pcm").relative_to(output)),
                "echo_audio": None,
                "vad_labels": str((bf_dir / "vad.labels").relative_to(output)),
                "control": {},
                "expected": {},
                "source": provenance,
            })


def self_test() -> None:
    fake: list[tuple[str, Path, Path]] = []
    for scenario in ("farend-singletalk", "doubletalk", "nearend-singletalk"):
        for index in range(3):
            fake.append((scenario, Path(f"{scenario}-{index}-mic.wav"), Path(f"{scenario}-{index}-lpb.wav")))
    selected = balanced_aec_pairs(fake, 6)
    counts = {name: sum(1 for item in selected if item[0] == name)
              for name in ("farend-singletalk", "doubletalk", "nearend-singletalk")}
    assert counts == {"farend-singletalk": 2, "doubletalk": 2, "nearend-singletalk": 2}
    with tempfile.TemporaryDirectory() as tmp:
        archive = Path(tmp) / "slr.zip"
        with zipfile.ZipFile(archive, "w") as zf:
            zf.writestr("x/rir-a.wav", b"")
            zf.writestr("x/rir-b.wav", b"")
            zf.writestr("x/noise-a.wav", b"")
            zf.writestr("x/noise-b.wav", b"")
        rirs, noises = select_zip_members(archive)
        assert len(rirs) == 2 and len(noises) == 2
    print("compact public corpus self-test: OK")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--lock", type=Path, default=Path("validation/datasets.lock.json"))
    parser.add_argument("--seal", type=Path)
    parser.add_argument("--data-root", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--aec-limit", type=int, default=60)
    parser.add_argument("--derived-limit", type=int, default=20,
                        help="number of public-derived acoustic combinations; each emits NS + BF cases")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    if args.seal is None or args.data_root is None or args.output is None:
        parser.error("--seal, --data-root and --output are required unless --self-test is used")
    if args.aec_limit < 3 or args.derived_limit < 4:
        parser.error("aec-limit must be >=3 and derived-limit must be >=4")

    lock = load_json(args.lock)
    validate_lock(lock)
    cache = verify_cache(args.lock, args.data_root, args.seal, "compact")
    slr_entry = next(item for item in cache["datasets"] if item["id"] == "openslr-slr28")
    slr_archive = Path(slr_entry["path"])
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
    expected_cases = args.aec_limit + 2 * args.derived_limit
    if len(cases) != expected_cases:
        raise ValueError(f"compact public corpus expected {expected_cases} cases, built {len(cases)}")

    corpus = {
        "schema_version": 1,
        "corpus_id": "public-validation-compact-v1",
        "tier": "validation-grade",
        "generator": {"name": "build_compact_public_corpus.py", "version": 1},
        "sources": ["microsoft-aec-challenge", "openslr-slr28"],
        "sealed_data": True,
        "dataset_lock_sha256": sha256_file(args.lock),
        "local_seal_sha256": sha256_file(args.seal),
        "cases": cases,
    }
    path = args.output / "corpus.json"
    path.write_text(json.dumps(corpus, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "corpus": str(path), "cases": len(cases), "aec": args.aec_limit,
        "ns_public_derived": args.derived_limit, "bf_public_derived": args.derived_limit,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
