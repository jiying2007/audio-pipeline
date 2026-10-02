#!/usr/bin/env python3
"""Lock reviewed terminal state of S003 mic-mismatch downstream-transfer review."""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LIVE = ROOT / ".github/workflows/research-s003-mic-mismatch-downstream-transfer-v1.yml"
CONSUMED = ROOT / "tests/validation/data/s003-mic-mismatch-downstream-transfer-consumed-workflow.yml"
RESULT = ROOT / "docs/program/iterations/S003-mic-mismatch-downstream-transfer-exclusion-v1-result.json"
ENTRY = ROOT / "validation/failure-replay/entries/s003-mic-gain-delay-mismatch-v1.json"
CATALOG = ROOT / "validation/failure-replay/catalog.json"


def main() -> int:
    live = LIVE.read_text(encoding="utf-8")
    consumed = CONSUMED.read_text(encoding="utf-8")
    result = json.loads(RESULT.read_text(encoding="utf-8"))

    assert "\n  pull_request:\n" in live
    assert "\n  workflow_dispatch:\n" not in live
    assert "\n  push:\n" not in live
    assert "\n  schedule:\n" not in live
    jobs = re.findall(
        r"(?m)^  ([A-Za-z_][A-Za-z0-9_-]*):\s*$",
        live[live.index("\njobs:") + 1 :],
    )
    assert jobs == ["contract"], jobs
    assert "test_s003_mic_mismatch_downstream_transfer_retirement.py" in live

    assert "\n  workflow_dispatch:\n" in consumed
    assert "\n  push:\n" in consumed
    assert "Synthesize frozen public stage-prefix evidence" in consumed
    assert "downstream_transfer_artifact_exclusion_satisfied" in consumed
    assert "prefix-capture mask" in consumed

    assert result["status"] == "CLOSED_DIAGNOSTIC_DOWNSTREAM_TRANSFER_ARTIFACT_EXCLUDED"
    assert result["investigation_terminal"] is True
    assert result["rerun_required"] is False
    execution = result["authoritative_execution"]
    assert execution["workflow_run_id"] == 36971346158
    assert execution["head_sha"] == "a5b84b27f44ed6985262e20ce4f689e2bd137bd9"
    assert execution["artifact_id"] == 11211114715
    assert execution["artifact_zip_sha256"] == (
        "cc796af72e21a38f32774e4e70cce3c49f4dafb138f5900f5f21865d32a20d08"
    )
    assert execution["aggregate_member_sha256"] == (
        "196bb20e4aa7eb8c7ee003e005a733895026c8a4ff394b9d02c1512e5b5c6b43"
    )

    mechanical = result["mechanical_result"]
    assert mechanical["measurement_domain_artifact_exclusion_satisfied"] is True
    assert mechanical["prefix_capture_hpf_only"] is True
    assert mechanical["bf_enabled_at_prefix_capture"] is False
    assert mechanical["ns_enabled_at_prefix_capture"] is False
    assert mechanical["agc_enabled_at_prefix_capture"] is False
    assert mechanical["vad_enabled_at_prefix_capture"] is False
    assert mechanical["final_full_pipeline_reached_at_prefix_capture"] is False
    assert mechanical["downstream_transfer_artifact_exclusion_satisfied"] is True
    assert mechanical["dechorate"] == {
        "8307": {"severe_cases": 11, "capture_first_observable_cases": 11, "total_cases": 11},
        "8407": {"severe_cases": 11, "capture_first_observable_cases": 11, "total_cases": 11},
    }
    assert mechanical["slr31"] == {
        "9307": {"severe_cases": 8, "capture_first_observable_cases": 8, "total_cases": 8},
        "9407": {"severe_cases": 8, "capture_first_observable_cases": 8, "total_cases": 8},
    }

    reviewed = result["reviewed_validity"]
    assert reviewed["downstream_transfer_artifact_exclusion_sufficiently_proven"] is True
    assert reviewed["root_cause_claim_authority"] is False
    assert "HPF is the causal root cause" in reviewed["not_supported"]

    s004 = result["s004_review"]
    assert s004["open"] is False
    assert s004["candidate_authority"] is False
    assert "downstream_transfer_artifact_exclusion" in s004["satisfied"]
    assert s004["missing"] == ["bounded_candidate_resource_fit"]

    entry = json.loads(ENTRY.read_text(encoding="utf-8"))
    review = entry["downstream_transfer_review"]
    assert review["review_status"] == "DOWNSTREAM_TRANSFER_ARTIFACT_EXCLUDED"
    assert review["downstream_transfer_artifact_exclusion_satisfied"] is True
    assert review["prefix_capture_mask"] == "AP_STAGE_HPF"
    assert review["hpf_root_cause_claim_authority"] is False
    assert review["bf_root_cause_claim_authority"] is False
    assert "downstream_transfer_artifact_exclusion" in entry["s004_eligibility"]["satisfied"]
    assert entry["s004_eligibility"]["missing"] == ["bounded_candidate_resource_fit"]
    assert entry["s004_eligibility"]["eligible"] is False

    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
    matches = [
        item for item in catalog["supplemental_evidence"]
        if item.get("kind") == "downstream-transfer-artifact-exclusion-review"
    ]
    assert len(matches) == 1
    item = matches[0]
    assert item["review_path"] == str(RESULT.relative_to(ROOT))
    assert item["workflow_run_id"] == 36971346158
    assert item["artifact_id"] == 11211114715
    assert item["downstream_transfer_artifact_exclusion_satisfied"] is True
    assert item["s004_candidate_authority"] is False

    print("S003 mic-mismatch downstream-transfer terminal state: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
