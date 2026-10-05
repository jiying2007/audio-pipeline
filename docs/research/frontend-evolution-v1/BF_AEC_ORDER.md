# FE04 BF/AEC order / 波束形成与回声消除顺序对照

Base: `0f295058466cd8d8355b9261a2d2ca44c8d717b9` (#664).
Preregistration: #657 comment 6001772668. Frozen contract:
`.github/research/frontend-evolution-v1/bf-aec-order-v1.json`.

## What actually executes

The offline C probe composes the existing public `ap_module_aec_*` module and
unchanged FE array in both orders:

```
raw microphones -> BF -> one linear AEC
raw microphones -> independent linear AEC per microphone -> BF
```

AEC remains MDF/SCALAR, 16 kHz, 160-sample calls, 64 ms tail, mu=0.2 and configured
adaptation stride=1. Its existing steady update policy remains active. The normal
CMake build is used, pipeline OFF and AEC only, with exact generated build identity.
This does not increase the installed high-level pipeline's maximum microphone
count; four mono module instances are composed by a research-only runner.

Reference synchronization and far/double-talk flags are supplied exactly by the
fixture. This isolates order from estimator errors; it does NOT qualify SYNC,
actual DTD, RES/NS/AGC, automatic DOA, barge-in or product full-duplex performance.
No new DSP algorithm, production source change, parameter search or SDK promotion.
The full FE04 work package remains open.

## Data and frozen matrix

The first two previously disclosed #664 development pairs (1673/1919,1988/1993)
are reused as `DISCLOSED_DEVELOPMENT_DIAGNOSTIC_NOT_HOLDOUT`. Exact source/crop
identities and original notices stay attached. The four-second real English
recordings are looped with 160-sample endpoint/phase ramps and fixed input scale
0.15 into 16 seconds. Loops are NOT additional independent recordings.

The existing 63-tap offline free-field renderer supplies near-source geometry;
its future access is synthetic stimulus generation, not deployable DSP lookahead.
Echo paths are synthetic short linear channel-specific taps, not measured RIRs.
Their complete coefficients fit within the fixed AEC tail and are preregistered.

| Time | Source phase |
|---|---|
| 0–2 s | Near only, initially cold |
| 2–6 s | Far only, adaptation |
| 6–10 s | Double talk, oracle freezes adaptation |
| 10–14 s | Far only, recovery |
| 14–16 s | Near only after playback |

A four-frame guard protects near/BF history at boundaries and marks far activity
while the short echo tail drains. Flags are supplied controls, not classifier
predictions. Two pairs × three equal-70mm geometries (dual/ULA4/UCA4) × two frozen
banks (FIR33/diffuse-load1.0) × three events = 36 scenes, each run in both orders.
The events are no change, a 0°→60° bank change at 8 s over 20 ms, or a synthetic
echo-path change at 8 s without changing BF. No simultaneous-event sweep. Near
speech remains at 0°: this is a commanded path perturbation, NOT a moving-talker
tracking test. No path-reset hint is sent to either AEC order.

## Shadows, timing and measurements

Each mixed-input order has an echo-only shadow with the SAME oracle adaptation
gates. Mutable AEC/BF state is not shared. Near speech is absent whenever adaptation
is permitted. This permits a controlled near-additivity check; do NOT extend it to
arbitrary adaptive filters, missed double talk or independently retrained shadows.

Six interleaved Float32 output columns are retained:

```
BF(near), BF(echo), BF->AEC(mixed), BF->AEC(echo shadow),
AEC->BF(mixed), AEC->BF(echo shadow)
```

The same bank command/sample is sent to all relevant BF instances. BF-only
references check linearity/commutation. Real zero-render execution verifies exact
pass-through. Additional actually adapting AEC controls check repeated bytes,
equal-prefix/different-future behavior and overwrite rejection on each architecture.
Output is not normalized or clipped; out-of-range values are counted. A per-mic
AEC residual outside the BF's declared input envelope fails, instead of silently
adding a limiter to only one order.

Canonical `si_sdr_span` compares the same-time BF-only target and actual output.
This measures **additional AEC error relative to that BF target**, not dry-speech
quality or absence of BF coloration. The evaluator's numeric/null behavior is
unchanged; engineering additivity is reported separately, with a predeclared
5e-6 absolute bound. No shipping acoustic or bitwise threshold is relaxed.

100 ms windows retain known BF-echo energy and shadow residual energy. Ratios are
interpretable only with valid echo energy. Double-talk SHADOW ratios are diagnostic,
not conventional mixed-signal ERLE. Recovery uses only predefined far-only windows:
last pre-double-talk baseline at 5–6 s; search 10.1–14 s for three consecutive valid
windows within 3 dB of that baseline. Recovery time is relative to the 8 s event
and INCLUDES the frozen-adaptation interval. No recovery before 10.1 s is inferred.
Unrecovered or invalid stays null. The no-event arm uses the same nominal 8 s
reference clock as a counterfactual, not a claim that it suffered an actual event.
Natural excitation varies: compare event and no-event counterparts, not only a
threshold crossing or a large single ERLE number.

## Resources and reproducibility

The proposed post-BF topology state is one BF plus one AEC; pre-BF is one BF plus
N AECs. Shadows and extra references are test instrumentation and not included in
those proposed state totals; the actual test process uses more memory. Full
pipeline/runtime, stack, I/O, other modules and platform dependencies are excluded.
Host elapsed cost includes both topologies and instrumentation, NOT isolated
algorithm throughput, SSC305 CPU/p99, target thermal/power or real-time deadlines.

The existing Quality spatial job reuses admitted data, builds native/sanitized/Arm
engineering executables and runs recorded-speech cases natively. Arm/QEMU functional
controls are not Arm speech timing. No new workflow or parallel evaluator. Original
source/build headers/library/binary, inputs, outputs, repeated-output hashes,
per-window metrics and checksum manifests are retained. Duplicate speech output
files are removed only after direct byte equality and digest recording; this is
not a second independently archived PCM copy. Future verification can rerun the
actual binary. Original evidence is never edited by the re-sealed negative suite.

```sh
python3 tests/validation/frontend_evolution/bf_aec_order.py --self-test
python3 tests/validation/frontend_evolution/bf_aec_order.py \
  --source /path/to/admitted-spatial-data --output /tmp/fe-order \
  --execution-source "$(git rev-parse HEAD)" --require-arm
python3 tests/validation/frontend_evolution/bf_aec_order.py \
  --output /tmp/fe-order --execution-source "$(git rev-parse HEAD)" --verify --require-arm
python3 tests/validation/frontend_evolution/bf_aec_order.py \
  --output /tmp/fe-order --execution-source "$(git rev-parse HEAD)" --negative-evidence
```

`BF_AEC_ORDER_DIAGNOSTIC_NO_PROMOTION` is the frozen decision, irrespective of
scores. Actual SYNC/DTD interactions, nonlinear playback, real rooms, moving
double talk, RES/NS, KWS/ASR, vendor BSP and final C2/C4 qualification remain open.

## 中文交接

本批真正把既有 BF 与公开 AEC 模块接起来运行，比较前后顺序；完全同步参考与
预设双讲标记只用于隔离拓扑，不冒充实际 SYNC/DTD 或完整全双工已通过。旧录音
明确作为披露后的开发诊断，不能重新称作独立验证。

每麦 AEC 需要多份真实滤波状态；波束切换、回声路径变化、无事件对照分开报告。
双讲时冻结适应，恢复时间含冻结区间，未恢复就保留 null。目标参考是同配置的
BF-only 输出，用来区分 AEC 额外损伤，不代表该 BF 没有指向误差或频谱染色。

影子法只在本实验同门控条件下成立，不可外推到误判双讲等实际故障。安装版2.x、
产品默认、既有证据和 E001 身份不变；后续继续验证真实估计器和整链的交互。
