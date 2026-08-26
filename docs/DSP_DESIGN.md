# DSP Design

## Front end

Each microphone uses a cheap one-pole DC/low-frequency remover:

`y[n] = x[n] - x[n-1] + r*y[n-1]`

For two microphones, a geometry-bounded integer TDOA search drives delay-and-sum. FULL tracks direction periodically, LITE holds/reduces work and SAFE bypasses beamforming. A fixed calibrated delay is preferable when product geometry permits it.

## Delay tracker and clock drift

Every ~100 ms the bounded reference history is searched at ~2 ms coarse resolution, then only the winning neighborhood is searched sample-by-sample.

A >20 ms change is considered a route/buffer path change and resets adaptive AEC state. Smaller motion feeds an IIR ppm estimate. The estimator integrates fractional clock error and adjusts the reference alignment one sample at a time when the accumulated error crosses ±1 sample. Catch-up from persistent residual delay error is bounded to avoid discontinuities.

This controller is intentionally much cheaper than a continuous full-band ASRC. It corrects the AEC reference domain; it does not replace a high-fidelity device resampler for full-band audio.

## AEC: MDF/AUMDF-lite default

The default backend is an independent partitioned frequency-domain adaptive filter based on standard MDF/AUMDF concepts:

- five 2 ms blocks per public 10 ms frame;
- 16 kHz: 32 samples, 64-point FFT, 33 unique bins;
- 8 kHz: 16 samples, 32-point FFT;
- at most 60 partitions for the 120 ms configured ceiling;
- bounded circular render-spectrum history;
- normalized `conj(X)*E` adaptation;
- one cyclic time-domain support constraint per adaptation step;
- double-talk freezes adaptation;
- half-spectrum history/weights and optional NEON complex MAC.

FULL/LITE/SAFE change active partitions and update cadence. `AP_ENABLE_MDF_AEC=OFF` selects the independent time-domain NLMS fallback for bring-up, short tails or comparison.

WebRTC AEC3 remains a higher-footprint production reference, not a minimum dependency.

## Predicted echo and residual suppression

Both MDF and NLMS expose the predicted echo waveform internally.

When NS is enabled and quality is FULL/LITE, the existing 20 ms STFT is reused to transform the predicted echo. A smoothed per-bin residual gain is derived from residual power versus predicted-echo power, then multiplied with the Wiener NS gain. This adds one FFT per 10 ms frame rather than a separate neural model or second complete enhancement pipeline.

- FULL uses stronger echo weighting/lower floor.
- LITE uses gentler settings.
- SAFE and NS-off use the cheaper broadband RES path.
- True double-talk disables subband RES; gain returns toward unity instead of erasing near-end speech.

## Noise suppression

The default NS is a 20 ms sqrt-Hann STFT with 10 ms hop: 256 FFT at 8 kHz or 512 FFT at 16 kHz, recursive per-bin noise PSD, speech-aware update rate, Wiener-like floor and 50% overlap-add. It has no model weights.

RNNoise/DeepFilterNet are optional future high-headroom choices, not default A32 costs.

## VAD and AGC

VAD combines output energy above a slow noise floor with the NS speech score and an 80 ms hangover. AGC moves slowly upward, faster downward and applies a peak limiter. DTX/comfort-noise packetization belongs to the codec/application domain.

## Resampling boundary

The built-in 24/32/48-to-8/16 kHz adapter is deterministic and cheap, suitable for bring-up/voice-band sources. Full-band products should use codec hardware or a proven anti-aliasing resampler at the boundary.
