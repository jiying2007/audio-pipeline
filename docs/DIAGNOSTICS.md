# Diagnostics, Dump and Replay

## Realtime contract

Diagnostics are designed so the 10 ms DSP worker never performs file I/O, heap allocation, JSON encoding or formatted logging. The worker only updates bounded counters, publishes fixed-size events and optionally writes into caller-owned Flight Recorder memory.

The event queue is deliberately lossy. `event_drop_events` reports notification loss. Flight Recorder triggering is independent of event delivery: an ERROR/FATAL condition can still freeze a dump even when the event ring is full.

## Runtime events

`ap_runtime_receive_event()` exposes fixed-size `ap_event_t` records covering runtime lifecycle, RT affinity/priority/bounded-memory-lock failures, queue pressure, output drops, DSP deadline misses, missing/underrun render reference, delay jumps, stream discontinuities, echo-path changes, AEC reset/convergence, ERLE collapse, pipeline failures, CPU migration observations and runtime quality transitions. Stepwise overload transitions keep their dedicated event kinds; a direct multi-level downward transition such as `FULL -> SAFE` emits `AP_EVENT_QUALITY_DEGRADED`, while upward transitions emit `AP_EVENT_QUALITY_RECOVERED`.

Consumers should drain the bounded event ring from a non-realtime control thread. Persistent statistics belong in `ap_runtime_metrics_t`, read through `ap_runtime_read_metrics()`, not in an unbounded log queue.

## Frame metadata and commands

`ap_runtime_submit_frame()` accepts optional `ap_frame_metadata_t` with stream sequence, capture/render hardware timestamps in one monotonic clock domain, discontinuity flags, XRUN/clock-reset/codec-reopen indications, and lost capture/render frame counts.

`ap_runtime_command()` is a bounded control queue. Commands are consumed only by the DSP worker at frame boundaries, preserving single-owner access to the live pipeline. Supported controls include echo-path change, stream discontinuity, reset, explicit runtime quality and tuning updates.

All extensible structures use `struct_size`, `api_version` and reserved fields with the current v2 API constants. Removed 1.x runtime entry points are not aliases and are not accepted by the v2 SDK.

## Runtime metrics

`ap_runtime_read_metrics()` fills the single current `ap_runtime_metrics_t` surface. It includes submitted/processed/failed frames, queue/output/DSP counters, command/event drops, capture/render gaps and discontinuities, scheduler failures, runtime processing failures, observed CPU changes, critical-event count, queue high-water marks, DSP timing estimates, actual CPU/scheduler/priority, last pipeline error and current quality.

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

A dump contains audio geometry, record mask, trigger event and the library build fingerprint subset represented by APD v1. Audio may contain private speech. Retention, consent, access control, upload and secure-erasure policy are product responsibilities; the SDK itself never uploads a dump.

## Released PC-side inspection and replay

The v2.3.16 released tools remain the stable APD v1 inspection/replay surface:

```bash
python3 tools/apdump.py info failure.apd
python3 tools/apdump.py extract failure.apd --output-dir extracted
python3 tools/apreplay.py failure.apd \
  --processor ./build/ap_process_pcm \
  --output-pcm replay.pcm \
  --require-bit-exact
```

When microphone/render/output PCM are present, replay can compare against the matching processor build. A different binary is useful for A/B analysis but is not a deterministic reproduction claim.

## Repository-internal terminal triage

The repository-internal harness lives under `tests/diagnostics/`; it does not modify the released `tools/*` surface or APD v1, so the immutable v2.3.16 Product Qualification identity remains unchanged.

Every normal triage invocation requires processor build information from the exact linked build:

```bash
./build/ap_build_identity_probe > processor-build-info.json
python3 tests/diagnostics/aptriage.py failure.apd \
  --processor ./build/ap_process_pcm \
  --processor-build-info processor-build-info.json \
  --output-dir triage \
  --require-bit-exact \
  --stage-counterfactuals
```

The repository CI builds `tests/diagnostics/build_identity_probe.c` against the same processor library. The six fields shared by APD v1 and `ap_build_info()` are always compared and a mismatch always makes triage fail closed. There is no `NOT_CHECKED` state and no opt-in match flag.

The harness writes:

- `triage.json` and `summary.md`;
- `analysis.json` as an internal component of the triage artifact;
- extracted metrics JSONL/CSV;
- replay output/logs;
- optional isolated counterfactual outputs.

`analysis.json` is not a standalone diagnosis input. `apdiagnose.py` consumes the complete `triage.json` so APD header/recording-trigger context is retained.

The isolated outputs are counterfactual reprocessing of recorded microphone input, not live intermediate PCM captured from the original integrated execution. They can narrow a fault family but cannot prove the exact internal signal present during the original failure.

## Repository-internal incident reasoning

`apdiagnose.py` is an explicitly heuristic layer over a complete `triage.json`:

```bash
python3 tests/diagnostics/apdiagnose.py triage/triage.json \
  --output-dir diagnosis
```

Reference comparison likewise uses a separately produced complete triage artifact:

```bash
python3 tests/diagnostics/apdiagnose.py bad/triage.json \
  --reference good/triage.json \
  --output-dir comparison
```

The reasoning output includes recording trigger context, deterministic first non-trigger anomaly, temporal intervals, anomaly counts, ranked hypotheses, temporal candidate chains and normalized reference comparison. Heuristic scores are evidence ranks rather than probabilities; candidate chains are temporal associations only and all outputs preserve `causal_proof=false`.

## Repository-internal cross-dump bundle

Cross-dump aggregation requires a source root and at least two triage/diagnosis pairs:

```bash
python3 tests/diagnostics/apincident.py \
  --source-root fault-injection \
  --entry capture-gap fault-injection/capture-gap/triage/triage.json fault-injection/capture-gap/diagnosis/diagnosis.json \
  --entry codec-reopen fault-injection/codec-reopen/triage/triage.json fault-injection/codec-reopen/diagnosis/diagnosis.json \
  --output-dir fault-injection/incident-bundle
```

Every source must resolve beneath `--source-root` before reading. Each source is represented only by SHA256, byte size and root-relative path under `source_evidence`; runner-local legacy path fields are not emitted. Missing source binding or root-relative identity fails closed.

The bundle can report repeated diagnostic domains and exact patterns, but caller-selected recurrence does not prove same device, same session, chronological capture order, authoritative capture time, or a shared physical root cause.

## Current APD v1 boundary

APD v1 records build fingerprint subset, audio geometry, frame metadata, optional microphone/render/final-output PCM and optional `ap_metrics_t`. It does **not** store a complete effective `ap_config_t`/live `ap_tuning_t` snapshot, exact source/config identity, or integrated per-stage PCM such as BF output, synchronized reference, AEC output/predicted echo, RES output, NS output or AGC output.

Adding such fields would be a diagnostic-format/API evolution and requires explicit versioning and bounded-memory design. Do not infer live intermediate stage samples or exact source/config identity from repository-internal counterfactual/replay evidence.

## Recommended product triggers

Keep automatic capture selective. Useful triggers include repeated DSP deadline misses, downgrade to SAFE, explicit XRUN/discontinuity, severe AEC/ERLE failure and product-known route/path faults. Routine INFO/WARN conditions normally remain counters/events rather than persistent audio captures.
