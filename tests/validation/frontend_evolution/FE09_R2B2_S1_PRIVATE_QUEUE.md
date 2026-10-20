# FE09-R2B2-S1: private C1/C2/C4 bounded queue and one first-party BF
# 非安装版四麦 SPSC 队列与统一 FIR33 研究原型

**Independent preregistration:** [#755](https://github.com/jiying2007/audio-pipeline/issues/755), parent #733/#730. Predecessor B2-S0 [#749](https://github.com/jiying2007/audio-pipeline/issues/749) fully closed on protected `da8a48b29b482215a0086d3c58e6eed8fc943c28`, new-main [Verify 38583607398](https://github.com/jiying2007/audio-pipeline/actions/runs/38583607398) and matching [Release 38588624391](https://github.com/jiying2007/audio-pipeline/actions/runs/38588624391) both completed success. Newer M1 governance main, if present, is independent; candidate must be synchronized and requalified before protected merge.

## Software boundary / 软件边界

This prototype is **entirely within `tests/validation/frontend_evolution/`** and only uses the already-qualified first-party `fe09_b1b0_src.c`, `fe09_b1b1_single_bf.c`, `array_native.c` and unchanged shipping `src/frontend/ap_resampler.c`. **No new SRC or FIR DSP implementation**, no change to 2.x installed/public `include/`, shipping `src/platform/linux/ap_runtime.c`, CMake, APD2/v1 producer/reader, release or product SDK.

`fe_b2s1_private_queue.h/.c` implements separate fixed-capacity **C11 SPSC capture and mono-render queues**, each depth 2 or 4, with release/acquire head/tail publication. Caller owns a 16-byte-aligned, configuration-sized state and independent work arena; frame submission copies one exact 10ms capture or optional render frame, and consumer drains matched sequences into **one existing B1B-S1 SRC→FIR33 BF** instance. No allocation/locks/file I/O/worker spawning in 10ms processing. The process caller must serially own control; there must be one producer per source queue and one DSP consumer. Reading metrics is only admitted while quiescent, not a race-free monitoring API.

- Capture and render streams are **different domains**. Explicit render gap/XRUN only resets the render SRC; capture gap/XRUN resets microphone SRC and array histories. A shared `CLOCK_RESET` requires matching flags for both when render exists, never inferred from timestamps.
- The only admitted rates for these B1B fixtures are 16/32/48 kHz fixed 10ms input→16 kHz/160 Float32 output, C1/C2/C4 physical mics; **no C3** or fifth render microphone.
- Frame sequence starts at 1. Gaps/jumps need explicit source flags, and mismatched render/capture sequences are rejected; missing render is `EEMPTY`, no fabricated samples. Timestamp source authority remains **UNKNOWN**, and no timestamp is synthesized.
- Rejected input or processing must preserve queue indices, first-party state and external outputs; the working scratch contains a complete pre-processing BF/SRC state snapshot. Full/empty queues remain bounded. This is software data-plane research, not demonstrated Linux realtime scheduling.
- `fe_b2s1_private_dump_sketch` returns **schema version 2 metadata only**, endian `0x01020304`, physical slot map, checked upper-bound stride and `new_magic_assigned=0`. **No APD v2/v3 file writer/parser exists** and APD2/v1 remains C1/C2 only.

## Qualification / 验证

`fe09_b2s1_private_queue_test.c` uses 12 synthetic scenes (C1 baseline, C2 ULA, C4 ULA, C4 UCA at 16/32/48k), two independent repeats of 100 accepted frames each, and compares queue outputs **byte-for-byte to a second direct instance of the exact same first-party BF/SRC** within each target. It exercises capture reset, render reset, global clock reset, capture/render XRUN, active physical slot permutations, nonfinite output rejection by the existing BF, sequence ordering, high-water, depth 2 and 4, full/empty and byte-identity of state on invalid calls. Source and beam hashes must match between repeats, but **cross-ISA exact Float32 hashes are not required**.

`fe09_b2s1_private_queue_qualification.py` builds and **executes** actual first-party C on hosted native, sanitizers (ASan+UBSan) and AArch32 GNU+QEMU. It checks B2-S0's 13 frozen source blobs and SHA256, plus B1B-S1 pinned resampler/array original authority. Hosted per-frame p95/p99 timing is printed on stderr for context, **not an SSC305 CPU/10ms scheduling or whole-C4 192KiB RAM certificate**. Only exact source/fixture/binary/negative counts and nonpromotion verdict are admissible in the four-member `SHA256SUMS, receipt.json, collect.log, verify.log` research Artifact.

**Offline qualification commands:**

```sh
python3 tests/validation/frontend_evolution/fe09_b2s1_private_queue_qualification.py --self-test
python3 tests/validation/frontend_evolution/fe09_b2s1_private_queue_qualification.py --collect --output fe09-b2s1 --execution-source "$(git rev-parse HEAD)"
python3 tests/validation/frontend_evolution/fe09_b2s1_private_queue_qualification.py --verify --output fe09-b2s1 --execution-source "$(git rev-parse HEAD)"
```

A real qualification requires compiler/QEMU and a generated first-party build header. Existing quality workflow handles this; do not treat synthetic stdout or an unbuilt C file as evidence. Fail closed on errors. No raw user audio, premium cloud, device lab, or commercial deployment is used.

**Positive software-only verdict:** `FE09_R2B2_S1_PRIVATE_LINUX_QUEUE_RUNTIME_RESEARCH_ONLY_NO_PUBLIC_ABI`.

**Negative/not admitted:** `FE09_R2B2_S1_QUEUE_EPOCH_OR_SOURCE_NOT_ADMITTED`.

**Next independently registered B2-S2:** real private on-disk APD next-version writer/parser and replay, not implicitly this prototype. Keep parent #733/#730 and #58 open until physical clocks/calibration, full AEC/NS, SSC305 resource/HIL and public major ABI gates are independently resolved.
