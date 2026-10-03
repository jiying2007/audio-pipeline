#!/usr/bin/env python3
"""Lock terminal state of S003 echo-path recovery sign variability."""

from __future__ import annotations

import json
import re
from pathlib import Path
from retired_workflow_contract import assert_contract_or_retired

ROOT = Path(__file__).resolve().parents[2]
LIVE = ROOT / ".github/workflows/research-s003-aec-echo-path-recovery-sign-variability-v1.yml"
CONSUMED = ROOT / "tests/validation/data/s003-aec-echo-path-sign-variability-consumed-workflow.yml"
RESULT = ROOT / "docs/program/iterations/S003-aec-echo-path-recovery-sign-variability-v1-result.json"


def main() -> int:
    assert_contract_or_retired(ROOT, LIVE, Path(__file__).name)
    consumed = CONSUMED.read_text(encoding="utf-8")
    result = json.loads(RESULT.read_text(encoding="utf-8"))

    assert "\n  workflow_dispatch:\n" in consumed
    assert "\n  push:\n" in consumed
    assert "Run fresh sign-variability observations" in consumed
    assert "13907 14007 14107 14207 14307 14407 14507 14607" in consumed
    assert "retain_all_sign_classes" in consumed

    assert result["status"] == "CLOSED_DIAGNOSTIC_SIGN_VARIABILITY_MAPPED_RES_SIDE_VARIATION_RETAINED"
    assert result["investigation_terminal"] is True
    assert result["rerun_required"] is False

    execution = result["authoritative_execution"]
    assert execution["workflow_run_id"] == 37026989089
    assert execution["head_sha"] == "8aa983dd97ece54cfcc795ffeee0dbe3b72bc057"
    assert execution["artifact_id"] == 11235626112
    assert execution["artifact_zip_sha256"] == (
        "3e6c3ac6a353cc60551038bc4b70e0e6a9c759f66f7bbfe20844099553e8ed68"
    )
    assert execution["aggregate_member_sha256"] == (
        "ea64388ddb5075f9909a78b853de9a4076325f6b250a10c2e856433885cdf2e9"
    )

    probe = result["probe_validity"]
    assert probe["test_only_internal_state_probe"] is True
    assert probe["output_bitwise_equivalent_all_seeds"] is True
    assert probe["public_api_changed"] is False
    assert probe["shipping_source_changed"] is False

    mechanical = result["mechanical_result"]
    assert mechanical["sign_distribution"] == {
        "extension": [13907, 14007, 14207, 14307, 14407, 14507, 14607],
        "neutral": [14107],
        "contraction": [],
        "censored": [],
    }
    assert mechanical["ns_minus_res_ms_by_seed"] == {
        "13907": 50, "14007": 100, "14107": 0, "14207": 100,
        "14307": 50, "14407": 100, "14507": 50, "14607": 100,
    }
    assert mechanical["res_recovery_time_ms_by_seed"]["14107"] == 250
    assert all(
        mechanical["res_recovery_time_ms_by_seed"][seed] == 150
        for seed in ("13907", "14007", "14207", "14307", "14407", "14507", "14607")
    )
    assert mechanical["neutral_seed"]["res_previous_window_margin_db"] == 0.049364658309904996
    assert mechanical["neutral_seed"]["ns_previous_window_margin_db"] == 2.370773706465954

    prior = result["prior_context"]
    assert prior["predecessor_sign_flip_seed"] == 13707
    assert prior["predecessor_ns_minus_res_ms"] == -50
    assert prior["predecessor_res_recovery_time_ms"] == 300
    assert prior["predecessor_ns_recovery_time_ms"] == 250
    assert prior["predecessor_res_previous_window_margin_db"] == 0.19612002372001314

    reviewed = result["reviewed_validity"]
    assert reviewed["res_to_ns_extension_is_common_but_not_invariant"] is True
    assert reviewed["non_positive_seed_is_res_side_delay"] is True
    assert reviewed["ns_state_family_ranking_authorized"] is False
    assert reviewed["ns_root_cause_proven"] is False
    assert reviewed["res_root_cause_proven"] is False
    assert reviewed["recovery_threshold_artifact_proven"] is False

    next_step = result["next_authorized_step"]
    assert next_step["phase"] == "S003_AEC_ECHO_PATH_RES_SIDE_RECOVERY_VARIABILITY_V1"
    assert next_step["candidate_limit"] == 0
    assert result["candidate_authority"] is False
    assert result["root_cause_claim_authority"] is False
    assert result["shipping_change_authority"] is False
    assert result["s004_open"] is False

    print("S003 echo-path sign variability terminal state: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
