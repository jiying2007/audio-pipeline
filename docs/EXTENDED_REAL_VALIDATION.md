# Extended Real Validation

This runbook defines the real/public acoustic-validation layer above Compact100/Full160 and below product certification. It expands acoustic diversity without changing the historical Compact/Full baselines and never upgrades public data into shipping authority.

## Evidence boundary

Extended-real results are `validation-grade`, `validation-grade-blind`, or `research-validation` evidence only. They can expose algorithmic weaknesses in real far-field, moving-source, measured-room, environmental-noise and meeting conditions. They do **not** prove the shipping microphone geometry, enclosure, codec, speaker path, target CPU/thermal/power or the 72 h product route. Product Certification remains the shipping authority.

## Profiles and license isolation

`validation/extended.datasets.lock.json` is the normative catalog.

| Profile | Sources | Intended use |
| --- | --- | --- |
| `commercial-core` | RealMAN, BUT ReverbDB, MUSAN, Mini LibriSpeech | frequent real far-field + measured-room + hard-negative validation |
| `commercial-plus` | core + VOiCES + AMI + ICSI | weekly/release-quality broader real-room and meeting stress |
| `research` | plus + AISHELL-4 + filtered FSD50K + WHAM | exploratory only; never commercial/shipping authority |

Usage classes are fail-closed. `commercial-core` and `commercial-plus` may contain only `commercial-validation` sources. CC-BY-SA, mixed-license and NonCommercial sources remain outside commercial profiles. ACE Challenge is catalog-only because the checked catalog treats NoDerivatives as non-transforming.

The catalog records upstream attribution and source URLs. Raw corpora remain outside Git and GitHub Actions artifacts.

## Runner layout

Use an isolated runner labelled:

```text
self-hosted, linux, audio-validation
```

Recommended root:

```text
/opt/audio-validation-extended/
  RealMAN/
  BUT_ReverbDB/
  musan/
  LibriSpeechMini/
  VOiCES/        # commercial-plus
  AMI/           # commercial-plus
  ICSI/          # commercial-plus
  AISHELL4/      # research only
  FSD50K/        # research only; per-clip license metadata required
  WHAM/          # research only
```

Install Python 3, CMake, a C compiler, Git, Git LFS and `ffmpeg`. The runner must have enough local storage for caller-materialized datasets. `audio-pipeline` deliberately does not silently mirror multi-gigabyte or terms-sensitive corpora.

## Recommended materialization

Minimize storage where upstream structure permits it:

- RealMAN: prefer validation/test material; training data is not required for validation.
- BUT ReverbDB: measured RIR and room-noise material is sufficient for the derived measured-room cases.
- MUSAN: noise and music are the primary hard-negative sources.
- Mini LibriSpeech SLR31: the small clean development subset is sufficient as a clean reference source.
- VOiCES: distant 16 kHz speech/distractor material is sufficient for the implemented scanner.
- AMI: microphone-array meeting audio is preferred.
- ICSI: meeting audio is sufficient for spontaneous-speech stress.
- AISHELL-4: use a test/evaluation subset for research validation.
- FSD50K: retain `*_clips_info_FSD50K.json` and split CSV metadata beside audio. The scanner accepts only clips whose per-clip metadata looks CC0/CC-BY and whose labels are non-speech; this is still research-only and does not replace legal review.
- WHAM: test material only; NonCommercial means research-only.

Always review current upstream terms before acquisition or redistribution. The repository catalog is an engineering guardrail, not legal advice.

## Immutable source manifest

Do not hand-author selected-file hashes. Scan the materialized cache:

```bash
python3 validation/tools/prepare_extended_validation.py scan \
  --catalog validation/extended.datasets.lock.json \
  --data-root /opt/audio-validation-extended \
  --profile commercial-core \
  --limit-per-dataset 48 \
  --output /tmp/extended-source-manifest.json
```

The scanner performs stable selection and hashes every selected audio file with SHA-256. Before corpus generation, verify all selected files again:

```bash
python3 validation/tools/prepare_extended_validation.py verify \
  --catalog validation/extended.datasets.lock.json \
  --data-root /opt/audio-validation-extended \
  --manifest /tmp/extended-source-manifest.json
```

A changed file, missing file, changed catalog, missing required dataset or usage-class drift fails closed.

## Implemented acoustic methods

The extended builder currently produces these families when their profile sources are present:

- RealMAN real far-field enhancement cases, with CH0/CH1 dual-mic use when available and direct-path speech references;
- RealMAN static/moving source coverage and distance metadata/buckets when present upstream;
- Mini LibriSpeech clean speech convolved with measured BUT RIRs and mixed with BUT/MUSAN noise;
- measured-RIR one-mic NS cases;
- measured-RIR two-mic BF cases using distinct measured responses;
- MUSAN music/noise VAD/NS hard negatives;
- VOiCES real distant-room speech stress and distractor hard negatives;
- AMI array-meeting stress;
- ICSI spontaneous meeting stress;
- AISHELL-4 Mandarin meeting stress in research mode;
- permissive-filtered FSD50K environmental hard negatives in research mode;
- WHAM noise/reverberation stress in research mode.

All generated PCM and case manifests retain upstream per-file SHA-256 provenance through the source manifest.

## Metrics and gates

Extended validation retains SI-SDR, ERLE, render correlation, VAD and noise attenuation and adds product-oriented failure signals:

- peak and RMS level;
- output/input RMS delta;
- clipping fraction;
- DC offset;
- VAD precision/recall/F1;
- VAD false-positive and false-negative rates;
- noise-only attenuation;
- speech-active attenuation;
- p10 tail SI-SDR improvement;
- p10 tail noise attenuation;
- per-scenario case counts and pass rates;
- required dimension values such as static/moving coverage.

The purpose of tail/scenario gates is to prevent a strong average from hiding a broken moving-source, far-distance, meeting or negative-noise subgroup.

## Blind holdout

Commercial extended validation uses the repository-external `AP_VALIDATION_HOLDOUT_KEY` and scenario-stratified HMAC partitioning:

```bash
python3 validation/tools/split_holdout.py \
  --corpus extended-out/corpus/corpus.json \
  --validation-output extended-out/corpus/corpus-validation.json \
  --blind-output extended-out/corpus/corpus-blind.json \
  --holdout-percent 20 \
  --stratify scenario
```

For strata containing at least two cases, both visible and blind partitions retain the stratum. The blind key never enters Git or an evidence artifact; only its fingerprint is recorded.

## Manual workflow

Run **Extended Real Validation** with an exact 40-character commit SHA. The workflow performs:

```text
exact SHA
  -> audio-validation runner preflight
  -> license catalog validation
  -> stable source scan + per-file SHA-256
  -> source-manifest re-verification
  -> exact processor build
  -> corpus generation
  -> scenario-stratified holdout
  -> visible policy enforcement
  -> blind policy enforcement
  -> evidence SHA256SUMS + artifact
```

Research mode skips shipping-like blind authority and emits `RESEARCH_ONLY_NOT_SHIPPING_AUTHORITY`.

## Automatic validation

`Extended Real Automation` is intentionally a thin dispatcher to the same canonical workflow:

- a published GitHub Release dispatches `commercial-core` against the exact release tag commit;
- Sunday 03:17 UTC dispatches `commercial-plus` against the current exact `main` SHA;
- research remains manual.

Automation is fail-visible. Set repository variable:

```text
EXTENDED_REAL_ENABLED=true
```

only after the isolated runner and required materialized datasets genuinely exist. Optional variable:

```text
EXTENDED_REAL_DATA_ROOT=/opt/audio-validation-extended
```

changes the runner cache root. If `EXTENDED_REAL_ENABLED` is absent or false, the hosted automation job fails with `EXTENDED_REAL_REQUIRED_BUT_DISABLED` and does not allocate a self-hosted job. This is infrastructure state, not an acoustic product failure.

## Activation sequence

1. Materialize `commercial-core` sources.
2. Run `tools/runner_preflight.py` with `--extended-catalog` and require `READY`.
3. Manually run commercial-core against the exact candidate/release SHA.
4. Run its scenario-stratified blind holdout and inspect failures/diversity.
5. Materialize VOiCES/AMI/ICSI and run commercial-plus.
6. Only after repeated successful manual runs set `EXTENDED_REAL_ENABLED=true`.
7. Keep research corpora isolated from commercial evidence.
8. Continue to require real DUT HIL and formal Product Certification for shipping.
