# Development and Module Rules

## Dependency direction

Allowed production dependency direction:

```text
core -> frontend / sync / aec / enhance
frontend -> dsp
sync -> dsp
AEC -> dsp / arch kernels
enhance -> dsp
arch kernels -> dsp data types only
platform/linux -> public core API only
```

Sibling DSP stages do not include or call each other's private contracts. In particular, synchronization reports route-jump events to core; only core decides whether to reset AEC. Algorithm modules must not depend on `platform/linux`.

## State ownership and contracts

`src/core/ap_pipeline_internal.h` is the only composite-state definition. Each DSP domain owns a private state type and a narrow private contract in its own directory:

- `ap_frontend_state_t` owns HPF/beamformer history;
- `ap_sync_state_t` owns render history, delay and drift state;
- `ap_aec_state_t` owns the selected MDF/NLMS backend state;
- `ap_enhance_state_t` owns RES/NS/AGC/VAD history.

Non-core DSP modules must not receive or reference `ap_pipeline_t`, `ap_config_t` or `ap_metrics_t`. They receive only the samples/scalars they need and return small event/result/status structures. Public telemetry is aggregated exactly once by core.

Do not introduce a repository-wide catch-all internal header. Module-private headers may expose only the state/types/functions required by core or a lower dependency layer. Avoid duplicating the public configuration inside module state unless the value is genuinely persistent algorithm state and the memory/performance trade is measured.

## Realtime rules

For `src/core`, `src/frontend`, `src/sync`, `src/aec`, `src/enhance`, `src/dsp` and `src/arch`:

- no heap allocation;
- no mutexes, file/network I/O, logging or control RPC;
- bounded loops/state only;
- no runtime plugin discovery or function-pointer backend dispatch in the 10 ms path;
- CPU model names are forbidden; depend on scalar/NEON capability only;
- architecture intrinsics live only under `src/arch/`.

Linux thread, affinity, semaphore and scheduling policy lives only under `src/platform/linux/`.

`scripts/check-architecture.sh` enforces state ownership, dependency direction and realtime boundaries in CI.

## Backend rules

AEC and SIMD are compile-time selectors. New backends implement the existing private AEC/kernel contract and add CI coverage. Do not add a new pair of `AP_ENABLE_X` / `AP_DISABLE_Y` booleans when the choice is mutually exclusive; use a string backend selector.

A backend must not reach through core to another stage. Cross-stage effects are represented as results/events and interpreted by core.

## Configuration rules

CPU architecture is not an algorithm configuration. Product resource class and runtime quality are separate concepts:

- resource class changes the nominal product envelope;
- FULL/LITE/SAFE reacts to runtime headroom;
- CPU-specific compiler flags belong to presets/certification records.

Module code should consume narrow parameters rather than the complete public `ap_config_t` object.

## Numeric policy

Precise IEEE-like compiler semantics are the default. `AP_ENABLE_FAST_MATH=ON` is opt-in and must pass the same contracts/acoustic corpus on each shipping target. Fast-math flags must never be embedded in a generic toolchain file.

## Public API changes

Before changing state layout, frame contract, enums or status behavior:

1. update `docs/API_CONTRACT.md`;
2. add/adjust a contract test;
3. verify MDF and NLMS builds;
4. verify ARMv7-A scalar and at least one NEON profile;
5. keep `AP_PIPELINE_STATE_MAX_BYTES` and alignment contracts truthful.

Private module refactors must preserve public behavior unless the API change is deliberate and separately documented.

## Verification for module refactors

A module-boundary change is complete only when:

1. `scripts/check-architecture.sh` passes;
2. default and NLMS tests pass under strict warnings and sanitizers;
3. all Arm cross profiles compile;
4. `state_bytes` does not silently grow;
5. active/idle, NS, resampler and runtime same-runner gates do not show a clear regression;
6. delay/ERLE/RES/double-talk telemetry remains behaviorally equivalent.

## Performance changes

A code change is not retained because it is theoretically faster. Use same-runner A/B for regression signals and board measurements for product claims. Never trade delay convergence, double-talk behavior or acoustic quality for a hosted benchmark result.
