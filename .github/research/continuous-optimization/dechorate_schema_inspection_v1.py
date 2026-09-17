#!/usr/bin/env python3
"""Metadata-only schema inspection for the frozen dEchorate qualification set.

This tool deliberately never indexes an HDF5 Dataset and never calls a dataset
payload read API. It inspects only object names, dataset metadata and HDF5
attributes. Source objects are downloaded only after their names have been
frozen by the predecessor qualification manifest and are hash/size verified
before opening.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import urllib.parse
import urllib.request

import h5py
import numpy as np

MIRROR = "https://www.sofaconventions.org/data/database/dechorate/"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def normalize_attr_atom(value):
    """Return stable JSON metadata without dereferencing HDF5 references."""
    if isinstance(value, h5py.RegionReference):
        return {"hdf5_reference": bool(value), "reference_type": "RegionReference"}
    if isinstance(value, h5py.Reference):
        return {"hdf5_reference": bool(value), "reference_type": "Reference"}
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    if isinstance(value, str):
        return value
    if isinstance(value, np.generic):
        return normalize_attr_atom(value.item())
    if isinstance(value, list):
        return [normalize_attr_atom(x) for x in value]
    if isinstance(value, tuple):
        return [normalize_attr_atom(x) for x in value]
    if isinstance(value, dict):
        return {str(k): normalize_attr_atom(v) for k, v in sorted(value.items(), key=lambda kv: str(kv[0]))}
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    return {"metadata_type": type(value).__name__}


def jsonable_attr(value):
    """Convert an HDF5 attribute value to bounded JSON-safe metadata."""
    if isinstance(value, np.ndarray):
        meta = {"shape": list(value.shape), "dtype": str(value.dtype)}
        # Attributes are metadata, not dataset payloads. Preserve only small
        # values so evidence remains bounded and readable. References are
        # represented by stable type/validity markers and are never followed.
        if value.size <= 32:
            meta["value"] = normalize_attr_atom(value.tolist())
        return meta
    return normalize_attr_atom(value)


def attrs_schema(obj) -> dict:
    return {str(k): jsonable_attr(v) for k, v in sorted(obj.attrs.items(), key=lambda kv: str(kv[0]))}


def dataset_schema(ds: h5py.Dataset) -> dict:
    return {
        "kind": "dataset",
        "shape": list(ds.shape),
        "dtype": str(ds.dtype),
        "maxshape": None if ds.maxshape is None else [x for x in ds.maxshape],
        "chunks": None if ds.chunks is None else list(ds.chunks),
        "compression": ds.compression,
        "compression_opts": normalize_attr_atom(ds.compression_opts),
        "shuffle": bool(ds.shuffle),
        "fletcher32": bool(ds.fletcher32),
        "scaleoffset": normalize_attr_atom(ds.scaleoffset),
        "attrs": attrs_schema(ds),
    }


def inspect_hdf5(path: Path) -> dict:
    if not h5py.is_hdf5(path):
        raise RuntimeError(f"not an HDF5/NetCDF4 object: {path.name}")
    result = {"root_attrs": {}, "objects": {}}
    with h5py.File(path, "r") as f:
        result["root_attrs"] = attrs_schema(f)

        def visitor(name, obj):
            if isinstance(obj, h5py.Group):
                result["objects"][name] = {
                    "kind": "group",
                    "attrs": attrs_schema(obj),
                }
            elif isinstance(obj, h5py.Dataset):
                result["objects"][name] = dataset_schema(obj)
            else:
                result["objects"][name] = {"kind": type(obj).__name__}

        f.visititems(visitor)
    return result


def fetch_verified(spec: dict, out_dir: Path) -> Path:
    name = spec["name"]
    if Path(name).name != name:
        raise RuntimeError(f"unsafe object name: {name}")
    url = urllib.parse.urljoin(MIRROR, urllib.parse.quote(name))
    target = out_dir / name
    if not target.exists():
        req = urllib.request.Request(url, headers={"User-Agent": "audio-pipeline-research-schema-inspection/1"})
        with urllib.request.urlopen(req, timeout=120) as response, target.open("wb") as out:
            while True:
                block = response.read(1024 * 1024)
                if not block:
                    break
                out.write(block)
    size = target.stat().st_size
    digest = sha256_file(target)
    if size != int(spec["size_bytes"]):
        raise RuntimeError(f"size mismatch for {name}: {size} != {spec['size_bytes']}")
    if digest != spec["sha256"]:
        raise RuntimeError(f"sha256 mismatch for {name}: {digest} != {spec['sha256']}")
    return target


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--qualification-manifest", required=True)
    p.add_argument("--download-dir", required=True)
    p.add_argument("--output", required=True)
    args = p.parse_args()

    manifest = json.loads(Path(args.qualification_manifest).read_text(encoding="utf-8"))
    protocol = manifest["inventory_protocol"]
    specs = protocol["expected_selected_objects"]
    if not protocol.get("inventory_frozen"):
        raise RuntimeError("qualification inventory must be frozen")
    if len(specs) != int(protocol["expected_selected_object_count"]):
        raise RuntimeError("selected object count drift")

    out_dir = Path(args.download_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    evidence = {
        "investigation": "dechorate-schema-inspection-v1",
        "authority": "SCHEMA_INSPECTION_ONLY",
        "dataset_payload_reads": False,
        "acoustic_processing": False,
        "source_inventory_fingerprint": protocol["expected_selected_fingerprint_sha256"],
        "objects": [],
    }

    for spec in specs:
        path = fetch_verified(spec, out_dir)
        schema = inspect_hdf5(path)
        evidence["objects"].append({
            "name": spec["name"],
            "size_bytes": path.stat().st_size,
            "sha256": sha256_file(path),
            "schema": schema,
        })

    canonical_schema = {
        "source_inventory_fingerprint": evidence["source_inventory_fingerprint"],
        "objects": [{"name": x["name"], "schema": x["schema"]} for x in evidence["objects"]],
    }
    encoded = json.dumps(canonical_schema, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    evidence["schema_fingerprint_sha256"] = hashlib.sha256(encoded).hexdigest()
    evidence["selected_object_count"] = len(evidence["objects"])
    evidence["selected_total_bytes"] = sum(x["size_bytes"] for x in evidence["objects"])

    Path(args.output).write_text(json.dumps(evidence, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({
        "selected_object_count": evidence["selected_object_count"],
        "selected_total_bytes": evidence["selected_total_bytes"],
        "schema_fingerprint_sha256": evidence["schema_fingerprint_sha256"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
