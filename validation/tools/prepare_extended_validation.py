#!/usr/bin/env python3
"""Scan, hash and verify caller-materialized extended-real validation sources.

This tool never downloads large corpora. It turns known upstream layouts into a
small normalized manifest whose selected audio files are individually SHA-256
bound. The manifest is the immutable input to build_extended_real_corpus.py.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path

from extended_dataset_lock import (
    catalog_items,
    load_json,
    profile_ids,
    sha256_file,
    validate_catalog,
    validate_manifest,
    verify_manifest_files,
)

AUDIO_SUFFIXES = {".wav", ".flac", ".sph", ".ogg"}
SPEECH_LABEL_TERMS = {
    "speech", "voice", "singing", "conversation", "whisper", "narration",
    "chant", "choir", "vocal", "yell", "scream", "shout", "baby cry",
}


def stable_key(path: Path, root: Path) -> str:
    return hashlib.sha256(path.relative_to(root).as_posix().encode("utf-8")).hexdigest()


def stable_select(paths: list[Path], root: Path, limit: int) -> list[Path]:
    unique = sorted(set(paths), key=lambda path: stable_key(path, root))
    return unique[:max(0, limit)]


def audio_files(root: Path) -> list[Path]:
    return [path for path in root.rglob("*") if path.is_file() and path.suffix.lower() in AUDIO_SUFFIXES]


def file_record(root: Path, path: Path, role: str) -> dict:
    if not path.is_file():
        raise FileNotFoundError(path)
    return {
        "role": role,
        "relative_path": path.relative_to(root).as_posix(),
        "size": path.stat().st_size,
        "sha256": sha256_file(path),
    }


def distance_bucket(distance: float) -> str:
    if distance <= 1.0:
        return "0-1m"
    if distance <= 2.0:
        return "1-2m"
    if distance <= 3.0:
        return "2-3m"
    if distance <= 4.0:
        return "3-4m"
    return "4m+"


def realman_distance_map(root: Path) -> dict[str, float]:
    result: dict[str, float] = {}
    for path in sorted(root.rglob("*source_location.csv")):
        try:
            with path.open("r", encoding="utf-8-sig", newline="") as handle:
                reader = csv.DictReader(handle)
                headers = reader.fieldnames or []
                distance_keys = [name for name in headers if "distance" in name.lower()]
                if not distance_keys:
                    continue
                distance_key = distance_keys[0]
                for row in reader:
                    try:
                        distance = float(row.get(distance_key, ""))
                    except (TypeError, ValueError):
                        continue
                    for name, value in row.items():
                        if name == distance_key or value is None:
                            continue
                        token = Path(str(value).strip()).stem
                        if token:
                            result[token.replace("_CH0", "").replace("_CH1", "")] = distance
        except (OSError, UnicodeDecodeError, csv.Error):
            continue
    return result


def scan_realman(root: Path, limit: int) -> list[dict]:
    candidates = [
        path for path in audio_files(root)
        if path.suffix.lower() == ".flac"
        and "_CH0" in path.stem
        and "ma_noisy_speech" in path.parts
        and any(part in {"val", "test"} for part in path.parts)
    ]
    distances = realman_distance_map(root)
    entries: list[dict] = []
    moving = [path for path in candidates if "moving" in path.parts]
    static = [path for path in candidates if "static" in path.parts]
    moving_limit = max(1, limit // 2)
    selected = stable_select(moving, root, moving_limit) + stable_select(static, root, max(1, limit - moving_limit))
    selected = stable_select(selected, root, limit)
    for mic0 in selected:
        rel = mic0.relative_to(root)
        parts = list(rel.parts)
        index = parts.index("ma_noisy_speech")
        clean_parts = parts[:]
        clean_parts[index] = "dp_speech"
        clean = root.joinpath(*clean_parts)
        clean = clean.with_name(clean.stem.replace("_CH0", "") + clean.suffix)
        if not clean.is_file():
            continue
        mic1 = mic0.with_name(mic0.stem.replace("_CH0", "_CH1") + mic0.suffix)
        files = [file_record(root, mic0, "mic0")]
        if mic1.is_file():
            files.append(file_record(root, mic1, "mic1"))
        files.append(file_record(root, clean, "clean"))
        source_id = mic0.stem.replace("_CH0", "")
        motion = next((part for part in rel.parts if part in {"moving", "static"}), "unknown")
        scene = rel.parts[index + 1] if len(rel.parts) > index + 1 else "unknown"
        split = next((part for part in rel.parts if part in {"val", "test"}), "unknown")
        dimensions: dict[str, object] = {"motion": motion, "scene": scene, "upstream_split": split}
        distance = distances.get(source_id)
        if distance is not None and 0.0 < distance < 100.0:
            dimensions["distance_m"] = round(distance, 3)
            dimensions["distance_bucket"] = distance_bucket(distance)
        entries.append({
            "source_id": source_id,
            "kind": "enhancement-pair",
            "files": files,
            "dimensions": dimensions,
        })
    if not entries:
        raise ValueError("RealMAN scan found no val/test CH0 + direct-path pairs")
    return entries


def scan_but(root: Path, limit: int) -> list[dict]:
    all_audio = audio_files(root)
    rirs = [p for p in all_audio if "rir" in p.as_posix().lower()]
    noises = [p for p in all_audio if any(token in p.as_posix().lower() for token in ("noise", "silence"))]
    half = max(2, limit // 2)
    entries: list[dict] = []
    for kind, paths in (("rir", rirs), ("noise", noises)):
        for path in stable_select(paths, root, half):
            entries.append({
                "source_id": f"{kind}:{path.relative_to(root).as_posix()}",
                "kind": kind,
                "files": [file_record(root, path, kind)],
                "dimensions": {"room": path.parts[-3] if len(path.parts) >= 3 else "unknown"},
            })
    if not any(entry["kind"] == "rir" for entry in entries):
        raise ValueError("BUT ReverbDB scan found no RIR audio")
    if not any(entry["kind"] == "noise" for entry in entries):
        raise ValueError("BUT ReverbDB scan found no room noise/silence audio")
    return entries


def scan_musan(root: Path, limit: int) -> list[dict]:
    entries: list[dict] = []
    per_kind = max(2, limit // 2)
    for kind in ("noise", "music"):
        paths = [p for p in audio_files(root) if kind in p.relative_to(root).parts]
        for path in stable_select(paths, root, per_kind):
            entries.append({
                "source_id": f"{kind}:{path.relative_to(root).as_posix()}",
                "kind": kind,
                "files": [file_record(root, path, kind)],
                "dimensions": {"negative_type": kind},
            })
    if not entries:
        raise ValueError("MUSAN scan found no noise/music audio")
    return entries


def scan_clean(root: Path, limit: int) -> list[dict]:
    selected = stable_select(audio_files(root), root, limit)
    if not selected:
        raise ValueError(f"clean-speech scan found no audio under {root}")
    return [{
        "source_id": f"clean:{path.relative_to(root).as_posix()}",
        "kind": "clean",
        "files": [file_record(root, path, "clean")],
        "dimensions": {},
    } for path in selected]


def scan_voices(root: Path, limit: int) -> list[dict]:
    distant = root / "distant-16k"
    speech_root = distant / "speech"
    distractor_root = distant / "distractors"
    speech = audio_files(speech_root) if speech_root.is_dir() else []
    distractors = audio_files(distractor_root) if distractor_root.is_dir() else []
    entries: list[dict] = []
    for path in stable_select(speech, root, max(2, limit * 3 // 4)):
        rel = path.relative_to(root)
        entries.append({
            "source_id": f"farfield:{rel.as_posix()}",
            "kind": "farfield",
            "files": [file_record(root, path, "farfield")],
            "dimensions": {"room_or_path": rel.parts[2] if len(rel.parts) > 2 else "unknown"},
        })
    for path in stable_select(distractors, root, max(1, limit // 4)):
        entries.append({
            "source_id": f"negative:{path.relative_to(root).as_posix()}",
            "kind": "negative",
            "files": [file_record(root, path, "negative")],
            "dimensions": {"negative_type": "voices-distractor"},
        })
    if not entries:
        raise ValueError("VOiCES scan found no distant-16k speech/distractor audio")
    return entries


def scan_meeting(root: Path, limit: int, dataset_id: str) -> list[dict]:
    candidates = audio_files(root)
    if dataset_id == "ami":
        arrays = [p for p in candidates if "array" in p.name.lower() or "array" in p.as_posix().lower()]
        if arrays:
            candidates = arrays
    selected = stable_select(candidates, root, limit)
    if not selected:
        raise ValueError(f"{dataset_id} scan found no meeting audio")
    return [{
        "source_id": f"meeting:{path.relative_to(root).as_posix()}",
        "kind": "meeting",
        "files": [file_record(root, path, "meeting")],
        "dimensions": {"language": "zh" if dataset_id == "aishell4" else "en"},
    } for path in selected]


def fsd50k_license_allowed(value: str) -> bool:
    normalized = value.lower().replace("_", "-")
    if "noncommercial" in normalized or "by-nc" in normalized or "sampling" in normalized:
        return False
    return "cc0" in normalized or "creative commons 0" in normalized or "attribution" in normalized or "cc-by" in normalized


def fsd50k_non_speech(labels: str) -> bool:
    lowered = labels.lower().replace("_", " ")
    return not any(term in lowered for term in SPEECH_LABEL_TERMS)


def scan_fsd50k(root: Path, limit: int) -> list[dict]:
    info: dict[str, dict] = {}
    for path in sorted(root.rglob("*clips_info_FSD50K.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            info.update({str(key): value for key, value in data.items() if isinstance(value, dict)})
    labels: dict[str, str] = {}
    for path in sorted(root.rglob("*.csv")):
        if path.name not in {"dev.csv", "eval.csv"}:
            continue
        with path.open("r", encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle):
                if row.get("fname"):
                    labels[str(row["fname"])] = str(row.get("labels", ""))
    candidates: list[Path] = []
    for path in audio_files(root):
        key = path.stem
        metadata = info.get(key, {})
        license_text = str(metadata.get("license", metadata.get("license_name", "")))
        if not license_text or not fsd50k_license_allowed(license_text):
            continue
        if not fsd50k_non_speech(labels.get(key, "")):
            continue
        candidates.append(path)
    selected = stable_select(candidates, root, limit)
    if not selected:
        raise ValueError("FSD50K scan found no CC0/CC-BY non-speech clips; metadata/audio may be incomplete")
    entries = []
    for path in selected:
        key = path.stem
        metadata = info.get(key, {})
        entries.append({
            "source_id": f"fsd50k:{key}",
            "kind": "negative",
            "files": [file_record(root, path, "negative")],
            "dimensions": {
                "labels": labels.get(key, ""),
                "clip_license": str(metadata.get("license", metadata.get("license_name", ""))),
            },
        })
    return entries


def scan_wham(root: Path, limit: int) -> list[dict]:
    selected = stable_select(audio_files(root), root, limit)
    if not selected:
        raise ValueError("WHAM scan found no audio")
    return [{
        "source_id": f"wham:{path.relative_to(root).as_posix()}",
        "kind": "negative",
        "files": [file_record(root, path, "negative")],
        "dimensions": {"research_only": True},
    } for path in selected]


def scan_dataset(dataset_id: str, root: Path, limit: int) -> list[dict]:
    if not root.is_dir():
        raise FileNotFoundError(root)
    if dataset_id == "realman":
        return scan_realman(root, limit)
    if dataset_id == "but-reverbdb":
        return scan_but(root, limit)
    if dataset_id == "musan":
        return scan_musan(root, limit)
    if dataset_id == "openslr-slr31":
        return scan_clean(root, limit)
    if dataset_id == "voices":
        return scan_voices(root, limit)
    if dataset_id in {"ami", "icsi", "aishell4"}:
        return scan_meeting(root, limit, dataset_id)
    if dataset_id == "fsd50k":
        return scan_fsd50k(root, limit)
    if dataset_id == "wham":
        return scan_wham(root, limit)
    raise ValueError(f"no extended dataset scanner for {dataset_id}")


def build_manifest(catalog_path: Path, data_root: Path, profile: str, limit: int) -> dict:
    catalog = load_json(catalog_path)
    validate_catalog(catalog)
    by_id = catalog_items(catalog)
    datasets = []
    for dataset_id in profile_ids(catalog, profile):
        item = by_id[dataset_id]
        root = data_root / item["local_path"]
        entries = scan_dataset(dataset_id, root, limit)
        datasets.append({
            "id": dataset_id,
            "usage_class": item["usage_class"],
            "license": item["license"],
            "attribution": item["attribution"],
            "entries": entries,
        })
    return {
        "schema_version": 1,
        "profile": profile,
        "catalog_sha256": sha256_file(catalog_path),
        "datasets": datasets,
    }


def self_test() -> None:
    assert distance_bucket(0.8) == "0-1m"
    assert distance_bucket(2.5) == "2-3m"
    assert distance_bucket(5.0) == "4m+"
    assert fsd50k_license_allowed("CC0")
    assert fsd50k_license_allowed("Attribution 4.0")
    assert not fsd50k_license_allowed("CC-BY-NC")
    assert fsd50k_non_speech("Door,Domestic sounds")
    assert not fsd50k_non_speech("Speech,Conversation")
    paths = [Path("/tmp/x/b.wav"), Path("/tmp/x/a.wav")]
    first = [p.name for p in stable_select(paths, Path("/tmp/x"), 2)]
    second = [p.name for p in stable_select(list(reversed(paths)), Path("/tmp/x"), 2)]
    assert first == second
    print("extended validation source scanner self-test: OK")


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    scan = sub.add_parser("scan")
    scan.add_argument("--catalog", type=Path, default=Path("validation/extended.datasets.lock.json"))
    scan.add_argument("--data-root", type=Path, required=True)
    scan.add_argument("--profile", choices=("commercial-core", "commercial-plus", "research"), required=True)
    scan.add_argument("--limit-per-dataset", type=int, default=24)
    scan.add_argument("--output", type=Path, required=True)
    verify = sub.add_parser("verify")
    verify.add_argument("--catalog", type=Path, default=Path("validation/extended.datasets.lock.json"))
    verify.add_argument("--data-root", type=Path, required=True)
    verify.add_argument("--manifest", type=Path, required=True)
    sub.add_parser("self-test")
    args = parser.parse_args()
    if args.command == "self-test":
        self_test()
        return 0
    if args.command == "scan":
        if args.limit_per_dataset < 2:
            raise SystemExit("limit-per-dataset must be >= 2")
        manifest = build_manifest(args.catalog, args.data_root, args.profile, args.limit_per_dataset)
        catalog = load_json(args.catalog)
        validate_manifest(manifest, catalog, args.catalog)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        verified = verify_manifest_files(manifest, catalog, args.data_root)
        print(json.dumps({
            "manifest": str(args.output),
            "manifest_sha256": sha256_file(args.output),
            "datasets": len(manifest["datasets"]),
            **verified,
        }, sort_keys=True))
        return 0
    catalog = load_json(args.catalog)
    manifest = load_json(args.manifest)
    validate_manifest(manifest, catalog, args.catalog)
    result = verify_manifest_files(manifest, catalog, args.data_root)
    result["manifest_sha256"] = sha256_file(args.manifest)
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
