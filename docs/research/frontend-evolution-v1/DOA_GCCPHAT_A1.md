# FE03 A1 — actual-PCM GCC-PHAT direction diagnostics / 多麦 PCM 方向估计

## Scope and fixed authority / 研究边界

Preregistered **before any A1 implementation or score** in
[issue #689](https://github.com/jiying2007/audio-pipeline/issues/689),
with [fixed representation/sign addendum](https://github.com/jiying2007/audio-pipeline/issues/689#issuecomment-6081291227).
The exact machine contract is
[doa-gccphat-a1.json](../../../.github/research/frontend-evolution-v1/doa-gccphat-a1.json).
Implementation reuses qualified FE03 A0 geometry/source identity. Prerequisite:
fresh-main [Verify 37930402899](https://github.com/jiying2007/audio-pipeline/actions/runs/37930402899)
on main 8550596522d08ee048a3ea7127e2802ba21e1565, completed success.

This is **first-party offline Python** engineering analysis of actual
four-channel deterministic *time-domain normalized Float32 PCM*, not an
ideal-delay oracle masquerading as an estimator. Estimator input is restricted
to PCM, approved array positions, fixed rate/FFT/search contract, and
caller-supplied physical microphone mask. It never receives the scene label,
true azimuth, clean source or render-reference channel. The generator alone
knows disclosed source directions; scene truth is attached *after* inference
for descriptive audit.

The fixed decision is FE03_DOA_PCM_GCCPHAT_A1_DIAGNOSTIC_NO_PROMOTION.
No shipping src/include C SDK, ABI, defaults, AEC, NS, AGC, model, release,
or E001 product-qualification authority changes. A contract/CI success is
not measured real-world DOA accuracy.

## Numerical experiment / 固定实验

At 16 kHz and 343 m/s, the exact FE03 A0 ULA4 (0/35/70/105 mm x-axis)
and UCA4 (35 mm radius orthogonal planar positions) are used. The source
vector points **from array toward source**, not along propagation. Four
physical channels are interleaved in all PCM buffers; a physical mask
selects active microphones, not render references. The first active mic
is the difference reference. Geometry determines possible identifiability.

The fixed generator synthesizes 2048-sample independent noise-like real
waveforms by xorshift32 random spectral phases, conjugate symmetry,
inverse radix-2 FFT and source-only peak scaling. It retains the 300–1500 Hz
source band before fixed 0.24 primary / 0.12 optional interferer amplitudes,
linear fractional sampling at the geometric delay and fixed 0.002 seeded
per-channel perturbation (except silence). Values outside [-1,+1] fail:
no output clipping, limiter or loudness normalization is allowed.

Eight **512-sample × four-physical-mic** scenes:

| Case | Geometry and mask | Input |
| --- | --- | --- |
| ula-plus30 / ula-minus30 | ULA4, 0xf | +30° / -30° |
| uca-plus30 / uca-minus30 | UCA4, 0xf | +30° / -30° |
| uca-three-plus30 | UCA4, 0xe | +30°, noncollinear 3-mic |
| uca-opposite-plus30 | UCA4, 0x5 | +30°, opposite 2-mic |
| uca-silence | UCA4, 0xf | all-zero PCM |
| uca-interferer | UCA4, 0xf | +30° plus weaker -60° |

All unfavorable/ambiguous responses remain in evidence. Only rank-2
planar arrays have a descriptive circular azimuth error. The ULA4 and
opposite-pair rank-1 arrays cannot distinguish all planar bearings.
A single active mic provides no DOA, and no planar array can resolve
the sign of elevation from far-field TDOA alone.

## Estimator, causality and evidence

A symmetric Hann window is applied to the 512-sample observation, followed by
the fixed 1024-point FFT. For each active nonreference microphone, PHAT is
the inverse FFT of X_ref times conjugate(X_mic), divided by
max(abs(X_ref times conjugate(X_mic)), 1e-12). Its signed circular
correlation is linearly interpolated at predicted lags from the geometry.
The score is the equal mean over active nonreference microphone pairs.
The frozen search grid has **72 candidates, -180° through +175° in 5° steps**,
and the lowest index wins exact ties. Peak score minus the best score
separated by at least 20° is a *descriptive gap*, not a calibrated confidence.
Single mic, exact silence and no valid cross-spectrum produce no bearing.

Forward/inverse FFT and positive signed correlation use independent
known-answer tests, including a positive six-sample impulse advance.
The full PCM is generated twice and must match byte-for-byte, as must
the complete 72-candidate direction scores. A changed suffix after
sample 383 must not affect a separately recomputed 384-sample prefix
using the same 1024-point FFT. This is **finite offline causal-prefix
evidence**, not certification of a 10 ms streaming system.

The canonical receipt binds the exact execution source SHA; FE03 A0,
A1 contract and oracle SHA-256; each PCM input SHA-256; full score vectors
and SHA-256; rank/mask/reference; estimated bearing/peak/gap; repeat
identity, changed-future and unchanged-prefix fingerprints; and disclosed
truth *only after* inference. Six resealed semantic receipt negatives
and separate contract mutations reject wrong identity, promotion, missing
scenes and rewritten scores. Symlinks, existing output files, invalid
Float32, non-finite numbers and stale evidence fail closed. The existing
docs/assurance Verify gate runs short self-tests without new workflows,
permissions, dependencies or another canonical evaluator.

## Reproduce / 复验

From a clean checkout with Python 3.10+:

~~~sh
python3 tests/validation/frontend_evolution/doa_gccphat_a1.py --self-test
python3 tests/validation/frontend_evolution/doa_gccphat_a1.py \
  --output /tmp/fe03-a1-new-receipt.json \
  --execution-source "$(git rev-parse HEAD)"
python3 tests/validation/frontend_evolution/doa_gccphat_a1.py \
  --verify --output /tmp/fe03-a1-new-receipt.json \
  --execution-source "$(git rev-parse HEAD)"
~~~

Use a new output path for each execution. The research PR needs exact-head
Verify/summary, and protected squash requires an independent fresh-main
Verify/Release. Hosted/QEMU or deterministic PCM evidence does **not**
certify SSC305 CPU/RSS/p99, real motor/wind/room acoustics, BF/AEC recovery,
KWS FAR, ASR WER, a shipped C4 SDK or E001 physical qualification.

Next: independently preregister recorded-speech direction diagnostics and
separate known-direction BF upper bounds from estimated-bearing candidates.
A1 does not close FE03, FE07–FE09, or physical issue #58.
