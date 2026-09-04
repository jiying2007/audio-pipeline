#!/usr/bin/env python3
"""Install stage-isolated capture profiles into the canonical validation engine.

The canonical evaluator intentionally remains the only metric implementation.
This module only extends processor invocation so regression/tuning corpora can
exercise one capture stage at a time without duplicating metric math.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

SUPPORTED_CAPTURE_PROFILES = {
    "default",
    "ns-isolated",
    "vad-isolated",
    "agc-isolated",
    "bf-isolated",
}


def install(engine: Any) -> None:
    original = engine.invoke

    def invoke(processor: Path, case: dict, corpus_path: Path, work: Path):
        profile = case.get("processor_profile", "default")
        if profile not in SUPPORTED_CAPTURE_PROFILES:
            raise ValueError(f"unsupported processor_profile: {profile}")
        if case.get("render_audio") is not None or profile in {"default", "ns-isolated"}:
            return original(processor, case, corpus_path, work)

        rate = int(case["sample_rate_hz"])
        channels = int(case["mic_channels"])
        mic_path = engine.resolve(corpus_path, case["mic_audio"])
        if mic_path is None:
            raise ValueError("mic_audio is required")
        mic, mic_raw = engine.stage_audio(mic_path, rate, channels, work, "mic.pcm")
        output_path = work / "out.pcm"
        metrics_path = work / "metrics.jsonl"
        command = [
            str(processor),
            "--sample-rate", str(rate),
            "--mic-channels", str(channels),
            "--metrics-jsonl", str(metrics_path),
            "--capture-profile", profile,
            "--capture-only", str(mic_raw), str(output_path),
        ]
        subprocess.run(command, check=True)
        output = engine.read_raw(output_path)
        trace = []
        if metrics_path.exists():
            for line in metrics_path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    trace.append(json.loads(line))
        return output, trace, {"mic": mic, "render": None}

    engine.invoke = invoke
