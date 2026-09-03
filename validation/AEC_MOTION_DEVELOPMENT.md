# AEC continuous-motion development corpus

`build_aec_motion_corpus.py` adds a deterministic development-only AEC layer for continuous, unannounced echo-path motion.

It exists because reset/recovery fixtures and a small hand-authored synthetic set can overestimate real moving-path robustness. The generator creates 12 far-end-only cases per seed across four motion families (`delay-wander`, `gain-crossfade`, `reflection-birth-death`, `compound`) and three intensities. Delay and gain trajectories are smooth knot interpolations, so no `echo_path_change` control notification is sent.

## Authority boundary

The corpus is always:

- `tier=regression`;
- `split=dev`;
- deterministic and seed-bound;
- synthetic/generated rather than public real audio;
- eligible for development/regression use only;
- never validation-grade, blind, HIL, certification or shipping evidence.

The GitHub workflow uses independent seeds `4107`, `4207`, and `4307` and seals each run separately. The policy requires all 12 cases to pass, no aggregate render-correlation regression, no far-end-only RMS amplification, and normal clipping/DC safety.

This layer must not consume or derive thresholds from the GitHub-hosted Microsoft AEC Challenge four-case microset. That real-data microset remains a one-way promotion gate after a candidate has already been selected. A candidate rejected by the hosted holdout is discarded rather than retuned against the holdout.

## Local use

```sh
python3 validation/tools/build_aec_motion_corpus.py --self-test
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

Use multiple previously unobserved development seeds before proposing an AEC default change. Do not move failed hosted-holdout examples into this generator or adapt generator parameters to reproduce a particular holdout outcome.
