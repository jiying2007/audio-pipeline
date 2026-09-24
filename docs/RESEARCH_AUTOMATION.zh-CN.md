# I015 证据自动收尾

本入口只处理已经执行完的 I015：run `35994848668`、attempt `1`、artifact
`10805915721`。它不是实验调度器，不会启动或重跑诊断，也不会改变四条 lane、
fresh seeds、VAD 常数、阈值或研究预算。

## 已关闭实验的执行入口

I015 已由归档 PR #411 和 #406 的原生机器人回执正式关闭。原诊断运行
`35994848668` 只消费一次；后续维护 run `36031859001` 已实际返回
`ALREADY_CLOSED_NOOP`，没有生成新证据或改写回执。

原研究工作流现在只保留 PR 契约、自测和 `-Werror` 编译检查；
`workflow_dispatch` 与整个 `diagnose` job 已退役，不再查询 Actions 历史来判断
已经关闭的实验是否还能启动。可清理的运行记录不是持久预算凭证；本次修复没有
删除任何历史 run、artifact、归档数据或研究源码，也没有重新执行诊断。

完整的已消费工作流保存在 `tests/validation/data/i015-consumed-workflow.yml`，
Git blob 仍为 `1bf5717bf4bb02f3847606a6d7cba7c61bde70f1`，位于 Actions 执行
目录之外，仅作为历史测试数据。原 18 项 one-shot 测试继续针对这个冻结版本运行，
不执行其中的 shell、音频生成器或 probe。新的退役检查解析 YAML 数据并拒绝恢复
手动/定时/事件执行入口、增加或改名诊断 job、改变契约步骤、权限或闭环文件。
独立 Finalization Contract 同时在 PR 与 main 对这些边界进行校验。

仍可重复运行的是 `i015-evidence-finalization.yml` 的幂等证据收尾；已关闭时只
核验 Git 中的原始归档后返回 no-op。它没有新实验、换 seed、选 lane 或发布授权。
历史提交和旧运行保留用于审计，不应从历史 ref 重新调度已消费的研究工作流。

## 无人值守的正常路径

1. 收尾实现通过 PR 门禁合入 main；精确 main 的 Verify/summary 成功后，
   `I015 Evidence Finalization` 自动读取固定的原始 artifact。
2. 验证来源仓库、工作流、source/infra、ZIP 摘要、包内全部九项哈希、JSON、
   mirror、权限标志、逐 seed/分域计数及归因分组；不执行包内任何内容。
3. 自动创建唯一分支 `automation/i015-evidence-35994848668` 和归档 PR。
   保存十份原始文本证据、规范闭环 JSON 和归档入口；过了 artifact 保留期，
   Git 中的原始文本证据依然可读。
4. 归档等待期间 main 可能合入基础设施修复。恢复入口先核验当前 main 的完整
   Verify/summary、归档 PR 的仓库/分支身份、全部新增文件路径和原始 Git blob 哈希。
   只有内容仍是原先那十二份材料、没有冲突且 head 没有漂移，才通过 GitHub 的
   `update-branch` 接口把 main 正常合入归档分支。请求绑定 `expected_head_sha`，
   不强推、不重建 PR、不执行 PR-head 代码，更不把这次更新当成合并到 main。
5. 新 head/base 必须重新运行全部适用门禁。Verify、Program Archive、Research
   Optimization、Research Algorithm Parameter Optimization 与独立收尾契约完成时
   触发复核。只有精确 head/base、全部实际检查、required summary、固定内容以及
   GitHub 的 clean mergeability 同时满足，原 finalizer 才请求普通 squash merge。
   不使用 admin bypass，不修改分支保护，不要求打开仓库级 auto-merge 开关。
6. 合并后的精确 main 再次通过 Verify/summary 后，自动在 #406 写入一次性完成回执。
   回执延迟时，分别绑定原归档 merge SHA 与当前已验证 main；两者都须通过精确
   Verify/summary，原归档合并必须是当前 main 的祖先，原 PR 与当前 Git 证据均须一致。
   后续重复事件校验已归档内容，不重复开 PR、不覆盖已有回执。

## 归档与产品版本的边界

归档不是产品代码修改，但不能仅凭 `result.json` 之类的文件名认定它无需升版。
`ci_impact.py` 仅接受以下同时成立的原始收据复制：

- 验证区间的可信 base 已有 `.github/program/i015-finalization.json`，且该登记文件
  在 base/head 间逐字节不变；PR 不能靠同一轮新增或修改登记来批准自己。
- 十份文件完整出现，目录与登记的 run ID 对应，全部为新加的 `100644` 普通文件，
  每份内容的 SHA256 等于可信 base 的登记值。
- 只排除这十份原始收据的产品升版要求；未知文件、嵌套文件、可执行文件、软链接、
  修改/删除既有归档以及混入的产品源码、验证器、正式策略等仍保持原有约束。

CI 矩阵与独立归档内容校验没有被缩减。当前完整归档 PR 仍运行完整适用检查；
main 推送仍强制完整 Verify。不为了存档制造一个新的产品版本。

## 凭证与权限

只读取证使用 `GITHUB_TOKEN`。创建 PR、提交归档、更新归档分支和普通合并只使用
`RESEARCH_AUTOMATION_TOKEN`，不回退到 `REPOSITORY_ADMIN_TOKEN` 或
`REPOSITORY_GOVERNANCE_TOKEN`。治理凭证继续只服务原有治理安装/审计。
完成评论仍由 `GITHUB_TOKEN` 以 `github-actions[bot]` 身份发布。跟踪对象 #406 是
PR，因此可信 main 的收尾 job 显式授予 Issues 与 Pull requests 写权限；Contents、
Actions 保持只读。独立 PR 契约检查仍只读，发布提交仍必须使用专用发布身份。

仓库 secret 应为仅授权 `jiying2007/audio-pipeline` 的有效 fine-grained PAT，
具有 Contents 与 Pull requests 的 Read and write。发布令牌不需要 Administration
或 Actions 写权限。GitHub App 短期安装令牌不应作为长效静态 secret 保存；逐次
签发机制不在本实现范围内。凭证有效期和轮换属于基础设施管理，值不能写入聊天、
日志或仓库文件。默认 `GITHUB_TOKEN` 创建/更新的 PR 工作流需要批准，因此不把它
作为无人值守发布的静默降级路径。

缺少发布令牌时报告 `BLOCKED_AUTOMATION_CREDENTIAL`；认证被拒绝时可能报告
`401 / INVALID_CREDENTIAL`，不能仅凭状态码判断具体过期、撤销或配置值错误。
403 需要核验接口权限、仓库授权和相关策略。失败时仍保留原始取证材料。

### 已验证的历史与恢复入口

2026-09-24，#409 合并后的收尾 run `36003168226` 在 `POST git/trees` 得到
`401 / INVALID_CREDENTIAL`。失败 artifact `10809142280` 的 ZIP SHA256 为
`82c06da7c3457fa64ac1d4ccc896ff5ef447cc2e1f0d3989b2e5285011467598`。
#410 移除治理凭证回退后，run `36005126369` 明确报告发布令牌不可用。

管理员配置专用 secret 后，run `36013668544` 已成功创建归档 PR #411，证明归档
创建的认证问题已解除；这不等于合并或完成回执已成功。#411 原 Verify
`36013704126` 因原始收据被错误识别为产品发布变更而失败。保留该失败，不通过
升版、改证据或重跑诊断隐藏它。恢复实现须经独立 PR 和精确主线验收后生效。

#412 合入并通过主线验收后，原生恢复已更新 #411；其新 head 的 Verify
`36022590607` 成功。收尾 run `36023132286` 已自动合并 #411 至
`4ec161ed7bdad80a22f5398fa1282e186a319317`，随后主线 Verify `36023171151` 成功。
最后的 run `36023667105` 在 `POST issues/406/comments` 遇到
`403 / INTEGRATION_PERMISSION_DENIED`；失败 artifact `10819360070` 的 SHA256 为
`477ecf493c17dc4495e162d25b9c9eeda82ec76d485c3b5d225bb6f766894f19`。
这次失败发生在回执评论，而不是归档发布或算法验收。补齐可信 job 的 PR 评论权限，
并以原始归档合并提交为身份恢复回执；不能把后来的修复提交冒充归档 merge SHA。

基础设施凭证确需轮换时，可在本地已认证的 `gh` 环境交互式设置：

```bash
gh secret set RESEARCH_AUTOMATION_TOKEN --repo jiying2007/audio-pipeline
```

secret 更新本身不会触发收尾事件。需要主动恢复时，只运行这个收尾工作流：

```bash
gh workflow run i015-evidence-finalization.yml \
  --repo jiying2007/audio-pipeline --ref main
```

## 失败恢复与停止边界

可以重试的是 **I015 Evidence Finalization**；它只读取同一个已消费 run/artifact。
绝不能重跑 **Research I015 VAD Upstream Consumption Decomposition v1**。
`ARCHIVE_BRANCH_UPDATE_REQUESTED` 表示等待新 head 的独立验收，不是正式关闭。
已关闭的 PR 不重建；内容漂移、冲突、draft、凭证故障和请求前 main 变化均不得
自动合并。纯粹落后于已验证 main 的原样归档分支可按上述受限流程更新。

`CLOSED_DIAGNOSTIC_ONLY` 仅代表原始 I015 证据已校验并按审核结论归档。
它不允许选 lane、重加权 guard/blend、改阈值、消耗候选/确认预算或发布产品。
包内没有 raw frame trace、音频或 probe 二进制，不能声称独立重算 AUC 或核验缺失二进制。

未在此实现的能力：新实验自动授权/调度、一般代码修复的自动合并、HIL 与产品认证。
每条新研究线仍须独立冻结契约；本控制器不会把 I015 证据变成新的训练/选型数据。

## 实现与可复核依据

冻结身份和审核解释：`.github/program/i015-finalization.json`。
原执行与校验：`.github/program/i015_finalize.py`，其合并门禁保持独立。
受限分支恢复入口：`.github/program/i015_archive_recovery.py`。
版本分类：`scripts/ci_impact.py` 的 `verified_archive_paths`。
原负例：`tests/validation/test_i015_finalize.py`。
新增真实 Git 元数据与分支恢复测试：`tests/validation/test_ci_archive_receipts.py`、
`tests/validation/test_i015_archive_recovery.py`。
延迟回执身份、重复事件与权限测试：`tests/validation/test_i015_receipt.py`。
工作流：`.github/workflows/i015-evidence-finalization.yml`。

GitHub 原生事件、令牌与权限语义：
- https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#workflow_run
- https://docs.github.com/en/actions/concepts/security/github_token
- https://docs.github.com/en/rest/pulls/pulls#update-a-pull-request-branch
- https://docs.github.com/en/rest/pulls/pulls#merge-a-pull-request
- https://docs.github.com/en/rest/issues/comments#create-an-issue-comment
