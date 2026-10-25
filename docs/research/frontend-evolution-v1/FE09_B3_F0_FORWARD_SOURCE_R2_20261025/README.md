# FE09 B3/F0 forward-source R2 preregistration

**Status: SOURCE-ONLY PREREGISTRATION; ZERO R2 DSP EXECUTIONS.**

This is a source governance attachment for [#854](https://github.com/jiying2007/audio-pipeline/issues/854), NOT a B3/F0 research result, shipping SDK or product qualification. It is deliberately separate from original FE09 B3 R1 and historical #848.

## Why this stage exists

The v2.3.57 Runtime PR #850 triggered genuine job `40205111409` / `121204639149` whose original `12602889503` artifact has sha256 `580c1f10015edd3be756f7866b333b163fec446f9bd1c2fd8204cbcfe202dd63`. The `receipt.json` says `LOCKED_EXECUTABLE_SOURCE_CHANGED:CMakeLists.txt`, `accepted_frames=0`; this is a **correct fail-closed R1** source rejection, not a scientific DSP comparison result. Runtime is another locked member, and the private research CMake compiles the actual public build through `add_subdirectory(AP_REPO_ROOT)`.

The approved FE09 maintenance pre-registration #853 is sufficient to identify two prospective source configurations, but it **does not** turn the R1 historic frozen-source acceptance into a current-head success. A separate R2 scientific identity is mandatory.

## Immutable lineage and limits

The adjacent `PREREGISTRATION.json` fixes the exact R1 77-member source-lock hash, the two reviewable version-specific Git blobs and forward-patch Git blob IDs, plus the original positive/negative control and time/size budgets. The original R1 lock, 71ce successful readback, earlier 300.00000000000006 rejection and latest zero-frame rejection retain their own immutable identities. No historical result is retroactively accepted.

Only two executable-source paths may differ from the R1 frozen inventory, and only by the exact preregistered reviewed bytes. All other originally locked compiled sources must remain identical; source-to-binary compiler flags, runtime profiles, build closure, and new actual corpus/metric receipts still require fresh independent scrutiny. Any unknown edit or unregistered software version fails closed. No science gate, resource cap, source right or HIL requirement is waived.

## Implementation and verification stages

**R2-T0 (this commit):** register exact candidate source identities and immutable R1 ancestry on protected main. No DSP is run and no new qualification is claimed.

**R2-T1:** implement an independent R2 source verifier with negative mutation controls. Verify all 77 original lock members and exact proposed source/compiled closure, reconstruct the R1 predecessor via trusted patches, and independently audit current CMake flags and source checksums. Never modify the R1 collector in place or inherit its receipt.

**R2-T2:** implement and execute new bounded three-target B3 and F0 qualification only after the T1 policy is merged. Keep 11×600 frames per target (19,800 frames total), the 48 API rejects, 8 semantic negatives, and F0 36×600 (21,600 frames; 144 groups). Preserve actual failing archives and require unchanged strict acceptance predicates and 300/120/180/300/900/60 s and 32 MiB boundaries.

**R2-T3:** separately review the new immutable ZIPs, source hash chain, and success/error evidence, then require full exact-head PR science and Verify summary, protected squash, fresh-main Verify and Release/convergence. The prior C4 synthetic research outcome never implies four-mic public SDK, SSC305 HIL, commercial license or product readiness.

This frozen plan must land through protected PR **before the first R2 candidate experiment**. A plan-only PASS cannot unlock any existing R1 failing science check.
