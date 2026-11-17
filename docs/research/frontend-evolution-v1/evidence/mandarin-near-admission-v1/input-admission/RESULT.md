# Mandarin known-near input admission V1

Actual measurement completed once, exit 0, elapsed 0.603265 s under an outer 120 s timeout. Source ZIP SHA256 is a3ab7823fdcd7586c3b72eb214b5536dcfb7531fdf0b1611d49e1575a29b2c3d. Exact base is 6bc79aeae22b104312fee3bc02017f9e89a43ca1. Main/open PRs were checked before execution; no duplicate input-decomposition admission experiment was identified in bounded repository search. No claim of exhaustive historical uniqueness.

This is a measurement-input admission, not a DSP candidate. The original D1/D2 decisions remain unchanged: they did not claim Chinese mixed input as clean-near truth. The present independently frozen operation reconstructs a distinct engineering near reference from already retained clean_mono and the historical preparation recipe. It does not use processed output to fit or infer near speech.

## Exact result

Five existing prepared PCM files match the immutable preparation byte lengths and SHA256 hashes. Clean mono padding is zero and both clean microphone channels exactly duplicate it. Original 68496 samples are taken from the documented interval [8000,76496); Python round(x*0.5) is placed at sample16000 in a 100640-sample sequence. The two echo streams use saved render and exact original taps/rounding. No alignment optimization, clipping, gain search, source substitution or input regeneration occurs.

Both saved duplex microphone channels equal known-near plus their reconstructed echo at every sample: 201280 total exact sample comparisons, zero mismatches. Peaks are 4988/4846, and all sums fit S16. The first-channel saved mono also matches exactly. The known-near output SHA256 is a81c2b25f9f35e4099f076c992ede1f17ed80d1fe3f3d9fd6eb0206dd0c97e2f. It has 68079 nonzero samples, first16000 and last84495. Those nonzero positions are engineering waveform support, not human speech-activity annotations.

Two deterministic one-sample alterations are rejected by the exact comparison. These negative controls only test the equality comparator, not a DSP algorithm, universal robustness or rights qualification.

The original preparation implementation was subsequently read unchanged from build/exact-source.tar: tests/validation/mandarin_downstream.py SHA256 2bba610f9154e0eb3d115a361104191a7fd2f5ac0fdb4d9972dd4633599bef9c. It is retained separately from admit.py. This binding is historical implementation evidence, not a claim the current script produced the original inputs.

## Scope and next boundary

Decision: ENGINEERING_NEAR_REFERENCE_ADMITTED for this single previously inspected synthetic-mixture development utterance only. This does not establish physical source separation, independent speech corpus quality, near truth for D30–D49 field recordings, Chinese CER/KWS improvement, detector correctness, or SSC305 performance. No DSP/ASR/KWS execution and no production/main change occurred.

A separately frozen subsequent stage may evaluate existing outputs against this reference using known pipeline latency and no lag fitting. Such measurements must keep upstream HPF/BF reference-domain effects, truncation/tail semantics and case dependence explicit. This admission must not self-approve a candidate algorithm or rewrite earlier null metrics. D49 historical matrix DEVELOPMENT_REJECTED and incomplete independent audit remain distinct; lack of its archived dependency closure was not bypassed.
