# 1.3.0

- Add a validation-grade self-validation layer with explicit `regression`, `validation-grade`, `validation-grade-blind`, and `product-certified` trust boundaries.
- Pin Microsoft AEC Challenge and DNS Challenge source revisions plus OpenSLR SLR28 metadata; require local SHA-256 sealing/checksum-index verification before public data can contribute to validation-grade evidence.
- Add deterministic multi-scenario regression corpus generation and a dependency-free evaluator for SI-SDR, SI-SDR improvement, AEC render-correlation reduction, ERLE, VAD F1, dynamic echo-path changes, and stream discontinuities.
- Add public AEC/DNS/SLR28 corpus adapters, HMAC blind holdout splitting with repository-external keys, hash-bound validation reports/evidence manifests, and a self-hosted `audio-validation` workflow.
- Extend `ap_process_pcm` with offline per-frame metrics JSONL and deterministic control-event injection without changing the core DSP ABI.
- Gate every PR/main on deterministic self-validation, run independent seeds nightly, and publish a clearly regression-only validation-smoke report alongside release SDK/source/SBOM artifacts.

# 1.2.0

- Close runtime async failure semantics: failed DSP submissions publish a bounded completion status when output capacity exists, increment failure counters, emit `AP_EVENT_PIPELINE_ERROR`, and latch ERROR/FATAL state independently from the event queue.
- Add additive runtime metrics v3 with pipeline-failure, critical-event, and sampled CPU-migration telemetry.
- Bind product certification records to exact policy/corpus/evidence bytes and add `ap_certify.py` plus machine-readable evidence/corpus manifests.
- Add ABI/API compatibility comparison against released v1.1.1, expanded runtime/recorder fuzzing, deterministic SPDX SBOM generation, reproducible release packaging, and supply-chain attestation hooks.

# Changelog

All notable changes are recorded here. The project follows semantic versioning. Starting with 1.0.0, documented public API/ABI and package contracts are treated as stable within the 1.x line; incompatible changes require a new major version.

## [Unreleased]

- SKU-specific Cortex-A7/A32/AArch64 board certification may be added independently of the software release line and does not block the repository SDK release.

## [1.1.1] - 2026-08-29

- validate Flight Recorder rate/frame/channel geometry and reject runtime/recorder mismatches before diagnostic copies;
- make Flight Recorder defaults metrics-only so private microphone/render/output PCM is explicit opt-in;
- reject unknown/invalid runtime commands before enqueue and surface apply-time tuning rejection as a bounded diagnostic event;
- consolidate PR/main verification behind one `Verify` workflow, include runtime in coverage/static analysis and execute runtime tests under Arm QEMU;
- gate Release on a successful exact-SHA main Verify run, add provenance attestations and pin third-party Actions to immutable commit SHAs with Dependabot maintenance;
- require explicit per-SKU certification policy plus CPU/RSS/latency/thermal/power/acoustic/soak thresholds for `product-certified` evidence;
- package LICENSE, third-party notice, README and changelog in the installed SDK.

## [1.1.0] - 2026-08-28

- add an additive, size/versioned runtime control plane for frame metadata, hardware timestamps, stream discontinuities, echo-path changes, reset, quality and tuning without changing the frozen 1.x public struct layouts;
- preserve DSP timeline continuity under output backpressure: a full output queue now drops only publication while AEC/SYNC/NS/AGC/VAD state continues to advance every accepted capture frame;
- extend long-running runtime observability with lock-free 32-bit-atomic-backed 64-bit counters, queue high-water marks, discontinuity/gap/timestamp counters, actual RT scheduler state and fixed-histogram DSP p50/p95/p99;
- harden Linux RT setup with validated CPU affinity, optional worker stack sizing/thread naming/mlock and observable non-fatal setup failures;
- add bounded fixed-size runtime events plus a caller-owned pre/post-roll Flight Recorder; event delivery may drop under pressure but recorder triggering is independent of event-ring capacity;
- add the versioned `.apd` dump format and PC-side `apdump`/`apreplay` tooling, with CI that generates, parses, extracts and bit-exact replays deterministic dumps;
- expand acoustic evaluation to 1/2-mic and capture-only/full-duplex cases with enforceable case thresholds, and repair the processor CLI so the evaluation runner's sample-rate/mic geometry is actually honored;
- strengthen SKU certification so `product-certified` requires concrete target performance/acoustic/artifact/8 h soak evidence plus semantic p95/p99/XRUN/overrun/drop gates;
- stabilize Activity/DTD with attack/release energy tracking and far-end/double-talk hysteresis; make MDF/NLMS adaptation convergence-aware so steady far-end-only operation reduces adaptation work and double-talk/reference loss immediately restores fast cadence;
- consume fractional SYNC drift residue with linear reference interpolation and replace delay-search square-root correlation with equivalent squared normalized correlation;
- retain resource ceilings after productization: current hosted GCC references are pipeline full=78,096 B, LOW=46,928 B, TINY=25,408 B, RAW=1,064 B and runtime full=32,632 B, TINY=5,080 B;
- install the diagnostics public header together with the Linux runtime SDK and promote the project package version to 1.1.0.

The 1.1.0 public surface is additive. Existing 1.0 configuration, metrics, runtime configuration and runtime metrics structure layouts are not changed.

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
- no DSP, API, ABI, resource-envelope or acoustic-behavior change relative to the validated v0.7.0 code line.

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
