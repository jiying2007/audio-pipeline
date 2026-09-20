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

Where the interaction grid stops, and why it is not widened. The `agc_target_dbfs` grid ends at -15.0, which is also where the selected candidate sits, so the edge was probed: `-14.0` and `-13.0` score 3.1618 and 3.1757, both above the 3.0721 selection, and both are rejected on noise-only attenuation (-0.9851 and -1.2595 dB worst case against the 0.75 dB tolerance). The grid boundary is therefore the gate boundary and not a truncated search. This is the second independent demonstration that the paired gates earn their place: without them, simply widening the grid would have reported `-13.0` as the strongest candidate instead of rejecting it.

Robustness costs less than it looks. The selection rule takes the highest-scoring compliant candidate, which leaves `ns_floor=0.06` with `agc_target_dbfs=-15.0` only 0.013 dB inside the noise-attenuation gate on development (-0.7374 dB against -0.75 dB). Stepping one grid point back to `agc_target_dbfs=-16.0` gives up roughly 5% of the development score (3.0721 -> 2.9143) and 3-5% on the held-out partitions (+6.2844 -> +6.1094 on validation, +3.3241 -> +3.1605 on shadow), but widens the noise-attenuation margin about eighteen-fold (-0.5121 dB on development, -0.4984 and -0.4938 dB held out) and improves near-end SI-SDR on every partition. The engine does not make that trade automatically, because choosing by margin rather than by score is a policy decision and not a search result.

The development ranking is not a reliable ordering at this granularity. `ns_floor=0.07` with `agc_target_dbfs=-16.0` scores higher on development than `ns_floor=0.06` does (2.9663 against 2.9143) yet lower on both held-out partitions (+5.5518 and +2.7915 against +6.1094 and +3.1605). Differences of a few hundredths of a development score should not be read as ordering evidence, and any promotion decision has to be taken on the blind holdout rather than on the development ranking.

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
