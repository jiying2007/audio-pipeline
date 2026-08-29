# Public Validation Runner

The `audio-validation` runner is a self-hosted Linux runner used only for public-data acoustic validation. It is intentionally separate from product certification and from normal GitHub-hosted CI.

Before allocating a public-data run, dispatch **Trusted Runner Readiness** for role `audio-validation` against the exact source ref and require `READY`. The same `tools/runner_preflight.py` contract is executed again inside Compact/Full validation and its JSON report is included in the validation evidence bundle. See [`docs/TRUSTED_RUNNERS.md`](../docs/TRUSTED_RUNNERS.md) for the cross-role activation sequence.

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

Compact is the recommended first public-data gate. It avoids the very large DNS5 training corpus and uses:

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

Full is a strict superset of Compact and adds Microsoft DNS Challenge source material. The upstream DNS5 repository provides clean speech, noise and RIR source archives rather than a canonical noisy/clean validation pair set. `audio-pipeline` therefore does not pretend that an arbitrary DNS materialization already contains official noisy/clean pairs.

Instead, Full selects official DNS clean WAVs and noise WAVs, verifies every selected source against Microsoft's pinned checksum index, and deterministically mixes them into validation-grade NS cases with a known clean reference. The generated noisy PCM is sealed by the corpus/evidence chain; the upstream clean/noise files retain their official SHA1 provenance.

DNS5 is intentionally not silently downloaded by `audio-pipeline`: upstream documents roughly 1 TB for the complete unpacked training data and provides `download-dns-challenge-5-*.sh` scripts so the operator can select the desired source archives. A full 1 TB mirror is not required by the validation workflow; the supplied DNS root only needs enough official indexed clean and noise WAV material to satisfy the requested case/diversity budget.

Use the pinned DNS repository checkout's official download scripts to materialize the desired clean/noise sources on suitable storage. Review upstream dataset licenses before downloading or redistributing any corpus.

Then prepare and seal the full cache:

```bash
python3 validation/tools/prepare_public_validation.py prepare \
  --profile full \
  --root /opt/audio-validation-data \
  --seal /opt/audio-validation-data/datasets.seal.json \
  --dns-data-root /data/dns5/datasets_fullband \
  --allow-large-downloads
```

This downloads/seals the pinned DNS checksum index but does not replace the upstream DNS dataset downloader. Full preparation fails closed unless the DNS root contains both clean and noise WAV sources.

Verify:

```bash
python3 validation/tools/prepare_public_validation.py verify \
  --profile full \
  --root /opt/audio-validation-data \
  --seal /opt/audio-validation-data/datasets.seal.json \
  --dns-data-root /data/dns5/datasets_fullband
```

Run the GitHub Actions workflow **Validation Grade**. Its official policy is fixed to `validation/policies/validation-full.json`; callers cannot weaken the workflow by supplying another policy path. The default full corpus is:

```text
60 balanced real AEC cases
20 AEC+SLR28 acoustic combinations × (1 NS + 1 BF) = 40 cases
60 verified DNS clean+noise derived NS cases
= 160 validation-grade cases
```

The workflow verifies multiple AEC scenarios, multiple AEC near-end sources, multiple SLR28 RIR/noise members, and multiple DNS clean/noise files.

## Processor identity

Both public-validation workflows bind the exact execution binary into the evidence bundle using:

- source revision;
- SHA-256 of `ap_process_pcm`;
- `ap_build_info_dump` output;
- compiler identity;
- runner readiness report;
- cache verification report;
- corpus/policy/report/evidence hashes.

This is intentionally lighter than shipping certification provenance, but it prevents a later unrelated processor binary from being presented as the binary that produced an earlier validation report.

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