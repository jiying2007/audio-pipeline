#!/usr/bin/env python3
"""Lock terminal rejection of the S003 mic-mismatch severe sub-signature."""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LIVE = ROOT / ".github/workflows/research-s003-hpf-aware-reference-oracle-v1.yml"
CONSUMED = ROOT / "tests/validation/data/s003-hpf-aware-reference-consumed-workflow.yml"
RESULT = ROOT / "docs/program/iterations/S003-mic-mismatch-hpf-aware-reference-oracle-v1-result.json"
ENTRY = ROOT / "validation/failure-replay/entries/s003-mic-gain-delay-mismatch-v1.json"
CATALOG = ROOT / "validation/failure-replay/catalog.json"


def main() -> int:
    live = LIVE.read_text(encoding="utf-8")
    consumed = CONSUMED.read_text(encoding="utf-8")
    result = json.loads(RESULT.read_text(encoding="utf-8"))

    assert "\n  pull_request:\n" in live
    assert "\n  push:\n" not in live
    assert "\n  workflow_dispatch:\n" not in live
    assert "\n  schedule:\n" not in live
    jobs = re.findall(
        r"(?m)^  ([A-Za-z_][A-Za-z0-9_-]*):\s*$",
        live[live.index("\njobs:") + 1 :],
    )
    assert jobs == ["contract"], jobs
    assert "test_s003_hpf_aware_reference_retirement.py" in live

    assert "\n  push:\n" in consumed
    assert "\n  workflow_dispatch:\n" in consumed
    assert "Run fresh HPF-aware reference controls" in consumed
    assert "9707 9807" in consumed
    assert "candidate_relevant_subsignature_valid" in consumed
    assert "right-channel-affects" in consumed

    assert result["status"] == "CLOSED_DIAGNOSTIC_METRIC_REFERENCE_ARTIFACT_REJECTED"
    assert result["investigation_terminal"] is True
    assert result["rerun_required"] is False
    execution = result["authoritative_execution"]
    assert execution["workflow_run_id"] == 36979768886
    assert execution["head_sha"] == "1b56ca91a1fc9f97bf9c5e22feeeeb38b55a72ed"
    assert execution["artifact_id"] == 11215231517
    assert execution["artifact_zip_sha256"] == (
        "47df4da418467c3912296897f8047bb55f76b6fbb50bf32afb702f4935574ebb"
    )

    mechanical = result["mechanical_result"]
    for seed in ("9707", "9807"):
        assert mechanical[seed] == {
            "current_severe_cases": 8,
            "hpf_aware_severe_cases": 0,
            "reference_metric_artifact_cases": 8,
            "right_channel_affects_prefix_capture_cases": 0,
            "total_cases": 8,
            "gate_satisfied": True,
        }
    assert mechanical["metric_reference_domain_artifact_detected"] is True
    assert mechanical["candidate_relevant_subsignature_valid"] is False

    reviewed = result["reviewed_validity"]
    assert reviewed["metric_reference_domain_artifact_sufficiently_proven"] is True
    assert reviewed["candidate_admission_measurement_domain_exclusion_satisfied"] is False
    assert reviewed["root_cause_claim_authority"] is False

    line = result["candidate_line_review"]
    assert line["status"] == "TERMINAL_REJECTED_METRIC_REFERENCE_ARTIFACT"
    assert line["s004_open"] is False
    assert line["candidate_authority"] is False
    assert line["resource_fit_required"] is False
    assert line["resource_fit_status"] == "NOT_APPLICABLE_AFTER_TERMINAL_REJECTION"

    qualification = result["qualification"]
    assert qualification["verify_run_id"] == 36979769108
    assert qualification["verify_conclusion"] == "success"
    assert qualification["system_robustness_run_id"] == 36979768921
    assert qualification["system_robustness_conclusion"] == "success"
    assert qualification["hosted_real_audio_conclusion"] == "success"
    assert qualification["hosted_real_aec_conclusion"] == "success"
    assert qualification["program_archive_conclusion"] == "success"
    assert qualification["i015_finalization_conclusion"] == "success"
    assert qualification["release_conclusion"] == "success"

    entry = json.loads(ENTRY.read_text(encoding="utf-8"))
    assert entry["candidate_line_status"] == "TERMINAL_REJECTED_METRIC_REFERENCE_ARTIFACT"
    review = entry["metric_reference_oracle_review"]
    assert review["review_status"] == "HPF_AWARE_REFERENCE_ARTIFACT_CONFIRMED"
    assert review["current_severe_cases"] == {"9707": 8, "9807": 8}
    assert review["hpf_aware_severe_cases"] == {"9707": 0, "9807": 0}
    assert review["reference_metric_artifact_cases"] == {"9707": 8, "9807": 8}
    assert review["right_channel_affects_prefix_capture_cases"] == {"9707": 0, "9807": 0}
    assert review["metric_reference_domain_artifact_detected"] is True
    assert review["candidate_relevant_subsignature_valid"] is False

    s004 = entry["s004_eligibility"]
    assert s004["status"] == "TERMINAL_REJECTED_METRIC_REFERENCE_ARTIFACT"
    assert s004["eligible"] is False
    assert "candidate_admission_measurement_domain_artifact_exclusion" in s004["failed"]
    assert s004["not_applicable"] == ["bounded_candidate_resource_fit"]

    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
    matches = [
        item for item in catalog["supplemental_evidence"]
        if item.get("kind") == "metric-reference-domain-artifact-review"
    ]
    assert len(matches) == 1
    item = matches[0]
    assert item["review_path"] == str(RESULT.relative_to(ROOT))
    assert item["workflow_run_id"] == 36979768886
    assert item["artifact_id"] == 11215231517
    assert item["metric_reference_domain_artifact_detected"] is True
    assert item["candidate_relevant_subsignature_valid"] is False
    assert item["s004_candidate_authority"] is False

    print("S003 HPF-aware reference terminal rejection: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
