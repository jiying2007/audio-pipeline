# FE03 A2 D2-S4 — Four-mic capture clock and source-label authority / 四麦采集时间基准审查

## Preregistered metadata-only question / 独立研究约束

This narrow noncommercial source audit implements [#713](https://github.com/jiying2007/audio-pipeline/issues/713), registered **before** code/metadata analysis. Its prerequisite [D2-S3R #711](https://github.com/jiying2007/audio-pipeline/issues/711) is CLOSED only after protected [PR #712](https://github.com/jiying2007/audio-pipeline/pull/712) merged main `1be9b89af778783bdbe695c72d048b3d77eee948`, fresh-main [Verify 38100098942](https://github.com/jiying2007/audio-pipeline/actions/runs/38100098942) **64 successes, one skip and required summary success**, matching [Release 38101857116](https://github.com/jiying2007/audio-pipeline/actions/runs/38101857116) success, [source vetting 38100098794](https://github.com/jiying2007/audio-pipeline/actions/runs/38100098794) **7/7 success**, and independently rehashed [Artifact 11687520995](https://github.com/jiying2007/audio-pipeline/actions/runs/38100098794/artifacts/11687520995). Frozen original 8/8 PCM-MD5 is valid **codec-byte proof only**, never an acquisition timing witness.

The specific scientific question: what authoritative, recording-specific evidence establishes that the four physical microphone channels **CH1/CH3/CH5/CH7** in the same Gym static/moving utterance share a single capture sample clock, known sample-zero, fixed per-channel drift, channel polarity and an origin that can be joined to the fisheye-camera source labels?

## Frozen metadata sources and two distinct kinds of evidence

1. Dataset **AISHELL/RealMAN** exact revision `fea47505cae8041f4b652b0954ba61c77d2b6df1`; frozen original `val/ma_noisy_speech/Gym.rar` **447127176 bytes**, SHA256 `8175dad412a752a34bdf2722f7e9b5ee671b62e67dfe5179f7a769d63912b2ea`. S2 sealed [Artifact 11669252369](https://github.com/jiying2007/audio-pipeline/actions/runs/38050714903/artifacts/11669252369) original receipt digest `16e690a4b32f0aeb9f011900af55f83f302a6f29662f2bb1601c058257ae3190`; eight original FLAC file hashes, physical channel IDs, 48-kHz/16-bit, lengths and per-file PCM-MD5 are frozen in first-party S3R anchor. **Do not download** 447MB RAR, any FLAC or PCM again for this S4 metadata study.
2. Official [Audio-WestlakeU/RealMAN](https://github.com/Audio-WestlakeU/RealMAN) pinned code revision **`9dc59f03a98149bc7fe5524d1363af83a5b399f7`**, retrieve **only three textual files** via immutable `raw.githubusercontent.com` URL with <=128 KiB/file and max 20s connection time. Compare exact Git blob SHA1 of each source, refuse redirect, unsupported encoding or unpinned path:

| Official source | Pinned original Git blob | Exact witness |
| --- | --- | --- |
| `README.md` | `a327db37ad48743725dc35cecfecfbca251e683b` | 32-channel recording claim and fisheye-camera annotations |
| `baselines/SSL/RecordData.py` | `affc5d50ca22751a7cf836b58865986164a55cb6` | File suffix `_CH{i}.flac`, separate per-channel load then NumPy stack; possible 16-kHz resampling/label slicing is **processing**, not clock authentication |
| `baselines/SSL/utils_.py` | `0f7554bbfd65f2c52a917526e277a264b325d102` | Native 32-sensor geometry: central microphone and 30/60/90-mm concentric rings |

3. Original D1-Q metadata-only exact-main [Artifact 11687810612](https://github.com/jiying2007/audio-pipeline/actions/runs/38100098794/artifacts/11687810612), ZIP SHA256 `645f53f5c262bfff6c02c5b9febb8bf02acdd210592d3e3c5a6009c6084b26cb`, receipt SHA256 `6aed993d727b32f047d4857324cd5ff8f248bdbc85844ac194b4b93d6838468a`. Original static CSV SHA256 `1f0be80d4ab1cc023e7599bf7e564f84acaf36ccad73fd59c992cc9e853f1233` and moving CSV SHA256 `542f04d011c2b6fbdd49bfa51c423942fe854e7e0615fb1f67954c762ad20bf5`. The original **full D1 CSV is BLOCKED**, because 544 Car-Electric static rows contain distance `-10000`; D1-Q whole-scene quarantine reports Gym among surviving shared scenes **but not a proven join of the eight hashed FLAC member stems to authoritative CSV timestamps**.

## How the audit treats evidence / 证据分类

The frozen D0 contract contains physical slot map `[1,3,5,7]`, native rate 48000 Hz, nominal 10-Hz label sequence and fields `real_st`, `real_ed`, `video_st`, `video_ed`, angle, distance and elevation. Source code confirms **software filename indexing** and **declared array geometry**, but does NOT by itself establish:

- Hardware-common multichannel ADC/sample clock and initial sample index.
- A known sample-zero origin relative to recording/video timestamps.
- Measured per-channel skew/drift, phase/polarity response or calibration.
- Exact camera-to-audio time-origin and moving source label alignment.
- An unambiguous recording-stem-to-original CSV-row join with sufficient timestamp information.

Every missing requirement receives `unsupported` rather than invented `proven`. If a later independent official device capture sheet provides all witnesses, the *next separately preregistered* study may test that exact evidence. Neither equal FLAC sample counts, SHA/MD5 agreement, `np.stack`, 10-Hz label rate nor a reconstructed cross-correlation can substitute for acquisition-source authority.

## First-party CI and decisions / 自动化审查

The validator cross-checks the frozen S2/S3R member metadata, D0 geometry/labels, D1-Q negative case and exact official Git blob bytes. It performs remote **text-only** readback in `collect` and again independently in `verify`, recording SHA, matching source line numbers and all unsupported clock authority fields. Offline negative tests mutate source hashes, unapproved URLs and false positive authority fields. S4 consumes **no RAR, FLAC, PCM, raw CSV rows, DSP metrics, upstream code bundle or executable**. Only metadata `receipt.json`, `collect.log`, `verify.log` and `SHA256SUMS` are retained for 30 days.

- `REALMAN_D2_S4_NATIVE_CAPTURE_TIMEBASE_DOCUMENTED_RESEARCH_ONLY` would require all original official acquisition clock and time-origin witnesses, NOT merely a matching code convention; **not claimed here**.
- **`REALMAN_D2_S4_CAPTURE_TIMEBASE_UNRESOLVED`** is an honest, evidence-complete source-audit outcome if the three pinned original source texts lack those witnesses. An audit workflow success means the negative/unknown classification was independently verified, **not a pass for physical synchronous capture or DOA qualification**.
- `REALMAN_D2_S4_SOURCE_METADATA_NOT_ADMITTED` blocks if pinned bytes/hash/schema/rights/timebase evidence is inconsistent or inaccessible; do not silently downgrade source errors to an unsupported finding.

Merge only through independent PR with original metadata readback, exact-head full Verify `summary=success`, zero review threads, unchanged active strict main ruleset and expected-head squash; then a *distinct* fresh-main Verify, Release, source metadata proof and independently checked metadata-only Artifact. Keep #713 open until the full governance closeout.

## No product promotion / 禁止扩大结论

This is disclosed-development noncommercial RealMAN research, with upstream attribution and no raw-data redistribution. Original preinstalled-only [#707](https://github.com/jiying2007/audio-pipeline/issues/707) / unmerged Draft #708 remain historical failures; full D1 CSV remains blocked. No original waveforms, source motion fitting, GCC-PHAT/DOA numerical scores, BF/AEC/NS performance, PCR02/SSC305 CPU/RAM/p99, E001 hardware qualification, commercial rights, shipping code or frozen I025–I040 research changes are authorized by this stage.
