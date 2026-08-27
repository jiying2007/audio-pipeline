# audio-pipeline

English | [简体中文](README.zh-CN.md)

A dependency-light, allocation-free real-time speech front end for **low-compute Arm Linux products**. The same DSP core is intended for ARMv7-A and ARMv8-A/AArch32-class systems such as Cortex-A7 and Cortex-A32, plus AArch64 products with comparable voice-processing budgets. CPU names are build/certification profiles, not DSP dependencies.

Default graph:

`S16 capture -> rate adapter -> HPF -> 2-mic BF -> delay/drift -> AEC -> RES -> STFT Wiener NS -> VAD -> AGC/limiter -> mono S16`

The public frame contract is fixed at 10 ms. Device I/O supports 8/16/24/32/48 kHz; heavy DSP stays at 8 or 16 kHz. The synchronous data plane uses caller-owned bounded state, no heap allocation, no mutexes and no runtime SIMD dispatch.

## Product dimensions

Three independent dimensions avoid tying product policy to one CPU model:

- **Use case:** `AP_PROFILE_CALL` or `AP_PROFILE_ASSISTANT`.
- **Resource class:** `AP_RESOURCE_TINY`, `AP_RESOURCE_LOW`, `AP_RESOURCE_STANDARD` selected at product configuration time.
- **Runtime quality:** `FULL`, `LITE`, `SAFE` selected automatically by the Linux overload controller or explicitly by the caller.

`TINY` defaults to an 8 kHz internal path, shorter AEC tail and no beamformer tracking; `LOW` retains 16 kHz with a shorter tail; `STANDARD` keeps the existing full voice-band geometry. These are starting envelopes, not Cortex-A7/A32 labels: certify the class on the actual board.

## Architecture

Production source boundaries are explicit:

```text
src/core/            pipeline/config/orchestration
src/frontend/        boundary resampler, HPF, beamformer
src/sync/            render delay and clock-drift alignment
src/aec/             compile-time MDF or NLMS backend
src/enhance/         RES, Wiener NS, AGC, VAD
src/dsp/             FFT/math primitives
src/arch/scalar/     portable scalar kernels
src/arch/arm_neon/   Arm NEON kernels
src/platform/linux/  pthread/semaphore SPSC runtime only
```

The algorithms never include Arm intrinsics or pthread/semaphore headers directly. SIMD and AEC selection are compile-time backends, so modularity does not add virtual calls/function-pointer dispatch to the 10 ms path.

## Build policy

The hard-cut build switches are:

```text
AP_AEC_BACKEND=MDF|NLMS
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
cmake --build build/cortex-a7-neon --parallel
```

The generic toolchain files describe compiler/ABI only; `-mcpu/-mfpu` tuning lives in presets or product build configuration.

## Caller-owned state contract

The exact state size is build-specific; the hard public ceiling is 80,000 bytes. Storage must be 16-byte aligned:

```c
_Alignas(AP_PIPELINE_STATE_ALIGNMENT)
static unsigned char pipeline_mem[AP_PIPELINE_STATE_MAX_BYTES];

ap_pipeline_t *pipeline = NULL;
ap_config_t cfg = ap_config_for_resource(AP_PROFILE_CALL, AP_RESOURCE_LOW);
ap_status_t rc = ap_pipeline_init(pipeline_mem, sizeof(pipeline_mem), &cfg, &pipeline);
```

Invalid/null/misaligned arguments return `AP_EINVAL`; insufficient caller-owned storage returns `AP_ENOMEM`. See [API contract](docs/API_CONTRACT.md).

## AEC, synchronization and enhancement

The default AEC is a clean-room partitioned MDF/AUMDF-lite implementation with five 2 ms sub-blocks per 10 ms frame. `AP_AEC_BACKEND=NLMS` builds the independent time-domain fallback. Both backends expose predicted echo internally for residual suppression.

The render reference must be the actual post-mix/post-gain DAC signal. A bounded coarse/fine tracker handles route-delay changes and small clock mismatch; large path jumps reset adaptive state. Hardware capture/playback timestamps remain preferred for narrowing the search.

FULL/LITE use frequency-dependent residual suppression when NS is active; SAFE or NS-off uses broadband RES. True double-talk disables subband RES.

## Linux runtime

The portable core does not require Linux. `AP_ENABLE_LINUX_RUNTIME=ON` adds the Linux-only bounded SPSC worker using pthreads, C11 atomics and a POSIX semaphore. Runtime defaults are topology-neutral:

```text
dsp_cpu = -1
dsp_priority = 0
```

Product integration may explicitly pin a worker or request `SCHED_FIFO` after IRQ/cpuset validation. The runtime uses lock-free-width 32-bit atomics internally so ARMv7-A telemetry does not depend on hidden 64-bit atomic locks.

## Verification

CI covers native GCC/Clang, strict warnings, ASan/UBSan, fuzzing, MDF and NLMS, explicit fast-math mode, optional ALSA compilation, runtime/performance smoke, architecture-boundary lint, and a cross-build matrix for:

- generic ARMv7-A scalar;
- Cortex-A7 scalar;
- Cortex-A7 NEON/VFPv4;
- Cortex-A32 NEON/FP-Armv8;
- generic AArch64/NEON.

Cross-build means **build-supported**, not board-certified. CPU/RSS/thermal/power claims require the shipping board/kernel/compiler/DVFS/audio route and the target benchmark/8 h soak wrappers.

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
