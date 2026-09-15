#!/usr/bin/env python3
"""Materialize SHA-256 pinned research-development audio on GitHub-hosted runners."""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import tarfile
import tempfile
import urllib.request
import zipfile
from pathlib import Path
from urllib.parse import urlparse

SCHEMA_VERSION = 1
EXPECTED_CATALOG = "audio-pipeline-public-development-v2"
EXPECTED_ROLES = {"clean-speech", "sim-rir", "noise-kitchen", "noise-traffic"}


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def load_json(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("JSON object required")
    return payload


def validate_lock(lock: dict) -> None:
    if lock.get("schema_version") != SCHEMA_VERSION or lock.get("catalog_id") != EXPECTED_CATALOG:
        raise ValueError("research development lock identity/schema invalid")
    archives = lock.get("archives")
    if not isinstance(archives, list) or len(archives) != 4:
        raise ValueError("research development lock requires exactly four archives")
    roles, ids = set(), set()
    for item in archives:
        if set(item) != {"id", "role", "url", "bytes", "sha256", "license", "usage_class", "upstream"}:
            raise ValueError(f"archive fields invalid: {item.get('id')}")
        ident, role = str(item["id"]), str(item["role"])
        if not ident or ident in ids or role in roles:
            raise ValueError("archive ids/roles must be unique")
        ids.add(ident); roles.add(role)
        parsed = urlparse(str(item["url"]))
        if parsed.scheme != "https" or not parsed.netloc:
            raise ValueError(f"HTTPS URL required: {ident}")
        digest = str(item["sha256"]).lower()
        if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
            raise ValueError(f"SHA-256 pin required: {ident}")
        if int(item["bytes"]) <= 0:
            raise ValueError(f"byte-size pin required: {ident}")
        if not str(item["license"]) or not str(item["usage_class"]):
            raise ValueError(f"license/usage_class required: {ident}")
    if roles != EXPECTED_ROLES:
        raise ValueError(f"archive role drift: {sorted(roles)}")


def download(url: str, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_suffix(target.suffix + ".part")
    request = urllib.request.Request(url, headers={"User-Agent": "audio-pipeline-research-development"})
    with urllib.request.urlopen(request, timeout=180) as response, partial.open("wb") as out:
        shutil.copyfileobj(response, out, length=1024 * 1024)
    partial.replace(target)


def _safe_member(name: str) -> None:
    path = Path(name)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError(f"unsafe archive member: {name}")


def safe_extract_tar_gz(archive: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive, "r:gz") as tf:
        members = tf.getmembers()
        for member in members:
            _safe_member(member.name)
            if member.issym() or member.islnk():
                raise ValueError(f"links forbidden in archive: {member.name}")
        tf.extractall(destination, members=members)


def safe_extract_zip(archive: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive) as zf:
        for info in zf.infolist():
            _safe_member(info.filename)
        zf.extractall(destination)


def by_role(lock: dict, role: str) -> dict:
    matches = [x for x in lock["archives"] if x["role"] == role]
    if len(matches) != 1:
        raise ValueError(f"expected exactly one archive role={role}")
    return matches[0]


def materialize(lock_path: Path, root: Path, output: Path) -> dict:
    lock = load_json(lock_path)
    validate_lock(lock)
    root = root.resolve()
    root.mkdir(parents=True, exist_ok=True)
    archives_dir = root / "archives"
    extracted = root / "extracted"
    evidence = []
    for role in sorted(EXPECTED_ROLES):
        item = by_role(lock, role)
        suffix = ".tar.gz" if item["url"].split("?", 1)[0].endswith(".tar.gz") else ".zip"
        archive = archives_dir / f"{item['id']}{suffix}"
        download(item["url"], archive)
        actual_bytes = archive.stat().st_size
        actual_sha = sha256_file(archive)
        if actual_bytes != int(item["bytes"]):
            raise ValueError(f"byte-size mismatch: {item['id']} {actual_bytes} != {item['bytes']}")
        if actual_sha != item["sha256"]:
            raise ValueError(f"SHA-256 mismatch: {item['id']}")
        destination = extracted / role
        if destination.exists():
            shutil.rmtree(destination)
        if suffix == ".tar.gz":
            safe_extract_tar_gz(archive, destination)
        else:
            safe_extract_zip(archive, destination)
        files = sorted(p for p in destination.rglob("*") if p.is_file())
        audio = [p for p in files if p.suffix.lower() in {".wav", ".flac"}]
        if not audio:
            raise ValueError(f"no audio members materialized: {item['id']}")
        evidence.append({
            "id": item["id"], "role": role, "bytes": actual_bytes, "sha256": actual_sha,
            "license": item["license"], "usage_class": item["usage_class"],
            "files": len(files), "audio_files": len(audio),
            "path": str(destination),
        })
    result = {
        "schema_version": 1,
        "catalog_id": lock["catalog_id"],
        "dataset_lock_sha256": sha256_file(lock_path),
        "root": str(root),
        "archives": evidence,
        "selection_authority": "research-development-only",
        "shipping_authority": False,
        "validation_grade_authority": False,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result


def self_test() -> None:
    fixture = {
        "schema_version": 1, "catalog_id": EXPECTED_CATALOG,
        "archives": [
            {"id": f"a-{i}", "role": role, "url": f"https://example.invalid/{i}.zip",
             "bytes": i + 1, "sha256": f"{i + 1:064x}"[-64:], "license": "fixture",
             "usage_class": "research-development", "upstream": "fixture"}
            for i, role in enumerate(sorted(EXPECTED_ROLES))
        ],
    }
    validate_lock(fixture)
    for bad in ("../x", "/tmp/x"):
        try:
            _safe_member(bad)
        except ValueError:
            pass
        else:
            raise AssertionError("unsafe member accepted")
    print("research development materializer self-test: OK")


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--self-test", action="store_true")
    p.add_argument("--lock", type=Path)
    p.add_argument("--root", type=Path)
    p.add_argument("--output", type=Path)
    a = p.parse_args()
    if a.self_test:
        self_test(); return 0
    if a.lock is None or a.root is None or a.output is None:
        p.error("--lock, --root and --output are required")
    result = materialize(a.lock, a.root, a.output)
    print(json.dumps({"result": "PASS", "archives": len(result["archives"]), "root": result["root"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
