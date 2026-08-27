# Architecture

## Product goals

1. One classical voice SDK for low-compute Arm Linux product families, not one CPU model.
2. Fixed 10 ms scheduling, bounded caller-owned state and allocation-free synchronous DSP.
3. Heavy compute stays at 8/16 kHz even when device I/O is 24/32/48 kHz.
4. High-level pipeline and standalone module SDK reuse one implementation set.
5. Compile-time product composition physically removes unused TUs/state; runtime composition selects a legal subset of compiled stages.
6. No arbitrary DAG, dynamic plugin discovery or hot-path function-pointer dispatch.
7. Linux/threading remains an adapter around the portable synchronous APIs.

## Layers

```text
application
   |
   +--> high-level pipeline API -----+
   |                                  |
   +--> standalone module SDK --------+--> stage implementations --> dsp/arch
                                      |
platform/linux runtime --> pipeline API
```

Production ownership:

```text
src/core/            public config/lifecycle, composite state, fixed graph orchestration, telemetry
src/frontend/        resampler, HPF, beamformer
src/sync/            render history, delay/route-jump/clock-drift
src/aec/             MDF or NLMS backend
src/enhance/         RES, NS, AGC, VAD
src/modules/         public standalone adapters only
src/dsp/             FFT/math primitives and DSP types
src/arch/            scalar/NEON kernels
src/platform/linux/  optional SPSC runtime
```

The dependency direction and realtime rules are enforced by `scripts/check-architecture.sh`. Stage implementations never depend upward on core or `src/modules`. Core never calls the standalone wrapper layer; both consumers call the same lower implementation contracts.

## Build-time graph

`AP_MODULES` defines which product capabilities physically exist. CMake compiles only those stage translation units and wraps pipeline state members with `AP_BUILD_STAGE_*` conditions. This is the ROM/RAM pruning boundary.

The generated installed `audio_pipeline_build.h` records the resulting capability set. Module-only builds can ship AEC or NS without the high-level pipeline header/runtime.

Representative graphs:

```text
FULL:          RESAMPLER HPF BF SYNC AEC RES NS AGC VAD
VOICE_FRONTEND:RESAMPLER HPF BF              NS AGC VAD
RAW:           RESAMPLER
AEC_ONLY:                           AEC
NS_ONLY:                                    NS
```

The first three may build the high-level pipeline; AEC_ONLY/NS_ONLY are standalone-SDK products. CI verifies physical high-level pipeline state pruning: full > voice frontend > RAW.

## Runtime graph

For a build containing the high-level pipeline, `ap_config_t.stages` chooses a subset of compiled DSP stages. It never changes topology. The execution order remains:

```text
rate -> HPF -> BF -> SYNC -> AEC -> RES/NS -> AGC -> VAD -> rate
```

Validation encodes the semantic edges instead of letting illegal graphs fail later:

```text
BF  requires 2 microphone channels
AEC requires SYNC
RES requires AEC
delay/drift policies require SYNC
runtime stages must be subset of compiled stages
```

RESAMPLER is a mandatory high-level boundary component, not an `AP_STAGE_*` bit, so RAW is represented by an empty DSP stage mask.

## State ownership

`src/core/ap_pipeline_internal.h` is the only full-pipeline composite state. Every selected stage owns a distinct state type. Conditional members mean an omitted module contributes zero resident pipeline state.

Standalone state is also caller-owned. The wrapper may add only small adapter metadata such as configured frame size; it embeds/reuses the same stage state rather than maintaining a parallel algorithm implementation.

Current GCC CI measurements are:

```text
full pipeline           78,456 B
voice frontend           9,936 B
RAW/resampler-only       3,392 B
```

These establish pruning behavior, not a cross-compiler ABI promise.

## Data/control interactions

Cross-stage effects are returned to core as events/results rather than sibling calls. SYNC reports route jumps; core resets AEC only when AEC is selected. Shared far-end/double-talk activity is computed once and passed to AEC/RES/NS.

Standalone AEC intentionally accepts activity and aligned reference from its caller. An application that wants repository-owned delay/drift may compose standalone SYNC before standalone AEC itself. This keeps AEC independently reusable without silently importing a 32 KiB render ring.

## Performance strategy

Source ownership stays modular. The full high-level target uses CMake unity compilation to preserve cross-module inlining/cache locality. Module-only builds retain independent TUs so the linker can prune at object granularity.

No runtime node objects, virtual tables or generic graph executor are used. The composition layer is deliberately finite and static because low-end Cortex-A7/A32 determinism is more important than desktop-style arbitrary graph flexibility.

## Linux runtime

The Linux runtime observes the initialized stage mask. Duplex graphs feed render only when SYNC exists; capture-only graphs process without a render path. It still uses bounded SPSC queues and a sleeping worker with topology-neutral defaults (`dsp_cpu=-1`, `dsp_priority=0`).

ARMv7-A remains first-class: realtime counters use lock-free-width 32-bit atomics rather than assuming cheap 64-bit atomics.

## CPU/platform separation

AEC kernels compile as scalar or NEON without algorithm code naming Cortex models. CPU model and `-mcpu/-mfpu` settings live in build presets/certification records. Resource class, compiled graph and runtime FULL/LITE/SAFE quality are independent product dimensions.
