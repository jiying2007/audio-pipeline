# Repository lifecycle

This document defines the **technical research** repository lifecycle: source hypotheses, independent validation, protected merges, separately authorized physical experiments and immutable historical evidence. Commercial release and product-certification instructions are archived provenance only; see [research execution](RESEARCH_ONLY_EXECUTION.md).

## Research lifecycle

Research branches are temporary execution surfaces, not durable evidence stores. Durable lineage lives in `.github/research/evidence-index.json`.

Allowed lifecycle states are `ACTIVE`, `ACCEPTED`, `REJECTED`, `SUPERSEDED`, `ABANDONED`, and `UNCLASSIFIED`. Only terminal records with an exact branch-head SHA and sealed evidence may be marked `gc_eligible`. Automatic GC additionally requires `auto_gc=true`, a live branch SHA that still matches the registry, and no open pull request.

`Research Branch GC` is fail-closed. A protected-main merge may automatically remove only exact registry entries marked `auto_gc`; any SHA drift or open PR blocks the apply transaction before deletion. Manual apply requires the explicit confirmation string `DELETE_GC_ELIGIBLE_REFS`.

## Validation-authority qualification

One-way holdout qualification uses `Validation Authority Qualification`. The caller provides an exact 40-hex candidate SHA and acknowledges `ONE_WAY_HOLDOUT`. The workflow freezes a fingerprint over the canonical evaluator, exact correlation backend, hosted-AEC policy, and dataset lock before calling the reusable Hosted Real AEC workflow against that exact SHA.

An acoustic holdout failure rejects the candidate. Threshold, search, or metric tuning from holdout feedback is forbidden. Compiler/import/infrastructure wiring failures may be corrected without changing the frozen acoustic candidate semantics.

Normal pull-request, main-push, and scheduled Hosted Real AEC validation remain unchanged.

## Research change and source identity

`scripts/ci_impact.py` selects the appropriate validation graph. Every
research PR must bind an exact head SHA, pass required `Verify/summary`, merge
through protected main and retain a distinct fresh-main result. A passing
source check is not a commercial publication or acoustic/physical PASS.
Changes to public API/ABI, corpus roles, independent evaluator or runner
constraints require full applicable regression coverage rather than a tag.

## Historical release provenance

The old `scripts/prepare_release.py` and `scripts/release_manifest.py`
describe historical version and archive preparation, not current research
execution commands. Git tags, past published immutable Releases, SBOMs,
`CHANGELOG.md` and `docs/releases/*` remain available solely to reconstruct
their original source, toolchain and artifact identities. Active automatic
GitHub Release and product-certification workflows are retired. Do not create
a new version/SDK or reinterpret a historical certificate because a research
PR or main Verify succeeds.

## Independently authorized physical experiments

Extended Real validation is bound to the specific lawful source/dataset
and actual runner environment. HIL uses a separately requested, exact-source
manual experiment on a real isolated audio-target board, with preflight,
measurement duration and sealed source/evidence receipts.
`READY` describes infrastructure only; `BLOCKED_RUNNER`,
`BLOCKED_CONFIG`, `NOT_RUN` and `FAIL` are never coerced to PASS.
A voluntary `research-72h` measurement does not become product
certification, and previous post-release summaries remain historical.

## Evidence retention versus branch retention

Deleting a terminal research branch does not delete its commit objects immediately and does not remove referenced Actions artifacts, pull-request discussions, release assets, immutable tags, or registry lineage. Branch names are therefore not used as the long-term evidence authority.


When GitHub's `delete_branch_on_merge` removes a merged ref, the registry must still retain the exact PR head SHA and closeout evidence. Do not set `head_sha` to null or leave a completed leaf `ACTIVE` merely because its remote branch is absent. Closeout evidence must identify the protected merge SHA, fresh-main Verify, and any required independently read-back artifact receipt. Remove the matching `active_dependencies` entry only after the leaf is actually closed and those identities are recorded. If GitHub already deleted the ref, keep `auto_gc=false`; `gc_eligible=true` records terminal eligibility without scheduling another deletion.
