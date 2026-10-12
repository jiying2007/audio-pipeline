# FE09-R2A — Single-core C1/C2/C4 array SDK ABI draft / 单核阵列接口研究原型

**Preregistration:** [#730](https://github.com/jiying2007/audio-pipeline/issues/730).
**Required architecture predecessor:** R1 [#728](https://github.com/jiying2007/audio-pipeline/issues/728) CLOSED `completed`; protected `main=dde6e936a159abac1b34f873c6cec19eeb4b81d9`, independent [Verify 38225457982](https://github.com/jiying2007/audio-pipeline/actions/runs/38225457982) 64 success+one skip, matching [Release 38229146978](https://github.com/jiying2007/audio-pipeline/actions/runs/38229146978) release and convergence success. The R1 19-source-anchor checker and bilingual ADR selected the *provisional* next-major **single private core** path, NOT actual public C4.

## Research-only prototype, NOT installed SDK / 仅研究原型

The only v3-sounding interface lives at
`tests/validation/frontend_evolution/fe09_array_sdk_draft_r2a.h` and is **never installed** or added to published 2.x public `include/`. No changes to production `src/`, CMake defaults, `ap_config_t`, 2.x public ABI, release assets or hardware code. No 3.x publication, E001 certification or target qualification is implied. The draft `FE_R2A_DRAFT_VERSION=0x00030000` is an internal *experiment identity*, **not an API version promised to consumers**.

`fe09_array_sdk_draft_r2a.c` is an adapter / ingress/ownership prototype only.
**All** fractional-delay FIR33 weights, geometry validation, calibration, steering, microphone-mask control and common-delay math are executed by **the same existing first-party `array_native.c` implementation**, linked unchanged. It adds only a caller-owned aligned header, S16↔F32 conversion, optional *separate reference observation* and explicit input/control validation. There is **no second FIR/BF implementation** and no second shipping DSP core.

## Bounded prototype ABI surface / 有界接口合同

`fe_r2a_config` declares `struct_size`, `api_version`, sample rate, 10 ms frame, 1/2/4 **physical** microphones, optional render-reference channel 0/1, physical reference index and active physical mask, a 3D unit source vector, per-mic XYZ metres, signed polarity/gain and explicit latency, and `capture_clock_authority=0`. Unknown descriptor versions/sizes, three microphones, bad map/position, nonfinite geometry, invalid gain/latency, render count 2 and unsupported rates are **rejected**, not coerced.

At this R2-A step **only native 16 kHz S16 interleaved** is accepted, exactly 160 *sample frames* per channel per call. In particular, 8/24/32/48 kHz are **not** claimed to work through this adapter merely because the lower-level FE array core accepts those rates. N-channel SRC + render-domain SRC, ALSA/driver integration and the real 3.x pipeline/Flight Recorder are **R2-B**, not hidden inside this step.

The input S16 capture stream uses `input_channel` as a permutation from physical microphone index to sample slot. The optional 160-sample mono render reference is **not microphone N+1** and is **not fed to BF or AEC**. R2-A separately validates, counts and fingerprints the render stream as an independent ownership proof; `render_is_not_aec=true` is an explicit scope limitation.

The adapter's state-query sums an aligned caller-owned adapter header and exactly one `fe_array_state_bytes_for_mode(N,FE_ARRAY_FIR33_HANN)` state; no additional processing cores, dynamic allocation, locks, file I/O or stateful global sources are used in the audio loop. Buffer overlap, invalid frame count, null/alias pointers, 16-byte misalignment, insufficient state bytes, overflow and invalid control flags fail closed before any state mutation. `fe_array_init` remains the geometry-validation authority.

An explicit capture-gap event resets the same FIR history and increments the capture epoch while cumulative accepted frame count survives. A render-gap event updates a **separate render epoch** and does **not** reinitialize microphone BF histories. Full `fe_r2a_reset` clears both epoch counters and cumulative frame statistics, preserving the native committed steering direction semantics; a fresh `fe_r2a_init` returns to configured initial direction. Steering and active-mic faults call the existing FE core; they are commanded controls, **not** detected DOA/microphone health.

## Frozen synthetic engineering matrix / 冻结的合成测试

| Case | Physical geometry (metres) | Render | Native FIR33 common delay |
|---|---|---:|---:|
| C1 baseline | one microphone at (0,0,0) | 0 | 17 samples |
| C2 ULA | x=0/0.035 | 1 | 19 samples |
| C4 ULA | x=0/0.035/0.070/0.105 | 1 | 22 samples |
| C4 UCA | XY cardinal points radius 0.035, ref +X | 1 | 21 samples |

All use **16 kHz, 10 ms, FIR33, (0,1,0) source direction**, gains=1, zero calibration and 100 first-party synthetic frames. Each profile is replayed twice from **freshly initialized same caller-owned arena**, with a fixed steering command at frame 25, one synthetic *lost capture frame* and actual capture-history gap at frame 50, a three-/one-of-four-or-two active mask event at frame 70 (C1 unchanged), and an independent render-gap control at frame 80 where render is present. No fabricated source/audio timestamp is used.

The C test exercises **25 explicit invalid-config, frame, alias, clock-authority and control cases per geometry**, retaining whole-arena state-byte snapshots on rejected operations; the Python verifier checks each failure count, static identities, repeat-input/render/output hashes, output saturation count, state bytes, epochs, and frame dimensions. The strict C flags remain `-Werror -Wconversion -fno-fast-math -ffp-contract=off`.

Three actual execution targets are required for R2-A:
`native`, `sanitized` (ASan/UBSan) and `arm` (Arm GNU hard-float/AArch32 under QEMU with explicit sysroot). **All three must execute and individually reproduce identical outputs across two identical runs.** Inter-architecture DSP hash identity is *not* assumed; structure/negative/resource invariants must agree. Missing toolchains or QEMU/sysroot **fails closed**. Hosted native timing uses `CLOCK_THREAD_CPUTIME_ID` around adapter `fe_r2a_process` only, excludes input generation and output hashing, and is merely descriptive; even Arm/QEMU functionality is **not SSC305 CPU p95/p99**.

## Evidence / 证据边界

Run with the existing `Quality/frontend-reference` job, not a new workflow, standalone evaluator or duplicated spatial-data pipeline:

```bash
python3 tests/validation/frontend_evolution/fe09_array_sdk_draft_qualification_r2a.py --self-test
python3 tests/validation/frontend_evolution/fe09_array_sdk_draft_qualification_r2a.py \
  --collect --output fe09-r2a --execution-source "$(git rev-parse HEAD)"
python3 tests/validation/frontend_evolution/fe09_array_sdk_draft_qualification_r2a.py \
  --verify --output fe09-r2a --execution-source "$(git rev-parse HEAD)"
```

In a container with different checkout ownership the existing CI supplies `$GITHUB_SHA`, which is *the actual execution source SHA* (a synthetic merge SHA for PR events). Python uses Git's **per-command exact checkout** `safe.directory` rather than changing global repository trust. Only a **metadata-only** four-file Artifact is retained for 30 days: `receipt.json`, `collect.log`, `verify.log`, `SHA256SUMS`. No compiled binary, test PCM, sample source or third-party DSP code is uploaded. The receipt retains source/ELF SHA256, individual functional outputs, 25 negatives per scene and timing methodology. It cannot independently recreate an expired binary, and it does not assert consumer ABI stability.

Positive verdict, only if native/sanitized/AArch32 functionality and all receipts pass:
`FE09_R2A_UNIFIED_ARRAY_SDK_PROTOTYPE_RESEARCH_ONLY_NO_RELEASE`.
Failure:
`FE09_R2A_ABI_OR_LIFECYCLE_NOT_ADMITTED`.
Either verdict is **software research only** and leaves [#730](https://github.com/jiying2007/audio-pipeline/issues/730) **OPEN for R2-B and R2-C**.

Protected source completion requires latest-HEAD Verify required `summary=success`, active strict/squash-only Ruleset 21804005, no unresolved reviews, expected-HEAD GitHub squash, then distinct fresh-main Verify and same-source Release success plus independent artifact SHA256/readback. No selected speech clip, original RealMAN Gym download, sound-quality A/B claims, actual per-ADC sample-zero/clock drift, barge-in/double-talk qualification, SSC305 hardware p99/RSS/power/thermal or E001 production acceptance.

## Next explicitly uncompleted / 下阶段未完成

**R2-B** requires separate approved next-major migration of public headers, capture SRC N+render, Linux runtime/Flight Recorder and 2.x compatibility/rollback policy, with real compiling consumer and ABI gates. **R2-C** requires independent original multi-mic clock/calibration/scene labels, true C2 vs C4 acoustic benefit, BF/AEC full duplex and physical SSC305 measurements. Original FE03 D1/S3/S5 negative admissions and frozen I025–I040 remain unchanged.
