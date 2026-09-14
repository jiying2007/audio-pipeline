# Data-driven Research Optimization

This directory defines the permanent **research-continuous / shipping-frozen** optimization lane for audio-pipeline.

The immutable shipping baseline remains `v2.3.16` at `57e4c64adc1cf06819e46e24e275ecd746d5f17f` with shipping `aec_mu=0.22`. Research may generate new hypotheses, source revisions and parameter candidates, but no research artifact has shipping, HIL or Product Certification authority.

## Closed loop

The supported loop is:

`Dataset Registry -> Failure Mining -> bounded search -> multi-seed development Pareto selection -> validation/shadow cross-dataset gates -> FROZEN_RESEARCH_CANDIDATE -> validation-grade-blind`

Only **development** data may rank candidates. Validation and shadow sources can reject the single development winner but cannot rescue, re-rank or select an alternate. `validation-grade-blind`, real PCR02 product capture and Product Certification evidence never enter optimizer feedback.

## Dataset registry

`dataset-registry.json` is the machine-readable admission list. Each source declares:

- covered DSP stages;
- whether it is synthetic, public, hosted-real or external-product data;
- the pinned lock/builder identity;
- legal selection/evaluation roles;
- frozen-holdout status;
- an explicit `may_promote_shipping=false` boundary.

Hosted P.808, hosted AEC and Extended Real research data are evaluation-only holdouts. The real PCR02 entry is deliberately unavailable to hosted optimizer roles and remains under issue #58 / existing HIL and Product Certification authority.

The previously rejected `aec_mu=0.24` candidate is retained as terminal evidence for its exact rejected source revision. A new experiment must carry a new hypothesis/source identity; terminal evidence cannot be silently reused as a passing candidate.

## Failure mining

`validation/tools/failure_mining.py` consumes validation reports and deterministically maps failures into curriculum categories such as motion, far field, low SNR, double-talk, non-stationary noise, mic faults, clipping, reverberation, residual echo, VAD false positives and speech recall.

The output is advisory research curriculum only. It cannot modify training/search weights automatically and cannot promote a candidate.

## Optimizer

`validation/tools/research_optimizer.py` reuses the existing authority-guarded tuning engine and its runtime-safe parameter surface:

- `aec_mu`
- `ns_floor`
- `agc_target_dbfs`
- `limiter_dbfs`

Algorithm/source changes are represented by a new exact `source_sha` plus `hypothesis_id`; unsupported structural knobs are not invented. The optimizer evaluates every bounded candidate over multiple independent development seeds, constructs a multi-objective Pareto frontier, selects exactly one development winner, and then subjects only that winner to validation/shadow gates. There is no fallback to a second candidate after a gate failure.

A successful run emits at most `FROZEN_RESEARCH_CANDIDATE` with `next_gate=validation-grade-blind`. Blind qualification, target resources, SSC305/PCR02 HIL, soak and Product Certification remain mandatory external authorities.

## Workflow

`.github/workflows/research-optimization.yml` is PR + manual only. It has **no schedule and no push trigger**.

PR runs execute schema/registry/tool self-tests. Manual execution can additionally run a bounded two-development-seed optimization smoke over deterministic regression corpora and archive the hash-bound optimization/failure-mining evidence. Cross-dataset runs can use any materialized registered evaluation-only source without changing candidate-selection authority.

## Local checks

```sh
python3 validation/tools/research_dataset_registry.py --self-test --check
python3 validation/tools/failure_mining.py --self-test
python3 validation/tools/research_optimizer.py --self-test
python3 validation/tools/tuning_iteration.py --self-test
```

Never feed `validation-grade-blind`, product capture, HIL, soak or certification evidence back into search.
