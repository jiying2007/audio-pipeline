#!/usr/bin/env python3
"""Build a tiny hash-pinned real AEC corpus for GitHub-hosted validation."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import wave
from collections import Counter
from pathlib import Path

SCHEMA_VERSION = 1
SOURCE_REPOSITORY = "microsoft/AEC-Challenge"
SOURCE_REVISION = "6c633d0a9d2a143a0e364899b91b06f127315b18"
USAGE_CLASS = "validation-only-composite-upstream-terms"
SUPPORTED_RATES = {8000, 16000, 24000, 32000, 48000}
ALLOWED_PREFIX = "datasets/test_set_icassp2022/farend-singletalk/"
REQUIRED_SCENARIOS = {"aec-farend-singletalk", "aec-farend-singletalk-movement"}
REQUIRED_CASES_PER_SCENARIO = 2


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def safe_rel(value: str) -> bool:
    path = Path(value)
    return bool(value) and not path.is_absolute() and ".." not in path.parts


def validate_lock(lock: dict) -> None:
    if lock.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("hosted AEC lock schema_version must be 1")
    if lock.get("source_repository") != SOURCE_REPOSITORY:
        raise ValueError("hosted AEC source repository drifted")
    if lock.get("source_revision") != SOURCE_REVISION:
        raise ValueError("hosted AEC source revision drifted")
    if lock.get("usage_class") != USAGE_CLASS:
        raise ValueError("hosted AEC usage class drifted")
    cases = lock.get("cases")
    required_total = len(REQUIRED_SCENARIOS) * REQUIRED_CASES_PER_SCENARIO
    if not isinstance(cases, list) or len(cases) < required_total:
        raise ValueError(f"hosted AEC lock requires at least {required_total} balanced cases")
    ids: set[str] = set()
    scenarios: set[str] = set()
    movement_values: set[bool] = set()
    scenario_counts: Counter[str] = Counter()
    for case in cases:
        case_id = str(case.get("id", ""))
        scenario = str(case.get("scenario", ""))
        movement = case.get("movement")
        if not case_id or case_id in ids:
            raise ValueError(f"invalid or duplicate hosted AEC case id: {case_id!r}")
        if scenario not in REQUIRED_SCENARIOS or not isinstance(movement, bool):
            raise ValueError(f"invalid hosted AEC dimensions: {case_id}")
        if movement != (scenario == "aec-farend-singletalk-movement"):
            raise ValueError(f"hosted AEC scenario/movement mismatch: {case_id}")
        ids.add(case_id)
        scenarios.add(scenario)
        movement_values.add(movement)
        scenario_counts[scenario] += 1
        for role in ("mic", "render"):
            item = case.get(role)
            if not isinstance(item, dict):
                raise ValueError(f"missing {role} descriptor: {case_id}")
            path = str(item.get("path", ""))
            digest = str(item.get("sha256", ""))
            size = int(item.get("size", 0))
            if not safe_rel(path) or not path.startswith(ALLOWED_PREFIX):
                raise ValueError(f"unsupported hosted AEC path: {path}")
            if re.fullmatch(r"[0-9a-f]{64}", digest) is None or size < 1024:
                raise ValueError(f"invalid hosted AEC integrity record: {case_id}/{role}")
    if scenarios != REQUIRED_SCENARIOS or movement_values != {False, True}:
        raise ValueError("hosted AEC static/movement coverage drifted")
    underfilled = {
        scenario: scenario_counts[scenario]
        for scenario in sorted(REQUIRED_SCENARIOS)
        if scenario_counts[scenario] < REQUIRED_CASES_PER_SCENARIO
    }
    if underfilled:
        raise ValueError(f"hosted AEC scenario coverage is underfilled: {underfilled}")


def load_lock(path: Path) -> dict:
    lock = json.loads(path.read_text(encoding="utf-8"))
    validate_lock(lock)
    return lock


def inspect_wav(path: Path, descriptor: dict) -> tuple[int, int]:
    expected_size = int(descriptor["size"])
    if path.stat().st_size != expected_size:
        raise ValueError(f"hosted AEC size mismatch: {path}: {path.stat().st_size} != {expected_size}")
    actual = sha256_file(path)
    if actual != descriptor["sha256"]:
        raise ValueError(f"hosted AEC SHA-256 mismatch: {path}: {actual}")
    with wave.open(str(path), "rb") as handle:
        channels = handle.getnchannels()
        rate = handle.getframerate()
        width = handle.getsampwidth()
        compression = handle.getcomptype()
        frames = handle.getnframes()
    if channels != 1 or width != 2 or compression != "NONE" or rate not in SUPPORTED_RATES or frames < rate:
        raise ValueError(f"unsupported hosted AEC WAV geometry: {path}")
    return rate, frames


def build(lock_path: Path, source_root: Path, output: Path) -> dict:
    lock = load_lock(lock_path)
    output.mkdir(parents=True, exist_ok=True)
    case_root = output / "cases"
    case_root.mkdir(exist_ok=True)
    cases = []
    manifest_files = []
    for item in lock["cases"]:
        mic_src = source_root / item["mic"]["path"]
        render_src = source_root / item["render"]["path"]
        if not mic_src.is_file() or not render_src.is_file():
            raise ValueError(f"hosted AEC source is not materialized: {item['id']}")
        mic_rate, mic_frames = inspect_wav(mic_src, item["mic"])
        render_rate, render_frames = inspect_wav(render_src, item["render"])
        if mic_rate != render_rate:
            raise ValueError(f"hosted AEC mic/render rate mismatch: {item['id']}")
        destination = case_root / item["id"]
        destination.mkdir(exist_ok=True)
        mic_dst = destination / "mic.wav"
        render_dst = destination / "render.wav"
        shutil.copyfile(mic_src, mic_dst)
        shutil.copyfile(render_src, render_dst)
        cases.append({
            "case_id": item["id"],
            "split": "validation",
            "scenario": item["scenario"],
            "sample_rate_hz": mic_rate,
            "mic_channels": 1,
            "mic_audio": str(mic_dst.relative_to(output)),
            "render_audio": str(render_dst.relative_to(output)),
            "clean_near_audio": None,
            "echo_audio": None,
            "vad_labels": None,
            "processor_profile": "default",
            "control": {},
            "expected": {
                "max_output_clip_fraction": 0.02,
                "max_output_dc_offset_dbfs": -20.0,
                "max_output_rms_delta_db": 0.0
            },
            "dimensions": {
                "movement": item["movement"],
                "source_rate_hz": mic_rate
            },
            "source": {
                "dataset_id": "microsoft-aec-challenge-hosted-real",
                "source_revision": lock["source_revision"],
                "mic_path": item["mic"]["path"],
                "render_path": item["render"]["path"],
                "mic_sha256": item["mic"]["sha256"],
                "render_sha256": item["render"]["sha256"],
                "usage_class": lock["usage_class"]
            }
        })
        manifest_files.extend([
            {"case_id": item["id"], "role": "mic", "path": item["mic"]["path"],
             "sha256": item["mic"]["sha256"], "size": item["mic"]["size"], "frames": mic_frames},
            {"case_id": item["id"], "role": "render", "path": item["render"]["path"],
             "sha256": item["render"]["sha256"], "size": item["render"]["size"], "frames": render_frames},
        ])
    manifest = {
        "schema_version": 1,
        "source_repository": lock["source_repository"],
        "source_revision": lock["source_revision"],
        "usage_class": lock["usage_class"],
        "license": lock["license"],
        "license_evidence": lock["license_evidence"],
        "dataset_lock_sha256": sha256_file(lock_path),
        "files": manifest_files
    }
    manifest_path = output / "source-manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    corpus = {
        "schema_version": 1,
        "corpus_id": "hosted-real-aec-microset-v1",
        "tier": "validation-grade",
        "generator": {"name": "build_hosted_aec_corpus.py", "version": 1},
        "sources": ["microsoft-aec-challenge-hosted-real"],
        "sealed_data": True,
        "dataset_lock_sha256": sha256_file(lock_path),
        "source_manifest_sha256": sha256_file(manifest_path),
        "cases": cases
    }
    corpus_path = output / "corpus.json"
    corpus_path.write_text(json.dumps(corpus, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    result = {
        "corpus": str(corpus_path),
        "source_manifest": str(manifest_path),
        "cases": len(cases),
        "source_revision": lock["source_revision"],
        "rates": sorted({case["sample_rate_hz"] for case in cases})
    }
    print(json.dumps(result, sort_keys=True))
    return result


def self_test() -> None:
    def fixture(case_id: str, scenario: str, movement: bool, digit: str) -> dict:
        return {
            "id": case_id,
            "scenario": scenario,
            "movement": movement,
            "mic": {"path": ALLOWED_PREFIX + f"{case_id}_mic.wav", "sha256": digit * 64, "size": 2048},
            "render": {"path": ALLOWED_PREFIX + f"{case_id}_lpb.wav", "sha256": digit * 64, "size": 2048},
        }

    good = {
        "schema_version": 1,
        "catalog_id": "self-test",
        "source_repository": SOURCE_REPOSITORY,
        "source_revision": SOURCE_REVISION,
        "usage_class": USAGE_CLASS,
        "license": "test",
        "license_evidence": "test",
        "cases": [
            fixture("static-a", "aec-farend-singletalk", False, "0"),
            fixture("static-b", "aec-farend-singletalk", False, "1"),
            fixture("moving-a", "aec-farend-singletalk-movement", True, "2"),
            fixture("moving-b", "aec-farend-singletalk-movement", True, "3"),
        ],
    }
    validate_lock(good)
    bad_revision = json.loads(json.dumps(good))
    bad_revision["source_revision"] = "0" * 40
    try:
        validate_lock(bad_revision)
    except ValueError:
        pass
    else:
        raise AssertionError("hosted AEC revision drift was accepted")
    underfilled = json.loads(json.dumps(good))
    underfilled["cases"].pop()
    try:
        validate_lock(underfilled)
    except ValueError:
        pass
    else:
        raise AssertionError("underfilled hosted AEC coverage was accepted")
    print("hosted AEC corpus builder self-test: OK")


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("self-test")
    validate = sub.add_parser("validate")
    validate.add_argument("--lock", type=Path, default=Path("validation/hosted_aec.datasets.lock.json"))
    build_parser = sub.add_parser("build")
    build_parser.add_argument("--lock", type=Path, default=Path("validation/hosted_aec.datasets.lock.json"))
    build_parser.add_argument("--source-root", type=Path, required=True)
    build_parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "self-test":
        self_test()
        return 0
    if args.command == "validate":
        lock = load_lock(args.lock)
        print(json.dumps({"catalog_id": lock["catalog_id"], "cases": len(lock["cases"]), "source_revision": lock["source_revision"]}, sort_keys=True))
        return 0
    build(args.lock, args.source_root, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
