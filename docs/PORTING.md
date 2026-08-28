# Porting Guide

## 1. Choose ABI/toolchain first

Generic toolchain files describe compiler/sysroot/ABI only. CPU tuning belongs in presets or product build configuration.

Current continuously checked profiles:

```text
ARMv7-A armhf scalar
Cortex-A7 armhf scalar/VFPv4
Cortex-A7 armhf NEON/VFPv4
Cortex-A32 armhf NEON/FP-Armv8
AArch64 NEON/ASIMD
```

Do not copy Cortex-A32 `-mcpu/-mfpu` flags into an A7 BSP.

## 2. Define the product artifact

Choose module set and maximum geometry before integrating ALSA/runtime:

```text
AP_MODULES
AP_BUILD_MAX_IO_RATE_HZ
AP_BUILD_MAX_INTERNAL_RATE_HZ
AP_BUILD_MAX_MIC_CHANNELS
AP_BUILD_MAX_DELAY_MS
AP_BUILD_MAX_AEC_TAIL_MS
AP_RUNTIME_QUEUE_DEPTH
AP_AEC_BACKEND
AP_NS_ESTIMATOR
AP_SIMD_BACKEND
AP_RESAMPLER_MODE
AP_ENABLE_FAST_MATH
```

Use `ap_build_info()` in product logs so the deployed binary can be reconstructed unambiguously.

## 3. Prefer installed package targets

For CMake products:

```cmake
find_package(AudioPipeline CONFIG REQUIRED)
target_link_libraries(product PRIVATE AudioPipeline::core)
```

Optional Linux worker:

```cmake
target_link_libraries(product PRIVATE AudioPipeline::runtime)
```

Traditional BSP/Make projects may consume `audio-pipeline.pc` / `audio-pipeline-runtime.pc` through pkg-config.

## 4. PCM integration

High-level frame period is fixed at 10 ms. Capture is 1/2-channel interleaved S16; render reference is mono S16; output is mono S16.

The render reference should represent the post-mix/post-volume signal actually headed toward playback. A pre-volume or unrelated media buffer weakens AEC observability.

BANDLIMITED is the default boundary resampler and adds short FIR delay. Query high-level algorithmic latency instead of assuming NS is the only source of delay.

## 5. Hardware timestamps

If ALSA/codec/driver exposes trustworthy hardware timestamps, verify that capture and playback positions are represented in the **same monotonic clock domain** and refer to corresponding sample positions. Then feed observations through:

```c
ap_pipeline_observe_io_timestamps(...)
```

Do not convert unrelated wall-clock timestamps into delay observations. When timestamp quality is uncertain, keep correlation tracking as the authority.

## 6. Product-known path changes

When the application knows that the acoustic route changed (codec reopen, speaker device/route replacement, gain-path switch, major topology change), call:

```c
ap_pipeline_notify_echo_path_change(...)
```

This clears stale SYNC/Activity/AEC state deterministically.

## 7. Linux runtime ownership

The synchronous API is caller-serialized. Once `ap_runtime_start()` succeeds, the runtime worker owns the pipeline until stop/deinit. Do not call pipeline metrics/quality/process APIs concurrently from another thread.

Use:

- `ap_runtime_submit()` for producer input;
- `ap_runtime_receive()` for complete per-frame output + pipeline metric snapshot;
- `ap_runtime_get_metrics()` for atomic runtime counters/quality.

Affinity/FIFO are optional product decisions; defaults do not assume CPU1 or realtime privilege.

## 8. ALSA geometry

Choose ALSA period/buffer sizes compatible with 10 ms processing. Record:

- capture/playback period and total buffer;
- whether capture/playback clocks are independent;
- hardware timestamp source/domain;
- XRUN recovery behavior;
- thread/cpuset/IRQ affinity.

The bundled ALSA examples are compile/integration references, not universal product policy.

## 9. Validate the actual target

Run the target benchmark and 8 h soak using the shipping compiler/kernel/DVFS/audio route. Record the artifact through `certification/record.schema.json`.

At minimum capture CPU, frame p95/p99, RSS/cache/context switches, XRUN/backpressure/overrun, thermal/power and acoustic corpus results.

QEMU and hosted CI prove correctness portability; they do not replace this step.
