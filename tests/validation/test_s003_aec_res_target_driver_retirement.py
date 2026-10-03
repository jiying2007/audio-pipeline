#!/usr/bin/env python3
from __future__ import annotations
import json,re
from pathlib import Path
from retired_workflow_contract import assert_contract_or_retired
ROOT=Path(__file__).resolve().parents[2]
LIVE=ROOT/".github/workflows/research-s003-aec-res-target-driver-v1.yml"
CONSUMED=ROOT/"tests/validation/data/s003-aec-res-target-driver-consumed-workflow.yml"
RESULT=ROOT/"docs/program/iterations/S003-aec-res-target-driver-decomposition-v1-result.json"

def main():
    assert_contract_or_retired(ROOT, LIVE, Path(__file__).name)
    consumed=CONSUMED.read_text(); r=json.loads(RESULT.read_text())
    assert "\n  push:\n" in consumed and "\n  workflow_dispatch:\n" in consumed
    assert "Run fresh target-driver counterfactuals" in consumed
    assert "16307 16407 16507 16607 16707 16807 16907 17007" in consumed

    assert r["status"]=="CLOSED_DIAGNOSTIC_RESIDUAL_DRIVER_NECESSARY_ECHO_DRIVER_NOT_NECESSARY"
    assert r["investigation_terminal"] is True and r["rerun_required"] is False
    e=r["authoritative_execution"]
    assert e["workflow_run_id"]==37079992608
    assert e["head_sha"]=="4f042dc01cb99b26cc3e7ec5d10f32adc966fb31"
    assert e["artifact_id"]==11258018897
    assert e["artifact_zip_sha256"]=="63dfcf5179502ea7e6723758d9e5afe69598622feb50edd11874566dd02dd273"
    assert e["aggregate_member_sha256"]=="98cc7adac256b192245365a2da4a21baaea81ae8be97943766b478360842dc55"
    assert all(r["mechanical_validity"].values())
    cf=r["counterfactual_result"]
    assert cf["positive_actual_delay_seeds"]==[16307,16507,16807,16907,17007]
    assert cf["freeze_residual"]["eliminates_positive_actual_target_delay_seed_count"]==5
    assert cf["freeze_echo"]["eliminates_positive_actual_target_delay_seed_count"]==0
    assert cf["freeze_both"]["eliminates_positive_actual_target_delay_seed_count"]==5
    rv=r["reviewed_validity"]
    assert rv["residual_energy_variation_mechanically_necessary_for_positive_target_delay"] is True
    assert rv["echo_energy_variation_mechanically_necessary_for_positive_target_delay"] is False
    assert rv["driver_root_cause_proven"] is False
    assert r["next_authorized_step"]["phase"]=="S003_AEC_RESIDUAL_ENERGY_TRAJECTORY_DECOMPOSITION_V1"
    assert r["next_authorized_step"]["candidate_limit"]==0
    assert r["candidate_authority"] is False and r["s004_open"] is False
    print("S003 RES target-driver terminal state: OK")
    return 0
if __name__=="__main__": raise SystemExit(main())
