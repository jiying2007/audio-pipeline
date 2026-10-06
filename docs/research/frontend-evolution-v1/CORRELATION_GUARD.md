# FE04 lag-correlation adaptation guard / 双讲适应保护候选

Base: `acc0bbd50d38e766e59dbdb156ac30a03e215f78` (#666).
Preregistration: #657 comment 6007373828, before implementation or scores.
Contract: `.github/research/frontend-evolution-v1/correlation-guard-v1.json`.

## One bounded candidate

The existing Activity detector compares microphone and render energies. The #666
controlled diagnosis exposed admitted adaptation during scheduled near speech and
subsequent residual-echo degradation. This first-party candidate adds a waveform
consistency veto; it does not replace Activity, retune its constants or change AEC.

Compute demeaned squared normalized correlation between the most recent 320
post-BF microphone samples and render history for integer lags 0..1023. Only
fully observed history participates. Every fourth window sample contributes
(80 values); this is explicitly a statistical approximation, not audio resampling
or a claim of anti-alias filtering. All integer lags are searched. Accumulation
uses double precision and deterministic smallest-lag ties. The candidate has no
AEC output, oracle flag, clean component, phase schedule or future-input access.

Insufficient history/variance or score below 0.55 blocks adaptation while Activity
reports far speech. A blocked guard requires three consecutive scores >=0.65 to
release. Otherwise its state is held; far-inactive frames clear the veto but still
advance history. Applied DT is original Activity DT OR this veto. Thus inherited
false freezes remain, and the new guard can also mistakenly freeze diffuse,
nonlinear or low-correlation echoes. Correlated near speech may evade it. It is
NOT the matrix/vector NCC detector, FRLS, an echo-path estimator, or certified DTD.

General public research context (no source/weights copied):
- Gansler/Benesty, fast normalized cross-correlation DTD, Signal Processing 2006,
  DOI 10.1016/j.sigpro.2005.07.035.
- Iqbal/Grant, normalized cross-correlation echo-path-change detector, 2007,
  DOI 10.1109/TPSD.2007.4380390: over-sensitive DTD can obstruct path recovery.

## Same runner, explicit modes

Compile the existing `bf_aec_order_runner.c` with
`-DFE04_CORRELATION_GUARD=1` and the unchanged ACTIVITY/AEC public library.

- `--monitor-correlation TRACE.csv`: compute/log the guard; still use original
  measured Activity flags. PCM must match the exact-run #666 measured baseline.
- `--guard-correlation TRACE.csv`: apply the veto before both AEC topology arms.
  Also writes `TRACE.csv.observed.f32` (actual post-BF mixed/reference pairs).

Default oracle/Activity modes and builds without the guard stay unchanged.
An unavailable mode must fail, not fall back. Additional trace columns contain
score, lag, warmup and veto; old columns distinguish detected versus USED flags.
C candidate state is caller-owned and finite; malloc/trace files in the runner
are offline instrumentation, not a newly introduced production callback behavior.

## Measurements and evidence

All 36 previously disclosed development cases are retained. No speaker/room
independence is newly claimed, and no threshold sweep or mode selection occurs.
Reuse `activity_gates.measures`: actual far-only mixed residual and canonical
complete-output SI-SDR relative to the same BF target. No shadow subtraction.
Report both far-only admission loss and scheduled-double admission, every case,
absolute residuals and fixed own-baseline recovery/nulls. Schedule counts are not
natural DTD accuracy or KWS false alarms/hour. A weak baseline makes relative
recovery easier, so counts alone never establish an improvement.

Actual C controls cover multiple lags, polarity/gain, independent near noise,
DC/silence, release, reset and invalid-input state preservation. Native,
ASan/UBSan and AArch32/QEMU run the candidate and common-prefix/repeat controls.
A separate centered-vector Python formula checks selected score/lag observations;
this is a finite within-CI independent formulation, not an independent local audit.
Reference samples and the actual mixed observation are retained and checked.

One dependent job in the existing Quality workflow consumes the SAME run's sealed
spatial/Activity artifact and static libraries. It does not reacquire speech or
rerun upstream acoustic experiments. The existing job and new job each retain
15-minute limits. Only candidate evidence is uploaded; its upstream manifests
are hash-bound, so both artifacts are needed for a complete later replay. This
avoids duplicating the full upstream receipt but does not extend Actions retention.

```
python3 tests/validation/frontend_evolution/correlation_guard.py \
  --base-evidence fe-spatial --output fe-correlation --execution-source "$GITHUB_SHA"
python3 tests/validation/frontend_evolution/correlation_guard.py \
  --base-evidence fe-spatial --output fe-correlation --execution-source "$GITHUB_SHA" --verify
python3 tests/validation/frontend_evolution/correlation_guard.py \
  --base-evidence fe-spatial --output fe-correlation --execution-source "$GITHUB_SHA" --negative-evidence
```

The fixed decision is `LAG_CORRELATION_GUARD_DEVELOPMENT_NO_PROMOTION`, including
when a development score improves. New speaker/room/level tests and integrated
absolute recovery must independently confirm a useful candidate. Failure to
improve is preserved, not repaired by revisiting already observed results.
Host CPU covers the declared guard loop only, not AEC/BF or silicon performance.

## 中文实施边界

本批不降低旧双讲阈值，而是新增唯一的相关性保护候选。既有 Activity、BF、AEC
算法保持不变；相关性不足时只增加冻结，不能以“永远不更新”冒充效果改善。
同时保留远端单讲适应被阻止的代价、双讲输出与路径恢复失败。当前仍使用已披露
录音和合成回声，相关性不是已校准的语音概率，不能代替真实同步、非线性回声和
机器人环境验证。产品默认、2.x API、版本及 E001 身份均不改变，#657 保持开放。

本批开始时本地 container/Python 工具连接失败。未执行的本地编译、ZIP 重算、
试听与独立原始 PCM 复核不得写成通过；远端日志、实际执行结果和后续本地验证
分别记录。本文是冻结设计与运行说明，不是成功报告。
