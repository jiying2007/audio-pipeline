#!/usr/bin/env python3
"""Lock the reviewed terminal state of the S003 mic-mismatch source oracle."""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LIVE = ROOT / ".github/workflows/research-s003-mic-mismatch-measurement-oracle-v1.yml"
CONSUMED = ROOT / "tests/validation/data/s003-mic-mismatch-measurement-oracle-consumed-workflow.yml"
RESULT = ROOT / "docs/program/iterations/S003-mic-mismatch-measurement-domain-oracle-v1-result.json"
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
    assert "test_s003_mic_mismatch_measurement_oracle_retirement.py" in live

    assert "\n  workflow_dispatch:\n" in consumed
    assert "\n  push:\n" in consumed
    assert "Run fresh source-domain oracle controls" in consumed
    assert "9507 9607" in consumed
    assert "no_near_si_sdr_improvement_in_gate" in consumed
    assert "s003-mic-mismatch-measurement-oracle" in consumed

    assert result["status"] == "CLOSED_DIAGNOSTIC_MEASUREMENT_DOMAIN_ARTIFACT_EXCLUDED"
    assert result["investigation_terminal"] is True
    assert result["rerun_required"] is False
    execution = result["authoritative_execution"]
    assert execution["workflow_run_id"] == 36969688211
    assert execution["run_attempt"] == 1
    assert execution["head_sha"] == "7f0a68e6b573c8eaccaee064e4843b62c496ef7c"
    assert execution["artifact_id"] == 11210684570
    assert execution["artifact_zip_sha256"] == (
        "67f950f418486b23be847a21549d7e2dd6a71f81b3b3acf9a45e665e4c50ea5a"
    )

    oracle = result["oracle_scope"]
    assert oracle["scoped_failure"] == "FR-S003-MIC-GAIN-DELAY-MISMATCH-V1"
    assert oracle["scoped_subsignature"] == "severe-near-reference-degradation"
    assert oracle["pipeline_invoked"] is False
    assert oracle["pipeline_output_consumed"] is False
    assert oracle["near_si_sdr_improvement_consumed"] is False

    mechanical = result["mechanical_result"]
    assert mechanical["9507"] == {
        "oracle_valid_utterances": 8,
        "total_utterances": 8,
        "oracle_invalid_utterances": 0,
    }
    assert mechanical["9607"] == {
        "oracle_valid_utterances": 8,
        "total_utterances": 8,
        "oracle_invalid_utterances": 0,
    }
    assert mechanical["minimum_required_per_seed"] == 6
    assert mechanical["measurement_domain_artifact_exclusion_satisfied"] is True

    reviewed = result["reviewed_validity"]
    assert reviewed["measurement_domain_artifact_exclusion_sufficiently_proven"] is True
    assert reviewed["root_cause_claim_authority"] is False

    s004 = result["s004_review"]
    assert s004["open"] is False
    assert s004["candidate_authority"] is False
    assert "measurement_domain_artifact_exclusion" in s004["satisfied"]
    assert s004["missing"] == [
        "downstream_transfer_artifact_exclusion",
        "bounded_candidate_resource_fit",
    ]

    entry = json.loads(ENTRY.read_text(encoding="utf-8"))
    review = entry["measurement_domain_oracle_review"]
    assert review["review_status"] == "SOURCE_DOMAIN_ORACLE_VALIDATED"
    assert review["oracle_valid_utterances"] == {"9507": 8, "9607": 8}
    assert review["pipeline_output_consumed"] is False
    assert review["near_si_sdr_improvement_consumed"] is False
    assert review["measurement_domain_artifact_exclusion_satisfied"] is True
    assert "measurement_domain_artifact_exclusion" in entry["s004_eligibility"]["satisfied"]
    # The immutable measurement-oracle result freezes blockers at its review time.
    # The live replay entry may advance as later independent evidence closes the
    # downstream blocker, but resource fit must remain unresolved until a
    # separately reviewed admission envelope exists.
    assert entry["s004_eligibility"]["eligible"] is False
    assert "measurement_domain_artifact_exclusion" in entry["s004_eligibility"]["satisfied"]
    assert "bounded_candidate_resource_fit" in entry["s004_eligibility"]["missing"]

    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
    matches = [
        item for item in catalog["supplemental_evidence"]
        if item.get("kind") == "measurement-domain-source-oracle-review"
    ]
    assert len(matches) == 1
    item = matches[0]
    assert item["review_path"] == str(RESULT.relative_to(ROOT))
    assert item["workflow_run_id"] == 36969688211
    assert item["artifact_id"] == 11210684570
    assert item["measurement_domain_artifact_exclusion_satisfied"] is True
    assert item["s004_candidate_authority"] is False

    print("S003 mic-mismatch measurement oracle terminal state: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
