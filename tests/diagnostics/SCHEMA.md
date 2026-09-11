# Diagnostic reasoning schema

`apdiagnose.py` emits schema version 1.

The stable diagnosis fields are:

- `authority`: always `repository-internal-heuristic-diagnostic-only`;
- `causal_proof`: always `false`;
- `recording_trigger`: APD file-header trigger context when `apdiagnose` receives a full `triage.json`, otherwise `null`;
- `first_fault`: first non-trigger anomaly after deterministic frame/kind ordering, or `null`;
- `intervals`: nearby non-trigger anomalies clustered only by frame distance;
- `anomaly_counts`: counts by anomaly kind;
- `root_cause_hypotheses`: ranked evidence families with deterministic heuristic scores;
- `candidate_chains`: recognized ordered event patterns marked `temporal-association-only`;
- `top_hypothesis`: first ranked hypothesis, or `null`;
- `notes`: evidence-boundary reminders.

## Recording trigger context

`recording_trigger` consumes the numeric `header.trigger_event` already present in APD v1; it does not add or change any on-disk field. When present it contains:

- `event`: the numeric public `ap_event_kind_t` value from the APD header;
- `name`: repository-internal human-readable event name;
- `source`: always `apd-header`;
- `relation`: always `recording-trigger-context-only`;
- `causal_proof`: always `false`.

The recording trigger answers **why the Flight Recorder froze**. It is intentionally not inserted into `anomalies`, is not eligible to become `first_fault`, does not create an interval, and contributes zero evidence to every root-cause hypothesis. This distinction matters for manually triggered captures: `AP_EVENT_DIAG_TRIGGERED` can explain why the dump exists while the same dump can legitimately have `first_fault=null` and `top_hypothesis=null`.

A standalone `analysis.json` has no APD file header, so `recording_trigger` remains `null`; this preserves compatibility with existing analysis-only consumers. Unknown positive event numbers are retained as the numeric source of truth and rendered as `unknown_event_<N>` rather than rejected.

Hypothesis scores are deterministic evidence ranks, not probabilities. Metadata faults use explicit domain weights so the ranking cannot silently depend on alphabetical tie-breaking. The primary mapping is:

- `render_discontinuity` / `clock_reset` -> `sync-reference-path`;
- `capture_discontinuity` / `codec_reopen` -> `capture-io`;
- `xrun` -> `runtime-continuity`.

Related secondary hypotheses may still be emitted with lower scores. For a single metadata record containing multiple matching flags, a hypothesis receives the maximum matching flag weight rather than a sum, preventing one multi-flag record from being counted as several independent observations.

Reference comparison also emits schema version 1. Existing raw fields remain additive/backward-compatible:

- `anomaly_count_delta_by_kind`;
- `new_anomaly_kinds` / `resolved_anomaly_kinds`;
- `summary_delta`;
- reference/candidate top hypotheses.

To prevent unequal capture lengths from creating a false apparent improvement or regression, comparison additionally reports:

- `comparison_geometry`: reference/candidate `frames`, `metrics_frames` and `duration_ms`, plus equality flags;
- `raw_count_comparability`: per count metric, the exposure denominator and whether the raw delta is directly comparable;
- `normalized_metrics`: anomaly rate per 1000 frames, quality/VAD transition rates per 1000 metrics frames, and far-end/double-talk/AEC-converged ratios;
- `warnings`: explicit notices when frame count, decoded-metrics exposure or capture duration differs.

`summary_delta` is retained for compatibility. A raw count delta must not be interpreted as an improvement/regression when its `raw_count_comparability.*.directly_comparable` value is false; use the corresponding normalized rate/ratio instead. Max delay-error and drift extrema are not normalized because longer captures inherently have more opportunity to observe an extreme value; unequal durations are therefore warned explicitly.

## Replay authority interpretation

`aptriage.py` keeps the raw released `apreplay.py` result unchanged under `replay` and additively emits `replay_authority`. This interpretation layer is schema-version-1 repository-internal metadata; it does not change APD v1, the released `tools/*` surface, replay return codes, `--require-bit-exact`, or triage PASS/FAIL.

`replay_authority` contains:

- `authority`: always `repository-internal-replay-interpretation-only`;
- `mode`: always `pcm-only` for the current replay path;
- `state_replay`: always `false`; runtime metadata/state is not re-injected into `ap_process_pcm`;
- `runtime_metadata_state_present`: whether the captured anomaly evidence contains a stateful runtime metadata fault;
- `runtime_metadata_flags`: sorted captured stateful flags among `capture_discontinuity`, `render_discontinuity`, `clock_reset`, `xrun`, and `codec_reopen`;
- `comparison_present`: whether the raw replay produced an output comparison;
- `bit_exact`: the raw `replay.comparison.bit_exact` value when present, otherwise `null`;
- `classification`: `pcm-only-replay-check` when no stateful runtime metadata fault is present, otherwise `stateful-runtime-context-not-replayed`;
- `bit_exact_claim_scope`: a human-readable statement limiting the comparison to recorded PCM output;
- `whole_incident_equivalence_authoritative`: always `false`.

The classification is deliberately about **claim scope**, not about success. A `bit_exact=false` raw comparison remains false. When stateful runtime metadata is present, that mismatch cannot by itself distinguish a DSP regression from runtime state that the PCM-only path did not re-inject. Conversely, `bit_exact=true` proves only equality of the compared recorded/replayed PCM bytes for that invocation; it does not prove whole-runtime incident equivalence.

## Shared processor build identity

`aptriage.py` additively emits `build_identity`. The current APD v1 header is itself populated by the runtime exporter from `ap_build_info()`, but it persists only a subset of that structure. Therefore the repository-internal check compares exactly the six fields present in both APD v1 and a processor-linked build-info probe:

- `version`;
- `module_mask`;
- `aec_backend`;
- `ns_estimator`;
- `simd_backend`;
- `resampler_mode`.

`build_identity` contains:

- `authority`: always `repository-internal-build-identity-subset-only`;
- `processor_identity_supplied`: whether a build-info JSON was provided;
- `require_match`: whether the caller requested fail-closed shared-subset matching;
- `status`: `NOT_CHECKED`, `MATCH`, or `MISMATCH`;
- `shared_fields`: the six fields above;
- `shared_fields_match`: `null` when no identity is supplied, otherwise boolean;
- `mismatches`: per-field APD and processor values;
- `apd_identity`: the six values decoded from APD v1;
- `processor_identity`: the six values emitted by the linked build-info probe;
- `processor_provenance`: processor-side `source_revision`, `config_digest`, compiler, target and build-type values when supplied;
- `exact_source_config_match_authoritative`: always `false`;
- `claim_scope`: explicit statement that the check covers only the APD-v1 shared subset.

`tests/diagnostics/build_identity_probe.c` obtains its values from the public `ap_build_info()` interface of the exact library it is linked against. `source_revision` and `config_digest` are useful processor provenance, but APD v1 does **not** record them, so they are never presented as APD-comparable evidence. Exact source/config fingerprint equality would require a future release-bearing dump-format contract and is outside this repository-internal check.

By default, absence of `--processor-build-info` leaves the status `NOT_CHECKED` and does not change triage PASS/FAIL. `--require-build-identity-match` is explicitly fail-closed: missing identity or any shared-field mismatch makes triage `FAIL`. This gate is independent from raw PCM replay. CI deliberately proves that a tampered identity can make build identity `MISMATCH` while the unchanged processor still produces `replay.comparison.bit_exact=true`.

The runtime fault-injection contract writes `fault-injection-summary.json` with schema version 1. Each case records the injected case name, preserved metadata flag, recording trigger context, diagnosed first-fault family, top hypothesis, heuristic score, raw replay values, replay authority, shared build-identity result, and `causal_proof=false`. The contract covers `capture-gap`, `render-gap`, `clock-reset`, `xrun`, and `codec-reopen` through the real runtime -> Flight Recorder -> APD v1 -> triage -> diagnosis path.

The schema intentionally does not contain a probability or claim causal certainty. None of these fields participate in HIL, Product Qualification, Product Certification or shipping gates. A future promotion into the released SDK/tool surface requires the normal release-bearing review and SemVer process.
