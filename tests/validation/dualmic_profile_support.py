#!/usr/bin/env python3
"""Explicit CALL/ASSISTANT invocation, reusing the canonical quality evaluator.

The legacy invocation is delegated unchanged when pipeline_profile is absent.
This adapter adds no DSP and no acoustic metric/threshold definitions.
"""
from __future__ import annotations

from dataclasses import replace
import json
import math
from pathlib import Path
import re
import subprocess
import sys
import time
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[2]
for directory in (ROOT / "validation/tools", ROOT / "tests/validation"):
    if str(directory) not in sys.path:
        sys.path.insert(0, str(directory))

import quality_metric_support
import run_validation
import run_validation_engine as engine
import stage_profile_support

PIPELINE_PROFILES = frozenset({"call", "assistant"})
PROCESS_TIMEOUT_SECONDS = 30


def continuity(case: dict, output: Any, trace: list[dict], inputs: dict) -> dict:
    """Check complete continuous output independently of metric truncation."""
    rate, channels = int(case["sample_rate_hz"]), int(case["mic_channels"])
    if rate not in engine.SUPPORTED_RATES or channels not in (1, 2):
        raise ValueError("unsupported PCM geometry")
    frame = rate // 100
    capture_samples = len(inputs["mic"])
    if capture_samples % (channels * frame):
        raise ValueError("capture is not a complete interleaved 10 ms stream")
    expected_samples = capture_samples // channels
    expected_frames = expected_samples // frame
    if len(output) != expected_samples:
        raise ValueError(f"output length mismatch: {len(output)} != {expected_samples}")
    if len(trace) != expected_frames:
        raise ValueError(f"metrics frame count mismatch: {len(trace)} != {expected_frames}")
    for index, row in enumerate(trace):
        if not isinstance(row, dict) or type(row.get("frame")) is not int or row["frame"] != index:
            raise ValueError(f"non-contiguous metrics frame at {index}")
        if any(isinstance(value, float) and not math.isfinite(value) for value in row.values()):
            raise ValueError(f"non-finite metrics at frame {index}")
    return {
        "input_samples_per_channel": expected_samples,
        "output_mono_samples": len(output),
        "frame_samples": frame,
        "capture_frames": expected_frames,
        "metrics_frames": len(trace),
        "frame_indices_contiguous": True,
    }


def case_directory(root: Path, case_id: str) -> Path:
    if not isinstance(case_id, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", case_id):
        raise ValueError("case_id cannot be used as an artifact directory")
    directory = root / case_id
    directory.mkdir(parents=True, exist_ok=False)
    return directory


def build_invoke(original: Callable, *, retain_root: Path | None = None,
                 run_command: Callable = subprocess.run):
    def invoke(processor: Path, case: dict, corpus_path: Path, work: Path):
        profile = case.get("pipeline_profile")
        if "pipeline_profile" in case and (
                not isinstance(profile, str) or profile not in PIPELINE_PROFILES):
            raise ValueError(f"unsupported pipeline_profile: {profile!r}")
        if retain_root is not None:
            work = case_directory(retain_root, case["case_id"])
        if profile is None:
            return original(processor, case, corpus_path, work)

        capture_profile = case.get("processor_profile", "default")
        if capture_profile not in stage_profile_support.SUPPORTED_CAPTURE_PROFILES:
            raise ValueError(f"unsupported processor_profile: {capture_profile!r}")
        rate, channels = int(case["sample_rate_hz"]), int(case["mic_channels"])
        if rate not in engine.SUPPORTED_RATES or channels not in (1, 2):
            raise ValueError("unsupported PCM geometry")
        mic_path = engine.resolve(corpus_path, case["mic_audio"])
        render_path = engine.resolve(corpus_path, case.get("render_audio"))
        if mic_path is None:
            raise ValueError("mic_audio is required")
        if render_path is not None and capture_profile != "default":
            raise ValueError("stage-isolated capture_profile cannot be used with render")
        mic, mic_raw = engine.stage_audio(mic_path, rate, channels, work, "mic.pcm")
        if len(mic) % (channels * (rate // 100)):
            raise ValueError("capture must contain complete interleaved 10 ms frames")
        render = None
        render_raw = None
        if render_path is not None:
            render, render_raw = engine.stage_audio(render_path, rate, 1, work, "render.pcm")
        output_path, metrics_path = work / "out.pcm", work / "metrics.jsonl"
        command = [
            str(processor), "--profile", profile,
            "--sample-rate", str(rate), "--mic-channels", str(channels),
            "--strict-capture-frames", "--metrics-jsonl", str(metrics_path),
        ]
        control = case.get("control", {})
        if "echo_path_change_frame" in control:
            command += ["--echo-path-change-frame", str(int(control["echo_path_change_frame"]))]
        if "discontinuity_frame" in control:
            command += [
                "--discontinuity-frame", str(int(control["discontinuity_frame"])),
                "--discontinuity-flags", str(int(control.get("discontinuity_flags", 1))),
                "--discontinuity-lost-frames", str(int(control.get("discontinuity_lost_frames", 1))),
            ]
        if render_raw is None:
            command += ["--capture-profile", capture_profile, "--capture-only", str(mic_raw), str(output_path)]
        else:
            command += [str(mic_raw), str(render_raw), str(output_path)]
        # No tuning options are synthesized: the selected SDK preset owns them.
        (work / "command.json").write_text(json.dumps(command, indent=2) + "\n", encoding="utf-8")
        started = time.monotonic()
        try:
            completed = run_command(command, check=False, capture_output=True, text=True,
                                    timeout=PROCESS_TIMEOUT_SECONDS)
        except subprocess.TimeoutExpired:
            (work / "execution.json").write_text(json.dumps({
                "status": "TIMEOUT", "timeout_seconds": PROCESS_TIMEOUT_SECONDS,
                "elapsed_seconds": time.monotonic() - started,
            }, indent=2) + "\n", encoding="utf-8")
            raise
        (work / "stdout.txt").write_text(completed.stdout, encoding="utf-8")
        (work / "stderr.txt").write_text(completed.stderr, encoding="utf-8")
        (work / "execution.json").write_text(json.dumps({
            "returncode": completed.returncode,
            "elapsed_seconds": time.monotonic() - started,
        }, indent=2) + "\n", encoding="utf-8")
        completed.check_returncode()
        output = engine.read_raw_array(output_path)
        trace = [json.loads(line) for line in metrics_path.read_text(encoding="utf-8").splitlines() if line.strip()]
        inputs = {"mic": mic, "render": render}
        observed = continuity(case, output, trace, inputs)
        (work / "continuity.json").write_text(json.dumps(observed, indent=2) + "\n", encoding="utf-8")
        return output, trace, inputs

    return invoke


def validation_semantics(*, retain_root: Path | None = None):
    base = quality_metric_support.build_validation_semantics(run_validation)
    return replace(base, evaluation=replace(
        base.evaluation,
        invoke=build_invoke(base.evaluation.invoke, retain_root=retain_root),
    ))
