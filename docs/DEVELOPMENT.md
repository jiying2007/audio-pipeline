# Development and Module Rules

## Dependency direction

Allowed production dependency direction:

```text
core -> frontend / sync / aec / enhance
frontend -> dsp
sync -> aec / dsp
AEC -> dsp / arch kernels
enhance -> dsp
arch kernels -> internal data types only
platform/linux -> public core API only
```

Algorithm modules must not depend on `platform/linux`.

## Realtime rules

For `src/core`, `src/frontend`, `src/sync`, `src/aec`, `src/enhance`, `src/dsp` and `src/arch`:

- no heap allocation;
- no mutexes, file/network I/O, logging or control RPC;
- bounded loops/state only;
- no runtime plugin discovery or function-pointer backend dispatch in the 10 ms path;
- CPU model names are forbidden; depend on scalar/NEON capability only;
- architecture intrinsics live only under `src/arch/`.

Linux thread, affinity, semaphore and scheduling policy lives only under `src/platform/linux/`.

`scripts/check-architecture.sh` enforces these boundaries in CI.

## Backend rules

AEC and SIMD are compile-time selectors. New backends must implement the existing internal backend/kernel contract and add CI coverage. Do not add a new pair of `AP_ENABLE_X` / `AP_DISABLE_Y` booleans when the choice is mutually exclusive; use a string backend selector.

## Configuration rules

CPU architecture is not an algorithm configuration. Product resource class and runtime quality are separate concepts:

- resource class changes the nominal product envelope;
- FULL/LITE/SAFE reacts to runtime headroom;
- CPU-specific compiler flags belong to presets/certification records.

## Numeric policy

Precise IEEE-like compiler semantics are the default. `AP_ENABLE_FAST_MATH=ON` is opt-in and must pass the same contracts/acoustic corpus on each shipping target. Fast-math flags must never be embedded in a generic toolchain file.

## Public API changes

Before changing state layout, frame contract, enums or status behavior:

1. update `docs/API_CONTRACT.md`;
2. add/adjust a contract test;
3. verify MDF and NLMS builds;
4. verify ARMv7-A scalar and at least one NEON profile;
5. keep `AP_PIPELINE_STATE_MAX_BYTES` and alignment contracts truthful.

## Performance changes

A code change is not retained because it is theoretically faster. Use same-runner A/B for regression signals and board measurements for product claims. Never trade delay convergence, double-talk behavior or acoustic quality for a hosted benchmark result.
