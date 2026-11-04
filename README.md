# audio-pipeline

English | [简体中文](README.zh-CN.md)

`audio-pipeline` is a dependency-light, allocation-free real-time speech front end and composable DSP SDK for **low-compute Arm Linux research targets**. It targets ARMv7-A/Cortex-A7, Cortex-A32-class AArch32 and AArch64 systems without embedding CPU-model assumptions into DSP algorithms.

> **Technical research only.** This repository advances reproducible DSP/audio-front-end algorithms, multi-microphone experiments, acoustic measurement, ARM/SSC305-class resource characterization and bounded embedded runtimes. Research requires source/rights checks and independent measured results—not commercial approval, Shipping SKU status, GitHub Release publication or a mandatory 72-hour certificate. Automatic Release and Product Certification Actions have been retired; remaining legacy names are historical or being migrated under [issue #882](https://github.com/jiying2007/audio-pipeline/issues/882). See [research execution boundary](docs/RESEARCH_ONLY_EXECUTION.md). Historical scientific evidence and actual upstream license restrictions remain intact.

Default high-level graph:

`S16 capture -> rate adapter -> HPF -> 2-mic BF -> SYNC -> Activity/DTD -> AEC -> RES -> NS -> AGC -> VAD -> mono S16`

The frame contract is fixed at 10 ms. Device I/O supports 8/16/24/32/48 kHz within the selected bounded build profile; heavy DSP runs at 8 or 16 kHz. Persistent DSP/runtime state is caller-owned and bounded.

## Public API and runtime

The current 2.x line has one public C API/ABI surface. Incompatible public symbol or structure changes require the next major version; the current line does not carry parallel compatibility aliases.

The runtime integration has one surface:

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

## Composition and bounded target profiles

High-level composition uses `ap_config_t.stages`. Standalone module APIs are available through `audio_pipeline/audio_modules.h` for resampler, HPF, BF, SYNC, Activity/DTD, AEC, RES, NS, AGC and VAD.

Build-time composition:

```text
AP_BUILD_PIPELINE=ON|OFF
AP_MODULES=RESAMPLER,HPF,BF,SYNC,ACTIVITY,AEC,RES,NS,AGC,VAD
AP_ENABLE_BF_DIRECTION_TRACKING=ON|OFF
```

A module omitted from `AP_MODULES` loses its implementation TU and resident state; it is not merely bypassed.

Reproducible target-build profiles can bound physical geometry:

```text
AP_BUILD_MAX_IO_RATE_HZ
AP_BUILD_MAX_INTERNAL_RATE_HZ
AP_BUILD_MAX_MIC_CHANNELS
AP_BUILD_MAX_DELAY_MS
AP_BUILD_MAX_AEC_TAIL_MS
AP_RUNTIME_QUEUE_DEPTH
```

Representative presets include `composition-full`, `composition-low`, `composition-tiny`, `composition-voice-frontend`, `composition-raw`, AEC/NS/Activity-only and FAST-resampler variants. The named `ssc305-cortex-a32-low` research target preset is also exercised by an independent required resource gate that configures/builds the exact preset, verifies its generated build identity, installs the SDK, and executes AArch32 build-info/core/runtime consumers under QEMU. This is source/build integration evidence, not measured silicon performance.

Hosted resource measurements have one machine source of truth in [`ci/resource-baseline.json`](ci/resource-baseline.json); [`docs/generated/RESOURCE_BASELINE.md`](docs/generated/RESOURCE_BASELINE.md) is generated from it. Hosted measurements prove only the declared CI build contract, not target-board performance.

## DSP and realtime policy

- AEC: compile-time MDF default or NLMS alternative.
- NS: EMA default or MCRA alternative.
- SIMD: compile-time SCALAR or NEON.
- Resampler: BANDLIMITED default or explicit lower-cost FAST mode.
- Fast math: OFF by default.
- BF direction tracking: explicit compile-time capability; the conservative `ssc305-cortex-a32-low` preset disables it and exports the effective state in build info.
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
python3 tools/apdump.py extract failure.apd --output-dir extracted
python3 tools/apreplay.py failure.apd \
  --processor ./build/ap_process_pcm \
  --output-pcm replay.pcm
```

Audio dumps may contain private speech; retention, access control and secure deletion are obligations of whoever handles the data. See [`docs/DIAGNOSTICS.md`](docs/DIAGNOSTICS.md).

## Research evaluation and independent evidence

`validation/` is the single repository-side acoustic data/evaluation/tuning framework. Its machine-readable authority source is [`validation/research-authority.json`](validation/research-authority.json), which defines four corpus tiers:

- `regression`: deterministic generated CI fixtures; eligible for development/search and regression replay;
- `research-validation`: sealed research/conditional data; eligible for algorithm research, not independent target-board or real-household evidence;
- `validation-grade`: pinned/sealed public or approved derived data; independent validation/shadow evidence only, never development search input;
- `validation-grade-blind`: repository-external HMAC holdout; independent post-selection evidence and never optimizer feedback.

The historical `product-certified` label is **not** a research evaluation tier. Prior certification schema v4 and its original receipts remain archived under `certification/`; the executable product-certification workflow has been retired. Real audio, board performance, thermal, power, routing and soak measurements each need their own actual evidence; none authorizes or blocks source-only experiments.

Pinned Compact/Full sources include Microsoft AEC Challenge, Microsoft DNS Challenge and OpenSLR SLR28 metadata. v2.1.0 adds a separate **Extended Real** family with license-isolated RealMAN, BUT ReverbDB, MUSAN, Mini LibriSpeech and optional VOiCES/AMI/ICSI plus research-only AISHELL-4/FSD50K/WHAM. Public corpora remain outside Git.

Extended Real adds real far-field/moving-source, measured-room, meeting/overlap and hard-negative stress with per-file SHA-256 provenance, scenario-stratified blind holdout, tail metrics, clipping/DC/VAD error gates and scenario/dimension coverage. It is public-data validation, not a substitute for physical-board/field measurements.

Large public validation runs only on a trusted `audio-validation` runner after readiness and dataset verification. See [`validation/README.md`](validation/README.md), [`docs/EXTENDED_REAL_VALIDATION.md`](docs/EXTENDED_REAL_VALIDATION.md) and [`docs/TRUSTED_RUNNERS.md`](docs/TRUSTED_RUNNERS.md).

## HIL and physical-target research

Optional real-board experiments run on trusted `[self-hosted, linux, audio-target]` runners with source/board identities, preflight/cleanup and immutable measurement evidence. Available experiment durations include 10 minutes, 1 hour, 8 hours, 24 hours and 72 hours; **no fixed 72-hour run is a prerequisite to research code, datasets or algorithm evaluation**.

When HIL is requested but not configured, `HIL_ENABLED!=true` is **fail-visible** rather than a silent PASS. A skipped or unavailable board run remains NOT_RUN/BLOCKED. A host or QEMU estimate must never be reported as an SSC305 measurement.

Record actual build/deployed/executed SHA-256, target CPU/RSS/p95/p99, audio-route continuity, independent acoustic results, thermal/power conditions and soak duration as available. Compare each against preregistered research questions; never infer deployment approval from a source-only or synthetic test. Historic product certificates and 72-hour policies remain available for provenance in [the archive](certification/README.md) but are not active scientific admission gates.

## Build and consume

Native Linux:

```bash
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build --parallel
ctest --test-dir build --output-on-failure
```

Cross-build presets include generic ARMv7-A, Cortex-A7 scalar/NEON, Cortex-A32 NEON, the conservative `ssc305-cortex-a32-low` research target profile and AArch64 NEON. Selected executable contracts also run under QEMU; QEMU timing is never treated as silicon timing.

Installed SDK:

```cmake
find_package(AudioPipeline CONFIG REQUIRED)
target_link_libraries(app PRIVATE AudioPipeline::core)
# Optional Linux runtime:
target_link_libraries(app PRIVATE AudioPipeline::runtime)
```

CMake and pkg-config consumers are built from a clean install prefix in CI.
Relative `CMAKE_INSTALL_LIBDIR` and `CMAKE_INSTALL_INCLUDEDIR` paths preserve
SDK relocation, including multiarch library directories. Absolute paths are
also supported as fixed install destinations and are emitted verbatim in the
pkg-config files; changing `cmake --install --prefix` does not relocate them.
For mixed absolute/relative layouts, set the final prefix at configure time;
the fixed destinations and their relation to that prefix are not relocatable.

## Repository gates

PR/main verification includes strict compile/tests, GCC/Clang, sanitizers, TSan, static analysis, coverage, backend/composition matrices, Arm cross-build/QEMU, resource/ROM pruning, paired performance comparisons, diagnostics replay, deterministic acoustic regression and public API/ABI contracts.

Public API/ABI version changes follow repository SemVer and keep CMake/CHANGELOG versions synchronized; research-only documentation and evidence updates do not manufacture new versions. PR/main changes are admitted through exact-SHA protected `summary=success` verification. **Successful Verify does not automatically publish a GitHub Release, tag or commercial artifact.** Public-audio, HIL and real-board results remain evidence-separated from source-only CI.

## Documentation

- [`docs/API_CONTRACT.md`](docs/API_CONTRACT.md) — public lifecycle/state/threading contract
- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — ownership and dependency direction
- [`docs/DSP_DESIGN.md`](docs/DSP_DESIGN.md) — algorithms
- [`docs/PERFORMANCE.md`](docs/PERFORMANCE.md) — performance/resource gates
- [`docs/DIAGNOSTICS.md`](docs/DIAGNOSTICS.md) — event/dump/replay contract
- [`docs/PORTING.md`](docs/PORTING.md) — BSP/ALSA/toolchain integration
- [`docs/TESTING.md`](docs/TESTING.md) — CI/HIL policy
- [`docs/TRUSTED_RUNNERS.md`](docs/TRUSTED_RUNNERS.md) — self-hosted runner readiness
- [`docs/EXTENDED_REAL_VALIDATION.md`](docs/EXTENDED_REAL_VALIDATION.md) — real/public far-field, measured-room, meeting and hard-negative validation
- [`certification/README.md`](certification/README.md) — retained historical certification policy/evidence (not active research authority)
- [`THIRD_PARTY.md`](THIRD_PARTY.md) — third-party/reference policy

## License

See [LICENSE](LICENSE).

Hosted CI also runs a required **Microsoft P.808 real-audio smoke** on four exact-revision CC-BY-4.0 clips. Inputs are SHA-256/Git-blob pinned, never stored in Git, and exercise stereo-to-mono materialization plus 48 kHz boundary resampling. This is validation-grade safety evidence, not far-field or physical-board evidence.

## Reproducible laboratory deployment

Trusted `audio-validation` and `audio-target` research controllers, public-data preparation, provenance, readiness and explicitly requested experiments are described in [`lab/README.md`](lab/README.md). Some older laboratory profiles still use historical commercial names; these do not establish research admission or hardware readiness. No genuine DUT data is claimed without a completed measurement.
