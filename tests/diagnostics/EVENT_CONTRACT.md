# Diagnostic event-name contract

This repository-internal contract keeps the human-readable event names used by diagnostic reasoning aligned with the public numeric `ap_event_kind_t` enum in `include/audio_pipeline/audio_diag.h`.

`event_contract.py` treats the public enum as the source of truth. It parses the explicit numeric values, derives the expected diagnostic presentation name by removing the `AP_EVENT_` prefix and lower-casing the symbol, then requires exact value/name equality with `apdiagnose.EVENT_NAMES`.

The contract also checks that `recording_trigger_context()` preserves the numeric event, uses the expected name, marks the source as `apd-header`, keeps the relation `recording-trigger-context-only`, and never claims causal proof. Unknown positive event numbers must remain representable through the `unknown_event_<N>` fallback rather than being rejected or silently remapped.

The machine-readable result uses schema version 1 and authority `repository-internal-event-name-contract-only`. It reports the public and diagnostic event counts, the normalized public event list, missing/extra events, name mismatches, trigger-context mismatches, and the unknown-event fallback check. Any drift makes the contract fail closed.

`--self-test` validates both directions: the live repository mapping must pass, while an intentionally mutated diagnostic name must fail. This prevents a broken checker from passing merely because both inputs happen to agree.

## Authority boundary

This contract validates repository-internal diagnostic presentation consistency only. It does not change, extend, or qualify the public enum; does not change APD v1; does not alter runtime event production; and does not affect shipping DSP, public API/ABI, Product Qualification, Product Certification, or release identity. A future public enum change still follows the normal API/release process; this checker only prevents the diagnostic name mirror from drifting silently.
