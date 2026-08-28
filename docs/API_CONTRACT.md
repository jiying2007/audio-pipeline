# Public API Contract

## Frame and sample contract

High-level pipeline:

- fixed frame duration: **10 ms**;
- capture: 1 or 2 channel interleaved S16, within the compiled mic envelope;
- render reference: mono S16 corresponding to the signal actually sent toward the DAC;
- output: mono S16;
- I/O rates: 8/16/24/32/48 kHz, limited by `AP_BUILD_MAX_IO_RATE_HZ`;
- internal rates: 8 or 16 kHz, limited by `AP_BUILD_MAX_INTERNAL_RATE_HZ`.

Standalone float DSP modules use normalized float samples and are fixed to the 10 ms frame implied by their init sample rate. Resampler APIs explicitly accept the supported 10 ms input/output frame geometries. Partial buffer overlap is unsupported unless explicitly documented.

## Build capability and fingerprint

Compile-time composition:

```text
AP_BUILD_PIPELINE=ON|OFF
AP_MODULES=RESAMPLER,HPF,BF,SYNC,ACTIVITY,AEC,RES,NS,AGC,VAD
```

The generated installed `audio_pipeline_build.h` is the macro capability source of truth. `ap_build_info()` exposes the corresponding runtime-readable immutable fingerprint including:

- semantic version;
- module mask;
- AEC/NS/SIMD/resampler backend names;
- fast-math state;
- pipeline/runtime presence;
- max I/O/internal rate, microphone channels, delay, AEC tail and runtime queue depth.

A module omitted from the build has no standalone declaration, implementation TU or embedded pipeline state.

## Build-time SKU envelope

The following are physical binary limits, not tuning suggestions:

```text
AP_BUILD_MAX_IO_RATE_HZ
AP_BUILD_MAX_INTERNAL_RATE_HZ
AP_BUILD_MAX_MIC_CHANNELS
AP_BUILD_MAX_DELAY_MS
AP_BUILD_MAX_AEC_TAIL_MS
AP_RUNTIME_QUEUE_DEPTH
```

Configuration outside the compiled envelope returns `AP_EINVAL`. The build envelope may reduce AEC partitions, SYNC render history, scratch geometry and runtime queue storage.

## Runtime pipeline composition

`ap_config_t.stages` selects a topology-safe subset of compiled DSP stages. The order is fixed; stage bits do not define a DAG.

Validation rules include:

- unknown/uncompiled stage -> `AP_ESTATE`;
- BF requires two microphones;
- high-level AEC requires SYNC and a build containing Activity/DTD support;
- RES requires AEC;
- delay/drift policy requires SYNC;
- all floating configuration parameters used by an enabled stage must be finite and in range.

RESAMPLER and Activity are supporting modules rather than public `AP_STAGE_*` bits. RAW/resampler-only is valid with `stages == 0`.

## Caller-owned state

Synchronous DSP does not allocate persistent state.

High-level pipeline:

```c
_Alignas(AP_PIPELINE_STATE_ALIGNMENT)
static unsigned char pipeline_mem[AP_PIPELINE_STATE_MAX_BYTES];
```

- alignment: 16 bytes;
- public hard ceiling: 80,000 bytes;
- `ap_pipeline_state_size()` is the exact requirement for the selected compiled graph.

Standalone stateful modules use `AP_MODULE_STATE_ALIGNMENT`, `AP_MODULE_STATE_MAX_BYTES` and exact `ap_module_*_state_size()` functions.

Linux runtime uses `AP_RUNTIME_STATE_ALIGNMENT`, `AP_RUNTIME_STATE_MAX_BYTES` and exact runtime size APIs. Runtime storage is also compile-time envelope aware.

Hosted GCC Quality CI currently demonstrates physical pipeline state pruning of full=78,072 B, LOW=46,904 B, TINY=25,384 B and RAW=1,064 B, and runtime pruning of full=31,824 B vs constrained TINY=4,464 B. These are verification values, not ABI constants.

## Standalone module lifecycle

Stateful standalone modules follow:

```text
state_size -> aligned caller storage -> init -> process/reset/status as applicable
```

Resampler, HPF, BF, SYNC, Activity, AEC, RES, NS, AGC and VAD all expose reset semantics when stateful. Wrappers reuse the same private implementation as the high-level pipeline.

Activity/DTD is independently available for applications that compose SYNC + Activity + AEC themselves. AEC standalone consumes already aligned microphone/reference frames plus explicit far-end/double-talk decisions.

## Resampler contract

`AP_RESAMPLER_MODE=BANDLIMITED|FAST` is compile-time.

- `BANDLIMITED` is the default and applies small fixed FIR filters to the supported downsampling ratios to reduce aliasing.
- `FAST` preserves the legacy lightweight interpolation/decimation path for explicitly accepted products.
- resampler state preserves history across 10 ms frames;
- reset restores deterministic initial history;
- filter delay is exposed through the standalone API and included in high-level algorithmic latency.

## Timestamp and echo-path contract

`ap_pipeline_observe_io_timestamps()` is optional. Capture and render timestamps must describe corresponding hardware positions in the same monotonic clock domain. Invalid/non-positive or out-of-envelope delay observations return `AP_EINVAL`.

A sufficiently large timestamp delay jump is treated as a route jump and resets stale AEC convergence state through the core orchestrator.

`ap_pipeline_notify_echo_path_change()` is for product-known route/path changes such as codec reopen, speaker path change or gain-route replacement. It resets stale SYNC/resampler/Activity/AEC state without waiting for correlation search.

## Telemetry semantics

`ap_metrics_t.erle_valid` is true only for valid AEC far-end-only, non-double-talk observations. ERLE does not update for non-AEC graphs or during double-talk. `aec_convergence_frames` counts valid convergence observations within the current AEC epoch; `aec_converged` is an explicit heuristic status. Route/path resets start a new epoch.

`timestamp_observations` counts accepted timestamp observations. Delay jumps, sample slips, AEC resets and underruns remain monotonic per initialized pipeline instance.

## Threading and runtime ownership

Synchronous pipeline/module APIs are caller-serialized and create no threads.

When `audio_pipeline_runtime` is running, the worker owns the supplied pipeline. Applications must not directly call pipeline mutating/metrics APIs until the runtime is stopped. Complete per-frame `ap_metrics_t` snapshots travel through the SPSC output queue. `ap_runtime_get_metrics()` reads only runtime-owned atomics and never reads live pipeline state concurrently.

This ownership model is validated by ThreadSanitizer CI. Runtime counters intentionally use lock-free-width atomics suitable for ARMv7-A and widen public snapshots to 64 bits.

## Status semantics

| Status | Meaning |
|---|---|
| `AP_OK` | operation completed |
| `AP_EINVAL` | NULL, bad alignment, non-finite/out-of-range value, unsupported geometry or dependency violation |
| `AP_ENOMEM` | caller state buffer is too small |
| `AP_ESTATE` | feature not compiled or invalid lifecycle/state |
| `AP_EFULL` | bounded producer queue full |
| `AP_EEMPTY` | bounded consumer queue empty |

`AP_ENOMEM` is never a generic invalid-argument status.

## Configuration dimensions

Independent dimensions are:

- use case: CALL / ASSISTANT;
- runtime resource class: TINY / LOW / STANDARD;
- compiled module set;
- compiled SKU envelope;
- runtime stage subset;
- runtime overload quality: FULL / LITE / SAFE.

CPU model does not imply any one resource class.

## Compile-time backend contract

```text
AP_AEC_BACKEND=MDF|NLMS
AP_NS_ESTIMATOR=EMA|MCRA
AP_SIMD_BACKEND=SCALAR|NEON
AP_RESAMPLER_MODE=BANDLIMITED|FAST
AP_ENABLE_LINUX_RUNTIME=ON|OFF
AP_ENABLE_FAST_MATH=ON|OFF
```

There are no compatibility aliases for removed stage-enable booleans or old build switches.
