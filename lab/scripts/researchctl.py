#!/usr/bin/env python3
"""Fail-closed controller for DSP research-only/conditional corpora.

This tool deliberately has no readiness, Extended Real, HIL or certification command.
Large/licensed sources are operator-imported through labctl.py adopt; this controller
only validates the research profile and confirms materialization markers.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_LOCK = REPO_ROOT / "lab" / "data-sources.lock.json"
PROFILE = "dsp-research"
EXPECTED_IDS = {"locata", "mimii", "mimii-due"}
ALLOWED_USAGE = {"conditional", "research-only"}


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def index(catalog: dict) -> dict[str, dict]:
    return {str(item["id"]): item for item in catalog.get("datasets", [])}


def validate_catalog(catalog: dict) -> None:
    profiles = catalog.get("profiles", {})
    if set(profiles.get(PROFILE, [])) != EXPECTED_IDS:
        raise ValueError("dsp-research profile must contain exactly LOCATA/MIMII/MIMII-DUE")
    by_id = index(catalog)
    if not EXPECTED_IDS <= set(by_id):
        raise ValueError("dsp-research dataset descriptors are incomplete")
    for dataset_id in EXPECTED_IDS:
        item = by_id[dataset_id]
        if item.get("provider") != "operator_import":
            raise ValueError(f"research source must be reviewed operator_import: {dataset_id}")
        if item.get("usage_class") not in ALLOWED_USAGE:
            raise ValueError(f"research source usage class is too permissive: {dataset_id}")
        local = Path(str(item.get("local_path", "")))
        if not str(local) or local.is_absolute() or ".." in local.parts:
            raise ValueError(f"unsafe research local_path: {dataset_id}")
    for profile in ("commercial-core", "commercial-plus"):
        leaked = EXPECTED_IDS.intersection(profiles.get(profile, []))
        if leaked:
            raise ValueError(f"research sources leaked into {profile}: {sorted(leaked)}")
    if by_id["mimii-due"].get("usage_class") != "research-only":
        raise ValueError("MIMII-DUE must remain research-only")


def materialization_status(catalog: dict, data_root: Path) -> dict:
    validate_catalog(catalog)
    by_id = index(catalog)
    result = {}
    for dataset_id in sorted(EXPECTED_IDS):
        root = data_root / by_id[dataset_id]["local_path"]
        marker = root / ".audio-pipeline-materialized.json"
        result[dataset_id] = {
            "path": str(root),
            "present": root.is_dir(),
            "adopted": marker.is_file(),
            "usage_class": by_id[dataset_id]["usage_class"],
        }
    return result


def self_test() -> None:
    catalog = {
        "profiles": {
            "commercial-core": ["clean"],
            "commercial-plus": ["clean"],
            PROFILE: ["locata", "mimii", "mimii-due"],
        },
        "datasets": [
            {"id": "clean", "provider": "operator_import", "local_path": "clean", "usage_class": "commercial-validation"},
            {"id": "locata", "provider": "operator_import", "local_path": "LOCATA", "usage_class": "conditional"},
            {"id": "mimii", "provider": "operator_import", "local_path": "MIMII", "usage_class": "conditional"},
            {"id": "mimii-due", "provider": "operator_import", "local_path": "MIMII_DUE", "usage_class": "research-only"},
        ],
    }
    validate_catalog(catalog)
    bad = json.loads(json.dumps(catalog))
    bad["profiles"]["commercial-plus"].append("mimii-due")
    try:
        validate_catalog(bad)
    except ValueError:
        pass
    else:
        raise AssertionError("research-only source leaked into commercial profile")
    bad = json.loads(json.dumps(catalog))
    next(item for item in bad["datasets"] if item["id"] == "locata")["provider"] = "http_archive"
    try:
        validate_catalog(bad)
    except ValueError:
        pass
    else:
        raise AssertionError("unreviewed automatic research download was accepted")
    print("DSP research dataset controller self-test: OK")


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--lock", type=Path, default=DEFAULT_LOCK)
    p.add_argument("--data-root", type=Path, default=Path.home() / "audio-validation-extended")
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("self-test")
    sub.add_parser("validate")
    sub.add_parser("status")
    args = p.parse_args()
    if args.command == "self-test":
        self_test()
        return 0
    catalog = load(args.lock)
    validate_catalog(catalog)
    if args.command == "validate":
        print(json.dumps({"result": "PASS", "profile": PROFILE, "datasets": sorted(EXPECTED_IDS)}, sort_keys=True))
        return 0
    print(json.dumps(materialization_status(catalog, args.data_root), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
