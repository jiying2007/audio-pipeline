# FE03 A2 D2-T0 — native Xiph reference FLAC toolchain qualification / 原生 FLAC 参考工具链准入

## Frozen independent preregistration / 独立预注册

Research issue [#709](https://github.com/jiying2007/audio-pipeline/issues/709) was registered **before official source build or any native toolchain proof**. This is a synthetic-only, non-commercial reference decoder feasibility step, **not** a retest of failed [D2-S3 #707](https://github.com/jiying2007/audio-pipeline/issues/707) and not a change to the preinstalled-only requirement or failed results of [draft PR #708](https://github.com/jiying2007/audio-pipeline/pull/708). The successful closed [D2-S2 #705](https://github.com/jiying2007/audio-pipeline/issues/705) remains unchanged.

**Exactly one frozen upstream:** official [xiph/flac](https://github.com/xiph/flac) Git tag `1.4.3` at immutable **`28e4f0528c76b296c561e922ba67d43751990599`**. Upstream `src/flac/CMakeLists.txt` names target `flacapp` with executable filename `flac`, verified before the experiment; this is the only native candidate. The CLI is GPL-licensed; no binary, third-party source package, or raw data is uploaded or redistributed.

## Fixed source and build policy / 源码与构建约束

- Clone once from only `https://github.com/xiph/flac.git` with Git shallow single-tag ref; reject source HEAD differing from frozen commit, dirty tree, unsafe symlink or over-128-MiB source. Max 120 seconds to clone; no fallback host, branch, source version or alternate source.
- Use **only preinstalled** Git, C compiler, CMake and build tools on free GitHub-hosted Ubuntu. Build out-of-tree, target **`flacapp`** using fixed `-DCMAKE_BUILD_TYPE=Release -DWITH_OGG=OFF -DBUILD_CXXLIBS=OFF -DBUILD_EXAMPLES=OFF -DBUILD_DOCS=OFF -DBUILD_TESTING=OFF -DBUILD_PROGRAMS=ON -DBUILD_SHARED_LIBS=OFF -DINSTALL_MANPAGES=OFF`; disable sharing/packaging. Configure/build at most 8 minutes total, 2 parallel build jobs, max 64 MiB output CLI. No sudo, apt, pip, downloaded binary, privileged runner, shared audio/cache, paid resource, or shipping code.
- Record official commit, tree, source-tree byte count, compiler/Git/CMake versions and preinstalled tool executable digests, compiled native CLI `flac 1.4.3` executable SHA256 and size; all outputs ephemeral except metadata-only receipt and logs.

## Exactly synthetic lossless byte proof / 只使用合成数据

- First-party deterministic **257-sample signed little-endian 16-bit mono 48 kHz** PCM fixture: deliberately spans signed extremes, fixed generation and byte length **514**. Encode using **the same just-built reference CLI**, then decode using `--silent --decode --stdout --force-raw-format --endian=little --sign=signed`, without WAV header, resampling, downmix, trimming, gain or denoise.
- Require decoded PCM length 514 and **complete bit-for-bit equality**, MD5 and SHA256 equality, exact native reference tool exit status. A deliberately truncated synthetic FLAC cannot produce an accepted full 514-byte stream and complete digest. No SNR, DER, GCC-PHAT, DOA, beamforming or other audio quality scores.
- **Independently verify** with second synthetic enc/dec run and reread the just-built binary SHA, official source commit/tree, canonical receipt and reproducible output hashes. Delete all synthetic WAV/PCM/FLAC files, compiled binary and upstream working tree before Artifact upload.

## Evidence and fail-closed governance / 证据与门禁

Only `REALMAN_D2_T0_XIPH_FLAC_1_4_3_NATIVE_CLI_TOOLCHAIN_QUALIFIED_SYNTHETIC_ONLY` after exact official revision, native command, two full synthetic positive and negative controls, fixed bounds and second independent receipt verification. Otherwise retain `REALMAN_D2_T0_NATIVE_DECODER_NOT_QUALIFIED` with the actual failure code. Reuse existing pinned `.github/workflows/research-development-dataset-source-vetting.yml` (new single path-scoped T0 job; no new orchestrator) and existing full Verify offline self-test. Upload only `receipt.json`, `collect.log`, `verify.log`, `SHA256SUMS` with 30-day retention, no binaries, third-party code or audio.

Protected merge requires exact-head full Verify `summary=success`, actual hosted T0 source/build/synthetic Artifact and independent ZIP + hash readback, zero unresolved review threads, existing active Ruleset 21804005 and expected-head squash. After merge require fresh-main Verify, same-SHA Release and new independent T0 source evidence before closing #709. **Never treat a PR's synthetic merge checkout SHA as PR HEAD.**

**Explicit nonclaims / 不扩大解释:** T0 is *synthetic reference CLI only*. It does **not** decode any actual RealMAN samples, does not convert failed #707 into success, does not validate captured CH1/3/5/7 microphone clock alignment, ground-truth source angles, BF/DOA/AEC/NS quality, SSC305 resources/latency/HIL, E001, product shipping or commercial licensing. A future separately preregistered D2-S3R may reuse a **fully qualified pinned toolchain** plus unchanged original S2 source identities; original D1 CSV remains blocked. Frozen I025–I040 and shipping DSP untouched.
