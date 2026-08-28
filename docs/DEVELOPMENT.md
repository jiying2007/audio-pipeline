# Development Rules

## Hard-cut policy

The repository is pre-1.0 and intentionally uses hard cuts for public/configuration changes unless a migration period is explicitly approved. Do not add compatibility aliases, dead switches or duplicate implementations merely to preserve an unreleased shape.

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

Adding/changing a build dimension requires:

1. generated build-info support;
2. validation in CMake and public runtime config;
3. at least one CI product exercising the boundary;
4. proof that smaller products physically reduce state/ELF where applicable.

Do not infer these values from a CPU name.

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

A pipeline is caller-owned until handed to the Linux runtime. While the runtime worker is started, only the worker may access the pipeline. Control-plane APIs must use runtime-owned atomics or published SPSC snapshots.

Any change to runtime ownership, counters, queue publication or lifecycle must pass ThreadSanitizer. ASan/UBSan is not a substitute for TSan.

## Numeric/API validation

Public floating-point inputs must be explicitly finite before range validation. Tests must cover NaN, positive/negative infinity and important range boundaries, including with `AP_ENABLE_FAST_MATH=ON`.

Status meaning must remain precise: invalid input is `AP_EINVAL`, insufficient caller storage is `AP_ENOMEM`, unavailable build feature/lifecycle state is `AP_ESTATE`.

## DSP backend rules

Mutually exclusive choices use one string selector, not paired booleans:

```text
AP_AEC_BACKEND=MDF|NLMS
AP_NS_ESTIMATOR=EMA|MCRA
AP_SIMD_BACKEND=SCALAR|NEON
AP_RESAMPLER_MODE=BANDLIMITED|FAST
```

A backend exists only when its owning module is compiled.

## Resampler changes

BANDLIMITED is the product default. Changes require both:

- signal-quality contracts: passband level, stopband/alias attenuation, continuity/reset and delay;
- performance regression measurements.

FAST remains an explicit accepted fallback and its behavior/performance must remain separately tested. Do not replace fixed-ratio paths with a large generic SRC without board evidence.

## Telemetry changes

Telemetry names are product contracts. ERLE is only valid for AEC far-end-only/non-double-talk observations. Route/path resets start a new convergence epoch. Do not reuse ERLE as a generic signal ratio.

## Standalone API rules

A stateful public module should provide a consistent lifecycle:

```text
state_size -> aligned caller storage -> init -> reset -> process/status
```

Standalone wrappers reuse stage implementations and remain separate TUs so high-level consumers can link-prune them. Do not fork algorithms for standalone use.

## Verification before merge

A production change is complete only when relevant gates pass:

- architecture contract;
- native GCC/Clang and strict warnings;
- ASan/UBSan;
- TSan for runtime ownership changes;
- MDF/NLMS, EMA/MCRA, precise/fast-math and BANDLIMITED/FAST where relevant;
- LOW/TINY/RAW/voice/module-only composition tests;
- pipeline/runtime RAM and final consumer ELF pruning;
- hosted same-runner core/module/runtime performance regression gates;
- ARMv7-A/Cortex-A7/Cortex-A32/AArch64 cross-builds;
- selected ARM QEMU executable contracts;
- static analyzer;
- source line coverage gate (currently >=90% hosted);
- acoustic evaluation harness contract.

Hosted performance is a regression signal, never a Cortex board claim.

## SDK/package changes

Installed SDK changes must be consumed from a clean prefix through both:

```text
find_package(AudioPipeline CONFIG REQUIRED)
pkg-config audio-pipeline
```

The consumer build must compile, link and run. File-existence checks alone are insufficient.

## Coverage, fuzz and analysis

PR Quality CI maintains the current coverage baseline. Nightly fuzz is intentionally longer than PR smoke. Static analyzer findings are release blockers unless explicitly triaged with a documented reason.

## Release/version rules

`project(audio_pipeline VERSION ...)`, generated build fingerprint and `CHANGELOG.md` must describe the same release. After a version bump reaches `main`, the release workflow is responsible for creating the matching `vX.Y.Z` tag (when absent), SDK/source archives, SHA256 checksums and GitHub Release.

A release does not imply target-board certification. Certification records remain SKU-specific.

## Product certification

No code/CI change can fabricate:

- target CPU percentage or frame p95/p99;
- thermal/power;
- XRUN behavior on the shipping audio route;
- private acoustic corpus scores;
- 8 h soak results.

Use `certification/record.schema.json` and `docs/PLATFORM_SUPPORT.md` to close those on real hardware.
