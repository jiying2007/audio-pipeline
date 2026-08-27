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

## Shared far-end / double-talk activity

Far-end activity and double-talk are classified once in the core after reference alignment and microphone combination. The same gate is then passed to both AEC adaptation and residual/noise suppression. A short three-frame hold counter prevents adaptation/suppression mode chatter after a detected near-end overlap.

This is deliberately conservative and inexpensive: the current gate uses aligned frame energy and does not claim a correlation/coherence DTD. More advanced DTD may replace the classifier later without changing the AEC/enhancement contracts.

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
- shared double-talk adaptation freeze;
- compile-time scalar or NEON complex kernels.

### NLMS

The NLMS backend is a separate translation unit implementing the same internal AEC contract. It uses the same compile-time scalar/NEON kernel layer for dot/update operations and the same core-owned far-end/double-talk gate as MDF.

Algorithm code never includes architecture intrinsics directly.

## Predicted echo and RES

Both AEC backends emit predicted echo. When NS is enabled in FULL/LITE, frequency RES reuses the NS spectral machinery, stores only unique-bin predicted-echo power and applies a smoothed per-bin residual gain. SAFE or NS-off uses broadband RES. Shared double-talk activity disables frequency RES.

## Noise suppression

The NS stage is a 20 ms sine-window STFT with 10 ms hop: 256 FFT at 8 kHz or 512 FFT at 16 kHz, speech-aware Wiener-like gain and no model weights.

`AP_NS_ESTIMATOR=EMA` is the default production estimator because it preserves the established CPU/behavior baseline. `AP_NS_ESTIMATOR=MCRA` enables a clean-room MCRA-lite backend that keeps a slowly rising local spectral minimum and uses minimum-to-current power ratio to slow noise-floor learning during speech while still learning persistent environmental changes. MCRA remains opt-in until a shipping profile proves a useful acoustic improvement on the product corpus together with acceptable target-board CPU/thermal headroom.

The 8/16 kHz analysis/synthesis sine windows are stored as symmetric read-only half-window tables generated from the repository's original formula. They are shared by all instances and do not consume per-pipeline RAM.

Neural NS/AEC, MVDR and GSC are not part of the minimum low-compute backend. Add heavier backends only after target measurements demonstrate headroom.

## VAD and AGC

VAD combines energy above a slow noise floor with the NS speech score and hangover. AGC uses slow gain-up, faster gain-down and a peak limiter. Codec DTX/comfort-noise policy remains outside the DSP core.

## Numeric policy

FP32 is the supported implementation format. Hardware floating point is required by the current product profiles. Precise compiler semantics are the default; `AP_ENABLE_FAST_MATH=ON` is an explicit separately tested product policy rather than a toolchain assumption.
