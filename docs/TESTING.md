# Test Intelligence and HIL Policy

This document is the normative test-routing and hardware-validation policy for `audio-pipeline`.

## Fast Gate and Full Gate

Pull requests enter a mandatory Fast Gate before expensive reusable workflows are expanded. The Fast Gate runs architecture checks, Python tool self-tests, strict Clang build, unit/contract/property tests and additive ABI checks when public/runtime ABI is impacted.

Documentation-only changes run a whitespace/impact self-check and do not compile DSP code. Any unknown path, public header, build-system file, workflow file, test-infrastructure file or unclassified core source conservatively expands to the full matrix. A `main` push always forces full verification regardless of impact selection.

The Full Gate retains `fail-fast: false` for diagnostic matrices so one failing architecture or composition does not hide independent failures. The final `summary` job is the single aggregate merge/release status and verifies that every expected domain succeeded and every non-selected domain was actually skipped.

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

`.github/workflows/ci-toolchain-image.yml` is the permanent rebuild path. It builds and smoke-tests the image before publishing SHA and `ci-latest` tags, then prints the digest that must be reviewed and pinned in normal workflows. Normal CI must not use mutable tags.

`ccache` is persisted through GitHub cache with a key bound to runner OS, job/compiler namespace and CMake/header hashes. Build directories, test results, credentials, certification records and product evidence are never restored from cache.

## Failure taxonomy and reproducer artifacts

`scripts/ci_failure.py` emits a stable machine-readable taxonomy including build, ABI, unit, sanitizer, DSP-quality, performance, resource, QEMU, HIL, XRUN, infrastructure, evidence and security failures.

Acoustic validation always writes its report before enforcement. On failure, `scripts/validation_reproducer.py` packages the exact failed case inputs, local case JSON, metrics/failure data and an executable `reproduce.sh`. These artifacts are retained independently of ordinary console logs.

## Flaky and historical-regression policy

Nightly `flaky-sentinel` builds once and replays the deterministic suite 100 times. A mixed pass/fail sequence is reported as `FLAKY_SUSPECT`; the current hard budget is 2%. Failures are not silently retried into a pass.

Nightly `historical-trend` stores revision-bound benchmark and validation points. `scripts/test_history.py` compares the current point with successful main history using median/MAD robust statistics plus a relative-change threshold. This catches slow CPU/latency/acoustic drift that may remain inside a single absolute gate.

## Metamorphic/property contracts

`tests/test_metamorphic.c` validates invariants that do not require a golden waveform, including deterministic reset/replay, stable silence behavior and topology invariants. These run in normal CTest and therefore participate in Fast Gate, sanitizers and other applicable builds.

## HIL board contract

Every self-hosted product board uses labels `[self-hosted, linux, audio-target]` and a board-local manifest, normally `/etc/audio-pipeline/board.json`, conforming to `hil/board.schema.json`. The manifest binds stable board/revision/SoC/codec/microphone/speaker identity, thermal/power inputs, optional reset/cleanup hooks and the default product audio route.

`tools/hil_board.py preflight` runs before DSP measurement and records board identity, kernel/machine, disk, thermal state, CPU governors, NTP state and ALSA inventory. Lab/setup faults are classified as `INFRA_FAILURE`, not product regressions. Cleanup always runs and evidence is SHA-256 sealed.

## Tiered soak and fault injection

`.github/workflows/hil-soak.yml` supports:

| Tier | Duration | Fault profile | Purpose |
| --- | ---: | --- | --- |
| accelerated-pr | 10 min | accelerated | trusted PR/reproduction, route restart/render gap/CPU stall |
| nightly-1h | 1 h | none | recurring product route health |
| release-8h | 8 h | none | post-release exact-SHA product route validation |
| weekly-24h | 24 h | none | long stability trend |
| certification-72h | 72 h | none | extended release/SKU evidence |

Because this is a public repository, untrusted pull requests never automatically execute on self-hosted product hardware. `accelerated-pr` is manually dispatched against a reviewed SHA.

Scheduled Nightly/Weekly and post-Release HIL are gated by repository variable `HIL_ENABLED=true`. With the variable absent/false, those jobs are skipped instead of queueing against nonexistent hardware. Once a board farm is online, each runner's local manifest supplies its route; adding a board does not require cloning the workflow.

Fault injection is intentionally enabled only for accelerated testing. Product certification and nominal performance evidence use the normal route with no synthetic fault profile.

## Evidence boundary

Hosted x86, cross-build and QEMU results are software correctness/regression evidence only. They are never relabeled as Cortex-A32 product performance or acoustic certification. Product certification still requires real shipping hardware, shipping compiler/sysroot, product audio route, acoustic corpus/results, thermal/power data and required soak evidence.
