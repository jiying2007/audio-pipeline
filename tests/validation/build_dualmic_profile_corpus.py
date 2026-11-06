#!/usr/bin/env python3
"""Frozen 42-case dual-mic preset regression, using existing signal functions."""
from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
for directory in (ROOT / "validation/tools", ROOT / "tests/validation"):
    if str(directory) not in sys.path:
        sys.path.insert(0, str(directory))

from build_validation_corpus import (FRAME, RATE, add_case, echo_from_render,
                                    interleave, mix, render_signal, scale,
                                    speech_like, write_pcm)
from build_quality_validation_corpus import fractional_delay, physical_tdoa_samples
from run_validation_engine import sha256_file

EXPERIMENT = "FE-C2-DUAL-USE-PROFILE-REPLAY-V1"
SEEDS = (5107, 6107, 7107)
PROFILES = ("call", "assistant")
SCENARIOS = ("near-only", "silent-render", "far-only", "doubletalk-nominal",
             "doubletalk-weak", "path-change", "render-gap")
SECONDS, FRAMES, SAMPLES = 6, 600, 96000
SOURCE_FIELDS = ("mic_audio", "render_audio", "clean_near_audio", "echo_audio",
                 "vad_labels", "interference_audio")


def build(output: Path) -> dict:
    if output.exists() and any(output.iterdir()):
        raise ValueError("corpus output must be new or empty; preserve prior evidence")
    output.mkdir(parents=True, exist_ok=True)
    cases = []
    tdoa = physical_tdoa_samples(35.0, 60.0)
    if not 0.0 < tdoa <= physical_tdoa_samples(35.0, 90.0) < 2.0:
        raise ValueError("physical two-mic delay bound drifted")
    for seed in SEEDS:
        clean, labels = speech_like(FRAMES, seed + 1,
                                   [(0.55, 1.80), (2.30, 3.90), (4.30, 5.40)],
                                   amplitude=8500.0)
        render = render_signal(SAMPLES, seed + 4)
        echo_a = echo_from_render(render, [(320, 0.52), (640, 0.21), (1120, 0.09)])
        echo_b = echo_from_render(render, [(160, 0.40), (720, 0.30), (1480, 0.10)])
        for scenario in SCENARIOS:
            source_id = f"seed-{seed}-{scenario}"
            near = None
            ref = None
            echo = None
            control = {}
            if scenario in ("near-only", "silent-render"):
                near = clean
                left, right = list(clean), list(clean)
                if scenario == "silent-render":
                    ref = [0] * SAMPLES
            else:
                ref = list(render)
                echo = list(echo_a)
                if scenario == "path-change":
                    echo = echo_a[:SAMPLES // 2] + echo_b[SAMPLES // 2:]
                    control = {"echo_path_change_frame": 300}
                if scenario == "render-gap":
                    # The physical echo remains present while four reference
                    # frames are unavailable to the processor.
                    ref[300 * FRAME:304 * FRAME] = [0] * (4 * FRAME)
                    control = {"discontinuity_frame": 300,
                               "discontinuity_flags": 2,
                               "discontinuity_lost_frames": 4}
                right_echo = fractional_delay(echo, tdoa)
                left, right = echo, right_echo
                if scenario.startswith("doubletalk-"):
                    near = scale(clean, 0.55 if scenario == "doubletalk-weak" else 1.0)
                    left, right = mix(near, echo), mix(near, right_echo)
            generated = []
            add_case(generated, output, source_id, scenario,
                     interleave(left, right), 2, clean=near, render=ref,
                     echo=echo if near is None else None,
                     labels=labels if near is not None else None,
                     control=control)
            case = generated[0]
            if near is not None and echo is not None:
                interference = output / "cases" / source_id / "interference.pcm"
                write_pcm(interference, echo)
                case["interference_audio"] = str(interference.relative_to(output))
            # Keep the canonical schema's validation split (as add_case does);
            # the corpus tier and explicit data_role remain regression only.
            case["quality"] = {"ground_truth": True, "role": "descriptive-regression"}
            case["dimensions"] = {
                "seed": seed, "data_role": "regression", "seconds": SECONDS,
                "frames": FRAMES, "mic_spacing_mm": 35.0,
                "target_tdoa_samples": 0.0, "echo_tdoa_samples": tdoa,
                "synthetic_engineering_signal": True,
            }
            for profile in PROFILES:
                member = copy.deepcopy(case)
                member["case_id"] = f"{source_id}-{profile}"
                member["pipeline_profile"] = profile
                member["dimensions"]["pipeline_profile"] = profile
                cases.append(member)
    files = {}
    for case in cases:
        for field in SOURCE_FIELDS:
            relative = case.get(field)
            if relative is not None and relative not in files:
                path = output / relative
                files[relative] = {"sha256": sha256_file(path), "size_bytes": path.stat().st_size}
    manifest = {"schema_version": 1, "experiment": EXPERIMENT,
                "data_role": "regression", "source_rights": "first-party deterministic engineering signals",
                "files": files}
    manifest_path = output / "source-manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    corpus = {
        "schema_version": 1, "corpus_id": "dualmic-profile-regression-v1",
        "tier": "regression", "sealed_data": False,
        "experiment": EXPERIMENT, "quality_decision": "DESCRIPTIVE_ONLY",
        "generator": {"name": Path(__file__).name, "seeds": list(SEEDS),
                      "seconds": SECONDS, "source_sha256": sha256_file(Path(__file__))},
        "sources": ["deterministic-generator"],
        "source_manifest_sha256": sha256_file(manifest_path), "cases": cases,
    }
    (output / "corpus.json").write_text(json.dumps(corpus, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return corpus


def verify(corpus_path: Path) -> dict:
    corpus = json.loads(corpus_path.read_text(encoding="utf-8"))
    expected_ids = {f"seed-{seed}-{scenario}-{profile}"
                    for seed in SEEDS for scenario in SCENARIOS for profile in PROFILES}
    cases = corpus.get("cases", [])
    if (len(cases) != len(expected_ids) or {case.get("case_id") for case in cases} != expected_ids
            or corpus.get("tier") != "regression" or corpus.get("experiment") != EXPERIMENT
            or corpus.get("quality_decision") != "DESCRIPTIVE_ONLY"):
        raise ValueError("frozen matrix identity/coverage drifted")
    if corpus.get("generator") != {
            "name": Path(__file__).name, "seeds": list(SEEDS), "seconds": SECONDS,
            "source_sha256": sha256_file(Path(__file__))}:
        raise ValueError("frozen generator identity drifted")
    manifest_path = corpus_path.parent / "source-manifest.json"
    if sha256_file(manifest_path) != corpus.get("source_manifest_sha256"):
        raise ValueError("source manifest hash mismatch")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    referenced = set()
    by_id = {case["case_id"]: case for case in cases}
    for case in cases:
        if (case.get("sample_rate_hz") != RATE or case.get("mic_channels") != 2
                or case.get("split") != "validation" or case.get("expected") != {}
                or case.get("processor_profile") != "default"
                or case.get("pipeline_profile") not in PROFILES):
            raise ValueError(f"frozen case configuration drifted: {case['case_id']}")
        dimensions = case.get("dimensions", {})
        if (dimensions.get("pipeline_profile") != case["pipeline_profile"]
                or dimensions.get("seed") not in SEEDS or dimensions.get("frames") != FRAMES
                or dimensions.get("data_role") != "regression"):
            raise ValueError("frozen dimensions drifted")
        if case["case_id"] != f"seed-{dimensions['seed']}-{case['scenario']}-{case['pipeline_profile']}":
            raise ValueError("case identity does not match its configuration")
        expected_control = ({"echo_path_change_frame": 300} if case["scenario"] == "path-change"
                            else {"discontinuity_frame": 300, "discontinuity_flags": 2,
                                  "discontinuity_lost_frames": 4} if case["scenario"] == "render-gap" else {})
        if case.get("control") != expected_control:
            raise ValueError("frozen event schedule drifted")
        for field in SOURCE_FIELDS:
            relative = case.get(field)
            if relative is None:
                continue
            path = corpus_path.parent / relative
            if path.resolve().parent.parent.parent != corpus_path.parent.resolve() or Path(relative).is_absolute():
                raise ValueError("source path escaped the corpus")
            referenced.add(relative)
            binding = manifest["files"].get(relative)
            if binding is None or path.stat().st_size != binding["size_bytes"] or sha256_file(path) != binding["sha256"]:
                raise ValueError(f"source identity mismatch: {relative}")
            expected_size = FRAMES * 2 if field == "vad_labels" else SAMPLES * 2 * (2 if field == "mic_audio" else 1)
            if path.stat().st_size != expected_size:
                raise ValueError(f"source sample/frame count mismatch: {relative}")
        other_profile = "assistant" if case["pipeline_profile"] == "call" else "call"
        partner = by_id[f"seed-{dimensions['seed']}-{case['scenario']}-{other_profile}"]
        if any(case.get(field) != partner.get(field) for field in SOURCE_FIELDS):
            raise ValueError("profile pair does not share identical source files")
    if referenced != set(manifest["files"]):
        raise ValueError("source manifest coverage mismatch")
    return corpus


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    corpus = build(args.output)
    verify(args.output / "corpus.json")
    print(json.dumps({"corpus": str(args.output / "corpus.json"), "cases": len(corpus["cases"]),
                      "authority": "regression-descriptive-only"}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
