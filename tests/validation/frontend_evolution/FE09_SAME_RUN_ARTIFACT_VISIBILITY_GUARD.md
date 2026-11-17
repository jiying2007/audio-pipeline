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

## 2026-10-23 A1/T3-S1 scheduling-state correction

On diagnostic PR #832 head `06ff1e59681178b1ef4f11cfb46615a757b77bb4`,
[Verify 39944956605 / job 120385811422](https://github.com/jiying2007/audio-pipeline/actions/runs/39944956605/job/120385811422)
completed scientific verification and uploaded Artifact 12497726986, then refused
the run metadata at `A1_RUN_ATTEMPT_REPOSITORY_OR_HEAD_MISMATCH:STATUS`.
An earlier exact-attempt response for this same run was `queued`/`null` while
multiple jobs were already running. The failed response's actual status value
was not retained; the older main failure's generic reason does not identify its field.

The old `in_progress`-only premise was invalid for workflow-level scheduling.
The shared A1/T3-S1 witness now permits only string `queued` or `in_progress`
with an explicitly present JSON-null `conclusion`; all other states, missing
fields or non-null conclusions refuse immediately, without retry. GitHub's
[official workflow-runs REST example](https://docs.github.com/en/rest/actions/workflow-runs)
also includes `queued`/`null`. Scheduling is not artifact identity: exact run,
attempt, head, repository IDs, actual quality execution source, original upload
ID/name/digest and creation-time checks remain mandatory, with unchanged request
budgets, pinned download and scientific readback. Fixed field suffixes reveal no
response values. The original failed run/artifact remain evidence, not a pass.

## 2026-11-10 T3-S1 attempt-scoped names / 保留重跑证据

At PR #928 head `44b2e22597a45171fdf83d657856958ff1af4720`,
[Verify 42847765892 attempt 1 / job 129942358773](https://github.com/jiying2007/audio-pipeline/actions/runs/42847765892/job/129942358773)
completed T3-S1 scientific checks and uploaded Artifact `13778683373`, but the
pinned downloader reported that its exact ID was unavailable. The one bounded
failed-job rerun, [attempt 2 / job 129964573573](https://github.com/jiying2007/audio-pipeline/actions/runs/42847765892/job/129964573573),
again completed those checks and uploaded Artifact `13782800825`. Its visibility
witness correctly rejected `A1_ARTIFACT_NAME_OR_ID_NOT_UNIQUE`: both uploads had
the same run-only name. Neither failure is relabeled as successful readback.

The narrow transport fix names new T3-S1 uploads
`frontend-fe09-t3s1-compact-handoff-<run-id>-attempt-<run-attempt>` and binds the
witness to that exact name before making any API request. The suffix must equal
the explicit positive integer run attempt; only T3-S1 accepts this new form.
Historical run-only T3-S1 names retain the original strict witness for
compatibility, including rejection of duplicate names. The current workflow
always supplies the new form for both upload and witness.

旧 attempt 原件保留，不删除、不覆盖、不放宽重复检查。列表仍完整分页读取，并按当前
上传步骤返回的 ID 或精确名称匹配；同名不同 ID、同 ID 错名仍失败。先前 attempt 的
不同名称可共存，但不能被选为本次上传原件。准确 run/attempt、仓库、head、实际 quality
源码、创建时间、digest、大小和未过期条件以及原八请求/两秒/响应上限均不变。

Offline tests replay all existing refusal controls with both naming forms and
cover old-attempt coexistence, cross-page enumeration, current-name collisions,
wrong ID/name/attempt/run and non-T3-S1 suffix rejection. Pinned upload/download,
four-member scientific readback and R1–R9 source pins remain unchanged. New
exact-head CI and independent readback are still required; these metadata tests
do not establish scientific, acoustic or device qualification.


## 2026-11-10 A1 strict snapshot restart / 严格完整快照重试

Frozen base: `43197447f5821abae06cab81b8c24761f4a68f84` (includes #932).
Concrete failure: PR #933 head `1a3ca400cdc62e6dd1caf98995955af5644d96da`,
[Verify 42909847685 / A1 job 130159135728](https://github.com/jiying2007/audio-pipeline/actions/runs/42909847685/job/130159135728),
reported `A1_ARTIFACT_LIST_INCOMPLETE_OR_CHANGED` after upload `13807331430`
(37,898 bytes, SHA256 `4e347ae81a3f6701129d93ed2237b2cc2480243283acd0ebd1d3f693eb376e00`).
The response pages were not retained, so neither a changed total across pages
nor a single-page total/row mismatch is established as the root cause. That run
remains failed, and this change does not rewrite or delete its artifact.

Hypothesis: concurrent publication can expose a transient inconsistent REST
list. A1 alone now discards every accumulated row and restarts at page 1 after
the existing two-second pause. The run-attempt lookup, every page, HTTP retry
and snapshot restart share the original **eight total requests**; pagination
and restarts never reset it. Request timeout (10 seconds), list response cap
(256 KiB), other metadata cap (64 KiB), page/total bounds and job deadline are
unchanged. Archive readiness retains its separate existing budget and still
runs only after complete list admission.

Acceptance still requires a complete enumeration with consistent total and
exact page sizes, unique IDs and exactly one selected ID/name, plus unchanged
run/attempt/head/repository/execution-source/time/digest/size/expiration checks.
Observed invalid IDs, duplicates, name collisions and selected-artifact identity
conflicts refuse before any restart. No row from a discarded snapshot can
qualify a later empty snapshot. Exhaustion never admits a partial list; an
inconsistent final page retains `A1_ARTIFACT_LIST_INCOMPLETE_OR_CHANGED`.
Non-A1 stages keep immediate refusal on inconsistent lists. Pinned download,
archive readiness and all scientific readback commands remain unchanged.

离线元数据夹具覆盖：单页不完整后恢复、跨页 total 变化后从第一页重读、丢弃旧匹配项、
八请求耗尽、HTTP 与快照共享预算、冲突/重复/坏行立即拒绝，以及其它阶段不扩展重试。
这些仅是传输控制测试，不是新科学、声学或物理设备证据。原失败保持 FAIL；新代码仍须
独立审查、准确 head 的必需 CI/summary 和保护合并后的 fresh-main 检验。
