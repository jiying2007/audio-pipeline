# DSP Design

## Processing model

The high-level synchronous path processes fixed 10 ms frames. Device PCM is S16; internal classical DSP uses float at 8 or 16 kHz. The graph is a fixed safe order with build/runtime pruning, not a general-purpose audio DAG.

Default logical order:

```text
boundary resampler
 -> HPF
 -> optional 2-mic delay/sum beamformer
 -> render SYNC / delay / drift
 -> Activity / DTD
 -> AEC
 -> RES
 -> Wiener NS
 -> AGC / limiter
 -> VAD
 -> boundary output resampler
```

## Boundary resampling

Two compile-time modes exist:

- `BANDLIMITED` default: small first-party FIRs for current supported downsampling ratios, with frame-to-frame history;
- `FAST`: the previous low-cost interpolation/decimation behavior.

Current BANDLIMITED filters cover fixed 2:1, 3:1, 4:1, 6:1 and 3:2 downsampling geometries. Other/same-rate/upconversion paths use the lightweight interpolation path. This is intentionally not a large arbitrary-ratio SRC.

The public latency API includes FIR group delay. Tests validate representative passband/stopband behavior rather than requiring BANDLIMITED output to match FAST samples.

## HPF

Per-channel first-order high-pass filtering removes DC/very-low-frequency energy before spatial processing. State is channel-local and independently resettable in standalone use.

## Beamformer

The two-mic frontend uses a low-cost delay-and-sum geometry with optional direction tracking. It is selected only for two-microphone configurations. SAFE quality bypasses tracking/beamforming work in the high-level graph.

## Render synchronization

SYNC stores a bounded render ring whose capacity is derived from the compiled max delay/internal sample rate. Coarse normalized correlation is periodically searched across the supported delay range, followed by a local one-sample refinement.

Large correlation jumps are emitted as route-jump events. Persistent small error drives the existing ppm estimate and integer reference-domain sample slips.

Optional hardware timestamp observations convert trusted capture/playback time deltas into delay observations. Timestamps must share a monotonic clock domain. Correlation remains the fallback and timestamp observations do not create a general ASRC.

## Activity / double-talk

Activity is a small stateful supporting module shared by high-level AEC/RES/NS and available standalone. The current clean-room implementation uses far-end energy threshold + near/reference energy ratio + hangover. It is intentionally cheap; future coherence/correlation implementations should preserve the same module contract.

A single Activity result avoids independent AEC and RES double-talk decisions.

## AEC

Default AEC is a clean-room partitioned MDF/AUMDF-lite style frequency-domain backend. It processes five 2 ms subblocks per 10 ms frame. A compile-time NLMS backend remains a validation/safety alternative.

AEC resident geometry is derived from the compiled max tail/internal rate, so LOW/TINY product builds physically remove unused partitions/history.

Adaptation is gated by far-end/double-talk activity. AEC reset occurs on explicit path changes or sufficiently large SYNC/timestamp route jumps through the core orchestrator.

## ERLE / convergence telemetry

ERLE is not computed as a generic graph input/output ratio. It updates only when:

```text
AEC selected
AND far-end active
AND double-talk inactive
AND valid reference/residual energy
```

`erle_valid` marks frames meeting this contract. `aec_convergence_frames` counts valid observations in the current epoch; route/path reset starts a new epoch.

## Residual echo suppression

RES has two forms:

- broadband attenuation fallback used when NS spectral processing is unavailable or SAFE mode requires the simpler path;
- frequency-dependent residual echo gain applied through the NS STFT when the graph has RES+NS and conditions permit.

Double-talk disables aggressive frequency RES.

## Noise suppression

NS uses an overlap STFT Wiener-style spectral gain. The default noise estimator is EMA; clean-room MCRA-lite is a compile-time opt-in. Read-only windows/tables live outside instance state.

Frequency RES stores only echo power bins and reuses the complex FFT scratch rather than holding a second persistent complex spectrum.

## AGC / limiter

AGC estimates frame RMS/peak, smooths gain with asymmetric attack/release behavior and applies a limiter. dB controls are converted to linear values at init, so the steady-state loop avoids `powf`.

The 10 ms cadence is part of the algorithm contract because gain smoothing advances once per process call.

## VAD

The lightweight VAD tracks an RMS noise floor and hangover. When NS exists, upstream NS speech probability may raise the decision probability. It is a classical low-cost product signal, not a calibrated neural posterior.

## Quality states

`FULL/LITE/SAFE` are runtime overload states, not CPU classes.

- FULL: nominal graph and AEC geometry;
- LITE: reduced active AEC tail/adaptation cadence and lower-cost choices;
- SAFE: strongest overload fallback, including BF bypass and broadband RES path.

Compile-time TINY/LOW product envelopes are separate and may physically remove capacity that runtime quality cannot restore.

## SIMD / math

Scalar and NEON kernels are compile-time selected; algorithm code does not contain CPU model names. Fast math is independently opt-in. Correctness and acoustic contracts must pass for every shipping combination.

## Clean-room policy

Algorithmic ideas may be informed by public literature and referenced open-source project architecture, but production source, tables and tuning values remain first-party clean-room unless explicitly documented in `THIRD_PARTY.md`.
