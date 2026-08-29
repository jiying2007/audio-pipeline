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

Current hosted GCC resource gates demonstrate physical pruning:

```text
Pipeline full   78,096 B
Pipeline LOW    46,928 B
Pipeline TINY   25,408 B
Pipeline RAW     1,064 B
Runtime full    32,632 B
Runtime TINY     5,080 B
```

These numbers prove pruning for the current hosted compiler/ABI only; exact size functions remain authoritative for a product build.

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
- Activity/DTD uses attack/release energy smoothing, far-end hysteresis and double-talk hysteresis/hangover while keeping the same low-cost module contract.
- AEC adapts quickly during acquisition/path recovery and automatically reduces adaptation cadence after a stable far-end-only window; double talk/reference loss returns it to the configured fast cadence.
- SYNC keeps integer delay correction but consumes the fractional drift residue with linear reference interpolation, reducing discrete sample-jump artifacts.
- Delay search compares squared normalized correlation and avoids per-candidate `sqrtf` calls.
- ERLE is valid only during AEC far-end-only/non-double-talk observations; convergence state is exposed explicitly.
- Large correlation/timestamp path jumps reset stale AEC convergence state.

The default boundary resampler uses small fixed FIR filters for supported downsampling ratios to reduce aliasing. `FAST` retains the previous lightweight interpolation/decimation behavior as an explicit product choice. The API reports resampler filter delay and high-level algorithmic latency includes that delay.

## Validation-grade self-validation

`validation/` is the formal acoustic evidence layer between unit tests and real target-board certification. It intentionally separates trust levels:

- `regression`: deterministic generated fixtures used by PR/main and Nightly CI; never presented as validation-grade evidence.
- `validation-grade`: pinned public real data plus locally sealed public-derived simulation. The current source lock pins Microsoft AEC Challenge, Microsoft DNS Challenge and OpenSLR SLR28 metadata without storing third-party corpora in Git.
- `validation-grade-blind`: the same sealed corpus HMAC-partitioned with a repository-external holdout key; release reports may suppress per-case blind metrics.
- `product-certified`: real shipping hardware/audio route plus performance, thermal, power and soak evidence under `certification/`.

The validation runner emits SI-SDR, SI-SDR improvement, AEC render-correlation reduction, ERLE and VAD F1 where references exist. Every report binds the exact dataset lock, corpus manifest, policy and source revision by SHA-256 and emits an evidence manifest.

```bash
python3 validation/tools/build_validation_corpus.py --output /tmp/ap-validation --seed 1307
cmake -S . -B build-validation -DCMAKE_BUILD_TYPE=Release -DAP_BUILD_BENCH=OFF
cmake --build build-validation --target ap_process_pcm --parallel
python3 validation/tools/run_validation.py \
  --corpus /tmp/ap-validation/corpus.json \
  --policy validation/policies/validation-smoke.json \
  --dataset-lock validation/datasets.lock.json \
  --processor build-validation/ap_process_pcm \
  --output /tmp/ap-validation/report.json --enforce
```

Large public corpora remain outside the repository. `Validation Grade` runs only on a self-hosted `audio-validation` runner after dataset revision/checksum/seal verification. See `validation/README.md`.

## Hardware timestamps, discontinuities and route changes

Products with trustworthy capture/playback hardware timestamps can seed SYNC using:

```c
ap_pipeline_observe_io_timestamps(...);
```

Both timestamps must describe corresponding positions in the same monotonic clock domain. Product-known route/path changes call `ap_pipeline_notify_echo_path_change()`.

For Linux runtime integration, `ap_runtime_submit_ex()` carries versioned frame metadata including stream sequence, capture/render timestamps, XRUN/discontinuity/clock-reset/codec-reopen flags and lost-frame counts. `ap_runtime_command()` queues echo-path changes, stream discontinuities, reset, quality and tuning controls. Commands are applied by the DSP worker only at frame boundaries, preserving single-owner access to the live pipeline.

## Linux runtime ownership and overload behavior

The synchronous API is caller-serialized. After a pipeline is handed to `audio_pipeline_runtime` and the worker is running, the worker owns pipeline access. Per-frame `ap_metrics_t` snapshots are returned through the SPSC output queue; control-plane metrics read runtime-owned atomics only. ThreadSanitizer CI enforces this ownership model.

Output backpressure never skips DSP processing. If the output queue is full, that output snapshot is dropped and counted while AEC/SYNC/NS/AGC/VAD state still advances. This preserves the 10 ms DSP timeline independently of consumer speed.

Runtime overload state is distinct from product resource class:

`FULL -> LITE -> SAFE` under sustained deadline pressure, with deterministic recovery.

`ap_runtime_get_metrics_v2()` exposes long-running 64-bit counters, queue high-water marks, capture/render gaps, discontinuities, timestamp observations, RT scheduler setup failures, actual scheduler/CPU state and fixed-histogram DSP p50/p95/p99 estimates.

## Diagnostics, dump and replay

`audio_pipeline/audio_diag.h` provides a bounded diagnostics plane. The realtime worker never performs file I/O, heap allocation, JSON encoding or formatted logging.

- Fixed-size events cover lifecycle, RT setup failures, queue pressure, deadline misses, reference/sync/AEC faults and quality transitions.
- Event delivery is intentionally lossy and separately counted; a full event ring cannot suppress a Flight Recorder trigger.
- The optional caller-owned Flight Recorder stores configurable pre-roll/post-roll mic/render/output/metrics in memory and freezes on selected severity/events.
- Exported `.apd` dumps include the exact build fingerprint.
- PC tools inspect/extract/replay dumps:

```bash
python3 tools/apdump.py info failure.apd
python3 tools/apdump.py extract failure.apd --out-dir extracted
python3 tools/apreplay.py failure.apd --processor ./build/ap_process_pcm --work-dir replay
```

Audio dumps may contain private speech. Retention, access control, upload consent and secure deletion are product responsibilities; the SDK never uploads data. See `docs/DIAGNOSTICS.md`.

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

Installation exports CMake and pkg-config metadata. Runtime packages install `audio_runtime.h` and its diagnostics dependency `audio_diag.h` together.

```cmake
find_package(AudioPipeline CONFIG REQUIRED)
target_link_libraries(app PRIVATE AudioPipeline::core)
# Optional Linux runtime:
target_link_libraries(app PRIVATE AudioPipeline::runtime)
```

CI installs the SDK into a clean prefix and builds/runs separate consumers, so packaging is exercised rather than only checking source-tree builds.

## Acoustic evaluation

`eval/run_eval.py` supports 1- or 2-mic cases, capture-only or full-duplex input, optional clean near-end reference and case-level thresholds for SI-SDR, RMS and input/output render correlation. `--enforce-thresholds` converts a case into an executable acoustic gate. Private product corpora remain outside the repository.

## Test intelligence and HIL automation

PR verification now uses a mandatory Fast Gate before expensive matrices expand. `scripts/ci_impact.py` conservatively selects affected composition/Arm/backend/performance domains; unknown/public/build/test-infrastructure changes expand to FULL, and every `main` push always runs full verification. Heavy ARM/QEMU/ALSA/static-analysis jobs use the reviewed GHCR toolchain image by immutable digest and share only `ccache` compiler objects, never test results or certification evidence.

Nightly adds explicit flaky detection and revision-bound historical trend analysis. Acoustic validation failures preserve a self-contained reproducer artifact. Metamorphic/property contracts cover deterministic reset/replay, silence stability and topology invariants.

Real-board HIL remains evidence-separated from hosted/QEMU CI. Trusted `[self-hosted, linux, audio-target]` runners use board-local metadata/preflight/cleanup and tiered 10 min / 1 h / 8 h / 24 h / 72 h soak. Scheduled and post-release HIL are disabled until repository variable `HIL_ENABLED=true`; untrusted public PR code is never automatically executed on product hardware. See `docs/TESTING.md` and `hil/README.md`.

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
- dump generation -> parse/extract -> deterministic replay contracts;
- acoustic evaluation self-tests/threshold contracts and strict SKU certification validation;
- release packaging and checksums from the project version on `main`.

Hosted x86 percentages are regression signals only. Shipping claims require the actual SoC/kernel/compiler/DVFS/audio route and acoustic corpus.

## Target certification

`product-certified` records must include target performance evidence, acoustic corpus revision/results, nominal XRUN/overrun/drop results, artifacts/checksums and a passing >=8 h soak. The semantic validator additionally enforces the initial product gates such as p95 <7 ms and p99 <10 ms.

See:

- `docs/PLATFORM_SUPPORT.md`
- `docs/PERFORMANCE.md`
- `docs/DIAGNOSTICS.md`
- `certification/record.schema.json`
- `certification/validate_record.py`
- `eval/README.md`

No repository CI result is presented as Cortex-A7/A32 board performance.

## Documentation

- `docs/API_CONTRACT.md` — public lifecycle, state, composition and threading contracts
- `docs/ARCHITECTURE.md` — ownership and dependency direction
- `docs/DSP_DESIGN.md` — algorithm details
- `docs/PERFORMANCE.md` — regression and product certification gates
- `docs/DIAGNOSTICS.md` — event, Flight Recorder, dump and replay contract
- `docs/PORTING.md` — BSP/ALSA/toolchain integration
- `docs/TUNING.md` — acoustic/product tuning rules
- `docs/TESTING.md` — Fast/Full CI, impact routing, cache, failure, flaky/trend and HIL policy
- `docs/DEVELOPMENT.md` — contribution and hard-cut rules
- `THIRD_PARTY.md` — clean-room/reference policy

## License

See [LICENSE](LICENSE).
