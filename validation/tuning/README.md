# Audio Quality Iteration

This directory closes the repeatable **dataset -> evaluate -> search -> independent replay -> candidate** loop without weakening the existing shipping evidence model.

## Authority boundary

`validation/tools/tuning_iteration.py` may emit only:

- `KEEP_BASELINE`
- `REJECT_CANDIDATE`
- `ACOUSTIC_CANDIDATE`

`ACOUSTIC_CANDIDATE` is deliberately **not** a shipping or certification decision. A candidate must still pass, using the exact same source/tuning revision:

1. repository-external HMAC `validation-grade-blind` holdout;
2. target CPU/RSS/latency/resource gates;
3. SSC305/product HIL and soak evidence;
4. product certification on the shipping device/corpus;
5. normal source review before defaults or product configuration change.

The optimizer never writes `main`. Its development input must be `regression` or `research-validation`; `validation-grade`, `validation-grade-blind`, and product/certification evidence are never legal candidate-selection inputs.

## Data partition contract

The hosted iteration uses three independently generated regression corpora:

- development: seed `1307` -- selection is allowed here;
- validation: seed `2307` -- selection is forbidden;
- shadow: seed `3307` -- selection is forbidden.

The iteration engine binds all three corpus hashes and rejects identical corpus IDs, hashes, or generated seeds. Real public/robot corpora remain governed by `validation/datasets.lock.json`, `validation/extended.datasets.lock.json`, the existing sealed cache, and the external blind key.

Large/raw third-party audio is not committed to Git. GitHub stores manifests, locks, policies, reports, hashes and workflow artifacts; reusable public data stays in the pinned cache/object-storage/self-hosted-runner layer already defined by `validation/` and `lab/`.

## Search model

`search-spaces/call-v1.json` starts from the shipping CALL defaults and uses a bounded one-at-a-time search over the four runtime-safe controls exposed by `ap_tuning_t`:

- `aec_mu`
- `ns_floor`
- `agc_target_dbfs`
- `limiter_dbfs`

One-at-a-time is intentional for the default CI loop: it keeps cost bounded, provides causal attribution for a gain/regression, and avoids blindly exploring an exponential grid. The engine also supports a capped Cartesian strategy for explicit research runs.

Candidates are ranked relative to the baseline across pass rate, p10 speech/noise tails, ERLE, VAD and clipping. The selected development winner is replayed from scratch on validation and shadow data. Any configured regression beyond tolerance rejects the candidate.

## Local run

```sh
cmake -S . -B build-tuning -DCMAKE_BUILD_TYPE=Release -DAP_BUILD_BENCH=OFF -DAP_STRICT_WARNINGS=ON
cmake --build build-tuning --target ap_process_pcm --parallel

for seed in 1307 2307 3307; do
  python3 validation/tools/build_validation_corpus.py \
    --output "/tmp/ap-tuning-$seed" --seed "$seed"
done

python3 validation/tools/tuning_iteration.py \
  --processor build-tuning/ap_process_pcm \
  --development-corpus /tmp/ap-tuning-1307/corpus.json \
  --validation-corpus /tmp/ap-tuning-2307/corpus.json \
  --shadow-corpus /tmp/ap-tuning-3307/corpus.json \
  --policy validation/policies/validation-smoke.json \
  --dataset-lock validation/datasets.lock.json \
  --search-space validation/tuning/search-spaces/call-v1.json \
  --output-dir /tmp/ap-tuning-result
```

Run `python3 validation/tools/tuning_iteration.py --self-test` before changing the search/evidence logic.

## Promotion workflow

The automated hosted job is a discovery/regression loop, not a shortcut around product evidence. If it finds an `ACOUSTIC_CANDIDATE`, materialize that tuning as a reviewed source/product-config change and validate the exact commit with the existing `Validation Grade` blind tier, target resource workflow, HIL/soak workflow, and product certification workflow. Only those existing authorities can close a release.
