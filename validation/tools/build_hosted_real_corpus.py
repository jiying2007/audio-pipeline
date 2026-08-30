#!/usr/bin/env python3
"""Build a tiny hosted real-audio corpus from SHA-pinned Microsoft P.808 clips."""

from __future__ import annotations

import argparse
import array
import hashlib
import io
import json
import os
import re
import time
import urllib.request
import wave
from pathlib import Path
from urllib.parse import quote

SCHEMA_VERSION = 1
SOURCE_REPOSITORY = "microsoft/P.808"
LICENSE = "CC-BY-4.0"
USAGE_CLASS = "commercial-validation"
MAX_DOWNLOAD_BYTES = 2 * 1024 * 1024
ALLOWED_PREFIXES = (
    "src/P808Template/assets/clips/math/",
    "src/P808Template/assets/clips/environment_test/",
)
SUPPORTED_RATES = {8000, 16000, 24000, 32000, 48000}


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def git_blob_sha1(data: bytes) -> str:
    return hashlib.sha1(f"blob {len(data)}\0".encode("ascii") + data).hexdigest()


def safe_path(value: str) -> bool:
    path = Path(value)
    return bool(value) and not path.is_absolute() and ".." not in path.parts


def validate_lock(lock: dict) -> None:
    if lock.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("hosted-real lock schema_version must be 1")
    if lock.get("source_repository") != SOURCE_REPOSITORY:
        raise ValueError("hosted-real source_repository must be microsoft/P.808")
    revision = str(lock.get("source_revision", ""))
    if re.fullmatch(r"[0-9a-f]{40}", revision) is None:
        raise ValueError("hosted-real source_revision must be exact lowercase 40-hex")
    if lock.get("license") != LICENSE or lock.get("usage_class") != USAGE_CLASS:
        raise ValueError("hosted-real lock must remain CC-BY-4.0 commercial-validation")
    clips = lock.get("clips")
    if not isinstance(clips, list) or len(clips) < 4:
        raise ValueError("hosted-real lock requires at least four clips")
    ids: set[str] = set()
    scenarios: set[str] = set()
    for clip in clips:
        clip_id = str(clip.get("id", ""))
        path = str(clip.get("path", ""))
        if not clip_id or clip_id in ids:
            raise ValueError(f"invalid/duplicate hosted-real clip id: {clip_id!r}")
        ids.add(clip_id)
        if not safe_path(path) or not path.startswith(ALLOWED_PREFIXES):
            raise ValueError(f"unsupported hosted-real path: {path}")
        digest = str(clip.get("sha256", ""))
        blob = str(clip.get("git_blob_sha1", ""))
        if re.fullmatch(r"[0-9a-f]{64}", digest) is None:
            raise ValueError(f"invalid SHA-256: {clip_id}")
        if re.fullmatch(r"[0-9a-f]{40}", blob) is None:
            raise ValueError(f"invalid Git blob SHA-1: {clip_id}")
        channels = int(clip.get("channels", 0))
        rate = int(clip.get("sample_rate_hz", 0))
        width = int(clip.get("sample_width_bytes", 0))
        scenario = str(clip.get("scenario", ""))
        if channels not in (1, 2) or rate not in SUPPORTED_RATES or width != 2 or not scenario:
            raise ValueError(f"invalid WAV geometry/scenario: {clip_id}")
        scenarios.add(scenario)
    if scenarios != {"p808-created-speech", "p808-degraded-speech"}:
        raise ValueError(f"hosted-real scenarios drifted: {sorted(scenarios)}")


def load_lock(path: Path) -> dict:
    lock = json.loads(path.read_text(encoding="utf-8"))
    validate_lock(lock)
    return lock


def download_clip(repository: str, revision: str, path: str) -> bytes:
    url = f"https://raw.githubusercontent.com/{repository}/{revision}/{quote(path, safe='/')}"
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            request = urllib.request.Request(url, headers={"User-Agent": "audio-pipeline-hosted-real/1"})
            with urllib.request.urlopen(request, timeout=30) as response:
                data = response.read(MAX_DOWNLOAD_BYTES + 1)
            if not data or len(data) > MAX_DOWNLOAD_BYTES:
                raise ValueError(f"unexpected hosted-real download size: {path} bytes={len(data)}")
            return data
        except Exception as exc:  # pragma: no cover - network path
            last_error = exc
            if attempt < 2:
                time.sleep(attempt + 1)
    raise RuntimeError(f"failed to download pinned hosted-real clip: {path}: {last_error}")


def wav_to_mono_pcm(data: bytes, clip: dict) -> tuple[bytes, int]:
    with wave.open(io.BytesIO(data), "rb") as handle:
        channels = handle.getnchannels()
        rate = handle.getframerate()
        width = handle.getsampwidth()
        compression = handle.getcomptype()
        frames = handle.getnframes()
        if channels != int(clip["channels"]) or rate != int(clip["sample_rate_hz"]):
            raise ValueError(f"WAV geometry mismatch: {clip['id']}")
        if width != int(clip["sample_width_bytes"]) or width != 2 or compression != "NONE":
            raise ValueError(f"hosted-real WAV must be uncompressed PCM16: {clip['id']}")
        raw = handle.readframes(frames)
    values = array.array("h")
    values.frombytes(raw)
    if os.sys.byteorder != "little":
        values.byteswap()
    if channels == 2:
        if len(values) % 2:
            raise ValueError(f"odd stereo sample count: {clip['id']}")
        mono = array.array("h", [int((int(values[i]) + int(values[i + 1])) / 2) for i in range(0, len(values), 2)])
    else:
        mono = values
    if os.sys.byteorder != "little":
        mono.byteswap()
    return mono.tobytes(), frames


def build(lock_path: Path, output: Path) -> dict:
    lock = load_lock(lock_path)
    output.mkdir(parents=True, exist_ok=True)
    case_root = output / "cases"
    case_root.mkdir(exist_ok=True)
    manifest_files = []
    cases = []
    for clip in lock["clips"]:
        data = download_clip(lock["source_repository"], lock["source_revision"], clip["path"])
        actual_sha = sha256_bytes(data)
        actual_blob = git_blob_sha1(data)
        if actual_sha != clip["sha256"]:
            raise ValueError(f"hosted-real SHA-256 mismatch: {clip['id']}")
        if actual_blob != clip["git_blob_sha1"]:
            raise ValueError(f"hosted-real Git blob mismatch: {clip['id']}")
        pcm, source_frames = wav_to_mono_pcm(data, clip)
        pcm_path = case_root / f"{clip['id']}.pcm"
        pcm_path.write_bytes(pcm)
        materialized_sha = sha256_bytes(pcm)
        transform = "stereo-downmix" if int(clip["channels"]) == 2 else "identity-pcm"
        manifest_files.append({
            "id": clip["id"],
            "path": clip["path"],
            "sha256": actual_sha,
            "git_blob_sha1": actual_blob,
            "source_channels": int(clip["channels"]),
            "sample_rate_hz": int(clip["sample_rate_hz"]),
            "source_frames": source_frames,
            "materialized_pcm_sha256": materialized_sha,
            "transform": transform,
        })
        cases.append({
            "case_id": clip["id"],
            "split": "validation",
            "scenario": clip["scenario"],
            "sample_rate_hz": int(clip["sample_rate_hz"]),
            "mic_channels": 1,
            "mic_audio": str(pcm_path.relative_to(output)),
            "render_audio": None,
            "clean_near_audio": None,
            "echo_audio": None,
            "vad_labels": None,
            "processor_profile": "default",
            "control": {},
            "expected": {
                "min_output_rms_delta_db": -35.0,
                "max_output_rms_delta_db": 20.0,
                "max_output_clip_fraction": 0.02,
                "max_output_dc_offset_dbfs": -20.0
            },
            "dimensions": {
                "source_rate_hz": int(clip["sample_rate_hz"]),
                "source_channels": int(clip["channels"]),
                "materialization": transform,
            },
            "source": {
                "dataset_id": "microsoft-p808-hosted-real",
                "source_id": clip["path"],
                "usage_class": USAGE_CLASS,
                "license": LICENSE,
                "upstream_revision": lock["source_revision"],
                "upstream_sha256": actual_sha,
                "materialized_pcm_sha256": materialized_sha,
            },
        })
    manifest = {
        "schema_version": 1,
        "source_repository": lock["source_repository"],
        "source_revision": lock["source_revision"],
        "license": lock["license"],
        "usage_class": lock["usage_class"],
        "dataset_lock_sha256": sha256_file(lock_path),
        "files": manifest_files,
    }
    manifest_path = output / "source-manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    corpus = {
        "schema_version": 1,
        "corpus_id": "hosted-real-p808-v1",
        "tier": "validation-grade",
        "generator": {"name": "build_hosted_real_corpus.py", "version": 1},
        "sources": ["microsoft-p808-hosted-real"],
        "sealed_data": True,
        "dataset_lock_sha256": sha256_file(lock_path),
        "source_manifest_sha256": sha256_file(manifest_path),
        "cases": cases,
    }
    corpus_path = output / "corpus.json"
    corpus_path.write_text(json.dumps(corpus, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    attribution = (
        "# Hosted real-audio attribution\n\n"
        "- Source: Microsoft P.808 Toolkit\n"
        f"- Repository: https://github.com/{SOURCE_REPOSITORY}\n"
        f"- Revision: `{lock['source_revision']}`\n"
        f"- License: `{LICENSE}` for the selected clips\n"
        f"- License evidence: {lock['license_evidence']}\n"
        "- Materialization: stereo source clips are averaged to mono PCM16; mono clips are copied as PCM16.\n"
    )
    (output / "DATASET_ATTRIBUTION.md").write_text(attribution, encoding="utf-8")
    result = {
        "corpus": str(corpus_path),
        "source_manifest": str(manifest_path),
        "cases": len(cases),
        "source_revision": lock["source_revision"],
        "rates": sorted({int(item["sample_rate_hz"]) for item in lock["clips"]}),
    }
    print(json.dumps(result, sort_keys=True))
    return result


def self_test() -> None:
    payload = b"abc"
    assert sha256_bytes(payload) == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
    assert git_blob_sha1(payload) == "f2ba8f84ab5c1bce84a7b441cb1959cfc7093b7f"
    good = {
        "schema_version": 1,
        "source_repository": SOURCE_REPOSITORY,
        "source_revision": "0" * 40,
        "license": LICENSE,
        "usage_class": USAGE_CLASS,
        "clips": [
            {"id": f"x{i}", "path": f"src/P808Template/assets/clips/math/x{i}.wav", "sha256": "0" * 64,
             "git_blob_sha1": "0" * 40, "channels": 1 if i < 2 else 2,
             "sample_rate_hz": 16000 if i < 2 else 48000, "sample_width_bytes": 2,
             "scenario": "p808-created-speech" if i % 2 == 0 else "p808-degraded-speech"}
            for i in range(4)
        ],
    }
    validate_lock(good)
    bad = json.loads(json.dumps(good))
    bad["license"] = "CC-BY-NC-4.0"
    try:
        validate_lock(bad)
    except ValueError:
        pass
    else:
        raise AssertionError("non-commercial hosted-real lock was accepted")
    print("hosted real corpus builder self-test: OK")


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("self-test")
    validate = sub.add_parser("validate")
    validate.add_argument("--lock", type=Path, default=Path("validation/hosted_real.datasets.lock.json"))
    build_parser = sub.add_parser("build")
    build_parser.add_argument("--lock", type=Path, default=Path("validation/hosted_real.datasets.lock.json"))
    build_parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "self-test":
        self_test()
        return 0
    if args.command == "validate":
        lock = load_lock(args.lock)
        print(json.dumps({"catalog_id": lock["catalog_id"], "clips": len(lock["clips"]), "source_revision": lock["source_revision"]}, sort_keys=True))
        return 0
    build(args.lock, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
