# FE09-R2B2-S3-T1 — private S1 frame truth and uint32 rollover
# 私有多线程输入 PCM 源身份见证与 32 位 SPSC 索引环绕验证

**Independent protocol:** [#764](https://github.com/jiying2007/audio-pipeline/issues/764). Its protected T0 predecessor was [PR #763](https://github.com/jiying2007/audio-pipeline/pull/763), merged source `97e0704bd97e4709571e727d7f5c818e13bb8f97`, with distinct [fresh-main Verify 38764545602](https://github.com/jiying2007/audio-pipeline/actions/runs/38764545602) (64 successful jobs, one expected skip, required summary success), same-source [Release 38769621816](https://github.com/jiying2007/audio-pipeline/actions/runs/38769621816) (2/2 success) and [Artifact 11989885905](https://github.com/jiying2007/audio-pipeline/actions/runs/38764545602/artifacts/11989885905) (4 member archive, 5,369 B, externally read back, SHA256 `7cc10d76f8f6ac9c00893879e43bc7447d1d9b91fdd6fa16e79282ea9bfe54c5`).

This T1 is an **uninstalled research candidate**, not software-qualification or public SDK. It adds no new DSP. The frozen source Git blobs for S1 (first-party SRC/FIR33 C1/C2/C4 queue), S2 (private LE APX3) and T0 (pthread worker/shadow-then-commit recorder) must match that predecessor main at all qualification points.

## Exactly scoped source-bound producer facade / 真实输入约束

- `fe09_b2s3_t1_source_witness.[ch]` defines an **exclusive producer-only facade** around *unchanged S1* `fe_b2s1_submit_capture` and `fe_b2s1_submit_render`. Each producer first copies user PCM into a bounded private staging slot, submits those identical staged bytes to the **real frozen S1** API (which copies them into its opaque queue), then independently retains an exact byte-for-byte witness, sequence, flags, epoch and sample count; only afterwards does it release-publish its witness slot to the worker.
- The independent worker acquire-loads both source publication counters, compares the candidate APX3 frame's actual PCM, sequence, flags, epoch, count and timestamp validity **against both immutable source witness copies**, before calling the frozen S3 T0 `fe_s3_bridge_step`. Its transaction has only one outcome: reject before queue consume / writer commit, or consume actual S1 then commit one source-attributed APX3 record. On success, the worker release-acknowledges both witness tails; producers can reuse a slot only after observing that acknowledgment.
- This cannot authenticate a caller that **bypasses** the exclusive facade and writes S1 directly, or magically detect live hardware sample-zero/drift. Such external S1 queue contents have no witness and must never be automatically assigned an APX3 identity. A tampered same-sequence candidate is rejected by actual PCM `memcmp`, not by an unbound metadata hash. The test deliberately mutates valid-sized capture/render PCM *after S1 submission* and proves no S1 dequeue, BF output or retained APX3 change.
- Cross-source timestamps remain UNKNOWN. There is no allocation, locking, blocking I/O, artificial silence, new resampler, clock inference or dynamic writer format in a successful frame path. Quiescent-only original S1 `fe_b2s1_get_info` is not polled concurrently. All sources/worker are serialized by the test facade's ownership rules, not by assuming direct S1 writes from other users are safe.

## Actual unsigned wrap testing / 索引环绕

- `fe09_b2s3_t1_source_wrap_test.c` links the *original frozen S1* implementation directly in a **single test-only translation unit**, allowing the quiescent test to seed capture head/tail, and optionally render head/tail, to `UINT32_MAX-2`. No S1 source modification or new public seed/reset API is introduced. This is a white-box test of the real internal C11 atomics, *not* a fake model of their arithmetic.
- Actual pthread producers and consumer then execute 100 real 10ms frames, crossing the 32-bit wrap boundary with both depth 2 and depth 4. 48 combinations (C1 baseline, C2 ULA, C4 ULA, C4 UCA × 16/32/48 kHz × render absent/present × depth 2/4) are tested for no duplicate/lost frame, correct first-party BF against an independent direct oracle and strictly replayable APX3 bytes. On each target the run also executes **another 48 real threaded profiles** using the attested facade with exact PCM identity, for 9,600 accepted frames per target.
- ≥130 targeted negative controls include valid-sized PCM altered after S1 submission, capture/render flags/epoch mismatch, forged/rewound sequence, timestamp-valid spoof, nonattested outsider S1 submission, successful continuation after rejects, producer/worker quiescence and frame-byte/recorder rollback. A near-wrap test **does not** qualify arbitrary real source clocks or render-only liveness recovery.
- Exact wire-format output has deterministic per-profile 64-bit byte hash and total digest (a *test comparator*, not a cryptographic source-integrity receipt). The independent SHA256 member/source/binary receipt provides cryptographic provenance.

## CI and admission / 准入约束

The `fe09_b2s3_t1_source_wrap_qualification.py` is required to actually compile and execute the same unchanged original C implementation on native GCC, ASan+UBSan, ARM32/QEMU and native ThreadSanitizer, twice per target. It compares per-scene APX3 LE bytes across targets while comparing floating BF outputs **only within the same ISA**, and enforces exact protected-source/binary hashes. Native TSan cannot be represented as ARM TSan. A real thread/data-race failure, compiler issue, missing QEMU, bad mutation count, nondeterministic byte result, wrong SHA or missing Artifact is a **fail-closed** outcome.

The existing Docs Gate self-test and `quality / frontend-reference` carry the actual C qualification. Preserve one tiny `SHA256SUMS, receipt.json, collect.log, verify.log` run-bound 30-day Artifact, independently re-download from GitHub Actions and rehash all members/source/target/nonpromotion flags before PR can pass.

```sh
python3 tests/validation/frontend_evolution/fe09_b2s3_t1_source_wrap_qualification.py --self-test
python3 tests/validation/frontend_evolution/fe09_b2s3_t1_source_wrap_qualification.py --collect --output fe09-b2s3-t1 --execution-source "$(git rev-parse HEAD)"
python3 tests/validation/frontend_evolution/fe09_b2s3_t1_source_wrap_qualification.py --verify --output fe09-b2s3-t1 --execution-source "$(git rev-parse HEAD)"
```

**Not admitted / 未闭环:** physical ADC/DAC clock/time alignment, unbiased live producer authentication outside the private facade, automatic render-only queue resynchronization preserving microphone histories, a complete two-thread/three-thread stack/SRC/BF/recorder memory optimum below SSC305 192KiB, actual SSC305 10ms p99/thermal/power, real physical C4 DOA/WNG/BF gains, full-duplex AEC product acoustics, HIL/E001 or public 3.x SDK. S3 parent #762, R2 #733/#730, hardware #58 remain OPEN after T1. No paid resource and no unlicensed dataset.

**Research-only decision if all gates succeed:**
`FE09_R2B2_S3_T1_EXACT_SOURCE_WRAP_RESEARCH_ONLY_NO_PUBLIC_ABI`.
**Fail-closed:** `FE09_R2B2_S3_T1_UNBOUND_FRAME_OR_UINT32_WRAP_NOT_ADMITTED`.
T1's **own** protected merge requires exact HEAD full Verify/summary, four-member upload/readback, strict ruleset and no unresolved review threads, expected-HEAD squash, and **distinct** new-main Verify+same-source Release. A green PR without all of these is still not terminal acceptance.
