# FE09 B2-S3 T2-A — Quiescent source-epoch restart (control only)
# 源拥有者受控停机与新纪元切换：明确**不保持**麦克风 BF 历史

**Independent preregistration:** [#769](https://github.com/jiying2007/audio-pipeline/issues/769). **Parent research:** [T2 #766](https://github.com/jiying2007/audio-pipeline/issues/766), S3 #762, R2 #733/#730. **Frozen predecessor:** `d911547091c792c4cded48283499361833674917`. Its distinct main Verify [38856220869](https://github.com/jiying2007/audio-pipeline/actions/runs/38856220869) and same-source Release [38858932544](https://github.com/jiying2007/audio-pipeline/actions/runs/38858932544) succeeded; [new-main F0 Artifact 12026963067](https://github.com/jiying2007/audio-pipeline/actions/runs/38856220869/artifacts/12026963067) was independently 4-member rehashed to ZIP SHA256 `d1432ac8b2e6472365057b281d705a837cc9c0ef5e851a7671cec802acacce61`.

## Architecture: no fake continuous BF history

Frozen S1 can consume only **paired** Capture/Render tails; F0 proves a purported stale Render behind *continuous* Capture is unreachable without a Capture source discontinuity. Therefore T2-A implements **Option A (conservative, nonseamless)** rather than pretending render-only retirement is an end-to-end repair.

- An **exclusive research control supervisor** publishes STOP with a source generation and enumerated reason. Producer and worker owners must finish in-flight calls, cease touching the old session and ACK from their actual threads. ACK is a *witness of the external stop protocol*, not an API that can magically suspend an arbitrary caller.
- After every required ACK, the supervisor validates an **independently initialized** distinct S1 queue, SRC/FIR33 BF core, S2 APX3 writer, S3 bridge and T1 source/PCM witness. Capture and optional Render logical IDs **increase**; the new sequence and source-local epochs start at 1 under the new identities. The old partial APX3 and all old queue/BF/witness storage remain immutable/quarantined.
- A checked receipt names old/new generations and source IDs, old queue counts and recorder commit count, stop reason, explicit `old_recorder_quarantined=1` and `mic_bf_history_preserved=0`. Success publishes the fresh pointer/generation before `RUNNING` with release memory ordering; stale generation requests cannot be accepted through this gate. Direct calls bypassing the gate are **outside** the qualified contract.
- There is **no in-place re-init, dummy Render, clock invention or partial APX3 masquerading as a completed archive**. Control is outside the 10ms callback; external owners re-launch explicitly after the cutover.

## Actual first-party executable qualification

`fe09_b2s3_t2a_controlled_restart_test.c` links unmodified first-party S1/S2/S3/T1, B1B-S1 SRC+FIR33 and deterministic C1/C2-ULA/C4-ULA/C4-UCA scenes. For **4 arrays × 3 rates (16/32/48k) × 2 Render settings × depth2/4 = 48 configurations**, actual pthread capture and optional render owner(s) and worker first process one real PCM pair, then exercise a mismatched or capture-invalid next frame. Producers finish, jointly acknowledge STOP; the supervisor checks immutable old S1/T1/BF/APX3 bytes and rejects stale/incomplete/aliased generations before admitting **new**, separately source-labeled real PCM. Two new accepted frames must equal first-party direct BF inside the same target and replay as exact private S2 APX3. At least 600 actual negative checks, not just JSON-labelled controls.

Native, ASan+UBSan, true native TSan and ARM32/QEMU must compile and execute the **modified C**, twice each, with frozen predecessor SHA256, per-binary hashes, full target equality for integer control verdicts (not cross-ISA Float32), and a strictly bounded four-member 30-day GitHub Artifact:
`SHA256SUMS`, `receipt.json`, `collect.log`, `verify.log`. Independent download/re-hash, run source and anti-promotion gates are required.

```bash
python3 tests/validation/frontend_evolution/fe09_b2s3_t2a_controlled_restart_qualification.py --self-test
python3 tests/validation/frontend_evolution/fe09_b2s3_t2a_controlled_restart_qualification.py --collect --output fe09-t2a --execution-source "$(git rev-parse HEAD)"
python3 tests/validation/frontend_evolution/fe09_b2s3_t2a_controlled_restart_qualification.py --verify --output fe09-t2a --execution-source "$(git rev-parse HEAD)"
```

Qualified ONLY after checks: `FE09_S3_T2A_NONSEAMLESS_RESTART_CONTROL_ONLY`. Fail closed: `FE09_S3_T2A_CONTROLLED_RESTART_NOT_ADMITTED`.

## Admission boundary

All 2.x shipping `src/`, installed `include/`, CMake, APD2/v1, immutable I025-I040 science baselines and tags stay untouched. **Do not close parent T2 #766**: Option B independent Capture BF advancement when Render is absent remains unimplemented and needs a distinct source/recorder contract. S3 #762, T3 #767 and HIL #58 also remain blocked. This is NOT a 3.x release, shipped runtime/ALSA stop design, real HIL, ADC/DAC drift measurement, full-duplex AEC, measured SSC305 CPU/stack/RSS/192KiB/10ms p99, thermal, power, physical C4 gain, or product certification.
