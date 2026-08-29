# Diagnostics, Dump and Replay

## Realtime contract

Diagnostics are designed so the 10 ms DSP worker never performs file I/O, heap allocation, JSON encoding or formatted logging. The worker only updates bounded counters, publishes fixed-size events and optionally writes into a caller-owned in-memory flight recorder.

The event queue is deliberately lossy. `event_drop_events` reports notification loss. Flight-recorder triggering is independent of event delivery: an ERROR/FATAL event can still freeze a dump even when the event ring is full.

## Runtime events

`ap_runtime_receive_event()` exposes fixed-size `ap_event_t` records. Current events cover runtime lifecycle, RT affinity/priority/mlock failures, queue pressure, output drops, DSP deadline misses, missing/underrun render reference, delay jumps, stream discontinuities, echo-path changes, AEC reset/convergence, ERLE collapse and runtime quality transitions. Stepwise overload transitions retain dedicated event kinds; a direct multi-level downgrade such as `FULL -> SAFE` emits `AP_EVENT_QUALITY_DEGRADED`, while upward transitions emit `AP_EVENT_QUALITY_RECOVERED`.

The runtime event ring is small by design; consumers should drain it from a non-realtime control thread. Persistent statistics belong in `ap_runtime_metrics_v2_t`, not in an unbounded log queue.

## Frame metadata and commands

`ap_runtime_submit_ex()` accepts versioned `ap_frame_metadata_t` with optional:

- stream sequence;
- capture/render hardware timestamps in one monotonic clock domain;
- capture/render discontinuity flags;
- XRUN, clock-reset and codec-reopen indications;
- lost capture/render frame counts.

`ap_runtime_command()` is a bounded control queue. Commands are consumed only by the DSP worker at frame boundaries, preserving single-owner access to the live pipeline. Supported controls are echo-path change, stream discontinuity, reset, explicit runtime quality and versioned tuning updates.

## Flight recorder

Create caller-owned state with:

```c
ap_flight_recorder_config_t cfg =
    ap_flight_recorder_config_default(sample_rate_hz, mic_channels);
size_t bytes = ap_flight_recorder_state_size(&cfg);
```

Allocate and align that memory outside the DSP path, initialize it with `ap_flight_recorder_init()` and attach it before `ap_runtime_start()` using `ap_runtime_attach_flight_recorder()`.

The recorder is a bounded circular buffer with configurable pre-roll and post-roll. The default policy records metrics only; microphone/render/output PCM require explicit opt-in. Recording masks independently select microphone PCM, render PCM, processed output and per-frame metrics. Trigger severity is configurable. Once post-roll completes the recorder freezes; a control thread can then query `ap_flight_recorder_export_size()` and export a versioned `.apd` blob with `ap_flight_recorder_export()`.

A dump contains the audio geometry, record mask, trigger event and the exact library build fingerprint, including project version, module mask and selected AEC/NS/SIMD/resampler backends.

Audio may contain private speech. Product integration must define retention, user-consent/access-control, upload and secure-erasure policy. The library itself never uploads a dump.

## PC-side inspection

```bash
python3 tools/apdump.py info failure.apd
python3 tools/apdump.py extract failure.apd --out-dir extracted
```

`extract` writes the recorded PCM streams and a JSON description for offline analysis.

## Deterministic replay

When the dump contains mic/render/output PCM, replay it through the matching build:

```bash
python3 tools/apreplay.py failure.apd \
  --processor ./build/ap_process_pcm \
  --work-dir replay
```

The tool reports byte/LSB differences and supports bit-exact comparison. Repository Audio Quality CI generates a deterministic dump, parses it, extracts it and replays it against the same build so the dump/replay path remains executable rather than documentation-only.

A production field dump should be replayed using the build fingerprint recorded in the `.apd`; replaying a different binary is useful for A/B analysis but is not a deterministic reproduction claim.

## Metrics

`ap_runtime_get_metrics_v2()` adds long-running 64-bit counters, queue high-water marks, discontinuity/gap counts, timestamp observations, RT setup failures, DSP last/max and fixed-histogram p50/p95/p99 estimates, actual CPU/scheduler/priority and runtime quality.

Percentiles are derived from fixed buckets. No sorting or dynamic allocation occurs in the 10 ms worker.

## Recommended product triggers

Keep automatic capture selective. Useful triggers include:

- repeated DSP deadline miss;
- quality downgrade to SAFE;
- explicit stream discontinuity/XRUN;
- severe AEC/ERLE failure;
- product-known route/path fault.

Routine INFO/WARN events should normally stay as counters/events and not create persistent audio dumps.
