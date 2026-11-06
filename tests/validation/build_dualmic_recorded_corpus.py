#!/usr/bin/env python3
"""Frozen recorded-speech C2 corpus; exact admitted bytes, no model selection."""
from __future__ import annotations

import argparse
import array
import copy
import hashlib
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
for directory in (ROOT / "validation/tools", ROOT / "tests/validation",
                  ROOT / "tests/validation/frontend_evolution"):
    if str(directory) not in sys.path:
        sys.path.insert(0, str(directory))

from build_validation_corpus import echo_from_render, interleave, mix, scale
from build_quality_validation_corpus import fractional_delay, physical_tdoa_samples
from contracts import load_json, require
from speech_spatial import source_check
from run_validation_engine import sha256_file

EXPERIMENT = "FE-C2-RECORDED-SPEECH-DUAL-USE-V1"
PAIRS = ((84, 174), (251, 422), (652, 777), (1272, 1462))
PROFILES = ("call", "assistant")
SCENARIOS = ("near-only", "silent-render", "far-only", "doubletalk-nominal",
             "doubletalk-weak", "path-change", "render-gap")
RATE, FRAMES, SAMPLES, SOURCE_SAMPLES = 16000, 600, 96000, 64000
NEAR_START = 24000
SOURCE_FIELDS = ("mic_audio", "render_audio", "clean_near_audio", "echo_audio",
                 "interference_audio")
PLAN = "docs/research/frontend-evolution-v1/DUALMIC_RECORDED_SPEECH_V1_PLAN.zh-CN.md"
ADMISSION = ".github/research/frontend-evolution-v1/speech-admission-v1.json"


def write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n",
                    encoding="utf-8")


def pcm(samples) -> bytes:
    values = array.array("h", samples)
    if sys.byteorder != "little":
        values.byteswap()
    return values.tobytes()


def samples(blob: bytes) -> list[int]:
    require(len(blob) % 2 == 0, "incomplete S16 sample")
    values = array.array("h")
    values.frombytes(blob)
    if sys.byteorder != "little":
        values.byteswap()
    return list(values)


def safe_mix(left: list[int], right: list[int]) -> list[int]:
    require(len(left) == len(right) == SAMPLES, "mixed component length drift")
    require(all(-32768 <= a + b <= 32767 for a, b in zip(left, right)),
            "input clipping forbidden; no reselection or level adjustment")
    return mix(left, right)


def derive(source: Path, record: dict) -> tuple[list[dict], dict[str, bytes], list[dict]]:
    """Deterministic derivative only; callers must first admit original source."""
    windows = {row["speaker"]: row for row in record["speaker_selection"]}
    require(set(windows) == {speaker for pair in PAIRS for speaker in pair},
            "frozen speaker set changed")
    cases, files, scales = [], {}, []
    tdoa = physical_tdoa_samples(35.0, 60.0)
    for pair_index, (near_id, far_id) in enumerate(PAIRS):
        original_near = samples((source / windows[near_id]["window_file"]).read_bytes())
        original_far = samples((source / windows[far_id]["window_file"]).read_bytes())
        require(len(original_near) == len(original_far) == SOURCE_SAMPLES,
                "source window must be exactly four seconds")
        near_peak, far_peak = max(map(abs, original_near)), max(map(abs, original_far))
        require(min(near_peak, far_peak) > 0, "silent admitted window; no reselection")
        gain = 0.45 * 32767 / (near_peak + far_peak)
        near = ([0] * NEAR_START + scale(original_near, gain)
                + [0] * (SAMPLES - NEAR_START - SOURCE_SAMPLES))
        far = scale(original_far, gain) + [0] * (SAMPLES - SOURCE_SAMPLES)
        scales.append({"pair": pair_index, "near_speaker": near_id, "far_speaker": far_id,
                       "original_near_peak": near_peak, "original_far_peak": far_peak,
                       "common_gain": gain, "derived_near_peak": max(map(abs, near)),
                       "derived_far_peak": max(map(abs, far))})
        echo_a = echo_from_render(far, [(320, .52), (640, .21), (1120, .09)])
        echo_b = echo_from_render(far, [(160, .40), (720, .30), (1480, .10)])
        for scenario in SCENARIOS:
            stem = f"pair-{pair_index}-{scenario}"
            clean, render, echo, interference, control = None, None, None, None, {}
            if scenario in ("near-only", "silent-render"):
                clean = near
                left, right = near, near
                if scenario == "silent-render":
                    render = [0] * SAMPLES
            else:
                render, echo = list(far), list(echo_a)
                if scenario == "path-change":
                    echo = echo_a[:48000] + echo_b[48000:]
                    control = {"echo_path_change_frame": 300}
                if scenario == "render-gap":
                    render[48000:48640] = [0] * 640
                    control = {"discontinuity_frame": 300, "discontinuity_flags": 2,
                               "discontinuity_lost_frames": 4}
                left, right = echo, fractional_delay(echo, tdoa)
                if scenario.startswith("doubletalk-"):
                    clean = scale(near, .55) if scenario == "doubletalk-weak" else near
                    left, right = safe_mix(clean, left), safe_mix(clean, right)
                    interference, echo = echo, None
            components = {"mic_audio": ("mic.pcm", interleave(left, right)),
                          "render_audio": ("render.pcm", render),
                          "clean_near_audio": ("clean-near.pcm", clean),
                          "echo_audio": ("echo.pcm", echo),
                          "interference_audio": ("interference.pcm", interference)}
            case = {"case_id": stem, "scenario": scenario, "split": "validation",
                    "sample_rate_hz": RATE, "mic_channels": 2, "vad_labels": None,
                    "processor_profile": "default", "control": control, "expected": {},
                    "source": {"dataset_id": "librispeech-dev-clean-fe03", "source_id": stem},
                    "quality": {"ground_truth": True, "role": "descriptive-regression"},
                    "dimensions": {"pair": pair_index, "near_speaker": near_id,
                        "far_speaker": far_id, "original_role": windows[near_id]["role"],
                        "data_role": "regression", "seconds": 6, "frames": FRAMES,
                        "near_start_sample": NEAR_START, "far_start_sample": 0,
                        "source_window_samples": SOURCE_SAMPLES, "common_gain": gain,
                        "mic_spacing_mm": 35.0, "target_tdoa_samples": 0.0,
                        "echo_tdoa_samples": tdoa, "recorded_speech": True,
                        "real_array_recording": False, "synthetic_propagation": True,
                        "human_vad_labels": False}}
            for field, (name, data) in components.items():
                relative = f"cases/{stem}/{name}" if data is not None else None
                case[field] = relative
                if relative is not None:
                    files[relative] = pcm(data)
            for profile in PROFILES:
                member = copy.deepcopy(case)
                member["case_id"] = f"{stem}-{profile}"
                member["pipeline_profile"] = profile
                member["dimensions"]["pipeline_profile"] = profile
                cases.append(member)
    return cases, files, scales


def expected(source: Path) -> tuple[dict, dict, dict[str, bytes]]:
    require(source.is_dir() and not source.is_symlink(), "source directory/link invalid")
    record = source_check(source)
    cases, generated, scales = derive(source, record)
    all_files = {f"source/{p.relative_to(source).as_posix()}": p.read_bytes()
                 for p in sorted(source.rglob("*")) if p.is_file()}
    all_files.update(generated)
    manifest = {"schema_version": 1, "experiment": EXPERIMENT, "data_role": "regression",
                "source_rights": "LibriSpeech CC-BY-4.0; retain original notices and attribution",
                "source_receipt_sha256": sha256_file(source / "source-receipt.json"),
                "admission_sha256": sha256_file(ROOT / ADMISSION), "scales": scales,
                "files": {name: {"sha256": hashlib.sha256(blob).hexdigest(), "size_bytes": len(blob)}
                          for name, blob in sorted(all_files.items())}}
    manifest_bytes = (json.dumps(manifest, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()
    corpus = {"schema_version": 1, "corpus_id": "dualmic-recorded-regression-v1",
              "tier": "regression", "sealed_data": False, "experiment": EXPERIMENT,
              "quality_decision": "DESCRIPTIVE_ONLY", "sources": ["librispeech-dev-clean-fe03"],
              "generator": {"name": Path(__file__).name, "source_sha256": sha256_file(Path(__file__)),
                            "plan_sha256": sha256_file(ROOT / PLAN), "seconds": 6},
              "source_manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(), "cases": cases}
    return corpus, manifest, all_files


def build(source: Path, output: Path) -> dict:
    require(not output.exists() and not output.is_symlink(), "corpus output must be fresh")
    corpus, manifest, files = expected(source)
    output.mkdir(parents=True)
    for name, blob in files.items():
        path = output / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(blob)
    write_json(output / "source-manifest.json", manifest)
    write_json(output / "corpus.json", corpus)
    return corpus


def verify(corpus_path: Path) -> dict:
    root = corpus_path.parent
    require(corpus_path.name == "corpus.json" and not root.is_symlink(), "invalid corpus path")
    corpus = load_json(corpus_path)
    manifest = load_json(root / "source-manifest.json")
    wanted, wanted_manifest, generated = expected(root / "source")
    require(corpus == wanted and manifest == wanted_manifest, "frozen corpus/source/configuration drift")
    actual = {p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()}
    require(actual == set(generated) | {"corpus.json", "source-manifest.json"},
            "missing or unexpected corpus file")
    require(all(not p.is_symlink() for p in root.rglob("*")), "corpus links forbidden")
    for name, blob in generated.items():
        require((root / name).read_bytes() == blob, "source/derivative bytes changed: " + name)
    return corpus


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    started = time.monotonic()
    if not args.verify:
        if args.source is None:
            parser.error("--source is required for generation")
        build(args.source.resolve(), args.output.resolve())
    corpus = verify(args.output.resolve() / "corpus.json")
    elapsed = time.monotonic() - started
    require(elapsed <= 300, "corpus generation/verification budget exceeded")
    print(json.dumps({"result": "RECORDED_SOURCE_CORPUS_VERIFIED", "cases": len(corpus["cases"]),
                      "elapsed_seconds": elapsed, "quality_decision": "DESCRIPTIVE_ONLY"}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
