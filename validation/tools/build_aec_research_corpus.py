#!/usr/bin/env python3
"""Select and seal an 8-case Microsoft AEC Challenge research corpus.

Selection can run on Git LFS pointer trees. Build must run after only the selected
mic/render files are materialized and records their actual PCM SHA-256/size.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import wave
from pathlib import Path, PurePosixPath

SOURCE_REVISION = "6c633d0a9d2a143a0e364899b91b06f127315b18"
ROOTS = {
    "aec-farend-singletalk": "datasets/test_set_icassp2022/farend-singletalk",
    "aec-doubletalk": "datasets/test_set_icassp2022/doubletalk",
}
SCENARIOS = (
    "aec-farend-static", "aec-farend-moving",
    "aec-doubletalk-static", "aec-doubletalk-moving",
)
CASES_PER_SCENARIO = 2


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def classify(directory: str, path: Path) -> str:
    moving = "with-movement" in path.name.lower()
    if directory == ROOTS["aec-farend-singletalk"]:
        return "aec-farend-moving" if moving else "aec-farend-static"
    return "aec-doubletalk-moving" if moving else "aec-doubletalk-static"


def _safe_component(value: object) -> str:
    if (not isinstance(value, str) or not value or value in {".", ".."} or
        any(c in value for c in ("/", "\\")) or
        any(ord(c) < 32 or ord(c) == 127 for c in value)):
        raise ValueError("AEC case identity is not a safe filename component")
    return value


def _source_path(source_root: Path, relative: object, *, directory: bool = False) -> Path:
    if not isinstance(relative, str) or "\\" in relative:
        raise ValueError("AEC source path must be canonical relative POSIX")
    path = PurePosixPath(relative)
    if (path.is_absolute() or path.as_posix() != relative or
        any(part in {".", ".."} for part in path.parts) or
        any(ord(c) < 32 or ord(c) == 127 for c in relative)):
        raise ValueError("AEC source path must be canonical relative POSIX")
    allowed = relative in ROOTS.values() if directory else str(path.parent) in ROOTS.values()
    if not allowed:
        raise ValueError("AEC source path is outside the existing source directories")
    root = source_root.resolve()
    current = root
    for part in path.parts:
        current = current / part
        if current.is_symlink():
            raise ValueError("AEC source path must not traverse symbolic links")
    try:
        current.resolve().relative_to(root)
    except ValueError as error:
        raise ValueError("AEC source path escapes the source tree") from error
    return current


def select(source_root: Path) -> dict:
    source_root = source_root.resolve()
    groups = {name: [] for name in SCENARIOS}
    for directory in ROOTS.values():
        root = _source_path(source_root, directory, directory=True)
        if not root.is_dir(): raise FileNotFoundError(root)
        for mic in sorted(root.glob("*_mic.wav")):
            render = mic.with_name(mic.name[:-8] + "_lpb.wav")
            if not render.exists(): continue
            _source_path(source_root, mic.relative_to(source_root).as_posix())
            _source_path(source_root, render.relative_to(source_root).as_posix())
            scenario = classify(directory, mic)
            groups[scenario].append((mic, render))
    cases = []
    for scenario in SCENARIOS:
        pairs = groups[scenario]
        if len(pairs) < CASES_PER_SCENARIO:
            raise ValueError(f"AEC research coverage underfilled: {scenario}={len(pairs)}")
        for index, (mic, render) in enumerate(pairs[:CASES_PER_SCENARIO]):
            cases.append({
                "id": f"{scenario}-{index}", "scenario": scenario,
                "mic": mic.relative_to(source_root).as_posix(),
                "render": render.relative_to(source_root).as_posix(),
                "movement": scenario.endswith("moving"),
                "doubletalk": "doubletalk" in scenario,
            })
    return {"schema_version": 1, "source_revision": SOURCE_REVISION, "cases": cases}


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
    if selection.get("source_revision") != SOURCE_REVISION or len(selection.get("cases", [])) != 8:
        raise ValueError("AEC research selection authority mismatch")
    # Validate all selected paths before opening audio or creating outputs.
    sources = []
    for item in selection["cases"]:
        _safe_component(item["id"])
        sources.append((_source_path(source_root, item["mic"]),
                        _source_path(source_root, item["render"])))
    counts = {name: 0 for name in SCENARIOS}
    output.mkdir(parents=True, exist_ok=True); (output / "cases").mkdir(exist_ok=True)
    cases = []; files = []
    for item, (mic_src, render_src) in zip(selection["cases"], sources):
        scenario = item["scenario"]
        if scenario not in counts: raise ValueError("unexpected AEC research scenario")
        counts[scenario] += 1
        mic_rate, mic_frames = inspect_wav(mic_src); render_rate, render_frames = inspect_wav(render_src)
        if mic_rate != render_rate: raise ValueError("AEC research mic/render rate mismatch")
        directory = output / "cases" / item["id"]; directory.mkdir(exist_ok=True)
        mic_dst, render_dst = directory / "mic.wav", directory / "render.wav"
        shutil.copyfile(mic_src, mic_dst); shutil.copyfile(render_src, render_dst)
        mic_sha, render_sha = sha256(mic_src), sha256(render_src)
        files += [
            {"case_id": item["id"], "role": "mic", "path": item["mic"], "sha256": mic_sha, "size": mic_src.stat().st_size, "frames": mic_frames},
            {"case_id": item["id"], "role": "render", "path": item["render"], "sha256": render_sha, "size": render_src.stat().st_size, "frames": render_frames},
        ]
        cases.append({
            "case_id": item["id"], "split": "development", "scenario": scenario,
            "sample_rate_hz": mic_rate, "mic_channels": 1,
            "mic_audio": str(mic_dst.relative_to(output)), "render_audio": str(render_dst.relative_to(output)),
            "clean_near_audio": None, "echo_audio": None, "vad_labels": None,
            "processor_profile": "default", "control": {},
            "expected": {"max_output_clip_fraction": 0.02, "max_output_dc_offset_dbfs": -20.0, "max_output_rms_delta_db": 6.0},
            "dimensions": {"movement": item["movement"], "doubletalk": item["doubletalk"]},
            "source": {"dataset_id": "microsoft-aec-challenge", "source_revision": SOURCE_REVISION, "mic_sha256": mic_sha, "render_sha256": render_sha},
        })
    if any(value != CASES_PER_SCENARIO for value in counts.values()):
        raise ValueError(f"AEC research scenario balance drifted: {counts}")
    manifest = {"schema_version": 1, "source_repository": "microsoft/AEC-Challenge", "source_revision": SOURCE_REVISION, "files": files}
    manifest_path = output / "source-manifest.json"; manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    corpus = {"schema_version": 1, "corpus_id": "aec-real-research-v1", "tier": "research-validation", "generator": {"name": "build_aec_research_corpus.py", "version": 1}, "sources": ["microsoft-aec-challenge"], "sealed_data": True, "research_only": True, "source_manifest_sha256": sha256(manifest_path), "cases": cases}
    corpus_path = output / "corpus.json"; corpus_path.write_text(json.dumps(corpus, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {"corpus": str(corpus_path), "manifest": str(manifest_path), "cases": len(cases), "scenarios": counts}


def self_test() -> None:
    assert len(SCENARIOS) * CASES_PER_SCENARIO == 8
    assert classify(ROOTS["aec-farend-singletalk"], Path("x_farend-singletalk-with-movement_mic.wav")) == "aec-farend-moving"
    assert classify(ROOTS["aec-doubletalk"], Path("x_doubletalk_mic.wav")) == "aec-doubletalk-static"
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
