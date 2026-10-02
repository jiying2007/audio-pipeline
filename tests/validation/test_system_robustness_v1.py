#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ITER = ROOT / "docs/program/iterations"
SCHEMA = ROOT / "validation/failure-replay/schema-v1.json"
RES = ROOT / "ci/ssc305-resource-profiles.json"
I040 = ROOT / ".github/research/continuous-optimization/development-v4/i040-ns-synthesis-overlap-add-transfer-decomposition-v1-result.json"


def main() -> int:
    items = {}
    for name in ("S001", "S002", "S003"):
        item = json.loads((ITER / f"{name}.json").read_text())
        items[name] = item
        assert item["candidate_limit"] == 0
        assert item["confirmation_limit"] == 0
        assert item["promotion_allowed"] is False
        assert item["shipping_change_allowed"] is False

    s002 = items["S002"]
    assert "validation/tools/build_aec_transition_corpus.py" in s002["source_assets"]
    assert "nonlinear_clipped_playback" in s002["required_conditions"]
    assert {"nlms_step_size", "dtd_threshold", "res_parameter_sweep"} <= set(s002["forbidden_search"])

    s003 = items["S003"]
    assert s003["fresh_seeds"] == [7307, 7407]
    assert s003["watch_contract"] == "docs/program/iterations/S001.json"
    assert s003["s004_candidate_authority"] is False
    assert s003["stage_prefix_profiles"] == [
        "prefix-capture", "prefix-bf", "prefix-sync", "prefix-aec",
        "prefix-res", "prefix-ns", "prefix-agc", "prefix-vad", "default",
    ]
    for path in s003["source_assets"]:
        assert (ROOT / path).is_file(), path

    watch = items["S001"]["diagnostic_watch"]
    assert watch["authority"] == "replay-trigger-only-not-release-acceptance-gate"
    assert watch["confirmation_seeds"] == [5307, 5407]
    assert {rule["id"] for rule in watch["rules"]} == {
        "severe-near-reference-degradation",
        "noise-amplification",
        "severe-vad-degradation",
    }

    schema = json.loads(SCHEMA.read_text())
    assert schema["properties"]["schema_version"]["const"] == 1
    assert "first_observable_stage" in schema["required"]

    resources = json.loads(RES.read_text())
    assert set(resources["profiles"]) == {"conservative", "effect-first"}
    assert resources["profiles"]["conservative"]["preset"] == "ssc305-cortex-a32-low"
    assert (
        "cpu_ms_per_audio_second"
        in resources["profiles"]["conservative"]["silicon_calibration_required"]
    )

    i040 = json.loads(I040.read_text())
    assert i040["research_line_terminal"] is True
    assert i040["proposed_followup_hypothesis"] is None

    print("system-robustness-v1 contracts: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
