#!/usr/bin/env python3
"""Lock the reviewed terminal state of S003 dEchorate cross-source diagnosis."""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LIVE = ROOT / ".github/workflows/research-s003-cross-source-artifact-exclusion-v1.yml"
CONSUMED = ROOT / "tests/validation/data/s003-cross-source-consumed-workflow.yml"
RESULT = ROOT / "docs/program/iterations/S003-cross-source-artifact-exclusion-v1-result.json"
CATALOG = ROOT / "validation/failure-replay/catalog.json"
ENTRIES = [
    ROOT / "validation/failure-replay/entries/s003-capture-clipping-v1.json",
    ROOT / "validation/failure-replay/entries/s003-mic-gain-delay-mismatch-v1.json",
]


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
    assert "test_s003_cross_source_retirement.py" in live

    assert "\n  workflow_dispatch:\n" in consumed
    assert "\n  push:\n" in consumed
    assert "Run fresh dEchorate stage-prefix diagnostics" in consumed
    assert "8307 8407" in consumed
    assert "minimum_exact_rooms_per_seed" in consumed

    assert result["status"] == "CLOSED_DIAGNOSTIC_ONLY_PARTIAL_SUBSIGNATURE_TRANSFER"
    assert result["investigation_terminal"] is True
    assert result["rerun_required"] is False
    assert result["authoritative_execution"]["workflow_run_id"] == 36960922825
    assert result["authoritative_execution"]["run_attempt"] == 1
    assert result["authoritative_execution"]["head_sha"] == (
        "4d4ef43f869e5e52bc6dabc53ffbe77fb11ca358"
    )
    assert result["authoritative_execution"]["artifact_id"] == 11207877723
    assert result["authoritative_execution"]["artifact_zip_sha256"] == (
        "62625c7b72cee6205c84e50135fd5366994544c18d6b2ce7fe14670abd6fb732"
    )
    assert result["authoritative_execution"]["aggregate_member_sha256"] == (
        "07a3cae7f0cf27f0724ec2af38c7eecb050a88f59f95e06a476d674e53869d98"
    )
    assert result["reviewed_validity"]["exact_full_signature_cross_source_reproduction_supported"] is False
    assert result["reviewed_validity"]["stable_severe_near_reference_subsignature_transfer_supported"] is True
    assert result["reviewed_validity"]["noise_amplification_cross_source_transfer_supported"] is False
    assert result["reviewed_validity"]["measurement_domain_artifact_exclusion_sufficiently_proven"] is False
    assert result["reviewed_validity"]["downstream_transfer_artifact_exclusion_sufficiently_proven"] is False
    assert result["s004_review"]["open"] is False
    assert result["s004_review"]["candidate_authority"] is False
    assert result["source_review"]["public_dataset_families_counted_toward_multi_dataset_gate"] == 1

    clip = result["mechanical_result"]["FR-S003-CAPTURE-CLIPPING-V1"]
    mismatch = result["mechanical_result"]["FR-S003-MIC-GAIN-DELAY-MISMATCH-V1"]
    for item in (clip, mismatch):
        assert item["exact_full_durable_signature_rooms"] == {"8307": 0, "8407": 0}
        assert item["raw_watch_clear_rooms"] == {"8307": 11, "8407": 11}
        assert item["stable_subsignature_rooms"] == {"8307": 11, "8407": 11}
        assert item["stable_public_subsignature"] == ["severe-near-reference-degradation"]
        assert item["absent_original_signature_component"] == ["noise-amplification"]
    assert clip["first_observable_stage_distribution"] == {
        "8307": {"NS": 7, "AGC": 4},
        "8407": {"NS": 6, "AGC": 5},
    }
    assert mismatch["first_observable_stage_distribution"] == {
        "8307": {"capture": 11},
        "8407": {"capture": 11},
    }

    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
    supplemental = catalog["supplemental_evidence"]
    assert len(supplemental) == 1
    assert supplemental[0]["review_path"] == str(RESULT.relative_to(ROOT))
    assert supplemental[0]["workflow_run_id"] == 36960922825
    assert supplemental[0]["s004_candidate_authority"] is False

    for path in ENTRIES:
        entry = json.loads(path.read_text(encoding="utf-8"))
        review = entry["public_cross_source_review"]
        assert review["review_status"] == "PARTIAL_SUBSIGNATURE_REPRODUCTION_ONLY"
        assert review["exact_full_durable_signature_rooms"] == {"8307": 0, "8407": 0}
        assert review["stable_subsignature_rooms"] == {"8307": 11, "8407": 11}
        assert review["raw_watch_clear_authority"] == (
            "SANITY_ONLY_NOT_SUFFICIENT_FOR_MEASUREMENT_DOMAIN_ARTIFACT_EXCLUSION"
        )
        assert review["measurement_domain_artifact_exclusion_status"] == "UNRESOLVED"
        assert entry["s004_eligibility"]["eligible"] is False
        assert "multiple_independent_public_dataset_repetition_of_candidate_relevant_signature" in entry["s004_eligibility"]["missing"]
        assert "measurement_domain_artifact_exclusion" in entry["s004_eligibility"]["missing"]
        assert "downstream_transfer_artifact_exclusion" in entry["s004_eligibility"]["missing"]
        assert "bounded_candidate_resource_fit" in entry["s004_eligibility"]["missing"]

    print("S003 dEchorate reviewed terminal state: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
