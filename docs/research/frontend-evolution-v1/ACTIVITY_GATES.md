# FE04 measured Activity gates / 真实双讲门控对照

Base `7e8646fc95c22084e6eca58f789f40cf74e5f9ec` (#665).
Preregistration: #657 comment 6006333134, before implementation or new scores.
Contract: `.github/research/frontend-evolution-v1/activity-gates-v1.json`.

## Single changed cause

The same public Activity module is used with the pipeline's existing constants:
far threshold 1e-7f, double-talk ratio 1.5f, hangover 3. Float32 energy accumulation
starts at 1e-12f, traverses 160 actual post-BF mixed and synchronous render samples,
and divides by 160. No threshold, source, AEC, BF, synchronization or recovery
policy is tuned. One common pre-AEC observation supplies BOTH topology arms; this
is NOT a per-microphone detector topology or the full installed pipeline.

The existing `bf_aec_order_runner.c` keeps its default AEC-only behavior. A build
with ACTIVITY adds two explicit opt-in modes:

```
--monitor-activity TRACE.csv    observe detector; still use supplied oracle gates
--measured-activity TRACE.csv   use the observed detector flags for every AEC
```

A build without the module rejects both requests, never silently falls back to
oracle flags. Monitor output must match the default oracle output byte for byte.
The trace contains frame index, mixed/reference energies, supplied oracle labels,
detected far/double flags and ACTUAL used flags. Trace I/O and test allocation are
offline instrumentation, not new work in the production callback. Both modes use
identical observations and detector state; AEC output never feeds the detector.

## Data and metric authority

All 36 previously disclosed development scenes of #665 are reused with their
unchanged admitted speech, phase ramps, synthetic channel echo taps, events,
geometries and fixed FIR33/diffuse-1.0 banks. No fresh holdout or real room data is
claimed. Source loops are not new independent recordings. The original sealed
order evidence is retained as a sibling and hash-bound; it is not modified.

Measured gates may admit adaptation during near speech. Consequently mixed and
echo-only shadow filters may diverge even under the same flags. The runner's old
shadow columns and algebra diagnostics remain instrumentation only. This new
measurement does NOT subtract shadows or claim isolated clean near/echo output.
Far-only residuals use the ACTUAL mixed output, only after near/BF tails drain:
100 ms windows 21..59 and 101..139. Other windows have null ERLE interpretation.
Near/double-talk canonical SI-SDR uses the same BF-only target, not dry speech;
it cannot certify absence of BF coloration. Recovery keeps the old 5–6s baseline,
3dB margin and three-window criterion. Both first-window start and confirming
third-window end are reported; unrecovered stays null. Event time includes any
adaptation-free intervals and is not pure AEC convergence latency.

Gate counts in fixed phase-interior spans indicate admission during scheduled
double talk or missed admission during scheduled far-only. These labels describe
the stimulus schedule, not whether a human actually phonated in every frame.
False-gate counts are not KWS false alarms/hour or product DTD error rates.

## Executable checks and finite scope

Native, ASan/UBSan and AArch32/QEMU builds run actual adapting, zero-render/steering,
repeat, different-future, overwrite, invalid-mode and missing-module controls.
A separate binary32 scalar reference replays the unchanged Activity recurrence
from logged energies. Reference energy is reconstructed exactly from PCM. Mixed
energy is bounded against the sum of separately rounded BF target/echo components
(2e-8 absolute); that sum is NOT falsely declared bitwise the mixed accumulator.
The DSP output itself is neither normalized nor limited.

The new receipt binds exact revision, baseline manifest, sources, generated build
identity, library, executable, trace, counts and metrics. Negative tests mutate
semantics and reseal checksums; originals remain intact. Existing Quality spatial
job and artifact are reused. The old oracle suite remains mandatory. No new
workflow, production algorithm, installed API, SDK/version or E001 identity.

```
python3 tests/validation/frontend_evolution/activity_gates.py --self-test
python3 tests/validation/frontend_evolution/activity_gates.py \
  --base-evidence fe-spatial/order --output fe-spatial/activity \
  --execution-source "$GITHUB_SHA"
python3 tests/validation/frontend_evolution/activity_gates.py \
  --base-evidence fe-spatial/order --output fe-spatial/activity \
  --execution-source "$GITHUB_SHA" --verify
python3 tests/validation/frontend_evolution/activity_gates.py \
  --base-evidence fe-spatial/order --output fe-spatial/activity \
  --execution-source "$GITHUB_SHA" --negative-evidence
```

`ACTIVITY_GATES_DIAGNOSTIC_NO_PROMOTION` is fixed irrespective of scores. A missing
case, invalid build, unexpected future access or broken evidence fails engineering
qualification. An unfavorable acoustic result remains a result, not a reason to
relax thresholds. Full FE04 and #657 remain open.

## 中文边界

本批把预设门控与既有真实 Activity 模块分别接入相同 AEC/BF 对照，参数不变。
monitor 模式只记录，必须逐字节保留原预设门控输出；measured 模式才改变实际门控。
门控轨迹包含实际使用标记，不能只记录检测器输出却让 AEC 继续使用 oracle。

真实门控可能在近端说话时继续适应，此时影子滤波器不再提供合法的干净语音分解。
远端单讲评价实际混合输出，双讲只使用相同 BF 目标的完整输出指标；未恢复保留空值。
此处计划时段不是逐帧人工语音标签，不能把门控计数直接称为产品 DTD 准确率。

本批开始时会话本地执行环境无法连接。未实际完成的本地编译、下载校验与独立重算
不得写成通过；远端执行证据、代码审查与本地证据必须分开陈述。完整四麦 SDK、
真实同步/残余回声/机器人环境和端侧 CPU/p99/温升仍需后续资格验证。
