# FE04 oracle near-presence RES upper bound

This tranche does not modify the Activity detector, AEC, synchronization or BF. It consumes the
sealed FE04-RES-IMMEDIATE-DT-PROTECTION-V1 evidence and replays only the public time-domain RES.

The measured-replay arm uses the predecessor's measured used_far/used_dt flags and the exact same
pre-RES AEC samples, echo energy and residual energy. It must reproduce the predecessor packed
Float32 output byte-for-byte. This proves the downstream replay has no hidden algorithm change.

The oracle-near arm changes one input only: the RES double_talk_active/near-protection flag is
replaced with the original frozen renderer near-present flag:

- frame < 204;
- 600 <= frame < 1004;
- frame >= 1400.

AEC adaptation remains the measured Activity trajectory from the predecessor. The oracle signal
therefore cannot repair AEC contamination; it only bounds how much remaining attenuation is caused
by RES near-protection coverage.

On every oracle-near frame, the candidate build uses the same immediate near-protection release
alpha 1.0 introduced in #679. Gain must be exactly 1 and post-RES samples must be bitwise identical
to pre-RES AEC samples.

The report includes full and stable-window confusion of measured used_dt versus the oracle
near-present schedule, longest miss/false-positive runs, measured adaptation admitted during stable
double talk, attenuation specifically on newly protected frames, far-only suppression, recovery and
near/double speech metrics.

This is an oracle upper bound, not a detector candidate and not a product label source. Its fixed
decision is RES_ORACLE_NEAR_BOUND_DIAGNOSTIC_NO_PROMOTION. No shipping API, preset, version, E001
identity or DUT authority changes.
