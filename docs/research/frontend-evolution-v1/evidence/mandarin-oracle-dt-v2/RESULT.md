# FE-MANDARIN-ORACLE-DT-V2: bounded diagnostic completed, no promotion

## Admission and execution

After recovering the original artifact ZIP with its exact historical SHA256 a3ab7823fdcd7586c3b72eb214b5536dcfb7531fdf0b1611d49e1575a29b2c3d (not the differently packaged Library archive), both rebuilt baseline wrappers were executed under the approved historical private runtime. CALL and ASSISTANT each reproduced all ten required outputs byte-for-byte: seven Float32 taps, control.csv, final PCM and metrics JSONL. Only after both baseline checks passed did either candidate execute. Each candidate ran once. All four processes exited0, each produced629 frames without observer errors; no retry or tolerance change. Terminal source/input/ELF/package/runtime checks passed.

The run and analysis implementation were independently reviewed before execution. Execution took4.034180084s within180s; separate analysis took3.530921589s within30s. These are orchestration elapsed times, not CPU/p99/SSC305 performance measurements. Prior V1 failure and runtime preflight failures remain unchanged in their own evidence.

## Actual intervention

The sole intervention preserved original Activity state updates and far output, replacing DT output with `far && any(admitted_known_near_frame != 0)`. Both profiles changed DT from0 to429 frames; gate eligibility dropped551 to122. This is an offline waveform-support oracle, not a deployable/human VAD detector or a guaranteed quality upper bound.

## Observed common-span results

Fixed physical interval[0,100480), post-NS/AGC/final outputs[160,100640); no fitted alignment, normalization or tail flush. Results below are raw engineering-near-domain descriptive metrics, not CER/MOS, pure speech distortion or independent quality qualification.

| Metric | CALL baseline | CALL candidate | ASSISTANT baseline | ASSISTANT candidate |
|---|---:|---:|---:|---:|
| Noncanonical projection SI-SDR(dB) |5.8621201895|-0.9253840191|5.7260342936|-1.0887982022|
| Gain-sensitive error ratio(dB) |-4.7712578033|11.0805409964|-4.7152156988|12.9894251653|
| Final RMS |0.0060815973|0.0474963756|0.0060619530|0.0576047793|
| Final peak |0.0593566895|0.4015502930|0.0604858398|0.4719543457|

Candidate-minus-baseline projection deltas are−6.7875042086/−6.8148324958dB; error-ratio deltas are+15.8517987997/+17.7046408641dB. All13 windows,7 lanes,2 profiles,2 arms (364 measurement groups) are retained, including zero-reference nulls. Gate counts use629 unshifted frames; waveform common-span metrics use628 frames, not the same denominator.

Raw mic and AEC input remain unchanged. Changes already appear in AEC residual (common projection deltas−9.0209465166/−8.5997126282dB); later NS/RES and AGC also evolve downstream. This does not identify one module as sole cause. The intervention jointly changes downstream adaptation/protection/gain behavior, while raw near was not passed through HPF/BF, so cross-stage error is not separable source distortion.

## Decision

DIAGNOSTIC_ONLY_NO_PROMOTION. On this one engineered Mandarin utterance, inserting these known-near DT flags is not supported as an improvement. Do not promote this offline oracle or infer a production detector adjustment from it. No ASR/KWS/model call, paid compute, target experiment, product claim or production code change occurred. A next causal intervention, if authorized, needs an independent contract and cannot be chosen by silently relaxing this measurement or rewriting the historical failure.

## Reproduction

PLAN.json, freeze.sha256, scripts, exact original metric source, build manifests/definitions/flags, source copies, static library, actual ELF hashes, command receipts, native stdout/stderr, all inputs/outputs, baseline gate receipts, analysis and source/runtime hashes are retained. The original474MB ZIP and the separately archived official runtime closure are external hash-locked dependencies, not duplicated here. Run once under `timeout --signal=KILL 180s python run.py`; only after successful execution run `timeout --signal=KILL 30s python analyze.py`. Existing run-state/result guards forbid overwriting evidence. Historical local path dependencies must be materialized and hash-verified before replay; this archive is evidence, not an auto-running installer.
