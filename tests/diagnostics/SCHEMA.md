# Repository diagnostic schema

All files in this document are repository-internal engineering evidence. They do not change APD v1, the released `tools/*` surface, public API/ABI, shipping DSP, Product Qualification, HIL, or certification authority.

## Triage

`aptriage.py` emits schema version 1 with authority `repository-internal-diagnostic-only`.

A normal invocation requires:

- an APD v1 dump;
- `--processor`;
- `--processor-build-info` from the exact processor-linked `ap_build_info()` probe;
- `--output-dir`.

There is no unchecked build-identity mode. The six fields present in both APD v1 and the processor probe are always compared:

- `version`;
- `module_mask`;
- `aec_backend`;
- `ns_estimator`;
- `simd_backend`;
- `resampler_mode`.

`build_identity` contains:

- `authority=repository-internal-build-identity-subset-only`;
- `status=MATCH|MISMATCH`;
- `shared_fields`;
- boolean `shared_fields_match`;
- `mismatches` with APD/processor values;
- `apd_identity`;
- `processor_identity`;
- processor-side `processor_provenance`;
- `exact_source_config_match_authoritative=false`;
- an explicit shared-subset claim scope.

Any shared-field mismatch makes triage fail closed. `processor_identity_supplied`, `require_match`, and `NOT_CHECKED` are not part of the terminal schema.

APD v1 does not record `source_revision` or `config_digest`. Those processor-side values remain provenance only, so exact source/config identity is never inferred from a shared-field `MATCH`.

### Replay authority

The raw released `apreplay.py` result remains under `replay`. Triage also emits `replay_authority`:

- `authority=repository-internal-replay-interpretation-only`;
- `mode=pcm-only`;
- `state_replay=false`;
- captured stateful runtime metadata flags;
- raw comparison presence and `bit_exact` value;
- classification `pcm-only-replay-check` or `stateful-runtime-context-not-replayed`;
- `whole_incident_equivalence_authoritative=false`.

A replay mismatch stays a mismatch. A bit-exact replay proves only the compared PCM bytes for that invocation, not whole-runtime equivalence.

## Diagnosis

`apdiagnose.py` emits schema version 1 with authority `repository-internal-heuristic-diagnostic-only` and always `causal_proof=false`.

Normal diagnosis input is a complete repository `triage.json`. Bare `analysis.json` is not an accepted terminal input because it lacks the APD header/recording-trigger context.

Stable diagnosis fields include:

- `recording_trigger`: APD header trigger context, never a fault or causal claim;
- `first_fault`: first non-trigger anomaly after deterministic frame/kind ordering;
- `intervals`: temporal anomaly clusters;
- `anomaly_counts`;
- ranked `root_cause_hypotheses` with deterministic heuristic scores;
- `candidate_chains` marked `temporal-association-only`;
- `top_hypothesis`;
- evidence-boundary notes.

Unknown positive trigger values remain numeric source-of-truth events rendered as `unknown_event_<N>`.

Metadata-domain ranking is deterministic:

- `render_discontinuity` / `clock_reset` -> `sync-reference-path`;
- `capture_discontinuity` / `codec_reopen` -> `capture-io`;
- `xrun` -> `runtime-continuity`.

For a single metadata record containing multiple matching flags, a hypothesis receives the maximum matching flag weight rather than counting one record as several independent observations.

### Reference comparison

A reference comparison accepts two complete `triage.json` inputs and emits:

- anomaly-count deltas by kind;
- newly observed/resolved anomaly kinds;
- raw summary deltas;
- reference/candidate geometry;
- per-count denominator comparability;
- normalized rates/ratios;
- explicit warnings for unequal exposure or duration;
- reference/candidate top hypotheses;
- `causal_proof=false`.

Raw count deltas must not be interpreted as improvement/regression when `raw_count_comparability.*.directly_comparable=false`; use the corresponding normalized rate or ratio. Duration-sensitive extrema are not normalized.

## Runtime fault contract

`fault_injection_contract.py` always requires processor build info and drives these real runtime metadata faults through Flight Recorder -> APD v1 -> triage -> diagnosis:

- `capture-gap`;
- `render-gap`;
- `clock-reset`;
- `xrun`;
- `codec-reopen`.

Each case must have a shared build-identity `MATCH`; there is no optional identity path. The contract also builds the cross-dump incident bundle from the five retained triage/diagnosis pairs.

## Incident bundle

See `INCIDENT_BUNDLE.md` for the cross-dump schema. In terminal form:

- `--source-root` is mandatory for normal operation;
- all sources must resolve under that root before reading;
- all source files are SHA256/byte-size/root-relative-path bound;
- incidents emit only `source_evidence`, not runner-local legacy source path fields;
- build/replay authority blocks are required;
- recurrence remains correlation only and `causal_proof=false`.

Promotion of any of these repository-internal contracts into the released SDK/tool surface is release-bearing and requires normal SemVer/release review.
