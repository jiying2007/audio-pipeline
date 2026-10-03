#!/usr/bin/env python3
from __future__ import annotations
import json,re
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
LIVE=ROOT/".github/workflows/research-s003-aec-raw-residual-coordinates-v1.yml"
CONSUMED=ROOT/"tests/validation/data/s003-aec-raw-residual-coordinates-consumed-workflow.yml"
RESULT=ROOT/"docs/program/iterations/S003-aec-residual-geometry-raw-coordinate-decomposition-v1-result.json"

def main():
    live=LIVE.read_text(); consumed=CONSUMED.read_text(); r=json.loads(RESULT.read_text())
    assert "\n  pull_request:\n" in live
    assert "\n  workflow_dispatch:\n" not in live and "\n  push:\n" not in live
    jobs=re.findall(r"(?m)^  ([A-Za-z_][A-Za-z0-9_-]*):\s*$",live[live.index("\njobs:")+1:])
    assert jobs==["contract"],jobs
    assert "test_s003_aec_raw_coordinate_retirement.py" in live
    assert "\n  workflow_dispatch:\n" in consumed and "\n  push:\n" in consumed
    assert "18707 18807 18907 19007 19107 19207 19307 19407" in consumed

    assert r["status"]=="CLOSED_DIAGNOSTIC_INDEPENDENT_RAW_COORDINATES_PHYSICALLY_INADMISSIBLE"
    assert r["investigation_terminal"] is True and r["rerun_required"] is False
    e=r["authoritative_execution"]
    assert e["workflow_run_id"]==37092345054
    assert e["head_sha"]=="63788cc9b244e3d2ae681e0583d442ff958cc55c"
    assert e["artifact_id"]==11262686324
    assert e["artifact_zip_sha256"]=="6662ddf06eaece6c5504c30b30c12cfdc2442c33f66474a24004194b113b93ce"

    m=r["mechanical_result"]
    for mode in ("freeze_M","freeze_E","freeze_C"):
        assert m[mode]["physically_admissible_seed_count"]==0
        assert m[mode]["physically_inadmissible_seed_count"]==8
        assert m[mode]["invalid_reason"]=="cauchy_violation"
        assert m[mode]["recovery_results_reported"] is False
    assert m["any_independent_raw_coordinate_counterfactual_physically_admissible"] is False
    assert m["invalid_values_clamped"] is False
    assert m["references_adjusted_after_results"] is False

    rv=r["reviewed_validity"]
    assert rv["independent_M_freeze_interpretable"] is False
    assert rv["independent_E_freeze_interpretable"] is False
    assert rv["independent_C_freeze_interpretable"] is False
    assert rv["raw_M_E_C_are_independently_manipulable_coordinates_for_this_signal_geometry"] is False
    assert rv["cauchy_coupling_is_material"] is True
    assert rv["pairwise_or_scale_sweep_authorized"] is False
    assert rv["prior_joint_q_rho_result_invalidated"] is False

    nxt=r["next_authorized_step"]
    assert nxt["phase"]=="S003_AEC_RESIDUAL_SCALE_GEOMETRY_DECOMPOSITION_V1"
    assert nxt["candidate_limit"]==0
    assert r["candidate_authority"] is False and r["root_cause_claim_authority"] is False
    assert r["s004_open"] is False
    print("S003 raw residual-coordinate terminal state: OK")
    return 0
if __name__=="__main__": raise SystemExit(main())
