#!/usr/bin/env python3
"""Lock terminal rejection of the S003 speaker-gain RES→NS recovery hypothesis."""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
LIVE=ROOT/".github/workflows/research-s003-speaker-gain-ns-recovery-confirmation-v1.yml"
CONSUMED=ROOT/"tests/validation/data/s003-speaker-gain-ns-recovery-confirmation-consumed-workflow.yml"
RESULT=ROOT/"docs/program/iterations/S003-aec-speaker-gain-ns-recovery-extension-confirmation-v1-result.json"
PRIOR=ROOT/"docs/program/iterations/S003-aec-transition-stage-recovery-decomposition-v1-result.json"


def main()->int:
    live=LIVE.read_text(encoding="utf-8")
    consumed=CONSUMED.read_text(encoding="utf-8")
    result=json.loads(RESULT.read_text(encoding="utf-8"))
    prior=json.loads(PRIOR.read_text(encoding="utf-8"))

    assert "\n  pull_request:\n" in live
    assert "\n  workflow_dispatch:\n" not in live
    assert "\n  push:\n" not in live
    assert "\n  schedule:\n" not in live
    jobs=re.findall(r"(?m)^  ([A-Za-z_][A-Za-z0-9_-]*):\s*$",live[live.index("\njobs:")+1:])
    assert jobs==["contract"],jobs
    assert "test_s003_speaker_gain_ns_confirmation_retirement.py" in live

    assert "\n  workflow_dispatch:\n" in consumed
    assert "\n  push:\n" in consumed
    assert "Run fresh pairwise confirmation" in consumed
    assert "10907 11007" in consumed
    assert "ns_recovery_time_ms - res_recovery_time_ms >= 100" in consumed

    assert result["status"]=="CLOSED_DIAGNOSTIC_SINGLE_HYPOTHESIS_REJECTED"
    assert result["investigation_terminal"] is True
    assert result["rerun_required"] is False
    e=result["authoritative_execution"]
    assert e["workflow_run_id"]==36992340263
    assert e["head_sha"]=="f84c7167248c7657659ebb565c64274ed62d7293"
    assert e["artifact_id"]==11219823878
    assert e["artifact_zip_sha256"]=="5c45968a576f2c97c9dcf81ed7fe8c2ca363e96ef1e6462498d2d103d9a1f3a8"
    assert e["aggregate_member_sha256"]=="56f65bad053784b6390a376caadc43a2bdb6b5f1a4d229d906d138f445ea551b"

    obs=result["observations"]
    assert obs["10907"]=={
        "res_recovery_time_ms":300,
        "ns_recovery_time_ms":300,
        "full_recovery_time_ms":300,
        "ns_minus_res_ms":0,
        "confirmed_on_seed":False,
    }
    assert obs["11007"]=={
        "res_recovery_time_ms":200,
        "ns_recovery_time_ms":300,
        "full_recovery_time_ms":300,
        "ns_minus_res_ms":100,
        "confirmed_on_seed":True,
    }

    mechanical=result["mechanical_result"]
    assert mechanical["hypothesis_confirmed"] is False
    assert mechanical["outcome"]=="REJECTED"
    assert mechanical["confirming_seed_count"]==1
    assert mechanical["rejecting_seed_count"]==1

    reviewed=result["reviewed_validity"]
    assert reviewed["stable_ns_stage_extension_supported"] is False
    assert reviewed["ns_root_cause_claim_authority"] is False
    assert reviewed["ns_temporal_state_attribution_authority"] is False
    assert reviewed["ns_parameter_search_authority"] is False
    assert reviewed["candidate_authority"] is False

    assert prior["status"]=="CLOSED_DIAGNOSTIC_STAGE_RECOVERY_DECOMPOSED"
    assert prior["mechanical_result"]["speaker-acoustic-gain-step"]["ns_minus_res_ms"]==[100,100]
    assert result["historical_context"]["precedence_rule"].startswith(
        "the preregistered independent fresh-seed confirmation governs hypothesis status"
    )

    nxt=result["next_authorized_step"]
    assert nxt["phase"]=="S003_AEC_RECOVERY_VARIABILITY_SOURCE_DECOMPOSITION_V1"
    assert nxt["candidate_limit"]==0
    assert "NS internal parameter search" in nxt["forbidden"]
    assert "NLMS step-size search" in nxt["forbidden"]
    assert result["s004_open"] is False
    assert result["candidate_authority"] is False

    print("S003 speaker-gain NS confirmation terminal rejection: OK")
    return 0

if __name__=="__main__":
    raise SystemExit(main())
