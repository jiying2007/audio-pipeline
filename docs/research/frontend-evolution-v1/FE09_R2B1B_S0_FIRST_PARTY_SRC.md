# FE09-R2B1B-S0 — N-mic + render first-party SRC research
# 第一方四麦及回声参考多采样率输入验证

Preregistration: https://github.com/jiying2007/audio-pipeline/issues/737
Parent: https://github.com/jiying2007/audio-pipeline/issues/733
Device gate: https://github.com/jiying2007/audio-pipeline/issues/730

**Status: research-only; not a public 3.x SDK or shipping admission.**

## Predecessor / 前置准入

B1A issue #735 is CLOSED completed, source main 4a9ff202862832581cce6990476fbc6216ffbf5e. Exact fresh-main Verify 38367239379 passed 64 jobs and one expected skip with required summary success. Same-source Release 38371240119 passed release and convergence. B1A fresh-main metadata Artifact 11798300162 was independently rehashed (ZIP SHA256 7cda1d9d093f335b169ee620de3bcf9d381273bcaefafd405f5b7b4d87acfa35).

## What executes / 实际执行内容

The only new implementation is the PRIVATE test-side adapter fe09_b1b0_src.[ch]. Its signal conversion calls the unchanged existing first-party src/frontend/ap_resampler.c, linked as its own translation unit. Source SHA256 is pinned as 5bf5e725dfdc516d82dce145b93ef881b1348bae17d2bd04130e7feb15834aff. No coefficients or SRC kernels have been copied. This is a real executable source-linked converter, not a stub.

The existing old resampler has three logical histories for the current two capture sources plus a distinct render. Directly raising the existing 2.x macro to four mics is unsafe: the third stream aliases the legacy render state. S0 instead allocates one independent complete ap_resampler_state_t for EACH physical microphone and another for the optional render, each invoked with an always-in-bounds stream index zero. This deliberately overallocates unused legacy history slots; it is not the future C4 memory optimization. A tiny generated audio_pipeline_build.h exists only inside a temporary test directory to select AP_BUILD_RESAMPLER_BANDLIMITED and never affects installed headers, CMake or shipping binaries.

## Frozen software matrix / 冻结的测试矩阵

| Physical scene | Mics | Physical-to-input slot mapping | Independent mono render | Mask from frame 70 |
|---|---:|---|---:|---:|
| C1_BASELINE | 1 | 0 | 0 | 1 |
| C2_ULA | 2 | 1,0 | 1 | 1 |
| C4_ULA | 4 | 2,0,3,1 | 1 | 13 |
| C4_UCA | 4 | 3,2,1,0 | 1 | 13 |

At EACH of 16k, 32k and 48kHz I/O, the four scenes are executed with 10ms input (160, 320 or 480 signed S16 samples per physical mic). The output is always 160 Float32 samples per physical mic and optionally a separate 160-sample mono render. Render shares the *specified test rate*, but NEVER shares a physical capture slot or SRC history. 16k is identity (no rate change); 32/48k execute actual first-party FIR decimation. The legacy kernel reports input-filter delay 0/5/7 samples respectively; no total end-to-end latency is certified.

The synthetic source lasts 100 accepted frames, replayed twice from fresh state for each of the 12 fixed profiles. The source skips a genuine capture input index at frame 50 and notifies a capture gap, applies physical active-mask control at frame 70, skips a true independent render index at frame 80 and notifies render gap, then notifies one clock reset at frame 90. No fake source timestamp is supplied. Masked physical input still advances only its OWN real capture history, but its output floats are explicitly zero. The three epochs and cumulative accepted count are distinguished.

Every frame is compared to a separate invocation of the SAME first-party resampler on independent per-source oracle state, with exact physical slot selection and ref isolation. Additionally, 16k samples are compared to the B1A normalized S16 identity expression. This is an engineering function and ownership test, NOT an independent FIR-quality benchmark or BF/DOA estimator.

## Bounded state, failure atomicity / 内存与异常处理

Configuration-specific, caller-owned and 16-byte-aligned state includes N+optional-render complete existing resampler state objects, no heap, locks or blocking I/O in callbacks. Validate all exact scalar counts and all non-overlapping pointers before committing history or output, and reject malformed descriptors, slot duplicates, zero/overwide masks, count=3, render=2, unsupported 8k/24k/44.1k, missing/extra reference and partial frames. Invalid epoch flags, insufficient/misaligned state and uint64 counter overflows fail without state/output mutation. Capture gap resets only capture histories; render gap only render; clock reset both available domains. Source-clock authority must remain zero (UNKNOWN).

Test-only C harness exercises at least 33 negative operations per scene including whole-state and buffer snapshots, independent uint64 overflow faults, exact source-to-buffer mapping, two fresh-run fingerprints, filter-delay and epoch contracts. Native C11, ASan+UBSan and AArch32 GNU/QEMU each compile and execute the genuine first-party source. Cross-target compare source, rates, controls and negative counts, while compiler-private sizes and Float32 hashes need not match bitwise. Missing tools fail closed. The actual old SRC translation unit has its existing -Wall/-Wextra/-Werror assurance; the NEW research wrapper/harness also requires -Wconversion/-Wshadow/-Wpedantic, no fast math and no FP contraction.

## Evidence and release / 证据和发布边界

Existing Quality/frontend-reference runs the bounded Python collector/verifier with actual source HEAD, source+compiler+binary SHA256, strict JSON, two within-target execution replays, cross-target invariant checks and single small four-file, 30-day metadata-only Artifact. Files: receipt.json, collect.log, verify.log, SHA256SUMS. No raw PCM, binary, large spatial dataset, third-party DSP code, new workflow or paid service. Docs/Verify uses the same first-party script's offline self-test.

Allowed success decision: FE09_R2B1B_S0_FIRST_PARTY_N_RENDER_SRC_RESEARCH_ONLY_NO_RELEASE.
On any failure: FE09_R2B1B_S0_SRC_OR_CLOCK_OWNERSHIP_NOT_ADMITTED.

Do not call the S0 gate complete from a local test or PR-head CI alone. Required: exact-head full Verify summary success, active strict/squash-only Ruleset 21804005, no unresolved threads, protected expected-head squash, independent new-main Verify plus same SHA Release, and independent new-main ZIP and inner SHA256 rehash. Keep the parent #733 and #730 OPEN.

## Explicit nonclaims / 未完成

Only 16/32/48k at a single common synthetic I/O rate are admitted. 8/24k, asynchronous capture/DAC clocks, full-duplex reference synchronization, microphone calibration/ADC sample-zero, actual BF or render-to-AEC, NS/AGC/VAD, speech intelligibility, objective aliasing/SNR/passband claims, SSC305 CPU p99/thermal/power/HIL, total C4 192KiB, new 3.x ABI/SDK, E001 or commercial RealMAN rights are NOT QUALIFIED. BF integration must later reuse the single authoritative first-party array_native.c and be preregistered separately. No 2.x shipping changes, no resurrection of original RealMAN D1/S3/S5 failed protocols, no unfreezing I025-I040.
