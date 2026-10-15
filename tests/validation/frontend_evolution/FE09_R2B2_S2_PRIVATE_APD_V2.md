# FE09-R2B2-S2 — experimental APX3 record, parser and bounded replay
# 非安装版 APD-v2 私有记录、解析及有界回放（研究用途）

**Prerequisite / 前置准入：** [#755](https://github.com/jiying2007/audio-pipeline/issues/755) CLOSED completed at protected `main=580d2b565f62fc9b29ef9237b498898c89e51b05`. Exact fresh-main [Verify 38694644604](https://github.com/jiying2007/audio-pipeline/actions/runs/38694644604), required `summary=success`, 64 passed + 1 expected skipped; same-source [Release 38698209211](https://github.com/jiying2007/audio-pipeline/actions/runs/38698209211) 2/2 success; B2-S1 [Artifact 11953149317](https://github.com/jiying2007/audio-pipeline/actions/runs/38694644604/artifacts/11953149317), four-member download/readback SHA256 `29741fc36d0df6e2f71582e98225700d6f72fdb779433a515389f542de08328d` passed. **Independent preregistration:** [#760](https://github.com/jiying2007/audio-pipeline/issues/760), parents #733/#730.

## Frozen software-only boundary / 软件边界

This is a **research-only, test-directory C codec**, not the installed/public 3.x SDK. The separate first-party C1/C2/C4 SRC/FIR33 research core remains in B2-S1; this phase adds **no new DSP**. Nothing changes under shipping `src/`, public `include/`, CMake, `src/platform/linux/ap_runtime.c`, `tools/apdump.py`, `tools/apreplay.py`, or existing APD2/v1 writer/reader semantics.

The new magic is **`0x33585041` (ASCII `APX3` in little endian)**, strictly distinct from legacy `APD2=0x32445041`; the private schema/version is **2** and the endian witness is `0x01020304`. `APX3` is an *experimental filename/header discriminator*, not a production-format upgrade. The old shipped reader must reject it by magic. This new parser rejects APD2 outright, with no guessed compatibility fallback.

### Fixed byte-level wire contract

All numbers are explicitly encoded little-endian, independent of the compiler's struct layout or CPU endianness. There is **no struct-memory dump, heap, unbounded parser or unverified timestamp**. The header is exactly **128 bytes**, records contain exactly one 10ms frame, max **128 frames** and **1 MiB** in total.

| Offset (bytes) | Width | Content |
| --- | ---: | --- |
| 0, 4, 8, 12 | 4 each | `APX3` magic, schema 2, endian tag, header byte count 128 |
| 16, 20, 24, 28 | 4 each | checked total bytes, bounded frame count, source rate, rate/100 samples |
| 32, 36, 40, 44 | 4 each | C1/C2/C4 physical microphone count, independent optional mono render, exact record stride, active mic mask |
| 48–63 | 4 × 4 | bijective physical-to-capture-slot mapping; unused slots must be `0xffffffff` |
| 64–79 | 4 × 4 | logical capture/render source identifiers, separate nonzero epochs (render absent => zero) |
| 80–95 | 4 × 4 | clock authority UNKNOWN=0, both timestamp-valid bits zero, flags/reserved zero |
| 96–123 | 28 | all reserved bytes zero |
| 124–127 | 4 | CRC32/IEEE of the preceding 124 header bytes |

Each record is `32-byte metadata + physical capture PCM (int16 LE interleaved) + optional independent mono-render PCM (int16 LE) + 4-byte CRC32/IEEE`. Metadata uses 64-bit frame sequence, two 32-bit source flags, two 32-bit epochs, and two explicit timestamp-valid fields (always zero). Each record CRC covers everything except its final CRC field.

Per-stream exact stride and total byte count are overflow-checked before any write/read. Frame sequences must start at 1 and remain strictly increasing; jumps require explicit source gap flags. Capture-only discontinuity changes only its capture epoch; render discontinuity independently changes render epoch; shared clock reset must be consistently flagged by both when render exists. Missing/unknown physical ADC or DAC timestamps are **not inferred, defaulted to measured, or synthesized**. The source IDs are logical test labels, not proof of hardware timebase.

**Writer:** caller-owned destination and state; initialization and rejected input cannot touch caller bytes; each admitted frame is encoded once, with canonical byte order and record CRC, and incomplete output cannot finish. **Reader:** first validates the entire header, all record CRCs, sequence/epoch/flag semantics and exact file length; no caller stream output is changed on a format rejection. **Replay:** only invokes the supplied observer after the entire file validates; observer receives immutable LE PCM bytes, never an unaligned host pointer. The optional decoded-result structure must not overlap any input-file byte; aliasing is rejected before callbacks and leaves the source untouched (tested on Native/Sanitizer/AArch32). Callback-side effects on a callback error remain explicitly caller-owned.

## Qualification / 资格认证

The nonshipping `fe09_b2s2_private_apd_test.c` uses 12 immutable synthetic profiles (C1 baseline, C2 ULA, C4 ULA, C4 UCA × 16/32/48k), each with **render absent and render present**, two byte-identical generations, 100 frames per subcase, and a checked replay callback against the original synthesized PCM. It injects explicit source gaps, capture/render epoch discontinuities, global clock reset and XRUN. At least 60 distinct negative parser/writer mutations must fail closed per subcase, including header/record corruption, invalid sequence/source/mask/endian/CRC, legacy version confusion, truncation, trailing bytes and rejected-write rollback. Per-10ms hosted p95/p99 encode timing is descriptive stderr only, not an SSC305 deadline claim.

`fe09_b2s2_private_apd_qualification.py` compares actual C execution on **native GCC, ASan+UBSan and ARM32 GNU/QEMU**, twice per target, with exact source/binary SHA256 and frozen predecessor B2-S1 + legacy-source identities. Because this wire format is explicitly LE, bit-identical serialized bytes and per-profile hash equality **are required across these three synthetic ISA targets**. It also calls the original `tools/apdump.py` parser against APX3 magic to prove old-reader rejection. Four-member `SHA256SUMS, receipt.json, collect.log, verify.log` Artifacts are source-bound and retained 30 days, with independent upload/download/re-hash.

Offline commands (require real native and ARM/QEMU compilers and the frozen source tree):

```sh
python3 tests/validation/frontend_evolution/fe09_b2s2_private_apd_qualification.py --self-test
python3 tests/validation/frontend_evolution/fe09_b2s2_private_apd_qualification.py --collect --output fe09-b2s2 --execution-source "$(git rev-parse HEAD)"
python3 tests/validation/frontend_evolution/fe09_b2s2_private_apd_qualification.py --verify --output fe09-b2s2 --execution-source "$(git rev-parse HEAD)"
```

## Admitted/not admitted / 正反准入

Expected **software-only** decision:
`FE09_R2B2_S2_PRIVATE_APD_V2_READ_WRITE_REPLAY_RESEARCH_ONLY_NO_PUBLIC_ABI`.

Negative decision:
`FE09_R2B2_S2_FORMAT_PROVENANCE_OR_ARITHMETIC_DRIFT_NOT_ADMITTED`.

**NOT admitted:** public 3.x SDK, v2 production writer/reader, physical four-mic gain, microphone geometry/calibration, real ADC/DAC clock, cross-clock synchronization, real full-duplex AEC, actual SSC305 10ms p99/RSS/192KiB whole-system, device HIL, E001 and Product Certification. Existing independent #733/#730 and #58 stay open. No paid services and no replacement of frozen real/public audio with synthetic evidence.
