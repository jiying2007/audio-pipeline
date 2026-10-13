# FE09-R2B1A — separated C1/C2/C4 capture + render ingress / 四麦分离输入合同

**Independent preregistration / 独立预注册:** [#735](https://github.com/jiying2007/audio-pipeline/issues/735). Parent [#733](https://github.com/jiying2007/audio-pipeline/issues/733) and physical [#730](https://github.com/jiying2007/audio-pipeline/issues/730). B0 predecessor protected main a0fc70d8fd1f325d8e86189eb0b131e034a79ecc, distinct [Verify 38351439101](https://github.com/jiying2007/audio-pipeline/actions/runs/38351439101) 64 successes + one expected skip / required summary success, exact [Release 38353815260](https://github.com/jiying2007/audio-pipeline/actions/runs/38353815260) 2/2 success.

## Engineering function / 实际作用

The only new C implementation is in tests/validation/frontend_evolution/fe09_b1a_ingress.[ch]. It is first-party, **noninstalled, nonpublished**, not compiled into shipping 2.x and not a 3.x public C SDK.

- Exactly 16kHz / 10ms / **160 sample frames per physical mic**. Input: interleaved signed S16, with explicit physical-index to capture-slot permutation. Output: physical-mic-major normalized Float32. No hidden downmix, channel duplication or resampling.
- Support **1, 2 or 4 physical mics** and independently **0 or 1 mono DAC render channel**. Render has its own separately checked buffer, epoch and fingerprint. Render is **NOT connected to BF or AEC**.
- Caller-owned configuration-specific state-size/alignment query; 16-byte alignment, strict private descriptor size/version, finite fixed-rate contract, no heap/locks/blocking I/O in audio callback. Physical active masks are commanded, not detected; masked microphone output is zeroed explicitly rather than substituted from other mics. No missing input channel is fabricated.
- Capture gap resets only physical mic source fingerprints and capture epoch. Render gap resets only reference history/epoch. Clock reset increments common clock epoch and both physically available epochs; cumulative frames survive, per-epoch counters restart. No synthetic event is a qualified ADC sample-zero/clock assertion.
- Invalid count 3, render count 2, unsupported 8/24/32/48k, bad/reserved/clock fields, missing/duplicate/out-of-range slots, overwide/zero masks, null/aliased input/output/state, partial frames, undersized/misaligned state and unknown gap flags are rejected without state/output mutation.

## Frozen synthetic engineering matrix / 冻结合成验证

| Fixed label | Physical mics | Render | Physical-to-slot permutation | Mask at frame 70 |
|---|---:|---:|---|---|
| C1_BASELINE | 1 | 0 | 0 | 1 |
| C2_ULA | 2 | 1 | 1,0 | 1 |
| C4_ULA | 4 | 1 | 2,0,3,1 | 13 |
| C4_UCA | 4 | 1 | 3,2,1,0 | 13 |

ULA/UCA here are **case names, not interpreted XYZ geometry**. The ingress does not evaluate BF coefficients or spatial response. Each fixture generates 100 source-only deterministic 10ms frames, explicit INT16_MIN/MAX input, then repeats with independently initialized same aligned memory. Frame 50 genuinely skips one capture source index and notifies a capture gap; frame 70 changes commanded active masks; frame 80 genuinely skips one render index and notifies an independent render gap only if render exists; frame 90 notifies CLOCK_RESET. Fixed positive counters: 100 accepted frames, capture_epoch=2, render_epoch=2 if reference exists otherwise 0, clock_epoch=1, 10 accepted per-source frames since last reset. No artificial source timestamps.

Per fixture, at least 25 separately executed malformed-config, frame-size, alias, gap, mask and buffer/state-integrity negatives are checked against full state and output snapshots. Exact physical float output and optional render float output are compared per sample. Native C11, ASan+UBSan and GNU AArch32/QEMU execute twice each with same-target repeat equality; cross-target source/control/negative invariants compare, not compiler-private struct sizes or host floating hash identity. Missing compiler/QEMU/sysroot fails closed. Strict -Werror, -Wconversion, -ffp-contract=off and -fno-fast-math.

## Single existing qualification path / 复用原有质量门禁

The existing Quality/frontend-reference job performs Python --self-test, --collect and --verify for tests/validation/frontend_evolution/fe09_b1a_ingress_qualification.py. Existing Docs/Verify runs only the offline --self-test. A single 30-day metadata-only Artifact stores exactly receipt.json, collect.log, verify.log, SHA256SUMS; source and binary SHA256, true execution checkout SHA, fixed result fingerprints, negative controls and explicit nonclaims. No binary, source recordings, raw test PCM, training model, third-party DSP, paid resource, new workflow or duplicated 531 MB spatial artifact is uploaded. The script reuses the existing first-party R2A safe subprocess/JSON/source-check helpers; it does not implement another signal-processing algorithm or scorer.

**Positive decision (only after independent checks):** FE09_R2B1A_SEPARATE_CAPTURE_RENDER_INGRESS_RESEARCH_ONLY_NO_RELEASE.

**Failure (never relabel):** FE09_R2B1A_CHANNEL_OR_EPOCH_NOT_ADMITTED.

The implementation must be checked at exact latest PR HEAD with full Verify required summary=success, strict active main Ruleset 21804005 squash-only and no unresolved review threads, expected-head protected squash and **distinct** new-main full Verify + same SHA Release. A second fresh-main metadata-only Artifact must be independently read back and rehashed before closing #735.

## Explicit nonclaims / 不得声明

**No actual SRC/rate conversion, no active beamformer/DOA, no AEC/render-to-DSP hookup, no full duplex or real acoustic gain, no physical ADC sample-zero calibration, no SSC305 CPU/p99/thermal/power/HIL, no full C4 192 KiB application budget, no 3.x public SDK, no E001, no shipping or commercial redistribution.** R2A remains the sole existing first-party FIR33 BF research kernel; B1-A creates none. Future B1-B must be separately preregistered to reuse/refactor that same kernel alongside a qualified N-capture plus separate render actual multirate SRC. Later B2 Linux runtime/Flight Recorder, B3 BF/AEC pairing and B4/R2C physical qualification remain blocked. Historical original RealMAN D1/S3/S5 negative results and unqualified ADC source timing stay immutable.
