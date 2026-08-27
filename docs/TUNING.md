# Tuning Guide

Tune with recordings from the real enclosure, speaker, microphone geometry and playback-volume table. CPU model is not a tuning parameter; select a resource envelope from measured product headroom.

## 1. Choose resource class

Start with the highest class that comfortably meets target CPU/thermal/power gates:

- `STANDARD`: 16 kHz, longest default classical tail;
- `LOW`: 16 kHz, shorter tail;
- `TINY`: 8 kHz, short tail and no beamformer tracking by default.

Then tune individual fields only with an acoustic/performance reason. Do not use FULL/LITE/SAFE as a substitute for selecting the correct nominal product class.

## 2. Reference and delay first

Verify that the AEC reference is the exact post-mix/post-gain DAC signal. Set `initial_delay_ms` near the median path and keep `max_delay_ms` only as wide as required.

Watch `delay_error_samples`, `estimated_drift_ppm`, `reference_sample_slips`, `delay_jumps` and `aec_resets`. Frequent jumps on a stable route usually indicate timestamp/reference plumbing problems, not `aec_mu`.

## 3. Clock drift

Keep drift compensation enabled when playback/capture clocks can differ. Small ppm mismatch should cause occasional sample slips, not repeated AEC resets. Continuous/high slips or ±2000 ppm clamp means the audio clock/timestamp/resampling architecture needs fixing.

## 4. AEC tail, activity and adaptation

Reduce tail until real-device ERLE/path-change recovery regresses. Increase beyond the selected class only with evidence. `aec_mu` trades convergence against stability; `aec_adapt_stride` trades CPU against tracking speed.

Monitor both `far_end_active` and `double_talk_active`. The shared classifier intentionally holds double-talk for a few frames to prevent rapid adaptation/RES mode switching. If it misclassifies a product acoustic condition, improve the classifier/corpus rather than independently retuning AEC and RES thresholds so that they disagree.

## 5. Microphone geometry

Use acoustic-center spacing for `mic_spacing_mm`. If target direction is fixed, a calibrated held delay may be cheaper and more stable than tracking. TINY intentionally starts with BF tracking disabled.

## 6. Residual echo suppression

FULL/LITE use frequency RES when NS is active; SAFE uses broadband RES. Tune both far-end-only and true double-talk. Monitor `residual_echo_gain` and `frequency_res_active`.

## 7. Noise suppression / AGC / VAD

`AP_NS_ESTIMATOR=EMA` is the default production estimator. `AP_NS_ESTIMATOR=MCRA` is an opt-in clean-room backend for products whose real noise corpus benefits from minimum-controlled tracking. Before enabling MCRA on a shipping profile, validate stationary noise, short speech/noise bursts, persistent background changes, speech distortion, pumping, CPU, thermal and power on the actual target. A short burst should not immediately become the estimated floor; a sustained environmental change must eventually be learned.

`ns_floor` is the minimum Wiener gain. Tune AGC only after AEC/RES/NS. Keep limiter headroom. If background pumps during pauses, inspect the noise estimate and speech score before lowering the limiter or making AGC more conservative.

## 8. Runtime policy

Runtime defaults are intentionally topology-neutral (`dsp_cpu=-1`, `dsp_priority=0`). Only pin or request FIFO after measuring IRQ/cpuset interaction on the product. Default overload threshold is 9 ms for a 10 ms frame; nominal target is >=99.9% FULL residence with zero queue drops/overruns.

Use `ap_runtime_bench` and the 8 h target soak rather than tuning against an unconstrained desktop loop.

## 9. Fast math

Keep `AP_ENABLE_FAST_MATH=OFF` until a target profile demonstrates a useful benefit. Turning it on requires the same unit/contracts, acoustic corpus and board performance/thermal/power certification as any other DSP change.
