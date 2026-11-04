# Development Rules

[简体中文](DEVELOPMENT.zh-CN.md)

The repository is maintained as **technical research only**, not a product launch or shipping-certification program. See [research-only execution](RESEARCH_ONLY_EXECUTION.md) and the [historical program archive](program/README.md). E001 refers to retained historical infrastructure evidence; no release/product approval or 72-hour certification is a prerequisite for algorithm, data, runtime or target-resource research. New work should start from a reproducible defect, an independently measured hypothesis or an explicit integration research goal.

## Public API/ABI discipline

The current 2.x line is the public C API/ABI compatibility line. Public structures and exported symbols are compatibility contracts; incompatible public changes require the next major version.

Do not reintroduce retired public names, version-suffixed compatibility APIs, parallel wrappers, duplicate certification schemas, dead switches or migration-only architecture. Historical release facts belong in `CHANGELOG.md`, not in the current public surface. The repository API/ABI contract keeps retired symbols negative-tested so accidental resurrection fails closed.

Extensible structures use `struct_size`, `api_version` and reserved space so compatible additions can remain explicit and bounded.

## Dependency direction

Allowed source dependency direction:

```text
core -> frontend / sync / activity / aec / enhance
modules -> frontend / sync / activity / aec / enhance
frontend/sync/activity/aec/enhance -> dsp/arch as required
platform/linux -> public pipeline API
```

Stage code must never depend on `src/modules`, core or Linux runtime. Sibling stage effects are events/results interpreted by core.

## Composition and build envelope

A research build has both module composition and a bounded geometry envelope:

```text
AP_MODULES
AP_BUILD_MAX_IO_RATE_HZ
AP_BUILD_MAX_INTERNAL_RATE_HZ
AP_BUILD_MAX_MIC_CHANNELS
AP_BUILD_MAX_DELAY_MS
AP_BUILD_MAX_AEC_TAIL_MS
AP_RUNTIME_QUEUE_DEPTH
```

Adding/changing a build dimension requires generated build-info support, CMake/public validation, at least one CI boundary build, and proof that smaller module/geometry configurations reduce state/ELF where applicable. CPU model names do not imply these values. A named embedded-target research preset must have an executable CI contract rather than relying on undocumented assumptions.

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

A backend exists only when its owning module is compiled. BANDLIMITED is the default resampler; FAST is an independent explicit experiment choice, not a compatibility alias.

## Acoustic-complexity rule

Added acoustic complexity requires a measured, reproducible failure inside a declared evaluation scope and evidence that the proposed change addresses its root cause. Freeze acceptance rules, data roles and budgets before searching. Physically audited simulation and hash-pinned public data may justify bounded software research, not physical-target performance claims.

A measurement-method change and a candidate-algorithm change must not approve each other in one experiment. Require engineering, anti-regression and independent confirmation gates before interpreting a candidate as improved. If no candidate demonstrates useful improvement, keep the lower-cost implementation.

Actual physical-target performance requires authorized real-device evidence. Missing DUT/HIL/physical experiments are `NOT_RUN` or `BLOCKED`, never a synthetic PASS.

## Telemetry and standalone APIs

Telemetry names are research reproducibility contracts. ERLE is valid only for AEC far-end-only/non-double-talk observations. Route/path resets start a new convergence epoch.

Stateful standalone modules follow one lifecycle:

```text
state_size -> aligned caller storage -> init -> reset -> process/status
```

Standalone wrappers reuse stage implementations and remain separate TUs for link pruning; never fork algorithms for standalone use.

## Verification before merge

A research source change is complete only when relevant gates pass: architecture/public-contract checks, native GCC/Clang strict builds, ASan/UBSan, TSan for runtime changes, backend/composition variants, RAM/ELF pruning, paired hosted performance, Arm cross-build/QEMU, named embedded-target research-preset contracts, static analysis, hosted coverage, acoustic validation contracts and the public API/ABI gate.

Hosted performance is a regression signal, never a Cortex board claim.

## SDK/package changes

Installed SDK changes must be consumed from a clean prefix through CMake and pkg-config. Consumer tests must compile, link and run; file-existence checks are insufficient.

## Documentation and Chinese integration surface

Changes to public API/lifecycle, research presets, ownership/data flow, validation authority, diagnostics/privacy, experimental commands, or historical release references must update documentation in the same PR. Critical research/integration changes must also check the Chinese entry layer (`README.zh-CN.md`, `docs/README.zh-CN.md` and relevant `docs/*.zh-CN.md`).

Low-level machine schemas and explicitly canonical specifications remain the single source of truth; the Chinese layer must not create a second independent protocol.

## Research source identity and historical version references

Each research result binds the exact source commit, build identity, configuration,
data-role/rights and recorded metrics. `project(audio_pipeline VERSION ...)`,
the generated build identity and historical `CHANGELOG.md` must remain
internally consistent; this does **not** authorize a GitHub Release or require
a new SemVer tag for ordinary studies.

Public C API/ABI compatibility remains a source-level engineering contract:
the required consumer/ABI regression uses exact preserved baselines and rejects
removed symbols or revived obsolete APIs. Historical packaged baseline identity
does not confer product readiness. A passed Verify is evidence of the checks
actually run at that SHA, not a product certificate or real-SSC305 measurement.

## Optional physical-target research and source rights

An independent physical HIL experiment requires an actual isolated target
runner, authorized source/audio, recorded toolchain/board/route and measured
CPU p95/p99, RSS, thermal/power, XRUN and observed duration. Dispatch
[`hil-soak.yml`](../.github/workflows/hil-soak.yml) manually with an exact
40-character source SHA; `research-72h` is optional and **not** a minimum
product-certification requirement. Missing hardware or independent evidence
must remain `NOT_RUN`, `BLOCKED` or `FAIL`, never PASS.

The historical `certification/` policies, past Release manifests and
published archives are read-only source/evidence context, not current research
execution authority. Third-party source-license restrictions, including
noncommercial clauses where applicable, and independent evaluation roles
must still be honored.

## Stop condition

When exact-main research gates are green and no independent experiment or reproducible defect is pending, preserve the stable source baseline. Do not manufacture new studies, approvals or product releases merely to advance status.
