#!/usr/bin/env python3
"""Lock terminal state of S003 echo-path NS internal-state observation."""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LIVE = ROOT / ".github/workflows/research-s003-aec-echo-path-ns-state-v1.yml"
CONSUMED = ROOT / "tests/validation/data/s003-aec-echo-path-ns-state-consumed-workflow.yml"
RESULT = ROOT / "docs/program/iterations/S003-aec-echo-path-ns-state-decomposition-v1-result.json"


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
    assert "test_s003_aec_echo_path_ns_state_retirement.py" in live

    assert "\n  workflow_dispatch:\n" in consumed
    assert "\n  push:\n" in consumed
    assert "Run fresh NS state observations" in consumed
    assert "13507 13607 13707 13807" in consumed
    assert "extension_reproduction_is_applicability_condition" in consumed

    assert result["status"] == "CLOSED_DIAGNOSTIC_STATE_OBSERVED_EXTENSION_NOT_INVARIANT"
    assert result["investigation_terminal"] is True
    assert result["rerun_required"] is False

    execution = result["authoritative_execution"]
    assert execution["workflow_run_id"] == 37017986746
    assert execution["head_sha"] == "03ae115863defcf6a5136565d0b99e064f60e0dd"
    assert execution["artifact_id"] == 11231721444
    assert execution["artifact_zip_sha256"] == (
        "b66bf1d3fa9506d772fe656ddfaabbc85a3b13c8a6fc0dc43d1eb1a772ba92d5"
    )
    assert execution["aggregate_member_sha256"] == (
        "806f1566ab9674c824ac9058d78b1a1dc345021024fb08254257ce31839d683d"
    )

    probe = result["probe_validity"]
    assert probe["test_only_internal_state_probe"] is True
    assert probe["shipping_api_changed"] is False
    assert probe["shipping_source_changed"] is False
    assert probe["output_bitwise_equivalent_all_fresh_seeds"] is True
    assert probe["full_per_frame_state_trace_retained"] is True

    mechanical = result["mechanical_result"]
    assert mechanical["extension_ms_by_seed"] == {
        "13507": 100,
        "13607": 50,
        "13707": -50,
        "13807": 100,
    }
    assert mechanical["applicable_seed_count"] == 3
    assert mechanical["non_applicable_seeds"] == [13707]
    assert mechanical["cross_followup_fresh_seed_invariant"] is False
    assert mechanical["sign_flip_observed"] is True
    assert mechanical["sign_flip_seed"] == 13707

    reviewed = result["reviewed_validity"]
    assert reviewed["previous_confirmation_still_truthful_for_its_seed_set"] is True
    assert reviewed["previous_4_of_4_confirmation_is_cross_future_seed_invariant"] is False
    assert reviewed["ns_state_decomposition_applicable_to_all_new_fresh_seeds"] is False
    assert reviewed["state_family_ranking_authorized"] is False
    assert reviewed["ns_root_cause_proven"] is False
    assert reviewed["ns_parameter_search_authorized"] is False

    obs = result["descriptive_state_observations_on_applicable_seeds"]
    assert all(x > 0 for x in obs["speech_probability_ns_minus_res"])
    assert all(x < 0 for x in obs["noise_rms_dbfs_ns_minus_res"])
    assert all(x < 0 for x in obs["noise_estimate_mean_after_ns_minus_res"])
    assert all(x < 0 for x in obs["residual_echo_gain_ns_minus_res"])
    assert all(x < 0 for x in obs["residual_gain_mean_after_ns_minus_res"])
    assert len(obs["tracker_phase_at_recovery_boundaries"]) == 3

    next_step = result["next_authorized_step"]
    assert next_step["phase"] == "S003_AEC_ECHO_PATH_RECOVERY_SIGN_VARIABILITY_V1"
    assert next_step["candidate_limit"] == 0
    assert result["candidate_authority"] is False
    assert result["root_cause_claim_authority"] is False
    assert result["shipping_change_authority"] is False
    assert result["s004_open"] is False

    print("S003 echo-path NS state terminal state: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
