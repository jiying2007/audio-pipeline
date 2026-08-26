# Tuning Guide

Tune with recordings from the real enclosure, speaker, microphone geometry and playback-volume table.

## 1. Reference and delay first

Verify that the reference is the exact post-mix/post-gain DAC signal. Set `initial_delay_ms` near the median path and keep `max_delay_ms` only as wide as the product needs.

Watch `delay_error_samples`, `estimated_drift_ppm`, `reference_sample_slips`, `delay_jumps` and `aec_resets`. Frequent route jumps in a steady route usually indicate reference/timestamp plumbing problems, not an AEC-mu problem.

## 2. Clock drift

Keep `enable_clock_drift_compensation=1` when playback/capture clocks can differ. Small ppm mismatch should produce occasional sample slips, not repeated AEC resets. If sample slips are continuous/high or drift is clamped near ±2000 ppm, fix the audio clock/timestamp/resampling architecture instead of increasing AEC tail.

## 3. AEC tail and adaptation

CALL starts at 96 ms; ASSISTANT at 80 ms. Reduce active tail until real-device ERLE/path-change recovery regresses. Increase beyond 100 ms only with evidence.

`aec_mu` trades convergence for stability. `aec_adapt_stride` trades CPU for tracking speed. Always re-run true double-talk and path-change tests after changing either.

## 4. Microphone geometry

Use acoustic-center spacing for `mic_spacing_mm`. If the target direction is fixed, a calibrated held delay is cheaper and more stable than continuous tracking.

## 5. Residual echo suppression

FULL/LITE use frequency-dependent RES when NS is active; SAFE uses broadband RES. Tune with both far-end-only and true double-talk. Too aggressive subband floors create musical/chopped near-end speech even if far-end-only ERLE looks excellent.

Monitor `residual_echo_gain` and `frequency_res_active`. During strong double-talk, `frequency_res_active` should drop to zero.

## 6. Noise suppression

`ns_floor` is the minimum Wiener gain. Lower is stronger/noisier in artifacts; higher preserves more natural speech/noise. ASSISTANT should generally be gentler than CALL.

## 7. AGC

Tune `agc_target_dbfs` after AEC/RES/NS. Keep limiter headroom. If background pumps during pauses, fix speech/noise estimation or gain attack/release rather than only lowering the limiter.

## 8. Runtime degradation

Default runtime overload threshold is 9 ms for a 10 ms frame, with downgrade after repeated overruns and slow recovery after sustained headroom. Nominal target is >=99.9% FULL residence with zero queue drops/overruns.

Use `ap_runtime_bench` and the 8 h target soak rather than tuning against an unconstrained desktop loop.
