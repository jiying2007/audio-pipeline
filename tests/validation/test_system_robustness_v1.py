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

    aec_safe = json.loads((ITER / "S003-aec-metric-safe-evidence-v1.json").read_text())
    assert aec_safe["authority"] == "CANDIDATE_ZERO_DIAGNOSTIC_ONLY"
    assert aec_safe["candidate_limit"] == 0 and aec_safe["confirmation_limit"] == 0
    assert aec_safe["promotion_allowed"] is False and aec_safe["shipping_change_allowed"] is False
    assert aec_safe["corpus"]["fresh_seeds"] == [10307, 10407]
    assert aec_safe["corpus"]["case_count"] == 8
    assert aec_safe["metric_applicability"]["near-end-only"]["forbidden_primary_metrics"] == ["near_si_sdr_improvement_db"]
    assert aec_safe["preregistered_rules"]["no_performance_threshold_search"] is True
    assert aec_safe["preregistered_rules"]["no_aec_parameter_search"] is True
    assert aec_safe["authority_boundary"]["may_open_s004"] is False

    recovery = json.loads((ITER / "S003-aec-transition-recovery-latency-v1.json").read_text())
    assert recovery["authority"] == "CANDIDATE_ZERO_MEASUREMENT_ONLY"
    assert recovery["candidate_limit"] == 0 and recovery["confirmation_limit"] == 0
    assert recovery["promotion_allowed"] is False and recovery["shipping_change_allowed"] is False
    assert recovery["corpus"]["fresh_seeds"] == [10507, 10607]
    assert recovery["corpus"]["target_cases"] == [
        "echo-path-change", "speaker-acoustic-gain-step", "render-level-step"
    ]
    assert recovery["measurement"]["window_ms"] == 100
    assert recovery["measurement"]["pre_baseline_ms"] == [-1000, -200]
    assert abs(recovery["measurement"]["recovery_excess_db"] - 3.01029995664) < 1e-12
    assert recovery["measurement"]["continuous_hold_ms"] == 300
    assert recovery["measurement"]["search_ms"] == [0, 2500]
    assert recovery["preregistered_rules"]["censored_is_valid_evidence_not_ci_failure"] is True
    assert recovery["preregistered_rules"]["no_recovery_time_pass_fail_threshold"] is True
    assert recovery["preregistered_rules"]["no_parameter_search"] is True
    assert recovery["authority_boundary"]["may_open_s004"] is False

    stage_recovery = json.loads((ITER / "S003-aec-transition-stage-recovery-decomposition-v1.json").read_text())
    assert stage_recovery["authority"] == "CANDIDATE_ZERO_STAGE_MEASUREMENT_ONLY"
    assert stage_recovery["candidate_limit"] == 0 and stage_recovery["confirmation_limit"] == 0
    assert stage_recovery["promotion_allowed"] is False and stage_recovery["shipping_change_allowed"] is False
    assert stage_recovery["corpus"]["fresh_seeds"] == [10707, 10807]
    assert stage_recovery["corpus"]["stage_profiles"] == [
        "prefix-aec", "prefix-res", "prefix-ns", "prefix-agc", "default",
    ]
    assert stage_recovery["corpus"]["cases_per_seed"] == 15
    assert stage_recovery["preregistered_rules"]["no_stage_recovery_pass_fail_threshold"] is True
    assert stage_recovery["preregistered_rules"]["no_parameter_search"] is True
    assert stage_recovery["authority_boundary"]["may_open_s004"] is False

    ns_confirm = json.loads((ITER / "S003-aec-speaker-gain-ns-recovery-extension-confirmation-v1.json").read_text())
    assert ns_confirm["authority"] == "CANDIDATE_ZERO_SINGLE_HYPOTHESIS_CONFIRMATION"
    assert ns_confirm["candidate_limit"] == 0 and ns_confirm["confirmation_limit"] == 0
    assert ns_confirm["corpus"]["fresh_seeds"] == [10907, 11007]
    assert ns_confirm["corpus"]["profiles"] == ["prefix-res", "prefix-ns", "default"]
    assert ns_confirm["hypothesis"]["gate"] == "ns_recovery_time_ms - res_recovery_time_ms >= 100"
    assert ns_confirm["preregistered_rules"]["no_ns_internal_parameter_search"] is True
    assert ns_confirm["authority_boundary"]["may_claim_ns_root_cause"] is False
    assert ns_confirm["authority_boundary"]["may_open_s004"] is False

    variability = json.loads((ITER / "S003-aec-recovery-variability-source-decomposition-v1.json").read_text())
    assert variability["authority"] == "CANDIDATE_ZERO_OBSERVATION_ONLY"
    assert variability["candidate_limit"] == 0 and variability["confirmation_limit"] == 0
    assert variability["promotion_allowed"] is False and variability["shipping_change_allowed"] is False
    assert variability["corpus"]["fresh_seeds"] == [11107, 11207, 11307, 11407]
    assert variability["corpus"]["cases_per_seed"] == 15
    assert variability["preregistered_rules"]["no_correlation_significance_threshold"] is True
    assert variability["preregistered_rules"]["no_root_cause_selection"] is True
    assert variability["preregistered_rules"]["no_parameter_search"] is True
    assert variability["authority_boundary"]["may_claim_causal_stage"] is False
    assert variability["authority_boundary"]["may_open_s004"] is False

    resolution = json.loads((ITER / "S003-aec-recovery-measurement-resolution-v1.json").read_text())
    assert resolution["authority"] == "CANDIDATE_ZERO_MEASUREMENT_ONLY"
    assert resolution["candidate_limit"] == 0 and resolution["confirmation_limit"] == 0
    assert resolution["promotion_allowed"] is False and resolution["shipping_change_allowed"] is False
    assert resolution["corpus"]["fresh_seeds"] == [11507, 11607, 11707, 11807]
    assert resolution["corpus"]["cases_per_seed"] == 15
    assert resolution["fixed_baseline"]["window_ms"] == 100
    assert resolution["paired_measurements"]["100ms"]["post_window_ms"] == 100
    assert resolution["paired_measurements"]["50ms"]["post_window_ms"] == 50
    assert resolution["paired_measurements"]["100ms"]["continuous_hold_ms"] == 300
    assert resolution["paired_measurements"]["50ms"]["continuous_hold_ms"] == 300
    assert resolution["preregistered_rules"]["no_multi_resolution_sweep_beyond_100_and_50_ms"] is True
    assert resolution["preregistered_rules"]["no_resolution_pass_fail_threshold"] is True
    assert resolution["preregistered_rules"]["no_parameter_search"] is True
    assert resolution["authority_boundary"]["may_claim_measurement_artifact"] is False
    assert resolution["authority_boundary"]["may_open_s004"] is False

    geometry = json.loads((ITER / "S003-aec-recovery-window-geometry-decomposition-v1.json").read_text())
    assert geometry["authority"] == "CANDIDATE_ZERO_MEASUREMENT_ONLY"
    assert geometry["candidate_limit"] == 0 and geometry["confirmation_limit"] == 0
    assert geometry["promotion_allowed"] is False and geometry["shipping_change_allowed"] is False
    assert geometry["corpus"]["fresh_seeds"] == [11907, 12007, 12107, 12207]
    assert [x["id"] for x in geometry["geometries"]] == ["100w-100s", "100w-50s", "50w-50s"]
    assert geometry["preregistered_rules"]["no_geometry_sweep_beyond_preregistered_three"] is True
    assert geometry["preregistered_rules"]["no_measurement_artifact_verdict_from_single_geometry_pair"] is True
    assert geometry["preregistered_rules"]["no_parameter_search"] is True
    assert geometry["authority_boundary"]["may_claim_measurement_artifact"] is False
    assert geometry["authority_boundary"]["may_open_s004"] is False

    geom_confirm = json.loads((ITER / "S003-aec-recovery-100w50s-geometry-confirmation-v1.json").read_text())
    assert geom_confirm["authority"] == "CANDIDATE_ZERO_MEASUREMENT_METHOD_CONFIRMATION_ONLY"
    assert geom_confirm["candidate_limit"] == 0 and geom_confirm["confirmation_limit"] == 0
    assert geom_confirm["promotion_allowed"] is False and geom_confirm["shipping_change_allowed"] is False
    assert geom_confirm["corpus"]["fresh_seeds"] == [12307, 12407, 12507, 12607]
    assert geom_confirm["hypothesis"]["compared_geometries"] == ["100w-100s", "100w-50s"]
    assert geom_confirm["hypothesis"]["confirmation_rule"]["minimum_non_worse_case_profiles"] == 13
    assert geom_confirm["preregistered_rules"]["either_outcome_is_valid_evidence"] is True
    assert geom_confirm["preregistered_rules"]["no_geometry_sweep"] is True
    assert geom_confirm["preregistered_rules"]["no_parameter_search"] is True
    assert geom_confirm["authority_boundary"]["may_open_s004"] is False

    rebaseline = json.loads((ITER / "S003-aec-recovery-rebaseline-100w50s-v1.json").read_text())
    assert rebaseline["authority"] == "CANDIDATE_ZERO_REBASELINE_ONLY"
    assert rebaseline["candidate_limit"] == 0 and rebaseline["confirmation_limit"] == 0
    assert rebaseline["promotion_allowed"] is False and rebaseline["shipping_change_allowed"] is False
    assert rebaseline["corpus"]["fresh_seeds"] == [12707, 12807, 12907, 13007]
    assert rebaseline["measurement"]["geometry_id"] == "100w-50s"
    assert rebaseline["measurement"]["post_window_ms"] == 100
    assert rebaseline["measurement"]["post_stride_ms"] == 50
    assert rebaseline["retention_rule"]["minimum_nonzero_delta_ms"] == 50
    assert rebaseline["preregistered_rules"]["rejected_ns_hypothesis_remains_rejected"] is True
    assert rebaseline["preregistered_rules"]["no_parameter_search"] is True
    assert rebaseline["authority_boundary"]["may_claim_causal_stage"] is False
    assert rebaseline["authority_boundary"]["may_open_s004"] is False

    echo_confirm = json.loads((ITER / "S003-aec-echo-path-res-ns-recovery-extension-confirmation-v1.json").read_text())
    assert echo_confirm["authority"] == "CANDIDATE_ZERO_SINGLE_HYPOTHESIS_CONFIRMATION"
    assert echo_confirm["candidate_limit"] == 0 and echo_confirm["confirmation_limit"] == 0
    assert echo_confirm["corpus"]["fresh_seeds"] == [13107, 13207, 13307, 13407]
    assert echo_confirm["hypothesis"]["gate"] == "ns_recovery_time_ms - res_recovery_time_ms >= 50"
    assert echo_confirm["measurement"]["geometry_id"] == "100w-50s"
    assert echo_confirm["preregistered_rules"]["either_outcome_is_valid_evidence"] is True
    assert echo_confirm["preregistered_rules"]["no_ns_internal_parameter_search"] is True
    assert echo_confirm["authority_boundary"]["may_claim_ns_root_cause"] is False
    assert echo_confirm["authority_boundary"]["may_open_s004"] is False

    ns_state = json.loads((ITER / "S003-aec-echo-path-ns-state-decomposition-v1.json").read_text())
    assert ns_state["authority"] == "CANDIDATE_ZERO_INTERNAL_STATE_OBSERVATION_ONLY"
    assert ns_state["candidate_limit"] == 0 and ns_state["confirmation_limit"] == 0
    assert ns_state["promotion_allowed"] is False and ns_state["shipping_change_allowed"] is False
    assert ns_state["corpus"]["fresh_seeds"] == [13507, 13607, 13707, 13807]
    assert ns_state["corpus"]["profiles"] == ["prefix-res", "prefix-ns", "default"]
    assert ns_state["measurement"]["geometry_id"] == "100w-50s"
    assert ns_state["probe"]["required_output_equivalence"].startswith("bitwise identical")
    assert ns_state["preregistered_rules"]["extension_reproduction_is_applicability_condition"] is True
    assert ns_state["preregistered_rules"]["non_reproduction_is_valid_evidence"] is True
    assert ns_state["preregistered_rules"]["no_state_threshold_fitting"] is True
    assert ns_state["preregistered_rules"]["no_state_family_ranking"] is True
    assert ns_state["preregistered_rules"]["no_ns_parameter_search"] is True
    assert ns_state["authority_boundary"]["may_claim_ns_root_cause"] is False
    assert ns_state["authority_boundary"]["may_open_s004"] is False

    sign_var = json.loads((ITER / "S003-aec-echo-path-recovery-sign-variability-v1.json").read_text())
    assert sign_var["authority"] == "CANDIDATE_ZERO_SIGN_VARIABILITY_OBSERVATION_ONLY"
    assert sign_var["candidate_limit"] == 0 and sign_var["confirmation_limit"] == 0
    assert sign_var["promotion_allowed"] is False and sign_var["shipping_change_allowed"] is False
    assert sign_var["corpus"]["fresh_seeds"] == [13907, 14007, 14107, 14207, 14307, 14407, 14507, 14607]
    assert sign_var["corpus"]["profiles"] == ["prefix-res", "prefix-ns", "default"]
    assert sign_var["measurement"]["geometry_id"] == "100w-50s"
    assert sign_var["state_probe"]["fixed_transition_relative_snapshots_ms"] == [0, 50, 100, 150, 200, 250, 300, 400]
    assert sign_var["preregistered_rules"]["retain_all_sign_classes"] is True
    assert sign_var["preregistered_rules"]["no_sign_bucket_selection_for_candidate"] is True
    assert sign_var["preregistered_rules"]["no_state_family_ranking"] is True
    assert sign_var["preregistered_rules"]["no_root_cause_selection"] is True
    assert sign_var["preregistered_rules"]["no_recovery_threshold_search"] is True
    assert sign_var["authority_boundary"]["may_open_s004"] is False

    res_side = json.loads((ITER / "S003-aec-echo-path-res-side-recovery-variability-v1.json").read_text())
    assert res_side["authority"] == "CANDIDATE_ZERO_RES_SIDE_OBSERVATION_ONLY"
    assert res_side["candidate_limit"] == 0 and res_side["confirmation_limit"] == 0
    assert res_side["promotion_allowed"] is False and res_side["shipping_change_allowed"] is False
    assert res_side["corpus"]["fresh_seeds"] == [14707, 14807, 14907, 15007, 15107, 15207, 15307, 15407]
    assert res_side["corpus"]["profiles"] == ["prefix-aec", "prefix-res", "prefix-ns", "default"]
    assert res_side["measurement"]["geometry_id"] == "100w-50s"
    assert res_side["res_probe"]["fixed_transition_relative_snapshots_ms"] == [0, 50, 100, 150, 200, 250, 300, 400]
    assert res_side["preregistered_rules"]["retain_all_fresh_seeds"] is True
    assert res_side["preregistered_rules"]["no_res_gain_threshold_fitting"] is True
    assert res_side["preregistered_rules"]["no_root_cause_selection"] is True
    assert res_side["preregistered_rules"]["no_res_alpha_or_gain_search"] is True
    assert res_side["authority_boundary"]["may_open_s004"] is False

    contribution = json.loads((ITER / "S003-aec-echo-path-res-gain-contribution-decomposition-v1.json").read_text())
    assert contribution["authority"] == "CANDIDATE_ZERO_COUNTERFACTUAL_ANALYSIS_ONLY"
    assert contribution["candidate_limit"] == 0 and contribution["confirmation_limit"] == 0
    assert contribution["promotion_allowed"] is False and contribution["shipping_change_allowed"] is False
    assert contribution["corpus"]["fresh_seeds"] == [15507, 15607, 15707, 15807, 15907, 16007, 16107, 16207]
    assert contribution["corpus"]["profiles"] == ["prefix-aec", "prefix-res"]
    assert contribution["measurement"]["geometry_id"] == "100w-50s"
    assert contribution["shipping_res_formula"]["floor_gain"] == 0.10
    assert contribution["shipping_res_formula"]["normal_release_alpha"] == 0.08
    assert contribution["probe"]["per_frame_formula_validation"]["max_abs_error"] == 1e-5
    assert all(contribution["validity_gates"].values())
    assert contribution["preregistered_rules"]["no_gain_or_alpha_search"] is True
    assert contribution["preregistered_rules"]["no_counterfactual_parameter_sweep"] is True
    assert contribution["preregistered_rules"]["no_root_cause_selection"] is True
    assert contribution["authority_boundary"]["may_open_s004"] is False

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
