#!/usr/bin/env python3
from __future__ import annotations

import json
import re
from pathlib import Path
from retired_workflow_contract import assert_contract_or_retired

ROOT=Path(__file__).resolve().parents[2]
LIVE=ROOT/".github/workflows/research-s003-aec-recovery-rebaseline-100w50s-v1.yml"
CONSUMED=ROOT/"tests/validation/data/s003-aec-recovery-rebaseline-100w50s-consumed-workflow.yml"
RESULT=ROOT/"docs/program/iterations/S003-aec-recovery-rebaseline-100w50s-v1-result.json"


def main() -> int:
    assert_contract_or_retired(ROOT, LIVE, Path(__file__).name)
    consumed=CONSUMED.read_text(encoding="utf-8")
    r=json.loads(RESULT.read_text(encoding="utf-8"))

    assert "\n  workflow_dispatch:\n" in consumed
    assert "\n  push:\n" in consumed
    assert "Run fresh 100w-50s recovery rebaseline" in consumed
    assert "12707 12807 12907 13007" in consumed

    assert r["status"]=="CLOSED_DIAGNOSTIC_100W50S_REBASELINED"
    assert r["investigation_terminal"] is True
    assert r["authoritative_execution"]["workflow_run_id"]==37012061058
    assert r["authoritative_execution"]["head_sha"]=="a9e586b2e53c6a32982781e1e7fe65896d3f78d6"
    assert r["authoritative_execution"]["artifact_id"]==11228052440
    assert r["authoritative_execution"]["artifact_zip_sha256"]=="1e32e8fd7a70787ba99694b968ffffe118b49ac6c33659b64aa719879f55afa4"
    assert r["authoritative_execution"]["aggregate_member_sha256"]=="67c5f000b40be92799b145144c6618fbcf36e735713a6d5bb851eefe8a679c08"

    m=r["mechanical_result"]
    assert m["retained_nonzero_phenomenon_count"]==1
    assert m["retained_nonzero_phenomena"]==[{
        "base_case_id":"echo-path-change",
        "from_stage":"RES",
        "to_stage":"NS",
        "classification":"repeatable_extension",
        "delta_ms":[50,100,100,100],
    }]
    assert m["rejected_historical_speaker_gain_res_to_ns_hypothesis_revived"] is False

    v=r["reviewed_validity"]
    assert v["retained_echo_path_res_to_ns_boundary_observation"] is True
    assert v["retained_observation_is_causal_claim"] is False
    assert v["speaker_gain_res_to_ns_hypothesis_remains_rejected"] is True

    nxt=r["next_authorized_step"]
    assert nxt["phase"]=="S003_AEC_ECHO_PATH_RES_NS_RECOVERY_EXTENSION_CONFIRMATION_V1"
    assert nxt["candidate_limit"]==0
    assert ">= 50" in nxt["confirmation_rule"]
    assert r["candidate_authority"] is False
    assert r["causal_stage_authority"] is False
    assert r["s004_open"] is False
    print("S003 100w-50s rebaseline terminal state: OK")
    return 0


if __name__=="__main__":
    raise SystemExit(main())
