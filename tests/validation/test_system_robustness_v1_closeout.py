#!/usr/bin/env python3
"""Lock system-robustness-v1 candidate-zero phase closeout."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ITER = ROOT / "docs/program/iterations"
RESULT = ITER / "system-robustness-v1-result.json"
CATALOG = ROOT / "validation/failure-replay/catalog.json"
GEOMETRY_REPLAY = ROOT / "validation/failure-replay/supplemental/aec-echo-path-geometry-v1.json"
RESOURCES = ROOT / "ci/ssc305-resource-profiles.json"
GEOMETRY_RESULT = ITER / "S003-aec-geometry-freeze-confirmation-v1-result.json"


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    result = load(RESULT)
    assert result["status"] == "CLOSED_CANDIDATE_ZERO_FOUNDATION_ACTIVE_REGRESSION"
    assert result["authority"] == "PHASE_GOVERNANCE_ONLY_NO_CANDIDATE_RELEASE_OR_SHIPPING_AUTHORITY"
    assert result["authoritative_main"]["sha"] == "41614296a4b2541ca7cd81d38e4995038ef2f592"

    q = result["authoritative_main"]["qualification"]
    for key in (
        "system_robustness_conclusion",
        "failure_replay_bank_conclusion",
        "aec_geometry_replay_conclusion",
        "hosted_real_audio_conclusion",
        "hosted_real_aec_conclusion",
        "verify_conclusion",
        "release_conclusion",
        "i015_contract_conclusion",
        "i015_finalization_conclusion",
    ):
        assert q[key] == "success", (key, q[key])
    assert q["verify_summary_jobs"] == 50

    model = result["phase_model"]
    assert model["research_progression_closed"] is True
    assert model["regression_qualification_active"] is True
    assert model["s001_s002_s003_workflows_retained"] is True
    assert model["candidate_authority"] is False
    assert model["promotion_authority"] is False
    assert model["shipping_change_authority"] is False
    assert model["release_acceptance_authority"] is False
    assert model["s004_open"] is False

    for name in ("S001", "S002", "S003"):
        contract = load(ITER / f"{name}.json")
        assert contract["status"] == "ACTIVE_DIAGNOSTIC"
        assert contract["candidate_limit"] == 0
        assert contract["confirmation_limit"] == 0
        assert contract["promotion_allowed"] is False
        assert contract["shipping_change_allowed"] is False
        assert result["milestones"][name]["lifecycle"] == "ACTIVE_REGRESSION_DIAGNOSTIC"

    predecessor = result["immutable_predecessor_lineage"]
    assert predecessor["no_i041_parameter_search"] is True
    assert predecessor["aec_internal_mechanism_reopen_authorized"] is False

    geometry_result = load(GEOMETRY_RESULT)
    assert geometry_result["status"] == (
        "CLOSED_DIAGNOSTIC_NORMALIZED_GEOMETRY_CONFIRMED_MECHANISM_LINE_TERMINAL"
    )
    assert geometry_result["mechanism_line_closeout"]["terminal"] is True
    assert geometry_result["candidate_authority"] is False
    assert geometry_result["s004_open"] is False

    catalog = load(CATALOG)
    assert catalog["authority"] == (
        "diagnostic-regression-only-not-release-or-candidate-authority"
    )
    assert catalog["s004_candidate_authority"] is False
    supplemental = {
        item["replay_id"]: item
        for item in catalog.get("supplemental_replays", [])
    }
    replay_id = "SR-S003-AEC-ECHO-PATH-GEOMETRY-V1"
    assert replay_id in supplemental
    assert supplemental[replay_id]["authority"] == "supplemental-replay-only"
    assert supplemental[replay_id]["candidate_authority"] is False
    assert supplemental[replay_id]["release_acceptance_authority"] is False
    assert supplemental[replay_id]["s004_candidate_authority"] is False

    replay = load(GEOMETRY_REPLAY)
    assert replay["replay_id"] == replay_id
    assert replay["lifecycle_status"] == "OPEN_DIAGNOSTIC"
    assert replay["mechanism_lineage"]["first_observable_stage"] == "AEC"
    assert replay["mechanism_lineage"]["mechanism_coordinate"] == "G=R/M"
    assert replay["source_identity"]["seeds"] == [20307, 20507]
    assert replay["authority_boundary"]["may_reopen_internal_mechanism_search"] is False

    resources = load(RESOURCES)
    assert resources["authority"] == "build-and-resource-qualification-not-silicon-performance"
    assert set(resources["profiles"]) == {"conservative", "effect-first"}
    assert "cpu_ms_per_audio_second" in resources["silicon_calibration_required"]
    assert any(
        "must not be relabeled as SSC305 silicon timing" in rule
        for rule in resources["rules"]
    )

    admission = result["s004_admission"]
    assert admission["open"] is False
    assert admission["candidate_selected"] is False

    forbidden = result["forbidden_automatic_continuations"]
    assert any("I025-I040" in item for item in forbidden)
    assert any("q/rho/G/M/E/C" in item for item in forbidden)
    assert any("validation-grade or blind" in item for item in forbidden)

    triggers = {item["trigger"] for item in result["next_authorized_triggers"]}
    assert "durable replay drift" in triggers
    assert "SSC305 silicon measurements become available" in triggers

    print("system-robustness-v1 phase closeout: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
