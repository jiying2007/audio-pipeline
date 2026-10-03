#!/usr/bin/env python3
"""Lock terminal S003 AEC stage-recovery decomposition evidence."""

from __future__ import annotations

import json
import re
from pathlib import Path
from retired_workflow_contract import assert_contract_or_retired

ROOT=Path(__file__).resolve().parents[2]
LIVE=ROOT/".github/workflows/research-s003-aec-stage-recovery-decomposition-v1.yml"
CONSUMED=ROOT/"tests/validation/data/s003-aec-stage-recovery-consumed-workflow.yml"
RESULT=ROOT/"docs/program/iterations/S003-aec-transition-stage-recovery-decomposition-v1-result.json"


def main()->int:
    assert_contract_or_retired(ROOT, LIVE, Path(__file__).name)
    consumed=CONSUMED.read_text(encoding="utf-8")
    result=json.loads(RESULT.read_text(encoding="utf-8"))

    assert "\n  workflow_dispatch:\n" in consumed
    assert "\n  push:\n" in consumed
    assert "Run fresh stage-prefix recovery decomposition" in consumed
    assert "10707 10807" in consumed
    assert "prefix-aec" in consumed and "prefix-ns" in consumed

    assert result["status"]=="CLOSED_DIAGNOSTIC_STAGE_RECOVERY_DECOMPOSED"
    assert result["investigation_terminal"] is True
    assert result["rerun_required"] is False
    e=result["authoritative_execution"]
    assert e["workflow_run_id"]==36990768856
    assert e["head_sha"]=="9224a1029ec823ffbcf26d8cde9ecdaffba4152f"
    assert e["artifact_id"]==11219557406
    assert e["artifact_zip_sha256"]=="5448f4bf2372db747d4c5edfb404756c1c04fc5f79a74cba40ef371ba31d3cab"
    assert e["aggregate_member_sha256"]=="7977d8b3d2d8155f7c86b279e6b19f4ed881ce4301cdf0b3ed90220efbe0ceec"

    speaker=result["mechanical_result"]["speaker-acoustic-gain-step"]
    assert speaker["AEC"]==[200,200]
    assert speaker["RES"]==[200,200]
    assert speaker["NS"]==[300,300]
    assert speaker["AGC"]==[300,300]
    assert speaker["full"]==[300,300]
    assert speaker["ns_minus_res_ms"]==[100,100]

    reviewed=result["reviewed_validity"]
    stable=reviewed["stable_stage_boundary_extension"]
    assert stable["case"]=="speaker-acoustic-gain-step"
    assert stable["from_stage"]=="RES"
    assert stable["to_stage"]=="NS"
    assert stable["recovery_extension_ms"]==[100,100]
    assert stable["repeatable_on_both_fresh_seeds"] is True
    assert reviewed["ns_root_cause_claim_authority"] is False
    assert reviewed["algorithm_pass_fail_verdict"]=="NOT_AUTHORIZED"

    nxt=result["next_authorized_step"]
    assert nxt["phase"]=="S003_AEC_SPEAKER_GAIN_NS_RECOVERY_EXTENSION_CONFIRMATION_V1"
    assert nxt["candidate_limit"]==0
    assert nxt["confirm_profiles"]==["prefix-res","prefix-ns","default"]
    assert nxt["no_parameter_search"] is True
    assert nxt["no_ns_internal_hypothesis_until_confirmed"] is True
    assert result["candidate_authority"] is False

    print("S003 AEC stage-recovery terminal state: OK")
    return 0

if __name__=="__main__":
    raise SystemExit(main())
