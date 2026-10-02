#!/usr/bin/env python3
"""Run canonical validation with S003-only stage-prefix processor invocation.

This wrapper does not alter canonical metric/policy math. It only supplies a
candidate-zero invocation adapter and extends accepted processor_profile names
inside this process.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import render_corr_exact
import run_validation
import run_validation_engine as engine

PREFIX_PROFILES = {
    "prefix-raw",
    "prefix-capture",
    "prefix-bf",
    "prefix-sync",
    "prefix-aec",
    "prefix-res",
    "prefix-ns",
    "prefix-agc",
    "prefix-vad",
}
RENDER_REQUIRED = {"prefix-sync", "prefix-aec", "prefix-res"}


def _control_args(case: dict, *, allow_echo_path_change: bool) -> list[str]:
    control = case.get("control", {})
    args: list[str] = []
    if allow_echo_path_change and "echo_path_change_frame" in control:
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


def invoke(processor: Path, case: dict, corpus_path: Path, work: Path):
    profile = case.get("processor_profile", "default")
    if profile == "default":
        return engine.invoke(processor, case, corpus_path, work)
    if profile not in PREFIX_PROFILES:
        raise ValueError(f"unsupported S003 processor_profile: {profile}")

    rate = int(case["sample_rate_hz"])
    channels = int(case["mic_channels"])
    mic_path = engine.resolve(corpus_path, case["mic_audio"])
    render_path = engine.resolve(corpus_path, case.get("render_audio"))
    if mic_path is None:
        raise ValueError("mic_audio is required")
    if profile in RENDER_REQUIRED and render_path is None:
        raise ValueError(f"{profile} requires render_audio")

    mic, mic_raw = engine.stage_audio(mic_path, rate, channels, work, "mic.pcm")
    render = None
    render_raw = None
    if render_path is not None:
        render, render_raw = engine.stage_audio(
            render_path, rate, 1, work, "render.pcm"
        )

    use_render = (
        render_raw is not None
        and profile not in {"prefix-raw", "prefix-capture", "prefix-bf"}
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
        *_control_args(case, allow_echo_path_change=use_render),
    ]
    if use_render:
        command += [str(mic_raw), str(render_raw), str(output_path)]
    else:
        command += ["--capture-only", str(mic_raw), str(output_path)]

    subprocess.run(command, check=True)
    output = engine.read_raw_array(output_path)
    trace: list[dict] = []
    if metrics_path.exists():
        for line in metrics_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                trace.append(json.loads(line))
    return output, trace, {"mic": mic, "render": render}


def semantics() -> run_validation.ValidationSemantics:
    evaluation = engine.EvaluationSemantics(
        invoke=invoke,
        max_abs_corr=render_corr_exact.build_max_abs_corr(engine.normalized_corr),
    )
    return run_validation.ValidationSemantics(
        evaluation=evaluation,
        evaluate_case=engine.evaluate_case,
        engine_policy_violations=engine.policy_violations,
    )


def main() -> int:
    # validate_corpus_shape intentionally uses the canonical profile registry.
    # Extend it only for this dedicated S003 process; no repository-global
    # validation semantics are changed.
    run_validation.stage_profile_support.SUPPORTED_CAPTURE_PROFILES.update(
        PREFIX_PROFILES
    )
    return run_validation.main(semantics=semantics())


if __name__ == "__main__":
    raise SystemExit(main())
