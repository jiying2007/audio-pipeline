# Acoustic validation framework

`validation/` is the single repository-side framework for acoustic datasets, corpus construction, objective metrics, policies, tuning candidates, independent replay and validation evidence. The previous standalone `eval/` harness has been removed so metric math, corpus semantics and evidence rules cannot drift across two implementations.

`certification/` remains the separate terminal shipping authority. `lab/` provisions trusted execution/data infrastructure; it does not define acoustic acceptance.

## Authority model

The machine-readable source of truth is [`authority.json`](authority.json). `validation/tools/authority.py --self-test` verifies the authority contract and keeps the corpus schema tier enum synchronized.

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

Required PR verification runs a small search neighborhood against development seed `1307`, then replays the selected result from scratch on validation seed `2307` and shadow seed `3307`. Scheduled/manual **Acoustic Tuning Search** runs the wider search space. The standalone search workflow has no PR trigger so a pull request does not execute the same optimization twice.

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

## Public validation profiles

Public validation runs only on an isolated self-hosted runner labelled `audio-validation`. See `validation/RUNNER.md` for cache preparation and operating instructions.

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
