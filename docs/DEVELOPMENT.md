# Development Rules

Project goals, phase scope, iteration contracts and progress are indexed in
[the software/public-data program](program/README.md).

## Stable v2 policy

Version 2.0.0 establishes the current public API/ABI baseline. Within the 2.x line, public structures and exported symbols are compatibility contracts; incompatible public changes require the next major version.

The v2 baseline itself is a deliberate hard cut from 1.x. Do not reintroduce removed 1.x aliases, version-suffixed compatibility APIs, transitional wrappers, duplicate certification schemas, dead switches or migration-only architecture. Historical release facts belong in `CHANGELOG.md`, not in the current public surface.

Extensible structures use `struct_size`, `api_version` and reserved space so future 2.x additions can remain explicit and bounded.

## Dependency direction

Allowed production direction:

```text
core -> frontend / sync / activity / aec / enhance
modules -> frontend / sync / activity / aec / enhance
frontend/sync/activity/aec/enhance -> dsp/arch as required
platform/linux -> public pipeline API
```

Stage code must never depend on `src/modules`, core or Linux runtime. Sibling stage effects are events/results interpreted by core.

## Composition and build envelope

A product has both module composition and geometry envelope:

```text
AP_MODULES
AP_BUILD_MAX_IO_RATE_HZ
AP_BUILD_MAX_INTERNAL_RATE_HZ
AP_BUILD_MAX_MIC_CHANNELS
AP_BUILD_MAX_DELAY_MS
AP_BUILD_MAX_AEC_TAIL_MS
AP_RUNTIME_QUEUE_DEPTH
```

Adding/changing a build dimension requires generated build-info support, CMake/public validation, at least one CI boundary product, and proof that smaller products physically reduce state/ELF where applicable. CPU model names do not imply these values.

## Realtime rules

For synchronous stage/core/module code:

- no heap allocation in the data plane;
- no mutex, file/network I/O, logging or RPC;
- bounded loops/state;
- no runtime backend/plugin discovery;
- CPU model names forbidden in algorithm code;
- architecture intrinsics live only under `src/arch`.

Linux control-plane/thread/scheduling functionality lives under `src/platform/linux`.

## Runtime ownership

A pipeline is caller-owned until handed to `ap_runtime_open()`. While the worker is started, only the worker may mutate/access the live pipeline. Frame input uses `ap_runtime_submit_frame()`; control-plane runtime telemetry uses `ap_runtime_read_metrics()` and runtime-owned atomics.

Any change to ownership, counters, queue publication or lifecycle must pass ThreadSanitizer. ASan/UBSan is not a substitute for TSan.

## Numeric/API validation

Public floating-point inputs must be finite before range validation. Tests cover NaN, positive/negative infinity and important boundaries, including with `AP_ENABLE_FAST_MATH=ON`.

Status meaning stays precise: invalid input is `AP_EINVAL`, insufficient caller storage is `AP_ENOMEM`, unavailable build feature/lifecycle state is `AP_ESTATE`.

## DSP backend rules

Mutually exclusive choices use one selector rather than paired booleans:

```text
AP_AEC_BACKEND=MDF|NLMS
AP_NS_ESTIMATOR=EMA|MCRA
AP_SIMD_BACKEND=SCALAR|NEON
AP_RESAMPLER_MODE=BANDLIMITED|FAST
```

A backend exists only when its owning module is compiled. BANDLIMITED is the default resampler; FAST is an independent explicit product choice, not a compatibility alias.

## Acoustic-complexity rule

Added acoustic complexity requires a measured failure inside a declared evaluation
scope and evidence that the change addresses its root cause. In the current
software/public-data phase, physically audited simulation and hash-pinned public
data can justify bounded software research, not real-SKU performance claims.
Freeze acceptance rules and data roles before searching; require engineering,
anti-regression and independent confirmation gates before shipping a behavior
change. If no candidate demonstrates useful improvement, keep the lower-cost
implementation. Actual SKU performance and product certification still require
real device evidence; product capture/DUT/HIL work is deferred in this phase, not
marked PASS. See [the iteration process](program/PROCESS.md).

## Telemetry and standalone APIs

Telemetry names are product contracts. ERLE is valid only for AEC far-end-only/non-double-talk observations. Route/path resets start a new convergence epoch.

Stateful standalone modules follow one lifecycle:

```text
state_size -> aligned caller storage -> init -> reset -> process/status
```

Standalone wrappers reuse stage implementations and remain separate TUs for link pruning; never fork algorithms for standalone use.

## Verification before merge

A production change is complete only when relevant gates pass: architecture/hard-cut contract, native GCC/Clang strict builds, ASan/UBSan, TSan for runtime changes, backend/composition variants, RAM/ELF pruning, paired hosted performance, ARM cross-build/QEMU, static analysis, hosted coverage, acoustic validation contracts and the v2 ABI gate.

Hosted performance is a regression signal, never a Cortex board claim.

## SDK/package changes

Installed SDK changes must be consumed from a clean prefix through CMake and pkg-config. Consumer tests must compile, link and run; file-existence checks are insufficient.

## Release/version rules

`project(audio_pipeline VERSION ...)`, generated build identity and the top `CHANGELOG.md` release must agree. A release SHA needs merged-PR lineage and successful exact-SHA main Verify. Release automation creates the matching annotated `vX.Y.Z` tag, reproducible SDK/source archives, checksums, SBOM and attestations, then requires an immutable published Release.

The initial v2 ABI gate rejects any removed 1.x runtime/build-info symbols. After `v2.0.0` is published, subsequent 2.x releases use it as the compatibility baseline.

## Product certification

Current certification accepts schema v4 only. No code or hosted CI may fabricate target CPU/p95/p99, thermal/power, shipping-route XRUN behavior, private acoustic scores, shipping toolchain identity, build/deploy/execute identity, required 72 h soak, or lifecycle archive durability.

Product Certification uses `audio-builder`, a distinct `audio-target` DUT and `certification-archive`. A record is valid only when exact binaries match across build/deploy/execute, real policy/corpus/sensor gates pass, the bundle is attested and the immutable `product-lifecycle` archive receipt validates.
