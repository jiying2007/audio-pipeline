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

    cross = json.loads((ITER / "S003-cross-source-artifact-exclusion-v1.json").read_text())
    assert cross["authority"] == "CANDIDATE_ZERO_DIAGNOSTIC_ONLY"
    assert cross["candidate_limit"] == 0 and cross["confirmation_limit"] == 0
    assert cross["promotion_allowed"] is False and cross["shipping_change_allowed"] is False
    assert cross["fresh_seeds"] == [8307, 8407]
    assert cross["public_source"]["expected_room_count"] == 11
    assert cross["preregistered_evidence_rules"]["minimum_exact_rooms_per_seed"] == 6
    assert cross["authority_boundary"]["may_open_s004"] is False

    slr31 = json.loads((ITER / "S003-public-clean-speech-subsig-transfer-v1.json").read_text())
    assert slr31["authority"] == "CANDIDATE_ZERO_DIAGNOSTIC_ONLY"
    assert slr31["candidate_limit"] == 0 and slr31["confirmation_limit"] == 0
    assert slr31["promotion_allowed"] is False and slr31["shipping_change_allowed"] is False
    assert slr31["fresh_seeds"] == [9307, 9407]
    assert slr31["microset"]["utterance_count"] == 8
    assert slr31["microset"]["require_unique_speakers"] is True
    assert slr31["preregistered_evidence_rules"]["minimum_reproduced_utterances_per_seed"] == 6
    assert slr31["preregistered_evidence_rules"]["required_subsignature"] == "severe-near-reference-degradation"
    assert slr31["authority_boundary"]["may_open_s004"] is False

    oracle = json.loads((ITER / "S003-mic-mismatch-measurement-domain-oracle-v1.json").read_text())
    assert oracle["authority"] == "CANDIDATE_ZERO_DIAGNOSTIC_ONLY"
    assert oracle["candidate_limit"] == 0 and oracle["confirmation_limit"] == 0
    assert oracle["promotion_allowed"] is False and oracle["shipping_change_allowed"] is False
    assert oracle["fresh_seeds"] == [9507, 9607]
    assert oracle["fixed_utterance_count"] == 8
    assert oracle["preregistered_evidence_rules"]["minimum_oracle_valid_utterances_per_seed"] == 6
    assert oracle["preregistered_evidence_rules"]["no_pipeline_output_metrics_in_gate"] is True
    assert oracle["preregistered_evidence_rules"]["no_near_si_sdr_improvement_in_gate"] is True
    assert oracle["authority_boundary"]["may_open_s004"] is False

    downstream = json.loads((ITER / "S003-mic-mismatch-downstream-transfer-exclusion-v1.json").read_text())
    assert downstream["authority"] == "CANDIDATE_ZERO_EVIDENCE_SYNTHESIS_ONLY"
    assert downstream["candidate_limit"] == 0 and downstream["confirmation_limit"] == 0
    assert downstream["promotion_allowed"] is False and downstream["shipping_change_allowed"] is False
    assert downstream["scoped_failure"] == "FR-S003-MIC-GAIN-DELAY-MISMATCH-V1"
    assert downstream["scoped_subsignature"] == "severe-near-reference-degradation"
    assert downstream["stage_semantics"]["capture_prefix_required_mask"] == "AP_STAGE_HPF"
    assert downstream["authority_boundary"]["may_claim_hpf_root_cause"] is False
    assert downstream["authority_boundary"]["may_claim_bf_root_cause"] is False
    assert downstream["authority_boundary"]["may_open_s004"] is False

    hpf_ref = json.loads((ITER / "S003-mic-mismatch-hpf-aware-reference-oracle-v1.json").read_text())
    assert hpf_ref["authority"] == "CANDIDATE_ZERO_DIAGNOSTIC_ONLY"
    assert hpf_ref["candidate_limit"] == 0 and hpf_ref["confirmation_limit"] == 0
    assert hpf_ref["promotion_allowed"] is False and hpf_ref["shipping_change_allowed"] is False
    assert hpf_ref["fresh_seeds"] == [9707, 9807]
    assert hpf_ref["fixed_utterance_count"] == 8
    assert hpf_ref["oracle"]["original_watch_limit_db"] == -10.0
    assert hpf_ref["preregistered_evidence_rules"]["minimum_artifact_cases_per_seed"] == 6
    assert hpf_ref["authority_boundary"]["may_open_s004"] is False

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
    assert resources["schema_version"] == 2
    assert resources["authority"] == "build-and-resource-qualification-not-silicon-performance"
    assert set(resources["profiles"]) == {"conservative", "effect-first"}
    assert resources["profiles"]["conservative"]["preset"] == "ssc305-cortex-a32-low"
    assert resources["profiles"]["effect-first"]["preset"] == "cortex-a32-neon"
    assert "qemu_deterministic_execution" in resources["qualify_now"]
    assert "cpu_ms_per_audio_second" in resources["silicon_calibration_required"]
    assert "frame_p99_ms" in resources["silicon_calibration_required"]

    i040 = json.loads(I040.read_text())
    assert i040["research_line_terminal"] is True
    assert i040["proposed_followup_hypothesis"] is None

    print("system-robustness-v1 contracts: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
