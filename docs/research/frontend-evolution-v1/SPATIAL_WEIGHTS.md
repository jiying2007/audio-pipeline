# FE03 fixed spatial weights / 固定空间权重研究

## Scope, design and authority

Base: `2179e94a4f7f690c743024e386f3148836368267` (#663).
Preregistration: #657 comment 5998029964, before new data acquisition and scores.
Canonical finite contract: `.github/research/frontend-evolution-v1/spatial-weights-v1.json`.

This tranche changes the **joint spatial weights**, rather than only increasing
fractional-delay interpolation accuracy. It extends the same first-party C array
and existing Quality/Verify. It is not an installed C4 SDK, adaptive covariance
estimator, automatic DOA, simultaneous multibeam selector or SOF code port.
B0/v2.3.55, installed 2.x, historical outcomes and E001 remain unchanged.

`spatial_weights.py` uses the public fixed diffuse-field design equations:

```
sinc(x) = sin(x)/x, with sinc(0)=1
R_ij(f) = sinc(2*pi*f*distance_ij/343)
a_i(f) = exp(+j*omega*dot(position_i-reference,look)*fs/343)
z = inverse(R + load*I) * a
applied_filter_i = conjugate(z_i)/(conjugate(a)^T*z)
```

The source vector points from array to source. Exactly two diagonal loads, 0.1
and 1.0, are frozen. A 256-point transform, Hermitian endpoint handling, 16-sample
linear phase, 33 real taps and Hann truncation produce finite filters. One
aggregate DC coefficient normalization follows truncation; coefficients are then
rounded to Float32. This is **not output audio normalization**. No recording,
interferer direction, held-out result or covariance observation trains the bank.
The implementation is first-party; no upstream code, model or coefficient table
is copied. Mathematical reference:
https://thesofproject.github.io/latest/developer_guides/algorithms/tdfb/time_domain_fixed_beamformer.html

Truncation and aggregate DC scaling do NOT preserve the ideal MVDR distortionless
constraint at every frequency. `response.json` reports the **realized Float32
FIR** look transfer, WNG and diffuse-field DI at the declared frequency grid.
WNG describes modeled uncorrelated microphone noise amplification relative to
look response; DI assumes the modeled diffuse field, not measured robot noise.
Neither the grid extrema nor the ideal design proves continuous-band robustness.
A 1e-30 floor makes diagnostic logarithms finite, not an acoustic acceptance gate.
Target transfer and spectral coloration must be assessed with SIR gains.

## Native bank contract

`FE_ARRAY_SPATIAL33` uses `fe_array_state_bytes_for_mode`, the existing channel
histories and two FIR banks. `fe_array_init_spatial33` explicitly admits exactly
`mic_count*33` coefficients in physical-microphone order. Each channel's tap starts
at `common_delay-16`; the channel map still resolves physical microphone to PCM.
The result is a **sum**, not a second equal-weight average of already weighted
signals. The four-mic allocation is the same 3,704 B arena as delay-only FIR33;
full runtime, controller, stack, I/O and platform dependencies are excluded.

Safety admission requires finite coefficients, each magnitude <=16, aggregate L1
<=64 and aggregate DC sum within 1e-3 of one. These bounds prevent malformed banks;
they do not certify speech quality or guarantee the research numerical tolerance
for all conceivable banks. The caller must bind bank geometry/rate/calibration/
look identity. The research design runner only admits full arrays with unity gain
and zero residual calibration delay. Geometric `compensation_samples` metadata
is a reference calculation, not the phase response of a general spatial filter.

All microphones must be active. An actual mask change is rejected atomically:
joint weights cannot safely be reused by dropping a microphone and re-averaging.
A new masked-geometry bank/fallback requires a separate qualified decision; it is
not silently substituted. Same-mask requests remain no-ops. Likewise, the old
`request_steer(direction)` API is rejected for this mode rather than regenerating
an unrelated delay-only bank. The generic confidence controller is not a spatial
bank designer and cannot automatically drive this mode.

`fe_array_request_spatial33` accepts a complete new bank and its direction.
Existing histories, fixed common delay, exact crossfade endpoints, busy rejection
and reset cancellation apply. Idle identical direction AND identical coefficient
bytes is a no-op; the same direction with different weights is a real transition.
The C API is tested with both banks. The offline PCM runner accepts static bank
files only; it does not claim a new bank-schedule transport or automatic tracking.
Crossfading may still attenuate targets and change the effective echo path.

The normalized input is processed without hidden clipping, resampling, padding,
limiting or AGC. Output is unclipped Float32. At 70 mm/16 kHz the declared reference
delay is 21 samples for FIR33 and both spatial arms, but realized frequency phase
can deviate. FIR processing is causal with bounded history and no data-plane heap
allocation, I/O or locks. Filter design runs offline; no matrix inversion enters
the audio callback. Worst-case timing still needs separate target measurement.

## Source admission and fixed scenes

Source-only acquisition precedes scores. Numeric speaker ordinals 9..16 in the
same official LibriSpeech dev-clean archive are selected without replacements:
1673, 1919, 1988, 1993, 2035, 2078, 2086, 2277. None is in the prior eight-speaker
FE03 selection. The first four numeric utterances are concatenated and their first
four seconds retained. Original notices and CC-BY-4.0 derivative attribution stay
with the source/evidence, not copied into Git as large audio files.

Source preflight run 37337539976, artifact 11357177181 was downloaded, hashed and
independently losslessly decoded (32 FLACs/eight windows). The committed
`spatial-speech-admission-v1.json` binds those bytes before scoring. The complete
upstream archive digest is runner-measured, not an independent local re-download.
Acquisition/decode failures fail the run and never select replacement speakers.

Two pairs are fixed development; two other pairs are fixed speaker-disjoint
confirmation. The designs are frozen with no score-dependent selection. This is
new speaker confirmation for this experiment, not new rooms, an independent
corpus or a blind product benchmark. Once inspected, future adaptive reuse must
be classified as disclosed diagnostic data.

All three arrays (dual/ULA4/UCA4) share a 70 mm aperture. Four `(look,target,noise)`
scenes are fixed: `(0,0,90)`, `(60,60,150)`, `(90,90,90)`, `(30,45,120)`.
The last has a deliberate 15-degree pointing error; the co-located condition is
retained as a negative spatial-separation control. 48 mixtures run all three arms
(FIR33, diffuse-0.1, diffuse-1.0), totaling 144 mixed results, with isolated target,
interference and repeated outputs. Equal source RMS and common input headroom do
not normalize any output. Propagation uses the unchanged first-party offline
63-tap renderer, not the spatial design's target response.

The original canonical SI-SDR and fixed 60,795-sample reference span are reused;
21 samples is declared, never optimized per example. Separate component SIR,
target gain/error, interference attenuation, decomposition, output peak and
out-of-range samples are retained. Co-located speech can have a small apparent
component-SIR change from spectral coloration; that is NOT direction separation.
No model recognizes speech in this experiment, and no ASR/KWS benefit is inferred.
The fixed outcome is `FIXED_SPATIAL_REFERENCE_NO_PROMOTION`, including when scores
are positive. All unfavorable, pointing-error and co-located results remain.

## Execute and verify

```sh
python3 tests/validation/frontend_evolution/array_qualification.py --self-test
python3 tests/validation/frontend_evolution/array_qualification.py \
  --output /tmp/fe-array --execution-source "$(git rev-parse HEAD)" --require-arm
python3 tests/validation/frontend_evolution/speech_source.py \
  --speaker-offset 8 --output /tmp/fe-spatial-source
python3 tests/validation/frontend_evolution/speech_spatial_weights.py --self-test
python3 tests/validation/frontend_evolution/speech_spatial_weights.py \
  --source /tmp/fe-spatial-source --output /tmp/fe-spatial \
  --execution-source "$(git rev-parse HEAD)"
python3 tests/validation/frontend_evolution/speech_spatial_weights.py \
  --output /tmp/fe-spatial --execution-source "$(git rev-parse HEAD)" --verify
python3 tests/validation/frontend_evolution/speech_spatial_weights.py \
  --output /tmp/fe-spatial --execution-source "$(git rev-parse HEAD)" --negative-evidence
```

Use an identified clean checkout and fresh output directories. Missing Arm tools
fail `--require-arm`; native-only local runs are explicitly not Arm passes. The
existing array gate preserves old cases and adds 24 spatial known answers per
architecture, exact repeats and future-prefix tests. New C contracts cover five
rates and 1/2/4 mics, coefficient/memory/alias validation, chunk/reset equality and
bank transitions. The 2e-6 known-answer bound is not a relaxed shipping gate.

The speech verifier checks source admission, complete case/file sets, exact bank,
geometry, role, binary and PCM identities, fixed rendering/convolution samples,
recomputed metrics and summaries. Re-sealed negative copies must still reject
incomplete cases, changed scores, altered banks, incorrect roles or false product
claims. Checksums alone are not semantic verification. The artifact contains
source, build logs, coefficients, actual outputs and notices. Actions retention
is finite; closure receipts should retain the actual bytes separately.

## 中文结论边界

本批研究从“更准确的延时对齐”进入“联合空间权重”，但不是在线自适应 MVDR。
两档对角加载、33 抽头、阵列孔径和场景均事先冻结；新说话人先准入再评分，
不在旧录音上继续调参。真实语音的传播仍是合成自由场，方向为已知配置。

既要看 SIR，也要看目标频响、电平、波形误差与白噪声增益。目标变响或频谱
改变不等于听感改善；同方向场景的小幅 SIR 变化不能称为空间分离收益。
当前不自动选默认、不修改正式 SDK。固定多波束/DOA、真实房间/设备噪声、
BF/AEC 双讲和转向恢复、下游识别、其他上游与神经方案、最终 C2/C4 仍在 #657。
