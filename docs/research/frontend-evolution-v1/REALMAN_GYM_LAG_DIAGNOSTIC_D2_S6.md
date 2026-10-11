# FE03 A2 D2-S6 — Original Gym lag/coherence observations / 原始四麦时延相干性诊断

## Independent scope / 独立预注册

This research study was independently [preregistered as #723](https://github.com/jiying2007/audio-pipeline/issues/723) before S6 implementation and any S6 original-audio run. Implementation did not start until previous protected-main CI hardening #722 completed exact [Verify 38143015640](https://github.com/jiying2007/audio-pipeline/actions/runs/38143015640) (64 successful jobs, one expected skipped, required summary success) and [Release 38145090533](https://github.com/jiying2007/audio-pipeline/actions/runs/38145090533) (release + convergence success), for `main=5cdf7cac5814b3ae990fec48465b2c7da2e39f03`. This is disclosed, **not blinded** development diagnostics.

The published NeurIPS source [S5R #720](https://github.com/jiying2007/audio-pipeline/issues/720) only supports the paper authors' clock-synchronized four-eight-channel **design assertion**. This project has not independently established a common ADC sample-zero, sample-accurate synchronized distributed Gym files, microphone residual timing drift, polarity/gain calibration, image↔audio numeric time origin, or original label timestamp join. **No correlation/lag peak may be converted into such a claim.**

## Exactly one source, eight frozen originals / 已冻结的原始音频

- `AISHELL/RealMAN@fea47505cae8041f4b652b0954ba61c77d2b6df1`; one `val/ma_noisy_speech/Gym.rar`, **447127176 bytes**, SHA256 `8175dad412a752a34bdf2722f7e9b5ee671b62e67dfe5179f7a769d63912b2ea`. No other scene, partition, external mirror, source CSV, camera video or favorable resampling. This one RAR was actually bytes-qualified previously, not a guessed content URL.
- Exactly the previously frozen lexical-first static and moving four-FLAC families, original physical `CH1/3/5/7`, as independently sealed in [S2 #705](https://github.com/jiying2007/audio-pipeline/issues/705) and source-built FLAC reference [S3R #711](https://github.com/jiying2007/audio-pipeline/issues/711). Selection SHA256 `7b6458adc4d335c6c1897f98e51501f897585623359ef147494d7635d4d9be37`. Original eight per-FLAC bytes, native STREAMINFO MD5 and S3R decoded PCM SHA256 are **individually revalidated**.
- Static 238895 signed-16-bit samples/channel, moving 237071 samples/channel, both mono 48kHz. Same-runner Xiph FLAC `1.4.3` source-built with pin commit `28e4f0528c76b296c561e922ba67d43751990599` and tree `9d1cf0c77df717e633c9020eb60c87642beb9037`; its synthetic reference qualification is mandatory **before** original RAR network access. No apt/pip/sudo, paid runners, binary/executable copy from an Artifact or source substitution.
- Source evidence prior to S6: S3R original PCM hashes from previously retained metadata-only Artifact `11687520995`, independently SHA-256 verified ZIP `f21e77672841dba4a0cab16fa29047f8a2e524067d4b5c14bd1e9390f0a34743`. These hashes are **frozen in the S6 JSON contract** before this S6 new original-audio observation; they are not rescored or derived from output lag peaks.

## Fixed diagnostic — 36 records, no model search

For each static and moving 4-channel source, take exactly three **unshifted** 8192-sample windows at offsets `0`, `(N-8192)//2`, `N-8192`, and all six ascending unordered mic pairs `(1,3),(1,5),(1,7),(3,5),(3,7),(5,7)`. Exactly `2 × 3 × 6 = 36` records must be retained, **including null, weak, ambiguous, high-boundary and any unfavorable observations**.

Estimator: first-party pure-Python radix-2 FFT already present in A1, applied to raw signed S16LE normalized by 32768, symmetric Hann window, zero pad to 16384 FFT. GCC-PHAT bins `X_left×conj(X_right)/max(abs(cross),1e-12)`. Search only integer signed lag `[-16,+16]`, maximize `abs(real(ifft(GCC-PHAT)))`; ties choose lowest signed lag. Sign convention: if `right[t]=left[t-d]` for synthetic delayed right with integer `d`, returned lag is `-d`. **Absolute peak does not determine microphone polarity.** Sidelobe is max absolute IFFT correlation outside ±2 lags from selected peak; separation proxy is `(peak_abs-sidelobe_abs)/max(peak_abs,1e-12)`. RMS is `sqrt(mean((int16/32768)^2))` over the original unshifted window, no audio normalization or mean subtraction. Explicit `UNDETERMINED_SIGNAL` for constant windows or level ≤ one LSB, `UNDETERMINED_PEAK` for relative separation ≤1e-6, `OUT_OF_SEARCH_WINDOW_UNKNOWN` when selected peak sits at ±16, and `UNDETERMINED_NUMERIC` for invalid IFFT result. These values are frozen and **cannot** be tuned after source results.

RealMAN C4 physical geometry is inner cardinal positions of the original 32-mic array (radius 0.03m), not PCR02/SSC305 geometry; maximum aperture 0.06m. Nominal far-field travel is ~8.4 samples at 48kHz and 343m/s, but acoustic geometry, room reflections, source motion, crop offsets and hardware clock offsets are inseparable from observed speech cross-correlation. Neither three windows nor a stable peak measures sample-zero, drift, DOA truth, or BF quality. We explicitly **do not fit slopes, estimate source angle, optimize time alignment or apply a post-hoc shift**.

## Program and negative evidence

The CLI `tests/validation/frontend_evolution/realman_gym_lag_diagnostic_d2_s6.py` has standalone *offline* synthetic known-lag tests at ±3/±7 samples, uninformative silence/constant and truncated-signal tests, strict JSON duplicate-key checks and forged observation/status/authority negative checks:

```bash
python3 tests/validation/frontend_evolution/realman_gym_lag_diagnostic_d2_s6.py self-test
```

Actual-hosted source path: one existing first-party Source Vetting workflow job, new path-scoped to exactly the S6 research script/contract/docs. Always skip unrelated historical D1 original CSV and redundant S1/S2/S3R source transfers on S6-only changes. Same runner: pinned source-built CLI + synthetic reference → one exact 447MB RAR byte transfer → eight original FLAC and decoded PCM hash checks → 36 observations → independent rehash and second eight-PCM readback + exact 36-observation comparison. No extra dataset, sweeps, or new orchestration controller.

Artifact: **only** `receipt.json`, `collect.log`, `verify.log`, `SHA256SUMS` (30-day retention), with 36 numeric metadata records and exact tool/source SHA. No raw FLAC/RAR/PCM, waveform, binaries, images, source CSV, downloaded vendor code or publication text. Ephemeral RAR, FLAC, reference sources/binaries and synthetic files are deleted on all paths **before public upload**. No commercial/shipping authority.

## Two frozen terminal outcomes / 收口准则

Only when the full actual-hosted source/PCM/parity/36 observations and offline negatives pass:

`REALMAN_D2_S6_GYM_SPATIAL_LAG_DIAGNOSTIC_RECORDED_NO_CLOCK_AUTHORITY`

Otherwise:

`REALMAN_D2_S6_SOURCE_OR_DIAGNOSTIC_NOT_ADMITTED`

Both outcomes preserve all original Gym **sample-zero/clock drift/polarity/AV epoch/CSV time join UNKNOWN** and never claim DOA/BF/NS/AEC improvement, SSC305 physical CPU/p99/RSS/HIL or shipping. Historical failures D1 #697, D2-S3 #707/Draft #708, S5 #716/Draft #717 remain frozen. I025–I040, FE03 A1, B0, E001 and shipping C ABI stay unchanged.

No merge or #723 closeout until protected PR exact-head full Verify `summary=success`, actual source job success and independently downloaded SHA256 manifest Artifact, 0 unresolved threads, active strict/squash-only Ruleset 21804005, expected-head protected squash, then **distinct** new-main Verify+Release+original source Artifact independently reverified.
