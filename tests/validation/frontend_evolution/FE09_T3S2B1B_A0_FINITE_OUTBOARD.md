# FE09 T3-S2-B1b-A0 — finite original-source outboard identity (nonshipping)

Status: **RESEARCH CANDIDATE / NOT ADMITTED**, until four-target execution, protected PR merge, fresh-main Verify/Release/Convergence and independently downloaded original Artifact ZIP/inner SHA256.

Parent: [A0 preregistration #803](https://github.com/jiying2007/audio-pipeline/issues/803); program #791/#796, resource #767, HIL #58. Strict predecessor F0 #801 and CI #804 have CLOSED Completed at protected SHA 899ea11b50d58ee36837c81b30a358ad32daabd6: Verify 39245811212 (77 success, one expected skip, summary success); Release 39250589348 (release and convergence success); externally rehashed F0 Artifact 12183885542.

## What is added

A first-party **test-only** C POSIX outboard sink, distinct from the frozen S2-A 16-file source directory and bound to the original fe_t3s1_outboard_sink interface before startup. No production code or public API changes. The first-party fe_s2_decode and fe_s2_replay validate APX3/CRC/PCM. The first-party fe_b1s1_sha256 computes FBS1 and APX3 digests; no duplicate codec or checksum.

Immutable global identity: capture_source_id, source_generation, uint64 global_capture_seq, SHA256(whole original 200B FBS1 canonical row, including its digest), SHA256(complete original APX3). Neither the physical K=1/K=2 SPSC slot index nor APX3 local sequence=1 is persistent global identity.

A caller-owned finite cap **17..32** includes all original Capture sequences starting at 1, never silently rolling or modulo-reusing slots. Cap+1 must fail original S1 sink acceptance and withhold ACK with ring tail unchanged. No root pruning, source unlink, history compaction or key reuse.

Hosted transaction: owner-only directory FD, exclusive/no-follow temporary file, exact bounded original 200B row+APX3 writes, fsync(file), no-clobber hardlink publish, temp unlink, fsync(directory), separately re-open and validate complete unchanged source and FBS1 previous-row chain before S1 ACK. Unknown .part, symlinks, aliases, holes, duplicates, missing middle row, identity drift, mutated digest and wrong PCM witness fail closed. A published file after failure is **not** proof that Capture ACK occurred; recovered on-disk bytes must not fabricate source progress or a live S1 owner state.

## Fixed test matrix and negative controls

C1 / C2-ULA / C4-ULA / C4-UCA × 16/32/48 kHz × source-owned Render enabled/disabled (PRESENT/ABSENT token when enabled) × K=1/K=2 physical S1 slots = **48 profiles**. At finite cap 32: expected 1,536 first-party original synthetic 10ms APX3/FBS1 records, explicitly crossing 16→17→32, and 48 cap+1 refusals. Verify directory/byte accounting, exact restart/rebind, preserved full previous-row hash, corrupt/foreign/missing-source negatives, and bounded POSIX syscall fault injection. Frozen S2-A original directory and B0 index must remain untouched.

Mandatory actual execution: Native, ASan+UBSan, ARM32/QEMU and TSan each twice on same candidate, original source SHA256 pins, compiler/ELF digests, deterministic output and new four-member SHA256SUMS / receipt.json / collect.log / verify.log Artifact, same-run upload/download/readback. External ZIP and all inner members must be independently SHA256 checked after main push. No numerical threshold or scientific data changes.

## Correct authority and limits

- **real_rolling_retention_qualified=false**; no GC, prune, root/left-anchor transition, modulo reuse or true continuous rolling.
- **original_source_deleted=false**; cleanup removes only isolated test-owned temporary fixture, never frozen original S2-A or user/device data.
- **physical_powerloss_qualified=false**; hosted fsync and injected syscall failure cannot certify NAND/UBIFS sudden power cut or FTL/EIO/EROFS behavior.
- **ssc305_hardware_qualified=false**; no real ADC clock, Capture/Render synchronization, complete target profiling or physical HIL.
- **whole_device_memory_qualified=false**; ARM/QEMU does not prove whole-device 192 KiB RAM, stacks or 10ms p99 timing.
- **public_sdk_installed=false**; no shipping API/ABI, v3 major release or four-mic BF/AEC performance claim.

This independently bounded outboard experiment is NOT durable rolling-storage certification. A1 must later independently prove nonzero-left-anchor immutable root without deletion; A2 must independently prove deletion/GC only after correct root publication/readback and crash scenarios. Preserve frozen I025–I040 research and noncommercial source/data rights.

## CI acceptance

Reuse Verify and separate quality/frontend-s3-t3s2b1ba0 job, exact source build/negative checks, no-waiver failure handling, four-member run Artifact and same-run readback. Only latest exact-head full Verify required summary=success, active Ruleset 21804005, zero bypass/unresolved reviews and expected-head protected squash permit merge. Then a distinct pushed-main full Verify required summary success, same SHA Release+Convergence success and external original ZIP+inner verification are mandatory before closing only #803. Parents/HIL remain OPEN.
