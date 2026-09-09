#!/usr/bin/env python3
"""Hash-bind operator-materialized DSP research sources.

Commercial Extended Real scanners remain unchanged. This research scanner accepts
only LOCATA, MIMII and MIMII-DUE and emits a separate manifest that cannot be used
as commercial/readiness authority.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from extended_dataset_lock import catalog_items, load_json, sha256_file, validate_catalog

AUDIO_SUFFIXES = {".wav", ".flac", ".ogg", ".sph"}
RESEARCH_IDS = ("locata", "mimii", "mimii-due")


def stable_key(path: Path, root: Path) -> str:
    return hashlib.sha256(path.relative_to(root).as_posix().encode()).hexdigest()


def stable_select(paths: list[Path], root: Path, limit: int) -> list[Path]:
    return sorted(set(paths), key=lambda p: stable_key(p, root))[:max(0, limit)]


def file_record(root: Path, path: Path) -> dict:
    return {
        "relative_path": path.relative_to(root).as_posix(),
        "size": path.stat().st_size,
        "sha256": sha256_file(path),
    }


def audio_files(root: Path) -> list[Path]:
    return [p for p in root.rglob("*") if p.is_file() and p.suffix.lower() in AUDIO_SUFFIXES]


def machine_type(path: Path) -> str:
    text = path.as_posix().lower()
    for token in ("gearbox", "fan", "pump", "valve", "slider", "slide_rail", "slide-rail"):
        if token in text:
            return "slide-rail" if token in {"slider", "slide_rail", "slide-rail"} else token
    return "unknown"


def scan_locata(root: Path, limit: int) -> list[dict]:
    selected = stable_select(audio_files(root), root, limit)
    if not selected:
        raise ValueError("LOCATA scan found no audio")
    entries = []
    for path in selected:
        text = path.as_posix().lower()
        entries.append({
            "source_id": f"locata:{path.relative_to(root).as_posix()}",
            "kind": "farfield",
            "files": [file_record(root, path)],
            "dimensions": {
                "moving_source": "moving" in text or "task3" in text or "task5" in text,
                "moving_array": "task4" in text or "task5" in text or "task6" in text,
                "research_only": True,
            },
        })
    return entries


def scan_machine(root: Path, dataset_id: str, limit: int) -> list[dict]:
    selected = stable_select(audio_files(root), root, limit)
    if not selected:
        raise ValueError(f"{dataset_id} scan found no audio")
    return [{
        "source_id": f"{dataset_id}:{path.relative_to(root).as_posix()}",
        "kind": "negative",
        "files": [file_record(root, path)],
        "dimensions": {
            "machine_type": machine_type(path),
            "domain_shift": dataset_id == "mimii-due",
            "research_only": True,
        },
    } for path in selected]


def build_manifest(catalog_path: Path, data_root: Path, limit: int) -> dict:
    catalog = load_json(catalog_path)
    validate_catalog(catalog)
    by_id = catalog_items(catalog)
    missing = [item for item in RESEARCH_IDS if item not in by_id]
    if missing:
        raise ValueError(f"research catalog missing datasets: {missing}")
    datasets = []
    for dataset_id in RESEARCH_IDS:
        item = by_id[dataset_id]
        if item["usage_class"] not in {"conditional", "research-only"}:
            raise ValueError(f"research source became commercial authority: {dataset_id}")
        root = data_root / item["local_path"]
        if not root.is_dir():
            raise FileNotFoundError(root)
        entries = scan_locata(root, limit) if dataset_id == "locata" else scan_machine(root, dataset_id, limit)
        datasets.append({
            "id": dataset_id,
            "usage_class": item["usage_class"],
            "license": item["license"],
            "attribution": item["attribution"],
            "entries": entries,
        })
    return {
        "schema_version": 1,
        "profile": "dsp-research",
        "authority": "research-validation-only",
        "catalog_sha256": sha256_file(catalog_path),
        "datasets": datasets,
    }


def self_test() -> None:
    assert machine_type(Path("fan/id_00/normal.wav")) == "fan"
    assert machine_type(Path("gearbox/section_01/source_test.wav")) == "gearbox"
    assert machine_type(Path("misc/x.wav")) == "unknown"
    paths = [Path("/tmp/r/b.wav"), Path("/tmp/r/a.wav")]
    assert [p.name for p in stable_select(paths, Path("/tmp/r"), 2)] == [p.name for p in stable_select(list(reversed(paths)), Path("/tmp/r"), 2)]
    print("DSP research source scanner self-test: OK")


def main() -> int:
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("self-test")
    scan = sub.add_parser("scan")
    scan.add_argument("--catalog", type=Path, default=Path("validation/extended.datasets.lock.json"))
    scan.add_argument("--data-root", type=Path, required=True)
    scan.add_argument("--limit-per-dataset", type=int, default=16)
    scan.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    if args.command == "self-test":
        self_test(); return 0
    if args.limit_per_dataset < 2:
        raise SystemExit("limit-per-dataset must be >=2")
    manifest = build_manifest(args.catalog, args.data_root, args.limit_per_dataset)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"manifest": str(args.output), "datasets": len(manifest["datasets"]), "catalog_sha256": manifest["catalog_sha256"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
