# Cross-stage acoustic quality evaluation

`audio-pipeline` distinguishes **execution/regression correctness** from
**algorithm quality**. A deterministic output hash, no clipping, a successful
reset, or a lower render correlation is useful evidence, but none of those alone
proves that AEC/RES, BF, NS or VAD is good.

The release-neutral repository-side ground-truth quality gate is implemented by:

- `tests/validation/build_quality_validation_corpus.py`
- `tests/validation/quality_metric_support.py`
- `tests/validation/audio_quality_contract.py`
- `tests/validation/audio_quality_evaluate.py`
- `tests/validation/audio_quality_tuning.py`
- `tests/validation/validation-audio-quality-development.json`
- `tests/validation/audio-quality-pr-v1.json`
- `.github/workflows/audio-quality-evaluation.yml`

These wrappers reuse the canonical evaluator and tuning engines under
`validation/tools/`; they do not modify canonical validation authority or
shipping defaults. The quality layer is **development/regression authority
only**. Public validation, blind holdout, PCR02 capture, SSC305 HIL, soak and
Product Certification remain separate promotion authorities.

## What each algorithm must prove

| Family | Required truth | Primary quality questions |
| --- | --- | --- |
| AEC far-end | render + exact echo component | ERLE, render suppression, convergence, path-change recovery |
| AEC/RES double-talk | render + clean near + exact echo/interference component | does echo go down without suppressing the user? |
| NS | clean near + exact noise + VAD labels | noise attenuation, SI-SDR, speech level preservation, VAD interaction |
| BF | 2-mic mixture + clean target + independent interferer | target SI-SDR, target level preservation, interferer rejection |
| VAD | frame labels | F1/recall/FPR plus onset and release latency |

The fail-closed truth contract rejects a corpus that tries to claim a quality
role without the references required to measure it. In particular, double-talk
cases must not use ordinary ERLE on an output that contains near-end speech;
they use clean-near preservation plus known-interference reduction instead.

## Added scale-sensitive metrics

SI-SDR is intentionally scale invariant. A suppressor can therefore attenuate
near speech and still keep a deceptively good SI-SDR. Quality cases additionally
measure `near_projection_gain_db`, the gain of the clean target projected onto
the processed output after declared-latency alignment. This catches strong RES,
NS or BF over-suppression that SI-SDR alone can hide.

Known echo/interferer truth also produces
`interference_projection_attenuation_db`. This is the scale-sensitive rejection
metric used for candidate protection. `interference_corr_reduction` remains a
useful independent diagnostic, but correlation alone is not allowed to stand in
for actual level reduction.

## Temporal quality

Far-end AEC truth is evaluated in 100 ms windows stepped every 10 ms. The
convergence target is within 3 dB of the final stable ERLE. Three consecutive
windows must satisfy the target. The same rule is applied after a declared echo
path change/discontinuity to derive recovery time.

VAD classification metrics are complemented by onset/release delay derived from
frame labels and the runtime VAD trace. This prevents a high F1 operating point
from hiding unusable latency.

## Partition discipline

CI uses three independent deterministic seeds:

```text
5107 -> Development
6107 -> Validation
7107 -> Shadow
```

The optimizer may search Development only. The selected candidate is replayed
from scratch on Validation and Shadow. Missing objective metrics fail closed;
blind or product evidence is never allowed back into the optimizer.

## Initial measured incumbent floor

The first three-partition measurement exposed a BF weakness that the older
SI-SDR-only view did not show. PCR02 geometry was fixed at 35 mm, the desired
source was broadside, and a coherent interferer was mirrored at +/-60 degrees.
The current FULL-quality beamformer uses dynamic lag tracking.

Measured incumbent results before freezing the regression floor were:

| Partition | Worst BF case interference projection attenuation | Cross-case p10 |
| --- | ---: | ---: |
| Development 5107 | -0.510 dB | -0.253 dB |
| Validation 6107 | -0.014 dB | -0.004 dB |
| Shadow 7107 | -0.017 dB | +0.013 dB |

The desired-speech SI-SDR change in those BF cases stayed close to neutral, so
this is a small but real interferer-rejection asymmetry rather than a catastrophic
target-speech failure. The repository therefore freezes the current incumbent
as a **regression floor**, not as a positive quality claim:

- per BF case: `interference_projection_attenuation_db >= -0.75 dB`;
- aggregate p10: `>= -0.35 dB`.

Positive interferer attenuation remains the optimization direction. A future BF
candidate should improve these measurements while preserving target projection
and SI-SDR, then pass public/blind and PCR02 real 35 mm confirmation before any
shipping change is considered. The floor must not be silently rewritten to make
a future regression pass.

## Current bounded tuning scope

The generic bounded search exposes only runtime tuning knobs already supported
by `ap_process_pcm`: AEC step size, NS floor and existing AGC/limiter controls.
The cross-stage quality gate evaluates BF and VAD as non-regression constraints,
while BF algorithm/operating-point and VAD operating-point development continue
through their existing stage-specific research workflows. Any change to shipping
BF/VAD/AEC/NS behavior is release-bearing and requires its own promotion evidence;
this release-neutral quality PR does not change those defaults.

## Promotion ladder

```text
Ground-truth Development search
  -> independent Validation
  -> independent Shadow
  -> public validation-grade
  -> validation-grade blind / one-way
  -> PCR02 35 mm real capture replay
  -> SSC305 HIL / soak
  -> Product Certification
```

A PASS in `Audio Quality Evaluation` means only that the repository-side
cross-stage quality baseline is measurable and satisfies the frozen development
policy. It is not a DUT, HIL or shipping qualification claim.
