# FE09-R2B2-S0 — Linux runtime / Flight Recorder cutover preflight
# Linux 运行时与记录格式迁移预检（只读）

**Stage:** `FE09_R2B2_S0_RUNTIME_RECORDER_PREFLIGHT_RESEARCH_ONLY_NO_PUBLIC_ABI`

Independent research protocol [#749](https://github.com/jiying2007/audio-pipeline/issues/749), parent [#733](https://github.com/jiying2007/audio-pipeline/issues/733) / [#730](https://github.com/jiying2007/audio-pipeline/issues/730). Protected predecessor: `e30c1e5e0619f02554077ed81dac312245aa4a31`. FE09-B1A / B1B-S0 / B1B-S1 were independently admitted as **noninstalled software research**, most recently S1 protected `626fd6a9d29ad5d5f61bc4b643c983f9546327d1` with exact-main Verify 38512013766 and Release 38515010354. **No public 3.x SDK, physical array efficacy, device timing or 192KiB full system claim is implied.**

## Grounded 2.x boundary / 现有代码事实

| Existing source | Authoritative old contract | Why C4 is blocked |
|---|---|---|
| `src/platform/linux/ap_runtime.c` | `AP_RT_MAX_CAPTURE=AP_BUILD_IO_FRAME_MAX*AP_BUILD_MAX_MIC_CHANNELS`; input/output and control/event rings; N capture plus separate render storage | Capacity is build-time 2.x, not dynamically queryable C4 |
| `src/core/ap_pipeline_internal.h` | One `ap_resampler_state_t`, `mic0/mic1/reference` scratch and fixed stages | Not N independent SRC+one first-party array BF data plane |
| `include/audio_pipeline/audio_runtime.h` | Public runtime API v1, 64KiB runtime cap, command/event queue depth 2; capture/render discontinuity metadata | Must not modify installed ABI or claim timestamps imply ADC/DAC clock synchronization |
| `include/audio_pipeline/audio_diag.h` | Public diagnosis API v1, `AP_DUMP_MAGIC=0x32445041` (APD2 little-endian), `AP_DUMP_FORMAT_VERSION=1` | A silent C4 increase would reuse the wrong file identity |
| `src/platform/linux/ap_runtime.c` recorder | `recorder_config_valid` rejects `mic_channels>2`; slot includes MIC, optional independent render, output, metrics | Recorder is not C4 just because sample rates include 8/16/24/32/48k |
| `tools/apdump.py` | Little-endian `<12I24s12s12s12s16s` file header, `<QQQII` record header; only 1/2 physical microphones; rejects version !=1 and bad endian/stride | C4 needs a separately versioned reader, not undocumented acceptance |
| `tools/apreplay.py` | Consumes `apdump.py` and supplies `--mic-channels` from its parser | Producer, parser and replay must cut over together |
| `tests/diagnostics/generate_fault_dump.c` | Fixed capture gap/render gap/clock reset/xrun/codec reopen source events | Useful synthetic regression, **not** measured capture sample-zero/drift |

All above bytes are pinned by a 13-file first-party Git-blob manifest `fe09_r2b2_runtime_recorder_contract_s0.json`. `fe09_r2b2_runtime_recorder_preflight_s0.py` checks the actual source bytes and exact source anchors; it does **not** patch them. The receipt publishes actual file SHA256 digests, source blob count, contract hash and strict nonshipping booleans.

## Two mutually exclusive architecture choices / 架构决策

**Selected for future independent experiment: next-major single private core.** A configuration-specific, caller-owned and aligned N+render arena contains N physical per-source SRC histories, an optional **separately clocked** mono render state, exactly one first-party FIR33 array BF, and explicit source/control epochs. A future private worker and queue/recorder sizing API can be qualified before any public ABI decision. No heap, locking, I/O or unbounded work in the 10ms callback; atomic failure/no partial frame commit. C2 legacy remains the frozen 2.x baseline, **not a compatibility layer inside future-major 3.x**.

**Rejected: permanent 2.x dual sidecar / 永久旁路双核心。** A second standing FIR/SRC algorithm or a raised global `AP_BUILD_MAX_MIC_CHANNELS` leaves runtime queue capacities, capture aliases, memory/recorder format, clocks, reader and rollback unsolved while duplicating the algorithm authority. Do not implement this as product code.

## Private v2 dump sketch — not implemented / 未来私有格式草案

An independently preregistered future B2-S1 would need a **new format identity**, proposed schema version 2 and *new magic yet unassigned*, explicit endian, physical mic count 1/2/4, complete capture-slot permutation, independent `render_channels=0/1`, per-source rates/epochs, capture/render timestamps with provenance, checked total stride arithmetic, reserved fields and bounded per-frame length, and a separate parser/replayer migration gate. **APD2/v1 remains unchanged** and rejects C4/unknown v2/truncation by design. Never claim future v2 is readable by existing `tools/apdump.py`; record exact negative-fault fixtures and new/old reader rejection before considering installed 3.x.

For actual future consumer prototypes, only **fixed** 16/32/48kHz 10ms input → 16k/160-sample BF has first-party B1 evidence. 8/24k, asynchronous DAC/ADC clocks, RealMAN physical calibration, SSC305 p99/RSS/stack/thermal/power and full C4 192KiB need their **own** evidence. Fake/unknown timestamps are not made real by counter increments.

## Offline verification / 只读资格运行

```sh
python3 tests/validation/frontend_evolution/fe09_r2b2_runtime_recorder_preflight_s0.py --self-test
python3 tests/validation/frontend_evolution/fe09_r2b2_runtime_recorder_preflight_s0.py --check
```

The self-test uses 9 synthetic possible configuration descriptions and **at least 40** deliberate invalid capture slot/clock/format/mic/rate/mask/ABI transitions, plus frozen-contract and per-source-blob mutation rejection. This is an architectural *screen*, not evidence that a future major runtime has been built or tested.

**Positive only after gates:** `FE09_R2B2_S0_RUNTIME_RECORDER_PREFLIGHT_RESEARCH_ONLY_NO_PUBLIC_ABI`.

**Fail closed:** `FE09_R2B2_S0_RUNTIME_DUMP_OR_ABI_DRIFT_NOT_ADMITTED`.

Before closing #749 require a fresh protected-main Verify with required `summary=success`, exact-SHA Release, strict ruleset 21804005, clean standalone PR-head checks and complete source/receipt readback. Parent #733/#730 and hardware #58 remain OPEN. **No changes** to shipping `src/`, installed `include/`, default CMake, public ABI, APD2 dump writer/parser, real device, releases, licensing or I025–I040 frozen research.
