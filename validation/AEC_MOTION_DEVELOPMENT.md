# AEC continuous-motion development corpus

`validation/tools/build_aec_motion_corpus.py` is the single canonical generated
AEC continuous-motion development source. It is deterministic, seed-bound,
`tier=regression`, `split=dev`, and never a blind/release/HIL/Product
Certification authority.

## Why generator v2 replaces v1

I001 fixed the product processor and compared the historical v1 generator with a
separately implemented geometry diagnostic. The historical render used five
fixed tones and its earliest echo tap moved roughly 186..376 samples in the
observed seeds. The audited geometry used broadband probes, kept the rigid
device direct path fixed at 672 samples and retained a 32-sample causal margin
relative to the 640-sample startup reference. Both corpora passed the existing
case gates, so the comparison did **not** prove a DSP improvement; it proved that
the old corpus represented a different and more ambiguous measurement model.
The exact I001 source/run/artifact identities remain archived in
`docs/program/iterations/I001-result.json`.

Generator v2 therefore makes the audited model canonical instead of keeping
parallel legacy/new backends. Git history and I001 evidence preserve the old
implementation for auditability.

## Canonical v2 model

The test fixture is intentionally explicit:

- sample rate: 16 kHz, 10 ms frames;
- rigid speaker/microphone separation: 0.08 m;
- rectangular room: 6.0 x 5.0 x 2.8 m;
- speed of sound: 343 m/s;
- fixed total direct delay: 42 ms / 672 samples;
- nominal startup reference: 40 ms / 640 samples;
- initial direct-path causal margin: 2 ms / 32 samples;
- paths: direct plus six first-order wall images;
- motion: stationary, translation, rotation of the rigid device;
- probes: deterministic colored broadband and speech-envelope broadband;
- direct gains: 0.30 and 0.03, producing 12 cases per seed.

The device I/O part of direct delay is fixed. Translation/rotation change only
room-image geometry; the direct path never moves and every reflection must stay
strictly later than direct. Fractional path sampling is linear and zero-extended.

Every case writes `ground-truth.json` with frame-start delays/gains, path minima
and maxima, causal margin, case seed, excitation/motion/direct-gain identity and
a hash of the canonical model. The source manifest binds the generator bytes,
model, corpus, PCM and ground-truth files. Output must be absent or empty so a
failed/stale attempt cannot be silently reused.

## Measurement limitations

This is a reduced-order quasi-static simulation, not a claim about a shipping
robot or a complete room acoustic field. It deliberately does **not** model:

- measured DUT speaker/microphone transfer functions;
- diffuse/late reverberation beyond first-order wall images;
- nonlinear loudspeaker distortion;
- clock drift or packet/ring-buffer faults;
- motor/structure noise;
- wind, microphone aging or physical enclosure leakage;
- real human speech labels or perceptual quality.

These omissions bound the conclusion. Passing v2 is software/generated-data
regression evidence only.

## Known-answer and negative qualification

Before any AEC/Sync algorithm candidate can use v2 as development evidence, I002
requires:

```sh
python3 validation/tools/build_aec_motion_corpus.py --self-test
python3 validation/tools/build_aec_motion_bundle.py --self-test
python3 tests/validation/aec_motion_model_qualification.py --self-test
```

The qualification rejects invalid geometry, nonempty outputs, duplicate bundle
seeds, a moving/noncausal direct path, model/hash drift and unregistered product,
evaluator, policy or dataset-lock changes. The fixed excitation ambiguity
diagnostic requires each broadband probe to remain below `0.30`; a deliberately
periodic negative control must exceed `0.999` so the detector proves it can see
the historical failure class.

`validation/tools/run_validation.py` remains the acoustic metric authority and
`validation/policies/validation-aec-motion-development.json` remains unchanged.
The measurement migration does not tune those thresholds.

## Data roles

The scheduled/PR development seeds are repeatable regression data. After a seed
has been observed it is exposed and cannot later be described as independent
confirmation. The existing Hosted Real Audio/AEC microsets are also repeated
hosted regression in the current phase; they cannot be used as fresh promotion
holdouts after repeated inspection.

Any future AEC product candidate must reserve new source groups/seeds before
candidate replay and follow the program's development -> validation -> shadow ->
independent-confirmation authority rules. I002 itself has `candidate_limit=0`,
`confirmation_limit=0` and cannot promote DSP.

## Local regression use

```sh
python3 validation/tools/build_aec_motion_corpus.py \
  --output /tmp/ap-aec-motion --seed 4107 --seconds 8

cmake -S . -B build-motion -DCMAKE_BUILD_TYPE=Release -DAP_BUILD_BENCH=OFF
cmake --build build-motion --target ap_process_pcm --parallel

python3 validation/tools/run_validation.py \
  --corpus /tmp/ap-aec-motion/corpus.json \
  --policy validation/policies/validation-aec-motion-development.json \
  --dataset-lock validation/datasets.lock.json \
  --source-manifest /tmp/ap-aec-motion/source-manifest.json \
  --processor build-motion/ap_process_pcm \
  --output /tmp/ap-aec-motion/report.json \
  --evidence-manifest /tmp/ap-aec-motion/evidence-manifest.json \
  --enforce
```

Different-corpus metrics from v1 and v2 must never be presented as a candidate
before/after gain. Exact-base differential claims require identical PCM and the
same evaluator/policy.
