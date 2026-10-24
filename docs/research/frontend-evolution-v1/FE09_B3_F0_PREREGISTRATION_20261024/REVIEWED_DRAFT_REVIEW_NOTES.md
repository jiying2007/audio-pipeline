# B3-F0 preregistration review notes

Status: DRAFT_FOR_ROOT_REVIEW_NOT_EXECUTION_ADMITTED. No source implementation, build, test or scientific execution has occurred.

## Source-backed decisions already resolved in this draft

- Reuse the original N-mic SRC/FIR33 and source-owned PRESENT/ABSENT APIs. Restrict this leaf to C4-ULA/16k and the actual mono CALL graph with BF cleared.
- Freeze exactly ALL_P and PAP600-frame cases, the literal integer D0 fixture, and two explicit Render notifications.
- Use actual public notify call observation. Separate explicit notifications from additional automatic SYNC/AEC resets.
- Respect the broad existing mono reset and ignored lost_frames. Preserve only the separate capture SRC/FIR33 at Render boundaries.
- Use actual frequency RES inside NS; do not claim standalone time-domain RES executed.
- Resolve normal reject atomicity by complete preflight plus the source-proven non-failing mono tail. Unexpected invariant breach is fatal retained failure, not a recoverable atomic reject. No new generic control API.
- Add literal direct-control replay independent of adapter transition logic. Plain/observed equality is solely an observer-transparency witness.
- Disable unity/IPO only in the private parent build so actual original calls are observable; keep original production source/build files unchanged.
- Freeze16 API rejects and8 receipt mutations,3 execution targets,19800 accepted frames per full qualification invocation and one300s added-stage deadline within the existing15min job. No workflow-timeout expansion.
- Bound observer RAM256KiB and report all instrumentation/reference/fixture overhead separately.
- Keep APX3 source semantics intact without adding recorder code.

## Independent review still required

Root and assigned reviewer must assess whether this proposal is ready to freeze. No review result is self-issued here. Reviewers should check the explicit post-owner AP_OK proof, actual wrap visibility, per-frame direct-control independence, rejection snapshot scope and fixed branch-coverage conditions.

The exact binary/config/compiler and new adapter/observer/test source hashes will only exist after an admitted implementation. They must be recorded then and cannot be borrowed from the original R0. The pinned original source bytes and the proposed future paths are not implementation evidence.

Required physical clocks, board memory/CPU/deadlines, true full-scene acoustics, complete B3, public SDK and shipping qualification remain outside this leaf. Stage-wide user authorization permits root to freeze a bounded preregistration; this draft creates no generic user-confirmation gate.
