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

Each event-bound receipt also contains integer `run_id` and `run_attempt`, taken
from strictly canonical nonzero GitHub environment identities. A later consumer
must compare both to the exact API run/attempt and the original artifact source;
an artifact name or the mutable `run.pull_requests[]` association cannot replace
that binding. Missing identities fail closed. A prior attempt's receipt does not
become evidence of a rerun, and earlier receipts are not rewritten to add fields.

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

## Actual protected-source M1 prerequisite, 2026-10-20

At 2026-10-20 12:59:55 UTC, the live M1 qualifier executed from clean protected
main `2f2ca4c283e700b4b89c3ccb293040aa39c81a49` and classified the actual same-repository
[Dependabot #714](https://github.com/jiying2007/audio-pipeline/pull/714) head
`8c8f28eaf13dc41a62247ed934f761d85403962b` against that exact base. The complete
actual and expected diffs agreed on 56 workflow files and 127 reviewed Action
pin replacements, with diff SHA256
`2183c40de9dccf5a17330d2f107cec2e890c62d47ae0eacd8760fb13eb21dab9`.
The earlier frozen 108-pin and 125-pin witnesses remain unchanged.

The exact-main prerequisite [Verify 39385063814](https://github.com/jiying2007/audio-pipeline/actions/runs/39385063814)
and [Release 39389019184](https://github.com/jiying2007/audio-pipeline/actions/runs/39389019184)
both completed successfully before this live probe. The Release run preserves
existing v2.3.55 source `37a1792861a89c815bec462f819f3deac7d29b09`; it does not create
a new release tag for this CI policy source.

The original stdout is reproduced byte for byte as the single JSON line below,
including its final newline: 1,539 bytes, SHA256
`b4550c0f9990713380a6fb143e9b0f3f1d1e2b306ebfba2b03c8e7d5e25c9cd8`.
This is the M1 nonmeasurement proof for those observed refs. It is not an M2
workflow positive, permission to skip a scientific job, or evidence about a
future main/head pair. The preceding negative receipt remains
`T1_ACTUAL_BOT_TREE_NOT_ADMITTED` / `BOT_PR_READ_UNAVAILABLE`; its three original
members do not encode an HTTP status, and are retained unchanged.

```json
{"action_supply_chain_attested":false,"actual_base_tree":"2574383b22513ca1d79ce307ac7fa3531dc75ccd","actual_bot_git_tree_checked":true,"actual_bot_tree":"4d478533f0578db955c9aca75cbc996f1551c687","actual_merge_base":"2f2ca4c283e700b4b89c3ccb293040aa39c81a49","automated_bypass_enabled":false,"bot_base_sha":"2f2ca4c283e700b4b89c3ccb293040aa39c81a49","bot_head_sha":"8c8f28eaf13dc41a62247ed934f761d85403962b","bot_patch_witness_sha256":"47ac0756f4989f619403f3689ce3fc305ec82469730da908559937ef03f86abb","decision":"T1_ACTUAL_BOT_TREE_CLASSIFIED_NON_MEASUREMENT_ONLY_NO_WORKFLOW_SKIP","expected_current_base_pin_diff_sha256":"2183c40de9dccf5a17330d2f107cec2e890c62d47ae0eacd8760fb13eb21dab9","file_count":56,"frozen_witness_content_diff_sha256":"c97935173e7a571f9a6631871c7d176be78679f100f3a67210731aa8d261e7dc","historical_witness_matches_current_diff":false,"observed_at_utc":"2026-10-20T12:59:55+00:00","pin_diff_sha256":"2183c40de9dccf5a17330d2f107cec2e890c62d47ae0eacd8760fb13eb21dab9","pin_replacements":127,"protected_main_sha":"2f2ca4c283e700b4b89c3ccb293040aa39c81a49","public_sdk_3x_admitted":false,"reason":"ACTUAL_TRUSTED_GIT_PIN_SCOPE_ONLY","review_id":"2026-10-20","schema_version":1,"scientific_experiment_executed":false,"ssc305_or_physical_hil_qualified":false,"trusted_classifier_git_blob":"2c3bafe13f9f6cb036bdd01328dd4f12fd336b4e","trusted_classifier_sha256":"fcce117736d32a2cafd3c95fc93a27f906f40b64f632116cd90e8ba1759d68cb","trusted_qualifier_sha256":"6d080c55e0334b96279f826e1615802cf1a8b58d57c1d9c8900900560d25ffd7"}
```

An independent readback compared the original receipts, real Git trees, T0
actual/expected results and two current public API snapshots. It confirmed the
same 56-file/127-pin scope, stable base/head and strict main protection; it did
not rerun the probe or an experiment. Its 4,940-byte report has SHA256
`4a498fe2ed9512982bb0a3a819da7bb929b2c53cfbe084c3c89512c14767bb69`.
All original M1 nonpromotion flags remain false. New protected source and
workflow integrations still require their own exact-source execution evidence.
