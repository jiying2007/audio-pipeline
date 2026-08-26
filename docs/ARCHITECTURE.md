# Architecture

## Product goals

1. Hands-free calls and assistant capture on a small dual-core Linux CPU.
2. Fixed 10 ms scheduling, bounded state, allocation-free synchronous DSP.
3. Heavy compute stays at 8/16 kHz even when the device boundary is 24/32/48 kHz.
4. Explicit overload/backpressure instead of hidden queue growth.
5. Stable portable C DSP API; Linux/ALSA remain adapters around the core.

## Data plane

```text
render/DAC reference -> bounded ring -> delay + ppm drift tracker --------+
                                                                     v
mic S16 -> rate -> HPF -> 2-mic TDOA/BF -> mono -> MDF/NLMS AEC -> predicted echo
                                                        |                 |
                                                        v                 v
                                                   AEC residual -> subband RES
                                                                     |
                                                                     v
                                                              STFT Wiener NS
                                                                     |
                                                                VAD -> AGC
                                                                     |
                                                              rate -> mono S16
```

AEC runs after microphone combination, not once per microphone. That is a major structural CPU saving.

## Dual-core model

- Core 0: PCM/ALSA I/O, render-reference construction, codec/application work.
- Core 1: serial DSP graph.
- Bounded SPSC input/output queues separate the two deadlines.
- A semaphore blocks the DSP worker when there is no work; no 200 us polling loop.
- Affinity/SCHED_FIFO are optional and never required for correctness.

A per-frame AEC-to-NS cross-core barrier is intentionally avoided because wakeup/cache/synchronization overhead is significant on a small dual-core system.

## Synchronization and clock domains

The caller supplies the post-mix/post-gain DAC reference. Every ~100 ms the pipeline performs a 2 ms-step coarse correlation plus one-sample local fine search.

- >20 ms mismatch is a route/buffer jump: snap and reset AEC.
- Small mismatch feeds a ppm IIR estimator.
- Fractional drift is integrated; reference delay changes by a single sample only when accumulated error reaches a whole sample.

This is a lightweight reference-domain sample-slip controller, not a full-band ASRC. Reliable hardware timestamps should be used to seed/narrow the estimator when available.

## Quality states

| State | Beamforming | AEC | RES | Essential NS/AGC/VAD |
|---|---|---|---|---|
| FULL | track | configured tail/stride | frequency-dependent | on |
| LITE | hold/less work | <=64 ms, slower update | frequency-dependent, gentler | on |
| SAFE | bypass BF | <=40 ms, slower update | broadband fallback | on |

Runtime degradation happens after repeated deadline overruns; recovery requires sustained headroom.

## Memory ownership

`ap_pipeline_init()` and `ap_runtime_init()` take caller-owned fixed memory. All DSP arrays, render history, adaptive-filter state, FFT state and queue data are bounded. Thread/semaphore creation is control-plane work outside the synchronous DSP data plane.

## API/adapters

- `audio_pipeline.h`: portable synchronous DSP API and telemetry.
- `audio_runtime.h`: Linux dual-core queue/worker policy.
- `examples/alsa_duplex.c`: optional synchronous ALSA reference wiring.
- `examples/alsa_runtime_duplex.c`: optional two-core ALSA/runtime wiring.
- `bench/*` and `scripts/run-target-*`: release/performance tooling.

ALSA is optional and disabled by default, preserving a dependency-light minimum library.
