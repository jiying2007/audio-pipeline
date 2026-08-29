# 2.0.0

- Hard-cut the public SDK at a new major-version boundary; v2 intentionally provides no source or binary compatibility aliases for removed v1 generational APIs.
- Collapse build identity to one complete `ap_build_info_t` returned by `ap_build_info()`; remove the parallel build-info v2 surface.
- Collapse Linux runtime integration to one API generation: `ap_runtime_open()`, `ap_runtime_submit_frame()` and `ap_runtime_read_metrics()` with the current options, frame metadata, command, critical-state and full long-running metric contracts.
- Remove runtime `init/init_ex`, `submit/submit_ex`, metrics v1/v2/v3 public generations and their exported compatibility symbols.
- Make product-certification records schema-v4-only; historical v2/v3 records remain historical release artifacts but are no longer accepted by the current validator or current shipping workflow.
- Replace the v1.1.1 additive ABI gate with a v2 hard-cut symbol/header contract; after v2.0.0 is released, later 2.x releases use v2.0.0 as their ABI baseline.
- Migrate native tests, fuzz targets, benchmarks, diagnostics, installed-SDK consumers and the real ALSA/HIL runtime path to the single v2 API.
- No DSP algorithm, acoustic threshold, resource envelope, HIL trust boundary or shipping certification threshold changes are introduced by the v2 API cleanup.

# 1.6.1

- Add a shared fail-closed `tools/runner_preflight.py` contract for `audio-validation`, `audio-builder`, `audio-target`, and `certification-archive` self-hosted roles; `READY` is infrastructure readiness only and never acoustic/HIL/product evidence.
- Add the manually dispatched Trusted Runner Readiness workflow so lab machines can be validated against an exact source ref before allocating public validation, 8/24 h HIL, or 72 h shipping certification work.
- Make Compact/Full public validation capture the `audio-validation` runner readiness report in the sealed evidence bundle before dataset verification or acoustic execution.
- Make HIL validate and seal `audio-target` runner readiness before board preflight, and classify missing runner prerequisites as `INFRA_FAILURE` rather than product failure.
- Add one trusted-runner activation runbook covering public validation, HIL enablement, shipping builder/toolchain readiness, lifecycle archive readiness, and readiness invalidation after machine/input changes.
- No DSP, public C API/ABI, acoustic thresholds, resource envelopes, or shipping-certification acceptance thresholds change in this maintenance release.

# 1.6.0

- Close the main-branch performance bypass: PR verification compares `origin/main` to the candidate while main push verification compares the exact `event.before` revision to `HEAD`; paired core/NS/resampler/runtime performance gates now run on main as part of FULL verification.
- Establish one hosted resource source of truth in `ci/resource-baseline.json`, generate `docs/generated/RESOURCE_BASELINE.md`, and make CI re-measure/diff the generated JSON and Markdown so resource values cannot silently drift across API/Performance/Platform documentation.
- Replace pre-1.0 development language with the stable 1.x ABI policy and keep API evolution additive/versioned.
- Promote shipping certification to schema v4 with a checked-in shipping-approved Cortex-A32 LOW policy, explicit 72 h minimum soak, and hard rejection of example/not-for-shipping policies.
- Split product certification across `audio-builder`, `audio-target`, and `certification-archive`: exact shipping compiler/sysroot/CFLAGS build, artifact deployment, build/deployed/executed SHA-256 equality, real target benchmark/route soak, evidence attestation, and immutable product-lifecycle archive receipt validation.
- Make HIL absence visible instead of silently skipped for scheduled/post-release tiers; real HIL/acoustic/thermal/power evidence remains mandatory and is never synthesized by hosted CI.
- Add `WARMING_UP`/`MATURE` historical-trend semantics so a passing short history cannot be described as a statistically mature gate; 30 comparable history samples are required for maturity.
- Add repository-governance audit tooling for PR-only main integration, strict required `summary`, deletion/non-fast-forward protection and protected `v*` tags, while keeping platform Ruleset/immutable-release enablement an explicit administrative prerequisite rather than a repository claim.
- Add acoustic-upgrade decision tooling: advanced BF/calibration/wind/mic-health/drift work is eligible only when real shipping acoustic evidence violates the approved policy; passing evidence preserves the low-compute baseline.
- No architecture redesign or speculative DSP expansion is introduced by this release; product-final status still requires enforced GitHub governance plus real shipping-board/HIL/certification evidence.

# 1.5.0

- Rework PR verification into mandatory Fast Gate -> impact-aware Full Gate while forcing every `main` push through the complete release verification graph.
- Add conservative `ci_impact.py` dependency routing with unknown/public/build/test-infrastructure changes expanding to FULL, plus dynamic composition, Arm, backend, performance, ALSA, ABI and extended matrices.
- Replace repeated ARM/QEMU/ALSA/static-analysis package installation with a smoke-tested GHCR toolchain image pinned by immutable digest; add content-addressed `ccache` reuse without caching test or certification results.
- Add stable CI failure taxonomy, acoustic failure reproducer bundles, Nightly 100-run flaky sentinel and median/MAD historical CPU/latency/acoustic trend gates.
- Add metamorphic/property DSP contracts for deterministic reset/replay, silence stability and topology invariants.
- Add real-route accelerated fault injection for codec/PCM restart, render gaps and CPU stalls while keeping nominal certification evidence fault-free.
- Add HIL board metadata, preflight, cleanup and SHA-256 evidence sealing with `INFRA_FAILURE` separated from product/HIL failures.
- Add tiered trusted-hardware soak: accelerated PR 10 min, Nightly 1 h, Release 8 h, Weekly 24 h and Certification 72 h. Scheduled/post-release HIL is explicitly gated by `HIL_ENABLED=true`, and untrusted public PR code never auto-runs on self-hosted product boards.
- Add permanent CI toolchain-image rebuild workflow and formal English/Chinese testing/HIL operations documentation.
- No hosted, cross-build or QEMU result is promoted to a real product-board certification claim; shipping certification still requires real target evidence.

# 1.4.0

- Add additive build identity v2 with exact source revision, compiler, target triple, build type and SHA-256 configuration digest while preserving the frozen 1.x `ap_build_info_t` layout.
- Make `ap_bench` route-geometry aware so target CPU/latency evidence measures the shipping sample rate and microphone count instead of an implicit 16 kHz/2-mic graph.
- Turn Product Certification into an `audio-target` self-hosted measurement workflow: exact target build, DSP benchmark, RSS/thermal/power sampling, real ALSA-route soak, immutable evidence packaging and strict policy validation.
- Upgrade new certification records to schema v3 with certification-binary hashes and materialized evidence size/SHA-256 revalidation; historical v2 records remain accepted.
- Make real ALSA route soak expose XRUN recovery, queue/drop/overrun/failure and runtime p50/p95/p99/critical telemetry; synthetic runtime soak is no longer accepted as product-route evidence.
- Keep private real-product acoustic results and corpus manifests external; the workflow refuses to manufacture hosted acoustic evidence or substitute missing power/thermal measurements.

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