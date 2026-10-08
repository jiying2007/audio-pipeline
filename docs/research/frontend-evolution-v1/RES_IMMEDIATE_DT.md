# FE04 immediate double-talk RES protection

This tranche isolates one variable from FE04-AEC-RES-COLLAB-V1: the current time-domain RES
uses a near-protection release alpha of 0.20 during detected double-talk, so gain returns toward
1.0 gradually. The research candidate compiles the same public RES implementation with
`AP_RES_NEAR_PROTECTION_RELEASE_ALPHA=1.0f`.

The shipping source is already written with an overrideable `#ifndef`; this experiment does
not modify `src/`, public headers, presets, API, version, E001 identity or default alpha. The
candidate build flag is recorded in every build receipt.

Single-variable guards are strict:
- pre-RES AEC output and reference lanes must be bitwise identical to the sealed current-RES
  predecessor;
- route/reset/Activity and all non-RES trace fields must remain identical;
- candidate post-RES output before the first detected-DT frame must remain bitwise identical to
  the predecessor;
- every detected-DT frame must have gain exactly 1.0 and candidate post-RES samples bitwise
  identical to candidate pre-RES AEC samples.

This does not protect near speech on frames the unchanged Activity detector fails to mark as
double-talk. That detector limitation is intentionally outside this candidate.

Post-DT reacquisition is descriptive. The fixed predecessor envelope is +1.0 dB in same-frame
post-output energy: candidate <= predecessor * 10^(1/10), measured from the first subsequent
non-DT frame until the next detected-DT run. Gain <0.99 and <0.95 reacquisition are reported
separately. The +1 dB envelope is not a promotion gate.

The fixed decision is RES_IMMEDIATE_DT_PROTECTION_DIAGNOSTIC_NO_PROMOTION. Even perfect
detected-DT bypass on these disclosed scenes cannot authorize shipping without independent
Activity/DTD and downstream validation.
