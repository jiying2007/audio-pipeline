# Architecture

## Product goals

1. One classical voice front end for low-compute Arm Linux product families, not one CPU model.
2. Fixed 10 ms scheduling, bounded caller-owned state and allocation-free synchronous DSP.
3. Heavy compute stays at 8/16 kHz even when device I/O is 24/32/48 kHz.
4. Compile-time AEC/SIMD selection; no hot-path plugin dispatch.
5. Linux/threading is an adapter around a portable core.
6. Resource class, runtime quality and CPU build profile remain independent.
7. DSP stages own their state and expose narrow contracts; only core owns the composite graph/public telemetry.

## Production modules

```text
src/core/            public config/lifecycle, composite state, graph orchestration, telemetry aggregation
src/frontend/        rate boundary, HPF, 2-mic beamformer state
src/sync/            render history, delay/route-jump/clock-drift state and events
src/aec/             MDF or NLMS compile-time backend state/results
src/enhance/         broadband/subband RES, NS, AGC, VAD state/results
src/dsp/             FFT/math primitives and DSP data types
src/arch/scalar/     portable kernels
src/arch/arm_neon/   Arm NEON kernels
src/platform/linux/  optional SPSC worker/runtime policy
```

The dependency direction and realtime rules are enforced by `scripts/check-architecture.sh`.

## State ownership and dependency direction

The portable DSP is intentionally not a set of files sharing one giant internal object. `src/core/ap_pipeline_internal.h` is the only place that composes the full pipeline state. Each stage owns its own private state type and receives only the samples/scalars required for that operation.

```text
                     +-> frontend -> dsp
                     |
public API -> core --+-> sync -----> dsp
                     |
                     +-> AEC ------> dsp + arch
                     |
                     +-> enhance --> dsp

platform/linux -> public API
```

Sibling stages do not call each other. Cross-stage effects are events/results returned to core. For example, the synchronization layer reports a route jump; core increments public telemetry and resets the AEC backend. The sync module never knows that an AEC implementation exists.

Likewise, frontend/AEC/sync/enhancement code cannot reference `ap_pipeline_t`, `ap_config_t` or `ap_metrics_t`. Core is the single owner of public configuration policy and public metrics aggregation. This makes a backend or stage replaceable without exposing the complete pipeline memory layout.

Physical module separation is combined with CMake unity compilation for the selected core/backend/kernel set, preserving cross-module inlining without reintroducing source-level state coupling.

## Data plane

```text
render/DAC reference -> bounded ring -> delay + ppm drift ----------------+
                                                                         v
mic S16 -> rate -> HPF -> optional 2-mic BF -> mono -> AEC -> predicted echo
                                                      |                  |
                                                      v                  v
                                                 residual ----------> RES/NS
                                                                         |
                                                                    VAD -> AGC
                                                                         |
                                                               rate -> mono S16
```

AEC runs once after microphone combination, not per microphone.

## Product resource versus runtime degradation

These dimensions are intentionally separate:

- `CALL` / `ASSISTANT`: user experience/use case;
- `TINY` / `LOW` / `STANDARD`: nominal product resource envelope;
- `FULL` / `LITE` / `SAFE`: runtime overload response.

A Cortex-A7 product may pass `STANDARD`; a Cortex-A32 product may deliberately ship `LOW`. The architecture never maps CPU model to resource class.

## Architecture kernels

AEC implementations call a small internal kernel contract for dot products and vector/complex updates. CMake compiles exactly one implementation:

- scalar C;
- Arm NEON.

There is no runtime CPU detection or function-pointer dispatch. CPU model and `-mcpu/-mfpu` settings live in build presets/certification records only.

## Synchronization and clock domains

The caller supplies the actual post-mix/post-gain DAC reference. Every ~100 ms the synchronization module performs a bounded coarse correlation plus one-sample local fine search.

- >20 ms mismatch emits a route/buffer-jump event;
- small mismatch feeds a ppm estimator;
- fractional drift is integrated and reference alignment moves by individual samples.

Core interprets a route-jump event by resetting the selected AEC backend. This keeps synchronization independent from AEC implementation details.

This is a lightweight AEC-reference alignment controller, not a full-band ASRC. Hardware capture/playback timestamps should seed/narrow it when available.

## Linux runtime

The runtime is Linux-specific and optional. It provides bounded SPSC input/output queues and one sleeping DSP worker. Default policy is topology-neutral (`dsp_cpu=-1`, `dsp_priority=0`). Affinity and `SCHED_FIFO` are explicit product integration choices.

ARMv7-A is treated as a first-class runtime target: queue/counter atomics use lock-free-width 32-bit objects rather than assuming cheap 64-bit atomic operations.

## Memory ownership

`ap_pipeline_init()` and `ap_runtime_init()` consume caller-owned aligned fixed storage. Alignment and exact-size functions are public contracts. Module-owned states are embedded directly in the one caller-owned pipeline object; there are no per-module heap allocations or duplicate public telemetry/config copies.
