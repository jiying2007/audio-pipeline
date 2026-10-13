# FE09-R2B0 — Next-major C1/C2/C4 migration preflight / 四麦统一 SDK 迁移前置审查

**Registration / 预注册:** [FE09-R2B #733](https://github.com/jiying2007/audio-pipeline/issues/733), parent [FE09-R2 #730](https://github.com/jiying2007/audio-pipeline/issues/730).

**Permitted B0 verdict:** `FE09_R2B0_MAJOR_MIGRATION_PREFLIGHT_RESEARCH_ONLY_NO_PUBLIC_ABI`.
**Failure / 不准入:** `FE09_R2B0_SOURCE_OR_MIGRATION_CONTRACT_NOT_ADMITTED`.
**Selected provisional architecture / 暂选架构:** `B_NEXT_MAJOR_SINGLE_PRIVATE_ARRAY_CORE` (independent R1, not an installed SDK).

## Scope and limits / 范围与边界

R2B0 is a **read-only, source-anchored design preflight**. It adds one JSON research contract, this bilingual architecture/cutover decision, one standard-library offline checker with negative mutation fixtures, and two calls in the **existing** Docs/Verify gate. **No** public `include/`, installed SDK, shipping `src/`, `CMakeLists.txt`, 2.x static library, device runtime, test waveform, metric scorer, new Actions workflow, release asset or C4 product API is changed.

The audited starting point is protected `main=6fcb74f5f498dc68fab6127d8bf9bf35411f7d61`. Independent prior-main [Verify 38330235032](https://github.com/jiying2007/audio-pipeline/actions/runs/38330235032) and same-SHA [Release 38333092634](https://github.com/jiying2007/audio-pipeline/actions/runs/38333092634) both succeeded, after [#732](https://github.com/jiying2007/audio-pipeline/pull/732) protected squash. Old lineage R2A main `36944fa85e180bdadbac5800bd7fe3cf35d6a619`, Verify 38325347248, Release 38327722158, independent original 4-file [Artifact 11780358590](https://github.com/jiying2007/audio-pipeline/actions/runs/38325347248/artifacts/11780358590) ZIP SHA256 `c15d83903a572ec51a07d2130c8e198d8628e25d9b55330ac51190acabb5f801`. **R2A is an uninstalled 16 kHz research-only adapter** and not an independently shipped 3.x major version.

The `.github/research/frontend-evolution-v1/fe09-r2b0-major-migration-contract.json` binds **34 distinct exact source anchors across 12 first-party source/docs files** and their original Git blob SHA-1 identities. That SHA-1 is Git object identity for reproducible source lineage; output also records independently computed SHA256 file digests. Source drift must trigger a new review, not an automatically accepted migration. The checker is source governance, not a C compiler, behavioral proof or external legal opinion.

## Current-source cutover matrix / 源代码迁移矩阵

| Workstream / 工作流 | Current actual code / 现有事实 | Required later cutover / 后续迁移门禁 |
|---|---|---|
| Public 2.x ABI | `include/audio_pipeline/audio_types.h` caps `AP_MAX_MIC_CHANNELS=2`; `CMakeLists.txt` is 2.3.55 and rejects >2; public `ap_config_t` and `ap_metrics_t` have no `struct_size`/`api_version` | New **separate** next-major public contract and consumer ABI tests, no by-value extension masquerading as 2.x compatibility |
| ABI sizing and lifecycle | `AP_PIPELINE_STATE_MAX_BYTES=80000`, `ap_pipeline_state_size(void)` and `sizeof(ap_pipeline_t)` are build-wide, not configuration-specific | Explicit B1 caller-owned per-configuration size/alignment, 32/64-bit checked arithmetic, reject without mutation; B2 public API only with independent major review |
| Capture BF path | `src/core/ap_pipeline.c` requires exactly two mics if BF is enabled; mic0/mic1 feed a mono downstream pipeline | B1 opt-in C1/C2/C4 data path with **one** authoritative first-party BF implementation and explicit per-mic geometry/slot/fault ownership |
| Capture SRC and render | `AP_RESAMPLER_INPUT_STREAMS=3` currently represents two capture histories plus **separate** render; `ap_resample_input_channel` is `void`, and bandlimited source directly indexes `input_history[stream]` | B1 checked **N physical mic** histories plus independently indexed zero-or-one DAC render history; no mic3 collision with old render slot |
| Linux runtime queues | `AP_RT_MAX_CAPTURE=AP_BUILD_IO_FRAME_MAX*AP_BUILD_MAX_MIC_CHANNELS`, runtime accepts interleaved capture + separate render and frame metadata | B2 experimental next-major capture capacity, backpressure, actor ownership, route reopen and thread-stack/queue bounds tested together |
| Flight Recorder | `src/platform/linux/ap_runtime.c` rejects recorder mic count >2; its slot stride scales with `frame_samples*mic_channels`; `AP_DUMP_FORMAT_VERSION=1` | B2 explicit **new on-disk reader/writer version**, endian/stride/mask/clock metadata, old v1 reader compatibility decision or clean break |
| BF/AEC topology | Existing C2 pipeline BF then mono SYNC/AEC; R2A render stream is *observed*, not fed to AEC | B3 independent pre-registered paired BF→AEC vs per-mic AEC→BF with double-talk/motion/echo negatives; no oracle selection |
| Device and acoustics | R0 C4 FIR33 = 3,704 B; old mono SDK = 78,192 B; no complete C4 application footprint | B4/R2C distinct SSC305 vendor BSP CPU p95/p99, 10ms deadline, RSS/stack/thermal/power, real ADC clocks, channel calibration, E001 |

**Do not** implement direct public C4 by raising one max-mic macro, assigning render SRC index 2 to a physical microphone, or appending C4 state to the old 80,000-byte arena. The **81,896 B** R0 C4-array + mono-state sum already exceeds that old ceiling by 1,896 B, *before* FIFO, scratch, recorder, threads, native resampler and diagnostics.

## ABI and memory ownership / ABI与内存归属

The future candidate accepts physical `mic_count ∈ {1,2,4}` and *independent* render `render_count ∈ {0,1}`. A new explicit configuration must describe layout/version, 3D positions in metres, physical capture slot permutation, signed gain/polarity, calibration latency, reference index, active microphone mask and provenance. Unrecognized or aliased descriptors, bad NaN/Inf, buffer overlaps, count=3, render-as-mic, partial input, or insufficient/misaligned caller storage must be rejected atomically before DSP state mutation.

R2A's first-party **16kHz, exactly 160 sample-frames/mic, S16 interleaved** adapter is currently the only individually qualified noninstalled test seam. Its 8/24/32/48k I/O paths were not admitted. B1 must measure **each** actually supported input rate, its capture resampling and optional render-rate path; infer nothing from a lower-level source supporting other rates. The 10 ms frame contract is not a device hard-deadline measurement.

The suggested **192 KiB** C4 *full-system research budget* is **NOT_MEASURED**. A meaningful later budget must itemize arrays, per-mic and DAC reference SRC, AEC/NS/AGC/VAD, stack frame scratch, queue depths, Flight Recorder, control state, ELF/bss, RSS, firmware heap, I/O DMA and safety margin. R2A reported architecture-dependent private header sizes (x86_64 96 B vs AArch32 80 B); **do not** demand identical private `sizeof` across architectures or call hosted timings SSC305 p99.

## Timebase, render and recorder / 时钟、回声参考与录制

The future design must retain N microphones versus playback reference as different source families, with capture ADC and render DAC ownership, sample-zero and clock-origin provenance, route/codec reset and underrun/gap event semantics. RealMAN original source **clip ADC sample-zero, interchannel drift, camera offset, geometric calibration and per-label timebase remain UNKNOWN**. Even peer-reviewed source-reported clock-synchronized recording equipment and original eight FLAC PCM MD5 matches do not independently prove the Gym excerpt's physical clock alignment.

Keep the existing 2.x recorder **v1** format and registered immutable tags untouched. B2 must separately preregister a versioned 3.x writer/reader or explicit incompatible format, including sample count stride, endianness, replayer behavior, frame sequence, capture/render epoch, overflow guards and rollback. A runtime/Flight Recorder dump must never silently reinterpret two-channel payload as four-channel PCM.

Control responsibility: source validation → 10ms capture admission → per-physical-mic SRC → single first-party BF → mono SYNC/AEC → NS/AGC/VAD/output; one optional separately mapped render stream joins at SYNC/AEC only. This is a **candidate**. Per-mic AEC→BF is a scientific counterfactual, not a second forever-shipped core. Capture gap resets capture FIR/epoch; render gap resets reference-domain state; codec/clock reopen must invalidate stale SYNC/AEC timing. DOA, source direction and microphone fault masks require measured authority rather than implicit synthetic oracle.

## Independent gates and rollback / 独立门禁与回滚

1. **R2-B0 only:** offline self-test with a mutation for each of 34 exact anchors, public by-value layout mutation, accidental private-adapter CMake install, Git source identity drift, every forbidden true claim, altered predecessor, phase promotion, omitted blocker, malformed/duplicate/nonfinite JSON and ADR claim tampering. Existing Docs/Verify reuses one checker. No new workflow, extra 531 MB spatial artifact, paid input or unreviewed toolchain. Passing B0 means only source architecture planning qualified.
2. **R2-B1:** separate preregistration after protected B0 main, then one private C1/C2/C4 core + actual N+render SRC and native/sanitizer/ARM functional tests. New state-size/alignment and 2.x C2 baseline preservation must be proven, not inferred.
3. **R2-B2:** separately authorize experimental next-major runtime, capture/record/replay, installed header ABI tests and explicit versioned on-disk migration and rollback. Preserve immutable 2.x release tags, never secretly modify their public layouts.
4. **R2-B3:** preregister controlled BF/AEC order, target preservation, ERLE, WNG, latency and negative-scene comparisons before any performance selection; no hidden test-scene threshold shift.
5. **R2-B4 / R2-C:** only real aligned array clock/calibration recordings and SSC305 BSP/thermal/CPU/p99/HIL evidence can authorize hardware claims. [HIL 38329856467](https://github.com/jiying2007/audio-pipeline/actions/runs/38329856467) failed closed because `HIL_ENABLED` was unset; it is NOT a pass or optional certification shortcut.

To qualify B0: exact latest PR HEAD full Verify required `summary=success`, active main Ruleset 21804005 strict/squash-only, zero unresolved review threads, protected expected-HEAD squash, **distinct** merged-main Verify+same-SHA Release; preserve original source and original R2A metadata identities. Current 2.x release/source remains rollback authority; closing B0 does **not** auto-authorize B1 or release.

Run the canonical offline checker (no network or raw audio):

```sh
python3 tests/validation/frontend_evolution/fe09_major_migration_preflight_r2b0.py --self-test
python3 tests/validation/frontend_evolution/fe09_major_migration_preflight_r2b0.py --check
```

## Explicit nonclaims / 不得宣称

**No published 3.x SDK. No installed C4 2.x feature. No real array acoustic improvement. No source clock or ADC sample-zero authority. No full C4 192 KiB runtime-memory or SSC305 CPU/p99/HIL qualification. No E001/product certification or commercial RealMAN redistribution permission.**

The only permitted result here is source-grounded migration readiness under `FE09_R2B0_MAJOR_MIGRATION_PREFLIGHT_RESEARCH_ONLY_NO_PUBLIC_ABI`. Historical failed D1 CSV (544 negative static-distance rows), original S3 preinstalled decoder, original S5 preinstalled PDF parser and still unresolved sample clock/label joins retain their original **fail-closed** evidence, regardless of other distinct S3R/S5R successes. B1+ and all shipping remain **BLOCKED**.
