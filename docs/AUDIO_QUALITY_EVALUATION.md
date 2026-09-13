# Cross-stage acoustic quality evaluation

`audio-pipeline` distinguishes **execution/regression correctness** from
**algorithm quality**.  A deterministic output hash, no clipping, a successful
reset, or a lower render correlation is useful evidence, but none of those alone
proves that AEC/RES, BF, NS or VAD is good.

The repository-side ground-truth quality gate is implemented by:

- `validation/tools/build_quality_validation_corpus.py`
- `validation/tools/quality_metric_support.py`
- `validation/tools/audio_quality_contract.py`
- `validation/policies/validation-audio-quality-development.json`
- `validation/tuning/search-spaces/audio-quality-pr-v1.json`
- `.github/workflows/audio-quality-evaluation.yml`

It is **development/regression authority only**.  Public validation, blind
holdout, PCR02 capture, SSC305 HIL, soak and Product Certification remain
separate promotion authorities.

## What each algorithm must prove

| Family | Required truth | Primary quality questions |
| --- | --- | --- |
| AEC far-end | render + exact echo component | ERLE, render suppression, convergence, path-change recovery |
| AEC/RES double-talk | render + clean near + exact echo/interference component | does echo go down without suppressing the user? |
| NS | clean near + exact noise + VAD labels | noise attenuation, SI-SDR, speech level preservation, VAD interaction |
| BF | 2-mic mixture + clean target + independent interferer | target SI-SDR, target level preservation, interferer rejection |
| VAD | frame labels | F1/recall/FPR plus onset and release latency |

The fail-closed truth contract rejects a corpus that tries to claim a quality
role without the references required to measure it.  In particular,
double-talk cases must not use ordinary ERLE on an output that contains near-end
speech; they use clean-near preservation plus known-interference reduction
instead.

## Added scale-sensitive metrics

SI-SDR is intentionally scale invariant.  A suppressor can therefore attenuate
near speech and still keep a deceptively good SI-SDR.  Quality cases additionally
measure `near_projection_gain_db`, the gain of the clean target projected onto
the processed output after declared-latency alignment.  This catches strong RES,
NS or BF over-suppression that SI-SDR alone can hide.

Known echo/interferer/noise references also allow correlation reduction to be
measured independently of target preservation.  Candidate selection therefore
cannot improve merely by turning everything down.

## Temporal quality

Far-end AEC truth is evaluated in 100 ms windows stepped every 10 ms.  The
convergence target is within 3 dB of the final stable ERLE.  Three consecutive
windows must satisfy the target.  The same rule is applied after a declared echo
path change/discontinuity to derive recovery time.

VAD classification metrics are complemented by onset/release delay derived from
frame labels and the runtime VAD trace.  This prevents a high F1 operating point
from hiding unusable latency.

## Partition discipline

CI uses three independent deterministic seeds:

```text
5107 -> Development
6107 -> Validation
7107 -> Shadow
```

The optimizer may search Development only.  The selected candidate is replayed
from scratch on Validation and Shadow.  `tuning_iteration.py` remains
fail-closed when an objective metric disappears and never writes shipping
defaults.

The current generic bounded search exposes the runtime tuning knobs already
supported by `ap_process_pcm` (AEC step size, NS floor and existing AGC/limiter
controls).  BF and VAD algorithm/operating-point iteration continues through the
existing stage-specific BF sensitivity/fault and VAD operating-point workflows;
the new cross-stage quality gate is the common acceptance layer those candidates
must satisfy before any higher authority is considered.

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
policy.  It is not a DUT, HIL or shipping qualification claim.
