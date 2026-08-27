# Development and Module Rules

## Dependency direction

Allowed production dependency direction:

```text
core -> frontend / sync / aec / enhance
modules -> frontend / sync / aec / enhance
frontend -> dsp
sync -> dsp
AEC -> dsp / arch
enhance -> dsp
arch -> dsp types only
platform/linux -> public pipeline API only
```

`src/modules` is a public standalone adapter layer. Stage implementations must never depend back on it, and core must never call through it. Sibling DSP stages do not include/call each other's private contracts; cross-stage effects are events/results interpreted by core.

## State ownership

`src/core/ap_pipeline_internal.h` is the only full-pipeline composite state. HPF, BF, SYNC, AEC, RES, NS, AGC and VAD own distinct private state types. A build that omits a stage must omit its pipeline member and implementation TU as well.

Standalone wrappers embed/reuse the same private stage state. Do not fork an algorithm into separate pipeline and standalone implementations. Wrapper-only persistent data is limited to adapter metadata needed to enforce the public contract.

No repository-wide catch-all internal header may be introduced.

## Composition rules

There are two composition times:

1. **Build time:** `AP_MODULES` defines physical SDK capability and controls ROM/RAM pruning.
2. **Runtime init:** `ap_config_t.stages` selects a topology-safe subset of compiled DSP stages.

Do not turn runtime composition into an arbitrary DAG or node/plugin framework. The high-level order is fixed. New dependencies must be represented in `ap_pipeline_validate_config()` and covered by invalid-composition tests.

Current required edges:

```text
BF -> two mics
AEC -> SYNC
RES -> AEC
delay/drift policy -> SYNC
```

RESAMPLER is a boundary module, not an `AP_STAGE_*` bit. RAW/resampler-only is therefore a valid high-level build/instance with zero DSP stage bits.

## Public SDK capability

`cmake/audio_pipeline_build.h.in` produces the installed capability header. When adding/removing a module:

- update `AP_MODULES` parsing;
- update `AP_HAVE_MODULE_*` generation;
- condition public declarations in `audio_modules.h`;
- ensure module-only install does not leak unrelated high-level/runtime headers;
- add a composition preset/CI case when the new boundary is materially different.

Do not expose a declaration for a module not present in the binary.

## Realtime rules

For synchronous core/stage/module code:

- no heap allocation;
- no mutexes, file/network I/O, logging or RPC;
- bounded loops/state only;
- no runtime plugin discovery or function-pointer backend dispatch in the 10 ms path;
- CPU model names are forbidden; depend on scalar/NEON capability only;
- architecture intrinsics live only under `src/arch/`.

Linux thread, affinity, semaphore and scheduling policy lives only under `src/platform/linux/`.

`scripts/check-architecture.sh` enforces these boundaries in CI, including removal of the old public `enable_*` stage booleans and old multi-stage frontend/enhance TUs.

## Backend rules

AEC, NS estimator and SIMD choices are compile-time selectors. New mutually exclusive choices use string selectors, not paired enable/disable booleans. Backend selectors are meaningful only when their owning module is part of `AP_MODULES`.

A backend must not reach upward into core or laterally into another stage.

## Memory/pruning verification

Every composition refactor must prove that pruning is physical, not just runtime bypass. CI must build representative graphs and compare exact state sizes. At minimum:

```text
RAW < voice frontend < full pipeline
```

The current GCC reference is 3,392 B < 9,936 B < 78,456 B. Do not encode those exact values as ABI constants; encode ordering/ceilings and report exact sizes from the selected build.

Standalone state must fit `AP_MODULE_STATE_MAX_BYTES`; exact per-module size functions are authoritative.

## Public API hard cuts

Before changing stage bits, public structs, state contracts or module declarations:

1. update `docs/API_CONTRACT.md`;
2. update high-level and standalone contract tests;
3. run full, RAW, voice, AEC-only and NS-only composition CI;
4. verify MDF/NLMS and EMA/MCRA where applicable;
5. verify ARMv7-A scalar and NEON/AArch64 cross profiles;
6. run same-runner core/module/runtime regression gates.

Do not add compatibility aliases unless the product explicitly requires a migration period; the current repository policy is hard-cut/no residue.

## Performance changes

A theoretically cleaner composition is rejected if it materially regresses the full realtime graph. Full pipeline keeps unity compilation to preserve inlining; module-only products keep independent translation units for linker pruning. Hosted same-runner numbers are regression signals only; Cortex-A7/A32 CPU/RSS/thermal/power claims require target-board certification.
