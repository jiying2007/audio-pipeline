# Repository-internal diagnostics

These helpers extend engineering diagnosis without changing the released `tools/*` surface, APD v1, shipping DSP, presets, public API/ABI, or Product Qualification authority.

- `aptriage.py` extracts/replays an APD and produces structured anomaly evidence. Its additive `replay_authority` block makes the current replay scope explicit: replay is PCM-only, does not re-inject runtime metadata/state, and never claims whole-incident equivalence. Raw `replay.comparison` values remain unchanged.
- `build_identity_probe.c` links against the processor library and emits machine-readable `ap_build_info()` values for repository-internal identity checking.
- `aptriage.py` can optionally compare the six build fields shared by APD v1 and the processor probe: version, module mask, AEC backend, NS estimator, SIMD backend, and resampler mode. `--require-build-identity-match` makes only this shared subset fail-closed.
- `apdiagnose.py` ranks evidence-backed hypotheses, identifies the first non-trigger anomaly, clusters nearby anomalies, recognizes temporal candidate chains, and can compare a failing triage result with a separately triaged reference.
- `fault_injection_contract.py` drives five real runtime metadata-fault families through the production Flight Recorder -> APD v1 -> triage -> diagnosis path and validates fault-domain ranking, replay-authority boundaries, and—when supplied—the shared build-identity subset.

For ordinary captures without stateful metadata faults, `replay_authority.classification` is `pcm-only-replay-check`. For captures containing `capture_discontinuity`, `render_discontinuity`, `clock_reset`, `xrun`, or `codec_reopen`, it is `stateful-runtime-context-not-replayed`; this means the metadata evidence exists in the dump but is not re-injected by the current replay path. The classification does **not** turn `bit_exact=false` into success and does not prove that a mismatch is or is not a DSP regression.

The build-identity result is intentionally narrower than a full fingerprint. APD v1 is populated from `ap_build_info()` but does not persist `source_revision` or `config_digest`, so those processor-side values are provenance only and `exact_source_config_match_authoritative` remains false. A `MATCH` means only that the six shared APD-v1 fields equal the supplied processor-linked build info.

`apdiagnose.py` is deliberately heuristic. `heuristic_score` is an evidence-ranking score rather than a probability, every candidate chain is marked `temporal-association-only`, and all outputs set `causal_proof=false`. These artifacts are diagnostic aids only and cannot claim HIL, Product Qualification, Product Certification, or shipping authority.
