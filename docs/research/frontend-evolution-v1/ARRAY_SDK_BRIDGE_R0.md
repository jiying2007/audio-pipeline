# FE09-R0 — C2/C4 research array → existing mono SDK bridge / 研究阵列到既有单声道 SDK

## Why this is a research bridge / 边界

Independently preregistered [#726](https://github.com/jiying2007/audio-pipeline/issues/726). Prerequisite [#725](https://github.com/jiying2007/audio-pipeline/pull/725) was protected-squash merged to main \`9a0e2b2bcca71946661296e086ab2c9881ca7ba3\`, and *distinct new-main* Verify \`38190138751\` / Release \`38192095566\` both completed with success and matching exact SHA before implementing R0.

This proves **only** a software composition seam. The **installed 2.x C API is still one/two mic**, and the shipping beamformer still accepts mic0 and mic1. Do not set \`AP_BUILD_MAX_MIC_CHANNELS=4\`, change \`AP_MAX_MIC_CHANNELS\`, patch installed headers, change default DSP, expose 4-mic captures through the existing Linux runtime or call this a 3.x API. Public C4 design, measured real capture geometry/calibration, effectiveness, SSC305/BSP hardware and E001 qualification remain independent future gates.

The first-party, noninstalled \`array_native.[ch]\` implements caller-owned 1/2/4-channel FIR33 processing; this is followed by a **separate explicit float→mono S16 conversion** and a newly initialized **real existing 2.x** \`ap_pipeline_t\` with \`mic_channels=1\` and \`AP_STAGE_BF\` disabled. Only actual compiled downstream processing is exercised, not a mock output. Render reference is a mono channel and never part of the mic count. Runtime queue and Flight Recorder stay untouched.

## Frozen inputs, geometry and functional controls

Exact first-party synthetic input at 16 kHz, 160 sample frames / 10 ms, 100 frames, repeated after explicit reset on the same underlying allocation. A fixed capture-gap event at **frame 50** triggers both \`fe_array_reset\` and \`ap_pipeline_notify_stream_discontinuity(AP_DISCONTINUITY_CAPTURE_GAP,1)\` at one processing boundary. The latter resets downstream temporal processing but **does not reset cumulative \`processed_frames\`**; the test asserts 100 accepted frames per replay, not a fabricated file clock.

| Research geometry | Physical slots | FIR33 common history delay |
|---|---|---:|
| C2 ULA | (0,0,0), (35mm,0,0) | 19 samples |
| C4 ULA | 0/35/70/105 mm along X | 22 samples |
| C4 UCA | cardinal XY ring radius 35 mm, ref +X | 21 samples |

All fixed direction \`(0,1,0)\`, gain=1, explicit input-channel permutation, latency correction=0, full active mask. R0 geometries **do not share a common aperture**; no effectiveness ranking is allowed. Causal per-geometry history delay is not complete audio I/O/system/AEC latency.

For each case, the actual harness:
- Builds the unmodified public v2.x library using the repository CMake project; rejects any build reporting public \`max_mic_channels !=2\`, fast-math or absent pipeline capability.
- Links that library with research-only array C code in a private test binary, uses the real mono capture and render-reference C functions, and compares repeat input, mono-bridge and final SDK fingerprints **bit for bit within a single build**.
- Rejects 4-mic public 2.x configuration, a BF-enabled single-mic public config, 3-mic research input, duplicate physical slot, undersized state, missing/bad sample-count, oversized 10ms frame, NaN, out-of-range signal and aliased buffer; also rejects an incorrect public SDK frame size. All negatives are before first valid process and must leave state sample count unchanged.
- Independently records array state bytes, returned mono pipeline state bytes, 10ms capture/mono frame sizes, fixed array delay, number of clipping samples, source/bridge/output hashes and three-run build identities. A separate hosted thread-CPU measurement is **descriptive** and not required to match bitwise across executions.

No RealMAN RAR, FLAC, PCM, source label CSV, video, third-party DSP binaries, paid service or speech scoring. The fixture is deterministic, disclosed, source-code-generated test signal, **not** blind evaluation or real-mic validation.

## Implementation / 运行

The only new C source is \`tests/validation/frontend_evolution/array_sdk_bridge_r0.c\` and the stdlib-only qualifying runner is \`array_sdk_bridge_r0.py\`. Native GCC/CMake available in the existing verified CI environment build a true public library, then link a dedicated noninstalled research test. No new production CMake target, published library, ABI or SDK artifact.

\`\`\`sh
python3 tests/validation/frontend_evolution/array_sdk_bridge_r0.py --self-test
python3 tests/validation/frontend_evolution/array_sdk_bridge_r0.py \
  --collect --output fe09-bridge --execution-source "$(git rev-parse HEAD)"
python3 tests/validation/frontend_evolution/array_sdk_bridge_r0.py \
  --verify --output fe09-bridge --execution-source "$(git rev-parse HEAD)"
\`\`\`

Existing \`Quality / frontend-reference\` is the single hosted gate. Artifact retains exactly \`receipt.json\`, \`collect.log\`, \`verify.log\`, \`SHA256SUMS\` for 30 days; independent SHA256SUMS verification and frozen decision guards are required. The compiled/linked binary and all synthetic PCM buffers remain ephemeral and are not redistributed. Do not upload duplicate 531MB spatial evidence.

Two outcome states are allowed: \`FE09_R0_C2_C4_MONO_SDK_BRIDGE_RESEARCH_ONLY_NO_PROMOTION\` or \`FE09_R0_INTEGRATION_OR_ABI_GATE_FAILED\`. Negative/failed runs are never reclassified as success by changing scoring, data, old constraints or product APIs.

## Exit and future work / 终态

R0 **cannot** certify a four-microphone public SDK, a 3.x version, perceptual BF gain, four-mic DOA, accurate RealMAN sample-zero, audio-video timestamps, real motor/noise/acoustic behavior, full duplex AEC performance or SSC305 p95/p99/RSS/thermal/power. FE08 prior 3,704-byte C4 FIR33 state is one component, not full C4 memory. The 192KiB C4 research budget remains unqualified.

Merge only after actual latest-head full Verify required summary, retained original CI job evidence, zero unresolved reviews, active strict squash-only Ruleset 21804005 and protected expected-head squash; then require a **separate exact-main** Verify, Release and evidence check before closing #726. The next *separate* phase must select a public C4 ABI design and fully measure microphone capture mapping, latency, runtime queues, multi-mic AEC, actual acoustic improvement and device performance before any product promotion. Preserve failed original FE03 D1/S3/S5 lineages and frozen I025–I040.
