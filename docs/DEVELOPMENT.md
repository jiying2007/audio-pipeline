# Development Rules

[简体中文](DEVELOPMENT.zh-CN.md)

The repository is in a **software-commercial-ready maintenance state**. Historical software/public-data iteration evidence remains indexed under [the program archive](program/README.md), but there is no default READY software task. E001 remains external/deferred. New software work should start from a concrete defect, regression, integration need or verified control-plane/documentation drift rather than from a desire to add more complexity.

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

Adding/changing a build dimension requires generated build-info support, CMake/public validation, at least one CI boundary product, and proof that smaller products physically reduce state/ELF where applicable. CPU model names do not imply these values. A named commercial product preset must itself be a required executable CI contract rather than an undocumented downstream configuration.

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

Added acoustic complexity requires a measured, reproducible failure inside a declared evaluation scope and evidence that the proposed change addresses its root cause. Freeze acceptance rules, data roles and budgets before searching. Physically audited simulation and hash-pinned public data may justify bounded software research, not real-SKU performance claims.

A measurement change and a shipping algorithm change must not approve each other in one experiment. Require engineering, anti-regression and independent confirmation gates before shipping a behavior change. If no candidate demonstrates useful improvement, keep the lower-cost implementation.

Actual SKU performance and Product Certification still require real device evidence. Missing DUT/HIL/physical evidence is external/deferred, never a synthetic PASS.

## Telemetry and standalone APIs

Telemetry names are product contracts. ERLE is valid only for AEC far-end-only/non-double-talk observations. Route/path resets start a new convergence epoch.

Stateful standalone modules follow one lifecycle:

```text
state_size -> aligned caller storage -> init -> reset -> process/status
```

Standalone wrappers reuse stage implementations and remain separate TUs for link pruning; never fork algorithms for standalone use.

## Verification before merge

A production change is complete only when relevant gates pass: architecture/hard-cut contract, native GCC/Clang strict builds, ASan/UBSan, TSan for runtime changes, backend/composition variants, RAM/ELF pruning, paired hosted performance, Arm cross-build/QEMU, named commercial product-preset contracts, static analysis, hosted coverage, acoustic validation contracts and the v2 ABI gate.

Hosted performance is a regression signal, never a Cortex board claim.

## SDK/package changes

Installed SDK changes must be consumed from a clean prefix through CMake and pkg-config. Consumer tests must compile, link and run; file-existence checks are insufficient.

## Documentation and Chinese integration surface

Changes to public API/lifecycle, product presets, ownership/data flow, validation authority, Release/Certification behavior, diagnostics/privacy or operator commands must update documentation in the same PR. Critical commercial integration changes must also check the Chinese entry layer (`README.zh-CN.md`, `docs/README.zh-CN.md` and relevant `docs/*.zh-CN.md`).

Low-level machine schemas and explicitly canonical specifications remain the single source of truth; the Chinese layer must not create a second independent protocol.

## Release/version rules

`project(audio_pipeline VERSION ...)`, generated build identity and the top `CHANGELOG.md` release must agree. A release SHA needs merged-PR lineage and successful exact-SHA main Verify. Release automation creates the matching annotated `vX.Y.Z` tag, reproducible SDK/source archives, checksums, SBOM and attestations, then requires an immutable published Release.

The initial v2 ABI gate rejects any removed 1.x runtime/build-info symbols. After `v2.0.0` is published, subsequent 2.x releases use it as the compatibility baseline. Release-neutral maintenance must not manufacture a new release merely to advance documentation/governance.

## Product certification

Current certification accepts schema v4 only. No code or hosted CI may fabricate target CPU/p95/p99, thermal/power, shipping-route XRUN behavior, private acoustic scores, shipping toolchain identity, build/deploy/execute identity, required 72 h soak, or lifecycle archive durability.

Product Certification uses `audio-builder`, a distinct `audio-target` DUT and `certification-archive`. A record is valid only when exact binaries match across build/deploy/execute, real policy/corpus/sensor gates pass, the bundle is attested and the immutable `product-lifecycle` archive receipt validates.

## Stop condition

When exact-main gates are green, no software task/PR is open and only real external Product Qualification evidence remains, preserve the stable baseline. Do not create software changes until a new verified defect, regression, integration requirement or external-infrastructure failure exists.
