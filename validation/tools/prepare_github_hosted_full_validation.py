#!/usr/bin/env python3
"""Bootstrap validation-grade public data on an ephemeral GitHub-hosted runner.

The frozen candidate source still owns the canonical dataset lock and corpus
builder. This helper only materializes a reproducible cache for that source:
AEC is bound by its pinned git/LFS revision, SLR28 by a committed SHA-256, and
a minimal official DNS5 clean/noise archive pair by committed SHA-256 values.
A derived local SHA1 index is generated from those already SHA-256-bound DNS
archives so the frozen source can reuse its existing per-WAV verification path.
"""

from __future__ import annotations

import argparse
import bz2
import csv
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

SCHEMA_VERSION = 1


def digest_file(path: Path, algorithm: str = "sha256") -> str:
    digest = hashlib.new(algorithm)
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def run(command: list[str], *, cwd: Path | None = None, capture: bool = False) -> str:
    result = subprocess.run(
        command,
        cwd=str(cwd) if cwd else None,
        check=True,
        text=True,
        stdout=subprocess.PIPE if capture else None,
    )
    return result.stdout if capture else ""


def validate_archive_lock(lock: dict) -> None:
    if lock.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("hosted archive lock schema_version must be 1")
    if not lock.get("lock_id"):
        raise ValueError("hosted archive lock_id is required")
    if len(lock.get("dns_revision", "")) != 40:
        raise ValueError("hosted archive lock must pin dns_revision")
    archives = lock.get("archives")
    if not isinstance(archives, list) or len(archives) < 3:
        raise ValueError("hosted archive lock requires DNS clean/noise and SLR28 entries")
    roles: set[str] = set()
    ids: set[str] = set()
    for item in archives:
        archive_id = item.get("id")
        role = item.get("role")
        if not archive_id or archive_id in ids:
            raise ValueError(f"invalid/duplicate hosted archive id: {archive_id}")
        ids.add(archive_id)
        roles.add(str(role))
        parsed = urlparse(str(item.get("url", "")))
        if parsed.scheme != "https" or not parsed.netloc:
            raise ValueError(f"hosted archive URL must be HTTPS: {archive_id}")
        sha256 = str(item.get("sha256", "")).lower()
        if len(sha256) != 64 or any(ch not in "0123456789abcdef" for ch in sha256):
            raise ValueError(f"hosted archive must pin SHA-256: {archive_id}")
        if int(item.get("bytes", 0)) <= 0:
            raise ValueError(f"hosted archive must pin byte size: {archive_id}")
    if not {"dns-clean", "dns-noise", "slr28"}.issubset(roles):
        raise ValueError("hosted archive lock must contain dns-clean, dns-noise and slr28 roles")


def download(url: str, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_suffix(target.suffix + ".part")
    request = urllib.request.Request(url, headers={"User-Agent": "audio-pipeline-validation"})
    with urllib.request.urlopen(request, timeout=120) as response, partial.open("wb") as out:
        shutil.copyfileobj(response, out, length=1024 * 1024)
    partial.replace(target)


def safe_extract_tar_bz2(archive: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive, mode="r:bz2") as handle:
        members = handle.getmembers()
        for member in members:
            path = Path(member.name)
            if path.is_absolute() or ".." in path.parts or member.issym() or member.islnk():
                raise ValueError(f"unsafe DNS archive member: {member.name}")
        handle.extractall(destination, members=members)


def dns_counts(root: Path) -> tuple[int, int, int]:
    clean = noise = total = 0
    for path in root.rglob("*.wav"):
        rel = path.relative_to(root).as_posix().lower()
        total += 1
        if "noisy" in rel:
            continue
        if "clean" in rel:
            clean += 1
        elif "noise" in rel:
            noise += 1
    return clean, noise, total


def write_derived_dns_index(dns_root: Path, output: Path) -> int:
    rows = 0
    output.parent.mkdir(parents=True, exist_ok=True)
    with bz2.open(output, "wt", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        for path in sorted(dns_root.rglob("*.wav")):
            rel = path.relative_to(dns_root).as_posix()
            writer.writerow([path.stat().st_size, digest_file(path, "sha1"), f"datasets_fullband/{rel}"])
            rows += 1
    if rows == 0:
        raise ValueError("derived DNS index would be empty")
    return rows


def archive_by_role(lock: dict, role: str) -> dict:
    matches = [item for item in lock["archives"] if item["role"] == role]
    if len(matches) != 1:
        raise ValueError(f"expected exactly one hosted archive for role {role}")
    return matches[0]


def source_dataset(lock: dict, dataset_id: str) -> dict:
    matches = [item for item in lock.get("datasets", []) if item.get("id") == dataset_id]
    if len(matches) != 1:
        raise ValueError(f"source dataset lock missing {dataset_id}")
    return matches[0]


def bootstrap(source_root: Path, data_root: Path, seal: Path,
              archive_lock_path: Path, output: Path) -> dict:
    source_root = source_root.resolve()
    data_root = data_root.resolve()
    seal = seal.resolve()
    archive_lock_path = archive_lock_path.resolve()
    source_lock_path = source_root / "validation/datasets.lock.json"
    source_lock = load_json(source_lock_path)
    hosted_lock = load_json(archive_lock_path)
    validate_archive_lock(hosted_lock)

    dns = source_dataset(source_lock, "microsoft-dns-challenge")
    slr = source_dataset(source_lock, "openslr-slr28")
    if dns["revision"] != hosted_lock["dns_revision"]:
        raise ValueError("hosted DNS revision does not match frozen source dataset lock")
    if slr["source"] != archive_by_role(hosted_lock, "slr28")["url"]:
        raise ValueError("hosted SLR28 URL does not match frozen source dataset lock")

    prepare = source_root / "validation/tools/prepare_public_validation.py"
    fetch = source_root / "validation/tools/fetch_public_data.py"
    python = sys.executable
    data_root.mkdir(parents=True, exist_ok=True)

    run([
        python, str(prepare), "prepare", "--lock", str(source_lock_path),
        "--profile", "compact", "--root", str(data_root), "--seal", str(seal),
        "--allow-large-downloads",
    ], cwd=source_root)

    slr_item = archive_by_role(hosted_lock, "slr28")
    slr_path = data_root / slr["local_path"]
    if slr_path.stat().st_size != int(slr_item["bytes"]):
        raise ValueError("SLR28 byte-size mismatch")
    if digest_file(slr_path) != slr_item["sha256"]:
        raise ValueError("SLR28 SHA-256 mismatch")

    run([
        python, str(fetch), "--lock", str(source_lock_path), "--root", str(data_root),
        "--dataset", "microsoft-dns-challenge",
    ], cwd=source_root)
    dns_repo = data_root / dns["local_path"]
    head = run(["git", "-C", str(dns_repo), "rev-parse", "HEAD"], capture=True).strip()
    if head != hosted_lock["dns_revision"]:
        raise ValueError("materialized DNS repository revision mismatch")

    archive_dir = data_root / "github-hosted-dns-archives"
    dns_root = dns_repo / "datasets_fullband"
    archive_evidence = []
    for role in ("dns-clean", "dns-noise"):
        item = archive_by_role(hosted_lock, role)
        target = archive_dir / f"{item['id']}.tar.bz2"
        download(item["url"], target)
        actual_size = target.stat().st_size
        actual_sha = digest_file(target)
        if actual_size != int(item["bytes"]):
            raise ValueError(f"hosted archive byte-size mismatch: {item['id']}")
        if actual_sha != item["sha256"]:
            raise ValueError(f"hosted archive SHA-256 mismatch: {item['id']}")
        safe_extract_tar_bz2(target, dns_repo)
        archive_evidence.append({
            "id": item["id"], "role": role, "bytes": actual_size,
            "sha256": actual_sha, "url": item["url"],
        })

    clean, noise, total = dns_counts(dns_root)
    if clean < 32 or noise < 32:
        raise ValueError(f"minimal hosted DNS corpus is too small: clean={clean} noise={noise}")

    derived_index = data_root / "dns5-hosted-minimal-sha1.csv.bz2"
    index_rows = write_derived_dns_index(dns_root, derived_index)
    seal_data = load_json(seal)
    dns_seal = seal_data.setdefault("datasets", {}).setdefault("microsoft-dns-challenge", {})
    dns_seal.update({
        "checksum_index_path": str(derived_index),
        "checksum_index_sha256": digest_file(derived_index),
        "hosted_archive_lock_sha256": digest_file(archive_lock_path),
        "hosted_archive_sha256": {entry["id"]: entry["sha256"] for entry in archive_evidence},
    })
    seal.write_text(json.dumps(seal_data, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    verify_text = run([
        python, str(prepare), "verify", "--lock", str(source_lock_path),
        "--profile", "full", "--root", str(data_root), "--seal", str(seal),
        "--dns-data-root", str(dns_root),
    ], cwd=source_root, capture=True)
    verification = json.loads(verify_text)
    report = {
        "schema_version": 1,
        "classification": "READY",
        "source_lock_sha256": digest_file(source_lock_path),
        "hosted_archive_lock_sha256": digest_file(archive_lock_path),
        "dns_revision": head,
        "dns_root": str(dns_root),
        "dns_clean_wavs": clean,
        "dns_noise_wavs": noise,
        "dns_total_wavs": total,
        "derived_dns_index_rows": index_rows,
        "derived_dns_index_sha256": digest_file(derived_index),
        "archives": archive_evidence,
        "slr28_sha256": digest_file(slr_path),
        "verification": verification,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report


def self_test() -> None:
    sample = {
        "schema_version": 1,
        "lock_id": "test",
        "dns_revision": "0" * 40,
        "archives": [
            {"id": "c", "role": "dns-clean", "url": "https://example.com/c.tar.bz2", "sha256": "1" * 64, "bytes": 1},
            {"id": "n", "role": "dns-noise", "url": "https://example.com/n.tar.bz2", "sha256": "2" * 64, "bytes": 2},
            {"id": "s", "role": "slr28", "url": "https://example.com/s.zip", "sha256": "3" * 64, "bytes": 3},
        ],
    }
    validate_archive_lock(sample)
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        dns = root / "datasets_fullband/clean_fullband"
        dns.mkdir(parents=True)
        wav = dns / "x.wav"
        wav.write_bytes(b"abc")
        index = root / "index.csv.bz2"
        assert write_derived_dns_index(root / "datasets_fullband", index) == 1
        with bz2.open(index, "rt", encoding="utf-8") as handle:
            text = handle.read()
        assert "datasets_fullband/clean_fullband/x.wav" in text
    print("github-hosted full validation self-test: OK")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--source-root", type=Path)
    parser.add_argument("--data-root", type=Path)
    parser.add_argument("--seal", type=Path)
    parser.add_argument("--archive-lock", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    required = (args.source_root, args.data_root, args.seal, args.archive_lock, args.output)
    if any(value is None for value in required):
        parser.error("--source-root, --data-root, --seal, --archive-lock and --output are required")
    report = bootstrap(args.source_root, args.data_root, args.seal, args.archive_lock, args.output)
    print(json.dumps({
        "classification": report["classification"],
        "dns_clean_wavs": report["dns_clean_wavs"],
        "dns_noise_wavs": report["dns_noise_wavs"],
        "output": str(args.output),
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
