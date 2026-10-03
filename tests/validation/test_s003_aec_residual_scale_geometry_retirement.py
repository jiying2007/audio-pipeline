#!/usr/bin/env python3
from __future__ import annotations
import json,re
from pathlib import Path
from retired_workflow_contract import assert_contract_or_retired
ROOT=Path(__file__).resolve().parents[2]
LIVE=ROOT/".github/workflows/research-s003-aec-residual-scale-geometry-v1.yml"
CONSUMED=ROOT/"tests/validation/data/s003-aec-residual-scale-geometry-consumed-workflow.yml"
RESULT=ROOT/"docs/program/iterations/S003-aec-residual-scale-geometry-decomposition-v1-result.json"

def main():
    assert_contract_or_retired(ROOT, LIVE, Path(__file__).name)
    consumed=CONSUMED.read_text(); r=json.loads(RESULT.read_text())
    assert "\n  workflow_dispatch:\n" in consumed and "\n  push:\n" in consumed
    assert "19507 19607 19707 19807 19907 20007 20107 20207" in consumed

    assert r["status"]=="CLOSED_DIAGNOSTIC_GEOMETRY_CONTRIBUTION_REPEATABLE_SCALE_SECONDARY"
    assert r["investigation_terminal"] is True and r["rerun_required"] is False
    e=r["authoritative_execution"]
    assert e["workflow_run_id"]==37094470698
    assert e["head_sha"]=="595c81c245eec2cfe87700980ed30664354e8262"
    assert e["artifact_id"]==11263739143
    assert e["artifact_zip_sha256"]=="3da6abeb56a01a21bfe9799c0eaaf33d6f90e386212c3406c252874ebe86247c"
    assert e["aggregate_member_sha256"]=="0cfb5cdc1aae69664122a20f6a561cc3a995d1ec7d2f284c2c6f658c6cbe0148"

    f=r["factorization"]
    assert f["equation"]=="R = M * G"
    assert f["physical_admissibility_preserved_all_modes_all_seeds"] is True
    assert f["invalid_values_clamped"] is False

    m=r["mechanical_result"]
    assert m["freeze_geometry"]["physically_admissible_seed_count"]==8
    assert set(m["freeze_geometry"]["recovery_time_ms"].values())=={0}
    assert m["freeze_geometry"]["earlier_seed_count"]==8
    assert m["freeze_scale"]["physically_admissible_seed_count"]==8
    assert m["freeze_scale"]["earlier_seed_count"]==5
    assert m["freeze_scale"]["unchanged_seed_count"]==3
    assert m["freeze_scale"]["later_seed_count"]==0

    rv=r["reviewed_validity"]
    assert rv["normalized_geometry_transition_is_cross_seed_repeatable_mechanical_contributor"] is True
    assert rv["subtraction_input_scale_transition_is_cross_seed_invariant_contributor"] is False
    assert rv["freeze_geometry_zero_ms_result_requires_independent_confirmation"] is True
    assert rv["geometry_root_cause_proven"] is False
    assert rv["scale_root_cause_proven"] is False
    assert rv["factor_scale_search_authorized"] is False
    assert rv["filter_weight_or_tap_inspection_authorized"] is False
    assert rv["aec_or_res_parameter_search_authorized"] is False

    nxt=r["next_authorized_step"]
    assert nxt["phase"]=="S003_AEC_GEOMETRY_FREEZE_CONFIRMATION_V1"
    assert nxt["candidate_limit"]==0 and nxt["confirmation_limit"]==1
    assert r["candidate_authority"] is False and r["s004_open"] is False
    print("S003 residual scale-geometry terminal state: OK")
    return 0
if __name__=="__main__": raise SystemExit(main())
