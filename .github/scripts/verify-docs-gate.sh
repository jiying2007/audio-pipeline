#!/bin/sh
# One offline documentation/assurance gate for docs-only and full verification.
# I010 is terminal: validate the current registry, never require retired live inputs.
set -eu

python3 tests/validation/frontend_evolution/test_contracts.py
python3 scripts/ci_impact.py --self-test
python3 tests/validation/test_immutable_whitespace.py
python3 tests/validation/frontend_evolution/test_device_capture.py
python3 scripts/github_governance.py --self-test
python3 scripts/resource_baseline.py --self-test
python3 scripts/docs_consistency.py --self-test
python3 tests/test_ci_evidence_transport.py
python3 scripts/research_registry.py --self-test
python3 scripts/prepare_release.py --self-test
python3 scripts/release_manifest.py --self-test
python3 scripts/post_release_status.py --self-test
python3 scripts/qualification_fingerprint.py --self-test
python3 .github/research/continuous-optimization/hosted-validation/public_candidate_pair.py --source-root . --self-test
python3 .github/program/acoustic_terminal_registry.py --self-test
python3 .github/program/acoustic_terminal_registry.py --check
python3 tests/validation/i010_ns_vad_observation.py --self-test
python3 tests/validation/i010_apply_vad_pre_ns_candidate.py --self-test
python3 tests/validation/i010_vad_pre_ns_candidate.py --self-test
python3 .github/research/continuous-optimization/source_candidate_authority_v2.py --self-test
python3 .github/research/continuous-optimization/source_candidate_execution_v2_contract.py --self-test --check
python3 -m json.tool .github/research/evidence-index.json >/dev/null
python3 -m json.tool .github/research/qualification-policy.json >/dev/null
python3 scripts/docs_consistency.py
python3 tests/validation/frontend_evolution/test_libfvad_reference.py
python3 tests/validation/frontend_evolution/array_qualification.py --self-test
python3 tests/validation/frontend_evolution/test_speech_spatial.py
python3 tests/validation/frontend_evolution/doa_observability_a0.py --self-test
python3 tests/validation/frontend_evolution/doa_gccphat_a1.py --self-test
python3 tests/validation/frontend_evolution/realman_source_metadata_d0.py --self-test
python3 tests/validation/frontend_evolution/realman_val_csv_d1.py self-test
python3 tests/validation/frontend_evolution/realman_scene_tree_d2_s0.py self-test
python3 tests/validation/frontend_evolution/realman_single_archive_d2_s1.py self-test
python3 tests/validation/frontend_evolution/realman_flac_quartets_d2_s2.py self-test
python3 tests/validation/frontend_evolution/realman_flac_decoder_toolchain_d2_t0.py self-test
python3 tests/validation/frontend_evolution/realman_pcm_reference_d2_s3r.py self-test
python3 tests/validation/frontend_evolution/realman_timebase_authority_d2_s4.py self-test
python3 tests/validation/frontend_evolution/realman_pypdf_toolchain_d2_s5_t0.py self-test
python3 tests/validation/frontend_evolution/realman_paper_clock_witness_d2_s5r.py self-test
python3 tests/validation/frontend_evolution/realman_gym_lag_diagnostic_d2_s6.py self-test
python3 tests/validation/frontend_evolution/fe09_array_abi_contract_r1.py --self-test
python3 tests/validation/frontend_evolution/fe09_array_abi_contract_r1.py --check
# Bind the reviewed patch-maintenance bytes, then run both original preflights
# and their negatives on exact reconstructed historical source copies.
python3 tests/validation/frontend_evolution/fe09_runtime_maintenance_rebind.py --self-test --check
python3 tests/validation/frontend_evolution/fe09_b1a_ingress_qualification.py --self-test
python3 tests/validation/frontend_evolution/fe09_b1b0_src_qualification.py --self-test
python3 tests/validation/frontend_evolution/fe09_b1b1_single_bf_qualification.py --self-test
# Preserve six original scientific self-tests and verify the versioned
# historical/current source boundary plus its independent receipt negatives.
python3 tests/validation/frontend_evolution/fe09_runtime_source_boundary.py --self-test
python3 tests/validation/frontend_evolution/fe09_b2s3_t2b_b0_capture_only_qualification.py --self-test
python3 tests/validation/frontend_evolution/fe09_b2s3_t2b_b1s0_owner_spsc_qualification.py --self-test
python3 tests/validation/frontend_evolution/fe09_b2s3_t2b_b1s1_source_chunks_qualification.py --self-test
python3 tests/validation/frontend_evolution/fe09_b2s3_t2c0_quiescent_fallback_qualification.py --self-test
python3 tests/validation/frontend_evolution/fe09_b2s3_t3s0_resource_census_qualification.py --self-test
python3 tests/validation/frontend_evolution/fe09_b2s3_t3s1_compact_handoff_qualification.py --self-test
python3 tests/validation/frontend_evolution/fe09_b2s3_t3s2a_atomic_spool_qualification.py --self-test
python3 tests/validation/frontend_evolution/fe09_b2s3_t3s2b0_manifest_qualification.py --self-test
python3 tests/validation/frontend_evolution/fe09_b2s3_t3s2b1a_immutable_root_qualification.py --self-test
python3 tests/validation/frontend_evolution/fe09_b2s3_t3s2b1bf0_seq17_qualification.py --self-test
python3 tests/validation/frontend_evolution/fe09_b2s3_t3s2b1ba1_anchor_root_qualification.py --self-test
python3 tests/validation/frontend_evolution/fe09_b2s3_t3s2b1ba2_finite_retirement_qualification.py --self-test
python3 tests/validation/frontend_evolution/test_fe09_same_run_artifact_visibility.py
python3 tests/validation/frontend_evolution/test_speech_download_retry.py
python3 tests/validation/frontend_evolution/test_speech_source_stage_budget.py
python3 tests/validation/frontend_evolution/test_speech_source_recovery.py
python3 tests/validation/frontend_evolution/speech_pinned_snapshot.py --self-test
python3 .github/program/workflow_pin_only_scope.py --self-test
python3 .github/program/workflow_pin_only_replay_t1.py --self-test
python3 .github/program/workflow_pin_only_actual_tree_t1m1.py --self-test
python3 .github/program/workflow_pin_pr_consumer.py --self-test
python3 .github/program/test_dechorate_event_source_t1m3.py --self-test
# Live GitHub bot Git-object probe only when this very qualifier is modified
# in a PR. Avoid an external network dependency for unrelated Verify runs.
if [ "${GITHUB_EVENT_NAME:-}" = pull_request ]; then
  test "${GITHUB_BASE_REF:-}" = main
  # A pull_request checkout may expose only refs/pull/<n>/merge, not origin/main.
  # Its first immutable parent is the checked-out protected PR base tree.
  set -- $(git -c "safe.directory=$PWD" rev-list --parents -n 1 HEAD)
  test "$#" -eq 3
  case "$2" in
    *[!0123456789abcdef]*|'') echo 'M1_PR_BASE_OID_MALFORMED' >&2; exit 1 ;;
  esac
  test "${#2}" -eq 40
  changed_t1m1=$(git -c "safe.directory=$PWD" diff --name-only "$2...HEAD" -- \
    .github/program/workflow_pin_only_actual_tree_t1m1.py)
  if [ "$changed_t1m1" = .github/program/workflow_pin_only_actual_tree_t1m1.py ]; then
    python3 .github/program/workflow_pin_only_actual_tree_t1m1.py --probe-real --review 2026-10-20
  fi
fi
