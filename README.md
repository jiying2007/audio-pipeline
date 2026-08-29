# audio-pipeline

English | [简体中文](README.zh-CN.md)

`audio-pipeline` is a dependency-light, allocation-free real-time speech front end and composable DSP SDK for **low-compute Arm Linux products**. It targets ARMv7-A/Cortex-A7, Cortex-A32-class AArch32 and AArch64 products without embedding CPU-model assumptions into DSP algorithms.

Default high-level graph:

`S16 capture -> rate adapter -> HPF -> 2-mic BF -> SYNC -> Activity/DTD -> AEC -> RES -> NS -> AGC -> VAD -> mono S16`

The frame contract is fixed at 10 ms. Device I/O supports 8/16/24/32/48 kHz within the compiled product envelope; heavy DSP runs at 8 or 16 kHz. Persistent DSP/runtime state is caller-owned and bounded.

## v2 hard-cut API

Version 2.0.0 establishes a new major-version API/ABI baseline. Removed 1.x generational wrappers are not declared, exported or aliased.

The current runtime integration has one surface:

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

`ap_build_info()` likewise returns one complete `ap_build_info_t` containing version, composition, geometry, backend, source/compiler/target/build identity and configuration SHA-256.

See [`docs/API_CONTRACT.md`](docs/API_CONTRACT.md) for the normative public contract.

## Composition and product envelope

High-level composition uses `ap_config_t.stages`. Standalone module APIs are available through `audio_pipeline/audio_modules.h` for resampler, HPF, BF, SYNC, Activity/DTD, AEC, RES, NS, AGC and VAD.

Build-time composition:

```text
AP_BUILD_PIPELINE=ON|OFF
AP_MODULES=RESAMPLER,HPF,BF,SYNC,ACTIVITY,AEC,RES,NS,AGC,VAD
```

A module omitted from `AP_MODULES` loses its implementation TU and resident state; it is not merely bypassed.

Shipping SKUs can also cap physical geometry:

```text
AP_BUILD_MAX_IO_RATE_HZ
AP_BUILD_MAX_INTERNAL_RATE_HZ
AP_BUILD_MAX_MIC_CHANNELS
AP_BUILD_MAX_DELAY_MS
AP_BUILD_MAX_AEC_TAIL_MS
AP_RUNTIME_QUEUE_DEPTH
```

Representative presets include `composition-full`, `composition-low`, `composition-tiny`, `composition-voice-frontend`, `composition-raw`, AEC/NS/Activity-only and FAST-resampler variants.

Hosted resource measurements have one machine source of truth in [`ci/resource-baseline.json`](ci/resource-baseline.json); [`docs/generated/RESOURCE_BASELINE.md`](docs/generated/RESOURCE_BASELINE.md) is generated from it. Hosted measurements prove only the declared CI build contract, not target-board performance.

## DSP and realtime policy

- AEC: compile-time MDF default or NLMS alternative.
- NS: EMA default or MCRA alternative.
- SIMD: compile-time SCALAR or NEON.
- Resampler: BANDLIMITED default or explicit lower-cost FAST mode.
- Fast math: OFF by default.
- Linux runtime: bounded SPSC data queues, bounded control/event queues and one DSP worker owning the pipeline after start.
- Output backpressure drops publication only; accepted frames still advance DSP state.
- Frame metadata carries timestamps, discontinuities, XRUN/clock-reset/codec-reopen state and lost-frame counts.
- Runtime metrics include long-running counters, failed frames, queue pressure, scheduler state and DSP p50/p95/p99 telemetry.

Algorithm details live in [`docs/DSP_DESIGN.md`](docs/DSP_DESIGN.md); performance policy lives in [`docs/PERFORMANCE.md`](docs/PERFORMANCE.md).

## Diagnostics

`audio_pipeline/audio_diag.h` provides fixed-size events and an optional caller-owned Flight Recorder. The realtime worker does not perform file I/O, heap allocation, JSON encoding or formatted logging.

`.apd` dumps can be inspected and replayed with:

```bash
python3 tools/apdump.py info failure.apd
python3 tools/apdump.py extract failure.apd --out-dir extracted
python3 tools/apreplay.py failure.apd --processor ./build/ap_process_pcm --work-dir replay
```

Audio dumps may contain private speech; retention, access control and secure deletion are product responsibilities. See [`docs/DIAGNOSTICS.md`](docs/DIAGNOSTICS.md).

## Validation trust levels

`validation/` separates four evidence levels:

- `regression`: deterministic generated CI fixtures;
- `validation-grade`: pinned/sealed public data;
- `validation-grade-blind`: HMAC-partitioned repository-external holdout;
- `product-certified`: real shipping hardware/audio route plus performance, thermal, power, acoustic and soak evidence.

Pinned public sources include Microsoft AEC Challenge, Microsoft DNS Challenge and OpenSLR SLR28 metadata. Public corpora remain outside Git.

Large public validation runs only on a trusted `audio-validation` runner after readiness and dataset-seal verification. See [`validation/README.md`](validation/README.md) and [`docs/TRUSTED_RUNNERS.md`](docs/TRUSTED_RUNNERS.md).

## HIL and shipping certification

Real-board HIL uses trusted `[self-hosted, linux, audio-target]` runners with board-local metadata, readiness, preflight/cleanup and evidence sealing.

Tiers are 10 min / 1 h / 8 h / 24 h / 72 h. Scheduled and post-release HIL are **fail-visible**: if `HIL_ENABLED!=true`, the availability gate fails instead of silently skipping or manufacturing a PASS.

HIL engineering history does not equal product certification. A current `product-certified` record must use **certification schema v4** and bind:

- a shipping-approved SKU policy;
- exact source/build/toolchain identity;
- distinct `audio-builder` and `audio-target` runners;
- build/deployed/executed binary SHA-256 equality;
- real target CPU/RSS/p95/p99 and route evidence;
- real acoustic corpus results;
- measured thermal and power evidence;
- policy-duration route soak;
- artifact attestation;
- an immutable `product-lifecycle` archive receipt.

The checked-in Cortex-A32 LOW shipping policy requires at least **72 h**. No hosted CI, QEMU, public-data validation or shorter HIL tier can substitute for it.

See [`certification/README.md`](certification/README.md) and [`docs/PRODUCT_ASSURANCE.md`](docs/PRODUCT_ASSURANCE.md).

## Build and consume

Native Linux:

```bash
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build --parallel
ctest --test-dir build --output-on-failure
```

Cross-build presets include generic ARMv7-A, Cortex-A7 scalar/NEON, Cortex-A32 NEON and AArch64 NEON. Selected executable contracts also run under QEMU; QEMU timing is never treated as silicon timing.

Installed SDK:

```cmake
find_package(AudioPipeline CONFIG REQUIRED)
target_link_libraries(app PRIVATE AudioPipeline::core)
# Optional Linux runtime:
target_link_libraries(app PRIVATE AudioPipeline::runtime)
```

CMake and pkg-config consumers are built from a clean install prefix in CI.

## Repository gates

PR/main verification includes strict compile/tests, GCC/Clang, sanitizers, TSan, static analysis, coverage, backend/composition matrices, Arm cross-build/QEMU, resource/ROM pruning, paired performance comparisons, diagnostics replay, deterministic acoustic regression and v2 API/symbol contracts.

Every `main` push runs the complete verification graph. Release automation requires the exact main SHA to pass the required `summary` check before creating the release tag/assets/attestations.

Real public-data validation, HIL and product certification remain evidence-separated from hosted CI.

## Documentation

- [`docs/API_CONTRACT.md`](docs/API_CONTRACT.md) — v2 public lifecycle/state/threading contract
- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — ownership and dependency direction
- [`docs/DSP_DESIGN.md`](docs/DSP_DESIGN.md) — algorithms
- [`docs/PERFORMANCE.md`](docs/PERFORMANCE.md) — performance/resource gates
- [`docs/DIAGNOSTICS.md`](docs/DIAGNOSTICS.md) — event/dump/replay contract
- [`docs/PORTING.md`](docs/PORTING.md) — BSP/ALSA/toolchain integration
- [`docs/TESTING.md`](docs/TESTING.md) — CI/HIL policy
- [`docs/TRUSTED_RUNNERS.md`](docs/TRUSTED_RUNNERS.md) — self-hosted runner readiness
- [`certification/README.md`](certification/README.md) — v4 shipping certification
- [`THIRD_PARTY.md`](THIRD_PARTY.md) — third-party/reference policy

## License

See [LICENSE](LICENSE).
