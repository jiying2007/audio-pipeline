# Repository Governance

This document defines the GitHub repository policy required for `audio-pipeline` shipping releases. Workflow/release behavior is versioned in the repository; GitHub Rulesets and immutable-release enforcement are administrative repository settings and must independently match this contract.

## Main branch policy

`main` is the release integration branch.

The active branch ruleset must:

- target `main` / the default branch;
- require changes through pull requests;
- require the exact aggregate status context `summary`;
- require the branch to be up to date before merge (`strict_required_status_checks_policy=true`);
- block branch deletion;
- block non-fast-forward/force updates;
- have no bypass actors for the shipping path.

Squash merge is the canonical merge method for feature/productization work. Unresolved review conversations should block merge when reviews are used.

The active tag ruleset must target `refs/tags/v*`, block deletion and non-fast-forward updates, and have no bypass actors. Shipping release tags are exact-SHA annotated tags created by the Release workflow.

`scripts/github_governance.py` encodes the machine-readable live audit for these rules plus repository immutable-release state. An audit is PASS only when all three controls are active: main ruleset, `v*` tag ruleset and immutable releases.

## Defense in depth for direct pushes

Platform rulesets are the primary enforcement boundary. The Release workflow also fail-closes against a direct-push release: the verified main SHA must be associated with at least one merged pull request targeting `main` before packaging/tagging can proceed.

This defense does not make an unprotected `main` acceptable. A direct push could still pollute main even though Release refuses to publish it; therefore the branch ruleset remains a P0 shipping prerequisite.

## Required automated evidence

A product-code PR should not merge unless the relevant current workflows succeed. The required platform status is the single aggregate `summary` job; its implementation verifies the selected underlying domains.

### CI

- architecture contract;
- native GCC and Clang;
- strict-clang;
- sanitizers;
- fuzz-smoke;
- backend NLMS;
- backend MCRA;
- fast-math contract;
- ALSA compile;
- composition contracts including LOW/TINY/RAW/voice/module-only/FAST-resampler;
- composition-size/resource SSoT contract;
- hosted paired performance comparators, including `event.before -> HEAD` on main;
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

1. accepts only a successful push-triggered Verify on `main` and checks out that exact SHA;
2. requires merged-PR lineage for that SHA;
3. resolves `vX.Y.Z` from the project version and skips an already-published version;
4. rebuilds/tests and packages reproducible installed SDK and source archives;
5. publishes checksums, SPDX SBOM and artifact attestations;
6. creates/pushes the exact-SHA annotated `vX.Y.Z` tag when absent;
7. creates a complete draft Release, then publishes it;
8. reads the published Release and fails unless its `immutable` field is true.

Repository immutable releases must therefore be enabled **before** a new shipping version is merged. A workflow failure after publication is intentionally not treated as an acceptable mutable release.

A software Release is not a target-board product certification.

## HIL and public-repository isolation

Untrusted public pull requests never run automatically on product hardware. Trusted HIL uses isolated self-hosted `audio-target` runners and reviewed SHAs. Scheduled Nightly/Weekly and successful post-Release HIL fail visibly if `HIL_ENABLED` is not enabled; disabled hardware is missing evidence, not a successful/skipped product signal.

Formal Product Certification separates `audio-builder`, `audio-target` and `certification-archive` responsibilities. A long-lived product DUT must not also act as an arbitrary public PR build runner.

## Security

Security reporting follows `SECURITY.md`. Public vulnerability details should not be opened before coordinated disclosure when a private channel is available.

## Certification

Every shipping SKU maintains a machine-readable v4 record conforming to `certification/record.schema.json`. Real target CPU/latency/RSS/thermal/power/acoustic, exact shipping toolchain, build/deployed/executed SHA-256 equality, policy-duration route soak, attestation and lifecycle archive evidence live in product certification records, not in hosted CI claims.

The checked-in `cortex-a32-low-shipping-v1` policy requires a 72-hour soak. The policy itself is only an acceptance contract and must never be presented as a PASS result.

## Live governance state and closure prerequisite

During v1.6 assurance-closure preparation, the repository API reported no active Rulesets and the v1.5.0 Release reported `immutable=false`. Those are historical observations explaining why governance remains a platform-level closure prerequisite rather than a documentation-only recommendation.

Before v1.6 is merged for release, repository administrators must make the live `scripts/github_governance.py` audit pass by enabling the required main/tag rulesets and repository immutable releases. The current ChatGPT GitHub connector exposes these administrative controls as read-only, so repository code cannot truthfully self-enable them.

## Repository lifecycle state machine

Research evidence, one-way validation qualification, immutable release lineage,
post-release laboratory states, and evidence-bound branch garbage collection are
specified in `docs/REPOSITORY_LIFECYCLE.md`. Research branches are not evidence
archives: terminal evidence must be sealed in the registry/artifacts before a
branch can become GC-eligible.
