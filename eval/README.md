# Acoustic evaluation harness

This directory defines the repository-side contract for repeatable acoustic/product evaluation. Shipping corpora, recordings and licensed metric implementations stay outside the repository.

## Manifest

A case is described by `manifest.schema.json`. PCM inputs are little-endian signed 16-bit. The high-level processor currently consumes two-channel interleaved microphone PCM and mono render reference PCM.

Example:

```json
{
  "sample_rate_hz": 16000,
  "mic_channels": 2,
  "mic_pcm": "case01/mic.pcm",
  "render_pcm": "case01/render.pcm",
  "clean_near_pcm": "case01/near.pcm",
  "metadata": {
    "scenario": "double-talk",
    "distance_cm": 100
  }
}
```

Run the current build:

```bash
python3 eval/run_eval.py \
  --manifest /path/to/corpus/case01.json \
  --processor ./build/ap_process_pcm \
  --output-json case01.metrics.json
```

The runner records deterministic, dependency-free baseline metrics such as RMS, render correlation and SI-SDR when a clean near-end reference exists. Product teams may add PESQ/POLQA/STOI through licensed/external tooling, but those results must be attached to the same SKU certification record rather than silently replacing these repository metrics.

## CI self-test

```bash
python3 eval/run_eval.py --self-test
```

The self-test verifies metric math only. It is not an acoustic-quality claim.

## Product corpus requirements

At minimum cover far-end-only at several playback levels, near-end-only, true double-talk, path/route changes, clock mismatch, stationary and non-stationary noise, quiet speech, motor/gear/PWM noise and CPU/DDR contention. Store raw data and generated JSON outside the source repository when licensing/privacy/product constraints require it.

A shipping certification report should record the exact audio-pipeline build fingerprint, target SoC/kernel/compiler/DVFS/audio route, module/backend selection and the corpus revision used for the run.
