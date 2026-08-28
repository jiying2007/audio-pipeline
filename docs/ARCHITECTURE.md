# Architecture

## Goals

`audio-pipeline` is a static, bounded DSP SDK for low-compute embedded Linux. Architecture decisions optimize for deterministic 10 ms processing, caller-owned memory, compiler visibility, field diagnosability and SKU-level RAM/ROM pruning rather than dynamic graph flexibility.

## Dependency direction

```text
Application
   |---------------- High-level Pipeline API
   |---------------- Standalone Module API
                         |
                         v
core ----------------> stages
modules adapters -----> stages
                         |
                         v
                    dsp / arch

platform/linux -> public pipeline API
```

Production directories:

```text
src/core/            high-level config/orchestration/telemetry
src/frontend/        boundary resampler, HPF, beamformer
src/sync/            render delay, drift and timestamp observations
src/activity/        far-end/double-talk activity state
src/aec/             MDF/NLMS compile-time backend
src/enhance/         RES, Wiener NS, AGC, VAD
src/modules/         public standalone adapters only
src/dsp/             FFT/math primitives
src/arch/scalar/     portable kernels
src/arch/arm_neon/   NEON kernels
src/platform/linux/  SPSC worker/control/diagnostics runtime
```

Stage implementations never depend upward on `src/modules`, core or Linux runtime. Sibling stages do not call one another directly; cross-stage consequences are interpreted by core.

## Composition times

There are three separate product dimensions:

1. **Build modules** — `AP_MODULES` physically decides what code/state exists.
2. **Build envelope** — max IO/internal rate, mic count, delay, AEC tail and runtime queue depth size the binary.
3. **Runtime pipeline stages** — `ap_config_t.stages` selects a topology-safe subset of compiled DSP stages.

The high-level order is fixed. No node allocation, runtime plugin discovery, arbitrary DAG or function-pointer backend dispatch is used in the 10 ms path.

## State ownership

Each stage owns a narrow private state object. `src/core/ap_pipeline_internal.h` is the only full-pipeline composite state. Omitted modules and reduced build geometry shrink the composite object at compile time.

Frame scratch is lifetime-shared. RAW/resampler-only has a dedicated minimal scratch path instead of reserving the full voice graph scratch set.

SYNC render storage is derived from the compiled maximum delay/internal rate. AEC state is derived from compiled tail/internal rate. Runtime input/output arrays are derived from compiled max I/O rate, mic count, SYNC presence and queue depth.

Diagnostics audio history is deliberately **not** resident inside `ap_runtime_t`. The Flight Recorder is separately sized caller-owned memory, so production SKUs that do not enable audio dumps do not pay the pre/post-roll RAM cost.

## Standalone adapters

Standalone module wrappers embed/use the same private stage state as the high-level graph. They are deliberately excluded from full-pipeline unity compilation so an application using only the high-level API does not drag unused public adapters into the final ELF. Quality CI measures final linked consumer ELF ordering in addition to `.a`/state size.

## Unity compilation

The selected high-level stage implementations use CMake unity compilation to preserve cross-module inlining for tiny realtime graphs. Physical source/state ownership remains separate. Public standalone adapters are `SKIP_UNITY_BUILD_INCLUSION` and stay independently link-prunable.

## SYNC, timestamps and discontinuities

SYNC owns render history, delay/drift tracking and accepted hardware timestamp observations. Timestamp APIs translate trusted same-clock-domain observations into delay hints; they do not replace the correlation tracker.

Clock-drift correction has two layers: integer delay crossings remain explicit sample-slip accounting, while the fractional `drift_credit` residue is consumed by two-point reference interpolation. This preserves bounded state and avoids turning SYNC into a general ASRC.

A route jump is reported upward as an event. Core alone decides to reset AEC convergence. Product-known path changes use the explicit high-level notification, which resets SYNC/resampler/Activity/AEC state in deterministic order. Capture/render gaps, XRUN, clock reset and codec reopen use the separate stream-discontinuity contract.

## Activity/DTD

Activity is a reusable supporting module rather than an `AP_STAGE_*` node. It converts near/reference energy into shared far-end/double-talk state. The low-cost implementation adds attack/release smoothing, far-end hysteresis and double-talk on/hold thresholds with hangover. High-level AEC/RES/NS consume the same decision rather than recomputing independent gates.

## AEC adaptation and telemetry

AEC backends return narrow results/status to core. Public telemetry is aggregated only by core. ERLE validity is tied to a far-end-only AEC observation and an AEC convergence epoch; it is not a generic input/output ratio.

MDF and NLMS keep the configured fast adaptation cadence during acquisition/recovery. After a sustained stable far-end-only window they raise the runtime adaptation stride to reduce steady-state CPU. Double talk or loss of far-end activity resets the steady window and immediately restores the configured fast cadence.

## Resampler

The boundary resampler is stateful because the default BANDLIMITED mode carries short FIR history across frame boundaries. Supported fixed downsampling ratios use small first-party FIRs. FAST is an explicit compile-time fallback retaining the lightweight path. Filter delay is part of the public latency accounting.

## Linux runtime ownership

The Linux runtime owns one DSP worker plus bounded input/output/control/event queues. While running, the worker is the sole owner of the pipeline. The control plane never reads or mutates live pipeline memory directly.

```text
capture producer -> input SPSC ----------------------+
                                                       v
control producer -> bounded command queue -> DSP worker -> output SPSC -> consumer
                                             |   |
                                             |   +-> fixed-size event ring
                                             +------> optional caller-owned Flight Recorder
                                             |
                                             +------> runtime-owned atomic metrics
```

Frame metadata and commands are interpreted by the worker only at frame boundaries. A full output queue does **not** stop DSP execution: the worker processes into bounded scratch, discards that publication and keeps the DSP timeline continuous.

Event transport is intentionally best-effort. Flight Recorder triggering happens before event-ring delivery checks, so notification pressure cannot suppress a configured dump trigger.

Full per-frame pipeline metrics are copied into output slots before publication. Runtime summary metrics use lock-free-width atomics. Long-running public 64-bit counters are built from 32-bit atomic snapshots so ARMv7/A32 does not require lock-free 64-bit atomics. ThreadSanitizer is a required Quality gate for this ownership model.

## Diagnostics plane

Realtime diagnostics obey the same bounded-data-plane rules:

- no `printf`/formatted logging in the worker;
- no file I/O;
- no heap allocation;
- no JSON/protobuf encoding;
- fixed-size event records;
- separately provisioned bounded Flight Recorder memory;
- frozen `.apd` export only from the control side.

PC-side `apdump` and `apreplay` provide inspection, extraction and deterministic replay. Audio Quality CI exercises the complete dump -> parse/extract -> replay path.

## Architecture/SKU boundaries enforced by CI

Automation verifies:

- no repository-wide catch-all internal header;
- no CPU-model dependencies in DSP stages;
- Arm intrinsics only under `src/arch`;
- pthread/semaphore only under `src/platform/linux`;
- no data-plane heap allocation;
- module adapters do not become stage dependencies;
- composition and build envelopes compile/test independently;
- state RAM, runtime RAM and final consumer ELF physically shrink for smaller products;
- installed CMake/pkg-config consumers build outside the source tree;
- dump/replay and certification contracts remain executable;
- QEMU executes selected ARM contracts rather than cross-compiling only.

## Deliberate non-goals

- general-purpose audio DAG engine;
- runtime shared-object/plugin loading;
- unbounded logging/dump queues;
- no-FPU/fixed-point implementation in this profile;
- claims of target-board CPU/thermal/power based on hosted CI.
