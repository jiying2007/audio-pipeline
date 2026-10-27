# FE09 F0 R2 T3 — Frozen C timing identity versus new collector identity

**Scope: source-only preregistration. Zero newly accepted R2 F0 runs. No DSP, no hardware, no product promotion.**

## Independently observed failed evidence

- #850 run 40459902165/a1, artifact 12715125160, original ZIP SHA-256 `ca7161a1382739651c3a5968a25c9edbc690fca5121b4916320459e1d0618f27`.
- #851 run 40460130863/a1, artifact 12714824044, original ZIP SHA-256 `08d6a40f0c002ed8dbbb02d513bd73b8a6e8f9ae163252f5999925ac6a99c2d7`.
- In both attempts B3 **actually accepted 19,800 frames** under independently named R2 execution. F0 failed **after 600 completed frames** at `TIMING_RUN_IDENTITY_OR_COMPLETENESS`, retaining actual C-driver `timing.json` and its hash-sealed partial archive. This is a genuine test failure, not an accepted F0 result.
- C probe Git blob `01e26892f18e5c64a7c74448817ed6c22e693bd7` writes immutable `FE09-T3S3-F0-ACTUAL-CALL-RESOURCE-V1`. Python R2 collector (`8ac87edbbd89289ec4b6fc2739af6460a6fd01d0`) checked that *raw driver record* against the *new collector receipt* ID `FE09-T3S3-F0-ACTUAL-CALL-RESOURCE-FORWARD-SOURCE-R2`. These are distinct authority layers.

## Proposed T3 contract, before any new execution

An exact one-statement-only patch to the R2 Python `validate_timing` compares the raw driver record with the unchanged **V1 C timing identity**, while the outer R2 collector `IDENTITY`, manifest, receipt and source-admission remain **R2**. Reviewed prospective F0 source Git blob: `065cce6349842876b01ec3e410e2958bfa55eeab`. No DSP, compiler flag, program algorithm, CPU/wall timing, 600-frame completeness, clock, negative cases, wall deadline, artifact cap, underlying C source or R1 source changes.

The independently pinned T3 checker rejects all source bytes except the original protected F0 R2 file or that **exact proposed Git blob**. It retains historical T2 verifier and manifest Git objects, reconstructs the one-statement patch from protected predecessor main, runs the original T2 source-review suite while unpatched, and requires a successful positive 600-frame timing fixture plus eight independent invalid timing negatives. A new R2 scientific run must not be claimed merely because this source-only preregistration passes.

## Subsequent gate (not performed by this preregistration)

After protected exact-head qualification and squash of the T3 source-registration PR, integrate **only** the reviewed Python Git blob into #850/#851 on the verified new main; re-run actual full B3 (19,800 frames), F0 (36 separate processes and 21,600 frames, 144 resource-stat groups), all direct PR CI, and independently read back original ZIP bytes, run/attempt/Git object/source lock. Preserve previous rejects; do not waive duration thresholds or accept partial frames. Merge #850 before #851 only on full exact-head green; both require distinct fresh-main Verify/Release.

The scheduled SSC305 HIL/72h, public C4 shipping, commercial data rights and product certification remain separate unqualified requirements.
