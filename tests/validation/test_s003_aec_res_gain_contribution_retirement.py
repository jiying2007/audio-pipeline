#!/usr/bin/env python3
from __future__ import annotations
import json,re
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
LIVE=ROOT/".github/workflows/research-s003-aec-res-gain-contribution-v1.yml"
CONSUMED=ROOT/"tests/validation/data/s003-aec-res-gain-contribution-consumed-workflow.yml"
RESULT=ROOT/"docs/program/iterations/S003-aec-echo-path-res-gain-contribution-decomposition-v1-result.json"

def main():
    live=LIVE.read_text(); consumed=CONSUMED.read_text(); r=json.loads(RESULT.read_text())
    assert "\n  pull_request:\n" in live
    assert "\n  workflow_dispatch:\n" not in live and "\n  push:\n" not in live
    jobs=re.findall(r"(?m)^  ([A-Za-z_][A-Za-z0-9_-]*):\s*$",live[live.index("\njobs:")+1:])
    assert jobs==["contract"],jobs
    assert "test_s003_aec_res_gain_contribution_retirement.py" in live
    assert "\n  workflow_dispatch:\n" in consumed and "\n  push:\n" in consumed
    assert "Run fresh contribution decomposition" in consumed
    assert "15507 15607 15707 15807 15907 16007 16107 16207" in consumed

    assert r["status"]=="CLOSED_DIAGNOSTIC_RES_GAIN_TARGET_DRIVER_RETAINED_SMOOTHING_REJECTED"
    assert r["investigation_terminal"] is True and r["rerun_required"] is False
    e=r["authoritative_execution"]
    assert e["workflow_run_id"]==37038235197
    assert e["head_sha"]=="802c021cf72d66b646c5ca05d05b692b57ad7d05"
    assert e["artifact_id"]==11240323902
    assert e["artifact_zip_sha256"]=="5efdd3e488895e3d06c22d400989aa9c7621f7a047ed8ce95482d19f775b40e2"
    assert e["aggregate_member_sha256"]=="ea5a1aaf3f4026aec2eda97686bed646c41ced9d350a9872ecf55ea4b873d51a"

    v=r["mechanical_validity"]; assert all(v.values())
    rv=r["reviewed_validity"]
    assert rv["frozen_pre_gain_removes_res_delay_all_seeds"] is True
    assert rv["smoothing_history_is_primary_recovery_delay_source"] is False
    assert rv["smoothing_history_adds_positive_recovery_delay_seed_count"]==0
    assert rv["smoothing_history_neutral_seed_count"]==6
    assert rv["smoothing_history_accelerates_vs_instantaneous_target_seed_count"]==2
    assert rv["instantaneous_target_trajectory_remains_candidate_relevant_mechanical_driver"] is True
    assert rv["release_alpha_search_authorized"] is False
    assert r["next_authorized_step"]["phase"]=="S003_AEC_RES_TARGET_DRIVER_DECOMPOSITION_V1"
    assert r["next_authorized_step"]["candidate_limit"]==0
    assert r["candidate_authority"] is False and r["s004_open"] is False
    print("S003 RES gain contribution terminal state: OK")
    return 0
if __name__=="__main__": raise SystemExit(main())
