#!/usr/bin/env python3
from __future__ import annotations
import json,re
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
LIVE=ROOT/".github/workflows/research-s003-aec-joint-geometry-confirmation-v1.yml"
CONSUMED=ROOT/"tests/validation/data/s003-aec-joint-geometry-confirmation-consumed-workflow.yml"
RESULT=ROOT/"docs/program/iterations/S003-aec-joint-geometry-confirmation-v1-result.json"

def main():
    live=LIVE.read_text(); consumed=CONSUMED.read_text(); r=json.loads(RESULT.read_text())
    assert "\n  pull_request:\n" in live
    assert "\n  workflow_dispatch:\n" not in live and "\n  push:\n" not in live
    jobs=re.findall(r"(?m)^  ([A-Za-z_][A-Za-z0-9_-]*):\s*$",live[live.index("\njobs:")+1:])
    assert jobs==["contract"],jobs
    assert "test_s003_aec_joint_geometry_confirmation_retirement.py" in live
    assert "\n  workflow_dispatch:\n" in consumed and "\n  push:\n" in consumed
    assert "17907 18007 18107 18207 18307 18407 18507 18607" in consumed

    assert r["status"]=="CLOSED_DIAGNOSTIC_JOINT_GEOMETRY_CONFIRMED"
    assert r["investigation_terminal"] is True and r["rerun_required"] is False
    e=r["authoritative_execution"]
    assert e["workflow_run_id"]==37084140802
    assert e["head_sha"]=="5c3033ba7691f7f59c5e116f007f0a04110b800a"
    assert e["artifact_id"]==11259736745
    assert e["artifact_zip_sha256"]=="3c8105e3e57edff37c9fa9eae117eccab2c2a9a44ca591ebea5460caa3e4d9f6"

    m=r["mechanical_result"]
    assert m["outcome"]=="CONFIRMED"
    assert m["confirmed_seed_count"]==8 and m["total_seed_count"]==8
    assert set(m["freeze_both_recovery_ms"].values())=={50}
    assert set(m["freeze_rho_shift_vs_actual_ms"].values())=={0}
    assert sum(v!=0 for v in m["freeze_q_shift_vs_actual_ms"].values())==2
    nonzero_q=[v for v in m["freeze_q_shift_vs_actual_ms"].values() if v != 0]
    assert sorted(nonzero_q)==[-50,50]
    assert m["probe_output_bitwise_equivalent_all_seeds"] is True
    assert m["identity_valid_all_seeds"] is True
    assert m["normalized_geometry_valid_all_seeds"] is True

    rv=r["reviewed_validity"]
    assert rv["joint_q_rho_freeze_effect_repeatable"] is True
    assert rv["joint_geometry_change_is_repeatable_mechanical_contributor"] is True
    assert rv["q_alone_is_cross_seed_sufficient_explanation"] is False
    assert rv["rho_alone_is_cross_seed_sufficient_explanation"] is False
    assert rv["q_root_cause_proven"] is False
    assert rv["rho_root_cause_proven"] is False
    assert rv["q_rho_interaction_root_cause_proven"] is False
    assert rv["filter_weight_or_tap_inspection_authorized"] is False

    nxt=r["next_authorized_step"]
    assert nxt["phase"]=="S003_AEC_RESIDUAL_GEOMETRY_RAW_COORDINATE_DECOMPOSITION_V1"
    assert nxt["candidate_limit"]==0
    assert r["candidate_authority"] is False and r["root_cause_claim_authority"] is False
    assert r["s004_open"] is False
    print("S003 joint geometry confirmation terminal state: OK")
    return 0
if __name__=="__main__": raise SystemExit(main())
