# Test Intelligence and HIL Policy

This document is the normative test-routing and hardware-validation policy for `audio-pipeline`.

## Fast Gate and Full Gate

Pull requests enter a mandatory Fast Gate before expensive reusable workflows are expanded. The Fast Gate runs architecture checks, Python tool self-tests, strict Clang build, unit/contract/property tests and additive ABI checks when public/runtime ABI is impacted.

Documentation-only changes run a whitespace/impact self-check and do not compile DSP code. Any unknown path, public header, build-system file, workflow file, test-infrastructure file or unclassified core source conservatively expands to the full matrix. A `main` push always forces full verification regardless of impact selection.

The Full Gate retains `fail-fast: false` for diagnostic matrices so one failing architecture or composition does not hide independent failures. The final `summary` job is the single aggregate merge/release status and verifies that every expected domain succeeded and every non-selected domain was actually skipped.

FULL includes paired performance comparison. Pull requests compare `origin/main -> candidate`; main push verification compares the exact pre-push `event.before -> HEAD`. Main is not exempt from the hosted performance gate.

## Change-aware test selection

`scripts/ci_impact.py` owns the explicit dependency map. It can select:

- composition presets relevant to AEC, NS, resampling and activity/VAD changes;
- Arm cross profiles relevant to DSP/runtime changes;
- NLMS or MCRA alternate backend contracts;
- performance comparison, ALSA compile, ABI, extended sanitizer/QEMU/resource work;
- acoustic validation for validation/certification changes.

The selector is an optimization layer, never a correctness authority. Unknown inputs expand to FULL.

## Reproducible CI toolchain

Heavy ARM/QEMU/ALSA/static-analysis jobs use a GHCR toolchain image by immutable digest. The image contains GCC/Clang, CMake/Ninja, ccache, ARM/AArch64 cross compilers plus cross libc headers, QEMU user emulation, ALSA development/runtime tools, gcovr and scan-build.

`.github/workflows/ci-toolchain-image.yml` is the permanent rebuild path. It builds and smoke-tests the image before publishing SHA and `ci-latest` tags, then prints the digest that must be reviewed and pinned in normal workflows. Normal heavy CI must not use mutable container tags.

`ccache` is persisted through GitHub cache with a key bound to runner OS, job/compiler namespace and CMake/header hashes. Build directories, test results, credentials, certification records and product evidence are never restored from cache.

## Failure taxonomy and reproducer artifacts

`scripts/ci_failure.py` emits a stable machine-readable taxonomy including build, ABI, unit, sanitizer, DSP-quality, performance, resource, QEMU, HIL, XRUN, infrastructure, evidence and security failures.

Acoustic validation always writes its report before enforcement. On failure, `scripts/validation_reproducer.py` packages the exact failed case inputs, local case JSON, metrics/failure data and an executable `reproduce.sh`. These artifacts are retained independently of ordinary console logs.

## Flaky and historical-regression policy

Nightly `flaky-sentinel` builds once and replays the deterministic suite 100 times. A mixed pass/fail sequence is reported as `FLAKY_SUSPECT`; the current hard budget is 2%. Failures are not silently retried into a pass.

Nightly `historical-trend` stores revision-bound benchmark and validation points. `scripts/test_history.py` can begin robust median/MAD regression detection after five comparable samples, but the output remains explicitly `WARMING_UP` until every current metric has at least 30 historical samples. Only then is its maturity status `MATURE`.

`PASS` and `MATURE` are intentionally separate concepts: a warming trend may pass today's regression check, but it is not evidence that the long-running statistical gate has accumulated enough operating history. The v1.6 closure therefore does not claim historical-trend operational maturity merely because the framework exists.

## Metamorphic/property contracts

`tests/test_metamorphic.c` validates invariants that do not require a golden waveform, including deterministic reset/replay, stable silence behavior and topology invariants. These run in normal CTest and therefore participate in Fast Gate, sanitizers and other applicable builds.

## Resource single source of truth

Representative hosted pipeline/runtime state measurements are generated into [`ci/resource-baseline.json`](../ci/resource-baseline.json) and [`docs/generated/RESOURCE_BASELINE.md`](generated/RESOURCE_BASELINE.md). Resource Gate regenerates those files from the current hosted GCC Release measurement and fails if the checked-in baseline is stale. Other documentation must link to that generated view rather than copying numeric values.

## Trusted runner readiness

Trusted self-hosted labels route jobs but do not prove that the underlying machine is ready. `tools/runner_preflight.py` defines a shared fail-closed infrastructure contract for `audio-validation`, `audio-builder`, `audio-target` and `certification-archive`. The manually dispatched **Trusted Runner Readiness** workflow runs that contract against an exact source ref before long-running lab work. Its JSON result is `READY` or `NOT_READY`; `READY` is infrastructure readiness only and is never acoustic, HIL, performance or product-certification evidence.

The runner-preflight self-test executes in the required hosted Fast Gate. Compact/Full public validation and HIL also execute the applicable preflight inside their real self-hosted jobs so a stale manual readiness result cannot bypass the workflow-local prerequisite check. Cross-role activation and invalidation rules are documented in [`TRUSTED_RUNNERS.md`](TRUSTED_RUNNERS.md).

## HIL board contract

Every self-hosted product board uses labels `[self-hosted, linux, audio-target]` and a board-local manifest, normally `/etc/audio-pipeline/board.json`, conforming to `hil/board.schema.json`. The manifest binds stable board/revision/SoC/codec/microphone/speaker identity, thermal/power inputs, optional reset/cleanup hooks and the default product audio route.

`tools/hil_board.py preflight` runs before DSP measurement and records board identity, kernel/machine, disk, thermal state, CPU governors, NTP state and ALSA inventory. Lab/setup faults are classified as `INFRA_FAILURE`, not product regressions. Cleanup always runs and evidence is SHA-256 sealed.

## Tiered soak and fault injection

`.github/workflows/hil-soak.yml` supports:

| Tier | Duration | Fault profile | Purpose |
| --- | ---: | --- | --- |
| accelerated-pr | 10 min | accelerated | trusted PR/reproduction, route restart/render gap/CPU stall |
| nightly-1h | 1 h | none | recurring product route health |
| release-8h | 8 h | none | post-release exact-SHA engineering route validation |
| weekly-24h | 24 h | none | long stability trend |
| certification-72h | 72 h | none | extended engineering/SKU route evidence |

Because this is a public repository, untrusted pull requests never automatically execute on self-hosted product hardware. `accelerated-pr` is manually dispatched against a reviewed SHA.

Scheduled Nightly/Weekly and successful post-Release HIL require repository variable `HIL_ENABLED=true`. If hardware is not enabled, the availability job fails visibly with `HIL_REQUIRED_BUT_DISABLED`; the workflow no longer silently skips and leaves a misleading green/empty evidence trail. Set the variable only after an isolated `audio-target` runner and valid board manifest are actually online.

Fault injection is intentionally enabled only for accelerated testing. Product certification and nominal performance evidence use the normal route with no synthetic fault profile.

## Shipping certification topology

Formal Product Certification is separate from ordinary HIL tiering:

```text
audio-builder
  exact compiler + sysroot + C flags + reviewed SKU CMake args
        |
        | sealed shipping artifact + build provenance
        v
audio-target DUT
  verify -> deploy -> benchmark -> real route soak -> execute
        |
        | build == deployed == executed SHA-256
        v
attested certification bundle
        |
        v
certification-archive
  immutable product-lifecycle storage + receipt
```

The builder and DUT must be different runners. The formal checked-in Cortex-A32 LOW shipping policy requires a 72-hour route soak. Actions artifacts with 7/90-day retention are transport/cache only; lifecycle acceptance requires a separately validated immutable archive receipt.

## Evidence boundary

Hosted x86, cross-build and QEMU results are software correctness/regression evidence only. They are never relabeled as Cortex-A32 product performance or acoustic certification. A shipping policy is also not a PASS result. Product certification requires real shipping hardware, exact shipping toolchain identity, exact deployed binary identity, product audio route, real acoustic corpus/results, thermal/power data, policy-duration soak evidence, cryptographic attestation and lifecycle archive evidence.