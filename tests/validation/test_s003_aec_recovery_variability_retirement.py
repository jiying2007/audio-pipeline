#!/usr/bin/env python3
"""Lock terminal state of S003 AEC recovery-variability decomposition."""

from __future__ import annotations

import json
import re
from pathlib import Path
from retired_workflow_contract import assert_contract_or_retired

ROOT = Path(__file__).resolve().parents[2]
LIVE = ROOT / ".github/workflows/research-s003-aec-recovery-variability-v1.yml"
CONSUMED = ROOT / "tests/validation/data/s003-aec-recovery-variability-consumed-workflow.yml"
RESULT = ROOT / "docs/program/iterations/S003-aec-recovery-variability-source-decomposition-v1-result.json"


def main() -> int:
    assert_contract_or_retired(ROOT, LIVE, Path(__file__).name)
    consumed = CONSUMED.read_text(encoding="utf-8")
    result = json.loads(RESULT.read_text(encoding="utf-8"))

    assert "\n  workflow_dispatch:\n" in consumed
    assert "\n  push:\n" in consumed
    assert "Run fresh recovery variability matrix" in consumed
    assert "11107 11207 11307 11407" in consumed
    assert "no_correlation_significance_threshold" in consumed

    assert result["status"] == "CLOSED_DIAGNOSTIC_VARIABILITY_DECOMPOSED"
    assert result["investigation_terminal"] is True
    assert result["rerun_required"] is False
    execution = result["authoritative_execution"]
    assert execution["workflow_run_id"] == 37001173725
    assert execution["head_sha"] == "4724b4d6fedef6314bcff522fda61bafa63d817e"
    assert execution["artifact_id"] == 11224270402
    assert execution["artifact_zip_sha256"] == (
        "12e7d70684bc351b39a072781fcfa8e559c573688849cb65881aff3bf48498c7"
    )
    assert execution["aggregate_member_sha256"] == (
        "996d2bdc2ee3baff5fd0d0372efeab3cbb2924ec37c1c55f50fa401f7b202ad4"
    )

    mechanical = result["mechanical_result"]
    ranges = mechanical["cross_seed_recovery_range_ms"]
    assert ranges["echo-path-change"] == {
        "AEC": 0, "RES": 100, "NS": 100, "AGC": 100, "full": 100
    }
    assert ranges["speaker-acoustic-gain-step"] == {
        "AEC": 0, "RES": 100, "NS": 0, "AGC": 0, "full": 0
    }
    assert ranges["render-level-step"] == {
        "AEC": 0, "RES": 100, "NS": 0, "AGC": 0, "full": 0
    }
    margin = mechanical["slow_observation_previous_window_margin_db"]
    assert 0.05 < margin["min"] < 0.06
    assert 0.58 < margin["max"] < 0.59
    assert mechanical["telemetry_review"]["common_boolean_state_shift_observed"] is False
    assert mechanical["telemetry_review"]["delay_state_common_shift_observed"] is False

    reviewed = result["reviewed_validity"]
    assert reviewed["all_measurements_complete"] is True
    assert reviewed["cross_seed_variability_is_bounded_to_100ms"] is True
    assert reviewed["stable_causal_stage_identified"] is False
    assert reviewed["recovery_boundary_sensitivity_observed"] is True
    assert reviewed["measurement_resolution_artifact_proven"] is False
    assert reviewed["algorithm_pass_fail_verdict"] == "NOT_AUTHORIZED"

    next_step = result["next_authorized_step"]
    assert next_step["phase"] == "S003_AEC_RECOVERY_MEASUREMENT_RESOLUTION_V1"
    assert next_step["candidate_limit"] == 0
    assert next_step["fresh_seeds"] == [11507, 11607, 11707, 11807]
    assert result["candidate_authority"] is False
    assert result["root_cause_claim_authority"] is False
    assert result["s004_open"] is False

    print("S003 AEC recovery variability terminal state: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
