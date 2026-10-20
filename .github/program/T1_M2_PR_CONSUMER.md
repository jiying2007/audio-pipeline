# T1-M2 direct PR maintenance consumer

## Defect and authority

This is the independent PR consumer preregistered by #758, after the separately
reviewed T0/M0/M1 current-base contract in T1_20261020_PIN_REVIEW.md. The current
source work is based on e3672ffe16e4c9d42a100e7712b9bbd3d8338545 plus the independent
M1 source-review commit 40cbcafe52ef7ecf35e4376f3f7083c6493f2413.
Source code and offline tests are not a protected-main M1 positive receipt.

Three existing research workflows currently classify the same-repository
Dependabot #714 workflow-pin proposal as if it were an acoustic experiment.
Only independently reviewed exact old/new Action SHA replacements are eligible
for the explicit `SCIENCE_NOT_EXECUTED_NON_MEASUREMENT_MAINTENANCE` decision.
The old failed research runs remain failed. Original scientific steps, inputs,
thresholds, artifacts and guards remain necessary for every other decision.

## Exact eligibility

The helper must be executed from the exact PR base checkout, with contents:read
and checkout credentials disabled. It requires its own bytes/mode from that
protected base, the separately protected M1 qualifier/T0/review observation,
an open non-draft same-repository #714 by immutable Dependabot actor ID/type,
the current main/base/head, complete real Git pin diff, and the reviewed policy.

It also binds the direct `pull_request` event and workflow file, the synthetic
event commit's two exact base/head parents and its tree, and rechecks the real
public PR/ref snapshot after event binding. No code from bot HEAD is checked
out, sourced, imported or executed by the qualifier.

The caller workflow context matters: GitHub documents that a reusable workflow
inherits its caller's `github` context. The helper compares the exact
`GITHUB_WORKFLOW_REF` to the explicitly selected direct workflow file.
Thus a nested PCR02 -> Real AEC `workflow_call` cannot inherit PR admission.
Push, dispatch, pull_request_target, foreign/fork/wrong-actor, stale source,
unknown policy, changed consumer code, merge-parent/tree drift and unreadable
source all request the original research branch.

Source:
https://docs.github.com/en/actions/reference/workflows-and-actions/reusing-workflow-configurations

The bounded receipt's outer `skip_measurement=true` /
`automated_bypass_enabled=true` describe only this separately approved M2
nonmeasurement consumer. The nested M1 observation remains
`automated_bypass_enabled=false`; M1 alone does not skip anything.
Neither layer calls a skipped experiment an acoustic PASS. A negative receipt
has both outer fields false and leaves all existing science guards active.
Event contents, authentication data and signed download URLs are never emitted.

## Staged integration

This helper commit changes no research workflow. Protect and verify it first.
Before connecting a consumer, independently obtain a fresh protected-main M1
positive for the exact rebased bot proposal.

Connect each existing research workflow in its own reviewed change so the
original narrow per-experiment PR path guards can execute. Add one contents:read
maintenance job that checks out exact PR base and writes a small bounded receipt.
An original scientific job may skip only when that job succeeded and its explicit
`skip_measurement` output is exactly `true`. Negative, absent, failed or malformed
admission cannot suppress science. Workflow cancellation remains cancellation.

The dEchorate workflow's old frozen-base-to-current-head scope check is a
separate M3 temporal-scope issue. Keep its original manifest/predecessor lineage
and scientific execution. Qualify the new event before/after range and any push
consumer independently; M2 does not authorize a main-push skip.

After connecting all PR consumers and independently qualifying M3, rerun the
exact live #714 head/base. Archive the new neutral maintenance receipts and the
preserved old failures separately. CodeQL execution, artifact upload/readback,
required Verify summary, strict expected-head protected merge and distinct new
main verification remain required. No release version, DSP or physical evidence
changes follow from this helper.

## Local verification

`python3 .github/program/workflow_pin_pr_consumer.py --self-test` uses only
offline metadata and actual tiny local Git fixtures. It rejects non-PR and
reusable-call contexts, actor/ref mismatches, stale or incomplete M1 results,
candidate consumer overrides, nonmerge/wrong-parent/wrong-tree event commits.
These tests are not real GitHub consumer execution or acoustic evidence.

中文边界：本提交只加入独立受保护的消费者源码及负例，还未修改三个科学工作流。
历史 108-pin 见证和本次 125-pin 观察均不授权未来候选代码；实际规则始终从当次
protected base 全量推导，并绑定真实 bot 和事件 Git 树。M2 仅允许直接 PR 的已审
依赖维护显示“未执行科学实验”，不扩展到 workflow_call、push 或任何算法变更。

