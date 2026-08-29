# Validation-grade acoustic corpus

This directory defines the self-validation layer between unit/regression testing and real target-board product certification.

## Trust levels

| Tier | Data | Purpose | Product-certified? |
| --- | --- | --- | --- |
| `regression` | deterministic generated fixtures | correctness, CI regression, metric contracts | no |
| `validation-grade` | pinned public real data + sealed public-derived simulation | acoustic quality evidence | no |
| `validation-grade-blind` | validation-grade data split with a repository-external HMAC key | release holdout | no |
| `product-certified` | real shipping hardware/audio route + product corpus + performance/thermal/power/soak | shipping decision | yes |

A generated fixture MUST NOT be relabeled as `validation-grade`. Product certification remains governed by `certification/`.

## Public sources

`datasets.lock.json` pins source metadata rather than copying third-party audio into this repository:

- Microsoft AEC Challenge: real and synthetic AEC data, including single-talk and double-talk. The upstream repository revision is pinned.
- Microsoft DNS Challenge: clean/noise/RIR synthesis assets and dev sets. The upstream repository revision and official per-file checksum-index URL are pinned.
- OpenSLR SLR28: real/simulated room impulse responses and noises, Apache-2.0. The large archive is locally SHA-256 sealed before it may contribute to validation-grade evidence.

Dataset licenses are upstream licenses. `audio-pipeline` does not relicense or redistribute those corpora. Review upstream dataset terms before acquisition or redistribution.

## Typical flow

```bash
python3 validation/tools/dataset_lock.py validate --lock validation/datasets.lock.json

# Always available and small: deterministic regression corpus.
python3 validation/tools/build_validation_corpus.py \
  --output /tmp/ap-validation-smoke --seed 1307
cmake -S . -B build-validation -DCMAKE_BUILD_TYPE=Release -DAP_BUILD_BENCH=OFF
cmake --build build-validation --target ap_process_pcm --parallel
python3 validation/tools/run_validation.py \
  --corpus /tmp/ap-validation-smoke/corpus.json \
  --policy validation/policies/validation-smoke.json \
  --dataset-lock validation/datasets.lock.json \
  --processor build-validation/ap_process_pcm \
  --output /tmp/ap-validation-smoke/report.json \
  --evidence-manifest /tmp/ap-validation-smoke/evidence-manifest.json \
  --enforce
```

For public data, acquire/cache data outside Git, verify the pinned revisions and local seals, build a canonical corpus with `build_public_corpus.py`, then run the same evaluator. The self-hosted `Validation Grade` workflow uses runner label `audio-validation` so large public corpora do not enter GitHub-hosted runners.

## Blind holdout

Never store a blind split key in the repository. A release-validation runner provides `AP_VALIDATION_HOLDOUT_KEY`; `split_holdout.py` HMAC-partitions immutable case identities. Per-case blind metrics can be suppressed from the published report while aggregate gates remain enforceable.

## Evidence binding

Every report records SHA-256 for:

- `datasets.lock.json`
- corpus manifest
- validation policy
- source revision

and emits an evidence manifest. This prevents a later same-name policy/corpus from being presented as the evidence used for an earlier result.
