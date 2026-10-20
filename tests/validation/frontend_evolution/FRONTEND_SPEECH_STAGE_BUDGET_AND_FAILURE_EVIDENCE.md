# Official speech-source stage budget & durable failure evidence
# 官方语音来源超时预算与失败证据保留

**Independent preregistration:** [#774](https://github.com/jiying2007/audio-pipeline/issues/774). This change is an operational CI fail-closed improvement, **not an acoustic algorithm result, dataset replacement or gate waiver**.

## Observed incident / 观察

On [Verify 38879901657](https://github.com/jiying2007/audio-pipeline/actions/runs/38879901657), the `frontend-speech` [job 116919844895](https://github.com/jiying2007/audio-pipeline/actions/runs/38879901657/job/116919844895) entered its official source stage after FFmpeg setup and produced no further visible source progress. At the fixed 20-minute *job* limit GitHub cancelled the process. The subsequent unconditional `upload-artifact` attempted `fe-speech/source/source-failure.json` plus positive evidence, but nothing existed, resulting in a second upload error. The exact cause of the blocked source read is **not proven**; it cannot be relabelled as failed BF, misattributed to source licensing, or treated as successful acoustic work.

## Bounded remedy / 修复

Existing `speech_source.py` and `speech_spatial.py` science logic, official LibriSpeech URL `https://www.openslr.org/resources/12/dev-clean.tar.gz`, pinned MD5 `42e2234ba48799c1f50f24a7926300a1`, selection, FFmpeg lossless decode, negative controls and same-source bounded three full transport attempts remain **unchanged**.

- A separate first-party wrapper `speech_source_stage_budget.py` launches the exact original `speech_source.py` (no alternate URL/command from CI arguments) in a separate process group. The source acquisition/extraction stage has a **30-minute hard wall budget**, including official retries, and the GitHub `frontend-speech` job has a **45-minute** hard budget. This reserves up to 15 minutes after source-stage timeout/success for science/cleanup/failure Artifact while remaining finite; the difference is not a guarantee of science completion if later steps independently exceed their budget.
- On source-stage timeout the wrapper explicitly TERM/KILLs the source process group, waits for it to exit and writes a small **negative-only** `source-failure.json` with source URL/MD5, max retry count, stage limit, elapsed wall bound, failure reason and zero shipping/acoustic authority. A nonzero worker exit leaves its original source-failure receipt intact or creates a bounded fallback. A zero-exit worker without `source-receipt.json` still fails closed. The wrapper never replaces an existing receipt or treats partial downloaded bytes as official corpus evidence.
- The unchanged `if: always()` existing 30-day Artifact path now finds a first-party failure marker for **controlled source-stage failures**, rather than losing all reason evidence when an enclosing job deadline SIGKILLs the worker. An external runner failure/host SIGKILL before the wrapper can write is still unhandled and must remain explicitly unverified, not magically claimed recovered.
- New offline `test_speech_source_stage_budget.py` tests a deliberately sleeping child timeout, nonzero exit, child-written failure preservation, missing success receipt, declared success receipt, prior output no overwrite and finite deadline controls, without any network calls, corpus download or genuine audio score substitutions. It runs in the Docs Gate and speech workflow.

## Exact acceptance / 验收边界

No source substitution, no `continue-on-error`, no edit to mandatory Verify dependency graph, no skipped speech validation, no lower quality threshold and no free-standing hardware claim. Any genuine source deadline remains a **red frontend-speech job and red required summary** with durable source failure metadata. The ordinary valid real-speech path still performs full pinned-source hash validation, actual spatial effect calculations and FIR counterfactuals on **the same original official corpus**.

Qualify only after exact current Draft PR HEAD full Verify `summary=success` and external four-member positive evidence, active strict Ruleset 21804005, zero unresolved review threads, expected-head Squash, distinct pushed-main Verify/Release/convergence and source-bound Artifact. Do not close [B0 #772](https://github.com/jiying2007/audio-pipeline/pull/772) by waiving its already-observed canceled speech job. If the repair merges first, B0 must rebase and requalify **all** new-head checks.

This is a hosted research CI durability measure, not proof of uninterrupted LibriSpeech availability, real 4-mic gain, SSC305 memory/10ms budget, HIL or Product Certification.
