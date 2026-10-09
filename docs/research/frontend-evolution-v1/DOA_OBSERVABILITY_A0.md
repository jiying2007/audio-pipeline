# FE03 A0 — microphone array geometry observability / 多麦阵列几何可辨识性

## Contract and boundary

Preregistered before implementation or results: [Issue #657, comment 6077581740](https://github.com/jiying2007/audio-pipeline/issues/657#issuecomment-6077581740). Frozen machine contract:
[`doa-observability-a0.json`](../../../.github/research/frontend-evolution-v1/doa-observability-a0.json).
The execution implementation is `tests/validation/frontend_evolution/doa_observability_a0.py`,
called through the **existing** `verify-docs-gate.sh` (docs-only and full Verify).
It runs only the Python standard library; there is no parallel acoustic evaluator,
new workflow, audio fixture, external download, shipping DSP path or SDK API.

This is an analytic **upper bound on possible direction observability** given ideal
far-field differential delays. It is *not* an estimated DOA, GCC-PHAT/SRP-PHAT
result, measured audio separation, BF enhancement, KWS/ASR score, microphone
failure classifier or SSC305 execution. It does not establish array robustness
against spatial aliasing, sampling quantization, synchronization, calibration,
self-noise, reverberation, motion, motor noise or far-end playback.
Decision is immutable: `FE03_DOA_GEOMETRY_OBSERVABILITY_A0_NO_PROMOTION`.

## Mathematical convention

Physical microphone index is separate from render-reference channels and from the
PCM channel map. All positions are metres in a right-handed XYZ frame; the unit
source vector points **from array toward source**, as in FE02 `array_native-v1.json`.
For azimuth `az` and elevation `el` in degrees:

```
u = (cos(el)*cos(az), cos(el)*sin(az), sin(el))
reference = first active physical microphone index
TDOA_samples(i relative to reference) = dot(r_i - r_reference, u) * 16000/343
```

The first active microphone's zero delay is excluded from the differential vector.
Only *XY baseline rank* is checked: rank 0 has no directional differences, rank 1
constrains just one projected dimension, and rank 2 has two independent planar
baselines. Planar arrays always lose the sign of elevation in this far-field
model; even a full planar rank 2 is **not** a unique 3D localization capability.
This is rank of the baseline geometry, not a guarantee of angle-estimator accuracy.

Fixed layouts: ULA4 on x at 0/35/70/105 mm; UCA4 in the xy plane at
(+35,0), (0,+35), (-35,0), (0,-35) mm. Both use 16 kHz and c=343 m/s.
Only the six frozen rank cases and three frozen mirror contrasts in the JSON
contract are admitted. Geometry and 16 kHz source constants are also bound to
the original first-party FE02 source to expose upstream drift; the source
record remains immutable.

| Case | Expected XY rank | Interpretation |
| --- | ---: | --- |
| ULA4, all 4 | 1 | +30°/-30° mirror directions indistinguishable |
| UCA4, all 4 | 2 | +30°/-30° differential delay vectors distinguishable |
| UCA4, mask `0xe` | 2 | Three noncollinear surviving microphones retain planar rank |
| UCA4, mask `0x5` | 1 | Opposite surviving pair behaves as linear pair |
| UCA4, mask `0x1` | 0 | One active microphone has no TDOA |
| ULA4, mask `0x7` | 1 | Three collinear active microphones still rank 1 |

The exact +30°/-30° ULA4 contrast must be <=1e-12 sample, UCA4 contrast
must be >=0.25 fractional sample, and UCA4 +20°/-20° elevation contrast
at azimuth +30° must be <=1e-12 sample. The latter checks a known limitation,
not 3D performance. Values are ideal fractional delays, not observed 16-kHz
sample-quantized correlation peaks.

## Reproduce and failure handling

From an exact-source checkout with Python 3.10+:

```sh
python3 tests/validation/frontend_evolution/doa_observability_a0.py --self-test
python3 tests/validation/frontend_evolution/doa_observability_a0.py \
  --output /tmp/fe03-a0-result.json \
  --execution-source "$(git rev-parse HEAD)"
python3 tests/validation/frontend_evolution/doa_observability_a0.py \
  --verify --output /tmp/fe03-a0-result.json \
  --execution-source "$(git rev-parse HEAD)"
```

Use a *new output path* for each run: existing paths fail closed. Self-test verifies
plan identity, FE02 source linkage, six ranks, three contrasts, deterministic
output and tamper rejection; corrupt geometry, authority, mask, nonfinite angle,
reference policy, partial cases and modified result are rejected. The result
receipt binds the exact source revision, plan SHA-256, FE02 source SHA-256 and
analytic oracle SHA-256, but does not independently audit the GitHub runner or
replace real recorded-signal evidence. No result is accepted as CI-qualified
until the exact-head Verify `summary` is successful.

## Next experiments / 后续

A0 addresses *whether* an ideal bearing dimension can be observed, not *how*
to estimate it. Separately preregister an actual microphone-signal GCC-PHAT or
SRP-PHAT candidate with fixed geometry and band limits, explicit ULA mirror-
equivalence scoring, UCA planar bearing, confidence/hold/switch behavior and
moving/noisy/double-talk cases. Keep known-direction BF (oracle) versus estimated
bearing (candidate) separate and report failures. Cross-device runtime and
real enclosure/motor/capture/SSC305 qualification remain open. A0 never closes
FE03/FE09 or E001 Product Certification.
