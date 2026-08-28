# audio-pipeline

English | [简体中文](README.zh-CN.md)

`audio-pipeline` is a dependency-light, allocation-free real-time speech front end and composable DSP SDK for **low-compute Arm Linux products**. The same source supports ARMv7-A/Cortex-A7, Cortex-A32-class AArch32 systems and AArch64 products with comparable voice-processing budgets. CPU model names belong to build/certification profiles, not DSP algorithms.

The default high-level graph is topology-safe and fixed-order:

`S16 capture -> rate adapter -> HPF -> 2-mic BF -> SYNC -> Activity/DTD -> AEC -> RES -> NS -> AGC -> VAD -> mono S16`

The public frame contract is 10 ms. Device I/O supports 8/16/24/32/48 kHz within the selected build envelope; heavy DSP stays at 8 or 16 kHz. The synchronous data plane uses caller-owned bounded state, no heap allocation, no mutexes and no runtime SIMD/plugin dispatch.

## Integration modes

**High-level composed pipeline.** `ap_config_t.stages` selects a legal runtime subset of stages physically present in the binary. The order is fixed; this is deliberately not an arbitrary DAG.

**Standalone module SDK.** `audio_pipeline/audio_modules.h` exposes caller-owned APIs for resampler, HPF, beamformer, SYNC, Activity/DTD, AEC, RES, NS, AGC and VAD. Standalone wrappers use the same private implementations as the high-level pipeline.

Build-time composition:

```text
AP_BUILD_PIPELINE=ON|OFF
AP_MODULES=RESAMPLER,HPF,BF,SYNC,ACTIVITY,AEC,RES,NS,AGC,VAD
```

A module omitted from `AP_MODULES` loses its implementation TU and resident state; it is not merely bypassed.

Representative presets:

```bash
cmake --preset composition-full
cmake --preset composition-low
cmake --preset composition-tiny
cmake --preset composition-voice-frontend
cmake --preset composition-raw
cmake --preset composition-aec-only
cmake --preset composition-ns-only
cmake --preset composition-activity-only
cmake --preset composition-fast-resampler
```

Current hosted GCC Quality gates demonstrate physical pipeline RAM pruning:

```text
full   78,072 B
LOW    46,904 B
TINY   25,384 B
RAW     1,064 B
```

The Linux runtime is also build-envelope aware: the current hosted reference is `31,824 B` for the full 48 kHz/depth-8 envelope and `4,464 B` for the constrained 16 kHz/depth-4 TINY envelope. These numbers prove pruning for that compiler/ABI only; exact size functions remain authoritative.

## Product build envelope

Besides module selection, a shipping SKU can physically cap maximum geometry:

```text
AP_BUILD_MAX_IO_RATE_HZ
AP_BUILD_MAX_INTERNAL_RATE_HZ
AP_BUILD_MAX_MIC_CHANNELS
AP_BUILD_MAX_DELAY_MS
AP_BUILD_MAX_AEC_TAIL_MS
AP_RUNTIME_QUEUE_DEPTH
```

These caps shrink AEC partitions, SYNC render history, scratch and runtime queue storage where applicable. They are compile-time product constraints, independent of runtime `TINY/LOW/STANDARD` policy.

The generated installed `audio_pipeline_build.h` plus `ap_build_info()` report the exact binary fingerprint: version, module mask, backends, resampler mode, fast-math state and build geometry.

## DSP and realtime policy

- AEC: compile-time `MDF` default or `NLMS` fallback.
- NS estimator: `EMA` default or clean-room `MCRA` opt-in.
- SIMD: compile-time `SCALAR` or `NEON`.
- Resampler: `BANDLIMITED` default or legacy-speed `FAST` fallback.
- Fast math: OFF by default and never hidden in a CPU toolchain.
- Activity/DTD is a reusable module shared by the high-level AEC/RES path rather than duplicated logic.
- ERLE is valid only during AEC far-end-only/non-double-talk observations; convergence state is exposed explicitly.
- Large correlation/timestamp path jumps reset stale AEC convergence state.

The default boundary resampler uses small fixed FIR filters for supported downsampling ratios to reduce aliasing. `FAST` retains the previous lightweight interpolation/decimation behavior as an explicit product choice. The API reports resampler filter delay and high-level algorithmic latency includes that delay.

## Hardware timestamps and route changes

Products with trustworthy capture/playback hardware timestamps can seed SYNC using:

```c
ap_pipeline_observe_io_timestamps(...);
```

Both timestamps must describe corresponding positions in the same monotonic clock domain. Product-known route/path changes should call:

```c
ap_pipeline_notify_echo_path_change(...);
```

This explicitly clears stale SYNC/Activity/AEC state instead of waiting for correlation to rediscover the path.

## Linux runtime ownership

The synchronous API is caller-serialized. After a pipeline is handed to `audio_pipeline_runtime` and the worker is running, the worker owns pipeline access. Per-frame `ap_metrics_t` snapshots are returned through the SPSC output queue; control-plane `ap_runtime_get_metrics()` reads runtime-owned atomics only. ThreadSanitizer CI enforces this ownership model.

Runtime overload state is distinct from product resource class:

`FULL -> LITE -> SAFE` under sustained deadline pressure, with deterministic recovery.

## Build

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

CI cross-compiles all profiles; Quality CI additionally executes selected Cortex-A7 NEON and AArch64 contracts under QEMU. Cross-build/QEMU are correctness signals, never target-board performance claims.

## Installed SDK

Installation exports both CMake and pkg-config metadata:

```cmake
find_package(AudioPipeline CONFIG REQUIRED)
target_link_libraries(app PRIVATE AudioPipeline::core)
# Optional Linux runtime:
target_link_libraries(app PRIVATE AudioPipeline::runtime)
```

or:

```bash
pkg-config --cflags --libs audio-pipeline
```

CI installs the SDK into a clean prefix and builds/runs a separate consumer project, so package metadata is tested rather than only checking that files exist.

## Quality and release gates

Repository automation includes:

- native GCC/Clang, strict warnings, ASan/UBSan and libFuzzer smoke;
- ThreadSanitizer runtime ownership checks;
- MDF/NLMS, EMA/MCRA, precise/fast-math and BANDLIMITED/FAST composition contracts;
- RAW/LOW/TINY/voice/module-only builds;
- pipeline/runtime RAM and final consumer ELF pruning gates;
- generic ARMv7-A, Cortex-A7, Cortex-A32 and AArch64 cross-builds;
- Cortex-A7 NEON and AArch64 QEMU execution;
- >=90% hosted source line coverage gate, clang static analyzer and nightly fuzz;
- acoustic evaluation harness/schema and per-SKU certification schema;
- automatic v0.5.0-style SDK/source/checksum GitHub release from the project version on `main`.

Hosted x86 percentages are regression signals only. Shipping claims require the actual SoC/kernel/compiler/DVFS/audio route and acoustic corpus.

## Target certification

A shipping SKU is not considered product-certified until it records at least CPU/p95/p99/RSS/cache/context switches, XRUN/backpressure/overrun counters, thermal/power, acoustic corpus results and an 8 h soak. See:

- `docs/PLATFORM_SUPPORT.md`
- `docs/PERFORMANCE.md`
- `certification/record.schema.json`
- `eval/README.md`

No repository CI result is presented as Cortex-A7/A32 board performance.

## Documentation

- `docs/API_CONTRACT.md` — public lifecycle, state, composition and threading contracts
- `docs/ARCHITECTURE.md` — ownership and dependency direction
- `docs/DSP_DESIGN.md` — algorithm details
- `docs/PERFORMANCE.md` — regression and product certification gates
- `docs/PORTING.md` — BSP/ALSA/toolchain integration
- `docs/TUNING.md` — acoustic/product tuning rules
- `docs/DEVELOPMENT.md` — contribution and hard-cut rules
- `THIRD_PARTY.md` — clean-room/reference policy

## License

See [LICENSE](LICENSE).
