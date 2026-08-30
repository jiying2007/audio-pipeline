#!/usr/bin/env python3
"""Validate the extended-real dataset catalog and normalized source manifests."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from urllib.parse import urlparse

SCHEMA_VERSION = 1
USAGE_CLASSES = {"commercial-validation", "conditional", "research-only", "catalog-only"}
PROFILE_CLASSES = {
    "commercial-core": {"commercial-validation"},
    "commercial-plus": {"commercial-validation"},
    "research": {"commercial-validation", "conditional", "research-only"},
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def safe_relative(value: str) -> bool:
    path = Path(value)
    return bool(value) and not path.is_absolute() and ".." not in path.parts


def validate_catalog(catalog: dict) -> None:
    if catalog.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("extended dataset catalog schema_version must be 1")
    datasets = catalog.get("datasets")
    profiles = catalog.get("profiles")
    if not isinstance(datasets, list) or not datasets:
        raise ValueError("extended dataset catalog requires a non-empty datasets list")
    if not isinstance(profiles, dict) or not profiles:
        raise ValueError("extended dataset catalog requires profiles")
    seen: set[str] = set()
    by_id: dict[str, dict] = {}
    for item in datasets:
        dataset_id = item.get("id")
        if not isinstance(dataset_id, str) or not dataset_id or dataset_id in seen:
            raise ValueError(f"invalid or duplicate extended dataset id: {dataset_id!r}")
        seen.add(dataset_id)
        by_id[dataset_id] = item
        parsed = urlparse(str(item.get("source", "")))
        if parsed.scheme != "https" or not parsed.netloc:
            raise ValueError(f"extended dataset source must be HTTPS: {dataset_id}")
        usage = item.get("usage_class")
        if usage not in USAGE_CLASSES:
            raise ValueError(f"invalid usage_class for {dataset_id}: {usage}")
        if not item.get("license") or not item.get("attribution"):
            raise ValueError(f"license and attribution are required: {dataset_id}")
        if not isinstance(item.get("validation_roles"), list) or not item["validation_roles"]:
            raise ValueError(f"validation_roles are required: {dataset_id}")
        if not safe_relative(str(item.get("local_path", ""))):
            raise ValueError(f"local_path must be safe and relative: {dataset_id}")
        if not isinstance(item.get("transforms_allowed"), bool):
            raise ValueError(f"transforms_allowed must be explicit: {dataset_id}")
    for profile, dataset_ids in profiles.items():
        if profile not in PROFILE_CLASSES:
            raise ValueError(f"unsupported extended profile: {profile}")
        if not isinstance(dataset_ids, list) or not dataset_ids:
            raise ValueError(f"profile must contain datasets: {profile}")
        allowed = PROFILE_CLASSES[profile]
        for dataset_id in dataset_ids:
            if dataset_id not in by_id:
                raise ValueError(f"profile {profile} references unknown dataset {dataset_id}")
            usage = by_id[dataset_id]["usage_class"]
            if usage not in allowed:
                raise ValueError(
                    f"profile {profile} may not include {dataset_id} with usage_class={usage}"
                )
    if not set(profiles["commercial-core"]).issubset(set(profiles["commercial-plus"])):
        raise ValueError("commercial-plus must be a superset of commercial-core")
    if not set(profiles["commercial-plus"]).issubset(set(profiles["research"])):
        raise ValueError("research must be a superset of commercial-plus")


def catalog_items(catalog: dict) -> dict[str, dict]:
    return {item["id"]: item for item in catalog["datasets"]}


def profile_ids(catalog: dict, profile: str) -> tuple[str, ...]:
    validate_catalog(catalog)
    try:
        values = catalog["profiles"][profile]
    except KeyError as exc:
        raise ValueError(f"unknown extended profile: {profile}") from exc
    return tuple(values)


def validate_manifest(manifest: dict, catalog: dict, catalog_path: Path | None = None) -> None:
    validate_catalog(catalog)
    if manifest.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("extended source manifest schema_version must be 1")
    profile = manifest.get("profile")
    expected_ids = set(profile_ids(catalog, str(profile)))
    actual = manifest.get("datasets")
    if not isinstance(actual, list) or not actual:
        raise ValueError("extended source manifest requires datasets")
    if catalog_path is not None:
        expected_catalog_sha = sha256_file(catalog_path)
        if manifest.get("catalog_sha256") != expected_catalog_sha:
            raise ValueError("extended source manifest was built from a different catalog")
    by_id = catalog_items(catalog)
    actual_ids = {item.get("id") for item in actual}
    if actual_ids != expected_ids:
        raise ValueError(
            f"extended source manifest dataset mismatch: missing={sorted(expected_ids-actual_ids)} "
            f"unexpected={sorted(actual_ids-expected_ids)}"
        )
    for dataset in actual:
        dataset_id = dataset.get("id")
        catalog_item = by_id[dataset_id]
        if dataset.get("usage_class") != catalog_item["usage_class"]:
            raise ValueError(f"usage class drift in source manifest: {dataset_id}")
        entries = dataset.get("entries")
        if not isinstance(entries, list) or not entries:
            raise ValueError(f"no materialized entries for extended dataset {dataset_id}")
        source_ids: set[str] = set()
        for entry in entries:
            source_id = entry.get("source_id")
            if not isinstance(source_id, str) or not source_id or source_id in source_ids:
                raise ValueError(f"invalid/duplicate source_id in {dataset_id}: {source_id!r}")
            source_ids.add(source_id)
            if entry.get("kind") not in {
                "enhancement-pair", "clean", "rir", "noise", "music",
                "farfield", "meeting", "negative",
            }:
                raise ValueError(f"invalid entry kind in {dataset_id}: {entry.get('kind')}")
            files = entry.get("files")
            if not isinstance(files, list) or not files:
                raise ValueError(f"entry files are required: {dataset_id}/{source_id}")
            for file_entry in files:
                relative = str(file_entry.get("relative_path", ""))
                digest = str(file_entry.get("sha256", ""))
                if not safe_relative(relative):
                    raise ValueError(f"unsafe relative_path in {dataset_id}/{source_id}: {relative}")
                if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest.lower()):
                    raise ValueError(f"invalid sha256 in {dataset_id}/{source_id}: {relative}")
            dimensions = entry.get("dimensions", {})
            if not isinstance(dimensions, dict):
                raise ValueError(f"dimensions must be an object: {dataset_id}/{source_id}")


def verify_manifest_files(manifest: dict, catalog: dict, data_root: Path) -> dict:
    validate_manifest(manifest, catalog)
    by_id = catalog_items(catalog)
    verified = 0
    bytes_hashed = 0
    for dataset in manifest["datasets"]:
        dataset_id = dataset["id"]
        root = data_root / by_id[dataset_id]["local_path"]
        for entry in dataset["entries"]:
            for file_entry in entry["files"]:
                path = root / file_entry["relative_path"]
                if not path.is_file():
                    raise FileNotFoundError(path)
                actual = sha256_file(path)
                if actual != file_entry["sha256"]:
                    raise ValueError(f"extended source file hash mismatch: {dataset_id}/{file_entry['relative_path']}")
                verified += 1
                bytes_hashed += path.stat().st_size
    return {"verified_files": verified, "verified_bytes": bytes_hashed}


def self_test() -> None:
    catalog = {
        "schema_version": 1,
        "profiles": {
            "commercial-core": ["a"],
            "commercial-plus": ["a"],
            "research": ["a", "b"],
        },
        "datasets": [
            {
                "id": "a", "source": "https://example.com/a", "license": "CC-BY-4.0",
                "usage_class": "commercial-validation", "attribution": "A", "local_path": "a",
                "transforms_allowed": True, "validation_roles": ["clean"],
            },
            {
                "id": "b", "source": "https://example.com/b", "license": "CC-BY-NC-4.0",
                "usage_class": "research-only", "attribution": "B", "local_path": "b",
                "transforms_allowed": True, "validation_roles": ["noise"],
            },
        ],
    }
    validate_catalog(catalog)
    bad = json.loads(json.dumps(catalog))
    bad["profiles"]["commercial-core"].append("b")
    try:
        validate_catalog(bad)
    except ValueError:
        pass
    else:
        raise AssertionError("research-only dataset entered commercial profile")
    manifest = {
        "schema_version": 1,
        "profile": "commercial-core",
        "datasets": [{
            "id": "a", "usage_class": "commercial-validation",
            "entries": [{
                "source_id": "x", "kind": "clean", "files": [
                    {"relative_path": "x.wav", "sha256": "0" * 64}
                ], "dimensions": {}
            }]
        }]
    }
    validate_manifest(manifest, catalog)
    print("extended dataset catalog self-test: OK")


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    validate = sub.add_parser("validate")
    validate.add_argument("--catalog", type=Path, required=True)
    verify = sub.add_parser("verify-manifest")
    verify.add_argument("--catalog", type=Path, required=True)
    verify.add_argument("--manifest", type=Path, required=True)
    verify.add_argument("--data-root", type=Path, required=True)
    sub.add_parser("self-test")
    args = parser.parse_args()
    if args.command == "self-test":
        self_test()
        return 0
    catalog = load_json(args.catalog)
    validate_catalog(catalog)
    if args.command == "validate":
        print(json.dumps({
            "catalog_sha256": sha256_file(args.catalog),
            "datasets": len(catalog["datasets"]),
            "profiles": sorted(catalog["profiles"]),
        }, sort_keys=True))
        return 0
    manifest = load_json(args.manifest)
    validate_manifest(manifest, catalog, args.catalog)
    result = verify_manifest_files(manifest, catalog, args.data_root)
    result["manifest_sha256"] = sha256_file(args.manifest)
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
