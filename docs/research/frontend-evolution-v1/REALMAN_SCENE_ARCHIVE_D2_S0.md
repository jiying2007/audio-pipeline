# FE03 A2 D2-S0 — RealMAN scene archive metadata preflight / 场景档案元数据预检

## Frozen authority / 冻结研究边界

This first-party, no-cost, **noncommercial research-only** source step is independently preregistered at [#701](https://github.com/jiying2007/audio-pipeline/issues/701), after D1-Q protected [PR #700](https://github.com/jiying2007/audio-pipeline/pull/700) closed on main `4ea71ff7bd2717c9d56cbfc06197f9958107d42e` with [fresh-main Verify 38027344338](https://github.com/jiying2007/audio-pipeline/actions/runs/38027344338), [Release 38028788021](https://github.com/jiying2007/audio-pipeline/actions/runs/38028788021), and [pinned source vetting 38027344134](https://github.com/jiying2007/audio-pipeline/actions/runs/38027344134) all successful on exactly that main SHA.

The official dataset revision remains **AISHELL/RealMAN@fea47505cae8041f4b652b0954ba61c77d2b6df1**. Source geometry revision **Audio-WestlakeU/RealMAN@9dc59f03a98149bc7fe5524d1363af83a5b399f7** is separately pinned by D0. The input role is exclusively `val/ma_noisy_speech`: *mixed/noisy, disclosed-development*, neither `val_raw`, clean microphone capture, an untouched blind holdout, nor a PCR02 enclosure recording.

Original source CSV SHA-256 identities remain static `1f0be80d4ab1cc023e7599bf7e564f84acaf36ccad73fd59c992cc9e853f1233` and moving `542f04d011c2b6fbdd49bfa51c423942fe854e7e0615fb1f67954c762ad20bf5`. Original D1 **failed source admission** due 544 Car-Electric static `-10000` distance labels; the independently registered D1-Q whole-scene *metadata-only* diagnostic has **3218 static + 2909 moving retained rows in 13 shared scenes**. No `-10000` placeholder meaning, physical distance correction, source-clock synchronization or product qualification was approved.

## Exactly 13 preregistered scene names

Auditorium, BadmintonCourt1, BasketballCourt1, BasketballCourt2, Cafeteria3, Gym, LivingRoom6, LivingRoom8, Market, OfficeLobby, OfficeRoom1, OfficeRoom3, SunkenPlaza1.

These are **label-scene candidates only**. No corresponding archive, scene member, physical microphone file, or static/moving utterance is assumed to exist merely because a CSV has a matching scene name.

## Boundaries of official metadata acquisition / 有界远端只读

`realman_scene_tree_d2_s0.py` is the only new read-only metadata collector. It uses the exact-revision official Hugging Face dataset-tree endpoint at `/api/datasets/AISHELL/RealMAN/tree/<revision>/val/ma_noisy_speech`, with `recursive=false`, `expand=false` and only a strictly validated provider pagination cursor. It never visits a `/resolve/`, `/raw/`, RAR or FLAC URL, and never requests original speech bytes.

- Only HTTPS on the precise `huggingface.co` host and frozen tree path; cross-host redirects, mutable refs, arbitrary query fields and injected token URLs are rejected.
- Up to **5 JSON pages**, **2 MiB per page**, connection/read time limits, and bounded list length. Invalid JSON, duplicate keys and file paths, unexpected nesting, source role or missing positive file size reject the source catalog.
- Record Git blob identity and available remote LFS SHA-256/declared size for each of the 13 fixed scene archives. A remote LFS oid is **a provider-reported digest only**, not independent verification of archive bytes. A missing or malformed expected SHA-256 is an explicit **fail-closed reason**; never infer a byte hash from the 40-hex dataset revision or Git blob ID.
- Report unexpected provider entries, missing preregistered scenes and declared total bytes. Metadata size is for capacity planning, not an authorization to download bulk archives, purchase hosted storage or choose a favorable scene.
- Preserve source execution SHA and the D0/D1 and D2 code digests in the canonical receipt. For PR runs, `execution_sha` binds the actual synthetic-merge checkout; for postmerge main it binds the real main SHA.

The **existing** Research Development Dataset Source Vetting workflow runs the D2-S0 job on path-scoped PR and main pushes. Offline negative tests also run in the existing Verify docs/assurance gate; there is no new generalized workflow, privileged runner, paid dependency, public SDK, version, C API, model or acoustic evaluator. The job keeps raw API response JSON only under `RUNNER_TEMP`; its 30-day Artifact contains `receipt.json`, `collect.log`, `verify.log`, and a checked `SHA256SUMS`, not original CSVs or archive bytes.

Local offline regression (synthetic provider list only):

```sh
python3 tests/validation/frontend_evolution/realman_scene_tree_d2_s0.py self-test
```

Actual CI invokes `collect --workspace "$RUNNER_TEMP/realman-d2-s0" --receipt realman-d2-s0-evidence/receipt.json`, then independently `verify` over precisely those ephemeral raw response JSON pages. Failed source retrieval, metadata schema, missing scenes or remote digests are **not** treated as success; preserve the failure receipt and logs without weakening acceptance requirements.

## Terminal scientific disposition / 研究结论边界

- `REALMAN_D2_S0_ARCHIVE_METADATA_CATALOGUED_ONLY`: only an exact provider-revision directory/catalog structure and externally declared archive identities/sizes have been checked. **It does not verify an archive's byte SHA, existence of internal 4-mic FLAC members, per-channel 48-kHz sample format, clocks, recorded audio or DOA error.**
- `REALMAN_D2_S0_ARCHIVE_METADATA_NOT_ADMITTED`: missing/inaccessible/ambiguous source metadata, unsafe redirect, limit breach, malformed digest or preregistered scene mismatch; the exact failure is recorded. No source/score role promotion.

A future independent D2 audio-byte admission must first explicitly preregister bounded archive size and transfer feasibility **after observing actual remote sizes**, inspect full members, verify original archive SHA-256 and four exact native channel byte IDs `CH1/CH3/CH5/CH7`, then establish audio/video and source-label time origins before any scored GCC-PHAT/DOA experiment. No original raw audio is redistributed. Accepted AISHELL CC BY-NC 4.0 **noncommercial and attribution** limitations apply separately from third-party code and commercial PCR02 rights. FE03/FE09, 4-mic shipping SDK and SSC305 HIL remain unqualified.
