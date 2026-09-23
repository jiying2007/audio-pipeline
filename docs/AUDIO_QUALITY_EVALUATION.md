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
- `tests/validation/audio-quality-ns-floor-call-v1.json`
- `tests/validation/audio-quality-ns-floor-call-v2.json`
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

The recurring generic CALL PR-smoke and formal `call-v1` search now have a
separate scale-sensitive confirmation path for the NS floor. Formal Acoustic
Tuning run `35725902946` on source `9b9ff166da2798f3a93d23b099783d918d445440`
selected `ns_floor=0.07` as candidate `0d5f52491863` and emitted
`ACOUSTIC_CANDIDATE`; its hash-bound artifact digest is
`sha256:99024abc064519e9e482fc9a0e75db0c73ef64bd7d71c50a8e13d628e9dcf045`.
That evidence remains non-shipping. The manual
`audio-quality-ns-floor-call-v1.json` search keeps the current `0.12`
baseline and isolates only `ns_floor` across `0.06/0.07/0.08/0.10/0.12/0.14`.
It deliberately reuses the quality objective containing
`p10_near_projection_gain_db`, so `0.07` must survive scale-sensitive target
preservation as well as SI-SDR, interference, AEC, VAD and clipping constraints.
Its purpose is candidate confirmation, not mutation of runtime or shipping
defaults.

After candidate `0d5f52491863` / `ns_floor=0.07` was terminally rejected by
public-relative qualification run `35815591807`, the next repository-side
selection lane is `audio-quality-ns-floor-call-v2.json`. V2 is deliberately
**terminal-aware, not public-metric-tuned**: it removes only the registered
terminal `0.07` point and keeps the v1 baseline, quality metrics, weights,
scales and regression limits unchanged. Its NS axis is
`0.06/0.08/0.10/0.12/0.14`. Selection still uses only the independent
Development/Validation/Shadow quality partitions; no Full160 public metric,
failed case, or blind evidence is fed back into the objective. A selected v2
candidate starts a new frozen lineage and must traverse public-relative,
blind, target/HIL and Product Certification gates independently.

AGC/limiter searches need an additional scale-sensitive check. The generic
regression objective can improve attenuation-oriented metrics while lowering the
near-end signal as a whole, so an `ACOUSTIC_CANDIDATE` from that loop is not by
itself evidence that the perceptual level trade is acceptable. The manual
`audio-quality-agc-limiter-frontier-v1.json` search replays the same bounded
paired AGC/limiter path through this ground-truth quality layer and reuses the
existing `p10_near_projection_gain_db` objective/regression constraint. No new
product loudness threshold is invented by that search: it asks the existing
scale-sensitive quality contract whether the apparent gain survives target-level
preservation. The result remains development/research authority only.

That distinction is now measured rather than hypothetical. Generic Acoustic
Tuning run `35568818095` selected `agc_target_dbfs=-20`,
`limiter_dbfs=-18` from the seven-point paired path with development score
`+0.5265` and emitted `ACOUSTIC_CANDIDATE`. Replaying the exact same path in
Audio Quality Evaluation run `35571014346` on source
`288ad1199168eecc808b059ea02f17aee05a121c` produced `KEEP_BASELINE`.
The scale-sensitive development scores from the `-16/-14` anchor through
`-22/-20` were:

```text
AGC / limiter     -16/-14   -17/-15   -18/-16   -19/-17   -20/-18   -21/-19   -22/-20
quality score      0.0000    -0.1961    -0.4724    -0.6939    -1.0230    -1.3599    -1.8161
near projection   -4.8862    -5.0262    -5.2236    -5.3818    -5.5711    -5.8118    -6.1376 dB
```

The principal SI-SDR, interference-projection, ERLE, VAD classification and
clipping summaries stayed effectively unchanged across that path; near-target
projection fell monotonically. This isolates target-level loss as the reason the
generic attenuation-oriented objective preferred a lower AGC/limiter pair. The
lower paired direction is therefore closed for generic CALL optimization, while
the quality search remains available as the reproducible evidence path.

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
