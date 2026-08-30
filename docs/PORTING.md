# Porting Guide

## 1. Choose ABI/toolchain first

Generic toolchain files describe compiler/sysroot/ABI only. CPU tuning belongs in presets or product build configuration.

Continuously checked profiles:

```text
ARMv7-A armhf scalar
Cortex-A7 armhf scalar/VFPv4
Cortex-A7 armhf NEON/VFPv4
Cortex-A32 armhf NEON/FP-Armv8
AArch64 NEON/ASIMD
```

Do not copy Cortex-A32 `-mcpu/-mfpu` flags into an A7 BSP.

## 2. Define the product artifact

Choose the module set and maximum geometry before integrating ALSA/runtime:

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

Use `ap_build_info()` in product logs. The v2 structure contains both capability and exact build identity; no separate build-info compatibility surface exists.

## 3. Prefer installed package targets

```cmake
find_package(AudioPipeline CONFIG REQUIRED)
target_link_libraries(product PRIVATE AudioPipeline::core)
# Optional Linux worker:
target_link_libraries(product PRIVATE AudioPipeline::runtime)
```

Traditional BSP/Make projects may consume `audio-pipeline.pc` / `audio-pipeline-runtime.pc` through pkg-config.

## 4. PCM integration

The high-level frame period is fixed at 10 ms. Capture is 1/2-channel interleaved S16; render reference is mono S16; output is mono S16. The render reference should represent the post-mix/post-volume signal actually sent toward playback.

BANDLIMITED is the default boundary resampler and adds short FIR delay. Query high-level algorithmic latency rather than assuming enhancement is the only source of delay.

## 5. Hardware timestamps and path changes

If ALSA/codec/driver exposes trustworthy hardware timestamps, verify capture and playback positions use the **same monotonic clock domain** and correspond to the represented samples. Synchronous integrations may use `ap_pipeline_observe_io_timestamps()`.

For Linux runtime integrations, pass timestamps and discontinuities through `ap_frame_metadata_t` to `ap_runtime_submit_frame()`. Product-known route/path replacement uses `ap_runtime_command()` with the echo-path-change command once the worker owns the pipeline.

Do not call mutating pipeline APIs concurrently with the runtime worker.

## 6. Linux runtime lifecycle

The v2 runtime has one lifecycle and one telemetry surface:

```c
ap_runtime_config_t cfg = ap_runtime_config_default();
ap_runtime_options_t options = ap_runtime_options_default();
ap_runtime_t *runtime = NULL;

ap_runtime_open(runtime_memory, runtime_memory_bytes,
                pipeline, &cfg, &options, &runtime);
ap_runtime_start(runtime);

ap_runtime_submit_frame(runtime, mic, render_or_null, metadata_or_null);
ap_runtime_receive(runtime, output, pipeline_metrics_or_null);
ap_runtime_read_metrics(runtime, &runtime_metrics);

ap_runtime_stop(runtime);
ap_runtime_deinit(runtime);
```

`ap_runtime_open()` validates caller-owned memory, CPU/priority settings and options. `ap_runtime_submit_frame()` is a bounded SPSC producer; `AP_EFULL` means the application must account for the missing frame and report discontinuity/lost-frame metadata according to product policy. `ap_runtime_read_metrics()` exposes the full current runtime telemetry contract.

Affinity/FIFO are optional product decisions; defaults do not assume CPU1 or realtime privilege.

## 7. ALSA geometry

Choose period/buffer sizes compatible with 10 ms processing. Record capture/playback period and total buffer, independent clock behavior, timestamp source/domain, XRUN recovery, thread/cpuset and IRQ affinity.

The bundled ALSA examples are compile/integration references, not universal product policy.

## 8. Validate the actual target

Use Trusted Runner Readiness before HIL/certification. Run target benchmark and real route soak with the shipping compiler/kernel/DVFS/audio path and preserve exact source/toolchain/binary identity.

At minimum collect CPU, frame p95/p99, RSS/cache/context switches, XRUN/backpressure/overrun, thermal/power and acoustic corpus results. Formal shipping acceptance uses schema-v4 `certification/record.schema.json` and the shipping policy minimum; the checked-in Cortex-A32 LOW policy requires 72 hours.

QEMU and hosted CI prove correctness portability only; they never replace target-board evidence.
