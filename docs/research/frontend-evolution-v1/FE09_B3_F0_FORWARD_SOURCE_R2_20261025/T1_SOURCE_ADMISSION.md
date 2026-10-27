# FE09 B3/F0 R2-T1 — immutable source admission (no DSP execution)

**Authority:** source-only engineering evidence. This document is not a B3/F0 measurement, R1 promotion, SSC305 HIL certificate, or commercial redistribution clearance.

## Frozen inputs

- Original R1 77-member source-lock SHA-256: `32bd625ee640bf60310bcdc9980a5f8a41711300aee66f029fbf65c98a9bb49d`.
- 66 executable/compiled-build members must match their original R1 source bytes, except the exact source identities recorded in the protected R2 preregistration; the remaining 11 historical authority/reference rows are read back against the original frozen commit, never represented as live compile inputs.
- `2.3.57` permits exactly two changed members: `CMakeLists.txt` and `src/platform/linux/ap_runtime.c`.
- `2.3.58` additionally permits exactly `cmake/audio-pipeline.pc.in` and `cmake/audio-pipeline-runtime.pc.in`; both template changes must equal the original byte streams with only the registered relocatable `prefix` token substituted.
- Replay each registered CMake/Runtime forward patch in isolated storage, then reverse it and compare to the frozen original bytes. The live checkout is not rewritten.
- Preserve original R1 collector, deadline correction, F0 resource source, private `add_subdirectory` CMake topology, fixed input contract and source-role selection.

## Offline commands

```sh
python3 tests/validation/frontend_evolution/fe09_b3_f0_r2_source_admission.py --self-test
python3 tests/validation/frontend_evolution/fe09_b3_f0_r2_source_admission.py --check
```

Use the exact committed checkout, full repository history and no dirty tracked files. The fast assurance gate invokes both commands. A rejected mutation must cause nonzero exit, not a synthetic success receipt.

## What is not yet proven

Passing T1 **does not** qualify either source profile's DSP behavior, full real compiler/linker graph, B3's 19,800 actual frames and 48 API rejections, F0's 21,600 frames and 144 groups, SSC305 hardware timing, four-mic public SDK, HIL/72h endurance or product promotion. Original R1 success and every failed zero-frame archive remain immutable, and cannot be inherited by a new R2 result.

T2 must separately review any additional study code *before first DSP execution*, use unchanged original strict time/error/size envelopes and build the real current exact-head source, then produce distinct hashed evidence. T3 must independently verify those new artifacts and require direct science gates, protected squash and fresh-main Verify/Release.
