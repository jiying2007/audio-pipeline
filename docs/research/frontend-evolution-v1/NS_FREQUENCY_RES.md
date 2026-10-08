# FE05 ordinary NS versus existing frequency-domain RES

This tranche isolates the existing frequency-domain residual-echo path inside the public NS
module. It does not execute the standalone time-domain RES stage.

One exact-timestamp / measured-Activity / MDF AEC execution produces one pre-NS signal and one
predicted-echo signal. Those exact same buffers feed two separately initialized NS modules:

- ns-only: FULL quality, floor_gain=0.18, frequency RES disabled;
- ns-freq-res: identical FULL/floor/input state, frequency RES enabled.

The NS noise tracker consumes the same pre-NS spectrum in both arms, so noise_rms_dbfs and
speech_probability must remain bit-identical. Frequency RES is active only for far-end-active,
non-double-talk frames.

Because NS is overlap-add, the first protected frame after an active frequency-RES frame may
contain one frame of synthesis-overlap carryover. That boundary was identified and frozen before
execution. Every protected frame not immediately following an active frequency-RES frame must be
byte-identical between arms; a second consecutive protected frame therefore reconverges.

Evidence keeps pre-NS AEC output, predicted echo, both NS outputs, reference, frame-level NS
statistics, frequency-RES activity/gain, OLA carryover counts, actual far-only residual and
near/double speech metrics. Pre-NS AEC output and reference must be bit-identical to the sealed
same-run FE04 AEC/RES predecessor.

This is disclosed synthetic-echo research evidence, not real-room or DUT NS qualification. The
fixed decision is NS_FREQUENCY_RES_DIAGNOSTIC_NO_PROMOTION. No shipping API, preset, version,
E001 identity, time-domain RES, AGC or VAD behavior changes.
