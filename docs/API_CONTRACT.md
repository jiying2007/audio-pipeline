# Public API Contract

## Compatibility baseline

The 1.x ABI baseline established by 1.0.0 remains in force. Version 1.1.0 is additive: existing `ap_config_t`, `ap_metrics_t`, `ap_runtime_config_t`, `ap_runtime_metrics_t` and existing module/public lifecycle layouts are not changed.

New extensible control/diagnostic structures use `struct_size`, `api_version` and reserved fields. Callers must initialize those fields with the corresponding `*_API_VERSION` constant.

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

The generated installed `audio_pipeline_build.h` is the macro capability source of truth. `ap_build_info()` exposes the corresponding runtime-readable immutable fingerprint including semantic version, module mask, AEC/NS/SIMD/resampler backend names, fast-math state, pipeline/runtime presence and compiled geometry.

A module omitted from the build has no standalone implementation TU or embedded pipeline state.

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

Linux runtime uses `AP_RUNTIME_STATE_ALIGNMENT`, `AP_RUNTIME_STATE_MAX_BYTES` and exact runtime size APIs. Flight Recorder storage is separate caller-owned memory sized by `ap_flight_recorder_state_size()` and therefore does not inflate runtime resident state unless a product explicitly provisions diagnostics audio history.

Current hosted state-size measurements are generated from the resource-gate result into the single machine-readable source [`ci/resource-baseline.json`](../ci/resource-baseline.json) and human view [`docs/generated/RESOURCE_BASELINE.md`](generated/RESOURCE_BASELINE.md). Numeric hosted measurements are intentionally not duplicated in this API contract. They are verification values, not ABI constants or target-board RAM claims.

## Standalone module lifecycle

Stateful standalone modules follow:

```text
state_size -> aligned caller storage -> init -> process/reset/status as applicable
```

Resampler, HPF, BF, SYNC, Activity, AEC, RES, NS, AGC and VAD expose deterministic reset semantics when stateful. Wrappers reuse the same private implementation as the high-level pipeline.

Activity/DTD is independently available for applications that compose SYNC + Activity + AEC themselves. AEC standalone consumes already aligned microphone/reference frames plus explicit far-end/double-talk decisions.

## Resampler contract

`AP_RESAMPLER_MODE=BANDLIMITED|FAST` is compile-time.

- `BANDLIMITED` is the default and applies small fixed FIR filters to supported downsampling ratios;
- `FAST` preserves the lightweight interpolation/decimation path for explicitly accepted products;
- state preserves history across 10 ms frames;
- reset restores deterministic initial history;
- filter delay is exposed and included in high-level algorithmic latency.

## Timestamp, discontinuity and echo-path contract

`ap_pipeline_observe_io_timestamps()` is optional. Capture and render timestamps must describe corresponding hardware positions in the same monotonic clock domain. Invalid/non-positive or out-of-envelope delay observations return `AP_EINVAL`.

A sufficiently large timestamp/correlation delay jump is treated as a route jump and resets stale AEC convergence state through core.

`ap_pipeline_notify_echo_path_change()` is for product-known route/path replacement. `ap_pipeline_notify_stream_discontinuity()` is distinct: it represents capture/render gaps, clock reset, XRUN or codec reopen and clears time-dependent state deterministically.

When using the Linux runtime, applications must not call these mutating pipeline functions concurrently. Supply timestamp/discontinuity observations in `ap_frame_metadata_t` to `ap_runtime_submit_ex()`, or enqueue explicit controls through `ap_runtime_command()`.

## Runtime control ownership

After `ap_runtime_start()`, the worker is the sole owner of the supplied pipeline until stop/deinit.

When `ap_runtime_options_t.lock_memory` is enabled, the runtime performs best-effort bounded `mlock()`
on the caller-provided runtime and pipeline arenas only. It never calls process-global `mlockall()`;
the product remains responsible for worker-stack prefaulting and any process-wide realtime memory policy.

`ap_runtime_command()` is a bounded single-producer control queue. Commands are applied only at frame boundaries and currently support:

- echo-path change;
- stream discontinuity;
- pipeline reset;
- explicit overload quality;
- versioned tuning updates.

`AP_EFULL` on the control queue means the application must retry/coalesce according to product policy; the runtime never silently creates an unbounded command backlog.

## Output backpressure contract

Accepted capture frames advance DSP state even when the output consumer is late. If the output queue is full, runtime processes the frame into bounded scratch, increments `output_drop_events`, emits a best-effort event and discards only that output publication. AEC/SYNC/NS/AGC/VAD state and the processing timeline are not skipped.

Input queue overflow remains explicit `AP_EFULL`: a frame that was never accepted cannot be processed and should be represented by discontinuity/lost-frame metadata when appropriate.

## Telemetry semantics

`ap_metrics_t.erle_valid` is true only for valid AEC far-end-only, non-double-talk observations. `aec_convergence_frames` counts valid convergence observations in the current AEC epoch and `aec_converged` is the explicit heuristic state. Route/path/discontinuity reset starts a new relevant epoch.

AEC backend status exposes the active runtime adaptation stride. The configured fast stride may increase after a sustained stable far-end-only window and returns to the configured value when double talk/reference loss requires fast reacquisition.

`ap_runtime_get_metrics_v2()` adds long-running 64-bit counters built from lock-free-width atomics, queue high-water marks, discontinuity/gap/timestamp counters, RT setup failures, actual CPU/scheduler/priority and fixed-histogram DSP p50/p95/p99 estimates.

## Diagnostics contract

`ap_runtime_receive_event()` returns fixed-size versioned events from a small bounded ring. Event delivery is best-effort; `event_drop_events` is authoritative for loss. Persistent state must be read from metrics rather than inferred from complete event delivery.

Flight Recorder triggering is independent of event-ring capacity. If an event meets the configured recorder severity, recorder triggering occurs even if the notification event itself must be dropped.

The realtime worker never opens/writes files, formats JSON/log lines or allocates heap storage for diagnostics. See `docs/DIAGNOSTICS.md`.

## Threading

Synchronous pipeline/module APIs are caller-serialized and create no threads. Runtime producer/consumer/control interfaces follow their documented SPSC ownership assumptions. Complete `ap_metrics_t` output snapshots travel with output slots; control-plane metric APIs read runtime-owned atomics and do not inspect worker-mutated pipeline memory.

ThreadSanitizer CI validates this ownership model.

## Status semantics

| Status | Meaning |
|---|---|
| `AP_OK` | operation completed |
| `AP_EINVAL` | NULL, bad alignment, bad version/size, non-finite/out-of-range value, unsupported geometry or dependency violation |
| `AP_ENOMEM` | caller state buffer is too small |
| `AP_ESTATE` | feature not compiled or invalid lifecycle/state |
| `AP_EFULL` | bounded producer/control queue full |
| `AP_EEMPTY` | bounded consumer/event queue empty |

`AP_ENOMEM` is never a generic invalid-argument status.

## Configuration dimensions

Independent dimensions are:

- use case: CALL / ASSISTANT;
- runtime resource class: TINY / LOW / STANDARD;
- compiled module set;
- compiled SKU envelope;
- runtime stage subset;
- runtime overload quality: FULL / LITE / SAFE;
- optional diagnostics recording policy.

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

## v1.1.1 hardening notes

Flight Recorder defaults are metrics-only; audio PCM recording is explicit opt-in. `ap_runtime_attach_flight_recorder()` rejects sample-rate/frame/channel geometry that does not match the runtime. `ap_runtime_command()` rejects unknown kinds and invalid payloads before enqueue; a command accepted into the bounded queue may still emit `AP_EVENT_COMMAND_REJECTED` if a frame-boundary state-dependent tuning application is rejected.
