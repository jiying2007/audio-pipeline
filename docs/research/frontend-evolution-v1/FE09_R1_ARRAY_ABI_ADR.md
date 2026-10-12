# FE09-R1 — Public C1/C2/C4 array API/ABI architecture decision / 四麦公开 SDK 架构决策

**Stage:** Design qualification only, no shipping/public C4 implementation.  
**Pre-registration:** [#728](https://github.com/jiying2007/audio-pipeline/issues/728); independent predecessor [FE09-R0 #726](https://github.com/jiying2007/audio-pipeline/issues/726) is CLOSED completed.  
**Frozen evidence base:** protected `main=c1b91e5086b0f8a3e82dc35506de4bcc1be58942`, [Verify 38207813048](https://github.com/jiying2007/audio-pipeline/actions/runs/38207813048) success (64 passed + one expected skip, required summary success), same-source [Release 38209605747](https://github.com/jiying2007/audio-pipeline/actions/runs/38209605747) release/convergence success. R0 metadata [Artifact 11727908969](https://github.com/jiying2007/audio-pipeline/actions/runs/38207813048/artifacts/11727908969) ZIP SHA256 `829ea522bce9e45b281b752808b2eac79cce620d6e67fc10cbd630d809eee315` independently verified.

**Architectural decision (provisional):** `B_NEXT_MAJOR_SINGLE_PRIVATE_ARRAY_CORE`. The *only admissible R1 outcome* is `FE09_R1_PUBLIC_ARRAY_ABI_ARCHITECTURE_REVIEWED_NO_PRODUCT_PROMOTION` after exact-head and fresh-main governance. This is a **design review conclusion, not an executed public ABI change, 3.x SDK, qualification or release**. 中文：此阶段选择后续统一四麦架构的设计方向，**不是已落地的产品四麦**。

## A versus B / 方案对比

| Axis / 对比维度 | A — additive 2.x C4 sidecar / 外挂四麦旁路 | B — next-major unified C1/C2/C4 array / 统一下一主版本 |
|---|---|---|
| Existing 2.x ABI | Can preserve existing symbols/layout by publishing *separate* versioned array→mono entrypoint | Requires explicit next-major API/ABI governance for changed capture/config/layout |
| Source evidence | R0 proves functional FIR33 array→mono S16→existing 2.x mono SDK only | First-party noninstalled array core supplies control/memory research patterns, not public source admission |
| Processing ownership | Independent BF and SDK histories, two reset/discontinuity/latency owners; duplicated input conversion | One physical capture/geometry/control owner and one downstream mono DSP chain; shared explicit frame epoch |
| Runtime/Flight Recorder | External arrays and old recorder/queues have separate capacity and tracing identities | Must migrate capture queues, recorder dump format, S16 source selection, runtime invariants together |
| CPU, memory, audio quality | Adds copy/transition cost, still needs target measurements | More migration risk initially; enables bounded scratch and one authoritative scheduler but **no proven savings** |
| Product maintenance / 长期维护 | Risks permanent duplicate DSP cores / ABI wrappers | Prefer **one private DSP core**, no indefinite sidecar, only one authoritative scorer |
| Verdict / 结论 | `RETAIN_AS_BOUNDED_R0_REFERENCE_NOT_PRODUCT_DEFAULT` | **`B_NEXT_MAJOR_SINGLE_PRIVATE_ARRAY_CORE`**, provisional R2 design input |

A remains valid as a **frozen research reference**, not a second maintained shipping backend. B is selected *provisionally* because one authoritative private core and one lifecycle fit the declared objective; no production benefit, cost reduction or acoustic gain is presumed. Breaking installed structs or symbols while claiming 2.x ABI compatibility is explicitly forbidden.

## Source traceability / 源代码可追溯矩阵

This table is bound by the first-party, fail-closed contract at `.github/research/frontend-evolution-v1/fe09-r1-public-array-abi-contract.json`. Source anchors refer to the protected R0 main, not hypothetical 3.x source. A standalone checker verifies the actual **current** source remains within these 2.x guardrails.

| Actual source / 已审查文件 | Evidence / 已证实事实 | Design consequence / 架构约束 |
|---|---|---|
| `include/audio_pipeline/audio_types.h` | `AP_MAX_MIC_CHANNELS=2`, 10 ms and build-info source/config identity | Do not repurpose existing public 2.x fields to represent four microphones |
| `CMakeLists.txt` | Build mic max 1/2, hard-rejects >2; project 2.x, BF direction tracking two-mic | A new 3.x SKU/profile/major-version migration is required for native public C4 |
| `src/core/ap_pipeline.c` / `src/core/ap_pipeline_internal.h` | BF requires two physical mics, local mic0/mic1 buffers and one downstream mono | Rework array ingress and buffers as a **single** core rather than flipping channel macro |
| `src/frontend/ap_frontend.h` / `include/audio_pipeline/audio_modules.h` | Two-channel lag history; public standalone BF takes mic0 and mic1 | Geometry-based C1/C2/C4 data-plane processing needs a future explicitly versioned API |
| `src/frontend/ap_resampler.h` | Exactly three input histories (mic0, mic1, independent render reference) | Scale capture histories by physical mic count N, keep render history separately owned |
| `src/platform/linux/ap_runtime.c` | Capture queue bound by compiled mic max; recorder config rejects >2; frame stride grows by mic count | Change FIFO, dumps, Flight Recorder, replay and reader/provenance format atomically with future ABI |
| `include/audio_pipeline/audio_pipeline.h` / `src/core/ap_pipeline_query.c` | Existing capture/control/reset API and discontinuity model | Align capture gaps, clock reset, BF steering/mask, AEC epoch and frame counters |
| `tests/validation/frontend_evolution/array_native.h` | Noninstalled research supports 1/2/4, XYZ, mapping, gain/polarity, latency/steering/fault mask | Evaluate lifting **one audited implementation** into a future private core, not copies |
| `tests/validation/frontend_evolution/array_sdk_bridge_r0.py` | R0 true linked 2.x mono SDK, 3 geometries, 100-frame×2, 13 negative controls | Proven **research bridge only**; direct 2.x C4 remains rejected |
| `docs/API_CONTRACT.md` | Published 2.x source/ABI compatibility and `struct_size`/`api_version` conventions | Publish a separate next-major compatible contract and preserve old immutable tags |

## Data-flow and ownership / 数据流及控制归属

```text
Physical microphones N=1/2/4      Playback render reference R=0/1 (mono)
  └─ interleaved S16 (physical slots)          └─ separate mono S16 path
     └─ validate sample rate/map/XYZ             └─ own clock epoch and SRC history
        └─ per-mic capture SRC, gain/polarity         │
           └─ bounded FIR/beam steering, fault mask  │
              └─ single mono BF output (float)       │
                 └─ SYNC and single AEC reference <──┘
                    └─ RES → NS → AGC → VAD → mono S16 output
```

- **Frames:** fixed 10 ms; at 16 kHz 160 samples/mic (C2 S16 640 B; C4 1280 B), at 48 kHz 480 samples/mic (C2 1920 B; C4 3840 B). Frame count is **per physical channel**, not interleaved scalar count. Resampling from 48k to 16k needs N microphone state histories plus separately owned playback-reference SRC. No implicit mic duplication, render-as-mic, silent downmix or unqualified rate conversion.
- **Configuration ownership:** future public *conceptual* array descriptor carries `struct_size`, `api_version`, physical mic count, render count, capture-slot permutation, per-mic position XYZ metres, reference physical mic index, signed gain including polarity, calibration delay and **evidence provenance**. These are **not installed or frozen public C structs** today. Reject NaN/Inf, duplicate slots/positions, out-of-range gains/delays, invalid frame sizes, insufficient aligned state and overlapping input/output/state without partial mutation.
- **Capture timebase:** ADC sample-zero alignment, independent ADC drift, camera/audio epoch and source calibration for actual recordings remain `UNKNOWN`. A first-party synthetic frame clock or Gym GCC-PHAT lag peak is NOT an absolute shared hardware timestamp.
- **Signal order:** use BF→single AEC→RES/NS/AGC/VAD as the conservative resource topology **only as an experiment candidate**. Preserve per-mic AEC→BF counterfactual. Existing FE04 paired/order experiment is synthetic/oracle-bounded and does not qualify physical double-talk, barge-in or best order for real PCM.
- **Discontinuity owner:** one validated sample-frame boundary dispatches capture gap, render gap, route/codec/clock reset, BF history/mask/steering cancellation and SYNC/AEC epoch invalidation. No automatic “click-free” claim. Counters for per-epoch state and cumulative frames are distinct; rejected control operations must be atomic. Steering observations must carry source clock and age, not fabricated DOA certainty.
- **Fallback:** C1 pass-through, C2 conservative default, C4 only with independently valid geometry/calibration/clock provenance; bad microphone mask, clipping and actuator/motor noise are separate fault signatures, not unqualified automatic sensor certification.

## Resource, quality and release gates / 资源、效果与发布

R0 measured only array-state + actual mono 2.x SDK state: C2 `2,152 + 78,192 = 80,344 B`; C4 `3,704 + 78,192 = 81,896 B`. This excludes **all capture FIFO, recorder, diagnostics, temporary scratch, thread stacks, final linked ELF, Linux runtime RSS, sysroot, algorithmic/end-to-end latency and I/O DMA**, so even the **192 KiB full C4 research budget** is *not admitted*. Host thread-CPU observations include harness work (hashes/convert/render), and neither hosted nor Arm/QEMU timing is SSC305 p95/p99.

Required later independent gates:
1. **R2 implementation:** explicit next-major 3.x SemVer/ABI proposal, additive or breaking header shape review; actual one-core C1/C2/C4 channel mapping, runtime/Flight Recorder size and dump changes, legacy C2 bitwise/regression baseline, source/build/package/ABI identities. No automatic 2.x aliases to perpetuate duplicate backends.
2. **Real acoustic selection:** rights-audited aligned actual source, separate BF functionality vs benefit, far-field near+echo/double-talk, moving speaker/robot motor/noise, target transfer/ESTOI/SIR/WNG, loss/negative and uncertainty intervals; no known-direction oracle promoted as a DOA tracker. Preserve room/geometry data lineage.
3. **Real SSC305 qualification:** vendor BSP/compiler/sysroot ABI, CPU/p95/p99/10ms hard deadline, scheduler/thermal/power/RSS/stack/I/O, full duplex AEC and HIL; separately migrate E001 qualification. Original FE03 D1/S3/S5 failed source admission and D2-S6 no-clock-authority stay explicitly negative.

**No implemented public C4 ABI. No published 3.x SDK. No source-clock or BF/DOA quality claims.**  
**未完成：正式四麦 SDK、真实阵列效果及 SSC305 量产验收。**

## Deterministic offline gate / 防漂移门禁

The read-only checker `tests/validation/frontend_evolution/fe09_array_abi_contract_r1.py` is executed by the existing `.github/scripts/verify-docs-gate.sh` for docs-only and full CI. It validates 19 concrete source anchors, the frozen R0 evidence identity, A/B architecture decision, all original false product-claim flags, and this bilingual ADR. Negative fixtures mutate each source anchor and promotion flag and must **fail closed**. It neither reads third-party audio nor modifies files, CMake, exports, ABI, product C code or model parameters. No new GitHub workflow or large Artifact.

```sh
python3 tests/validation/frontend_evolution/fe09_array_abi_contract_r1.py --self-test
python3 tests/validation/frontend_evolution/fe09_array_abi_contract_r1.py --check
```

R1 closure is permitted only after exact-HEAD full Verify required `summary=success`, active strict/squash-only Ruleset 21804005, protected expected-head merge, and a **distinct merged-main** Verify and matching-SHA Release both successful. If any claim/source contract mismatches, emit `FE09_R1_ARCHITECTURE_UNRESOLVED` and preserve the failure; never silently widen the current 2.x ABI.
