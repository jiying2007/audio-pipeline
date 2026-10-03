#!/usr/bin/env python3
"""Lock the reviewed terminal state of S003 SLR31 subsignature transfer."""

from __future__ import annotations

import json
import re
from pathlib import Path
from retired_workflow_contract import assert_contract_or_retired

ROOT = Path(__file__).resolve().parents[2]
LIVE = ROOT / ".github/workflows/research-s003-slr31-subsig-transfer-v1.yml"
CONSUMED = ROOT / "tests/validation/data/s003-slr31-consumed-workflow.yml"
RESULT = ROOT / "docs/program/iterations/S003-public-clean-speech-subsig-transfer-v1-result.json"
CATALOG = ROOT / "validation/failure-replay/catalog.json"
CAPTURE = ROOT / "validation/failure-replay/entries/s003-capture-clipping-v1.json"
MISMATCH = ROOT / "validation/failure-replay/entries/s003-mic-gain-delay-mismatch-v1.json"


def main() -> int:
    assert_contract_or_retired(ROOT, LIVE, Path(__file__).name)
    consumed = CONSUMED.read_text(encoding="utf-8")
    result = json.loads(RESULT.read_text(encoding="utf-8"))

    assert "\n  workflow_dispatch:\n" in consumed
    assert "\n  push:\n" in consumed
    assert "Run fresh SLR31 stage-prefix diagnostics" in consumed
    assert "9307 9407" in consumed
    assert "minimum_reproduced_utterances_per_seed" in consumed
    assert "soundfile==0.13.1" in consumed

    assert result["status"] == "CLOSED_DIAGNOSTIC_SECOND_PUBLIC_FAMILY_REPETITION"
    assert result["investigation_terminal"] is True
    assert result["rerun_required"] is False
    execution = result["authoritative_execution"]
    assert execution["workflow_run_id"] == 36965720270
    assert execution["run_attempt"] == 1
    assert execution["head_sha"] == "61d7e5ac95ff113ebac0ad7753a9303f8c8aaa32"
    assert execution["artifact_id"] == 11210085727
    assert execution["artifact_zip_sha256"] == (
        "694f8d9e5b85b103893488ade95cb500e2dfd446940d2fc968e870b6e18e2b1b"
    )
    assert execution["aggregate_member_sha256"] == (
        "654763f7c599f83b33d015732d90178631ee7be433ee0960176c5751610fdb28"
    )

    source = result["source_review"]
    assert source["fixed_utterance_count"] == 8
    assert source["fixed_unique_speaker_count"] == 8
    assert len(source["selected_microset"]) == 8
    assert len({item["speaker_id"] for item in source["selected_microset"]}) == 8
    assert source["archive_sha256"] == (
        "47805806c8b15f7549f3c51bd6b7da72ec0128a34d32830c8014a88658c0292d"
    )

    capture = result["mechanical_result"]["FR-S003-CAPTURE-CLIPPING-V1"]
    mismatch = result["mechanical_result"]["FR-S003-MIC-GAIN-DELAY-MISMATCH-V1"]
    assert capture["reproduced_utterances"] == {"9307": 0, "9407": 0}
    assert capture["second_public_family_repetition_satisfied"] is False
    assert mismatch["reproduced_utterances"] == {"9307": 8, "9407": 8}
    assert mismatch["second_public_family_repetition_satisfied"] is True
    assert mismatch["first_observable_stage_distribution"] == {
        "9307": {"capture": 8},
        "9407": {"capture": 8},
    }

    review = result["s004_review"]
    assert review["open"] is False
    assert review["candidate_authority"] is False
    assert "multiple_independent_public_dataset_repetition_of_candidate_relevant_signature" in review["satisfied"]
    assert review["missing"] == [
        "measurement_domain_artifact_exclusion",
        "downstream_transfer_artifact_exclusion",
        "bounded_candidate_resource_fit",
    ]

    capture_entry = json.loads(CAPTURE.read_text(encoding="utf-8"))
    cap_review = capture_entry["public_clean_speech_review"]
    assert cap_review["second_public_family_repetition_satisfied"] is False
    assert cap_review["reproduced_utterances"] == {"9307": 0, "9407": 0}
    assert "multiple_independent_public_dataset_repetition_of_candidate_relevant_signature" in capture_entry["s004_eligibility"]["missing"]

    mismatch_entry = json.loads(MISMATCH.read_text(encoding="utf-8"))
    mm_review = mismatch_entry["public_clean_speech_review"]
    assert mm_review["second_public_family_repetition_satisfied"] is True
    assert mm_review["reproduced_utterances"] == {"9307": 8, "9407": 8}
    # The immutable SLR31 result freezes the blockers at review time. The live
    # replay entry may legitimately advance as later independent evidence closes
    # blockers, but it must never lose the SLR31 multi-public evidence or grant
    # candidate authority implicitly.
    assert mismatch_entry["s004_eligibility"]["eligible"] is False
    if mismatch_entry["s004_eligibility"].get("status") == "TERMINAL_REJECTED_METRIC_REFERENCE_ARTIFACT":
        assert "multiple_independent_public_dataset_repetition_of_candidate_relevant_signature" in mismatch_entry["s004_eligibility"]["historical_satisfied"]
        assert mismatch_entry["s004_eligibility"]["not_applicable"] == ["bounded_candidate_resource_fit"]
    else:
        assert "multiple_independent_public_dataset_repetition_of_candidate_relevant_signature" in mismatch_entry["s004_eligibility"]["satisfied"]
        assert "bounded_candidate_resource_fit" in mismatch_entry["s004_eligibility"]["missing"]

    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
    slr = [
        item for item in catalog["supplemental_evidence"]
        if item.get("kind") == "public-clean-speech-subsig-transfer-review"
    ]
    assert len(slr) == 1
    assert slr[0]["review_path"] == str(RESULT.relative_to(ROOT))
    assert slr[0]["workflow_run_id"] == 36965720270
    assert slr[0]["artifact_id"] == 11210085727
    assert slr[0]["s004_candidate_authority"] is False

    print("S003 SLR31 reviewed terminal state: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
