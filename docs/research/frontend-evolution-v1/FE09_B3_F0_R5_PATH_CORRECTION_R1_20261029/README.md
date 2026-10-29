# R5 provenance path correction R1

This is a source-metadata correction for the exact 2.3.61 profile admitted by
R5. It does not change CMake, DSP, source locks, measurement methods, acceptance
limits, timeouts, data roles or product authority.

## Preserved failure

PR #868 candidate C2, head `34e5d8d91be662b1685424a228715155da6ac47f`,
[Verify 40871685101 / job 123441104210](https://github.com/jiying2007/audio-pipeline/actions/runs/40871685101/job/123441104210),
reported the original R5 B3 rejection with zero accepted frames. Retain artifact
12897300987 (4,415 bytes; SHA-256
`7f51554cf280ae84ef366909d5fd7a9df2961d68c66f8de12a0e080158a35b7a`).
No result from this failed attempt qualifies a later candidate.

Both old R5 collectors name the nonexistent directory
`FE09_B3_F0_IO_SOURCE_R5_20261029` in their source provenance lists.
The actual immutable registration is
`FE09_B3_F0_PCM_IO_SOURCE_R5_20261029`.
The old metadata self-tests did not read these literal targets.

## Exact correction

The original R1–R5 files remain unchanged. New `r5_path_r1` entrypoints derive
from the exact old R5 bytes using the frozen replacement lists in
`PREREGISTRATION.json`. Changes are limited to the two provenance path
literals, independent correction review, additional provenance, and distinct
receipt/log identities. The exact R5 source-admission gate is still used.

The independent contract verifies full-byte derivation, unchanged scientific
function bodies/classes, and the existence of every literal ROOT/file target
inside the affected source function. It pins both registration documents,
the old review and old/new collectors. Six source mutations and two missing
provenance-target mutations per collector must be rejected. The old R5
derivation self-test and its 45 negative controls remain intact.

The new receipt namespace is `R5-PATH-R1` / `R5_PATH_R1`; old R5 receipts
cannot satisfy the unchanged identity validators with these new constants.
New artifacts use `forward-r5-path-r1` and retain actual run/attempt identity.
The 39 B3 scientific functions and three classes, and 33 F0 scientific
functions and one class, remain byte-identical to R5 and transitively to
its independently reviewed predecessors.

## Admission sequence

First protected-merge this release-neutral source prerequisite from 2.3.60,
then require a distinct main Verify and existing-release identity guard.
Only afterward integrate it into the 2.3.61 PCM candidate. The 2.3.60 source
prerequisite continues to execute the original R4 science.

Source and metadata self-tests execute zero DSP frames. They cannot qualify
B3/F0 measurements. After admission the candidate must produce fresh complete
native, sanitized and Arm evidence with the original frame counts, budgets,
clocks, negative controls and archive requirements. No old PASS is inherited.

The correction is registered in
[#866](https://github.com/jiying2007/audio-pipeline/issues/866#issuecomment-6496783942).
The separate immutable v2.3.16 physical program in #58, and terminal attempts
including #833, remain unchanged.
