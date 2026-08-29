#!/usr/bin/env python3
"""Prepare and verify sealed public-data caches for validation-grade runs.

The compact profile avoids the very large DNS5 training corpus. It uses pinned
Microsoft AEC Challenge audio plus sealed OpenSLR SLR28. The full profile adds
caller-materialized official DNS5 clean/noise WAV sources plus the pinned
upstream checksum index. Neither profile is product-certification evidence.
"""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

from dataset_lock import (
    check_not_lfs_pointer,
    load_json,
    seal_asset,
    sha256_file,
    validate_lock,
)
from fetch_public_data import clone_pinned, download

COMPACT_IDS = ("microsoft-aec-challenge", "openslr-slr28")
FULL_IDS = ("microsoft-aec-challenge", "microsoft-dns-challenge", "openslr-slr28")
DNS_INDEX_NAME = "dns5-datasets-files-sha1.csv.bz2"


def items_by_id(lock: dict) -> dict[str, dict]:
    return {item["id"]: item for item in lock["datasets"]}


def profile_ids(profile: str) -> tuple[str, ...]:
    if profile == "compact":
        return COMPACT_IDS
    if profile == "full":
        return FULL_IDS
    raise ValueError(f"unsupported public-validation profile: {profile}")


def git_output(*args: str) -> str:
    return subprocess.check_output(["git", *args], text=True).strip()


def command_version(command: list[str]) -> str | None:
    try:
        return subprocess.check_output(command, text=True, stderr=subprocess.STDOUT).splitlines()[0].strip()
    except (FileNotFoundError, subprocess.CalledProcessError, IndexError):
        return None


def require_aec(lock_items: dict[str, dict], root: Path) -> dict:
    item = lock_items["microsoft-aec-challenge"]
    local = root / item["local_path"]
    if not (local / ".git").exists():
        raise FileNotFoundError(f"missing pinned AEC Challenge checkout: {local}")
    head = git_output("-C", str(local), "rev-parse", "HEAD")
    if head != item["revision"]:
        raise ValueError(f"AEC Challenge revision mismatch: {head} != {item['revision']}")
    materialized = 0
    for required in item.get("required_paths", []):
        directory = local / required
        if not directory.is_dir():
            raise FileNotFoundError(f"missing AEC validation directory: {directory}")
        wavs = sorted(directory.rglob("*.wav"))
        if not wavs:
            raise ValueError(f"no WAV files under AEC validation directory: {directory}")
        for wav in wavs[:16]:
            check_not_lfs_pointer(wav)
        materialized += len(wavs)
    return {"id": item["id"], "revision": head, "materialized_wavs": materialized}


def resolve_sealed_asset(seal: dict, dataset_id: str, key: str, root: Path) -> Path:
    entry = seal.get("datasets", {}).get(dataset_id, {})
    raw = entry.get(key)
    if not raw:
        raise ValueError(f"local seal missing {dataset_id}.{key}")
    path = Path(raw)
    return path if path.is_absolute() else root / path


def require_slr28(lock_items: dict[str, dict], root: Path, seal: dict) -> dict:
    item = lock_items["openslr-slr28"]
    archive = resolve_sealed_asset(seal, item["id"], "path", root)
    expected = seal["datasets"][item["id"]].get("sha256")
    if not expected:
        raise ValueError("SLR28 local seal is missing sha256")
    if not archive.is_file():
        raise FileNotFoundError(archive)
    actual = sha256_file(archive)
    if actual != expected:
        raise ValueError("SLR28 archive SHA-256 does not match local seal")
    return {"id": item["id"], "path": str(archive), "sha256": actual}


def dns_role_counts(data: Path) -> tuple[int, int, int]:
    clean = 0
    noise = 0
    total = 0
    for path in data.rglob("*.wav"):
        total += 1
        rel = path.relative_to(data).as_posix().lower()
        if "noisy" in rel:
            continue
        if "clean" in rel:
            clean += 1
        elif "noise" in rel:
            noise += 1
    return clean, noise, total


def require_dns(lock_items: dict[str, dict], root: Path, seal: dict,
                dns_data_root: Path | None) -> dict:
    item = lock_items["microsoft-dns-challenge"]
    repo = root / item["local_path"]
    if not (repo / ".git").exists():
        raise FileNotFoundError(f"missing pinned DNS Challenge checkout: {repo}")
    head = git_output("-C", str(repo), "rev-parse", "HEAD")
    if head != item["revision"]:
        raise ValueError(f"DNS Challenge revision mismatch: {head} != {item['revision']}")
    index = resolve_sealed_asset(seal, item["id"], "checksum_index_path", root)
    expected = seal["datasets"][item["id"]].get("checksum_index_sha256")
    if not expected or not index.is_file() or sha256_file(index) != expected:
        raise ValueError("DNS checksum index is missing or does not match its local seal")
    data = dns_data_root or (repo / "datasets_fullband")
    if not data.is_dir():
        raise FileNotFoundError(
            f"DNS full profile requires caller-materialized official DNS5 WAV sources: {data}. "
            "Use the pinned upstream download-dns-challenge-5-* scripts; audio-pipeline does not "
            "silently download the large upstream corpus."
        )
    clean_count, noise_count, wav_count = dns_role_counts(data)
    if clean_count < 2 or noise_count < 2:
        raise ValueError(
            f"DNS data root must contain official clean and noise WAV sources; "
            f"clean={clean_count} noise={noise_count} total={wav_count} under {data}"
        )
    return {
        "id": item["id"], "revision": head, "checksum_index": str(index),
        "checksum_index_sha256": expected, "data_root": str(data),
        "wav_count": wav_count, "clean_wavs": clean_count, "noise_wavs": noise_count,
    }


def verify(lock_path: Path, root: Path, seal_path: Path, profile: str,
           dns_data_root: Path | None = None) -> dict:
    lock = load_json(lock_path)
    validate_lock(lock)
    if not seal_path.is_file():
        raise FileNotFoundError(seal_path)
    seal = load_json(seal_path)
    lock_sha = sha256_file(lock_path)
    if seal.get("lock_sha256") != lock_sha:
        raise ValueError("local public-data seal does not bind the current datasets.lock.json")
    lock_items = items_by_id(lock)
    evidence = [require_aec(lock_items, root), require_slr28(lock_items, root, seal)]
    if profile == "full":
        evidence.insert(1, require_dns(lock_items, root, seal, dns_data_root))
    elif profile != "compact":
        raise ValueError(f"unsupported public-validation profile: {profile}")
    return {
        "schema_version": 1,
        "profile": profile,
        "lock_id": lock["lock_id"],
        "lock_sha256": lock_sha,
        "seal_sha256": sha256_file(seal_path),
        "datasets": evidence,
    }


def prepare(lock_path: Path, root: Path, seal_path: Path, profile: str,
            allow_large_downloads: bool, dns_data_root: Path | None) -> dict:
    lock = load_json(lock_path)
    validate_lock(lock)
    items = items_by_id(lock)
    root.mkdir(parents=True, exist_ok=True)

    aec = items["microsoft-aec-challenge"]
    clone_pinned(aec, root, materialize=True)

    slr = items["openslr-slr28"]
    slr_path = root / slr["local_path"]
    if not slr_path.exists():
        if not allow_large_downloads:
            raise RuntimeError("SLR28 materialization requires --allow-large-downloads")
        download(slr["source"], slr_path)
    seal_asset(lock_path, seal_path, slr["id"], slr_path, checksum_index=False)

    if profile == "full":
        dns = items["microsoft-dns-challenge"]
        clone_pinned(dns, root, materialize=False)
        index_url = dns.get("integrity", {}).get("index_url")
        if not index_url:
            raise ValueError("DNS lock entry is missing its upstream checksum-index URL")
        index_path = root / DNS_INDEX_NAME
        if not index_path.exists():
            download(index_url, index_path)
        seal_asset(lock_path, seal_path, dns["id"], index_path, checksum_index=True)
    elif profile != "compact":
        raise ValueError(f"unsupported public-validation profile: {profile}")

    report = verify(lock_path, root, seal_path, profile, dns_data_root)
    report["tools"] = {
        "python": command_version(["python3", "--version"]),
        "git": command_version(["git", "--version"]),
        "git_lfs": command_version(["git", "lfs", "version"]),
    }
    manifest = root / f"public-validation-{profile}-runner-manifest.json"
    manifest.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    report["runner_manifest"] = str(manifest)
    return report


def self_test() -> None:
    assert profile_ids("compact") == COMPACT_IDS
    assert profile_ids("full") == FULL_IDS
    try:
        profile_ids("invalid")
    except ValueError:
        pass
    else:
        raise AssertionError("invalid profile accepted")
    assert "microsoft-dns-challenge" not in profile_ids("compact")
    assert "microsoft-dns-challenge" in profile_ids("full")
    print("public validation preparation self-test: OK")


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)

    for name in ("prepare", "verify"):
        cmd = sub.add_parser(name)
        cmd.add_argument("--lock", type=Path, default=Path("validation/datasets.lock.json"))
        cmd.add_argument("--root", type=Path, required=True)
        cmd.add_argument("--seal", type=Path, required=True)
        cmd.add_argument("--profile", choices=("compact", "full"), default="compact")
        cmd.add_argument("--dns-data-root", type=Path)
        if name == "prepare":
            cmd.add_argument("--allow-large-downloads", action="store_true")
    sub.add_parser("self-test")
    args = parser.parse_args()

    if args.command == "self-test":
        self_test()
        return 0
    if args.command == "verify":
        report = verify(args.lock, args.root, args.seal, args.profile, args.dns_data_root)
    else:
        report = prepare(args.lock, args.root, args.seal, args.profile,
                         args.allow_large_downloads, args.dns_data_root)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
