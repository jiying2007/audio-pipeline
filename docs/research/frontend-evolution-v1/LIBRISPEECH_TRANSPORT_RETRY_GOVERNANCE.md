# LibriSpeech Source Transport — Bounded Retry Governance / 下载稳定性治理

**Preregistration:** [Issue #741](https://github.com/jiying2007/audio-pipeline/issues/741). This is independent of FE09-R2B1B-S0 [#737](https://github.com/jiying2007/audio-pipeline/issues/737). No product or measured sound-quality promotion is authorized.

## Original failure / 原始失败

Protected main 2c2ff18c5c5c7957ad48e45c523c28c6242c7aed, [Verify 38408813450](https://github.com/jiying2007/audio-pipeline/actions/runs/38408813450) attempt 1: existing frontend-spatial-effects job 115336039871 failed while reading the official LibriSpeech dev-clean archive through Python urllib/SSL, raising a genuine TimeoutError. The original [failure Artifact 11819528760](https://github.com/jiying2007/audio-pipeline/actions/runs/38408813450/artifacts/11819528760) retained preflight metadata but no detailed source-failure.json because the source folder was excluded from the upload. This is NOT a measured DSP regression or a spatial/AEC pass.

## Bounded retry / 有界化重试

The source remains exclusively https://www.openslr.org/resources/12/dev-clean.tar.gz; original frozen MD5 42e2234ba48799c1f50f24a7926300a1, archive size bound 400,000,000, source/license notices, speaker offset selection 0/8, tar path/size, native FLAC and FFmpeg checks remain UNCHANGED.

Only explicit transient socket timeout/reset, incomplete HTTP read, remote disconnect or unexpected SSL EOF may retry, including an urllib URLError with such a transport cause. **At most three entire fresh attempts** with the same original URL, 60-second socket timeout and deletion of all partial local bytes each time. Both existing source-acquisition quality jobs have a fixed **20-minute** maximum runtime (previously 15 minutes); no unbounded retry loop or alternate source is allowed. No alternate source, mirror, insecure TLS, partial resume, fabricated PCM, source sample clock or test-score threshold changes.

HTTP 403/404/500, unexpected HTTP status or redirect, certificate verification error, oversize data or source hash/format mismatch must FAIL CLOSED immediately. Original source acquisition retains DATA_OR_INFRASTRUCTURE_FAILURE as a non-acoustic verdict when all retries fail.

## Artifact retention / 失败证据

The original frontend-spatial-effects metadata Artifact gains only the optional source/source-failure.json entry; the original frontend-speech Artifact is narrowed to effects, FIR and optional source-failure.json so incomplete FLAC/PCM is NOT uploaded after failure. Retain preexisting evidence and avoid a duplicate audio archive.

The new test_speech_download_retry.py is standard-library-only and offline. It simulates partial-data timeout then success, wrapped resets, unexpected EOF, three exhausted failures, HTTP 403/404/500, certificate failures, redirect/status mismatch, size-bound rejection, and protection against overwriting an existing destination. It makes zero network calls and is invoked by the existing Docs/Verify gate.

## Stage authorization / 阶段准入

Do not merge ahead of B1B-S0 fresh-main Verify + matching Release. This independent code hardening requires full exact-head Verify summary success, strict active squash-only Ruleset 21804005, zero unresolved review threads, expected-head protected squash, independent new-main Verify and exact same-source Release.

**Explicit nonclaims:** no BF/DOA/AEC/NS/AGC/VAD gain, no SSC305 HIL CPU/thermal/p99, no hardware ADC clock calibration, no 3.x SDK, no RealMAN commercialization or E001 product release. Never reclassify original failed Actions run to success.
