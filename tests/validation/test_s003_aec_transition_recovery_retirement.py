#!/usr/bin/env python3
"""Lock terminal state of S003 AEC transition recovery-latency measurement."""

from __future__ import annotations

import json
import re
from pathlib import Path
from retired_workflow_contract import assert_contract_or_retired

ROOT = Path(__file__).resolve().parents[2]
LIVE = ROOT / ".github/workflows/research-s003-aec-transition-recovery-latency-v1.yml"
CONSUMED = ROOT / "tests/validation/data/s003-aec-transition-recovery-consumed-workflow.yml"
RESULT = ROOT / "docs/program/iterations/S003-aec-transition-recovery-latency-v1-result.json"


def main() -> int:
    assert_contract_or_retired(ROOT, LIVE, Path(__file__).name)
    consumed = CONSUMED.read_text(encoding="utf-8")
    result = json.loads(RESULT.read_text(encoding="utf-8"))

    assert "\n  workflow_dispatch:\n" in consumed
    assert "\n  push:\n" in consumed
    assert "Run fresh recovery measurements" in consumed
    assert "10507 10607" in consumed
    assert "recovery_excess_db" in consumed

    assert result["status"] == "CLOSED_DIAGNOSTIC_RECOVERY_LATENCY_MEASURED"
    assert result["investigation_terminal"] is True
    assert result["rerun_required"] is False
    execution = result["authoritative_execution"]
    assert execution["workflow_run_id"] == 36986384168
    assert execution["head_sha"] == "23d776f68a4bd7688f265a2a7702ebdf757cac89"
    assert execution["artifact_id"] == 11217782676
    assert execution["artifact_zip_sha256"] == (
        "11bc3a86ab4d6667c72abd267f70c817a9e0e0022e38f231b10221dea1166ad2"
    )
    assert execution["aggregate_member_sha256"] == (
        "c6ad5d27047f789883b7a18d4212f1ff398046e27833b1c977741376255cb033"
    )

    mechanical = result["mechanical_result"]
    assert mechanical["echo-path-change"]["10507"]["recovery_time_ms"] == 200
    assert mechanical["echo-path-change"]["10607"]["recovery_time_ms"] == 200
    assert mechanical["speaker-acoustic-gain-step"]["10507"]["recovery_time_ms"] == 300
    assert mechanical["speaker-acoustic-gain-step"]["10607"]["recovery_time_ms"] == 300
    assert mechanical["render-level-step"]["10507"]["recovery_time_ms"] == 400
    assert mechanical["render-level-step"]["10607"]["recovery_time_ms"] == 300
    for case in mechanical.values():
        for obs in case.values():
            assert obs["censored"] is False

    reviewed = result["reviewed_validity"]
    assert reviewed["measurements_complete"] is True
    assert reviewed["censored_cases"] == 0
    assert reviewed["performance_requirement_established"] is False
    assert reviewed["algorithm_pass_fail_verdict"] == "NOT_AUTHORIZED"

    next_step = result["next_authorized_step"]
    assert next_step["phase"] == "S003_AEC_TRANSITION_STAGE_RECOVERY_DECOMPOSITION_V1"
    assert next_step["candidate_limit"] == 0
    assert result["candidate_authority"] is False
    assert result["shipping_change_authority"] is False

    print("S003 AEC transition recovery terminal state: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
