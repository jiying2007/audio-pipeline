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

The search is intentionally tiered:

- `search-spaces/call-pr-smoke-v1.json` is the bounded PR neighborhood. It probes representative AEC and NS neighbors while retaining the baseline and the full independent replay gates.
- `search-spaces/call-v1.json` is the wider scheduled/manual search over all four runtime-safe controls.
- `search-spaces/call-interaction-v1.json` is a bounded Cartesian research run over `ns_floor` x `agc_target_dbfs`. One-at-a-time cannot express combinations, and these two controls stack: on the regression corpus the best single-control change scores 1.5458 while the best gated combination reaches 3.0721. It is a research/discovery space, not a promotion path.

`aec_mu` is deliberately excluded from that space. Every probed combination that raised `aec_mu` above the baseline violated the near-end SI-SDR improvement gate, with worst-case per-case costs of -0.76 to -1.10 dB. The reason is that the costs stack: `ns_floor`, `agc_target_dbfs` and `aec_mu` each cost roughly 0.27 dB on their own and all sit inside the 0.75 dB tolerance, but three of them together exceed it. One-at-a-time can never observe this because it only ever moves one control, so the interaction space is what stops a stacked regression from being reported as a 3.6-point improvement.

Both start from the shipping CALL defaults and use the controls exposed by `ap_tuning_t`:

- `aec_mu`
- `ns_floor`
- `agc_target_dbfs`
- `limiter_dbfs`

One-at-a-time is intentional for the default CI loop: it keeps cost bounded, provides causal attribution for a gain/regression, and avoids blindly exploring an exponential grid. The engine also supports a capped Cartesian strategy for explicit research runs.

Candidates are ranked relative to the baseline across pass rate, p10 speech/noise tails, ERLE, VAD and clipping. The selected development winner is replayed from scratch on validation and shadow data. Any configured regression beyond tolerance rejects the candidate. A smaller PR search changes discovery breadth only; it does not weaken validation/shadow authority.

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
