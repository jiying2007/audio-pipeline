# Test Intelligence and HIL Policy

This document is the normative test-routing and hardware-validation policy for `audio-pipeline`.

## Fast Gate and Full Gate

Pull requests enter a mandatory Fast Gate before expensive reusable workflows expand. The Fast Gate runs architecture/hard-cut checks, Python tool self-tests, strict Clang build, unit/contract/property tests and the v2 ABI gate when public/runtime ABI is impacted.

Documentation-only changes run a whitespace/impact self-check. Any unknown path, public header, build-system file, workflow file, test-infrastructure file or unclassified core source conservatively expands to the full matrix. A `main` push always forces full verification.

The Full Gate retains `fail-fast: false` for diagnostic matrices. Required `summary` is the single aggregate merge/release status and verifies every expected domain succeeded and every non-selected domain was actually skipped.

FULL includes paired performance comparison: pull requests compare `origin/main -> candidate`; main push verification compares exact `event.before -> HEAD`.

## v2 API/ABI hard-cut gate

The initial 2.0.0 gate is intentionally not additive against 1.x. It requires the terminal v2 symbols and rejects removed 1.x runtime/build-info symbols, types and compatibility headers. Current certification schema must be v4-only.

After the immutable `v2.0.0` tag exists, subsequent 2.x ABI checks use v2.0.0 as their released compatibility baseline. This prevents compatibility residue from returning while restoring normal same-major ABI protection.

## Change-aware test selection

`scripts/ci_impact.py` owns the explicit dependency map. It can select composition presets, Arm profiles, alternate AEC/NS backends, performance/ALSA/ABI/extended sanitizer/QEMU/resource work and acoustic validation. The selector is an optimization layer, never a correctness authority; unknown inputs expand to FULL.

## Reproducible CI toolchain

Heavy ARM/QEMU/ALSA/static-analysis jobs use the reviewed GHCR toolchain image by immutable digest. `ccache` persists compiler objects only. Build directories, test results, credentials, certification records and product evidence are never restored from cache.

## Deterministic regression and public validation

PR/main audio-quality regression uses deterministic generator v3 and seeds `1307`, `2307`, `3307`. Each seed generates 27 cases and must pass 27/27 under the regression policy; deterministic regeneration is hash-compared.

This 81-case generated suite is regression evidence only. Public validation remains separately materialized/sealed on trusted `audio-validation` runners using Compact 100 / Full 160 profiles and optional HMAC blind holdout. Product certification remains a still higher trust tier.

## Failure taxonomy and reproducer artifacts

`scripts/ci_failure.py` emits stable machine-readable build, ABI, unit, sanitizer, DSP-quality, performance, resource, QEMU, HIL, XRUN, infrastructure, evidence and security categories.

Acoustic validation writes its report before enforcement. On failure, `scripts/validation_reproducer.py` packages exact failed inputs, case JSON, metrics/failure data and executable reproduction instructions.

## Flaky and historical-regression policy

Nightly `flaky-sentinel` replays the deterministic suite 100 times. A mixed pass/fail sequence is `FLAKY_SUSPECT`; failures are not silently retried into a pass.

Nightly history can begin median/MAD regression detection after enough comparable samples, but maturity remains `WARMING_UP` until every current metric has at least 30 historical points. `PASS` and `MATURE` are separate concepts.

## Metamorphic/property contracts

`tests/test_metamorphic.c` validates deterministic reset/replay, stable silence and topology invariants. These participate in normal CTest and applicable sanitizer/build matrices.

## Resource single source of truth

Representative hosted pipeline/runtime state measurements live in [`ci/resource-baseline.json`](../ci/resource-baseline.json) and generated [`docs/generated/RESOURCE_BASELINE.md`](generated/RESOURCE_BASELINE.md). Resource Gate remeasures/regenerates both and fails on drift; current docs do not duplicate the numbers.

## Trusted runner readiness

`tools/runner_preflight.py` defines fail-closed readiness for `audio-validation`, `audio-builder`, `audio-target` and `certification-archive`. The manually dispatched **Trusted Runner Readiness** workflow runs that contract against an exact source ref. `READY` means infrastructure readiness only and is never acoustic, HIL, performance or product-certification evidence.

Compact/Full validation and HIL repeat the applicable preflight inside their real self-hosted jobs so a stale manual readiness result cannot bypass local prerequisites. See [`TRUSTED_RUNNERS.md`](TRUSTED_RUNNERS.md).

## HIL board contract

Product boards use `[self-hosted, linux, audio-target]` plus a board-local manifest, normally `/etc/audio-pipeline/board.json`, conforming to `hil/board.schema.json`. It binds stable board/revision/SoC/codec/microphone/speaker identity, sensor inputs, optional reset/cleanup hooks and default product route.

`tools/hil_board.py preflight` records board/kernel/machine/disk/thermal/governor/NTP/ALSA state. Setup faults are `INFRA_FAILURE`, not product regressions. Cleanup always runs and evidence is SHA-256 sealed.

## Tiered soak and fault injection

| Tier | Duration | Fault profile | Purpose |
| --- | ---: | --- | --- |
| accelerated-pr | 10 min | accelerated | reviewed PR/reproduction |
| nightly-1h | 1 h | none | recurring product route health |
| release-8h | 8 h | none | post-release exact-SHA engineering validation |
| weekly-24h | 24 h | none | long stability trend |
| certification-72h | 72 h | none | shipping certification minimum for the checked-in LOW policy |

Untrusted public PRs never automatically execute on product hardware. Scheduled/Release HIL requires `HIL_ENABLED=true`; if policy expects hardware but it is disabled, availability **fails visibly** / is **fail-visible** with `HIL_REQUIRED_BUT_DISABLED` rather than silently skipping.

Fault injection is reserved for accelerated engineering testing. Product certification and nominal performance evidence use the normal route without synthetic fault profiles.

## Shipping certification topology

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

The builder and DUT must be different runners. Current certification accepts schema v4 only. The checked-in Cortex-A32 LOW shipping policy requires 72 hours. Actions artifacts are transport/cache; lifecycle acceptance requires the separately validated immutable archive receipt.

## Evidence boundary

Hosted x86, generated regression, cross-build and QEMU signals are software evidence only. They are never relabeled as Cortex-A32 product performance or shipping acoustic certification. A shipping policy is not a PASS result. Product certification requires real hardware, exact shipping toolchain/deployed identity, product route, real acoustic results, thermal/power data, policy-duration soak, attestation and lifecycle archive evidence.
