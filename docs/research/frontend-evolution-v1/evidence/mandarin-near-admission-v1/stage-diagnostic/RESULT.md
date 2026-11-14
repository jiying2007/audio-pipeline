# Mandarin fixed-stage baseline diagnostic V1

Actual single read-only measurement exit0 in 1.936414s, under outer timeout120. No DSP, ASR/KWS, new recording, candidate or alignment search. Input is the hash-locked D2 archive and separately admitted known-near engineering reconstruction, not mixed duplex mono used as truth. The historical D1/D2 null Chinese near metrics remain unchanged; this is a new descriptive measurement identity.

Historical audio source is cc853616685b9faf7880e6d8f8f1a89d187d342a-D1-observer. The current archive base6bc79ae is not a new audio execution of current main.

Independent review recomputed182 groups/1638 core metric fields and all gate counts/ratio ranges exactly; it did not execute DSP or rerun scientific timing.

Both profiles: 13 fixed windows ×7 lanes, total182 measurement groups. All consumed D1 artifact hashes pass. Plain, observer and original final PCM/metrics are byte-equal. Original629-frame observer has zero errors. AEC residual and NS input exactly match. Inputs/NSinput are offset0; NSoutput/AGC/finalS16 are offset160; all waveform scores use common physical[0,100480),628frames. Gate counts retain all629frames and are not denominator-equivalent to the waveform window.

## Observations for independent review

In both CALL/ASSISTANT, all629 frames include551 far-active and0 DT-active frames. All429 frames with nonzero known-near waveform samples are far-active and gate-eligible, none DT-active. The recorded EMA mic/reference ratio over those frames ranges0.0719116–0.6166214, below the existing1.5 onset requirement. This explains failure of that particular energy-threshold condition on these already constructed inputs, not universal DTD accuracy, human VAD, actual adaptive-update count or a causal proof of speech damage. Instant ratios can become huge after render energy vanishes because of the fixed numerical epsilon; never use that maximum alone as near evidence.

Common whole-span diagnostics:

| Lane | CALL gain-sensitive error dB | ASSISTANT error dB | CALL projection gain | ASSISTANT projection gain |
|---|---:|---:|---:|---:|
| AEC residual / NS input | -5.697940 | -5.321871 | 0.949977 | 0.939726 |
| NS joint RES output | -4.771246 | -4.715240 | 0.475993 | 0.472911 |
| AGC output | -4.771246 | -4.715240 | 0.475993 | 0.472911 |

The error rises after the joint NS/RES stage while the uncentered projection SI-SDR improves (CALL5.292751→5.862132dB; ASSISTANT4.835964→5.726068dB). These two different diagnostics must be reported together: reduced mixed-output energy and approximately halved near projection do not alone establish perceptual quality, separated near attenuation or echo suppression quality. NS includes spectral RES. No candidate or preference is selected from these results.

## Necessary interpretation limits

The engineering reference is raw pre-HPF/BF near. Upstream phase/filter/spatial processing changes its domain, so fixed-offset cross-stage errors are not pure near distortion or proof of a unique faulty module. Projection is only scalar least-squares geometry of mixed outputs, not physical separation. The noncanonical SI-SDR is explicitly uncentered with exact-zero numerator/denominator mapped to null; it does not replace canonical pipeline scores. Perfect identity can therefore have null logarithmic ratios with zero raw error, while zero-near windows also remain null; inspect energy fields to distinguish these conditions.

No optimal gain is applied to output; projection gain is a reported diagnostic. No resampling, tail flush, new metric floor, threshold relaxation, independent-sample claim, Chinese CER rerun, target resource claim, production or main mutation. Any future DTD candidate must independently freeze its causal intervention and protect pure echo/path-change cases, not tune to this single inspected utterance.
