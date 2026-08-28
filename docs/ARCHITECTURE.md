# Architecture

## Goals

`audio-pipeline` is a static, bounded DSP SDK for low-compute embedded Linux. Architecture decisions optimize for deterministic 10 ms processing, caller-owned memory, compiler visibility and SKU-level RAM/ROM pruning rather than dynamic graph flexibility.

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
src/platform/linux/  SPSC worker/control plane
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

## Standalone adapters

Standalone module wrappers embed/use the same private stage state as the high-level graph. They are deliberately excluded from full-pipeline unity compilation so an application using only the high-level API does not drag unused public adapters into the final ELF. Quality CI measures final linked consumer ELF ordering in addition to `.a`/state size.

## Unity compilation

The selected high-level stage implementations use CMake unity compilation to preserve cross-module inlining for tiny realtime graphs. Physical source/state ownership remains separate. Public standalone adapters are `SKIP_UNITY_BUILD_INCLUSION` and stay independently link-prunable.

## SYNC, timestamps and route changes

SYNC owns render history, delay/drift tracking and accepted hardware timestamp observations. Timestamp APIs only translate trusted same-clock-domain observations into delay hints; they do not replace the correlation tracker.

A route jump is reported upward as an event. Core alone decides to reset AEC convergence. Product-known path changes use the explicit high-level notification, which resets SYNC/resampler/Activity/AEC state in a deterministic order.

## Activity/DTD

Activity is a reusable supporting module rather than an `AP_STAGE_*` node. It converts near/reference energies into shared far-end/double-talk state with hangover. High-level AEC requires Activity support in the build, and AEC/RES/NS consume one common decision rather than recomputing independent gates.

## AEC/ERLE telemetry

AEC backends return narrow results/status to core. Public telemetry is aggregated only by core. ERLE validity is tied to a far-end-only AEC observation and an AEC convergence epoch; it is not a generic input/output ratio.

## Resampler

The boundary resampler is stateful because the default BANDLIMITED mode carries short FIR history across frame boundaries. Supported fixed downsampling ratios use small first-party FIRs. FAST is an explicit compile-time fallback retaining the legacy lightweight path. Filter delay is part of the public latency accounting.

## Linux runtime ownership

The Linux runtime owns one worker and bounded SPSC queues. While running, the worker is the sole owner of the pipeline. The control plane never snapshots live pipeline memory directly.

```text
producer -> input SPSC -> DSP worker -> output SPSC -> consumer
                              |
                              +-> runtime-owned atomic counters/quality
```

Full per-frame pipeline metrics are copied into the output slot before publication. Runtime summary metrics are atomic. ThreadSanitizer is a required Quality gate for this ownership model.

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
- QEMU executes selected ARM contracts rather than cross-compiling only.

## Deliberate non-goals

- general-purpose audio DAG engine;
- runtime shared-object/plugin loading;
- no-FPU/fixed-point implementation in this profile;
- claims of target-board CPU/thermal/power based on hosted CI.
