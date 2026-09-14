# Data-driven Research Optimization

This document describes the permanent **research-continuous / shipping-frozen** optimization lane for audio-pipeline. Its executable control plane lives under `.github/research/continuous-optimization/`; existing `validation/` files remain the validation/evidence authority rather than becoming an optimizer control surface.

The immutable shipping baseline remains `v2.3.16` at `57e4c64adc1cf06819e46e24e275ecd746d5f17f` with shipping `aec_mu=0.22`. Research may generate new hypotheses, source revisions and parameter candidates, but no research artifact has shipping, HIL or Product Certification authority.

## Closed loop

The supported loop is:

`Dataset Registry -> Failure Mining -> bounded search -> multi-seed development Pareto selection -> validation/shadow cross-dataset gates -> FROZEN_RESEARCH_CANDIDATE -> validation-grade-blind -> target-resource review`

Only **development** data may rank candidates. Validation and shadow sources can reject the single development winner but cannot rescue, re-rank or select an alternate. `validation-grade-blind`, real PCR02 product capture and Product Certification evidence never enter optimizer feedback. Passing blind qualification only admits that exact candidate to a separate target-resource review; it does not execute target/HIL work or promote shipping.

## Dataset registry

`.github/research/continuous-optimization/dataset-registry.json` is the machine-readable admission list. Each source declares:

- covered DSP stages;
- whether it is synthetic, public, hosted-real or external-product data;
- the pinned lock/builder identity;
- legal selection/evaluation roles;
- frozen-holdout status;
- an explicit `may_promote_shipping=false` boundary.

Hosted P.808, hosted AEC and Extended Real research data are evaluation-only holdouts. The real PCR02 entry is deliberately unavailable to hosted optimizer roles and remains under issue #58 / existing HIL and Product Certification authority.

Terminal tuning IDs remain terminal across later source SHAs. In particular, rejected tuning `4a6a408bf0e3` / `aec_mu=0.24` cannot become eligible again merely because maintenance or governance commits move `source_sha`.

## Failure mining

`.github/research/continuous-optimization/failure_mining.py` consumes primary validation reports and deterministically maps failures into curriculum categories such as motion, far field, low SNR, double-talk, non-stationary noise, mic faults, clipping, reverberation, residual echo, VAD false positives and speech recall. Evidence sidecars are not reports and are excluded from mining.

The output is advisory research curriculum only. It cannot modify training/search weights automatically and cannot promote a candidate.

## Optimizer

`.github/research/continuous-optimization/research_optimizer.py` reuses the existing authority-guarded tuning engine and its runtime-safe parameter surface:

- `aec_mu`
- `ns_floor`
- `agc_target_dbfs`
- `limiter_dbfs`

Algorithm/source changes are represented by a new exact `source_sha` plus `hypothesis_id`; unsupported structural knobs are not invented. The optimizer evaluates every bounded candidate over multiple independent development seeds, constructs a multi-objective Pareto frontier, selects exactly one development winner, and then subjects only that winner to validation/shadow gates. There is no fallback to a second candidate after a gate failure.

A successful run emits at most `FROZEN_RESEARCH_CANDIDATE` with `next_gate=validation-grade-blind`. Blind qualification, target resources, SSC305/PCR02 HIL, soak and Product Certification remain separate authorities.

## Frozen candidate and blind qualification

A frozen candidate is committed under `.github/research/continuous-optimization/candidates/` only after a successful manual Research Optimization run. The manifest binds the exact research source, hypothesis, tuning ID, research-candidate ID, development/generalization evidence, workflow run ID, artifact ID, artifact digest and search-space digest.

The first admitted manifest is `f5ad7c495d7f67d6.json`, produced by Research Optimization #11 / run `34833101088` from source `01c7e0adf3ec9bcb1d401540c5e9d209176bd9ef`. It binds tuning ID `542ae198199b`: `aec_mu=0.22`, `ns_floor=0.10`, `agc_target_dbfs=-20.0`, `limiter_dbfs=-2.0`. This is research evidence only and does not alter the shipping defaults.

`.github/workflows/research-candidate-blind-qualification.yml` is the only generic blind-admission surface for these manifests. It is PR + manual only and has no push or schedule trigger. PR runs execute contracts only and never consume the blind holdout. Manual execution must be dispatched from protected `main` and:

1. verifies the committed candidate is not terminal;
2. verifies the exact retained Research Optimization artifact metadata and ZIP SHA-256;
3. verifies the downloaded `optimization-result.json` matches the committed source/hypothesis/tuning/result identity;
4. checks out qualification infrastructure and the exact candidate source separately;
5. builds the exact candidate-source processor and injects only the frozen runtime-safe tuning through a wrapper;
6. verifies the sealed public cache on the isolated `audio-validation` runner;
7. creates the repository-external HMAC blind holdout;
8. runs the same fixed candidate on the visible validation partition and then the blind summary-only partition;
9. emits either `BLIND_QUALIFIED_NON_SHIPPING` or `BLIND_REJECTED_NON_SHIPPING`.

There is no fallback, re-ranking, rescue candidate, threshold mutation, source mutation or automatic main mutation. A rejection is terminal for that tuning identity. A pass only sets `next_gate=target-resource`; `target_execution_authority=false`, and HIL/Product Certification/shipping authority remain false.

## Workflows

`.github/workflows/research-optimization.yml` is PR + manual only. It has **no schedule and no push trigger**. PR runs execute schema/registry/tool self-tests. Manual execution can additionally run a bounded two-development-seed optimization smoke over deterministic regression corpora and archive the hash-bound optimization/failure-mining evidence.

`.github/workflows/research-candidate-blind-qualification.yml` is likewise PR + manual only. Its PR path is contract-only; only an explicit manual dispatch may consume the external blind partition on the isolated `audio-validation` runner.

## Local checks

```sh
PYTHONPATH=validation/tools:.github/research/continuous-optimization \
  python3 .github/research/continuous-optimization/research_dataset_registry.py --self-test
PYTHONPATH=validation/tools:.github/research/continuous-optimization \
  python3 .github/research/continuous-optimization/failure_mining.py --self-test
PYTHONPATH=validation/tools:.github/research/continuous-optimization \
  python3 .github/research/continuous-optimization/research_optimizer.py --self-test
python3 .github/research/continuous-optimization/research_candidate_blind.py --self-test
python3 validation/tools/tuning_iteration.py --self-test
```

The committed registry checks are performed against the repository root explicitly, so relocating the research implementation cannot silently change validation authority.

Never feed `validation-grade-blind`, product capture, HIL, soak or certification evidence back into search.