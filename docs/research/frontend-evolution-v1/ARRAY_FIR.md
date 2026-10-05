# FE03 fixed FIR comparison / 固定 FIR 结构对照

## Scope and hypothesis

Base: `f10aa3b8eae53fd0e56bb025f63cdd32e0669506` (#662).
Preregistration: #657 comment 5996299744; machine contract:
`.github/research/frontend-evolution-v1/array-fir-v1.json`.

The recorded-speech diagnostic exposed limited spatial SIR benefit and target
transfer loss. This experiment tests whether **17/33-tap Hann-windowed-sinc
fractional delays** preserve target transfer better than four-tap Lagrange,
without assuming that flatter delays yield stronger spatial separation. Exactly
two structures are retained: no angle/window/weight/SNR/threshold sweep.

This extends the SAME first-party research C core and its shared-history steering.
It is not a SOF/Athena port, a superdirective or adaptive MVDR beamformer, a DOA
estimator, BF/AEC qualification, or an installed C4 SDK. No external implementation,
coefficients, data or model is copied into the product library.

Mathematical reference: Julius O. Smith, *Physical Audio Signal Processing*,
[windowed-sinc interpolation](https://www.dsprelated.com/freebooks/pasp/Windowed_Sinc_Interpolation.html).
SOF's offline-design/online-filter-sum approach remains an architectural reference,
not a claim of reproducing its spatial filter design.

## Exact kernel and time accounting

For radius R=8 or 16 and channel delay D, let m=floor(D), f=D-m. Offsets are
m-R .. m+R. For k=-R .. R:

```
raw[k] = sinc(k-f) * (0.5 + 0.5*cos(pi*k/R))
weight[k] = raw[k] / sum(raw)
D = old_geometric_common_delay + R + projected_arrival - calibration_latency
```

An exactly integer delay uses exactly one unit coefficient. This is **unit-DC
coefficient normalization**, not per-file/per-frame output normalization. Weights
are computed in init/control, not in the audio loop. Float32 output remains
unclipped. The full causal tap range must fit the 128-sample history; unsupported
geometry fails rather than clamps. Reset/steering/mask semantics remain as in
[ARRAY_STEERING.md](ARRAY_STEERING.md).

At 16kHz, FIR17/FIR33 add 8/16 samples (0.5/1ms) over the old geometric delay.
For the existing 70mm diagnostic array the complete delays are 13/21 samples,
versus 5 for cubic. This is core algorithmic delay, not total device latency.
The existing canonical metric evaluates the SAME target/reference span (60,795
samples), shifted by each declared delay. No best-lag search, extra zero padding,
output rescale, source reselection, or silent tail flush is allowed.

Neither finite FIR is an ideal all-pass delay. Actual C impulse probes retain
DC and 1/3/6/7/7.5/8kHz responses for fractional phases 0/.125/.5/.875. Passband
ripple, high-frequency attenuation, ringing and white-noise response tradeoffs
remain visible, even when a scalar speech metric improves.

## Allocation and workload

The legacy `fe_array_state_bytes(n)` continues to size **linear/cubic only**.
Use `fe_array_state_bytes_for_mode(n, mode)` for FIR. The original header/history
layout and allocations do not grow: FIR adds two per-channel coefficient banks
after the existing history; no extra PCM history or permanent parallel runtime.
The mode-aware init validates the larger required arena before mutation.

For four microphones the layout is 2,648 B (legacy), 3,192 B (FIR17), or 3,704 B
(FIR33). These exclude the direction controller, whole pipeline/runtime, stack,
I/O, diagnostics and process dependencies. The same 4,096 B research cap is used.
The existing invalid-enum test now uses 99, since values 2 and 3 are newly defined;
no invalid-input check is removed.

At four microphones/16kHz, the convolution term is 1.088 or 2.112 million multiply-
accumulates/second, doubled while blending two banks. Calibration, summing,
control, conversion and integration overhead are separate. The retained single-
pass native `clock()` benchmark includes the process call and a checksum; it is
**host process CPU, not DUT CPU/p99 or a calibrated cross-host speed comparison**.

## Engineering and disclosed speech evidence

The existing array qualifier additionally runs native/sanitized/AArch32 C tests,
mode-aware exact-memory/canary checks, integer delay, per-sample/block/reset
identity, busy rejection, mask/NaN protection and 8,192 stress frames/32 lifecycles.
Its new fixed matrix covers four geometries, two signals and two FIR structures,
static and shared-history steering. A tap-major double convolution oracle is
independent of the C ring loop; max absolute error must stay <=2e-6. Existing
linear/cubic known-answer and steering cases retain their original criteria.

The speech comparison runs all 36 previously admitted #662 mixtures with cubic,
FIR17 and FIR33: 108 mixed-arm rows plus isolated target/interference and repeats.
It reuses `speech_spatial.metrics` and the unchanged canonical `si_sdr_span`.
Cubic outputs must equal the original diagnostic run in that execution. Old
source roles are preserved as provenance, but BOTH groups are now explicitly
`DISCLOSED_DIAGNOSTIC_REUSE_NOT_INDEPENDENT_HOLDOUT` for this new comparison.
There is no candidate selection or promotion using the disclosed confirmation
speakers. Fresh, independent data is required for any later selection claim.

All results remain **FIXED_FIR_DIAGNOSTIC_NO_PROMOTION**, whether positive, negative
or mixed. SIR, target transfer/error, SI-SDR, output range, decomposition, per-case
metrics, compiler and source/config/binary identities are retained. Re-sealed
negative tests must reject missing cases/arms, false holdout labels, invented
real-array evidence, altered delays/scores and truncated PCM.

## Execute

The existing `array_qualification.py` now includes FIR engineering checks and
stores them inside its original `frontend-array` artifact. Existing Quality's
recorded-speech job generates its original `effects/` then adds `fir/` inside the
same `frontend-speech` artifact. No new workflow, dataset download, or repeated
source-audio archive is introduced for FIR.

```sh
python3 tests/validation/frontend_evolution/array_qualification.py --self-test
python3 tests/validation/frontend_evolution/array_qualification.py \
  --output /tmp/array --execution-source "$(git rev-parse HEAD)" --require-arm
python3 tests/validation/frontend_evolution/speech_fir.py --self-test
python3 tests/validation/frontend_evolution/speech_fir.py \
  --base-evidence /tmp/fe-speech/effects --output /tmp/fe-speech/fir \
  --execution-source "$(git rev-parse HEAD)"
python3 tests/validation/frontend_evolution/speech_fir.py \
  --base-evidence /tmp/fe-speech/effects --output /tmp/fe-speech/fir \
  --execution-source "$(git rev-parse HEAD)" --verify
python3 tests/validation/frontend_evolution/speech_fir.py \
  --base-evidence /tmp/fe-speech/effects --output /tmp/fe-speech/fir \
  --execution-source "$(git rev-parse HEAD)" --negative-evidence
```

Use a newly generated, source-matching `speech_spatial.py` effects receipt. Do not
splice a different compiled core into an old sealed source receipt. Historical
raw recordings may be reused only with their admitted source identity unchanged.

## 中文执行边界

本轮在同一研究核心内增加 17/33 抽头 FIR，并比较已有三阶插值。旧线性／三阶
的内存大小、公共延迟和输出不变；FIR 使用明确的模式内存查询，附加延迟单列。
有限 FIR 不是理想全通延时，更不是自适应 MVDR、多波束、自动 DOA 或正式四麦 SDK。

全部已披露录音只作结构诊断，原“确认组”不再作为新实验的独立留出集。结果不论
正负都完整保留，不用旧确认数据挑参数。后续固定空间滤波／多波束、真实房间与
独立语音、BF/AEC 联调及最终 C2/C4 交付仍由 #657 跟踪，产品默认与 E001 不变。
