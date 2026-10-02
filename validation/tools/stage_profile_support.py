#!/usr/bin/env python3
"""Build diagnostic stage-profile invocation for canonical validation.

The canonical evaluator remains the only metric implementation. This adapter
only changes the processor stage mask used for diagnostic replay; it never
changes shipping DSP parameters or metric math.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

ISOLATED_CAPTURE_PROFILES = {
    "ns-isolated",
    "vad-isolated",
    "agc-isolated",
    "bf-isolated",
}

PREFIX_PROFILES = {
    "prefix-capture",
    "prefix-bf",
    "prefix-sync",
    "prefix-aec",
    "prefix-res",
    "prefix-ns",
    "prefix-agc",
    "prefix-vad",
}

SUPPORTED_CAPTURE_PROFILES = {"default"} | ISOLATED_CAPTURE_PROFILES | PREFIX_PROFILES
RENDER_REQUIRED_PROFILES = {"prefix-sync", "prefix-aec", "prefix-res"}


def _control_args(case: dict) -> list[str]:
    control = case.get("control", {})
    args: list[str] = []
    if "echo_path_change_frame" in control:
        args += [
            "--echo-path-change-frame",
            str(int(control["echo_path_change_frame"])),
        ]
    if "discontinuity_frame" in control:
        args += [
            "--discontinuity-frame",
            str(int(control["discontinuity_frame"])),
            "--discontinuity-flags",
            str(int(control.get("discontinuity_flags", 1))),
            "--discontinuity-lost-frames",
            str(int(control.get("discontinuity_lost_frames", 1))),
        ]
    return args


def _read_trace(path: Path) -> list[dict]:
    trace: list[dict] = []
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                trace.append(json.loads(line))
    return trace


def build_invoke(engine: Any):
    """Build a stage-profile invoke adapter without mutating the engine module."""
    original = engine.invoke

    def invoke(processor: Path, case: dict, corpus_path: Path, work: Path):
        profile = case.get("processor_profile", "default")
        if profile not in SUPPORTED_CAPTURE_PROFILES:
            raise ValueError(f"unsupported processor_profile: {profile}")

        # Preserve legacy behavior exactly for default and existing isolated
        # profiles. The new prefix profiles are the only S003 extension.
        if profile == "default":
            return original(processor, case, corpus_path, work)
        if profile in ISOLATED_CAPTURE_PROFILES:
            if case.get("render_audio") is not None or profile == "ns-isolated":
                return original(processor, case, corpus_path, work)

        rate = int(case["sample_rate_hz"])
        channels = int(case["mic_channels"])
        mic_path = engine.resolve(corpus_path, case["mic_audio"])
        render_path = engine.resolve(corpus_path, case.get("render_audio"))
        if mic_path is None:
            raise ValueError("mic_audio is required")
        if profile in RENDER_REQUIRED_PROFILES and render_path is None:
            raise ValueError(f"{profile} requires render_audio")

        mic, mic_raw = engine.stage_audio(mic_path, rate, channels, work, "mic.pcm")
        render = None
        render_raw = None
        if render_path is not None:
            render, render_raw = engine.stage_audio(
                render_path, rate, 1, work, "render.pcm"
            )

        output_path = work / "out.pcm"
        metrics_path = work / "metrics.jsonl"
        command = [
            str(processor),
            "--sample-rate",
            str(rate),
            "--mic-channels",
            str(channels),
            "--metrics-jsonl",
            str(metrics_path),
            "--capture-profile",
            profile,
            *_control_args(case),
        ]

        # Capture/BF prefixes intentionally observe the pre-reference path even
        # for full-duplex cases. Later prefixes consume the exact same render.
        use_render = (
            render_raw is not None
            and profile not in {"prefix-capture", "prefix-bf"}
        )
        if use_render:
            command += [str(mic_raw), str(render_raw), str(output_path)]
        else:
            command += ["--capture-only", str(mic_raw), str(output_path)]

        subprocess.run(command, check=True)
        output = engine.read_raw_array(output_path)
        return output, _read_trace(metrics_path), {"mic": mic, "render": render}

    return invoke
