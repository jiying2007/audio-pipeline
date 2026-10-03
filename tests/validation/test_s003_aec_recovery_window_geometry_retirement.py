#!/usr/bin/env python3
"""Lock terminal state of S003 AEC recovery window-geometry decomposition."""

from __future__ import annotations

import json
import re
from pathlib import Path
from retired_workflow_contract import assert_contract_or_retired

ROOT=Path(__file__).resolve().parents[2]
LIVE=ROOT/".github/workflows/research-s003-aec-recovery-window-geometry-v1.yml"
CONSUMED=ROOT/"tests/validation/data/s003-aec-recovery-window-geometry-consumed-workflow.yml"
RESULT=ROOT/"docs/program/iterations/S003-aec-recovery-window-geometry-decomposition-v1-result.json"

def main()->int:
    assert_contract_or_retired(ROOT, LIVE, Path(__file__).name)
    consumed=CONSUMED.read_text(encoding="utf-8")
    result=json.loads(RESULT.read_text(encoding="utf-8"))

    assert "\n  workflow_dispatch:\n" in consumed
    assert "\n  push:\n" in consumed
    assert "Run fresh paired geometry measurements" in consumed
    assert "11907 12007 12107 12207" in consumed

    assert result["status"]=="CLOSED_DIAGNOSTIC_WINDOW_GEOMETRY_DECOMPOSED"
    assert result["investigation_terminal"] is True
    e=result["authoritative_execution"]
    assert e["workflow_run_id"]==37007715869
    assert e["head_sha"]=="6ac1f3118f11b30b0daae7f9bba19bc5aac15f19"
    assert e["artifact_id"]==11226891116
    assert e["artifact_zip_sha256"]=="4477e2a10d31d1b7209ab94572c36d3f4def93de52ff5bce2e3b183abf2a7a48"
    assert e["aggregate_member_sha256"]=="a28c013b4bd4770e6002f82e431f0f453426750ddc37e29999d5e8559d2d9cbc"

    mech=result["mechanical_result"]
    assert mech["cross_seed_range_effect_counts"]["stride_100w100s_to_100w50s"]=={
        "shrank":9,"grew":1,"unchanged":5,"total":15
    }
    assert mech["cross_seed_range_effect_counts"]["integration_100w50s_to_50w50s"]=={
        "shrank":1,"grew":3,"unchanged":11,"total":15
    }
    assert mech["total_cross_seed_range_ms"]=={
        "100w-100s":1000,"100w-50s":600,"50w-50s":1000
    }
    assert mech["per_seed"]["12007"]["censored"]["50w-50s"]==1
    reviewed=result["reviewed_validity"]
    assert reviewed["100w_50s_non_worse_pairs"]==14
    assert reviewed["100w_50s_better_pairs"]==9
    assert reviewed["100w_50s_worse_pairs"]==1
    assert reviewed["measurement_default_change_authority"] is False
    assert reviewed["measurement_artifact_verdict"]=="NOT_AUTHORIZED"

    nxt=result["next_authorized_step"]
    assert nxt["phase"]=="S003_AEC_RECOVERY_100W50S_GEOMETRY_CONFIRMATION_V1"
    assert nxt["fresh_seeds"]==[12307,12407,12507,12607]
    assert nxt["confirmation_rule"]["minimum_non_worse_case_profiles"]==13
    assert result["candidate_authority"] is False
    assert result["measurement_default_authority"] is False
    assert result["s004_open"] is False
    print("S003 AEC recovery window-geometry terminal state: OK")
    return 0

if __name__=="__main__":
    raise SystemExit(main())
