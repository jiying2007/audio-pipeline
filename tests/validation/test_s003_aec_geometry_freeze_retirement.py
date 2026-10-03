#!/usr/bin/env python3
from __future__ import annotations
import json,re
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
LIVE=ROOT/".github/workflows/research-s003-aec-geometry-freeze-confirmation-v1.yml"
CONSUMED=ROOT/"tests/validation/data/s003-aec-geometry-freeze-confirmation-consumed-workflow.yml"
RESULT=ROOT/"docs/program/iterations/S003-aec-geometry-freeze-confirmation-v1-result.json"
def main():
    live=LIVE.read_text(); consumed=CONSUMED.read_text(); r=json.loads(RESULT.read_text())
    assert "\n  pull_request:\n" in live and "\n  push:\n" not in live and "\n  workflow_dispatch:\n" not in live
    jobs=re.findall(r"(?m)^  ([A-Za-z_][A-Za-z0-9_-]*):\s*$",live[live.index("\njobs:")+1:])
    assert jobs==["contract"],jobs
    assert "test_s003_aec_geometry_freeze_retirement.py" in live
    assert "\n  push:\n" in consumed and "\n  workflow_dispatch:\n" in consumed
    assert "20307 20407 20507 20607 20707 20807 20907 21007" in consumed
    assert r["status"]=="CLOSED_DIAGNOSTIC_NORMALIZED_GEOMETRY_CONFIRMED_MECHANISM_LINE_TERMINAL"
    assert r["mechanical_result"]["outcome"]=="CONFIRMED"
    assert r["mechanical_result"]["confirmed_seed_count"]==8
    assert set(r["mechanical_result"]["freeze_geometry_recovery_ms"].values())=={0}
    assert r["mechanical_result"]["freeze_geometry_physically_admissible_all_seeds"] is True
    assert r["reviewed_validity"]["normalized_geometry_transition_is_independently_repeatable_mechanical_contributor"] is True
    assert r["reviewed_validity"]["filter_weight_or_tap_inspection_authorized"] is False
    assert r["mechanism_line_closeout"]["terminal"] is True
    assert r["next_authorized_step"]["phase"]=="S003_AEC_GEOMETRY_SIGNATURE_REPLAY_V1"
    assert r["candidate_authority"] is False and r["s004_open"] is False
    print("S003 geometry-freeze terminal state: OK")
    return 0
if __name__=="__main__": raise SystemExit(main())
