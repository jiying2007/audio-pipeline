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
- Microsoft DNS Challenge: clean/noise/RIR source material plus official per-file checksum index. The upstream repository revision and checksum-index URL are pinned.
- OpenSLR SLR28: real/simulated room impulse responses and noises, Apache-2.0. The archive is locally SHA-256 sealed before it may contribute to validation-grade evidence.

Dataset licenses are upstream licenses. `audio-pipeline` does not relicense or redistribute those corpora. Review upstream dataset terms before acquisition or redistribution.

## Generated regression flow

The always-available deterministic regression corpus is small enough for hosted CI:

```bash
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

## Evidence binding

Every public-data evidence bundle includes or binds:

- exact source revision;
- `datasets.lock.json` SHA-256;
- local cache seal verification;
- corpus manifest and policy SHA-256;
- validation report and evidence manifest;
- SHA-256 of the executing `ap_process_pcm` binary;
- `ap_build_info_dump` output and compiler identity;
- aggregate `SHA256SUMS` for the uploaded evidence directory.

This is intentionally lighter than formal shipping-certification provenance but prevents a later unrelated binary or same-name corpus/policy from being presented as the evidence used for an earlier validation run.

## Evidence boundary

Compact and Full are acoustic validation evidence only. They do not establish target CPU/RSS, thermal/power limits, real microphone/codec/enclosure acoustics, far-field product performance, HIL stability or the formal 72-hour shipping certification. Those remain governed by `product-certification.yml` and real product evidence.
