# Diagnostics, Dump and Replay

## Realtime contract

Diagnostics are designed so the 10 ms DSP worker never performs file I/O, heap allocation, JSON encoding or formatted logging. The worker only updates bounded counters, publishes fixed-size events and optionally writes into caller-owned Flight Recorder memory.

The event queue is deliberately lossy. `event_drop_events` reports notification loss. Flight Recorder triggering is independent of event delivery: an ERROR/FATAL condition can still freeze a dump even when the event ring is full.

## Runtime events

`ap_runtime_receive_event()` exposes fixed-size `ap_event_t` records covering runtime lifecycle, RT affinity/priority/mlock failures, queue pressure, output drops, DSP deadline misses, missing/underrun render reference, delay jumps, stream discontinuities, echo-path changes, AEC reset/convergence, ERLE collapse, pipeline failures, CPU migration observations and runtime quality transitions.

Consumers should drain the bounded event ring from a non-realtime control thread. Persistent statistics belong in `ap_runtime_metrics_t`, read through `ap_runtime_read_metrics()`, not in an unbounded log queue.

## Frame metadata and commands

`ap_runtime_submit_frame()` accepts optional `ap_frame_metadata_t` with:

- stream sequence;
- capture/render hardware timestamps in one monotonic clock domain;
- capture/render discontinuity flags;
- XRUN, clock-reset and codec-reopen indications;
- lost capture/render frame counts.

`ap_runtime_command()` is a bounded control queue. Commands are consumed only by the DSP worker at frame boundaries, preserving single-owner access to the live pipeline. Supported controls are echo-path change, stream discontinuity, reset, explicit runtime quality and tuning updates.

All extensible structures use `struct_size`, `api_version` and reserved fields with the current v2 API constants. Removed 1.x runtime entry points are not aliases and are not accepted by the v2 SDK.

## Runtime metrics

`ap_runtime_read_metrics()` fills the single current `ap_runtime_metrics_t` surface. It includes:

- submitted/processed/failed frames;
- input-full/output-drop/DSP-overrun counters;
- command/event drops;
- capture/render gaps, discontinuities and timestamp observations;
- scheduler bind/mlock failures;
- render-push/capture-process failures;
- observed CPU changes and critical-event count;
- queue high-water marks;
- DSP last/max and fixed-histogram p50/p95/p99 estimates;
- actual CPU/scheduler/priority;
- last pipeline error and current quality.

Counters that must remain reliable on AArch32 are implemented without requiring lock-free 64-bit atomics. Percentiles are derived from fixed buckets; no sorting or dynamic allocation occurs in the worker.

## Flight Recorder

Create caller-owned state with:

```c
ap_flight_recorder_config_t cfg =
    ap_flight_recorder_config_default(sample_rate_hz, mic_channels);
size_t bytes = ap_flight_recorder_state_size(&cfg);
```

Allocate and align that memory outside the DSP path, initialize it with `ap_flight_recorder_init()` and attach it before `ap_runtime_start()` using `ap_runtime_attach_flight_recorder()`.

The recorder is a bounded circular buffer with configurable pre-roll and post-roll. The default policy records metrics only; microphone/render/output PCM require explicit opt-in. Recording masks independently select microphone PCM, render PCM, processed output and per-frame metrics. Once post-roll completes the recorder freezes; a control thread can query `ap_flight_recorder_export_size()` and export a versioned `.apd` blob with `ap_flight_recorder_export()`.

A dump contains audio geometry, record mask, trigger event and the exact library build fingerprint. Audio may contain private speech. Retention, consent, access control, upload and secure-erasure policy are product responsibilities; the SDK itself never uploads a dump.

## PC-side inspection and replay

```bash
python3 tools/apdump.py info failure.apd
python3 tools/apdump.py extract failure.apd --out-dir extracted
python3 tools/apreplay.py failure.apd \
  --processor ./build/ap_process_pcm \
  --work-dir replay
```

When mic/render/output PCM are present, replay can perform bit-exact comparison against the matching processor build. Repository Audio Quality CI generates, parses, extracts and replays deterministic dumps so this field-debug path remains executable rather than documentation-only.

A production dump should be replayed using the build fingerprint recorded in the `.apd`; a different binary is useful for A/B analysis but is not a deterministic reproduction claim.

## Recommended product triggers

Keep automatic capture selective. Useful triggers include repeated DSP deadline misses, downgrade to SAFE, explicit XRUN/discontinuity, severe AEC/ERLE failure and product-known route/path faults. Routine INFO/WARN conditions normally remain counters/events rather than persistent audio captures.
