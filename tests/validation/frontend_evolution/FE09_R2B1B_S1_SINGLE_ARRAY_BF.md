# FE09-R2B1B-S1 — single first-party array BF after N+render SRC

**Status / 状态: research qualification candidate only; not shipping.**
Independent registration: issue #743, parent #733/#730. Predecessor protected
main 65f8589e708b9a2708699a9514f0c414ad4258ab; independent Verify
38427035530 and exact-SHA Release 38431798704.

## Ownership and interface / 数据及所有权

- Reuse the **unchanged** first-party src/frontend/ap_resampler.c, with pinned
  SHA256 5bf5e725dfdc516d82dce145b93ef881b1348bae17d2bd04130e7feb15834aff.
  S0 owns independent per-microphone SRC history plus one optional mono render.
- S0 outputs physical-major Float32 [N][160]; S1 explicitly transposes
  to the **interleaved** Float32 [160][N] expected by the ONE existing
  array_native.c FIR33_HANN core. Physical array input_channel is identity,
  even when S16 capture slots are arbitrarily permuted.
- Finite check followed by bounded [-1,1] pre-BF clipping tracks clip count.
  BF output remains UNCLIPPED, as does separately observed mono render.
  Render is **never** microphone N+1 and never passed to BF/AEC.
- No second FIR implementation, public 3.x ABI, 2.x source/header/CMake
  change, allocator, I/O, lock or unbounded frame callback. Aligned caller
  arena and **separate** frame work memory include a rollback snapshot.
  This is NOT an optimized SSC305 or complete 192KiB C4 memory budget.

## Matrix, faults and evidence / 测试矩阵

- 16/32/48kHz I/O × C1 (no render), C2 ULA, C4 ULA, C4 UCA (each separate
  mono render) = **12 synthetic scenarios**. BF always 16k/160 samples.
- Exactly two 100-accepted-frame deterministic replays per profile on
  native, ASan+UBSan and AArch32/QEMU. Both first-party SRC and first-party
  BF are executed, including an independent same-target baseline.
- Frame 50 missing capture resets physical SRC+BF, not a fabricated frame;
  frame 70 commanded active mask; frame 75 explicit steering; frame 80
  render-only gap leaves BF history intact; frame 90 resets common source
  clock and both domains. No automatic fault, DOA or clock estimator.
- More than 30 distinct malformed/overlap/geometry/NaN/Inf/clock/overflow
  negative controls per profile; rejected frame operations preserve
  byte-for-byte state and external outputs. Physical input source fingerprints
  must match across targets. Float32 output fingerprints are compared within
  target only.
- Reuse existing frontend-reference qualification and Docs self-tests.
  One 30-day metadata-only Artifact with exactly four members:
  receipt.json, collect.log, verify.log and SHA256SUMS. Source, binary,
  toolchain and inner-file hashes, state and epoch counters, clips, negative
  checks, and all 12 profiles are verified. No raw audio, new workflow,
  paid services or product releases.

**Positive only after gates:** FE09_R2B1B_S1_SINGLE_ARRAY_BF_RESEARCH_ONLY_NO_RELEASE

**Fail closed:** FE09_R2B1B_S1_GEOMETRY_OR_SOURCE_TRANSFER_NOT_ADMITTED

Required sequence: full exact-HEAD PR Verify summary success, zero unresolved
threads, active protected strict/squash rule, expected-HEAD squash; independent
new-main Verify + exact-SHA Release + four-member Artifact readback. Parent
#733/#730 remain OPEN.

**Explicitly NOT qualified:** measured BF WNG/SNR/DOA improvement; motor
noise; physical geometry/calibration and RealMAN sample-zero; ADC/DAC drift;
8/24k or asynchronous SRC; AEC/SYNC/NS/AGC/VAD; SSC305 10ms p99/RSS/
stack/thermal/power; complete 192KiB C4 system; HIL/E001; product release;
public 3.x SDK; real microphone quality or shipping licenses.
