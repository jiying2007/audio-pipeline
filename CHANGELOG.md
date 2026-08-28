# Changelog

All notable changes are recorded here. The project follows semantic versioning. Starting with 1.0.0, documented public API/ABI and package contracts are treated as stable within the 1.x line; incompatible changes require a new major version.

## [Unreleased]

- SKU-specific Cortex-A7/A32/AArch64 board certification may be added independently of the software release line and does not block the repository SDK release.

## [1.0.0] - 2026-08-28

- promote the validated low-compute Arm speech pipeline and standalone DSP module SDK to the first stable product release;
- freeze the public 10 ms PCM/frame contract, caller-owned state/alignment/error semantics, topology-safe stage-mask composition and standalone module lifecycle as the 1.x compatibility baseline;
- freeze the build/product composition model: `AP_MODULES`, build geometry caps, MDF/NLMS, EMA/MCRA, SCALAR/NEON, BANDLIMITED/FAST and precise/fast-math selectors remain explicit compile-time product choices;
- ship CMake package exports and pkg-config metadata with clean-prefix consumer validation;
- ship race-safe Linux SPSC runtime ownership, TSan coverage, resource/RAM/ELF pruning gates, QEMU Arm execution, coverage/static-analysis/nightly fuzz automation and acoustic-evaluation/certification schemas;
- ship the BANDLIMITED boundary resampler, timestamp observation, echo-path-change notification, reusable Activity/DTD module and corrected ERLE convergence telemetry;
- ship reproducible GitHub release automation that builds/tests/installs/packages/checksums before creating the annotated tag and Release assets;
- retain target-board CPU/thermal/power/8 h soak and private acoustic-corpus measurements as per-SKU certification records rather than prerequisites for the software SDK release.

No DSP, public API, ABI, resource-envelope or acoustic-behavior changes are introduced by the 1.0.0 promotion relative to the validated 0.7.1 code line; 1.0.0 establishes the stable support contract for that validated productized implementation.

## [0.7.1] - 2026-08-28

- create annotated release tags only after build, test, SDK installation, packaging and checksum generation have all succeeded;
- close the release/main reproducibility gap introduced by the v0.7.0 release-promotion workflow fix;
- no DSP, public API, ABI, resource-envelope or acoustic-behavior change relative to the validated v0.7.0 code line.

## [0.7.0] - 2026-08-28

- make the bandlimited boundary resampler the formally gated production default while preserving the explicit FAST validation fallback;
- enforce fixed-ratio anti-alias/passband contracts for 8/16 kHz internal DSP paths across supported device rates;
- formalize capture/render timestamp observation and explicit echo-path-change notification as synchronization/AEC reset contracts;
- add a repository acoustic-evaluation manifest/schema/runner so private product corpora can use the same metric interface without being committed to the repository;
- add dedicated Audio Quality Gates covering bandlimited/FAST resampling, synchronization/route-change semantics and the acoustic-eval self-test.

The repository audio-quality gate is synthetic/contract validation. Real robot far-end, double-talk, motor-noise, enclosure/path-change and product microphone/speaker corpus certification remains per shipping SKU and is not inferred from hosted CI.

## [0.6.0] - 2026-08-28

- formalize compile-time geometry caps for maximum I/O/internal rate, microphone count, render delay, AEC tail and runtime queue depth;
- make LOW/TINY/RAW builds physically reduce pipeline resident RAM rather than only reducing runtime work;
- prune Linux runtime queue storage from the selected maximum I/O geometry and queue depth;
- keep standalone module adapters out of full-pipeline unity batches so the linker can drop unused public wrappers;
- add final-consumer ELF pruning verification instead of treating static-library size as a ROM claim;
- add absolute hosted GCC RAM ceilings: full <=80,000 B, LOW <=50,000 B, TINY <=28,000 B, RAW <=2,048 B; runtime full <=32,768 B and TINY <=8,192 B.

Current hosted GCC reference measurements are pipeline full=78,072 B, LOW=46,904 B, TINY=25,384 B, RAW=1,064 B and runtime full=31,824 B, TINY=4,464 B. These are CI resource-contract measurements, not target-board CPU/performance claims.

## [0.5.0] - 2026-08-28

- eliminate unsynchronized Linux runtime reads of worker-owned pipeline telemetry and require ThreadSanitizer coverage;
- add consistent finite/NaN/Inf configuration validation and negative contracts;
- tighten ERLE telemetry to valid AEC far-end-only, non-double-talk convergence epochs;
- promote Activity/DTD to a standalone reusable module shared by high-level and standalone AEC integration;
- add explicit timestamp observation and echo-path-change notification contracts;
- normalize standalone module reset/frame/lifecycle semantics;
- add build fingerprinting for backend, SIMD, fast-math and compiled-envelope diagnostics.

## [0.4.0] - 2026-08-27

- add static pipeline composition and standalone DSP module APIs;
- physically prune omitted module translation units and state;
- add RAW, voice-front-end, AEC-only and NS-only composition contracts.
