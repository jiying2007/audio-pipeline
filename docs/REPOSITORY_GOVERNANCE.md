# Research repository governance

**Current scope: reproducible technical DSP, AFE and embedded-resource research.** This page describes protection of source, experimental evidence, GitHub CI and contributor review. The former product-release procedure is archived in Git history, not an active execution or acceptance rule. See [research-only execution](RESEARCH_ONLY_EXECUTION.md).

## Protected main

`main` is the integration branch for reviewed technical research. The GitHub ruleset must:

- require pull requests and **squash-only** merge;
- require current `summary` status from GitHub Actions, with strict up-to-date comparison;
- require unresolved review conversations to be resolved when applicable;
- block branch deletion, force and non-fast-forward updates;
- have **no bypass actors**;
- enable `delete_branch_on_merge=true` for merged same-repository branches.

`scripts/research_github_governance.py` audits these properties against the live branch ruleset and repository settings. A failure is visible and never converted to PASS. `scripts/bootstrap_github_governance.py` is an optional, explicitly administrative main-ruleset restoration tool; it does not create product Release artifacts, publish tags or alter immutable-Release settings. The matching workflow checks source contracts on PRs; a manual administrative restore requires a scoped credential and is not a normal research gate.

Existing historical tags, already published archives, original commit identities and rights documentation are not deleted or rewritten. Their existence does **not** create a current commercial admission requirement.

## Scientific CI acceptance

The protected `summary` check aggregates the applicable job graph, not just a filename or a job that happens to be skipped. Changes must preserve the required checks selected by the conservative impact analyzer:

- GCC/Clang native builds, installed C SDK and ABI consumer contracts;
- sanitizers, thread safety, fuzz smoke, static analysis and coverage;
- ARM/Cortex-A32 cross builds, QEMU portability and configured resource ceilings;
- audio front-end BF/AEC/RES/NS/AGC/VAD regressions, acoustic experiment roles and source-rights verification;
- source-/artifact-SHA reproducibility, exact held-out replay and failure receipts;
- manual HIL/physical-target measurements only when the actual devices, consented audio and proper isolation are available.

Hosted x86, synthetic audio, QEMU or skipped physical jobs cannot be described as actual SSC305 CPU/power, far-field FAR/FRR, thermals or field qualification. Unknown source paths continue to receive conservative CI. No historical product policy can mint a present research PASS.

## Versioning and dependency updates

`CMakeLists.txt`, `CHANGELOG.md` and build-info version remain synchronized for source/API compatibility. Version increments may still be required by conservative source/ABI change governance, but they are **not automatic GitHub Releases** or proof of model/device readiness.

Dependabot updates only propose changes. GitHub Actions pins, build images, C toolchain dependencies, Ansible laboratory requirements and experiment sources must be reviewed according to their actual effect on source determinism, security, reproducibility, protected data and hardware safety. Preserve exact dependency pins where necessary; never weaken an acoustic gate to solve a CI download issue.

## Data rights and independent evidence

Third-party software, corpus and voice licenses remain binding, including research-only/noncommercial limitations. Record source/revision, original file hash, authorized purpose, speaker-consent scope where relevant, train/calibration/evaluation separation and real-hardware evidence. Unavailable data is `NOT_RUN`/`BLOCKED`, never inferred PASS.

The repository keeps immutable historical results, failed studies and scientific research artifacts. An ordinary research PR does not require shipping approval, a commercial SKU, a GitHub Release, a 72-hour product soak, product certification, or administrator-read release credentials.

## Operations and incident boundaries

Protect physical runners against untrusted pull requests and require an exact reviewed source SHA for manual HIL. Maintain device-specific source, environment, raw input/output, CPU/RSS/I/O and power measurements as research data only. Follow `SECURITY.md` for vulnerability handling and [repository lifecycle](REPOSITORY_LIFECYCLE.md) for branch/evidence retention. Deleting a merged branch never deletes the historical Git commit, source review or stored experiment receipts.
