#!/usr/bin/env python3
from __future__ import annotations
import json,re
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
LIVE=ROOT/".github/workflows/research-s003-aec-residual-energy-trajectory-v1.yml"
CONSUMED=ROOT/"tests/validation/data/s003-aec-residual-energy-consumed-workflow.yml"
RESULT=ROOT/"docs/program/iterations/S003-aec-residual-energy-trajectory-decomposition-v1-result.json"

def main():
    live=LIVE.read_text(); consumed=CONSUMED.read_text(); r=json.loads(RESULT.read_text())
    assert "\n  pull_request:\n" in live
    assert "\n  workflow_dispatch:\n" not in live and "\n  push:\n" not in live
    jobs=re.findall(r"(?m)^  ([A-Za-z_][A-Za-z0-9_-]*):\s*$",live[live.index("\njobs:")+1:])
    assert jobs==["contract"],jobs
    assert "test_s003_aec_residual_geometry_retirement.py" in live
    assert "\n  workflow_dispatch:\n" in consumed and "\n  push:\n" in consumed
    assert "17107 17207 17307 17407 17507 17607 17707 17807" in consumed

    assert r["status"]=="CLOSED_DIAGNOSTIC_JOINT_Q_RHO_GEOMETRY_RETAINED_SINGLE_FACTOR_NOT_INVARIANT"
    assert r["investigation_terminal"] is True and r["rerun_required"] is False
    e=r["authoritative_execution"]
    assert e["workflow_run_id"]==37083012742
    assert e["head_sha"]=="caca41bd855e8d6e3b4de97a0a6cce9675c09833"
    assert e["artifact_id"]==11258859727
    assert e["artifact_zip_sha256"]=="843bd8e1be6c57a5d65c35100adabd5a8ff6c6a4acd5970a2aaeeef961a2d080"
    assert e["aggregate_member_sha256"]=="53bc972eae82b492bb4a5e5c66514cb82dc1e24fd854cb7b20e026c4614907ab"

    p=r["probe_validity"]
    assert p["probe_output_bitwise_equivalent_all_seeds"] is True
    assert p["identity_valid_all_seeds"] is True
    assert p["normalized_reconstruction_valid_all_seeds"] is True
    assert p["actual_observed_recovery_matches_standard_aec_all_seeds"] is True
    assert p["filter_weight_or_tap_access"] is False

    c=r["counterfactual_result"]
    assert c["freeze_both"]["all_seeds_earlier_than_actual"] is True
    assert c["freeze_both"]["all_seeds_equal_50ms"] is True
    assert set(c["freeze_both"]["recovery_time_ms"].values())=={50}
    assert c["freeze_q"]["directionally_invariant"] is False
    assert c["freeze_rho"]["directionally_invariant"] is False

    rv=r["reviewed_validity"]
    assert rv["joint_q_rho_transition_variation_is_repeatable_mechanical_contributor"] is True
    assert rv["q_root_cause_proven"] is False
    assert rv["rho_root_cause_proven"] is False
    assert rv["q_or_rho_parameter_search_authorized"] is False
    assert rv["filter_weight_or_tap_inspection_authorized"] is False
    assert r["next_authorized_step"]["phase"]=="S003_AEC_JOINT_GEOMETRY_CONFIRMATION_V1"
    assert r["next_authorized_step"]["candidate_limit"]==0
    assert r["candidate_authority"] is False and r["s004_open"] is False
    print("S003 AEC residual geometry terminal state: OK")
    return 0
if __name__=="__main__": raise SystemExit(main())
