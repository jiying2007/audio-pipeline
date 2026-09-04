# Public API Contract

## v2 boundary

`audio-pipeline` 2.x starts a new public C API/ABI baseline. Version 2.0.0 is an intentional hard cut: removed 1.x generational wrappers, version-suffixed runtime metric types and parallel build-info surfaces are not declared, exported or aliased.

The supported public surface is the installed headers under `include/audio_pipeline/`. Historical release notes describe older APIs only as history and are not compatibility promises.

New extensible control/diagnostic structures use `struct_size`, `api_version` and reserved fields. Callers initialize them with the current API version constant documented by the owning header.

## Frame and sample contract

High-level pipeline:

- fixed frame duration: **10 ms**;
- capture: 1 or 2 channel interleaved S16, within the compiled mic envelope;
- render reference: mono S16 corresponding to the signal actually sent toward the DAC;
- output: mono S16;
- I/O rates: 8/16/24/32/48 kHz, limited by `AP_BUILD_MAX_IO_RATE_HZ`;
- internal rates: 8 or 16 kHz, limited by `AP_BUILD_MAX_INTERNAL_RATE_HZ`.

Standalone float DSP modules use normalized float samples and the same 10 ms cadence. Resampler APIs accept only supported 10 ms input/output geometries. Partial buffer overlap is unsupported unless explicitly documented.

## Build capability and identity

Compile-time composition:

```text
AP_BUILD_PIPELINE=ON|OFF
AP_MODULES=RESAMPLER,HPF,BF,SYNC,ACTIVITY,AEC,RES,NS,AGC,VAD
```

The generated installed `audio_pipeline_build.h` is the compile-time capability source of truth. The single `ap_build_info()` API returns one complete immutable `ap_build_info_t` containing semantic version, module mask, geometry, selected AEC/NS/SIMD/resampler backends, fast-math state, the effective BF direction-tracking capability, source revision, compiler/target/build identity and configuration SHA-256. `AP_BUILD_BF_DIRECTION_TRACKING` and `ap_build_info_t.bf_direction_tracking` report the effective compiled capability rather than requiring a product to infer it from CMake arguments.

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
AP_ENABLE_BF_DIRECTION_TRACKING=ON|OFF
```

Configuration outside the compiled envelope returns `AP_EINVAL`. A smaller envelope can reduce AEC partitions, SYNC history, scratch geometry and runtime queue storage.

## Runtime pipeline composition

`ap_config_t.stages` selects a topology-safe subset of compiled DSP stages. Stage order is fixed; the mask does not define a DAG.

Validation rules include:

- unknown/uncompiled stage -> `AP_ESTATE`;
- BF requires two microphones;
- high-level AEC requires SYNC and Activity/DTD support;
- RES requires AEC;
- delay/drift policy requires SYNC;
- enabled floating configuration parameters must be finite and in range.

RESAMPLER and Activity are supporting modules rather than public `AP_STAGE_*` bits. RAW/resampler-only is valid with `stages == 0`.

## Caller-owned state

Synchronous DSP does not allocate persistent state.

```c
_Alignas(AP_PIPELINE_STATE_ALIGNMENT)
static unsigned char pipeline_mem[AP_PIPELINE_STATE_MAX_BYTES];
```

- pipeline alignment: 16 bytes;
- public pipeline hard ceiling: 80,000 bytes;
- `ap_pipeline_state_size()` returns the exact selected-graph requirement.

Standalone modules use `AP_MODULE_STATE_ALIGNMENT`, `AP_MODULE_STATE_MAX_BYTES` and exact module state-size functions.

Linux runtime uses `AP_RUNTIME_STATE_ALIGNMENT`, `AP_RUNTIME_STATE_MAX_BYTES` and exact runtime size APIs. Flight Recorder storage is separate caller-owned memory sized by `ap_flight_recorder_state_size()`.

Hosted state-size measurements live only in [`ci/resource-baseline.json`](../ci/resource-baseline.json) and its generated human view [`docs/generated/RESOURCE_BASELINE.md`](generated/RESOURCE_BASELINE.md). Those values are regression evidence, not target-board RAM claims.

## Standalone module lifecycle

Stateful standalone modules follow:

```text
state_size -> aligned caller storage -> init -> process/reset/status
```

Resampler, HPF, BF, SYNC, Activity, AEC, RES, NS, AGC and VAD expose deterministic reset semantics when stateful. Wrappers reuse the same private implementation as the high-level pipeline.

Activity/DTD is independently available for applications that compose SYNC + Activity + AEC themselves. Standalone AEC consumes aligned microphone/reference frames plus explicit far-end/double-talk decisions.

## Resampler contract

`AP_RESAMPLER_MODE=BANDLIMITED|FAST` is compile-time.

- `BANDLIMITED` is the default and applies fixed small FIR filters to supported downsampling ratios;
- `FAST` is the explicit lower-cost interpolation/decimation option;
- state preserves history across 10 ms frames;
- reset restores deterministic initial history;
- filter delay is exposed and included in high-level algorithmic latency.

Neither mode is a compatibility alias.

## Reference-alignment policy

Reference alignment is orthogonal to CALL/ASSISTANT use case and resource class. The default remains `AP_REFERENCE_ALIGNMENT_ADAPTIVE`, which keeps acoustic correlation delay tracking and correlation-based clock-drift compensation enabled when SYNC is present.

`AP_REFERENCE_ALIGNMENT_FIXED_GEOMETRY` is an explicit opt-in for products whose direct speaker/DAC-to-microphone/ADC geometry is stable. Apply it with `ap_config_apply_reference_alignment_policy()`. It sets the startup/fallback anchor delay and disables acoustic correlation delay chasing plus correlation-based drift compensation. It does **not** disable trusted hardware timestamp observation.

Fixed geometry is not a generic replacement for adaptive alignment and must not be inferred from robot/device motion alone. See [`docs/FIXED_GEOMETRY_REFERENCE.md`](FIXED_GEOMETRY_REFERENCE.md) for the evidence boundary and promotion gates.

## Timestamp, discontinuity and echo-path contract

`ap_pipeline_observe_io_timestamps()` is optional. Capture and render timestamps must describe corresponding hardware positions in the same monotonic clock domain. Invalid or out-of-envelope observations return `AP_EINVAL`.

Correlation-based delay updates are ambiguity-gated. Small delay/drift corrections require the winning peak to be separated from non-local competitors; a large correlation route-change candidate must remain consistent for three search epochs before it is committed and stale AEC convergence is reset. Trusted hardware timestamps and explicit application path-change notifications remain authoritative and are not delayed by the correlation confirmation policy.

This authority is unchanged under `AP_REFERENCE_ALIGNMENT_FIXED_GEOMETRY`: a valid hardware timestamp observation may update the active reference delay even though acoustic tracking and correlation-based drift compensation are disabled. The configured fixed delay is therefore a stable startup/fallback causal anchor rather than a ban on trusted calibration.

`ap_pipeline_notify_echo_path_change()` represents product-known route/path replacement. `ap_pipeline_notify_stream_discontinuity()` represents capture/render gaps, clock reset, XRUN or codec reopen and clears time-dependent state deterministically.

With the Linux runtime, applications must not mutate the owned pipeline concurrently. Supply per-frame timestamps/discontinuities through `ap_frame_metadata_t` to `ap_runtime_submit_frame()`, or enqueue explicit controls through `ap_runtime_command()`.

## Linux runtime lifecycle

The v2 runtime has one lifecycle and one metric surface:

```c
ap_runtime_config_t cfg = ap_runtime_config_default();
ap_runtime_options_t opts = ap_runtime_options_default();

ap_runtime_open(memory, memory_size, pipeline, &cfg, &opts, &runtime);
ap_runtime_start(runtime);
ap_runtime_submit_frame(runtime, mic, render_or_null, metadata_or_null);
ap_runtime_receive(runtime, output, metrics_or_null);
ap_runtime_read_metrics(runtime, &runtime_metrics);
ap_runtime_stop(runtime);
ap_runtime_deinit(runtime);
```

`ap_runtime_open()` validates caller-owned state, basic scheduling/overload policy and extensible runtime options. `ap_runtime_submit_frame()` is the only frame producer API and always accepts optional metadata. `ap_runtime_read_metrics()` returns the complete long-running runtime metric structure.

After `ap_runtime_start()`, the worker is the sole owner of the supplied pipeline until stop/deinit. If `ap_runtime_options_t.lock_memory` is enabled, the runtime performs best-effort bounded `mlock()` only on the caller-owned runtime and pipeline arenas and releases those locks on stop. The SDK never invokes process-global `mlockall()`; worker-stack prefaulting and process-wide realtime memory policy remain product responsibilities.

## Runtime control ownership

`ap_runtime_command()` is a bounded single-producer control queue. Commands are applied only at frame boundaries and support:

- echo-path change;
- stream discontinuity;
- pipeline reset;
- explicit overload quality;
- tuning updates.

`AP_EFULL` means the application must retry or coalesce according to product policy. The runtime never creates an unbounded control backlog.

## Output backpressure contract

Accepted capture frames advance DSP state even when the output consumer is late. If the output queue is full, runtime still processes the frame into bounded scratch, increments `output_drop_events`, emits a best-effort event and discards only output publication. AEC/SYNC/NS/AGC/VAD state and timeline continue to advance.

Input queue overflow remains explicit `AP_EFULL`: a frame that was never accepted cannot be processed and should be represented by discontinuity/lost-frame metadata when appropriate.

## Telemetry semantics

`ap_metrics_t.erle_valid` is true only for valid AEC far-end-only, non-double-talk observations. `aec_convergence_frames` and `aec_converged` describe the current convergence epoch. Route/path/discontinuity reset begins a new epoch.

AEC status exposes the active runtime adaptation stride. Stable far-end-only operation may increase stride; double talk/reference loss restores the configured fast cadence.

`ap_runtime_metrics_t` contains long-running 64-bit counters, failed-frame and pipeline-error state, queue high-water marks, discontinuity/gap/timestamp counters, RT setup failures, render/capture failures, sampled CPU migration, critical-event count, actual scheduler state and fixed-histogram DSP p50/p95/p99 estimates.

## Diagnostics contract

`ap_runtime_receive_event()` returns fixed-size events from a small bounded ring. Delivery is best-effort; `event_drop_events` is authoritative for notification loss. Persistent state belongs in `ap_runtime_metrics_t`.

Flight Recorder triggering is independent of event-ring capacity. An eligible event can freeze the recorder even if event publication itself is dropped.

The realtime worker never opens/writes files, formats JSON/log lines or allocates heap storage for diagnostics. See `docs/DIAGNOSTICS.md`.

## Threading

Synchronous pipeline/module APIs are caller-serialized and create no threads. Runtime producer, consumer and control paths follow their documented SPSC ownership assumptions. Complete per-frame `ap_metrics_t` snapshots travel with output slots; control-plane runtime metrics use runtime-owned atomics and do not inspect worker-mutated pipeline memory.

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
- reference alignment: ADAPTIVE / FIXED_GEOMETRY;
- compiled module set;
- compiled SKU envelope;
- runtime stage subset;
- runtime overload quality: FULL / LITE / SAFE;
- optional diagnostics policy.

CPU model does not imply any one resource class.

## Compile-time backend contract

```text
AP_AEC_BACKEND=MDF|NLMS
AP_NS_ESTIMATOR=EMA|MCRA
AP_SIMD_BACKEND=SCALAR|NEON
AP_RESAMPLER_MODE=BANDLIMITED|FAST
AP_ENABLE_LINUX_RUNTIME=ON|OFF
AP_ENABLE_FAST_MATH=ON|OFF
AP_ENABLE_BF_DIRECTION_TRACKING=ON|OFF
```

Removed v1 API generations and removed build/stage switches have no v2 compatibility aliases.
