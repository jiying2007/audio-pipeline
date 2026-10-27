# FE09 T3-S3 F0: local diagnostic readback, 2026-10-24

## Scope and source identity

This additive readback records the first local diagnostics for [#841](https://github.com/jiying2007/audio-pipeline/issues/841). The measured source is exactly `87eace16b9cacbf0cb911eab02b91ca941cc6eff`. This document and subsequent integration commits are later records; their commit identities must not replace the source identity of these local executions.

The [frozen preregistration](FE09_T3S3_F0_RESOURCE_PREREGISTRATION_20261024/README.md) remains unchanged: contract SHA-256 `42496ab0f6f01d5b36f03d23f670f585a5f57c120ecf9fc0237a27d5aa2f34f2`, source-lock SHA-256 `16cd84381647bef1015fc8ef338bb9b10dd09ce4669248355ac4f48745d8a4ff`, and 88 original source/input files. Baseline `5187c5e59526d4047b3965b44c770ab21edbde9f` passed its own [Verify 40104717635/a1](https://github.com/jiying2007/audio-pipeline/actions/runs/40104717635/attempts/1), summary `120911306166` / App `15368`, and [Release 40107235174/a1](https://github.com/jiying2007/audio-pipeline/actions/runs/40107235174/attempts/1), convergence job `120911401408`, before either diagnostic started.

Local compilation used `/usr/bin/cc` (GCC 13.3), with compiler binary SHA-256 `6117c52522997d2aaccb2b52b3c6bf42c0a6c5edb1d718431fed6b2fc5fec234`. The receipt records `context.kind=local` and `toolchain_image=null`. It does not claim execution inside the registered CI image or provide AArch32 evidence. Protected hosted PR/main qualification and matching Release/convergence remain required for this leaf's final closure.

## Preserved original evidence

The local evidence package is `fe09-t3s3-f0-local-evidence/`. These are local original records, not GitHub artifact IDs. Both original directories, console logs, sealed members and the measured-source bundle are preserved without overwriting or reselection.

| Original directory | Attempted target processes | Raw frames executed | Validated frames | Outcome |
| --- | ---: | ---: | ---: | --- |
| `fe09-t3s3-native-87eace16-first` | 12 | 7,200 | 7,200 | Local partial characterization; readonly verifier passed |
| `fe09-t3s3-sanitized-87eace16-first` | 1 | 600 | 0 | Rejected at LeakSanitizer exit; measured probe never launched |

| Original member | SHA-256 |
| --- | --- |
| Native `SHA256SUMS` | `01f12194e7d5ee909a8481e3bd74585a566e33cac112eb31d5cfd47b19264809` |
| Native `receipt.json` | `7b208d7c4a565d60aa4d8e7db666f57016b7ef96d50add2333a1e6640e727840` |
| Sanitized `SHA256SUMS` | `4c9c9629b37fbf3641b999fd41f028571ccedd4a3057c92d7742a1fb4a1fc2ab` |
| Sanitized `receipt.json` | `3fb5526a8119ad084bb2a44c23204a356e195007403e38936448b6e0e769abc7` |
| `measured-source-87eace16.bundle` | `5d4357ea7e44b1ec8344a3b8fad5505e0f58fdf31fa2ad97cab022ce02ac7f5a` |

The 36,784-byte thin Git bundle retains measured commit `87eace16b9cacbf0cb911eab02b91ca941cc6eff` and requires baseline commit `5187c5e59526d4047b3965b44c770ab21edbde9f`; `git bundle verify` passed. Readback must use that measured source and its clean worktree, even after later integration changes.

## Native: all registered repetitions retained

The fixed order was ALL_P then PAP, three repetitions each, reference followed by measured. Every process completed and validated all 600 frames. There are 3,600 measured frame rows across the six measured processes, in addition to their six bind intervals; no initial frames or slow samples were removed. Every raw output/beam stream and every canonical public frame metric matched the same-case reference and all three repetitions.

The collector consumed **12.961282892 seconds** of its 180-second local stage budget. The sealed artifact is **3,097,361 bytes**. Independent original-artifact readback on exact source `87eace16` passed source/build closure, actual executable/argument binding, full PCM/public-metric equivalence, all-frame coverage and recomputed timing summaries. The nine build-metadata, thirteen scientific-semantic and four invocation mutations were rejected without extra DSP execution.

Combined CPU time below is the sum of disjoint capture publication, Render publication and B3 worker intervals. Values include the registered clock/wrapper overhead. Quantiles use the registered nearest-rank definition over all 600 frames separately for each repetition.

| Case | Repeat | CPU p50 (µs) | CPU p95 (µs) | CPU p99 (µs) | CPU max (µs) | CPU ms / audio second |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| ALL_P | 1 | 66.699 | 114.210 | 165.998 | 308.800 | 7.155841 |
| ALL_P | 2 | 66.619 | 84.936 | 104.756 | 176.513 | 6.754550 |
| ALL_P | 3 | 66.630 | 88.871 | 122.333 | 280.548 | 6.859201 |
| PAP | 1 | 66.608 | 84.504 | 110.925 | 164.324 | 6.686100 |
| PAP | 2 | 66.589 | 89.003 | 116.674 | 569.848 | 6.783536 |
| PAP | 3 | 66.778 | 86.529 | 107.611 | 189.722 | 6.680537 |

| Case | Repeat | Wall p50 (µs) | Wall p95 (µs) | Wall p99 (µs) | Wall max (µs) |
| --- | ---: | ---: | ---: | ---: | ---: |
| ALL_P | 1 | 67.151 | 114.763 | 166.751 | 311.339 |
| ALL_P | 2 | 67.121 | 85.419 | 105.269 | 177.087 |
| ALL_P | 3 | 67.121 | 89.776 | 123.204 | 283.969 |
| PAP | 1 | 67.082 | 85.079 | 111.818 | 164.829 |
| PAP | 2 | 67.081 | 89.485 | 117.247 | 570.751 |
| PAP | 3 | 67.262 | 87.090 | 108.123 | 190.257 |

These are finite measurements on this local host. They establish no scheduler deadline, device throughput, acoustic improvement or shipping admission threshold. The complete raw times, frame 201/241 costs, bind samples and exact process usage remain in the original artifact.

## Resource ledger and the RSS boundary

All twelve Native child-lifetime `wait4` records report **54,632,448 bytes (52.1015625 MiB)** of peak RSS. Those original numbers are retained. Linux [getrusage(2)](https://man7.org/linux/man-pages/man2/getrusage.2.html) documents that resource usage survives `execve`. The collector starts its child with `start_new_session=True`; inspection of the local CPython 3.12.14 `Popen._execute_child` confirms the `_fork_exec` path. The recorded maximum can therefore include the child's launcher/pre-exec address-space history as well as the eventual executable, loader, libc and test harness.

The identical RSS values are consistent with a launcher contribution, but this experiment did **not** independently quantify that contribution. No parent-RSS subtraction or post-exec estimate has been applied. This result must not be described as the isolated CALL executable's RSS, working set, minimum deployable memory, or complete application/device resource budget.

| Scope | Recorded evidence | Interpretation |
| --- | --- | --- |
| Exact child lifetime | `wait4` PID, exit, user/system CPU, wall and peak RSS | Includes launch/pre-exec history; peak RSS remains 54,632,448 B for all twelve Native processes |
| Native reference ELF | `.text` 70,206 B; `.rodata` 9,248 B; `.data` 32 B; `.bss` 2,648,784 B | Linked section sizes of the retained original reference ELF |
| Native measured ELF | `.text` 74,062 B; `.rodata` 9,664 B; `.data` 32 B; `.bss` 2,694,448 B | Linked section sizes include the probe; these are not resident-memory measurements |
| Measurement globals | 45,644 B | All timing arrays, Render events, bind sample, error flag and clock-resolution scalars; section padding remains in the ELF totals |
| Existing B3 demand ledger | capture state 4,848 B; capture work 11,248 B; mono state 78,192 B; owner queue 19,496 B; bridge 216 B | Original `result.json.resource` fields; no changed DSP or state/work screening threshold |
| Existing driver storage | one fixture 149,200 B; three fixture instances; input arrays 960,000 B; output/beam arrays 576,000 B; frame logs 566,400 B; fresh mono storage 80,000 B; canonical scratch 16,384 B | Driver allocations overlap logical demand fields; do not sum both layers |
| Bind scratch / compiler stack | original bind-reference scratch 96,384 B; largest single compiler-reported frame 97,840 B | Bind scratch and `.su` reports are not a cumulative stack bound or thread-stack high-water measurement |
| Post-exec executable-image RSS | **NOT_MEASURED** | A separate observation must identify the new program image and isolate its measurement lifetime |
| Working set | **NOT_MEASURED** | A separate definition, observation mechanism and coverage argument are required |
| Whole-thread stack, cumulative stack, heap peak, cold-system boot, device timing/power/thermal | **NOT_MEASURED** | Remain outside this finite F0 leaf |

The Native reference ELF SHA-256 is `7fba75313265b1773807b1b67ca255b7e9e169edfa528803870e44b55bcbd70a`; measured ELF SHA-256 is `3bd3b5d9afb682975bb9cf6d72702f41a75b5863397b01d2b4f8d74a9ba20edd`. Complete compiler/link recipes, archive bytes, ELF files and per-function stack records are sealed in the artifact.

## Sanitized: executed raw frames retained, qualification rejected

The first sanitized reference process (PID 357) produced `result.json` with `status=OK`, `attempted_frame=600`, `frames=600` and `failed_frame=0`. Its raw `frames.jsonl` contains exactly sequences 1 through 600; `output.s16le` is 192,000 bytes and `beam.f32le` is 384,000 bytes. It then exited with signal-derived return code `-6` while LeakSanitizer reported:

```text
==358==Can't open /proc/357/task for reading.
==357==LeakSanitizer has encountered a fatal error.
==357==HINT: LeakSanitizer does not work under ptrace (strace, gdb, etc)
```

The observed failure is local `/proc` access during leak checking. The log does not establish the underlying sandbox mechanism. The collector's receipt records **one attempted process and zero validated frames** (`processed_frames=0`); the retained raw files independently establish **600 executed frames**. All original bytes are preserved. No measured probe ran; no leak-detection option was disabled; no retry was performed.

The attempt consumed **5.311094964 seconds** and retained **7,405,384 bytes in 21 sealed members**. Independent readback rehashed every member, confirmed the complete raw frame sequence and original failure log, and confirmed that the failed artifact cannot pass the success verifier. The pinned hosted sanitized execution must provide its own evidence; prior B3 sanitized success does not replace this leaf's gate.

## Remaining engineering work

F0's finite hosted matrix still needs its own Native, ASan/UBSan and AArch32-under-QEMU evidence, protected PR/main checks, matching Release/convergence and independent original-artifact readback. Its contract, repeat schedule, resource method and thresholds remain fixed.

The next resource-specific measurement gap is a separately preregistered observation of the **post-exec program image**, with an explicit resident-memory definition, measured binary identity, start/stop boundaries, complete observation coverage and failure controls. It must retain the existing child-lifetime measurement as a separately labelled quantity and must not estimate an image peak by subtracting unrelated process maxima. Working-set, whole-thread-stack and heap-peak questions require their own stated measurement scope. T3-S3's complete application/device budget remains open; this local diagnostic closes none of those missing scopes.

I025-I040, continuous rolling recovery, public C4 SDK admission and physical E001/SSC305 boundaries remain unchanged.
