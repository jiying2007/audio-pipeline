# FE09 T3-S2-B0 — Original FBS1 anchored bounded manifest contract / 源哈希锚定有界索引

**Implementation child:** [#797](https://github.com/jiying2007/audio-pipeline/issues/797), successor parent [#796](https://github.com/jiying2007/audio-pipeline/issues/796), top-level [#791](https://github.com/jiying2007/audio-pipeline/issues/791). Source predecessor [T3-S2-A #794](https://github.com/jiying2007/audio-pipeline/issues/794) CLOSED Completed only after protected `main=2dba395fd7d86b1e5b395f142fde15fdcd884f99` full [Verify 39132759577](https://github.com/jiying2007/audio-pipeline/actions/runs/39132759577) 74 success /1 expected skip, required summary success, same-SHA [Release 39136023423](https://github.com/jiying2007/audio-pipeline/actions/runs/39136023423) both release+convergence success and independent downloaded/rehashed 4-member [S2-A Artifact 12138806676](https://github.com/jiying2007/audio-pipeline/actions/runs/39132759577/artifacts/12138806676).

## Exact original-source B0 index / 非归档的原始源索引

This is a **NONINSTALLED research-only in-memory contract**, not yet a durable/rolling recorder, safe prune or new public APX3 serializer. Original Capture/optional owner-reported Render, first-party S1 two physical K1/K2 source queues, first-party unchanged S2 `fe_s2_writer_begin/append/finish/decode/replay` and S2-A POSIX sink are executed in the test. The B0 client observes only after S2-A has ACTUALLY fully ACKed the original APX3 + exact original 200B canonical FBS1 row. All BF/source and S2-A C implementations are frozen by predecessor SHA256 pins. The B0 layer never issues a disk syscall or deletes anything.

The B0 private **outer index** uses a fixed 160-byte little-endian header plus 200B × N **original unmodified full FBS1 rows**, N=0..16. Header offset table (all integer fields LE):

| Offset | Width | Original anchored meaning |
|---|---:|---|
| 0 / 4 | 4 / 4 | FRM1 outer magic / index version 1 (not APX3) |
| 8 / 12 | 4 / 4 | header size 160 / canonical row size 200 |
| 16 / 20 | 4 / 4 | caller-owned hard capacity 1..16 / exact retained count |
| 24 / 28 / 32 | 4 each | original input rate, physical mic count and Render owner flag |
| 36 / 40 | 4 each | pinned Capture and Render source IDs |
| 44..60 | 4×4 | pinned physical-to-PCM slot bijection |
| 60 / 68 / 76 / 84 | 8 each | source generation / last global sequence / first global sequence / high-water |
| 92..124 | 32 | SHA256 of entire immediately preceding canonical FBS1 row, required zero for unpruned B0 |
| 124..156 | 32 | first-party SHA256 of **complete outer index** with this root field zero |
| 156..160 | 4 | reserved zero; any noncanonical bits reject |
| 160.. | 200×N | original complete FBS1 rows, never a synthesized new APX3 record |

The `left_anchor_sha256` is deliberately ZERO in B0: first observed retained row must be original global Capture seq=1. **B0 cannot prune**, cannot start an unauthenticated later sequence or fake a checkpoint. Later B1 must add a trusted persisted checkpoint/root transition and explicit left-boundary prior-row SHA and lock-step retention before any old file is actually deleted. High-water == head for B0; no rolling reset, modulo-wrap alias or silent epoch restart.

## Validation and resource model / 验收矩阵

- In C, `fe_t3s2b0_bind` pins the original fully admitted S2-A owner (generation, C1/C2/C4, rate, Render config, source IDs, slot map, quota). `fe_t3s2b0_can_accept` is a pre-ACK capacity preflight; `fe_t3s2b0_observe_acked` requires an actual original S1 drain receipt, S2-A exact committed global source frame/bytes, original unchanged FBS1 200B and first-party original APX3 CRC/decode/replay/PCM witness. Failed observations never modify manifest or root.
- Strict `encode` uses a **caller-supplied bounded buffer**, with on-stack scratch for failure-atomic no-overwrite; `decode` independently recomputes header, source ID/generation, original per-row FBS1 full previous-row SHA chain, index SHA root and exact former S2-A source receipt (including last original stored FBS1 row). Unknown version, trailing garbage, short/oversized capacity, fake left-anchor, gap/duplicate/wrap, Render/owner mismatch, modified CRC/FNV or whole-root mutation is rejected. Source bytes and error output remain unchanged on failure.
- Actual first-party C matrix 4 geometries × 3 sample rates × Render disabled/owner present/owner absent × physical K1/2 = 48 source cases; 2 original source frames per case, 16 actual file/row maximum capacity, 97 byte-exact restart index roundtrips, at least 1,500 executed negative checks. Native, ASan+UBSan, ARM32/QEMU and native TSan execute twice each under the identical immutable first-party source and report cross-ISA exact JSON, binary ELF/compiler digests and SHA256 manifests. No time/stack/RSS budget claim from this index alone; original Stage-A outboard/OS resources are separate.

## Admission and forbidden promotion / 阶段边界

Latest PR-head full Verify required `summary=success`, actual scoped four-ISA compiled source evidence, original 4-member immutable GitHub Artifact upload/download and independent ZIP/inner SHA256 rehash, zero unresolved reviews, strict active Ruleset 21804005 zero bypass and expected-HEAD protected Squash. Then **different pushed-main** Verify required summary success, same-SHA Release+Convergence and independently downloaded/rehash-verified 4-member main Artifact before closing only B0 child #797.

**Not admitted by B0:** no persistent manifest root, atomic dual file+index transaction, prune/retention, safe `tail>1`, restore after deleting files, nonblocking real DSP end-to-end performance, NAND/UBIFS power-loss durability, whole SSC305 192KiB/10ms p99, actual HIL #58, public 3.x, production 2.x changes or license promotion. Parent #796/#791 and HIL #58 remain OPEN after B0.

**Candidate decision:** FE09_T3S2B0_ORIGINAL_FBS1_SOURCE_INDEX_RESEARCH_ONLY; on_disk_manifest_published=false, rolling_retention_qualified=false, durable_powerloss_qualified=false, ssc305_hardware_qualified=false, whole_device_memory_qualified=false, public_sdk_installed=false.
