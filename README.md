# audio-pipeline

English | [简体中文](README.zh-CN.md)

A dependency-light, allocation-free real-time speech front end and composable DSP SDK for **low-compute Arm Linux products**. The same codebase targets ARMv7-A and ARMv8-A/AArch32-class systems such as Cortex-A7 and Cortex-A32, plus AArch64 products with comparable voice-processing budgets. CPU names are build/certification profiles, not DSP dependencies.

The high-level pipeline uses the topology-safe order:

`S16 capture -> rate adapter -> HPF -> 2-mic BF -> delay/drift -> AEC -> RES -> STFT Wiener NS -> AGC -> VAD -> mono S16`

The public frame contract is fixed at 10 ms. Device I/O supports 8/16/24/32/48 kHz; heavy DSP stays at 8 or 16 kHz. The synchronous data plane uses caller-owned bounded state, no heap allocation, no mutexes and no runtime SIMD/plugin dispatch.

## Two consumption modes

`audio-pipeline` supports two deliberate integration levels without maintaining duplicate DSP implementations.

**High-level composed pipeline.** `ap_config_t.stages` selects a legal runtime subset of the modules physically present in the build. The order is fixed and validated; this is not an arbitrary DAG. Examples include full CALL, capture-only voice frontend and RAW rate adaptation.

**Standalone module SDK.** `audio_pipeline/audio_modules.h` exposes caller-owned standalone APIs for resampler, HPF, beamformer, sync, AEC, RES, NS, AGC and VAD. These wrappers call the same internal implementations used by the high-level pipeline.

Compile-time product composition is controlled by:

```text
AP_BUILD_PIPELINE=ON|OFF
AP_MODULES=RESAMPLER,HPF,BF,SYNC,AEC,RES,NS,AGC,VAD
```

A module omitted from `AP_MODULES` is not merely bypassed: its translation unit and pipeline resident state are removed. The generated installed header `audio_pipeline_build.h` exposes `AP_HAVE_PIPELINE` and `AP_HAVE_MODULE_*` as the build capability source of truth.

Representative presets:

```bash
cmake --preset composition-full
cmake --preset composition-voice-frontend
cmake --preset composition-raw
cmake --preset composition-aec-only
cmake --preset composition-ns-only
```

Current GCC CI composition probes report `78,456 B` for the full graph, `9,936 B` for the voice-front-end graph and `3,392 B` for RAW/resampler-only. These numbers prove physical pruning for that build; use the exact size function for every shipping compiler/ABI.

## Composition rules

The pipeline validates dependencies at initialization:

- BF requires two microphone channels;
- AEC requires SYNC/reference alignment;
- RES requires AEC;
- delay/drift policy requires SYNC;
- runtime stages must be a subset of stages compiled into the binary.

A RAW pipeline may have no DSP stage bits at all; RESAMPLER is a boundary module rather than an `AP_STAGE_*` DSP stage. A capture-only graph does not require a render reference, and the Linux runtime only submits render when SYNC is active.

## Product dimensions

Three independent dimensions avoid tying product policy to one CPU model:

- **Use case:** `AP_PROFILE_CALL` or `AP_PROFILE_ASSISTANT`.
- **Resource class:** `AP_RESOURCE_TINY`, `AP_RESOURCE_LOW`, `AP_RESOURCE_STANDARD` selected at product configuration time.
- **Runtime quality:** `FULL`, `LITE`, `SAFE` selected automatically by the Linux overload controller or explicitly by the caller.

`TINY` defaults to an 8 kHz internal path, shorter AEC tail and no beamformer tracking; `LOW` retains 16 kHz with a shorter tail; `STANDARD` keeps the full voice-band geometry. These are starting envelopes, not Cortex-A7/A32 labels: certify the class on the actual board.

## Architecture

Production source boundaries are explicit:

```text
src/core/            pipeline/config/orchestration
src/frontend/        boundary resampler, HPF, beamformer
src/sync/            render delay and clock-drift alignment
src/aec/             compile-time MDF or NLMS backend
src/enhance/         RES, Wiener NS, AGC, VAD
src/modules/         public standalone adapters only
src/dsp/             FFT/math primitives
src/arch/scalar/     portable scalar kernels
src/arch/arm_neon/   Arm NEON kernels
src/platform/linux/  pthread/semaphore SPSC runtime only
```

The algorithms never include Arm intrinsics or pthread/semaphore headers directly. Public module wrappers depend downward on stage implementations; core never calls back through the wrapper layer. Full-pipeline unity compilation preserves cross-module inlining while source/state ownership remains modular.

## Build policy

The hard-cut selectors are:

```text
AP_BUILD_PIPELINE=ON|OFF
AP_MODULES=...
AP_AEC_BACKEND=MDF|NLMS
AP_NS_ESTIMATOR=EMA|MCRA
AP_SIMD_BACKEND=SCALAR|NEON
AP_ENABLE_LINUX_RUNTIME=ON|OFF
AP_ENABLE_FAST_MATH=ON|OFF
```

Fast math is **OFF by default** and is a product performance policy, not part of a CPU toolchain.

Native Linux:

```bash
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build --parallel
ctest --test-dir build --output-on-failure
```

Cross-build presets:

```bash
cmake --preset armv7a-scalar
cmake --preset cortex-a7-scalar
cmake --preset cortex-a7-neon
cmake --preset cortex-a32-neon
cmake --preset aarch64-neon
```

The generic toolchain files describe compiler/ABI only; `-mcpu/-mfpu` tuning lives in presets or product build configuration.

## Caller-owned state contract

Pipeline state is build-specific; the high-level hard ceiling is 80,000 bytes. Standalone modules use the independent `AP_MODULE_STATE_MAX_BYTES` ceiling and `AP_MODULE_STATE_ALIGNMENT`. Always prefer each exact `*_state_size()` function when sizing a product image.

```c
_Alignas(AP_PIPELINE_STATE_ALIGNMENT)
static unsigned char pipeline_mem[AP_PIPELINE_STATE_MAX_BYTES];

ap_pipeline_t *pipeline = NULL;
ap_config_t cfg = ap_config_for_resource(AP_PROFILE_CALL, AP_RESOURCE_LOW);
cfg.stages = AP_STAGE_HPF | AP_STAGE_NS | AP_STAGE_AGC | AP_STAGE_VAD;
ap_status_t rc = ap_pipeline_init(pipeline_mem, sizeof(pipeline_mem), &cfg, &pipeline);
```

Invalid/null/misaligned arguments return `AP_EINVAL`; insufficient caller-owned storage returns `AP_ENOMEM`; requesting a stage that is not compiled into the SDK returns `AP_ESTATE`. See [API contract](docs/API_CONTRACT.md).

## AEC, synchronization and enhancement

The default AEC is a clean-room partitioned MDF/AUMDF-lite implementation with five 2 ms sub-blocks per 10 ms frame. `AP_AEC_BACKEND=NLMS` builds the independent time-domain fallback. The default NS noise estimator is EMA; clean-room MCRA-lite remains an opt-in compile-time backend.

The render reference must be the actual post-mix/post-gain DAC signal. A bounded coarse/fine tracker handles route-delay changes and small clock mismatch; large path jumps reset adaptive state. Hardware capture/playback timestamps remain preferred for narrowing the search.

FULL/LITE use frequency-dependent residual suppression when RES+NS are selected; SAFE uses broadband RES. Shared double-talk activity freezes AEC adaptation and disables subband RES.

## Linux runtime

The portable core does not require Linux. `AP_ENABLE_LINUX_RUNTIME=ON` adds the Linux-only bounded SPSC worker using pthreads, C11 atomics and a POSIX semaphore. Runtime defaults are topology-neutral (`dsp_cpu=-1`, `dsp_priority=0`). Capture-only composed pipelines are supported; render submission is required only when SYNC is selected.

## Verification

CI covers native GCC/Clang, strict warnings, ASan/UBSan, fuzzing, MDF/NLMS, EMA/MCRA, explicit fast-math mode, optional ALSA, architecture-boundary lint, full/RAW/voice/AEC-only/NS-only composition contracts, physical state-size pruning, same-runner regression gates and cross-builds for generic ARMv7-A scalar, Cortex-A7 scalar/NEON, Cortex-A32 NEON and AArch64 NEON.

Hosted x86 timing is regression evidence only. Cross-build means **build-supported**, not board-certified. CPU/RSS/thermal/power claims require the shipping board/kernel/compiler/DVFS/audio route and target benchmark/8 h soak.

## Documentation

- [Platform support and certification](docs/PLATFORM_SUPPORT.md)
- [Architecture](docs/ARCHITECTURE.md)
- [API contract](docs/API_CONTRACT.md)
- [DSP design](docs/DSP_DESIGN.md)
- [Porting](docs/PORTING.md)
- [Performance and release gates](docs/PERFORMANCE.md)
- [Tuning](docs/TUNING.md)
- [Development/module rules](docs/DEVELOPMENT.md)

## License

Apache-2.0. No third-party DSP source is vendored; see [THIRD_PARTY.md](THIRD_PARTY.md).
