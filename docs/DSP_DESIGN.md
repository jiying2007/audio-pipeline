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

The search compares **squared normalized correlation**, so candidate ranking and the acceptance threshold are equivalent to absolute normalized correlation without performing `sqrtf` for every candidate.

Large correlation jumps are emitted as route-jump events. Persistent small error drives the ppm estimate and `drift_credit`. Integer crossings still update the reference delay and increment sample-slip telemetry. The remaining fractional credit is applied directly during reference fetch using two-point linear interpolation. This reduces discrete correction artifacts without introducing a general-purpose ASRC or new large state.

Optional hardware timestamp observations convert trusted capture/playback time deltas into delay observations. Timestamps must share a monotonic clock domain. Correlation remains the fallback.

## Activity / double-talk

Activity is a small stateful supporting module shared by high-level AEC/RES/NS and available standalone. The clean-room low-compute detector now uses:

- asymmetric attack/release smoothing for mic/reference energy;
- a far-end activation threshold plus a lower release threshold and short hangover;
- a double-talk activation ratio plus a lower hold ratio and hangover.

The first valid observation seeds the smoothers directly so cold-start far-end/double-talk response is not delayed by EMA warm-up. The implementation remains energy-domain and intentionally avoids per-frame FFT/coherence cost in the default low-compute profile.

A single Activity result avoids independent AEC, RES and NS double-talk decisions.

## AEC

Default AEC is a clean-room partitioned MDF/AUMDF-lite style frequency-domain backend. It processes five 2 ms subblocks per 10 ms frame. A compile-time NLMS backend remains a validation/safety alternative.

AEC resident geometry is derived from the compiled max tail/internal rate, so LOW/TINY product builds physically remove unused partitions/history.

Adaptation is gated by far-end/double-talk activity. Both MDF and NLMS maintain two adaptation cadences:

- **acquisition/recovery cadence** — the configured `aec_adapt_stride`;
- **steady cadence** — after 50 consecutive far-end-active/non-double-talk frames, at least stride 4.

Double talk or loss of far-end activity clears the steady window and immediately restores the configured acquisition cadence. Quality changes and AEC reset also clear the steady state. This lowers steady-state update/constrain work without slowing path reacquisition after a real condition change.

AEC reset occurs on explicit path changes, stream discontinuities that invalidate alignment or sufficiently large SYNC/timestamp route jumps through core.

## ERLE / convergence telemetry

ERLE is not computed as a generic graph input/output ratio. It updates only when:

```text
AEC selected
AND far-end active
AND double-talk inactive
AND valid reference/residual energy
```

`erle_valid` marks frames meeting this contract. `aec_convergence_frames` counts valid observations in the current epoch; route/path reset starts a new epoch. `active_aec_adapt_stride` reports the effective runtime cadence rather than only the configured base value.

## Residual echo suppression

RES has two forms:

- broadband attenuation fallback used when NS spectral processing is unavailable or SAFE mode requires the simpler path;
- frequency-dependent residual echo gain applied through the NS STFT when the graph has RES+NS and conditions permit.

Double-talk disables aggressive frequency RES.

## Noise suppression

NS uses an overlap STFT Wiener-style spectral gain. The default noise estimator is EMA; clean-room MCRA-lite is a compile-time opt-in. Read-only windows/tables live outside instance state.

Frequency RES stores only echo power bins and reuses the complex FFT scratch rather than holding a second persistent complex spectrum.

The current product policy is to optimize measured target-board hotspots rather than expand SIMD surface speculatively. Existing AEC vector kernels remain compile-time SCALAR/NEON; full FFT/NS vectorization should be accepted only when target profiling demonstrates material benefit and all acoustic contracts remain unchanged.

## AGC / limiter

AGC estimates frame RMS/peak, smooths gain with asymmetric attack/release behavior and applies a limiter. dB controls are converted to linear values at init, so the steady-state loop avoids `powf`.

The 10 ms cadence is part of the algorithm contract because gain smoothing advances once per process call.

## VAD

The lightweight VAD tracks an RMS noise floor and hangover. When NS exists, upstream NS speech probability may raise the decision probability. It is a classical low-cost product signal, not a calibrated neural posterior.

## Quality states

`FULL/LITE/SAFE` are runtime overload states, not CPU classes.

- FULL: nominal graph and AEC geometry;
- LITE: reduced active AEC tail/base adaptation policy and lower-cost choices;
- SAFE: strongest overload fallback, including BF bypass and broadband RES path.

Steady-state AEC cadence is an additional backend-local CPU reduction and does not replace FULL/LITE/SAFE overload policy.

Compile-time TINY/LOW product envelopes are separate and may physically remove capacity that runtime quality cannot restore.

## SIMD / math

Scalar and NEON kernels are compile-time selected; algorithm code does not contain CPU model names. Fast math is independently opt-in. Correctness, deterministic behavior where required and acoustic contracts must pass for every shipping combination.

## Clean-room policy

Algorithmic ideas may be informed by public literature and referenced open-source project architecture, but production source, tables and tuning values remain first-party clean-room unless explicitly documented in `THIRD_PARTY.md`.
