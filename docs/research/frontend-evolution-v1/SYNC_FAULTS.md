# FE04 fixed synchronization faults / 固定同步故障对照

Base: `8993505a940534d6de22bd81f54576e6934bf01d`. Preregistration: #657 comments `6010010528` and
`6010120012`, both before implementation or scores.

This diagnostic isolates the existing public SYNC module from RES and from any
new synchronization algorithm. It reuses the two disclosed FE04 development
pairs, ULA4-70/FIR33 and the no-event source audio. The acoustic microphone and
physical playback sequence do not change between arms.

Three fixed application-render transport faults are used: a 320-sample lead, a
320→800 sample route jump exactly halfway through the 16 s capture, and a
deterministic +250 ppm producer drift. There is no fault-size sweep.

Each case executes:
- **oracle**: exact physical playback reference, diagnostic upper-bound arm;
- **raw**: most recent application-render samples with no synchronization;
- **public-sync**: existing `ap_module_sync`, initial delay 0, max 120 ms,
  delay tracking and drift compensation enabled. Its returned reference alone
  feeds unchanged Activity and AP MDF AEC.

The standalone public-SYNC arm intentionally does **not** apply the full
pipeline's AEC reset on `route_jump`. That integration behavior is a separate
causal contrast. No timestamp assistance, SpeexDSP, #667 hard guard, RES, NS or
AGC is present.

## Measurement boundary

The public tracker correlates post-BF microphone with render, so absolute
`delay_samples` includes the fixed acoustic/BF path and is not transport lead
truth. We therefore retain absolute state descriptively but score changes from
each case's own stable pre-event interval. Route truth is +480 samples. Drift
truth is the deterministic application-lead change over the corresponding
measurement intervals; sample slips, route observations, underruns and
drift-ppm state are retained.

Audio authority stays with actual mixed output: far-only known-echo/output
ratio and full-output SI-SDR relative to the unchanged BF target. There is no
measured-mode shadow subtraction.

Native, ASan/UBSan and AArch32/QEMU execute synthetic engineering controls.
The full six speech/fault cases run on native CI with repeat receipts, exact
input/predecessor identities and resealed semantic negatives. Host/QEMU
execution is not SSC305 timing, HIL, room or product qualification.

Fixed result identity is `SYNC_FAULTS_DIAGNOSTIC_NO_PROMOTION` regardless of
scores. No shipping API, preset, version or E001 identity changes in this
tranche.
