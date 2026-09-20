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

The validation step in `.github/workflows/acoustic-tuning-iteration.yml` runs the engine's own `validate_search_space` over every file under `search-spaces/` rather than over a hand-written list, so a space that nobody remembered to enumerate is still validated instead of silently skipped. The CALL spaces remain pinned to their expected strategy, and a `call-*` space that is not listed fails the step closed.

`aec_mu` is deliberately excluded from that space. Every probed combination that raised `aec_mu` above the baseline violated the near-end SI-SDR improvement gate, with worst-case per-case costs of -0.76 to -1.10 dB. The reason is that the costs stack: `ns_floor`, `agc_target_dbfs` and `aec_mu` each cost roughly 0.27 dB on their own and all sit inside the 0.75 dB tolerance, but three of them together exceed it. One-at-a-time can never observe this because it only ever moves one control, so the interaction space is what stops a stacked regression from being reported as a 3.6-point improvement.

Where the interaction grid stops, and why it is not widened. The `agc_target_dbfs` grid ends at -15.0, which is also where the selected candidate sits, so the edge was probed: `-14.0` and `-13.0` score 3.1618 and 3.1757, both above the 3.0721 selection, and both are rejected on noise-only attenuation (-0.9851 and -1.2595 dB worst case against the 0.75 dB tolerance). The grid boundary is therefore the gate boundary and not a truncated search. This is the second independent demonstration that the paired gates earn their place: without them, simply widening the grid would have reported `-13.0` as the strongest candidate instead of rejecting it.

Robustness costs less than it looks. The selection rule takes the highest-scoring compliant candidate, which leaves `ns_floor=0.06` with `agc_target_dbfs=-15.0` only 0.0126 dB inside the per-case noise-attenuation bound on development (-0.7374 dB against the -0.75 dB bound). That per-case bound is the binding constraint, and the aggregate `p10_noise_only_attenuation_db` term is only marginally looser at 0.0182 dB inside its own 0.75 dB tolerance. Stepping one grid point back to `agc_target_dbfs=-16.0` gives up roughly 5% of the development score (3.0721 -> 2.9143) and 3-5% on the held-out partitions (+6.2844 -> +6.1094 on validation, +3.3241 -> +3.1605 on shadow), but widens the noise-attenuation margin about eighteen-fold (-0.5121 dB on development, -0.4984 and -0.4938 dB held out) and improves near-end SI-SDR on every partition. The engine does not make that trade automatically, because choosing by margin rather than by score is a policy decision and not a search result. The iteration evidence now makes that distinction machine-readable: every case-delta gate summary records its margin to each configured bound plus the binding bound/margin, and the selected candidate repeats its development gate summary directly. Negative margin means a violated bound; positive margin is remaining headroom. This is evidence only: the default selection policy remains highest development score among case-gate-compliant candidates, so adding margin telemetry does not silently turn the search into margin-first ranking. The result also records `development_adjacent_sensitivity`: for each already-generated candidate one grid step away from the selected tuning along exactly one search axis, it binds the neighbor's score, gate summaries and violations and counts compliant versus violating neighbors. Missing Cartesian combinations are not invented or evaluated. This turns observations such as “the next `ns_floor` point crosses the gate” into deterministic evidence while leaving selection unchanged.

The development ranking is not a reliable ordering at this granularity. `ns_floor=0.07` with `agc_target_dbfs=-16.0` scores higher on development than `ns_floor=0.06` does (2.9663 against 2.9143) yet lower on both held-out partitions (+5.5518 and +2.7915 against +6.1094 and +3.1605). Differences of a few hundredths of a development score should not be read as ordering evidence, and any promotion decision has to be taken on the blind holdout rather than on the development ranking.

`limiter_dbfs` is a live axis, and the two-dimensional interaction space does not cover it. Probed one at a time it looks nearly free: at the shipping defaults, -3.0 scores +0.1980 against the baseline with no per-case delta at all, and the whole `call-v1` limiter grid (-3.0 to -1.5) sits on the far side of the optimum. Combined with the other two controls the effect is far larger than one-at-a-time suggests. Holding `ns_floor=0.07` and `agc_target_dbfs=-16.0`:

```
limiter_dbfs    -2.0     -8.0    -10.0    -12.0    -14.0    -15.0
score          2.9663   3.9848   4.1220   4.0551   3.9715   4.0193
```

The optimum is interior, near -10.0 dBFs, so unlike `ns_floor` and `agc_target_dbfs` this grid is not truncated by a gate. Every probed point carries zero per-case gate violations, and the per-case worst-case deltas are identical to the same candidate at the shipping limiter, which means the entire gain sits in the aggregate statistics.

That is also the reason to treat it carefully. Lowering the output ceiling is a product-level perceptual change, and no metric in the objective measures output level or loudness, so the objective has an unpenalised direction that the search will walk down as far as the aggregate terms allow. `search-spaces/call-interaction-3d-v1.json` covers this region as a research space; its results are discovery input only, and the blind holdout plus product review remain mandatory.

The limiter also buys back `aec_mu`, which the gates had closed. Every combination raising `aec_mu` above the baseline violates the per-case near-end SI-SDR bound at the shipping limiter: the strongest point of the `aec_mu` interaction probe scores 3.5959, above the current champion, with a -0.7830 dB worst case against the -0.75 dB bound, so the engine correctly reports `KEEP_BASELINE` for the whole space. Reducing the ceiling moves that worst case, recovering roughly 0.07 to 0.13 dB of per-case headroom per 2 dB. Holding `ns_floor=0.07` and `agc_target_dbfs=-16.0`, each cell pairs the worst-case per-case near-end SI-SDR delta with the score below it:

```
                aec_mu=0.22   aec_mu=0.24   aec_mu=0.26
limiter=-10.0     -0.4582       -0.7447       -0.8944  violates
                  4.1220        4.5914        4.1134
limiter=-12.0     -0.3396       -0.6315       -0.7874  violates
                  4.0551        4.5245        4.1915
limiter=-14.0     -0.2730       -0.5043       -0.6739
                  3.9715        4.4409        4.1950
```

`aec_mu=0.24` wins within every limiter column and `-10.0` wins within every `aec_mu` row, so the score-selected point is `ns_floor=0.07`, `agc_target_dbfs=-16.0`, `aec_mu=0.24`, `limiter_dbfs=-10.0` at 4.5914. It is also the tightest point in the table, at 0.0053 dB of per-case near-end headroom on development against 0.2051 dB for the `aec_mu=0.22` point the earlier space selected, which is the sharpest instance so far of a selection rule that ranks by score and reports no margin. Held-out replay is looser than development rather than tighter, 0.1326 dB on validation and 0.0544 dB on shadow, scoring +7.0232 and +4.7465, so a development margin of a few thousandths is not evidence about the candidate's margin in either direction. `search-spaces/call-aec-limiter-v1.json` carries this grid as a research space, with `agc_target_dbfs` pinned because that axis is gate-bound and already covered above.

The same space also sweeps `ns_floor` at 0.06 and 0.07, and the second value never wins: `ns_floor=0.07` outscores 0.06 in all nine cells. More usefully, the champion's near-end margin does not survive a step in `ns_floor`. At `limiter_dbfs=-10.0` and `aec_mu=0.24` the worst per-case near-end delta is -0.7447 dB at `ns_floor=0.07`, which is 0.0053 dB inside the -0.75 dB bound, and -0.7884 dB at `ns_floor=0.06`, which violates it. The 0.0053 dB figure is therefore not merely small: it is small enough that the adjacent grid point in a different control fails the gate. `limiter_dbfs=-12.0` is the only ceiling whose near-end margin survives that step in both directions, 0.1185 dB at `ns_floor=0.07` and 0.0728 dB at `ns_floor=0.06`; -14.0 is looser still at 0.2457 and 0.1953 dB, while -10.0 fails. `aec_mu=0.26` is admissible only at `limiter_dbfs=-14.0`, at both `ns_floor` values, so its admissibility is set by the ceiling and not by `ns_floor`.

`aec_mu` below the baseline is not a candidate direction. Probed one at a time at the shipping defaults it is monotonically worse as it falls: 0.20 scores -0.5085, 0.18 scores -1.0060 and 0.16 scores -1.6901, the opposite of the limiter, whose isolated probe was positive. Lowering the step size is therefore closed off rather than untested.

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
