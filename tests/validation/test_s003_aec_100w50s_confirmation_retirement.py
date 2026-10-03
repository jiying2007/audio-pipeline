#!/usr/bin/env python3
"""Lock terminal state of confirmed S003 100w-50s research geometry."""

from __future__ import annotations

import json
import re
from pathlib import Path
from retired_workflow_contract import assert_contract_or_retired

ROOT = Path(__file__).resolve().parents[2]
LIVE = ROOT / ".github/workflows/research-s003-aec-100w50s-geometry-confirmation-v1.yml"
CONSUMED = ROOT / "tests/validation/data/s003-aec-100w50s-confirmation-consumed-workflow.yml"
RESULT = ROOT / "docs/program/iterations/S003-aec-recovery-100w50s-geometry-confirmation-v1-result.json"


def main() -> int:
    assert_contract_or_retired(ROOT, LIVE, Path(__file__).name)
    consumed = CONSUMED.read_text(encoding="utf-8")
    result = json.loads(RESULT.read_text(encoding="utf-8"))

    assert "\n  workflow_dispatch:\n" in consumed
    assert "\n  push:\n" in consumed
    assert "Run independent fresh confirmation" in consumed
    assert "12307 12407 12507 12607" in consumed
    assert "minimum_non_worse_case_profiles" in consumed

    assert result["status"] == "CLOSED_DIAGNOSTIC_RESEARCH_GEOMETRY_CONFIRMED"
    assert result["investigation_terminal"] is True
    assert result["rerun_required"] is False
    execution = result["authoritative_execution"]
    assert execution["workflow_run_id"] == 37010050284
    assert execution["head_sha"] == "68b1b18ed8b608bf74a060717a16e6bee39a1f1a"
    assert execution["artifact_id"] == 11227571224
    assert execution["artifact_zip_sha256"] == (
        "8f5087a435644dc557e0d077defad68c3929f61a0291b83aede471706901654f"
    )
    assert execution["aggregate_member_sha256"] == (
        "473d6389776eac0e357613db3be5c3690a0cfd555c2b7f18520baa8d9a97637b"
    )

    mechanical = result["mechanical_result"]
    assert mechanical["hypothesis_confirmed"] is True
    assert mechanical["outcome"] == "CONFIRMED"
    assert mechanical["non_worse_case_profiles"] == 14
    assert mechanical["total_case_profiles"] == 15
    assert mechanical["summed_cross_seed_range_ms"] == {
        "100w-100s": 1000,
        "100w-50s": 600,
    }
    assert mechanical["censored_observations"] == {
        "100w-100s": 0,
        "100w-50s": 0,
    }

    reviewed = result["reviewed_validity"]
    assert reviewed["research_measurement_geometry_authorized"] == "100w-50s"
    assert reviewed["product_recovery_requirement_authority"] is False
    assert reviewed["dsp_candidate_authority"] is False
    assert reviewed["dsp_parameter_change_authority"] is False
    assert reviewed["shipping_source_change_authority"] is False
    assert reviewed["s004_open"] is False

    default = result["research_default_geometry"]
    assert default["id"] == "100w-50s"
    assert default["integration_window_ms"] == 100
    assert default["stride_ms"] == 50
    assert default["continuous_hold_ms"] == 300
    assert default["pre_baseline_window_ms"] == 100
    assert default["pre_baseline_ms"] == [-1000, -200]

    next_step = result["next_authorized_step"]
    assert next_step["phase"] == "S003_AEC_RECOVERY_REBASELINE_100W50S_V1"
    assert next_step["candidate_limit"] == 0
    assert result["candidate_authority"] is False
    assert result["shipping_change_authority"] is False

    print("S003 100w-50s research geometry terminal state: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
