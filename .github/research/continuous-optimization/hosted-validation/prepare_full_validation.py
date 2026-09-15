#!/usr/bin/env python3
"""Bootstrap validation-grade public data on an ephemeral GitHub-hosted runner.

The frozen candidate source still owns the canonical dataset lock, verifier and
corpus builder. This helper materializes only the public inputs required by the
requested gate: exact AEC LFS files at the pinned revision, SHA-256-bound SLR28,
and a minimal official DNS5 clean/noise archive pair pinned by SHA-256. A local
SHA1 index is derived only after those DNS archives pass their SHA-256 pins so
the frozen source can reuse its existing per-WAV verification path.
"""

from __future__ import annotations

import argparse
import bz2
import csv
import hashlib
import json
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

SCHEMA_VERSION = 1
AEC_SCENARIOS = ("farend-singletalk", "doubletalk", "nearend-singletalk")


def digest_file(path: Path, algorithm: str = "sha256") -> str:
    digest = hashlib.new(algorithm)
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_progress(path: Path | None, stage: str, status: str = "in_progress", **details: object) -> None:
    if path is None:
        return
    payload = {"schema_version": 1, "stage": stage, "status": status, **details}
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


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
    revision = str(lock.get("dns_revision", "")).lower()
    if len(revision) != 40 or any(ch not in "0123456789abcdef" for ch in revision):
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
    with urllib.request.urlopen(request, timeout=180) as response, partial.open("wb") as out:
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


def normalize_dns_wavs(staging: Path, dns_root: Path) -> int:
    moved = 0
    for source in sorted(staging.rglob("*.wav")):
        parts = list(source.relative_to(staging).parts)
        lowered = [part.lower() for part in parts]
        marker = None
        marker_index = -1
        for candidate in ("clean_fullband", "noise_fullband"):
            if candidate in lowered:
                marker = candidate
                marker_index = lowered.index(candidate)
                break
        if marker is None:
            continue
        tail_parts = parts[marker_index + 1:] or [source.name]
        destination = dns_root / marker / Path(*tail_parts)
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            if digest_file(destination) != digest_file(source):
                raise ValueError(f"conflicting DNS archive member: {destination}")
            source.unlink()
        else:
            shutil.move(str(source), str(destination))
        moved += 1
    if moved == 0:
        raise ValueError("DNS archive did not contain clean_fullband/noise_fullband WAV members")
    return moved


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


def check_materialized(path: Path) -> None:
    with path.open("rb") as handle:
        prefix = handle.read(80)
    if prefix.startswith(b"version https://git-lfs.github.com/spec/v1"):
        raise ValueError(f"AEC LFS object was not materialized: {path}")


def aec_pairs(aec_repo: Path) -> list[tuple[Path, Path]]:
    base = aec_repo / "datasets" / "test_set_icassp2022"
    pairs: list[tuple[Path, Path]] = []
    for scenario in AEC_SCENARIOS:
        directory = base / scenario
        for mic in sorted(directory.glob("*_mic.wav")):
            lpb = mic.with_name(mic.name[:-8] + "_lpb.wav")
            if lpb.exists():
                pairs.append((mic, lpb))
    return pairs


def materialize_aec(source_root: Path, source_lock_path: Path, data_root: Path,
                    aec: dict, aec_limit: int) -> dict:
    fetch = source_root / "validation/tools/fetch_public_data.py"
    run([
        sys.executable, str(fetch), "--lock", str(source_lock_path), "--root", str(data_root),
        "--dataset", "microsoft-aec-challenge",
    ], cwd=source_root)
    repo = data_root / aec["local_path"]
    head = run(["git", "-C", str(repo), "rev-parse", "HEAD"], capture=True).strip()
    if head != aec["revision"]:
        raise ValueError("materialized AEC repository revision mismatch")
    pairs = aec_pairs(repo)
    buckets = {
        scenario: [(mic, lpb) for mic, lpb in pairs if mic.parent.name == scenario]
        for scenario in AEC_SCENARIOS
    }
    balanced: list[tuple[Path, Path]] = []
    index = 0
    while len(balanced) < aec_limit:
        progressed = False
        for scenario in AEC_SCENARIOS:
            if index < len(buckets[scenario]) and len(balanced) < aec_limit:
                balanced.append(buckets[scenario][index])
                progressed = True
        if not progressed:
            break
        index += 1
    if len(balanced) < aec_limit:
        raise ValueError(f"AEC checkout has only {len(balanced)} balanced pairs for requested limit {aec_limit}")

    selected: set[Path] = set()
    for mic, lpb in balanced:
        selected.update((mic, lpb))
    for required in aec.get("required_paths", []):
        directory = repo / required
        wavs = sorted(directory.rglob("*.wav"))
        if len(wavs) < 16:
            raise ValueError(f"AEC required directory has fewer than 16 WAVs: {directory}")
        selected.update(wavs[:16])
    includes = sorted(path.relative_to(repo).as_posix() for path in selected)
    run(["git", "-C", str(repo), "lfs", "pull", "--include", ",".join(includes), "--exclude", ""])
    for path in selected:
        check_materialized(path)
    return {
        "id": aec["id"], "revision": head, "requested_pairs": aec_limit,
        "materialized_files": len(selected),
    }


def bootstrap(source_root: Path, data_root: Path, seal: Path,
              archive_lock_path: Path, output: Path, aec_limit: int,
              progress_output: Path | None = None) -> dict:
    write_progress(progress_output, "bootstrap-init")
    if aec_limit <= 0:
        raise ValueError("aec_limit must be positive")
    source_root = source_root.resolve()
    data_root = data_root.resolve()
    seal = seal.resolve()
    archive_lock_path = archive_lock_path.resolve()
    source_lock_path = source_root / "validation/datasets.lock.json"
    source_lock = load_json(source_lock_path)
    hosted_lock = load_json(archive_lock_path)
    validate_archive_lock(hosted_lock)

    aec = source_dataset(source_lock, "microsoft-aec-challenge")
    dns = source_dataset(source_lock, "microsoft-dns-challenge")
    slr = source_dataset(source_lock, "openslr-slr28")
    if dns["revision"] != hosted_lock["dns_revision"]:
        raise ValueError("hosted DNS revision does not match frozen source dataset lock")
    if slr["source"] != archive_by_role(hosted_lock, "slr28")["url"]:
        raise ValueError("hosted SLR28 URL does not match frozen source dataset lock")

    data_root.mkdir(parents=True, exist_ok=True)
    write_progress(progress_output, "aec-materialization")
    aec_evidence = materialize_aec(source_root, source_lock_path, data_root, aec, aec_limit)
    write_progress(progress_output, "aec-materialization", "success",
                   materialized_files=aec_evidence["materialized_files"])

    write_progress(progress_output, "slr28-materialization")
    slr_item = archive_by_role(hosted_lock, "slr28")
    slr_path = data_root / slr["local_path"]
    download(slr_item["url"], slr_path)
    if slr_path.stat().st_size != int(slr_item["bytes"]):
        raise ValueError("SLR28 byte-size mismatch")
    if digest_file(slr_path) != slr_item["sha256"]:
        raise ValueError("SLR28 SHA-256 mismatch")
    run([
        sys.executable, str(source_root / "validation/tools/dataset_lock.py"), "seal",
        "--lock", str(source_lock_path), "--seal", str(seal),
        "--dataset-id", "openslr-slr28", "--asset", str(slr_path),
    ], cwd=source_root)
    write_progress(progress_output, "slr28-materialization", "success",
                   bytes=slr_path.stat().st_size, sha256=digest_file(slr_path))

    write_progress(progress_output, "dns-checkout")
    fetch = source_root / "validation/tools/fetch_public_data.py"
    run([
        sys.executable, str(fetch), "--lock", str(source_lock_path), "--root", str(data_root),
        "--dataset", "microsoft-dns-challenge",
    ], cwd=source_root)
    dns_repo = data_root / dns["local_path"]
    dns_head = run(["git", "-C", str(dns_repo), "rev-parse", "HEAD"], capture=True).strip()
    if dns_head != hosted_lock["dns_revision"]:
        raise ValueError("materialized DNS repository revision mismatch")
    write_progress(progress_output, "dns-checkout", "success", revision=dns_head)

    archive_dir = data_root / "github-hosted-dns-archives"
    dns_root = dns_repo / "datasets_fullband"
    archive_evidence = []
    for role in ("dns-clean", "dns-noise"):
        write_progress(progress_output, f"{role}-archive")
        item = archive_by_role(hosted_lock, role)
        target = archive_dir / f"{item['id']}.tar.bz2"
        download(item["url"], target)
        actual_size = target.stat().st_size
        actual_sha = digest_file(target)
        if actual_size != int(item["bytes"]):
            raise ValueError(f"hosted archive byte-size mismatch: {item['id']}")
        if actual_sha != item["sha256"]:
            raise ValueError(f"hosted archive SHA-256 mismatch: {item['id']}")
        with tempfile.TemporaryDirectory(prefix="dns-extract-", dir=data_root) as tmp:
            staging = Path(tmp)
            safe_extract_tar_bz2(target, staging)
            moved = normalize_dns_wavs(staging, dns_root)
        archive_evidence.append({
            "id": item["id"], "role": role, "bytes": actual_size,
            "sha256": actual_sha, "url": item["url"], "wav_count": moved,
        })
        write_progress(progress_output, f"{role}-archive", "success",
                       bytes=actual_size, sha256=actual_sha, wav_count=moved)

    clean, noise, total = dns_counts(dns_root)
    if clean < 32 or noise < 32:
        raise ValueError(f"minimal hosted DNS corpus is too small: clean={clean} noise={noise}")

    write_progress(progress_output, "dns-index")
    derived_index = data_root / "dns5-hosted-minimal-sha1.csv.bz2"
    index_rows = write_derived_dns_index(dns_root, derived_index)
    write_progress(progress_output, "dns-index", "success", rows=index_rows)
    seal_data = load_json(seal)
    dns_seal = seal_data.setdefault("datasets", {}).setdefault("microsoft-dns-challenge", {})
    dns_seal.update({
        "checksum_index_path": str(derived_index),
        "checksum_index_sha256": digest_file(derived_index),
        "hosted_archive_lock_sha256": digest_file(archive_lock_path),
        "hosted_archive_sha256": {entry["id"]: entry["sha256"] for entry in archive_evidence},
    })
    seal.write_text(json.dumps(seal_data, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    write_progress(progress_output, "full-cache-verification")
    prepare = source_root / "validation/tools/prepare_public_validation.py"
    verify_text = run([
        sys.executable, str(prepare), "verify", "--lock", str(source_lock_path),
        "--profile", "full", "--root", str(data_root), "--seal", str(seal),
        "--dns-data-root", str(dns_root),
    ], cwd=source_root, capture=True)
    verification = json.loads(verify_text)
    write_progress(progress_output, "full-cache-verification", "success")
    report = {
        "schema_version": 1,
        "classification": "READY",
        "source_lock_sha256": digest_file(source_lock_path),
        "hosted_archive_lock_sha256": digest_file(archive_lock_path),
        "aec": aec_evidence,
        "dns_revision": dns_head,
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
    write_progress(progress_output, "ready", "success",
                   dns_clean_wavs=clean, dns_noise_wavs=noise, dns_total_wavs=total)
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
        staging = root / "staging/a/clean_fullband/set"
        staging.mkdir(parents=True)
        wav = staging / "x.wav"
        wav.write_bytes(b"abc")
        dns_root = root / "datasets_fullband"
        assert normalize_dns_wavs(root / "staging", dns_root) == 1
        assert (dns_root / "clean_fullband/set/x.wav").read_bytes() == b"abc"
        index = root / "index.csv.bz2"
        assert write_derived_dns_index(dns_root, index) == 1
        with bz2.open(index, "rt", encoding="utf-8") as handle:
            text = handle.read()
        assert "datasets_fullband/clean_fullband/set/x.wav" in text
    print("github-hosted full validation self-test: OK")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--source-root", type=Path)
    parser.add_argument("--data-root", type=Path)
    parser.add_argument("--seal", type=Path)
    parser.add_argument("--archive-lock", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--progress-output", type=Path)
    parser.add_argument("--aec-limit", type=int, default=60)
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    required = (args.source_root, args.data_root, args.seal, args.archive_lock, args.output)
    if any(value is None for value in required):
        parser.error("--source-root, --data-root, --seal, --archive-lock and --output are required")
    try:
        report = bootstrap(
            args.source_root, args.data_root, args.seal, args.archive_lock, args.output,
            args.aec_limit, args.progress_output)
    except Exception as exc:
        stage = "bootstrap"
        if args.progress_output is not None and args.progress_output.exists():
            try:
                stage = str(load_json(args.progress_output).get("stage", stage))
            except Exception:
                pass
        write_progress(args.progress_output, stage, "failure",
                       error_type=type(exc).__name__, error=str(exc))
        raise
    print(json.dumps({
        "classification": report["classification"],
        "aec_materialized_files": report["aec"]["materialized_files"],
        "dns_clean_wavs": report["dns_clean_wavs"],
        "dns_noise_wavs": report["dns_noise_wavs"],
        "output": str(args.output),
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
