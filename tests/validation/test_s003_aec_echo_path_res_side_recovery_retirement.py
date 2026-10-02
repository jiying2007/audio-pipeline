#!/usr/bin/env python3
"""Lock terminal state of S003 echo-path RES-side recovery variability."""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LIVE = ROOT / ".github/workflows/research-s003-aec-echo-path-res-side-recovery-v1.yml"
CONSUMED = ROOT / "tests/validation/data/s003-aec-echo-path-res-side-recovery-consumed-workflow.yml"
RESULT = ROOT / "docs/program/iterations/S003-aec-echo-path-res-side-recovery-variability-v1-result.json"


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
    assert "test_s003_aec_echo_path_res_side_recovery_retirement.py" in live

    assert "\n  workflow_dispatch:\n" in consumed
    assert "\n  push:\n" in consumed
    assert "Run fresh RES-side recovery observations" in consumed
    assert "14707 14807 14907 15007 15107 15207 15307 15407" in consumed
    assert "probe_output_bitwise_equivalent_all_seeds" in consumed

    assert result["status"] == "CLOSED_DIAGNOSTIC_RES_SIDE_VARIABILITY_MAPPED_AEC_LATE_RECOVERY_RETAINED"
    assert result["investigation_terminal"] is True
    assert result["rerun_required"] is False

    execution = result["authoritative_execution"]
    assert execution["workflow_run_id"] == 37034854322
    assert execution["head_sha"] == "1bf43b8d486e5d79585f69f877726a9bf759a978"
    assert execution["artifact_id"] == 11238644302
    assert execution["artifact_zip_sha256"] == (
        "32c47e669b11c898459482ea017361c0199ad16b3f23fadfb7fe99499b744cef"
    )
    assert execution["aggregate_member_sha256"] == (
        "2eea7dda5d94c29d346db84f5429d6dd7e9888014b558808bb6099e270033bf6"
    )

    probe = result["probe_validity"]
    assert probe["test_only_res_state_probe"] is True
    assert probe["output_bitwise_equivalent_all_seeds"] is True
    assert probe["public_api_changed"] is False
    assert probe["shipping_source_changed"] is False

    mechanical = result["mechanical_result"]
    assert mechanical["non_positive_seeds"] == [14807, 14907, 15107]
    assert mechanical["non_positive_all_have_aec_recovery_at_or_after_250ms"] is True
    assert mechanical["contraction_pattern"] == {
        "seeds": [14807, 14907],
        "aec_recovery_time_ms": 250,
        "res_recovery_time_ms": 300,
        "ns_recovery_time_ms": 250,
        "aec_to_res_ms": 50,
        "res_to_ns_ms": -50,
    }
    assert mechanical["neutral_pattern"] == {
        "seed": 15107,
        "aec_recovery_time_ms": 300,
        "res_recovery_time_ms": 300,
        "ns_recovery_time_ms": 300,
        "aec_to_res_ms": 0,
        "res_to_ns_ms": 0,
    }
    assert mechanical["fixed_time_res_gain_observation"]["at_200ms"]["all_seed_range"] == [
        0.100102425,
        0.100875184,
    ]

    reviewed = result["reviewed_validity"]
    assert reviewed["res_side_timing_variability_repeatable_on_fresh_set"] is True
    assert reviewed["standalone_res_only_explanation_supported"] is False
    assert reviewed["all_non_positive_signs_coincide_with_late_aec_recovery_on_this_fresh_set"] is True
    assert reviewed["contraction_seeds_add_an_extra_50ms_aec_to_res_delay"] is True
    assert reviewed["single_res_gain_state_separator_supported"] is False
    assert reviewed["res_gain_root_cause_proven"] is False
    assert reviewed["aec_root_cause_proven"] is False
    assert reviewed["recovery_threshold_artifact_proven"] is False

    next_step = result["next_authorized_step"]
    assert next_step["phase"] == "S003_AEC_ECHO_PATH_RES_GAIN_CONTRIBUTION_DECOMPOSITION_V1"
    assert next_step["candidate_limit"] == 0
    assert result["candidate_authority"] is False
    assert result["root_cause_claim_authority"] is False
    assert result["shipping_change_authority"] is False
    assert result["s004_open"] is False

    print("S003 echo-path RES-side recovery terminal state: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
