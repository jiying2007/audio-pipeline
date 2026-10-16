# FE09 B2-S3 T2-F0 — Frozen S1 Render-only recovery feasibility
# 原始 S1 队列 Render-only 安全恢复的负面可行性认证

**Independent preregistration:** [#766](https://github.com/jiying2007/audio-pipeline/issues/766). T1 [#764](https://github.com/jiying2007/audio-pipeline/issues/764) CLOSED completed at protected main `31f2360aece28deb4136cc3daab3e4d3d6010fcf` after exact pushed-main [Verify 38833461062](https://github.com/jiying2007/audio-pipeline/actions/runs/38833461062), 65 successful jobs + 1 expected skip and required summary success; same-source [Release 38836273501](https://github.com/jiying2007/audio-pipeline/actions/runs/38836273501) release/convergence 2/2 success. T1 [Artifact 12018392851](https://github.com/jiying2007/audio-pipeline/actions/runs/38833461062/artifacts/12018392851), 5,613 bytes, was externally downloaded and source/member-rehashed to SHA256 `99e0772abf47235ded7a07b027e8c0be1bebe372020c0de70c2efb1ec36bac09`.

This F0 is a **negative feasibility audit**, not a new render-drop control or product qualification. It freezes the S1/S2/T0/T1 source bytes, compiles the actual S1 source in a *test-only* translation unit, and demonstrates how its existing strict paired-consume API behaves when Capture/Render source identity is inconsistent. It never modifies production `src/`, installed `include/`, CMake, published APD2/v1 reader or an S1 queue field outside legitimate first-party calls. Its documentation remains noninstalled.

## Proven source-level invariant / 配对消费后的序列不变量

Let P be the most recent fully processed Capture+Render pair sequence (P=0 when none). Frozen S1 `submit()` requires each independent producer to publish strictly increasing positive sequence numbers; a jump is only accepted if explicitly flagged as a source gap, XRUN or clock reset. Frozen S1 `process_one()` accepts exactly matching Capture and Render tail sequence, advancing **both** tail counters together. Therefore every retained Render tail after processing P must have sequence R greater than P.

If the next Capture is continuous without an authorized gap, its sequence is `C=P+1`; thus R cannot be smaller than C. **The purported stale-Render case R<C under Capture continuity is unreachable in this frozen paired-consume model.** The test enumerates bounded 16 predecessor sequences × 5 next Capture choices × 5 next Render choices; it requires zero cases with R<C and continuous Capture, while validating the gap cases are possible.

This is a **logical sequence invariant**, not proof that the actual ADC/DAC have the same sample-zero, rate drift or physical clock. A caller falsifying sequence/flags is outside the exclusive source-attested T1 facade and is not made trustworthy by the invariant.

## Actual frozen C negative controls / 原始 C 代码执行

`fe09_b2s3_t2_f0_render_feasibility_test.c` includes the original `fe09_b2s1_private_queue.c` *exactly once, privately in the noninstalled test TU*. It reuses the frozen T0 first-party C1/C2/C4 scene generator, real BF state and APX3 writer, without cloning DSP, S1 or S2 logic.

For C1/C2-ULA/C4-ULA/C4-UCA ×16/32/48 kHz ×SPSC depth 2/4, four admission classes are actually executed (96 cases):

1. **Render ahead (R.seq=2, C.seq=1):** render-source gap explicitly flagged; S1 returns mismatch without consuming any capture or render, and cannot fabricate missing Render seq1.
2. **Render behind (R.seq=1, C.seq=2):** capture-source gap is mandatory for accepting first Capture seq2; it invalidates any claim that microphone BF histories are continuous. A second capture with sequence 2 *without* such gap cannot be submitted to S1.
3. **After one real processed matched frame P=1, stale Render seq2 behind Capture seq3:** S1 only admits Capture seq3 with explicit `CAPTURE_GAP`, so preserving pre-gap BF histories cannot be falsely claimed.
4. **Render entirely absent:** real frozen S1 returns `EEMPTY`, not a synthesized Render sample.

Each case creates two actual pthread producer submissions where Render exists, joined before the quiescent observation. Four successive failed `process_one()` attempts must preserve **entire owned S1 state+BF snapshot, source head/tail/counters, external output buffers and retained APX3 file and writer**. The T0 bridge is also checked for noncommit on these missing/mismatched sources. No test expects a success after a missing Render or falsely labels a quiescent re-init as seamless history-preserving recovery.

## Qualification and what remains / 资格门禁与未完成项

First-party `fe09_b2s3_t2_f0_feasibility_qualification.py` compiles/executes the above C fixture twice on actual Native, ASan+UBSan, native TSan and ARM32/QEMU; compares deterministic negative classifications, pins immutable S1/S2/T0/T1 code and exact toolchain/binary hashes. Real native+ARM concurrency is only **two producer submissions followed by quiescent worker validation**, not a claim of fully concurrent progress. A bounded, source-run-specific four-member `SHA256SUMS / receipt.json / collect.log / verify.log` Artifact is uploaded, externally downloaded, independently rehashed and checked for **negative-only decision/no product authority**.

```sh
python3 tests/validation/frontend_evolution/fe09_b2s3_t2_f0_feasibility_qualification.py --self-test
python3 tests/validation/frontend_evolution/fe09_b2s3_t2_f0_feasibility_qualification.py --collect --output fe09-s3-t2-f0 --execution-source "$(git rev-parse HEAD)"
python3 tests/validation/frontend_evolution/fe09_b2s3_t2_f0_feasibility_qualification.py --verify --output fe09-s3-t2-f0 --execution-source "$(git rev-parse HEAD)"
```

**Expected only when actual tests pass:**
`FE09_S3_T2_F0_FROZEN_S1_RENDER_RECOVERY_INFEASIBLE_WITH_CAPTURE_CONTINUITY`

**Fail-closed:** `FE09_S3_T2_F0_SOURCE_OR_LIVENESS_ASSUMPTION_NOT_ADMITTED`.

Even if F0 is protected-merged with a new-main Verify, Release and independently rehashed Artifact, **it does not close [T2 #766](https://github.com/jiying2007/audio-pipeline/issues/766)**. T2 requires a new separately preregistered **design change** that supports truly independent Capture BF progression when a reference frame is missing, or an explicit source-authorized whole epoch reset; it must correctly integrate S2's render-present/absent source identity and cannot invent a DAC reference sample. If the current S1's semantics make such recovery impossible, preserve the negative finding rather than waive it.

The parent S3 #762, R2 #733/#730, product HIL #58 and resource [T3 #767](https://github.com/jiying2007/audio-pipeline/issues/767) remain OPEN. No public ABI, physical microphone calibration/gain, ADC/DAC drift authority, fully captured 192KiB C4 memory, SSC305 10ms p99, real full-duplex AEC or product certification is claimed.
