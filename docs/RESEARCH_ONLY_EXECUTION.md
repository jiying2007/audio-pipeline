# Technical-research execution boundary

**Status: research execution is separated from retired publication and governance protocols.** [Issue #882](https://github.com/jiying2007/audio-pipeline/issues/882) is the completed migration record, not an open research-admission gate. Exact commit and CI evidence determine each subsequent cleanup result; historical words, license conditions and receipts are not new commercial authority.

## Active research authority

The subject of this repository is reproducible low-resource speech DSP and audio front-end engineering: BF (1/2/4 microphones), AEC, RES, NS, AGC, VAD, transport/runtime timing, fixed-memory pipelines, acoustic regressions and ARM/SSC305-class resource experiments. Research runs are admitted by recorded sources/rights, roles and immutable measurements, not by sales readiness, shipping SKU approval, a GitHub Release, product certification or a 72-hour physical board soak.

The normal PR/main `Verify` gate is for code correctness, sanitizers, resource/performance diagnostics, cross-architecture build portability, reproducibility and validation. It must not execute or require `certification/` policy assertions, commercial signing credentials, `shipping_approved` or a release/tag prerequisite. `tests/test_research_ci_boundary.py` checks this contract on each docs gate. This is a *necessary first step*, not sufficient evidence that all obsolete launch surfaces are retired.

## Evidence that remains valuable

- Preserve existing immutable scientific results, regression replay, data rights and source/hash receipts; never manufacture or silently upgrade real-person, final AFE, hardware, thermal or power evidence.
- Keep experimental SSC305-style build and CPU/RSS/latency/energy measurements as research resource profiles. QEMU/host estimates must be distinguished from physical DUT data.
- Maintain blind and independent evaluation roles and truthful NOT_RUN/FAIL signals. An empty or skipped target experiment must never be recast as PASS.
- Historical `release.yml` and `post-release-qualification-summary.yml` have been retired from the active workflow directory in this change. Their source and previous results remain available in Git history and GitHub Actions history. `product-certification.yml` is also retired from active Actions, while archived `certification/` source, schema, and historical receipts remain for provenance review and source-only negative tests; they are not research-admission authority. No historical audit payload is rewritten.

## Archived commercial documentation is not current CI authority

The old `docs/PRODUCT_ASSURANCE.md`, `docs/PRODUCT_ASSURANCE.zh-CN.md`,
`certification/README.md` and `certification/policies/README.md`
remain available as **archived commercial documentation** for source and
decision provenance. The ordinary `scripts/docs_consistency.py` gate no longer
requires their presence, validates their old commercial assertions, or regards
their historical SKU/release values as current research prerequisites. Current
bilingual navigation may link to the archive *as history*, not a live
certification workflow. A negative research CI test prevents re-adding these
files as current documentation requirements.

This does not remove original measurement evidence, third-party license
obligations, historic Git commits or archived certification receipts. Actual
research correctness/resource/HIL evidence continues to be tested on its own
terms. No archived state creates a new product or hardware PASS.

## Retired orphaned product-program executables (2026-11-05)

A complete inspection of the 70 current GitHub Actions workflow files found no
caller for the historical `.github/program/existing_release_identity.py`,
`p002_candidate_zero_audit.py`, `product_soak_observed_duration.py` or
`test_product_soak_observed_duration.py`. Those files could only reconstruct
retired publication identity and fixed 72-hour product soak decisions; the P002
audit depended on the now-absent `release.yml`. Their active-tree copies are
retired, while original Git commits and previous evidence remain unchanged.

Current `.github/program/maintenance_workflow_contract.py` describes only
source-bound research maintenance, and the required research boundary test
rejects reintroducing old product executables or wiring them into Actions.
Physical HIL/readiness, exact real elapsed duration and immutable experimental
source evidence continue through separate research controls. This cleanup
does not claim real device qualification or rewrite historical release results.

## Scope of completion and retained history

Active research commands, required CI, data preparation and algorithm evaluation must not require commercial publication, SKU approval or hypothetical commercial licensing. Legacy certificates and documents are explicit historical records, not new research authority. Original source rights, including noncommercial conditions, still apply. Frozen experiment bytes and release/attestation schemas are not renamed or re-signed to satisfy a text search. Retain Python 3.8 compatibility where used; require exact-head CI and fresh protected-main verification for each change.

## Protected research-main governance (2026-11-05)

Current repository administration no longer uses the retired product-release governance launcher. The optional `.github/workflows/repository-governance-bootstrap.yml` manual administrative job restores **only** the existing main-branch PR/status ruleset. `scripts/bootstrap_github_governance.py` does not create tags, configure immutable GitHub Releases or grant publication status. The required offline and optional live `scripts/research_github_governance.py` audit verifies strict source/CI `summary`, squash PR-only merges, review-thread resolution, no bypass/force/delete and `delete_branch_on_merge`. Historical Git tags and released archives remain preserved without becoming current research gates.

No changed ruleset is applied automatically by this source migration. A manual operator action still requires explicit scoped repository administration. CI tests reject the return of active commercial release administration while keeping exact-head protected-main checks.

## Default language and admission

The EN/ZH root README files describe only technical algorithm, data-source,
resource and independent test authority. Their historical product-facing
contract wording no longer defines default experiment admission; the automated
GitHub Release and product-certification entrypoints are retired. A successful
Verify `summary` establishes source/quality coverage at that SHA, **not**
commercial release approval or a physical target performance claim.

Current laboratory routes use research validation and target-measurement profiles. Historical `commercial-core` names and `product-certified` records may remain inside original evidence or explicit archive replay. They do not authorize current research, grant new license rights or constitute newly collected measurements. Reviewed unattended dataset permissions are not broadened by retiring product terminology.

## Research acoustic decision — no product policy (2026-11-05)

The `Verify` self-test in `tools/acoustic_upgrade_decision.py` now uses an explicit `technical-research` study/policy identity and recorded acoustic metrics, not a SKU, `shipping_approved`, or product release authority. Its original ERLE, convergence, double-talk SI-SDR, noise SI-SDR, VAD F1 and corpus-case checks remain; non-finite metrics and historical product-policy inputs are rejected. `UPGRADE_ELIGIBLE` means only that a controlled research comparison may be justified, never model promotion, physical-board qualification or new evidence admission. Source, dataset rights and independent evaluation remain separate requirements. The prior implementation is available in Git history.

## Research-only physical HIL

The HIL Actions controller is now **manual-only**: a real isolated
`audio-target` runner, `HIL_ENABLED=true` and explicit 40-character source
SHA are mandatory. Neither a weekly schedule nor a GitHub Release triggers
physical HIL. Missing hardware/configuration fails visibly, not as an invented
result. The exact-DUT route/resource/thermal/power/long-soak evidence still
remains hash-bound and physically measured.

Durations 600 s, 1 h, 8 h, 24 h and optional 72 h are scientific
experiment choices; **72 h is not a product-certification prerequisite** for
research. Historic product soak policies remain in Git/Actions history only,
not active workflow authority. See [HIL research runner guide](../hil/README.md).

## E001 commercial activation retired

`.github/workflows/e001-activation-preflight.yml` formerly required an
immutable GitHub Release, exact shipping C compiler/sysroot/toolchain and an
independent `certification-archive` runner before creating a product
activation readiness receipt. It is **retired from active GitHub Actions**,
along with its release-bound source validator
`.github/program/e001_activation_preflight.py`. The historical source,
old workflow results, baseline SHA, and 72-hour product requirement remain
in Git/Actions history for read-only provenance.

The remaining `e001-hardware-readiness.yml` now checks E001 **historical
record consistency and actual research infrastructure configuration**, not
product/SKU readiness. Its results never imply human audio, device HIL or a
certified release. For real physical experiments, use the manual, exact-SHA
[research HIL workflow](../hil/README.md) and a separately authorized source,
board and data-rights contract. Missing devices are `NOT_RUN`/`BLOCKED`.


## Retired scheduled product-certificate self-test (2026-11-04)

The scheduled `nightly.yml` now runs research validation/data-source,
provenance, fuzz, HIL **source-only** preflight, statistical regressions and
workflow correctness checks without calling `certification/validate_record.py`.
The original product-certificate script, policy snapshots and earlier nightly
results remain available as historical source/evidence. A successful hosted
research nightly is neither a new product certificate nor a physical-device
measurement. The required research CI gate rejects restoration of this active
product-certification command.

## Research validation terminal authority

The active `validation/research-authority.json` v2 now terminates candidate review at
`independent-research-review`, not historical product certification. Four
research/validation corpus roles and sealed blind-selection separation are
unchanged; `target-resource` and `hil-soak` are **optional, separately
source/rights-bound** physical experiments. Existing VAD/AEC/BF/NS/AGC
numerical gates, data-source permissions and generated report hashes remain
fail-closed; changing the authority contract is a new source identity, not a
retroactive reinterpretation of historical experiments. Missing real SSC305
measurements remain `NOT_RUN` or `BLOCKED`, never `PASS`.

The original `validation/authority.json` v1 remains **byte-for-byte unchanged**
for I020 source-bound historical replay; it is not a valid new research
v2 authority, and no historic failure/receipt is silently reclassified.

## Retired orphaned release-metadata helpers

The former `scripts/prepare_release.py` and `scripts/release_manifest.py`
were product-publication metadata tools. Neither is needed to build, train,
evaluate, profile or verify current research, nor to reproduce the exact
historical source. Their executables are retired from the active tree;
source commits, old tags, manifests and immutable publication evidence remain
available in Git/GitHub history. Current documentation consistency checks
explicitly reject reintroduction of either helper, rather than executing
their old product-release self-tests as a hidden requirement of research CI.

The orphaned `scripts/post_release_status.py` tool previously assembled
`software_release=PASS` post-release status payloads after the publisher was
retired. It has now also been removed from the active research tree. Its
original source remains in Git history. Required research CI rejects
reintroduction rather than executing its former product status self-test.

Required C API/ABI compatibility, source SHA identity, integrity of historical
`CHANGELOG.md` and existing protected-main quality gates are unchanged.
Actual SSC305/HIL or real human recordings remain separately measured or
`NOT_RUN`/`BLOCKED`; an archived release never supplies new acoustic truth.

## Historical governance execution isolated (2026-11-06)

The automatic `ci-dechorate-governance-evidence.yml` workflow-run observer and its dormant PR833/M3/V2 command chain are retired from the active tree, together with `scripts/github_governance.py`. The current scientific dEchorate diagnostic workflow and algorithm/source/data manifests are unchanged; that workflow does not consume the withdrawn observer. The current main-only governance tool remains `scripts/research_github_governance.py`.

All eleven removed paths remain byte-exact in Git commit `e504368662f41d0a731f7ca777f4d62af7f92754`, tree `e720700b4f4f83f242eeab8d137b61276371f937`, with per-file hashes in `tests/fixtures/archived-governance.json`. Required CI runs `scripts/run_archived_governance_tests.py`: it makes a disposable local checkout of that fixed tree, validates every retained member, and runs the same eight historical test/mode invocations with explicit fake HTTP fixtures. It cannot select a new revision or live operation, does not fetch Git objects, strips credentials/Actions context, blocks the GitHub CLI and bounds total test time. This is offline regression, not a general network sandbox or a new observation.

New negative tests reject restored active legacy paths, modified archive members, substituted history, credential inheritance and omitted test entries. Existing source/measurement failures and real attempt budgets remain unchanged. No old receipt is relabeled as a new scientific or hardware PASS.
