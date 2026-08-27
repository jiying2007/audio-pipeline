# DSP Design

## Boundary and front end

I/O rates are 8/16/24/32/48 kHz; internal processing is 8 or 16 kHz. Fixed 10 ms product ratios use deterministic direct/fixed-phase linear paths. The boundary adapter is intended for voice-band bring-up/integration, not as a production full-band anti-aliasing guarantee.

Each microphone uses a one-pole high-pass/DC remover. Two-mic mode uses a geometry-bounded integer TDOA search and delay-and-sum. TINY disables beamformer tracking by default; LOW/STANDARD keep it available. Product geometry may use a fixed calibrated delay when cheaper and more stable.

## Delay tracker and drift

Every ~100 ms the bounded reference history is searched at ~2 ms coarse resolution, then the winning cell is refined sample-by-sample.

- >20 ms change: route/buffer-path jump, snap and reset AEC;
- smaller motion: jitter/clock mismatch feeding a ppm estimate;
- accumulated clock error: slow single-sample reference slips.

Hardware timestamps are preferred whenever the audio driver exposes them.

## AEC backend contract

AEC is selected at compile time with `AP_AEC_BACKEND`.

### MDF

The default MDF/AUMDF-lite backend uses:

- five 2 ms blocks per public 10 ms frame;
- 16 kHz: 32-sample blocks, 64-point FFT, 33 unique bins;
- 8 kHz: 16-sample blocks, 32-point FFT;
- at most 60 partitions for the 120 ms hard ceiling;
- rolling per-bin reference power;
- normalized `conj(X)*E` adaptation;
- cyclic support constraint;
- double-talk adaptation freeze;
- compile-time scalar or NEON complex kernels.

### NLMS

The NLMS backend is a separate translation unit implementing the same internal AEC contract. It uses the same compile-time scalar/NEON kernel layer for dot/update operations.

Algorithm code never includes architecture intrinsics directly.

## Predicted echo and RES

Both AEC backends emit predicted echo. When NS is enabled in FULL/LITE, frequency RES reuses the NS spectral machinery, stores only unique-bin predicted-echo power and applies a smoothed per-bin residual gain. SAFE or NS-off uses broadband RES. True double-talk disables frequency RES.

## Noise suppression

The default NS is a 20 ms sqrt-Hann STFT with 10 ms hop: 256 FFT at 8 kHz or 512 FFT at 16 kHz, recursive noise PSD, speech-aware update and Wiener-like gain floor. It has no model weights.

Neural NS/AEC is not part of the minimum low-compute backend. Add heavier backends only after target measurements demonstrate headroom.

## VAD and AGC

VAD combines energy above a slow noise floor with the NS speech score and hangover. AGC uses slow gain-up, faster gain-down and a peak limiter. Codec DTX/comfort-noise policy remains outside the DSP core.

## Numeric policy

FP32 is the supported implementation format. Hardware floating point is required by the current product profiles. Precise compiler semantics are the default; `AP_ENABLE_FAST_MATH=ON` is an explicit separately tested product policy rather than a toolchain assumption.
