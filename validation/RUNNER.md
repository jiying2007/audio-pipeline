# Public Validation Runner

The `audio-validation` runner is a self-hosted Linux runner used only for public-data acoustic validation. It is intentionally separate from product certification and from normal GitHub-hosted CI.

## Evidence levels

- `regression`: deterministic generated fixtures; correctness/regression only.
- `validation-grade`: pinned public real data and sealed public-derived simulations; acoustic validation only.
- `validation-grade-blind`: validation-grade data with repository-external HMAC holdout.
- `product-certified`: real shipping hardware, product corpus, route, performance, thermal, power and soak evidence.

Public validation MUST NOT be reported as product certification.

## Runner labels and prerequisites

Register an isolated runner with labels:

```text
self-hosted, linux, audio-validation
```

Install at least:

- Python 3
- CMake and a C compiler
- Git
- Git LFS (required for AEC Challenge materialization)
- enough local storage for the selected profile

Recommended cache root:

```text
/opt/audio-validation-data
```

Do not place public corpora in this repository or in GitHub Actions artifacts.

## Compact profile

Compact is the recommended first public-data gate. It avoids the roughly 1 TB unpacked DNS5 training corpus and uses:

- pinned Microsoft AEC Challenge test audio;
- sealed OpenSLR SLR28 RIR/noise;
- balanced real AEC far-end / double-talk / near-end cases;
- public-derived NS and 2-mic robot simulations using real AEC near-end captures with multiple SLR28 RIR/noise members.

Prepare once on the runner:

```bash
python3 validation/tools/prepare_public_validation.py prepare \
  --profile compact \
  --root /opt/audio-validation-data \
  --seal /opt/audio-validation-data/datasets.seal.json \
  --allow-large-downloads
```

Verify without changing the cache:

```bash
python3 validation/tools/prepare_public_validation.py verify \
  --profile compact \
  --root /opt/audio-validation-data \
  --seal /opt/audio-validation-data/datasets.seal.json
```

The preparation command writes `public-validation-compact-runner-manifest.json` containing the pinned lock hash, local seal hash, materialized AEC revision, SLR28 archive hash and tool versions.

Run the GitHub Actions workflow **Validation Compact**. The default corpus is:

```text
60 balanced real AEC cases
20 public-derived acoustic combinations × (1 NS + 1 BF)
= 100 validation-grade cases
```

The workflow fails if it does not cover all three AEC scenarios or if the derived corpus does not span multiple clean sources, RIRs and noises.

## Full profile

Full adds Microsoft DNS Challenge real noisy/clean pairs. DNS5 is intentionally not silently downloaded by `audio-pipeline`: the upstream documentation states that the unpacked training data is about 1 TB and provides `download-dns-challenge-5-*.sh` scripts for operators to select and download the desired data.

First use the pinned DNS repository checkout's official download scripts to materialize `datasets_fullband` on storage sized for the data. Review upstream dataset licenses before downloading or redistributing any corpus.

Then prepare and seal the full cache:

```bash
python3 validation/tools/prepare_public_validation.py prepare \
  --profile full \
  --root /opt/audio-validation-data \
  --seal /opt/audio-validation-data/datasets.seal.json \
  --dns-data-root /data/dns5/datasets_fullband \
  --allow-large-downloads
```

This downloads/seals the pinned DNS checksum index but does not replace the upstream DNS dataset downloader. Full preparation fails closed if the DNS materialization is absent.

Verify:

```bash
python3 validation/tools/prepare_public_validation.py verify \
  --profile full \
  --root /opt/audio-validation-data \
  --seal /opt/audio-validation-data/datasets.seal.json \
  --dns-data-root /data/dns5/datasets_fullband
```

Run the GitHub Actions workflow **Validation Grade**. Its official policy is fixed to `validation/policies/validation-full.json`; callers cannot weaken the workflow by supplying another policy path.

## Blind holdout

For either workflow, configure repository secret:

```text
AP_VALIDATION_HOLDOUT_KEY
```

Select `validation-grade-blind`. The secret must never be committed or copied into the public dataset cache. Missing keys fail the workflow. Blind reports expose aggregate results while suppressing per-case metrics for the blind partition.

## Cache lifecycle

When `validation/datasets.lock.json` changes, the existing seal becomes invalid by design. Re-run preparation and review the new upstream revision/license/source changes before accepting a new cache.

Never reuse a seal whose `lock_sha256` does not match the checked-out repository. Never edit files inside a pinned dataset checkout after preparation. A cache verification failure is an infrastructure/evidence failure, not an acoustic pass.

## Release interpretation

A passing Compact or Full run means the exact source revision passed the corresponding public-data policy against the sealed cache used by that run. It does **not** establish target CPU, RSS, thermal, power, microphone/codec/box acoustics, 3–5 m far-field behavior, HIL stability or 72-hour shipping certification. Those remain the responsibility of `product-certification.yml` and real product evidence.
