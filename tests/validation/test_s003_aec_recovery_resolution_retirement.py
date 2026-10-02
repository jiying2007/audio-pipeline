#!/usr/bin/env python3
"""Lock terminal state of S003 AEC recovery measurement-resolution study."""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LIVE = ROOT / ".github/workflows/research-s003-aec-recovery-measurement-resolution-v1.yml"
CONSUMED = ROOT / "tests/validation/data/s003-aec-recovery-measurement-resolution-consumed-workflow.yml"
RESULT = ROOT / "docs/program/iterations/S003-aec-recovery-measurement-resolution-v1-result.json"


def main() -> int:
    live = LIVE.read_text(encoding="utf-8")
    consumed = CONSUMED.read_text(encoding="utf-8")
    result = json.loads(RESULT.read_text(encoding="utf-8"))

    assert "\n  pull_request:\n" in live
    assert "\n  workflow_dispatch:\n" not in live
    assert "\n  push:\n" not in live
    jobs = re.findall(
        r"(?m)^  ([A-Za-z_][A-Za-z0-9_-]*):\s*$",
        live[live.index("\njobs:") + 1 :],
    )
    assert jobs == ["contract"], jobs
    assert "test_s003_aec_recovery_resolution_retirement.py" in live

    assert "\n  workflow_dispatch:\n" in consumed
    assert "\n  push:\n" in consumed
    assert "Run fresh paired-resolution measurements" in consumed
    assert "11507 11607 11707 11807" in consumed
    assert "no_multi_resolution_sweep_beyond_100_and_50_ms" in consumed

    assert result["status"] == "CLOSED_DIAGNOSTIC_MEASUREMENT_GEOMETRY_SENSITIVE"
    assert result["investigation_terminal"] is True
    assert result["rerun_required"] is False
    execution = result["authoritative_execution"]
    assert execution["workflow_run_id"] == 37002887914
    assert execution["head_sha"] == "6d3c91f10613e83fe3a5278bb24ff3a18647772c"
    assert execution["artifact_id"] == 11224214179
    assert execution["artifact_zip_sha256"] == (
        "c9187602dad43f0e9a93f9b06ae269dc7348d582e5459349e14588ca97241e39"
    )
    assert execution["aggregate_member_sha256"] == (
        "fb07a2cca3d9676fafd290ef1881f6a2b611ff6e6bb1e50c74fd66d9e08eb37a"
    )

    scope = result["scope"]
    assert scope["fresh_seeds"] == [11507, 11607, 11707, 11807]
    assert scope["total_observations"] == 60
    assert scope["censored_100ms"] == 0
    assert scope["censored_50ms"] == 0

    mechanical = result["mechanical_result"]
    assert mechanical["cross_seed_range_direction_counts"] == {
        "shrank": 5,
        "grew": 3,
        "unchanged": 7,
        "total_case_profiles": 15,
    }
    paired = mechanical["paired_recovery_time_change"]
    assert paired["changed_observations"] == 46
    assert paired["unchanged_observations"] == 14
    assert paired["total_observations"] == 60
    assert paired["median_delta_ms"] == 0

    ranges = mechanical["cross_seed_ranges_ms"]
    assert ranges["echo-path-change"]["AEC"] == {"100ms": 100, "50ms": 0, "delta": -100}
    assert ranges["echo-path-change"]["RES"] == {"100ms": 0, "50ms": 150, "delta": 150}
    assert ranges["speaker-acoustic-gain-step"]["AEC"] == {"100ms": 0, "50ms": 150, "delta": 150}
    assert ranges["render-level-step"]["RES"] == {"100ms": 100, "50ms": 50, "delta": -50}

    reviewed = result["reviewed_validity"]
    assert reviewed["measurement_geometry_sensitivity_observed"] is True
    assert reviewed["simpler_100ms_quantization_only_explanation_supported"] is False
    assert reviewed["measurement_artifact_proven"] is False
    assert reviewed["algorithm_pass_fail_verdict"] == "NOT_AUTHORIZED"

    next_step = result["next_authorized_step"]
    assert next_step["phase"] == "S003_AEC_RECOVERY_WINDOW_GEOMETRY_DECOMPOSITION_V1"
    assert next_step["candidate_limit"] == 0
    assert next_step["fresh_seeds"] == [11907, 12007, 12107, 12207]
    assert next_step["geometries"] == [
        {"id": "100w-100s", "window_ms": 100, "stride_ms": 100, "required_windows_for_300ms_coverage": 3},
        {"id": "100w-50s", "window_ms": 100, "stride_ms": 50, "required_windows_for_300ms_coverage": 5},
        {"id": "50w-50s", "window_ms": 50, "stride_ms": 50, "required_windows_for_300ms_coverage": 6},
    ]

    assert result["candidate_authority"] is False
    assert result["measurement_artifact_verdict_authority"] is False
    assert result["s004_open"] is False

    print("S003 AEC recovery resolution terminal state: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
