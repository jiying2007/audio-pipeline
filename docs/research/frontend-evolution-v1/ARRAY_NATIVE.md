# FE02/03 native array research / 原生多麦与分数延时求和

## Scope and authority

Implementation base: `712013b9415a53c50a0ac003b42f944f9a9d59f5`.
Experiment: `.github/research/frontend-evolution-v1/array-native-v1.json`.
Preregistration: issue #657, comment 5988218312. Original approved plan unchanged.

This is a first-party **research C implementation**, not just a Python geometry
schema. `array_native.c` actually consumes raw 1/2/4-channel samples and produces
one beam. It is NOT installed in the 2.x SDK, does not modify the production
pipeline or its two-microphone envelope, and is not a product qualification.
Promotion must move the selected implementation into the single production core,
with explicit API/ABI and profile qualification, not leave duplicate cores.

## Geometry and timing

Positions are metres in a caller-defined right-handed XYZ frame. The unit source
vector points **from array toward source**, not the propagation direction. Norm
squared must be within 1e-6 of one; the core does not silently normalize it.
`reference_mic` defines the coordinate/time origin and need not remain active.
`channel_map` is a permutation from physical microphone index to PCM slot.
Microphone and render-reference counts are never conflated. This BF takes no
render channel. Calibration gain includes optional polarity correction; positive
calibration latency means that channel arrives late relative to ideal geometry.

For reference position r0, microphone position ri, source direction u, sample
rate fs and assumed sound speed c=343 m/s:

```
R = max_i ||ri-r0||
C = max_i |calibration_latency_i|
L = ceil(R*fs/c + C) + 1
Di = L + dot(ri-r0, u)*fs/c - calibration_latency_i
```

A plane wave arriving as `s[n + dot(ri-r0,u)*fs/c - calibration_latency_i]`
aligns to `s[n-L]` in the ideal-delay model. All microphones, including masked
ones, determine L. Thus active-mask changes and reinitializing at another source
direction do not silently change the declared common delay.

Actual interpolation is NOT an ideal all-pass delay. Two fixed structures are
available: linear two-tap and centered four-tap cubic Lagrange. Both use the same
L and causal history bounds. Cubic uses offsets floor(D)-1 through floor(D)+2;
D is restricted to [1,125] in a 128-sample ring. Unsupported geometry is rejected,
not clamped. Each output is the arithmetic mean over active calibrated channels.
There is no hidden normalization, limiter, NS, VAD, DOA or target selection.

The fixed half-sample response is retained at 0/1/3/6/7.5 kHz in the report. This
exposes high-frequency attenuation rather than manufacturing a speech-quality
win. Linear and cubic are both research baselines; neither is promoted by this
qualification. Better fractional/fixed FIR designs remain in FE03.

Public mathematical references (no copied implementation, coefficients or tables):
- Julius O. Smith, *Physical Audio Signal Processing*, fractional-delay filters:
  https://www.dsprelated.com/freebooks/pasp/Fractional_Delay_Filters.html
- SOF fixed-beamformer design and geometry/robustness considerations:
  https://thesofproject.github.io/latest/developer_guides/algorithms/tdfb/time_domain_fixed_beamformer.html

## Native contract

`array_native.h` is a research-only interface. Memory is caller-owned and aligned
to 16 bytes. State physically scales with 1/2/4 microphone histories. Init checks
finite geometry, distinct microphone positions, permutation, signed gain bounds,
calibration bounds, supported sample rate and ring capacity before any state
mutation. Failed initialization nulls a disjoint output handle; aliasing handle or
configuration storage is rejected without overwriting it.

Processing accepts normalized interleaved float input from one sample frame up
to 10 ms per call; output has exactly one float per input sample frame. Active input must be finite and
within [-1,1]. Input, output and state must not overlap. Validation of the entire
submitted chunk precedes mutation. Inactive channel slots are ignored/zero-stored
so a masked NaN does not poison future state. Output is **unclipped float** and may
exceed unity after gain calibration/cubic interpolation. Converting to S16 for a
later pipeline requires explicit clipping accounting; it is not hidden here.

`set_active_mask` is caller-serialized and supports three-of-four or one-of-four.
An empty mask is invalid. Continuing histories survive; newly enabled channels
start with zero history. Mask changes are explicit fault control, NOT automatic
health detection or click-free steering. The caller must account for transition
and re-warm-up effects. Reset clears histories/counters but preserves geometry,
mask, mode and calibration. There is no live direction-update API in this tranche.

The offline runner accepts a fixed text geometry, raw S16LE input and emits F32LE
plus JSON. It rejects empty/partial 10 ms PCM and existing output files. Conversion
is explicitly int16/32768, with no final normalization or padding. Zero prehistory
and one-output-per-input mean the last L target samples have not emerged when
input ends; no hidden tail flush is manufactured. A 10 ms transport call is not a
claim that total latency is just L or that a DUT scheduler meets deadlines.

## Run and retained evidence

```sh
python3 tests/validation/frontend_evolution/array_qualification.py --self-test
python3 tests/validation/frontend_evolution/array_qualification.py \
  --output /tmp/fe-array-run --execution-source "$(git rev-parse HEAD)" --require-arm
python3 tests/validation/frontend_evolution/array_qualification.py \
  --output /tmp/fe-array-run --execution-source "$(git rev-parse HEAD)" --verify --require-arm
python3 tests/validation/frontend_evolution/array_qualification.py \
  --output /tmp/fe-array-run --execution-source "$(git rev-parse HEAD)" --negative-evidence
```

Use a clean, identified checkout. `--require-arm` fails when the Arm compiler or
QEMU is unavailable. Omitting it permits a clearly native-only local run, never
an implicit Arm PASS. CI requires Arm in the pinned existing project image and
runs through the existing Quality/Verify reference job, not a new workflow.

The analytic fixtures cover ten geometries/masks/calibration variants, three
patterns and two interpolators: 60 cases per native/Arm target. ULA4, UCA4 and a
nonplanar four-point geometry are actual four-channel inputs. Impulses and distinct
per-channel components detect ignored microphones. The independent oracle uses
the generic polynomial basis product, not the C kernel's expanded coefficients.
The explicit 2e-6 absolute arithmetic error bound is a new research known-answer
contract, not a relaxation of any existing shipping bit-exact/acoustic gate.

C tests additionally cover five sample rates, single-sample versus full-frame
chunk equality, reset equality, calibration/polarity, invalid inputs and masked
faults. A 64,000-frame/64-lifecycle workload runs under native and sanitizers; Arm
executes the same C contract. This is accelerated engineering input, not speech
quality, DUT wall-clock soak or silicon CPU/p99/stack qualification. Compiler
stack-use output describes that object only, not complete thread stack usage.

Evidence preserves source bytes, plan, compile commands, binary hashes, compiler
identity, Arm ELF header, unit results, all geometry/PCM/meta outputs, repeated PCM,
finite-prefix variants, interpolation response and checksums. The verifier
recreates fixtures, recomputes oracle errors and checks full case/identity/count
coverage. Re-sealed semantic negatives run on a temporary copy, never by damaging
the real receipt. A green engineering result cannot authorize shipping promotion.

## 中文接续边界

本轮是真正可运行的 C 多麦 BF 原型：单/双/四麦、线性/环形/任意四点坐标、
通道映射、增益/极性/延时校准、三路有效降级及两种分数延时插值。不是把
四路音频先在 Python 中合成单路再宣称四麦支持。

旧 2.x SDK 的最大麦数、DSP、默认参数和产品资格身份均不变。当前几何和
已知方向测试是数值与接口证据，不是 DOA 算法、全双工效果或四麦优于双麦
的证明。方向估计/平滑转向、更多 FIR、BF/AEC 联调、独立语音场景与最终
C4 SDK 仍由 #657 跟踪。其他上游适配器和独立数据工作继续推进，不能把本轮
第一方原型当作 Athena、SOF 或任何第三方原版复现。
