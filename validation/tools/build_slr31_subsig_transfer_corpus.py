#!/usr/bin/env python3
"""Build candidate-zero S003 stage-prefix cases from public SLR31 clean speech."""

from __future__ import annotations

import argparse
import array
import hashlib
import json
import math
import os
import re
from pathlib import Path

from build_validation_corpus import (
    RATE,
    clamp16,
    delayed,
    interleave,
    mix,
    noise,
    nonstationary_noise,
    rotate,
    scale,
    write_pcm,
)

TARGET_SECONDS = 6
TARGET_SAMPLES = RATE * TARGET_SECONDS
TARGET_RMS = 3500.0
MICROSET_SIZE = 8
SELECT_SALT = "s003-slr31-v1:"
FLAC_RE = re.compile(r"^(?P<speaker>[0-9]+)-(?P<chapter>[0-9]+)-(?P<utterance>[0-9]+)[.]flac$")
STAGE_INDEX = {
    "prefix-capture": 0,
    "prefix-bf": 1,
    "prefix-ns": 5,
    "prefix-agc": 6,
    "default": 8,
}
PROFILES = {
    "capture-clipping": ["prefix-capture", "prefix-ns", "prefix-agc", "default"],
    "mic-gain-delay-mismatch": [
        "prefix-capture", "prefix-bf", "prefix-ns", "prefix-agc", "default"
    ],
}


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def stable_key(relative: str) -> str:
    return hashlib.sha256((SELECT_SALT + relative).encode("utf-8")).hexdigest()


def select_microset(root: Path) -> list[Path]:
    candidates: list[tuple[str, str, Path]] = []
    for path in root.rglob("*.flac"):
        match = FLAC_RE.fullmatch(path.name)
        if not match:
            continue
        relative = path.relative_to(root).as_posix()
        candidates.append((stable_key(relative), match.group("speaker"), path))
    if not candidates:
        raise ValueError("no LibriSpeech FLAC files found")
    selected: list[Path] = []
    speakers: set[str] = set()
    for _key, speaker, path in sorted(candidates):
        if speaker in speakers:
            continue
        selected.append(path)
        speakers.add(speaker)
        if len(selected) == MICROSET_SIZE:
            break
    if len(selected) != MICROSET_SIZE or len(speakers) != MICROSET_SIZE:
        raise ValueError(
            f"need {MICROSET_SIZE} unique speakers, got files={len(selected)} speakers={len(speakers)}"
        )
    return selected


def decode_flac(path: Path) -> list[int]:
    import soundfile as sf

    values, rate = sf.read(str(path), dtype="int16", always_2d=True)
    if int(rate) != RATE:
        raise ValueError(f"SLR31 source rate must be {RATE} Hz: {path} rate={rate}")
    if values.ndim != 2 or values.shape[1] != 1:
        raise ValueError(f"SLR31 source must be mono: {path} shape={values.shape}")
    out = [int(value) for value in values[:, 0]]
    if not out:
        raise ValueError(f"empty decoded audio: {path}")
    return out


def materialize_length(samples: list[int]) -> list[int]:
    if not samples:
        raise ValueError("cannot materialize empty signal")
    repeats = (TARGET_SAMPLES + len(samples) - 1) // len(samples)
    return (samples * repeats)[:TARGET_SAMPLES]


def rms(samples: list[int]) -> float:
    return math.sqrt(sum(float(x) * x for x in samples) / max(1, len(samples)))


def normalize(samples: list[int]) -> tuple[list[int], float]:
    current = rms(samples)
    if current <= 1.0:
        raise ValueError("public clean speech is effectively silent")
    peak = max(abs(x) for x in samples)
    gain = TARGET_RMS / current
    if peak > 0:
        gain = min(gain, (0.95 * 32767.0) / peak)
    out = [clamp16(x * gain) for x in samples]
    if max(abs(x) for x in out) >= 32767:
        raise ValueError("normalization clipped public clean speech")
    return out, gain


def hard_clip(samples: list[int], limit: int) -> list[int]:
    return [max(-limit, min(limit, int(x))) for x in samples]


def source_record(path: Path, root: Path) -> dict:
    match = FLAC_RE.fullmatch(path.name)
    if match is None:
        raise ValueError(f"unexpected selected FLAC name: {path.name}")
    return {
        "dataset_id": "openslr-slr31",
        "relative_path": path.relative_to(root).as_posix(),
        "speaker_id": match.group("speaker"),
        "chapter_id": match.group("chapter"),
        "utterance_id": match.group("utterance"),
        "sha256": sha256_file(path),
    }


def write_case(
    cases: list[dict],
    output: Path,
    *,
    case_id: str,
    scenario: str,
    mic: list[int],
    channels: int,
    clean: list[int],
    profile: str,
    dimensions: dict,
    source: dict,
) -> None:
    root = output / "cases" / case_id
    root.mkdir(parents=True, exist_ok=True)
    write_pcm(root / "mic.pcm", mic)
    write_pcm(root / "clean.pcm", clean)
    cases.append({
        "case_id": case_id,
        "split": "dev",
        "scenario": scenario,
        "sample_rate_hz": RATE,
        "mic_channels": channels,
        "mic_audio": str((root / "mic.pcm").relative_to(output)),
        "render_audio": None,
        "clean_near_audio": str((root / "clean.pcm").relative_to(output)),
        "echo_audio": None,
        "vad_labels": None,
        "control": {},
        "processor_profile": profile,
        "expected": {},
        "dimensions": dimensions,
        "source": source,
    })


def build(
    source_root: Path,
    archive_sha256: str,
    output: Path,
    seed: int,
) -> dict:
    selected = select_microset(source_root)
    output.mkdir(parents=True, exist_ok=True)
    cases: list[dict] = []
    selected_manifest: list[dict] = []

    for index, path in enumerate(selected):
        record = source_record(path, source_root)
        decoded = materialize_length(decode_flac(path))
        clean, normalization_gain = normalize(decoded)
        item_id = f"u{index:02d}"
        selected_manifest.append({
            **record,
            "microset_id": item_id,
            "selection_key": stable_key(record["relative_path"]),
            "decoded_samples": TARGET_SAMPLES,
            "normalization_gain": normalization_gain,
            "materialized_pcm_sha256": hashlib.sha256(
                array.array("h", clean).tobytes()
            ).hexdigest(),
        })

        clip_noise = nonstationary_noise(TARGET_SAMPLES, seed * 101 + index, 6000.0)
        clipped = hard_clip(mix(clean, scale(clip_noise, 0.35)), 7000)
        for profile in PROFILES["capture-clipping"]:
            base = f"capture-clipping-{item_id}"
            write_case(
                cases,
                output,
                case_id=f"{base}--{profile}",
                scenario="s003-slr31-capture-clipping",
                mic=clipped,
                channels=1,
                clean=clean,
                profile=profile,
                dimensions={
                    "base_case_id": base,
                    "failure_kind": "capture-clipping",
                    "durable_failure_id": "FR-S003-CAPTURE-CLIPPING-V1",
                    "utterance_id": item_id,
                    "source_family": "openslr-slr31-clean-speech",
                    "stage_profile": profile,
                    "stage_index": STAGE_INDEX[profile],
                    "clip_limit": 7000,
                    "noise_scale": 0.35,
                },
                source={
                    **record,
                    "authority": "research-development-candidate-zero",
                },
            )

        mismatch_noise = noise(TARGET_SAMPLES, seed * 103 + index, 2200.0)
        left = mix(clean, scale(mismatch_noise, 0.25))
        right = mix(
            scale(delayed(clean, 3), 0.72),
            scale(rotate(mismatch_noise, 137), 0.38),
        )
        stereo = interleave(left, right)
        for profile in PROFILES["mic-gain-delay-mismatch"]:
            base = f"mic-gain-delay-mismatch-{item_id}"
            write_case(
                cases,
                output,
                case_id=f"{base}--{profile}",
                scenario="s003-slr31-mic-gain-delay-mismatch",
                mic=stereo,
                channels=2,
                clean=clean,
                profile=profile,
                dimensions={
                    "base_case_id": base,
                    "failure_kind": "mic-gain-delay-mismatch",
                    "durable_failure_id": "FR-S003-MIC-GAIN-DELAY-MISMATCH-V1",
                    "utterance_id": item_id,
                    "source_family": "openslr-slr31-clean-speech",
                    "stage_profile": profile,
                    "stage_index": STAGE_INDEX[profile],
                    "right_gain": 0.72,
                    "right_delay_samples": 3,
                    "left_noise_scale": 0.25,
                    "right_noise_scale": 0.38,
                },
                source={
                    **record,
                    "authority": "research-development-candidate-zero",
                },
            )

    if len(cases) != MICROSET_SIZE * (
        len(PROFILES["capture-clipping"]) + len(PROFILES["mic-gain-delay-mismatch"])
    ):
        raise ValueError(f"unexpected case count: {len(cases)}")

    manifest = {
        "schema_version": 1,
        "dataset_id": "openslr-slr31-clean-speech",
        "archive_id": "openslr-slr31-train-clean-5",
        "archive_sha256": archive_sha256,
        "selection_salt": SELECT_SALT,
        "selection_rule": "stable hash order with one utterance per unique speaker",
        "selected": selected_manifest,
        "decoder": {"python_package": "soundfile==0.13.1", "required_rate_hz": RATE, "required_channels": 1},
        "selection_authority": "research-development-only",
        "candidate_authority": False,
        "shipping_authority": False,
    }
    manifest_path = output / "source-manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    corpus = {
        "schema_version": 1,
        "corpus_id": f"s003-slr31-subsig-transfer-seed-{seed}",
        "tier": "research-validation",
        "generator": {
            "name": "build_slr31_subsig_transfer_corpus.py",
            "version": 1,
            "seed": seed,
        },
        "sources": ["openslr-slr31"],
        "sealed_data": True,
        "source_manifest_sha256": sha256_file(manifest_path),
        "candidate_limit": 0,
        "confirmation_limit": 0,
        "promotion_allowed": False,
        "shipping_change_allowed": False,
        "cases": cases,
    }
    (output / "corpus.json").write_text(
        json.dumps(corpus, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return corpus


def self_test() -> None:
    assert MICROSET_SIZE == 8
    assert stable_key("x.flac") == stable_key("x.flac")
    assert stable_key("x.flac") != stable_key("y.flac")
    assert len(materialize_length([1, 2, 3])) == TARGET_SAMPLES
    clean, gain = normalize([1000, -1000] * (TARGET_SAMPLES // 2))
    assert len(clean) == TARGET_SAMPLES and gain > 0.0
    assert max(abs(x) for x in hard_clip([10000, -10000], 7000)) == 7000
    assert len(PROFILES["capture-clipping"]) == 4
    assert len(PROFILES["mic-gain-delay-mismatch"]) == 5
    print("SLR31 subsignature transfer corpus self-test: OK")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--source-root", type=Path)
    parser.add_argument("--archive-sha256")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--seed", type=int, default=9307)
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    if args.source_root is None or args.output is None or not args.archive_sha256:
        parser.error("--source-root, --archive-sha256 and --output are required")
    corpus = build(args.source_root, args.archive_sha256, args.output, args.seed)
    print(json.dumps({
        "seed": args.seed,
        "cases": len(corpus["cases"]),
        "microset": MICROSET_SIZE,
        "corpus": str(args.output / "corpus.json"),
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
