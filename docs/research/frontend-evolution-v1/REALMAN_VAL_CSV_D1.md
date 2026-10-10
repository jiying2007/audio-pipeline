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

Even a successful D1 **does not verify an audio archive, four real FLAC channels, 48-kHz format equivalence, recording↔camera timebase alignment, 10-Hz annotation synchronization, azimuth-error performance, C2/C4 SDK deployment, SSC305 p99/thermal/power, or Product Certification**. The original RealMAN val data are disclosed development samples, never a blind test set. Any recorded-signal DOA experiment must separately preregister data/audio and clock admission through [FE03 A2 #693](https://github.com/jiying2007/audio-pipeline/issues/693).
