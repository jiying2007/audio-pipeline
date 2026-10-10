# FE03 A2 D1 — RealMAN val CSV source-byte admission / 真实 CSV 准入

## Preconditions and scope / 前置与研究边界

This is the noncommercial, read-only source-byte research task frozen in [issue #697](https://github.com/jiying2007/audio-pipeline/issues/697). It starts only after D0 protected main 39a445d4c21d2f716e6602450a0bf944f248383b, fresh-main [Verify 38016025462](https://github.com/jiying2007/audio-pipeline/actions/runs/38016025462) (64 successes, one intentional skip, required summary success), and same-SHA [Release 38017881646](https://github.com/jiying2007/audio-pipeline/actions/runs/38017881646) (success). Those CI gates do not provide RealMAN acoustic accuracy evidence.

Dataset revision: **AISHELL/RealMAN@fea47505cae8041f4b652b0954ba61c77d2b6df1**. Geometry-source revision, a separate authority: **Audio-WestlakeU/RealMAN@9dc59f03a98149bc7fe5524d1363af83a5b399f7**. The more restrictive AISHELL CC BY-NC 4.0 data notice is accepted for this explicitly noncommercial research with attribution. Do not imply commercial deployment, redistribution of original audio or rights to third-party code and weights.

Exactly **two original CSV byte streams**, fetched independently from immutable provider-revision HTTPS paths:

- val/val_static_source_location.csv
- val/val_moving_source_location.csv

No dataset partition, RAR, FLAC, WAV or recorded microphone data is downloaded by D1. The unchanged D0 [contract](../../../.github/research/frontend-evolution-v1/realman-source-metadata-d0.json) and [first-party parser](../../../tests/validation/frontend_evolution/realman_source_metadata_d0.py) remain authoritative. Static/moving source annotation tables are parsed separately: optional differing Unnamed index headers are nonsemantic; missing or duplicate meaningful headers, conflicting file identities, bad timestamps, nonfinite values and malformed vector labels are rejected, never silently corrected.

## Network and evidence controls / 数据完整性

The existing **Research Development Dataset Source Vetting** workflow now contains one independently named, path-scoped D1 job on pull requests and postmerge main. Pinned checkout, pinned artifact action, no additional credentials, no pip packages or paid runner are required. All original CSV bytes remain temporary outside the git repository and are **not uploaded** in the evidence artifact or release assets.

The sole approved provider URL pair is constructed internally; only HTTPS and provider-controlled HF redirect hosts are accepted. Each stream has a hard **16 MiB cap**, bounded reads and timeout, and rejects empty, truncated, HTML, encoded or malformed responses. No alternate revision/source/file is automatically substituted to obtain a PASS.

The resulting 30-day GitHub Actions artifact contains:

- canonical receipt with original raw SHA-256, byte sizes, semantic headers and counts, filename range, common source-label scenes, execution checkout SHA, parser/contract/script hashes and no-product/no-audio authority
- separate bounded fetch/admission and independent raw-byte rehash/reparse verification logs
- SHA256SUMS for the receipt and both logs

For a PR event the execution SHA is the **actually checked-out synthetic merge commit**, not a renamed PR head; on postmerge main it is the real main commit. Successful evidence requires matching source revision and both independently parsable original CSVs. A real upstream failure is retained as a red job with a failure-code receipt; it is not replaced by a synthetic fixture, and the required full Verify summary is not weakened.

## Reproduction / 复验

Offline synthetic-fixture guard, with no network:

    python3 tests/validation/frontend_evolution/realman_val_csv_d1.py self-test

The Actions job separately invokes the **admit** and **verify** commands with the identical ephemeral workspace and evidence receipt. Offline guards also remain in the existing Verify assurance gate; actual network-source admission remains in the dedicated source-vetting workflow.

Possible decisions:

**REALMAN_VAL_CSV_BYTES_VERIFIED_METADATA_ONLY** — both original source CSVs independently pass source-byte hash, bounded-size, semantic schema, row and identity checks.

**REALMAN_VAL_CSV_SOURCE_ADMISSION_BLOCKED** — explicit fail-closed reason such as REMOTE_METADATA_INACCESSIBLE, SOURCE_BYTES_TOO_LARGE, CSV_SCHEMA_MISMATCH or TIMESTAMP_REPRESENTATION_UNRESOLVED, without data promotion.


## Actual frozen-source anomaly / 本轮真实标注异常

The first real-source D1 audit [run 38018616730](https://github.com/jiying2007/audio-pipeline/actions/runs/38018616730) downloaded **both** original `val` CSVs at the pinned dataset revision and retained evidence artifact `11656539339`:

| Raw CSV | Bytes | SHA-256 | Original D0 result |
| --- | ---: | --- | --- |
| Static | 667203 | `1f0be80d4ab1cc023e7599bf7e564f84acaf36ccad73fd59c992cc9e853f1233` | `CSV_SCHEMA_MISMATCH` |
| Moving | 2458884 | `542f04d011c2b6fbdd49bfa51c423942fe854e7e0615fb1f67954c762ad20bf5` | 2909 rows, 13 scenes parsed |

The static file has **3762 source rows**, **544 rows with negative distance**, zero exactly-zero values, zero nonfinite values and zero nonnumeric distance rows. This is a field-level anomaly, not proof the raw CSV was unavailable or a valid source label was admitted. The original RealMAN NeurIPS 2024 paper ([arXiv 2406.19959](https://arxiv.org/pdf/2406.19959), paper pages 7 and 17) describes *physical source-to-array distance* computed from a calibrated fisheye camera and reports most physical distances around 0.5–5 m. It does **not define a negative-distance sentinel** in the consulted sections.

A [pre-execution source-diagnostic addendum](https://github.com/jiying2007/audio-pipeline/issues/697#issuecomment-6093336455) therefore fixes a **nonpromotable** bounded audit: histogram of negative constants, scene aggregates and finite negative range, together with readback consistency and receipt-tamper rejection. These are not calibration, row exclusion, censoring, corrected coordinates or a substitute for frozen D0's strictly positive physical-distance requirement.

Do not turn a negative physical distance into a valid measurement by clamping, taking the absolute value, assuming a sentinel or silently discarding 544 records. A future field-specific angle-only data role requires its own explicit preregistration and review before use. The current decision remains `REALMAN_VAL_CSV_SOURCE_ADMISSION_BLOCKED / CSV_SCHEMA_MISMATCH`.

Even a successful D1 **does not verify an audio archive, four real FLAC channels, 48-kHz format equivalence, recording↔camera timebase alignment, 10-Hz annotation synchronization, azimuth-error performance, C2/C4 SDK deployment, SSC305 p99/thermal/power, or Product Certification**. The original RealMAN val data are disclosed development samples, never a blind test set. Any recorded-signal DOA experiment must separately preregister data/audio and clock admission through [FE03 A2 #693](https://github.com/jiying2007/audio-pipeline/issues/693).

## Distinct D1-Q protected-main qualification / 独立派生元数据证据

[Preregistered D1-Q #699](https://github.com/jiying2007/audio-pipeline/issues/699) is a **new, score-blind whole-scene-quarantine diagnostic** after observing the original D1 failure; it is not an edit to #697's frozen full-CSV PASS criterion. Its initial executed [run 38021433972](https://github.com/jiying2007/audio-pipeline/actions/runs/38021433972) retained artifact `11658716690`. The source-only derived preview quarantines **all** Car-Electric rows: static original 3762 / quarantine 544 / retained 3218; moving original 2909 / quarantine 0 / retained 2909; unchanged D0 validator passed the 13 shared retained scene labels, with no DOA scores or file-selection.

On the separate D1-Q qualification PR, a source-vetting job can succeed *only* if it proves the **two simultaneous immutable findings**: (a) full original CSV D1 remains `REALMAN_VAL_CSV_SOURCE_ADMISSION_BLOCKED / CSV_SCHEMA_MISMATCH` and (b) a new `REALMAN_D1Q_SCENE_QUARANTINE_METADATA_DIAGNOSTIC_ONLY` receipt with exact original hashes, 544 excluded whole-scene static records and unchanged D0 validation of every retained label is regenerated and independently checked. Any changed upstream bytes, extra invalid labels, rejected derived rows, absent original artifact/manifest, false original D1 PASS, or other failure keeps the job red. **A green D1-Q job qualifies diagnostic execution, never original RealMAN CSV source admission.**

Retained semantic-row hashes for the **derived label-only** result are static `cf60c7775896a9426fb5f142be5de7af7f936ccfd2c02519edfb865fde006cc5` and moving `2f4d36cd8b6e9a39d14105387fc02736830e51202d6b05d1ada2468e6f6ee3c3`. No raw files, generated filtered CSV, FLAC or angle scores are committed or packaged. Validity of individual physical recordings, capture-to-camera clocks, dynamic source timestamps and C2/C4 deployed DSP are still independent unanswered questions.
