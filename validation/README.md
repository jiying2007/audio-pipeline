# Acoustic validation framework

`validation/` is the single repository-side framework for acoustic datasets, corpus construction, objective metrics, policies, tuning candidates, independent replay and validation evidence. The previous standalone `eval/` harness has been removed so metric math, corpus semantics and evidence rules cannot drift across two implementations.

`certification/` remains the separate terminal shipping authority. `lab/` provisions trusted execution/data infrastructure; it does not define acoustic acceptance.

## Authority model

The machine-readable source of truth is [`validation/authority.json`](authority.json). `validation/tools/authority.py --self-test` verifies the authority contract and keeps the corpus schema tier enum synchronized.

### Validation corpus tiers

| Tier | Data | Optimizer role | Purpose | Shipping authority? |
| --- | --- | --- | --- | --- |
| `regression` | deterministic generated fixtures | development / validation / shadow | correctness, CI regression, metric contracts | no |
| `research-validation` | explicitly research/conditional data | development / validation / shadow | algorithm research that cannot satisfy commercial evidence | no |
| `validation-grade` | pinned public real data + sealed public-derived simulation | validation / shadow only | independent acoustic quality evidence | no |
| `validation-grade-blind` | validation-grade data split with a repository-external HMAC key | never optimizer input | post-candidate hidden holdout | no |

`product-certified` is intentionally **not** a validation corpus tier. It is a schema-v4 certification record owned by `certification/` and is the only terminal shipping authority.

A generated fixture MUST NOT be relabeled as `validation-grade`. A validation-grade or blind corpus MUST NOT be used as tuning development/search input.

## Public sources

`datasets.lock.json` pins source metadata rather than copying third-party audio into this repository:

- Microsoft AEC Challenge: real and synthetic AEC data, including single-talk and double-talk. The upstream repository revision is pinned.
- Microsoft DNS Challenge: clean/noise/RIR source material plus official per-file checksum index. The upstream repository revision and checksum-index URL are pinned.
- OpenSLR SLR28: real/simulated room impulse responses and noises, Apache-2.0. The archive is locally SHA-256 sealed before it may contribute to validation-grade evidence.

Dataset licenses are upstream licenses. `audio-pipeline` does not relicense or redistribute those corpora. Review upstream dataset terms before acquisition or redistribution.

## Generated regression flow

The always-available deterministic regression corpus is small enough for hosted CI:

```bash
python3 validation/tools/authority.py --self-test
python3 validation/tools/dataset_lock.py validate --lock validation/datasets.lock.json
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

The generator is deterministic and remains `tier=regression`; it is not public-data or product evidence.

## Dataset-driven tuning

The bounded search engine is `validation/tools/tuning_iteration.py`; search contracts live under `validation/tuning/`.

Required PR verification always runs the deterministic 1307/2307/3307 regression matrix and tuner self-tests. The bounded `call-pr-smoke-v1` candidate search runs only when CI impact says the change can affect candidate discovery (DSP/build semantics, canonical validation/tuning assets, or the required audio-quality/Verify routing itself); `main` always forces the search again. Manual **Acoustic Tuning Search** runs the wider search space. The standalone search workflow has no PR trigger, so candidate discovery is never duplicated automatically. When the bounded search runs, it may reuse the just-enforced 1307/2307/3307 baseline reports only after exact source/corpus/policy/dataset/processor bindings and the processor-reported default tuning are proven identical to the search-space baseline; otherwise reuse fails closed.

An optimizer result may be only `KEEP_BASELINE`, `REJECT_CANDIDATE`, or `ACOUSTIC_CANDIDATE`. Candidate promotion remains:

```text
development search
  -> independent validation/shadow
  -> validation-grade-blind
  -> target resource evidence
  -> HIL/soak
  -> product-certified
```

No hosted optimizer path writes shipping defaults or bypasses certification.

## Frozen acoustic candidate replay

`Validation Grade` can optionally bind a prior `Audio Quality Evaluation` artifact via
`acoustic_candidate_artifact_id`. In candidate mode the workflow verifies the artifact
SHA-256, exact source revision, originating workflow, `ACOUSTIC_CANDIDATE` decision,
validation/shadow non-regression result, complete adjacent sensitivity coverage, and
the copied search-space digest before any public-data execution. It then wraps the
exact source-built `ap_process_pcm` with the selected runtime-safe tuning and records
both the underlying processor hash and wrapper hash in the public validation evidence.
The candidate wrapper is then passed through the shared strict metrics JSONL proxy used
by hosted blind qualification. That proxy changes no audio samples or tuning; it only
canonicalizes the diagnostic `vad_probability` / `erle_db` non-finite spellings to JSON
`null`, audits the replacements, and rejects every other malformed/non-standard token.

Frozen-candidate public replay is paired with the exact canonical baseline on the same
Full corpus and fixed absolute policy. The source-built processor default tuning must
numerically match the baseline recorded in the frozen Audio Quality search space before
either result is interpreted. Processor defaults are float32 runtime values, so identity
compares the printed values to the contract with zero relative tolerance and `1e-6`
absolute tolerance; the contract values remain canonical while the observed processor
values are retained in evidence.

The Full absolute policy is retained as diagnostic evidence, but it is not candidate
promotion authority: the canonical baseline itself currently fails the inherited Full
aggregate thresholds. Candidate-specific public authority therefore reuses the
pre-existing `call-v1` baseline-relative `max_regression` limits and
`case_delta_gates` from the exact candidate source revision. Metrics that are
structurally unavailable on both baseline and candidate are recorded as symmetrically
not applicable; asymmetric coverage fails closed. Report identity, corpus/policy/source
bindings and case sets must match exactly apart from the expected processor hash.

Public relative qualification has three machine-readable outcomes:

- `PUBLIC_RELATIVE_QUALIFIED_NON_SHIPPING`: no frozen relative regression or case-delta violation; candidate may advance to blind.
- `PUBLIC_RELATIVE_REJECTED_NON_SHIPPING`: one or more pre-frozen relative regression gates fail; the exact candidate is terminal.
- `PUBLIC_RELATIVE_INCOMPLETE_NON_SHIPPING`: bindings, metric coverage or case identity are incomplete/mismatched; candidate is not terminal.

This prevents stale absolute thresholds from being mistaken for candidate-specific
evidence while still forbidding public data from tuning or selecting a new candidate.

Candidate mode is intentionally limited to visible `validation-grade` execution and
runs on GitHub-hosted infrastructure. It bootstraps the same hash-bound Full public
cache contract used by hosted blind qualification, then replays the exact frozen tuning
against the fixed `validation-full.json` policy. This avoids reintroducing a persistent
`audio-validation` service solely for candidate promotion. Blind qualification must bind
the completed visible result in a later promotion step; the workflow therefore rejects
`validation-grade-blind` when an acoustic candidate artifact is supplied. Omitting
`acoustic_candidate_artifact_id` preserves the existing self-hosted baseline/manual
validation behavior.

For the frozen NS candidate selected by Audio Quality run `35729155489`, the bound
artifact is `10695375199`; candidate `0d5f52491863` is
`aec_mu=0.22, ns_floor=0.07, agc_target_dbfs=-20, limiter_dbfs=-2`. This evidence is
still non-shipping and cannot mutate runtime defaults.
## Terminal acoustic candidate identities

Terminal public/blind qualification outcomes are registered in
`docs/program/evidence/acoustic-terminal-registry.json`. The registry key is the pair
`source_revision + candidate_id`, not tuning alone. `Validation Grade` validates the
registry and rejects a matching terminal identity before any new public replay. A future
source revision may produce the same tuning value only through a new frozen candidate
lineage.

Candidate `0d5f52491863` on source
`f19d7ac928aa9db6c23b122faa63e4fcfe52e1a1` is terminal
`PUBLIC_RELATIVE_REJECTED_NON_SHIPPING` from run `35815591807`. Its pre-frozen
`call-v1` public relative gate found one case-delta excursion:
`compact-ns-008` VAD false-positive rate changed from `0.4868421053` to
`0.5614035088`, delta `+0.0745614035` against the frozen maximum `+0.05`.
Blind, target-resource, SSC305 HIL/soak, Product Certification and shipping promotion
are therefore not admitted for this exact identity.

## Public validation profiles

Baseline/manual Compact and Full validation continue to use the isolated self-hosted
runner labelled `audio-validation`. Frozen acoustic candidate visible replay is the
explicit exception: it runs on GitHub-hosted infrastructure with the hash-bound Full
cache bootstrap described above, so candidate promotion does not depend on a persistent
lab service. See `validation/RUNNER.md` for self-hosted cache preparation and operating
instructions.

### Compact

`Validation Compact` is the recommended first real/public-data gate. It does not require DNS5 materialization. Default coverage:

```text
60 balanced real Microsoft AEC Challenge cases
20 AEC+SLR28 acoustic combinations × (1 NS + 1 BF)
= 100 validation-grade cases
```

It uses `validation/policies/validation-compact.json`. The workflow fails if the AEC corpus does not cover far-end single-talk, double-talk and near-end single-talk, or if the public-derived cases do not span multiple clean sources, RIRs and noises.

### Full

`Validation Grade` is a strict superset of Compact. Default coverage:

```text
60 balanced real Microsoft AEC Challenge cases
20 AEC+SLR28 acoustic combinations × (1 NS + 1 BF) = 40 cases
60 Microsoft DNS Challenge clean+noise derived NS cases
= 160 validation-grade cases
```

The DNS5 source download contains official clean/noise/RIR material, not a canonical noisy/clean validation pair set. The full builder therefore verifies each selected DNS clean WAV and noise WAV against Microsoft's pinned checksum index and deterministically mixes them into an NS case with a known clean reference. This avoids treating locally generated audio as an official upstream pair while preserving exact upstream provenance.

The full workflow uses the fixed `validation/policies/validation-full.json`; callers cannot replace it with a weaker policy through workflow inputs.

## Extended Real validation

Compact100/Full160 remain frozen historical comparison families. v2.1.0 adds a separate Extended Real catalog and workflow for real far-field/moving-source, measured-room, meeting/overlap and hard-negative stress. Commercial profiles are license-isolated; research-only/conditional sources remain `research-validation` and cannot enter commercial validation. Selected real files are individually SHA-256 bound in a source manifest and verified again before corpus construction.

Extended Real uses scenario-stratified blind holdout plus tail/scenario/dimension gates and remains non-authoritative for shipping. See [`../docs/EXTENDED_REAL_VALIDATION.md`](../docs/EXTENDED_REAL_VALIDATION.md).

## Public cache preparation

`prepare_public_validation.py` provides fail-closed cache preparation and verification:

```bash
# Compact
python3 validation/tools/prepare_public_validation.py prepare \
  --profile compact --root /opt/audio-validation-data \
  --seal /opt/audio-validation-data/datasets.seal.json \
  --allow-large-downloads

# Full after official DNS clean/noise sources have been materialized
python3 validation/tools/prepare_public_validation.py prepare \
  --profile full --root /opt/audio-validation-data \
  --seal /opt/audio-validation-data/datasets.seal.json \
  --dns-data-root /data/dns5/datasets_fullband \
  --allow-large-downloads
```

The seal binds the current `datasets.lock.json`. A lock revision change invalidates the old cache by design.

## Case-local processor profiles

Validation cases may declare `processor_profile`. The default profile exercises the normal capture graph. `ns-isolated` runs only NS + VAD so NS preservation is not contaminated by HPF or AGC transforms. NS cases with deterministic VAD labels additionally measure `noise_only_attenuation_db` on stable non-speech frames after declared-latency alignment; a positive gate proves the suppressor is not a no-op while SI-SDR protects near-end fidelity.

## Blind holdout

Never store a blind split key in the repository. An `audio-validation` runner receives `AP_VALIDATION_HOLDOUT_KEY` from GitHub Actions secrets; missing keys fail the blind workflow. `split_holdout.py` HMAC-partitions immutable case identities. Per-case blind metrics can be suppressed from the published report while aggregate gates remain enforceable.

Blind data is a promotion authority, not an iterative optimizer dataset. Repeated candidate search against blind results would destroy its purpose.

## Evidence binding

Every public-data evidence bundle includes or binds:

- exact source revision;
- dataset lock SHA-256;
- local cache seal verification;
- corpus manifest and policy SHA-256;
- validation report and evidence manifest;
- SHA-256 of the executing `ap_process_pcm` binary;
- `ap_build_info_dump` output and compiler identity;
- aggregate `SHA256SUMS` for the uploaded evidence directory.

This is intentionally lighter than formal shipping-certification provenance but prevents a later unrelated binary or same-name corpus/policy from being presented as the evidence used for an earlier validation run.

## Evidence boundary

Compact, Full, Extended Real and tuning results are acoustic validation evidence only. They do not establish target CPU/RSS, thermal/power limits, real microphone/codec/enclosure acoustics, HIL stability or the formal 72-hour shipping certification. Those remain governed by `product-certification.yml`, `certification/` and real product evidence.

## Hosted real-audio smoke

`hosted_real.datasets.lock.json` pins four small CC-BY-4.0 Microsoft P.808 WAVs to an exact upstream revision and SHA-256. `Verify` downloads them on GitHub-hosted Linux, rechecks SHA-256 and Git blob identity, materializes mono PCM, and enforces `validation-hosted-real-smoke.json` through the canonical evaluator. Raw third-party audio remains outside this repository.
