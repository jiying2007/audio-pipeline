#!/usr/bin/env python3
"""Select hash-bound AEC research cases from the upstream training partition.

Never select ICASSP test-set or test-identity recordings for development. Selection
works on LFS pointer trees; build requires the selected real WAVs materialized.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import wave
from pathlib import Path

SOURCE_REVISION = "6c633d0a9d2a143a0e364899b91b06f127315b18"
# Development uses the upstream real TRAINING partition, never the 2022
# competition test set that also feeds hosted/validation-grade evaluation.
TRAIN_ROOT = "datasets/real"
SCENARIOS = (
    "aec-farend-static", "aec-farend-moving",
    "aec-doubletalk-static", "aec-doubletalk-moving",
)
SUFFIXES = {
    "aec-farend-static": "_farend_singletalk",
    "aec-farend-moving": "_farend_singletalk_with_movement",
    "aec-doubletalk-static": "_doubletalk",
    "aec-doubletalk-moving": "_doubletalk_with_movement",
}
CASES_PER_SCENARIO = 2


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def recording_id(path: Path) -> str:
    # Audio IDs may themselves contain underscores; parse the *terminal*
    # scenario label rather than splitting on the first underscore.
    # A recording ID is not proof of a unique speaker or room.
    match = re.fullmatch(
        r"(.+?)_(?:(?:farend|nearend)[_-]singletalk|doubletalk|sweep)"
        r"(?:[_-]with[_-]movement)?_mic\.wav",
        path.name,
    )
    if match is None:
        raise ValueError(f"unrecognized AEC mic filename; cannot prove isolation: {path}")
    return match.group(1)


def classify(path: Path) -> str | None:
    return next((name for name, suffix in SUFFIXES.items()
                 if path.name.endswith(suffix + "_mic.wav")), None)


TEST_INVENTORY_SHA256 = "3b6df275c6f874b9980890a94d7f610f1aaea2bf404f666a319c9d9c8d04f385"


def _load_test_inventory() -> dict:
    # Trusted, reviewed metadata shipped with this tool, not caller-supplied.
    path = Path(__file__).with_name("aec_test_inventory.json")
    if sha256(path) != TEST_INVENTORY_SHA256:
        raise ValueError("AEC trusted test inventory digest mismatch")
    inventory = json.loads(path.read_text(encoding="utf-8"))
    if inventory["source_revision"] != SOURCE_REVISION:
        raise ValueError("AEC trusted test inventory revision mismatch")
    return inventory


def excluded_test_ids(source_root: Path) -> set[str]:
    # Bind the *complete* namespace, including non-mic files, to the seven
    # upstream trees. WAV/LFS pointer contents are intentionally not read:
    # exclusion depends on recording names, not blind/test audio inspection.
    inventory = _load_test_inventory()
    datasets = source_root / "datasets"
    expected = inventory["roots"]
    actual = {p.name for p in datasets.glob("*test_set*")}
    if datasets.is_symlink() or actual != set(expected):
        raise ValueError("AEC complete test partition root inventory mismatch")
    forbidden: set[str] = set()
    for name, bound in expected.items():
        root = datasets / name
        if root.is_symlink() or not root.is_dir():
            raise ValueError("AEC test partition must be a real directory")
        files = []
        def walk_error(error):
            raise error
        for directory, dirs, names in os.walk(root, followlinks=False, onerror=walk_error):
            for child in dirs + names:
                path = Path(directory) / child
                if path.is_symlink():
                    raise ValueError("AEC test inventory symlink forbidden")
            for child in names:
                path = Path(directory) / child
                if not path.is_file():
                    raise ValueError("AEC test inventory non-regular file forbidden")
                files.append(path.relative_to(root).as_posix())
        digest = hashlib.sha256(("\n".join(sorted(files)) + "\n").encode("utf-8")).hexdigest()
        if len(files) != bound["file_count"] or digest != bound["paths_sha256"]:
            raise ValueError("AEC complete test partition file inventory mismatch: " + name)
        forbidden.update(recording_id(Path(path)) for path in files if path.endswith("_mic.wav"))
    return forbidden


def select(source_root: Path) -> dict:
    root = source_root / TRAIN_ROOT
    if not root.is_dir():
        raise FileNotFoundError(root)
    forbidden = excluded_test_ids(source_root)
    groups = {name: [] for name in SCENARIOS}
    for mic in sorted(root.glob("*_mic.wav")):
        scenario = classify(mic)
        if scenario is None:
            continue
        render = mic.with_name(mic.name[:-8] + "_lpb.wav")
        if render.is_file():
            groups[scenario].append((mic, render))
    cases = []
    used_ids: set[str] = set()
    for scenario in SCENARIOS:
        count = 0
        for mic, render in groups[scenario]:
            identity = recording_id(mic)
            if identity in forbidden or identity in used_ids:
                continue
            cases.append({
                "id": f"{scenario}-{count}", "scenario": scenario,
                "source_id": identity,
                "mic": mic.relative_to(source_root).as_posix(),
                "render": render.relative_to(source_root).as_posix(),
                "movement": scenario.endswith("moving"),
                "doubletalk": "doubletalk" in scenario,
            })
            used_ids.add(identity)
            count += 1
            if count == CASES_PER_SCENARIO:
                break
        if count != CASES_PER_SCENARIO:
            raise ValueError(f"AEC training development coverage underfilled: {scenario}={count}")
    return {
        "schema_version": 3,
        "test_inventory_sha256": TEST_INVENTORY_SHA256,
        "source_revision": SOURCE_REVISION,
        "source_partition": TRAIN_ROOT,
        "test_recording_ids_excluded": True,
        "cases": cases,
    }


def inspect_wav(path: Path) -> tuple[int, int]:
    with wave.open(str(path), "rb") as w:
        if w.getnchannels() != 1 or w.getsampwidth() != 2 or w.getcomptype() != "NONE":
            raise ValueError(f"unsupported AEC WAV geometry: {path}")
        rate, frames = w.getframerate(), w.getnframes()
    if rate not in {8000, 16000, 24000, 32000, 48000} or frames < rate:
        raise ValueError(f"unsupported AEC WAV rate/duration: {path}")
    return rate, frames


def build(selection_path: Path, source_root: Path, output: Path) -> dict:
    selection = json.loads(selection_path.read_text(encoding="utf-8"))
    if (selection.get("schema_version") != 3 or
        selection.get("test_inventory_sha256") != TEST_INVENTORY_SHA256 or
        selection.get("source_revision") != SOURCE_REVISION or
        selection.get("source_partition") != TRAIN_ROOT or
        selection.get("test_recording_ids_excluded") is not True or
        len(selection.get("cases", [])) != len(SCENARIOS) * CASES_PER_SCENARIO):
        raise ValueError("AEC training research selection authority mismatch")
    forbidden = excluded_test_ids(source_root)
    counts = {name: 0 for name in SCENARIOS}
    used: set[str] = set()
    output.mkdir(parents=True, exist_ok=True)
    (output / "cases").mkdir(exist_ok=True)
    cases = []
    files = []
    for item in selection["cases"]:
        scenario = item.get("scenario")
        if scenario not in counts:
            raise ValueError("unexpected AEC research scenario")
        identity = item.get("source_id")
        if not isinstance(identity, str) or not identity or identity in forbidden or identity in used:
            raise ValueError("AEC development source identity overlaps test/selection")
        if item.get("id") != f"{scenario}-{counts[scenario]}":
            raise ValueError("AEC research case ordering drifted")
        expected_mic = f"{TRAIN_ROOT}/{identity}{SUFFIXES[scenario]}_mic.wav"
        expected_render = f"{TRAIN_ROOT}/{identity}{SUFFIXES[scenario]}_lpb.wav"
        if item.get("mic") != expected_mic or item.get("render") != expected_render:
            raise ValueError("AEC research path is not in training partition")
        if item.get("movement") is not scenario.endswith("moving") or item.get("doubletalk") is not ("doubletalk" in scenario):
            raise ValueError("AEC research scenario dimension drifted")
        used.add(identity)
        counts[scenario] += 1
        mic_src = source_root / expected_mic
        render_src = source_root / expected_render
        mic_rate, mic_frames = inspect_wav(mic_src)
        render_rate, render_frames = inspect_wav(render_src)
        if mic_rate != render_rate:
            raise ValueError("AEC research mic/render rate mismatch")
        directory = output / "cases" / item["id"]
        directory.mkdir(exist_ok=True)
        mic_dst, render_dst = directory / "mic.wav", directory / "render.wav"
        shutil.copyfile(mic_src, mic_dst)
        shutil.copyfile(render_src, render_dst)
        mic_sha, render_sha = sha256(mic_src), sha256(render_src)
        files += [
            {"case_id": item["id"], "role": "mic", "path": expected_mic,
             "sha256": mic_sha, "size": mic_src.stat().st_size, "frames": mic_frames},
            {"case_id": item["id"], "role": "render", "path": expected_render,
             "sha256": render_sha, "size": render_src.stat().st_size, "frames": render_frames},
        ]
        cases.append({
            "case_id": item["id"], "split": "development", "scenario": scenario,
            "sample_rate_hz": mic_rate, "mic_channels": 1,
            "mic_audio": str(mic_dst.relative_to(output)),
            "render_audio": str(render_dst.relative_to(output)),
            "clean_near_audio": None, "echo_audio": None, "vad_labels": None,
            "processor_profile": "default", "control": {},
            "expected": {"max_output_clip_fraction": 0.02,
                         "max_output_dc_offset_dbfs": -20.0,
                         "max_output_rms_delta_db": 6.0},
            "dimensions": {"movement": item["movement"], "doubletalk": item["doubletalk"]},
            "source": {
                "dataset_id": "microsoft-aec-challenge",
                "source_revision": SOURCE_REVISION,
                "source_partition": TRAIN_ROOT,
                "recording_id": identity,
                "mic_sha256": mic_sha,
                "render_sha256": render_sha,
            },
        })
    if any(value != CASES_PER_SCENARIO for value in counts.values()):
        raise ValueError(f"AEC research scenario balance drifted: {counts}")
    manifest = {
        "schema_version": 2,
        "source_repository": "microsoft/AEC-Challenge",
        "source_revision": SOURCE_REVISION,
        "source_partition": TRAIN_ROOT,
        "selection_sha256": sha256(selection_path),
        "test_inventory_sha256": TEST_INVENTORY_SHA256,
        "files": files,
    }
    manifest_path = output / "source-manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    corpus = {
        "schema_version": 1,
        "corpus_id": "aec-real-research-v2",
        "tier": "research-validation",
        "generator": {"name": "build_aec_research_corpus.py", "version": 2},
        "sources": ["microsoft-aec-challenge"],
        "sealed_data": True, "research_only": True,
        "source_manifest_sha256": sha256(manifest_path),
        "cases": cases,
    }
    corpus_path = output / "corpus.json"
    corpus_path.write_text(json.dumps(corpus, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {"corpus": str(corpus_path), "manifest": str(manifest_path),
            "cases": len(cases), "scenarios": counts}


def self_test() -> None:
    import tempfile
    from unittest.mock import patch
    fixture_inventory = {"roots": {"test_set_icassp2022": {"file_count": 1,
        "paths_sha256": hashlib.sha256(b"doubletalk/fixture00_doubletalk_mic.wav\n").hexdigest()}}}
    with patch(__name__ + "._load_test_inventory", return_value=fixture_inventory), tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        train = root / TRAIN_ROOT
        test = root / "datasets/test_set_icassp2022/doubletalk"
        train.mkdir(parents=True)
        test.mkdir(parents=True)
        for index, scenario in enumerate(SCENARIOS):
            for j in range(3):
                identity = f"fixture{index}{j}"
                name = identity + SUFFIXES[scenario]
                (train / (name + "_mic.wav")).touch()
                (train / (name + "_lpb.wav")).touch()
        # The first candidate's GUID is also present in the test partition.
        (test / ("fixture00_doubletalk_mic.wav")).touch()
        assert recording_id(Path("sample_with_underscore_doubletalk_mic.wav")) == "sample_with_underscore"
        selected = select(root)
        assert len(selected["cases"]) == 8
        assert selected["source_partition"] == TRAIN_ROOT
        ids = [c["source_id"] for c in selected["cases"]]
        assert len(set(ids)) == 8 and "fixture00" not in ids
        assert {c["scenario"] for c in selected["cases"]} == set(SCENARIOS)
        assert all(c["mic"].startswith(TRAIN_ROOT + "/") for c in selected["cases"])
        # A future malformed selection must not re-admit a test-set path.
        selection_path = root / "selection.json"
        broken = json.loads(json.dumps(selected))
        broken["cases"][0]["mic"] = (
            "datasets/test_set_icassp2022/doubletalk/fixture00_doubletalk_mic.wav"
        )
        selection_path.write_text(json.dumps(broken), encoding="utf-8")
        try:
            build(selection_path, root, root / "out")
        except ValueError:
            pass
        else:
            raise AssertionError("AEC test partition was accepted for development")
        missing = root / "missing"
        missing.mkdir()
        (missing / "datasets/real").mkdir(parents=True)
        try:
            select(missing)
        except ValueError:
            pass
        else:
            raise AssertionError("missing test-set inventory silently bypassed overlap check")
    print("AEC research corpus builder self-test: OK")


def main() -> int:
    p = argparse.ArgumentParser(); sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("self-test")
    s = sub.add_parser("select"); s.add_argument("--source-root", type=Path, required=True); s.add_argument("--output", type=Path, required=True)
    b = sub.add_parser("build"); b.add_argument("--selection", type=Path, required=True); b.add_argument("--source-root", type=Path, required=True); b.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    if args.command == "self-test": self_test(); return 0
    if args.command == "select":
        value = select(args.source_root); args.output.parent.mkdir(parents=True, exist_ok=True); args.output.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"); print(json.dumps({"selection": str(args.output), "cases": len(value["cases"])}, sort_keys=True)); return 0
    print(json.dumps(build(args.selection, args.source_root, args.output), sort_keys=True)); return 0


if __name__ == "__main__": raise SystemExit(main())
