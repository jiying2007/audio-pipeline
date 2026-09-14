#!/usr/bin/env python3
"""Release-neutral quality-aware wrapper around canonical acoustic tuning."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
for path in (ROOT / "validation/tools", ROOT / "tests/validation"):
    value = str(path)
    if value not in sys.path:
        sys.path.insert(0, value)

import tuning_iteration
import tuning_iteration_engine as engine

QUALITY_OBJECTIVES = {
    "p10_near_projection_gain_db",
    "p10_interference_projection_attenuation_db",
    "p10_interference_corr_reduction",
    "p90_erle_convergence_ms",
    "p90_erle_recovery_ms",
    "p90_vad_onset_delay_ms",
    "p90_vad_release_delay_ms",
}


def quality_run_validation(repo_root: Path, processor: Path, corpus: Path, policy: Path,
                           dataset_lock: Path, tuning: dict[str, float], output: Path):
    output.parent.mkdir(parents=True, exist_ok=True)
    evidence = output.with_suffix(".evidence.json")
    with tempfile.TemporaryDirectory(prefix="ap-quality-tuning-wrapper-") as temporary:
        wrapper = Path(temporary) / "processor"
        engine.write_wrapper(wrapper, processor, tuning)
        command = [
            sys.executable, str(repo_root / "tests/validation/audio_quality_evaluate.py"),
            "--corpus", str(corpus), "--policy", str(policy),
            "--dataset-lock", str(dataset_lock), "--processor", str(wrapper),
            "--output", str(output), "--evidence-manifest", str(evidence),
            "--source-revision", os.environ.get("GITHUB_SHA", "local-quality-tuning"),
            "--enforce",
        ]
        started = time.monotonic()
        completed = subprocess.run(command, cwd=repo_root, text=True, capture_output=True)
        elapsed = time.monotonic() - started
        if completed.returncode != 0 and not output.exists():
            raise RuntimeError(
                f"quality validation execution failed rc={completed.returncode}: "
                f"{completed.stderr[-2000:] or completed.stdout[-2000:]}"
            )
        report = json.loads(output.read_text(encoding="utf-8"))
        report["_iteration_elapsed_s"] = elapsed
        report["_iteration_returncode"] = completed.returncode
        return report, elapsed


def install() -> None:
    tuning_iteration.KNOWN_OBJECTIVE_METRICS.update(QUALITY_OBJECTIVES)
    engine.run_validation = quality_run_validation


def self_test() -> None:
    install()
    tuning_iteration.self_test()
    assert QUALITY_OBJECTIVES.issubset(tuning_iteration.KNOWN_OBJECTIVE_METRICS)
    print("release-neutral audio quality tuning self-test: OK")


def main() -> int:
    install()
    if "--self-test" in sys.argv[1:]:
        self_test()
        return 0
    return tuning_iteration.main()


if __name__ == "__main__":
    raise SystemExit(main())
