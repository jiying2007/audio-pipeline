# Repository Governance

This document defines the intended GitHub repository policy for `audio-pipeline`. Workflow/release behavior is versioned in the repository; GitHub Ruleset/branch-protection enforcement is an administrative repository setting and must match this contract.

## Main branch policy

`main` is the release integration branch.

Required policy:

- changes arrive through pull requests;
- direct force-push is disabled;
- branch deletion is disabled;
- pull requests must be up to date with required checks before merge;
- squash merge is the canonical merge method for feature/productization work;
- required CI and Quality checks must pass;
- unresolved review conversations block merge when reviews are used.

The repository currently keeps historical `feat/*` refs aligned to `main` when deletion is unavailable. Those refs must not diverge after their work is merged.

## Required automated evidence

A product-code PR should not merge unless the relevant current workflows succeed.

### CI

- architecture-contract;
- native GCC and Clang;
- strict-clang;
- sanitizers;
- fuzz-smoke;
- backend-nlms;
- backend-ns-mcra;
- fast-math-contract;
- ALSA compile;
- composition contracts including LOW/TINY/RAW/voice/module-only/FAST-resampler;
- composition-size-contract;
- hosted paired performance comparators;
- ARM cross-build matrix.

### Quality

- installed SDK consumer through CMake package and pkg-config;
- SKU pipeline/runtime RAM and final consumer ELF pruning;
- ThreadSanitizer runtime ownership;
- Cortex-A7 NEON and AArch64 QEMU executable contracts;
- source line coverage gate;
- clang static analyzer;
- acoustic-eval harness contract.

Hosted performance/QEMU signals do not substitute for board certification.

## Version and release

`CMakeLists.txt` project version is the release source of truth. `CHANGELOG.md` and `ap_build_info()` must match it.

When a new project version reaches `main`, `.github/workflows/release.yml`:

1. resolves `vX.Y.Z` from the project version;
2. skips if a GitHub Release for that version already exists;
3. creates/pushes the annotated tag when absent;
4. rebuilds and tests the release SDK;
5. packages installed SDK and source archives;
6. publishes SHA256 checksums;
7. creates the GitHub Release.

A software Release is not a target-board product certification.

## Security

Security reporting follows `SECURITY.md`. Public vulnerability details should not be opened before coordinated disclosure when a private channel is available.

## Certification

Every shipping SKU maintains a machine-readable record conforming to `certification/record.schema.json`. Real target CPU/latency/RSS/thermal/power/acoustic/8 h soak evidence lives in product certification records, not in hosted CI claims.

## Ruleset audit

Repository administrators should periodically compare the active GitHub Ruleset/branch protection against this file. If platform enforcement is unavailable, this document remains the normative desired policy but must not be described as enforced.
