#!/usr/bin/env python3
"""Lock terminal reviewed state of S003 AEC metric-safe evidence."""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LIVE = ROOT / ".github/workflows/research-s003-aec-metric-safe-evidence-v1.yml"
CONSUMED = ROOT / "tests/validation/data/s003-aec-metric-safe-consumed-workflow.yml"
RESULT = ROOT / "docs/program/iterations/S003-aec-metric-safe-evidence-v1-result.json"


def main() -> int:
    live = LIVE.read_text(encoding="utf-8")
    consumed = CONSUMED.read_text(encoding="utf-8")
    result = json.loads(RESULT.read_text(encoding="utf-8"))

    assert "\n  pull_request:\n" in live
    assert "\n  push:\n" not in live
    assert "\n  workflow_dispatch:\n" not in live
    assert "\n  schedule:\n" not in live
    jobs = re.findall(
        r"(?m)^  ([A-Za-z_][A-Za-z0-9_-]*):\s*$",
        live[live.index("\njobs:") + 1 :],
    )
    assert jobs == ["contract"], jobs
    assert "test_s003_aec_metric_safe_retirement.py" in live

    assert "\n  push:\n" in consumed
    assert "\n  workflow_dispatch:\n" in consumed
    assert "Run fresh canonical AEC transition evidence" in consumed
    assert "10307 10407" in consumed
    assert "no_aec_parameter_search" in consumed

    assert result["status"] == "CLOSED_DIAGNOSTIC_METRIC_APPLICABILITY_ESTABLISHED"
    assert result["investigation_terminal"] is True
    assert result["rerun_required"] is False
    execution = result["authoritative_execution"]
    assert execution["workflow_run_id"] == 36984527224
    assert execution["head_sha"] == "89b3a8170061ac0fadd3de7559086384a60bf751"
    assert execution["artifact_id"] == 11217011011
    assert execution["artifact_zip_sha256"] == (
        "4f764fc824d7c391c71d797a1a9739f06e430aec268acfeb775dc56907978ad5"
    )
    assert execution["aggregate_member_sha256"] == (
        "75692c82060b42c2cfe3180261d7c7c829d998685d854f99f408bf7ec1cbcd80"
    )

    contract = result["metric_contract"]
    assert contract["fresh_seeds"] == [10307, 10407]
    assert contract["metric_contract_complete_cases"] == {"10307": 8, "10407": 8}
    assert contract["incomplete_cases"] == {"10307": 0, "10407": 0}
    assert contract["metric_applicability_map_complete"] is True
    assert contract["algorithm_performance_verdict_authority"] is False
    assert contract["candidate_authority"] is False
    assert contract["near_end_only_raw_clean_si_sdr_primary_metric_rejected"] is True

    reviewed = result["reviewed_validity"]
    assert reviewed["metric_applicability_sufficiently_established"] is True
    assert reviewed["near_end_only_raw_clean_si_sdr_invalid_as_primary_metric"] is True
    assert reviewed["transition_residual_spike_repeatable"] is True
    assert reviewed["transition_late_recovery_observed"] is True
    assert reviewed["performance_threshold_established"] is False
    assert reviewed["algorithm_pass_fail_verdict"] == "NOT_AUTHORIZED"

    transition = result["transition_residual_trajectory_db"]
    for case in (
        "echo-path-change",
        "speaker-acoustic-gain-step",
        "render-level-step",
    ):
        assert set(transition[case]) == {"10307", "10407"}
        for seed in ("10307", "10407"):
            item = transition[case][seed]
            assert item["early_post"] > item["pre"]
            assert item["late_post"] < item["early_post"]

    next_step = result["next_authorized_step"]
    assert next_step["phase"] == "S003_AEC_TRANSITION_RECOVERY_LATENCY_V1"
    assert next_step["candidate_limit"] == 0
    assert next_step["no_performance_threshold"] is True
    assert next_step["no_parameter_search"] is True
    assert "3.01029995664" in next_step["definition"]
    assert "300 ms" in next_step["definition"]

    qualification = result["qualification"]
    assert qualification["verify_run_id"] == 36984527579
    assert qualification["verify_conclusion"] == "success"
    assert qualification["system_robustness_run_id"] == 36984527256
    assert qualification["system_robustness_conclusion"] == "success"
    assert qualification["hosted_real_audio_conclusion"] == "success"
    assert qualification["hosted_real_aec_conclusion"] == "success"

    print("S003 AEC metric-safe terminal state: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
