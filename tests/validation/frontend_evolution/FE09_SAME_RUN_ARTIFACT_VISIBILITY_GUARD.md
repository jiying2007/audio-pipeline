# FE09 exact-run Artifact visibility / 同运行证据可见性门禁

**Independent preregistration:** [#779](https://github.com/jiying2007/audio-pipeline/issues/779). Research-only CI safety improvement, NOT an audio DSP, SDK or science result.

## Incident / 问题

On protected B1-S0 main [Verify 38928394697](https://github.com/jiying2007/audio-pipeline/actions/runs/38928394697) attempt 1, the original four-target C executable successfully uploaded/finalized exact-run [Artifact 12057283554](https://github.com/jiying2007/audio-pipeline/actions/runs/38928394697/artifacts/12057283554) (5,645 B), but the immediately following pinned `actions/download-artifact` step returned `Artifact not found`. Artifact listing and independent connector download later confirmed its bytes remained available. This was an observable upload→readback visibility failure, **not proven GitHub provider root cause** or an audio test failure. One exact same-SHA targeted job retry produced independently downloaded/rehashed [Artifact 12062966967](https://github.com/jiying2007/audio-pipeline/actions/runs/38928394697/artifacts/12062966967) and complete summary success; same-source Release [38940767664](https://github.com/jiying2007/audio-pipeline/actions/runs/38940767664) succeeded. Issue #776 was closed as a software SPSC research stage but #779 remains for reliability hardening.

## Fail-closed remedy / 有界恢复

The B1-S0 `quality.yml` job now names its existing pinned `upload-artifact@...v7.0.1` step and reads that step's **actual output artifact-id**; no guessing artifact IDs, no manual upload/reupload or cross-run fallback.

Before the **unchanged pinned** `download-artifact@...v7.0.0` action, `fe09_same_run_artifact_visibility.py` performs up to **8** read-only metadata attempts at the official GitHub API, each with a **10 second** request timeout and at most **2 seconds** between attempts (a finite cap; an unhealthy API still leaves the required job red). The URL is constructed solely from the fixed GitHub API host, exact `GITHUB_REPOSITORY` and the uploading step's artifact ID; the token is never printed.

The API must present exactly the original **artifact-id**, run-scoped filename `frontend-fe09-t2b-b1s0-owner-spsc-<run-id>`, matching workflow_run.id, unexpired status, positive size ≤1MiB and SHA256 digest; mismatches, 403/401/429, malformed/duplicate JSON keys or unexpected redirects **fail immediately**, without trying a different run, URL, mirror, artifact name or any user-controlled endpoint. Only short 404/502/503 visibility transitions are retried with a hard cap; exhausted requests **fail**.

Crucially, **metadata visibility is NOT artifact integrity**. The original pinned download is still mandatory, followed by its separate four-member `SHA256SUMS`/receipt/source and no-product verdict check. No `continue-on-error`, waived check, new network resource, altered audio corpus, unbounded waiting or skipped code path. The artifact failure receipts and original B1-S0 C test/ABI remain unchanged.

New offline no-network unit tests inject 404→200, 503→200, forever 404, immediate 403/401/429, source/run/name/ID mismatch, expired/oversize/wrong SHA, redirect, malformed/duplicate/oversize JSON and invalid retry budgets. They run in the fast Docs Gate.

## Admission

Only latest-head full Verify `summary=success`, strict active protected main Ruleset 21804005, zero unresolved review threads, expected-head Squash, distinct new-main Verify+same-SHA Release/convergence success and complete source-linked Artifact readback can close #779. No shipping 2.x DSP, `src/`, public installed SDK, legacy APD2/CMake or immutable I025–I040 changes. B1-S1 #778, true hardware/SSC305/HIL #58 and durable APX3 remain separately qualified.

One future absence visible after eight attempts **remains a regression**: do not mark a broken GitHub storage service healthy or fabricate a passing source receipt.
