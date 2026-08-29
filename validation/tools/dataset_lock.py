#!/usr/bin/env python3
"""Validate and locally seal public validation dataset inputs."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
from pathlib import Path
from urllib.parse import urlparse

HEX40 = set("0123456789abcdef")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def safe_relative(value: str) -> bool:
    path = Path(value)
    return not path.is_absolute() and ".." not in path.parts


def validate_lock(lock: dict) -> None:
    if lock.get("schema_version") != 1:
        raise ValueError("dataset lock schema_version must be 1")
    if not lock.get("lock_id"):
        raise ValueError("dataset lock_id is required")
    datasets = lock.get("datasets")
    if not isinstance(datasets, list) or not datasets:
        raise ValueError("datasets must be a non-empty list")
    seen: set[str] = set()
    valid_modes = {"git-revision", "upstream-checksum-index", "local-sha256-seal"}
    for item in datasets:
        dataset_id = item.get("id")
        if not isinstance(dataset_id, str) or not dataset_id:
            raise ValueError("dataset id is required")
        if dataset_id in seen:
            raise ValueError(f"duplicate dataset id: {dataset_id}")
        seen.add(dataset_id)
        if item.get("kind") not in {"git", "archive", "checksum-index"}:
            raise ValueError(f"invalid dataset kind: {dataset_id}")
        source = item.get("source", "")
        parsed = urlparse(source)
        if parsed.scheme != "https" or not parsed.netloc:
            raise ValueError(f"dataset source must be HTTPS: {dataset_id}")
        local_path = item.get("local_path", "")
        if local_path and not safe_relative(local_path):
            raise ValueError(f"unsafe local_path: {dataset_id}")
        revision = item.get("revision")
        if item.get("kind") == "git":
            if not isinstance(revision, str) or len(revision) != 40 or any(c not in HEX40 for c in revision.lower()):
                raise ValueError(f"git dataset must pin a 40-hex revision: {dataset_id}")
        for required in item.get("required_paths", []):
            if not safe_relative(required):
                raise ValueError(f"unsafe required path in {dataset_id}: {required}")
        integrity = item.get("integrity", {})
        if integrity.get("mode") not in valid_modes:
            raise ValueError(f"invalid integrity mode: {dataset_id}")
        if not item.get("license") or not item.get("validation_roles"):
            raise ValueError(f"license and validation_roles are required: {dataset_id}")


def read_seal(path: Path | None) -> dict:
    if path is None or not path.exists():
        return {"schema_version": 1, "datasets": {}}
    seal = load_json(path)
    if seal.get("schema_version") != 1 or not isinstance(seal.get("datasets"), dict):
        raise ValueError("invalid local seal")
    return seal


def git_output(*args: str) -> str:
    return subprocess.check_output(["git", *args], text=True).strip()


def check_not_lfs_pointer(path: Path) -> None:
    if not path.is_file():
        return
    with path.open("rb") as handle:
        prefix = handle.read(80)
    if prefix.startswith(b"version https://git-lfs.github.com/spec/v1"):
        raise ValueError(f"Git LFS object is not materialized: {path}")


def verify_local(lock_path: Path, root: Path, seal_path: Path | None,
                 validation_grade: bool, require_materialized: bool) -> dict:
    lock = load_json(lock_path)
    validate_lock(lock)
    seal = read_seal(seal_path)
    if seal.get("lock_sha256") and seal["lock_sha256"] != sha256_file(lock_path):
        raise ValueError("local seal was created for a different datasets.lock.json")
    results = []
    for item in lock["datasets"]:
        dataset_id = item["id"]
        mode = item["integrity"]["mode"]
        local = root / item.get("local_path", dataset_id)
        result = {"id": dataset_id, "verified": False, "path": str(local)}
        if item["kind"] == "git":
            if not (local / ".git").exists():
                raise FileNotFoundError(f"missing pinned git dataset: {local}")
            head = git_output("-C", str(local), "rev-parse", "HEAD")
            if head != item["revision"]:
                raise ValueError(f"revision mismatch for {dataset_id}: {head} != {item['revision']}")
            for required in item.get("required_paths", []):
                candidate = local / required
                if not candidate.exists():
                    raise FileNotFoundError(f"missing required path for {dataset_id}: {candidate}")
                if require_materialized and candidate.is_dir():
                    wavs = sorted(candidate.rglob("*.wav"))[:8]
                    if not wavs:
                        raise ValueError(f"no materialized WAV files under {candidate}")
                    for wav in wavs:
                        check_not_lfs_pointer(wav)
            result.update({"verified": True, "revision": head})
        elif mode == "local-sha256-seal":
            seal_item = seal.get("datasets", {}).get(dataset_id, {})
            expected = seal_item.get("sha256") or item["integrity"].get("digest")
            sealed_path = Path(seal_item.get("path", str(local)))
            if not sealed_path.is_absolute():
                sealed_path = root / sealed_path
            if not expected:
                if validation_grade:
                    raise ValueError(f"validation-grade requires a local SHA-256 seal for {dataset_id}")
                result["note"] = "unsealed"
            else:
                if not sealed_path.exists():
                    raise FileNotFoundError(sealed_path)
                actual = sha256_file(sealed_path)
                if actual != expected:
                    raise ValueError(f"SHA-256 mismatch for {dataset_id}")
                result.update({"verified": True, "sha256": actual, "path": str(sealed_path)})
        elif mode == "upstream-checksum-index":
            seal_item = seal.get("datasets", {}).get(dataset_id, {})
            index_path = seal_item.get("checksum_index_path")
            expected = seal_item.get("checksum_index_sha256")
            if index_path and expected:
                candidate = Path(index_path)
                if not candidate.is_absolute():
                    candidate = root / candidate
                if sha256_file(candidate) != expected:
                    raise ValueError(f"checksum-index SHA-256 mismatch for {dataset_id}")
                result.update({"verified": True, "checksum_index": str(candidate)})
            elif validation_grade:
                raise ValueError(f"validation-grade requires sealed upstream checksum index for {dataset_id}")
            else:
                result["note"] = "checksum index not locally sealed"
        results.append(result)
    return {
        "lock_id": lock["lock_id"],
        "lock_sha256": sha256_file(lock_path),
        "validation_grade": validation_grade,
        "datasets": results,
    }


def seal_asset(lock_path: Path, seal_path: Path, dataset_id: str, asset: Path,
               checksum_index: bool) -> None:
    lock = load_json(lock_path)
    validate_lock(lock)
    known = {item["id"] for item in lock["datasets"]}
    if dataset_id not in known:
        raise ValueError(f"unknown dataset id: {dataset_id}")
    if not asset.exists() or not asset.is_file():
        raise FileNotFoundError(asset)
    seal = read_seal(seal_path)
    seal["schema_version"] = 1
    seal["lock_sha256"] = sha256_file(lock_path)
    entry = seal.setdefault("datasets", {}).setdefault(dataset_id, {})
    if checksum_index:
        entry["checksum_index_path"] = str(asset)
        entry["checksum_index_sha256"] = sha256_file(asset)
    else:
        entry["path"] = str(asset)
        entry["sha256"] = sha256_file(asset)
    seal_path.parent.mkdir(parents=True, exist_ok=True)
    seal_path.write_text(json.dumps(seal, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def self_test() -> None:
    sample = {
        "schema_version": 1,
        "lock_id": "test",
        "datasets": [{
            "id": "x", "kind": "git", "source": "https://example.com/x.git",
            "revision": "0" * 40, "license": "test", "validation_roles": ["test"],
            "local_path": "x", "required_paths": [], "integrity": {"mode": "git-revision"}
        }],
    }
    validate_lock(sample)
    bad = json.loads(json.dumps(sample))
    bad["datasets"][0]["revision"] = "main"
    try:
        validate_lock(bad)
    except ValueError:
        pass
    else:
        raise AssertionError("unpinned git revision accepted")
    assert sha256_bytes(b"abc") == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
    print("validation dataset-lock self-test: OK")


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    validate = sub.add_parser("validate")
    validate.add_argument("--lock", type=Path, required=True)
    verify = sub.add_parser("verify-local")
    verify.add_argument("--lock", type=Path, required=True)
    verify.add_argument("--root", type=Path, required=True)
    verify.add_argument("--seal", type=Path)
    verify.add_argument("--validation-grade", action="store_true")
    verify.add_argument("--require-materialized", action="store_true")
    seal = sub.add_parser("seal")
    seal.add_argument("--lock", type=Path, required=True)
    seal.add_argument("--seal", type=Path, required=True)
    seal.add_argument("--dataset-id", required=True)
    seal.add_argument("--asset", type=Path, required=True)
    seal.add_argument("--checksum-index", action="store_true")
    sub.add_parser("self-test")
    args = parser.parse_args()

    if args.command == "validate":
        lock = load_json(args.lock)
        validate_lock(lock)
        print(json.dumps({"lock_id": lock["lock_id"], "sha256": sha256_file(args.lock)}, sort_keys=True))
    elif args.command == "verify-local":
        print(json.dumps(verify_local(args.lock, args.root, args.seal,
                                      args.validation_grade, args.require_materialized),
                         indent=2, sort_keys=True))
    elif args.command == "seal":
        seal_asset(args.lock, args.seal, args.dataset_id, args.asset, args.checksum_index)
        print(args.seal)
    else:
        self_test()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
