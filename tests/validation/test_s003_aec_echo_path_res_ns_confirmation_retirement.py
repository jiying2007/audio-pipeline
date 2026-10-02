#!/usr/bin/env python3
"""Lock terminal state of confirmed echo-path RES->NS recovery extension."""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LIVE = ROOT / ".github/workflows/research-s003-aec-echo-path-res-ns-confirm-v1.yml"
CONSUMED = ROOT / "tests/validation/data/s003-aec-echo-path-res-ns-confirm-consumed-workflow.yml"
RESULT = ROOT / "docs/program/iterations/S003-aec-echo-path-res-ns-recovery-extension-confirmation-v1-result.json"


def main() -> int:
    live = LIVE.read_text(encoding="utf-8")
    consumed = CONSUMED.read_text(encoding="utf-8")
    result = json.loads(RESULT.read_text(encoding="utf-8"))

    assert "\n  pull_request:\n" in live
    assert "\n  workflow_dispatch:\n" not in live
    assert "\n  push:\n" not in live
    jobs = re.findall(
        r"(?m)^  ([A-Za-z_][A-Za-z0-9_-]*):\s*$",
        live[live.index("\njobs:") + 1 :],
    )
    assert jobs == ["contract"], jobs
    assert "test_s003_aec_echo_path_res_ns_confirmation_retirement.py" in live

    assert "\n  workflow_dispatch:\n" in consumed
    assert "\n  push:\n" in consumed
    assert "Run independent fresh confirmation" in consumed
    assert "13107 13207 13307 13407" in consumed
    assert "ns_recovery_time_ms - res_recovery_time_ms >= 50" in consumed

    assert result["status"] == "CLOSED_DIAGNOSTIC_SINGLE_HYPOTHESIS_CONFIRMED"
    assert result["investigation_terminal"] is True
    assert result["rerun_required"] is False

    execution = result["authoritative_execution"]
    assert execution["workflow_run_id"] == 37013949148
    assert execution["head_sha"] == "e8cd8978b5e1011f64267af4b0d0e74b0b352005"
    assert execution["artifact_id"] == 11229605062
    assert execution["artifact_zip_sha256"] == (
        "3007e1d316233c3db004d3dbea1056e97fa16b446074c6d4dc4a84d996e15e82"
    )
    assert execution["aggregate_member_sha256"] == (
        "8ae4385c488f900202a2602d4c229441159b87bbc59c88e7926fbba00be73318"
    )

    mechanical = result["mechanical_result"]
    assert mechanical["hypothesis_confirmed"] is True
    assert mechanical["outcome"] == "CONFIRMED"
    assert mechanical["confirmed_seed_count"] == 4
    assert mechanical["total_seed_count"] == 4
    assert mechanical["minimum_ns_minus_res_ms"] == 50
    assert mechanical["maximum_ns_minus_res_ms"] == 100
    assert [x["ns_minus_res_ms"] for x in mechanical["observations"]] == [100, 50, 50, 50]
    assert all(x["confirmed_on_seed"] for x in mechanical["observations"])

    reviewed = result["reviewed_validity"]
    assert reviewed["res_to_ns_recovery_extension_repeatable"] is True
    assert reviewed["ns_root_cause_proven"] is False
    assert reviewed["ns_parameter_search_authorized"] is False
    assert reviewed["aec_parameter_search_authorized"] is False
    assert reviewed["res_parameter_search_authorized"] is False
    assert reviewed["algorithm_performance_verdict"] == "NOT_AUTHORIZED"

    next_step = result["next_authorized_step"]
    assert next_step["phase"] == "S003_AEC_ECHO_PATH_NS_STATE_DECOMPOSITION_V1"
    assert next_step["candidate_limit"] == 0
    assert result["candidate_authority"] is False
    assert result["root_cause_claim_authority"] is False
    assert result["shipping_change_authority"] is False
    assert result["s004_open"] is False

    print("S003 echo-path RES-NS confirmation terminal state: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
