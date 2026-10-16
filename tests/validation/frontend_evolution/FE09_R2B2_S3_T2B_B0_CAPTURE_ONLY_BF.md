# FE09 B2-S3 T2-B/B0 — Capture-only first-party BF equivalence
# 缺失 Render 时独立 Capture SRC+FIR33 前进：软件模型资格认证

**Prerecorded research protocol:** [T2-B #771](https://github.com/jiying2007/audio-pipeline/issues/771). B0 does **NOT** close T2 #766 or claim end-to-end reference/recorder liveness. Frozen predecessor: T2-A protected main `46a29d288f4b58a940400e1f0a50195863631d18`, [Verify 38871738147](https://github.com/jiying2007/audio-pipeline/actions/runs/38871738147) 67 success/1 expected skip, [Release 38876039158](https://github.com/jiying2007/audio-pipeline/actions/runs/38876039158) release+convergence both success and independently rehashed [4-member Artifact 12033612802](https://github.com/jiying2007/audio-pipeline/actions/runs/38871738147/artifacts/12033612802), ZIP SHA256 `78e20d6876012b1439d0551b9b87124c57b6b66d7e7db645cb80eeb28367f459`. T2-A #769 CLOSED completed.

## Why a genuinely independent capture BF core is needed

Frozen S1 `fe_b2s1_process_one` only advances when Capture and Render tails match. Frozen B1B1 `fe_b1b1_process` with `render_channels=1` also requires an actual reference frame. Therefore neither API can be told that missing Render is implicitly zero; an S1 queue-drop trick cannot preserve missing mic state.

The noninstalled B0 adapter owns a **separately initialized** original B1B1/FIR33 instance configured `render_channels=0`, and a **distinct** `ap_resampler_state_t` for optional actual reference samples. Only original `fe_b1b1_process` and `ap_resample_input_channel` execute DSP. No rewritten resampler, cloned beamformer, frame-stuffing or source timebase assertion. Capture sequences must be exactly contiguous from 1; any unknown Capture gap fails closed until an independently qualified reset. Actual Render is ingested **only on explicit delivery**, may be absent for many Capture frames and may resume after an explicit `RENDER_GAP`; its independent epoch/history does not reset mic SRC/FIR33. No Render processing call is made on absent frames.

For each scene, a **separate synthetic, paired-first-party B1B1 control** is fed the same captured PCM and a *counterfactual* synthetic reference even when Render is absent in the DUT. That counterfactual exists solely to detect whether the original mic BF calculation accidentally depends on its own Render history; **it is NOT source-attested real Render and must never appear as an actual device reference or APX3 record**. The asserted property is bitwise equal mic BF output / mic-source hashes and array sample histories **inside one platform** across the same real synthetic Capture history. Cross-ISA raw Float32 hashes are diagnostic, not a release criterion.

## Executed test matrix and explicitly limited meaning

The independent C fixture executes 4 array geometries (C1, C2-ULA, C4-ULA, C4-UCA) × 3 rates (16/32/48 kHz) × 4 genuinely different present/missing/gapped/ahead reference schedules, **48 BF scenarios**, each with **48 actually accepted 10ms Capture frames**. It also exercises actual identical mask change and steering transition on the two mic BF cores. This is not 48 SPSC queue configurations: B0 has **no queue depth** and no worker thread, so a duplicated "depth2/depth4" field is prohibited.

Invalid Capture seq/count/beam output/work alias, duplicated or false-gap Render, invalid clock-reset flags, stale Render and improper history changes are rejected with full Capture BF/output and independent reference-source history snapshots. The test requires >9000 actual exercised negative calls, deterministic control-only integer digests and per-target mic Float32 hashes. A positive is **real first-party continuous Capture BF output during Render absence**; neither B0 nor the counterfactual oracle is an end-to-end recorder, physical latency or 4-mic acoustic improvement proof.

Native, ASan+UBSan, ARM32/QEMU and Native TSan must **compile/run actual modified C twice**, source-pin unchanged B1B0/B1B1/S1/S2/T0/T1/T2A and original public shipping paths, hash binaries and toolchain IDs, and independently upload/download/re-hash a four-member 30-day Artifact (`SHA256SUMS`, `receipt.json`, `collect.log`, `verify.log`). A successful B0 sanitizer build is **not** a threaded race-liveness demonstration; true producer/consumer interleavings belong to B1.

```sh
python3 tests/validation/frontend_evolution/fe09_b2s3_t2b_b0_capture_only_qualification.py --self-test
python3 tests/validation/frontend_evolution/fe09_b2s3_t2b_b0_capture_only_qualification.py \
  --collect --output fe09-t2b-b0 --execution-source "$(git rev-parse HEAD)"
python3 tests/validation/frontend_evolution/fe09_b2s3_t2b_b0_capture_only_qualification.py \
  --verify --output fe09-t2b-b0 --execution-source "$(git rev-parse HEAD)"
```

**Admissible B0 decision only after all actual protected gates:**
`FE09_S3_T2B_B0_CAPTURE_ONLY_BF_EQUIVALENCE_NO_QUEUE_OR_RECORDER`.

**Fail-closed:**
`FE09_S3_T2B_B0_CAPTURE_BF_NOT_ADMITTED`.

## B1 and product boundary

B1 remains separately blocked until B0 protected PR-head Verify, expected-HEAD squash, distinct main Verify, same-SHA Release/convergence, fresh main Artifact, and a separate preregistration. B1 must add actual exclusive source-attested producer/worker queues, real optional-reference source epochs, independent capture-only vs paired **original S2 APX3 chunks**, externally hashed ordered manifest and finite transactional recorder policy. Frozen APX3 header `render_channels` fixes each file's frame layout: **do not invent in-file per-frame optional Render, fake reference PCM or an unqualified shared clock.**

No 2.x shipping `src/`, public `include/`, CMake, APD2/v1 tools, immutable I025-I040, release tags or public SDK 3.x are modified. No measured ADC/DAC timebase, full-duplex AEC, true SSC305 10ms p99/192KiB/thermal/power, real C4 WNG/DOA/SI-SDR gain, HIL/E001 or product certification #58 is claimed. T2 #766, B1 #771, T3 #767, S3 #762 remain OPEN.
