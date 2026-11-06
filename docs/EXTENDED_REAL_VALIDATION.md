# Extended Real Independent Research Validation

> **Current research scope:** This workflow evaluates exact source and lawfully usable acoustic data. [RESEARCH_ONLY_EXECUTION.md](RESEARCH_ONLY_EXECUTION.md) defines current execution. Commercial Releases, SKU approval and product certification are not prerequisites. Missing data produces BLOCKED/NOT_RUN, not a restriction on independent software research.

## Current entrypoint and data scope

`.github/workflows/validation-extended-real.yml` is an explicit `workflow_dispatch` entrypoint requiring an exact 40-character `source_sha`. It does not subscribe to Release publication or scheduled commercial validation.

The only current profiles are `research-attribution-core`, `research-attribution-extended` and `research`. Their exact source roster and usage classes come from `validation/extended.datasets.lock.json`. The first two use attribution-reviewed research sources; the last includes additional sources subject to their specific research-use conditions. A profile name does not grant voice-use, transformation or redistribution rights. Preserve NonCommercial and other actual source restrictions; review the exact version and intended use rather than demanding unrelated commercial authorization.

Prepare approved data outside Git on an isolated runner labelled `self-hosted`, `linux`, `audio-validation`. The cleanup and source CI do not acquire corpora, execute models or publish private audio. The workflow resolves an empty `data_root` through `AUDIO_PIPELINE_LAB_DATA_ROOT` or `$HOME/audio-validation-extended`.

## Reproducible execution

1. `runner_preflight.py --role audio-validation` checks tools, data root, catalog and writable output against the exact source revision.
2. `extended_dataset_lock.py validate` checks the catalog. `prepare_extended_validation.py scan` and `verify` bind selected original files and their SHA256 values.
3. Build `ap_process_pcm` and `ap_build_info_dump` from that source; retain executable hashes, compiler identity and build information.
4. `build_extended_real_corpus.py` constructs explicit direct/derived cases from the bound sources. Preserve source ancestry; a derived recording is not a new independent speaker or blind sample.
5. Use the existing canonical `run_validation.py`, selected policy, source manifest and exact processor. Retain per-case metrics, failures and original evidence.

For a deliberately selected local attribution-core research scan:

```bash
python3 validation/tools/prepare_extended_validation.py scan \
  --catalog validation/extended.datasets.lock.json \
  --data-root /path/to/approved-acoustic-data \
  --profile research-attribution-core \
  --limit-per-dataset 24 \
  --output /tmp/extended-source-manifest.json

python3 validation/tools/prepare_extended_validation.py verify \
  --catalog validation/extended.datasets.lock.json \
  --data-root /path/to/approved-acoustic-data \
  --manifest /tmp/extended-source-manifest.json
```

This verifies real files; it is not evidence that data acquisition or acoustic evaluation has happened. Changed/missing source bytes, catalog drift and incompatible source-use classes must fail. The workflow defaults are 24 source entries per dataset, 24 direct cases and 16 derived cases; these are execution budgets, not measured coverage or quality guarantees. Change them only through an explicit bounded study design.

## Independent blind evaluation

`research-attribution-core` and `research-attribution-extended` use an independent `AP_VALIDATION_HOLDOUT_KEY` for scenario-stratified HMAC holdout, restricted by the workflow to 20% or 30%. Never publish the key or feed blind results back to optimizer selection. The `research` route follows its declared research policy; it must not impersonate a different profile's independent holdout.

Existing `validation-extended-real-core*.json` and `validation-extended-real-plus*.json` filenames are code references, not commercial permissions. Preserve SI-SDR, ERLE, clipping/DC/level, VAD precision/recall/FPR/FNR, speech/noise attenuation, p10 tails, scenario sample/pass rates and coverage requirements in the chosen policy. Do not rewrite data, relax thresholds, reuse exposed holdouts or overwrite failed outcomes to produce PASS.

## What the results establish

Separate source readiness, successful execution, acoustic threshold results, independent evidence and actual device measurements. Public/derived acoustic evaluation does not establish SSC305 CPU/RSS, thermal/power, sustained real-route behavior or final-AFE recording quality. Those dimensions need their own actual observations; absent measurements remain NOT_RUN. There is no universal product-certification or 72-hour prerequisite for other research.

Retired profile names, Release schedules and certification protocols remain recoverable in Git history, not current executable instructions. Public outputs may contain only the metadata, hashes and results permitted by source rights and privacy constraints. The Chinese companion is [EXTENDED_REAL_VALIDATION.zh-CN.md](EXTENDED_REAL_VALIDATION.zh-CN.md).
