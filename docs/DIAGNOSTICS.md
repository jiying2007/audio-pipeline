# Diagnostics, Dump and Replay

## Realtime contract

Diagnostics are designed so the 10 ms DSP worker never performs file I/O, heap allocation, JSON encoding or formatted logging. The worker only updates bounded counters, publishes fixed-size events and optionally writes into caller-owned Flight Recorder memory.

The event queue is deliberately lossy. `event_drop_events` reports notification loss. Flight Recorder triggering is independent of event delivery: an ERROR/FATAL condition can still freeze a dump even when the event ring is full.

## Runtime events

`ap_runtime_receive_event()` exposes fixed-size `ap_event_t` records covering runtime lifecycle, RT affinity/priority/bounded-memory-lock failures, queue pressure, output drops, DSP deadline misses, missing/underrun render reference, delay jumps, stream discontinuities, echo-path changes, AEC reset/convergence, ERLE collapse, pipeline failures, CPU migration observations and runtime quality transitions. Stepwise overload transitions keep their dedicated event kinds; a direct multi-level downward transition such as `FULL -> SAFE` emits `AP_EVENT_QUALITY_DEGRADED`, while upward transitions emit `AP_EVENT_QUALITY_RECOVERED`.

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

When microphone/render/output PCM are present, replay can perform bit-exact comparison against the matching processor build. A production dump should be replayed using the build fingerprint recorded in the `.apd`; a different binary is useful for A/B analysis but is not a deterministic reproduction claim.

## Repository-internal one-command triage

For current engineering and CI work, the repository contains an internal triage harness under `tests/diagnostics/`. It deliberately does **not** modify the released `tools/*` surface or APD v1 format, so the active v2.3.16 Product Qualification identity remains unchanged.

From a repository checkout:

```bash
python3 tests/diagnostics/aptriage.py failure.apd \
  --processor ./build/ap_process_pcm \
  --output-dir triage \
  --require-bit-exact \
  --stage-counterfactuals
```

The harness chains APD extraction, decoding of the stable 120-byte per-frame `ap_metrics_t` block, anomaly analysis and the released bit-exact replay path. It writes:

- `triage.json` and a human-readable `summary.md`;
- `analysis.json` with anomaly timeline and aggregate diagnostic state;
- `extracted/metrics.jsonl` and `extracted/metrics.csv`;
- replay output/logs;
- optional `bf-isolated`, `ns-isolated`, `vad-isolated` and `agc-isolated` counterfactual outputs where applicable.

The anomaly timeline reports metadata discontinuity/XRUN/codec-reopen observations, dump triggers, render-underrun/AEC-reset/delay-jump/reference-slip counter changes, quality transitions and AEC convergence loss. The summary also exposes maximum observed delay error and drift together with far-end, double-talk and AEC-convergence frame counts.

The isolated outputs are **counterfactual reprocessing** of recorded microphone input, not live intermediate PCM captured from the original integrated execution. They are useful for narrowing a fault to a stage family, but must not be described as proof of the exact internal signal that existed during the original failure.

## Repository-internal incident reasoning

`apdiagnose.py` adds a second, explicitly heuristic layer over `triage.json` or `analysis.json` without changing the captured evidence. It is useful when a dump contains multiple symptoms and an engineer needs a deterministic first-pass ordering before inspecting raw metrics.

```bash
python3 tests/diagnostics/apdiagnose.py triage/triage.json \
  --output-dir diagnosis
```

For a known-good capture that was triaged separately, the same command can compare the two diagnostic views:

```bash
python3 tests/diagnostics/apdiagnose.py bad/triage.json \
  --reference good/triage.json \
  --output-dir comparison
```

The reasoning layer writes `diagnosis.json` and `diagnosis.md`, plus `comparison.json` when a reference is supplied. Its machine-readable output includes:

- the first non-trigger anomaly (`first_fault`);
- temporally clustered anomaly intervals;
- anomaly-kind counts;
- ranked `root_cause_hypotheses` for sync/reference, AEC adaptation, capture I/O and runtime continuity families;
- recognized candidate event chains such as delay jump → reference slip → AEC convergence loss;
- good/bad summary deltas and newly introduced or resolved anomaly kinds.

The ranking score is a deterministic **heuristic evidence score**, not a probability. Candidate chains state only temporal association and set `causal_proof=false`; they must not be reported as proof of physical causation. These outputs are repository-internal diagnostic evidence only and are never HIL, Product Qualification, Product Certification or shipping authority.

`Diagnostic Triage` CI self-tests the reasoning layer with a synthetic fault sequence, then runs it against the real deterministic APD fixture produced by the repository. The resulting diagnosis artifacts are uploaded together with extraction, replay and triage evidence.

If the internal triage or reasoning functionality is later promoted into `tools/*` as part of the shipped SDK/source tool surface, that promotion is release-bearing and must advance SemVer through the normal release process.

## Current APD v1 boundary

APD v1 records build fingerprint, audio geometry, frame metadata, optional microphone/render/final-output PCM and optional `ap_metrics_t`. It does **not** store a complete effective `ap_config_t`/live `ap_tuning_t` snapshot, nor integrated per-stage PCM such as BF output, synchronized reference, AEC output/predicted echo, RES output, NS output or AGC output.

Adding those fields would be a diagnostic-format/API evolution and must use an explicit backward-compatible versioning and bounded-memory design. Do not infer live intermediate stage samples from isolated counterfactual replays.

## Recommended product triggers

Keep automatic capture selective. Useful triggers include repeated DSP deadline misses, downgrade to SAFE, explicit XRUN/discontinuity, severe AEC/ERLE failure and product-known route/path faults. Routine INFO/WARN conditions normally remain counters/events rather than persistent audio captures.
