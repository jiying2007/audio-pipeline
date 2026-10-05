# FE03 controlled live beam steering / 连续音频上的受控波束切换

Base: `327b0e67572df5629a302dca3b474d2ce110aecf` (native array #660).
Preregistration: #657 comment 5988936077.
Contract: `.github/research/frontend-evolution-v1/array-steering-v1.json`.
This extends the same first-party C research core; no installed SDK, production
preset, version, old acoustic policy or physical E001 qualification is changed.

## Why this step

The original array must be reinitialized to change its direction. Reinitializing
also clears history. This implementation changes direction on continuous input,
without introducing a second runtime or a cold target history. It separates the
DSP transition mechanism from an optional control policy. Neither estimates DOA.
Independent recorded speech, spatial noise/room studies and joint BF/AEC recovery
remain separate unfinished work. Analytic correctness is not a speech-quality gain.

## Shared-history transition

`fe_array_request_steer(array, direction, T)` is caller-serialized before a process
call. It validates a finite unit vector and T in [2, sample_rate/10] samples. There
is no implicit normalization, queue, clipping, resampling or additional lookahead.
Per-direction delays must fit the existing ring; an unsupported direction rejects
atomically, even when the original initialized direction fitted that geometry.

The old and target tap banks read the SAME per-microphone histories and use the
same geometric common delay L defined in ARRAY_NATIVE.md. At transition sample k:

```
alpha = k / (T - 1)
y[k] = (1-alpha)*old_beam[k] + alpha*target_beam[k]
```

The first sample is evaluated as the old beam exactly; the last as the target beam
exactly. After the last sample, the target bank is committed. Intermediate output
is a convex blend of two beams, NOT a claim that an angle rotates uniformly.
This bounds the coefficient-envelope change; it cannot guarantee absence of all
clicks, destructive cancellation, target attenuation or modulation on arbitrary
signals. The effective echo path can still change. AEC recovery must be measured
separately; no AEC-reset behavior is changed here.

An idle same-direction request is a no-op. Any otherwise valid request while a
transition is active returns EBUSY without mutation. Invalid controls and invalid
processing blocks do not consume transition samples. No pending target is queued.
`get_info` reports last committed/target direction, progress and accepted/completed/
cancelled counts. Compensation values refer to the last committed bank.

Actual active-mask changes cancel the transition, keep the committed bank and
apply the original masked-history clearing semantics. Same-mask calls do nothing.
Reset cancels a transition, keeps the last committed direction, clears histories
and all sample/steering counters. Fault cancellation/reset is intentionally NOT a
crossfade guarantee. Reset the observation controller with the array lifecycle.
No automatic microphone-fault detector is added.

The core uses one history and one extra tap bank. State size is queried via the
existing caller-memory API and remains below the original 4096-byte core budget.
Source-level no-allocation/no-lock rules apply to processing and control. Temporary
initialization/control stack is not counted as persistent state or total process
memory. A 20ms transition is a coefficient-change duration, not 20ms extra latency.

## Optional fixed research controller

`array_direction_control.c/.h` consumes caller-supplied direction, confidence,
near-speech and render-active flags. These are uncalibrated external observations,
not inferred ground truth. For this finite engineering experiment:

- confidence >=0.8, near_speech=1 and render_active=0;
- three directions coherent within 5 degrees of the FIRST observation, over at
  least 20ms; observation gap <=20ms; change >=15 degrees from committed beam;
- observation age <=20ms in the array's audio sample-frame clock;
- 20ms crossfade and 200ms cooldown after a request is accepted.

Valid but gated observations clear stability; there is no hidden queue or future
reselection. Stale, future, duplicate and malformed observations reject atomically.
A backwards audio clock requires explicit controller reset. The caller must reset
both objects on array reset/reinitialization; pointer reuse is not an epoch signal.
The controller is not thread-safe or a real-time scheduler. The caller must supply
observations at explicit processing boundaries on the same sample-frame clock.
Do not count interleaved scalar values or wall-clock milliseconds as sample indices.

During render playback this research policy holds direction even if near speech
is asserted. This conservative rule has NOT been qualified for barge-in or moving
double-talk. Its constants were fixed before measurement, not calibrated on D0 or
any public/independent/blind speech dataset. Deployment policy requires new evidence.

## Offline runner and evidence

The existing static invocation is unchanged. Optional arguments are:

```
array-runner GEOMETRY INPUT.s16le OUTPUT.f32le INFO.json COMMANDS [MAX_CHUNK_SAMPLES]
```

A command file contains `FE_STEERING_V1 COUNT`, then COUNT rows of
`sample_index duration_samples ux uy uz`. Indices are strictly increasing uint32
sample-frame positions, below the input length. At most 64 commands are accepted.
The runner splits a 10ms transport block at the exact command sample, including
non-frame-aligned positions. Invalid/overlapping controls make the run fail;
partial output files are NOT success evidence. Existing files are never overwritten.
The optional chunk limit is 1..480 samples (bounded again by the transport hop).

The existing Quality/Verify array job builds the core, controller and C tests on
native, ASan/UBSan and actual AArch32/QEMU. It retains the original 60 static cases
per architecture and adds 48 transition cases per architecture: four geometries,
two input patterns, two interpolators and durations 2/320/1600 samples. Commands
occur at samples 517 and 2401 in a 4800-sample input. Every case has repeat, 7-sample
chunk and different-future runs, with a common-prefix boundary inside a long fade.

The independent oracle uses generic polynomial-basis interpolation, evaluates all
three static banks on the entire input, and blends according to the fixed schedule.
The 2e-6 absolute numerical bound remains a research engineering check, never an
existing acoustic threshold relaxation. C tests also exercise five sample rates,
120 transition configurations, exact endpoints, reset/mask/busy/invalid controls,
controller timing/coherence/confidence gates and repeated lifecycle stress.

Evidence remains in the ONE existing `frontend-array` artifact with source,
compiler/build/binary identities, both experiment contracts, PCM, schedules,
metadata, metrics and unit logs. The array result schema is version 2; historical
version-1 artifacts remain historical and are not admitted through a fallback.
The verifier regenerates fixtures and recomputes transitions; re-sealed semantic
negatives include missing steering cases, fake DOA/AEC claims and command/output
corruption. No workflow or independent acoustic evaluator is created.

## 中文结论边界

本轮增加的是实际 C 处理上的连续波束切换和受控方向接纳。它不重新创建
音频处理器，不清空目标波束所需的共享历史，也不会暗中排队接受后续目标。
置信度、语音和播放标记仍由外部提供；测试中的标记是明确的工程输入，
不能称为真实 DOA、VAD 或双讲检测结果。

固定策略阈值未经过独立真实语音校准。平滑混合两个波束仍可能造成局部
相消和等效回声路径变化，不得写成“无损转向”或“AEC 已恢复”。旧 2.x
SDK 仍不包含此研究核心。独立语音空间评估、固定 FIR/多波束、DOA 估计、
BF/AEC 联合效果、自动坏麦、其他外部实现和最终 C2/C4 交付继续在 #657。
