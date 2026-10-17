# FE09 S3-T2-C0 — quiescent logical owner-ACK, NONSEAMLESS source fallback
# 来源方停止确认控制 / 独立新会话 BF + 原始 APX3 回放

**Independent preregistration:** [#784](https://github.com/jiying2007/audio-pipeline/issues/784); parent [T2 #766](https://github.com/jiying2007/audio-pipeline/issues/766). Frozen input main `b29252d182e5ba8f76313ed1c75b41221e5b372a` carries completed B1-S0 #776 / B1-S1 #778. Independent B1-S1 CI-visibility repair PR #783 is merged but its distinct pushed-main qualification must close #782 separately. The newly added C0 stage does NOT retroactively qualify #783, T2 or T3.

## Decision boundary / 为何是非无缝恢复

Original paired S1's stale Render tail with otherwise continuous Capture is unreachable under strict monotone paired consumption, as independently proven in T2-F0. A silent Render producer also **cannot** attest a physical missing Render signal: B1-S0/B1-S1 correctly stay PENDING without an explicit source-owner ABSENT token. No arbitrary elapsed timer or fake silence can create such an event.

This noninstalled control path is the conservative alternative when actual sources cannot authorize matching Render. It **does not** drop a private S1 Render tail, mutate frozen S1/B1/S2 state, preserve missing Capture BF history, or claim continuous ADC/DAC clocks. Instead, an exclusive supervisor suspends publication, collects independently attested *logical* owner ACKs, quarantines old uncommitted frames, and atomically exposes a **fresh independently initialized first-party Capture/BF/APX3** session with new logical generation and IDs.

## Source-ownership and linearization / 真实边界

- Frozen B1-S0's two SPSC producers and worker must **actually stop** before they issue ACK and stay stopped. `fe_t2c0_ack` only records an atomic bit; it **does not prove driver stop, cryptographic identity or physical Render absence**. A missing ACK blocks restart forever until an explicit authorized decision, with no timeout bypass. The supervisor itself is single-owner.
- `fe_t2c0_request_stop` release-publishes STOPPING; once all required Capture, Worker and (when enabled) Render owners ACK, it may inspect their previously non-atomic counters **quiescently**. Wrong/duplicate/stale-generation ACKs and stop commands are denied. No new callbacks during inspection; the embedding caller must enforce this lifetime contract.
- Old source, real B1-S1 original APX3 record and canonical manifest are independently checked in memory. The control receipt gives last committed Capture, independent queued Capture/Render events, exact old generation/source IDs and logical lost-Capture range; it says no durable archive and no preserved BF continuity. No old committed PCM or SHA row is rewritten.
- New first-party queue, B0 state and B1-S1 archive must be fresh, disjoint, empty, same rate/mic geometry/depth/physical slot map, with strictly advancing new logical generation and source IDs. Old render-enabled to new Render-disabled **or** properly initialized Render-enabled are both admitted as **new sessions** only.
- All fallible checks and receipt construction finish **before** atomically publishing the fresh session pointer and generation; RUNNING release publication is last. New Capture #1 is true new source data (separate logical epoch), not continuation of missing old #2. Source-owner code checks the new generation; old-generation session lookup and ACK are rejected.
- Proven only in hosted C tests: actual first-party B0/B1-S0 Capture SRC+FIR33, original S2 one-frame APX3 writer/decode/replay and manifest SHA256, fresh BF equality with a separately initialized first-party oracle **within each ISA**. No cross-ISA Float32 equality claim.

## Executable matrix / 验收

C1, C2-ULA, C4-ULA, C4-UCA × 16/32/48kHz × queue depth2/4 × new Render disabled/enabled: **48 logical source lifecycle profiles**. Each uses real first-party C PCM through an old Render-present Capture+APX3 commit, a true second Capture with no Render token (PENDING), then three **actual native pthread ACKs** and new-source Capture+APX3 commit. Every accepted old/new chunk is re-decoded/replayed using **original first-party S2 C**; the old store is hash-snapshotted before publication and unchanged after. Each profile executes multiple negative cases: premature/no-ACK, forged/wrong/duplicate ACK, wrong-generation stop/restart, in-place session, non-increasing generation/source ID, invalid physical slot, dirty next session and old-generation ACK after release.

Native, ASan+UBSan, ARM32/QEMU and **native** TSan must compile and execute changed C twice per target, with negative count ≥624 per target, exact SHA of first-party sources, toolchain and ELF, and no product/clock qualification. Cross-target integer/manifest witness equality is required, never cross-ISA Float32 BF identity. Preserve an exact-run 30-day **four-member** `SHA256SUMS / receipt.json / collect.log / verify.log` Artifact, with pinned upload/download and independent hash/source/target/no-promotion verification; fail closed on failure or upload visibility race. No source substitution, fake timebase, physical clock or paid resource.

## Hard nonqualification / 不能推出的结论

This stage proves **logical ACK control only**, not authentic physical stop, real Render absence, AEC alignment, real C4 BF/WNG/DOA improvement, SSC305 192KiB/10ms p99/RSS/stack/thermal/power, durable rolling archive, product/HIL/E001 or public SDK. The two complete in-memory B1-S1 stores are large hosted-only buffers. No shipping `src/`, installed `include/`, CMake, S1/S2/B1 frozen codec, legacy APD2, release tag or I025–I040 source was changed. T3 #767 and physical #58 remain separate.

**Completion**: independent latest-HEAD full Verify summary success; active strict Rule 21804005/zero unresolved threads/squash-only; expected-HEAD protected merge; **distinct** new-main full Verify, same-SHA Release `release+convergence`, independent exact-run four-file ZIP+inner SHA readback. Until then keep #784 and parent #766 OPEN.

Success decision must be only `FE09_T2C0_LOGICAL_OWNER_ACK_NONSEAMLESS_FALLBACK_NO_PHYSICAL_AUTHORITY`; failure `FE09_T2C0_QUISCIENT_SESSION_NOT_ADMITTED`. No hardware/product promotion.
