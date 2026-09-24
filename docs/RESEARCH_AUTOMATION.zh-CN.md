# I015 证据自动收尾

本入口只处理已经执行完的 I015：run `35994848668`、attempt `1`、artifact
`10805915721`。它不是实验调度器，不会启动或重跑诊断，也不会改变四条 lane、
fresh seeds、VAD 常数、阈值或研究预算。

## 无人值守的正常路径

1. 本收尾实现通过 PR 门禁合入 main；精确 main 的 Verify/summary 成功后，
   `I015 Evidence Finalization` 自动读取固定的原始 artifact。
2. 验证来源仓库、工作流、source/infra、ZIP 摘要、包内全部九项哈希、JSON、
   mirror、权限标志、逐 seed/分域计数及归因分组；不执行包内任何内容。
3. 自动创建唯一分支 `automation/i015-evidence-35994848668` 和归档 PR。
   保存十份原始文本证据、规范闭环 JSON 和归档入口；过了 artifact 保留期，
   Git 中的原始文本证据依然可读。
4. Verify、Program Archive、Research Optimization、Research Algorithm Parameter
   Optimization 完成时触发复核。只有精确 head/base、全部实际检查、required summary、
   固定文件路径/内容以及 GitHub 的 clean mergeability 同时满足，才请求普通 squash merge。
   不使用 admin bypass，不修改分支保护，不要求打开仓库级 auto-merge 开关。
5. 合并后的精确 main 再次通过 Verify/summary 后，自动在 #406 写入一次性完成回执。
   后续重复事件只校验并退出，不重复开 PR、不覆盖已有回执。

## 凭证与权限

只读取证使用 `GITHUB_TOKEN`。创建 PR、提交归档和普通合并只使用
`RESEARCH_AUTOMATION_TOKEN`，不再回退到 `REPOSITORY_ADMIN_TOKEN` 或
`REPOSITORY_GOVERNANCE_TOKEN`。后两者继续只服务原有治理安装/审计；
本收尾代码不调用 Administration 接口，也不自动扩大任何令牌权限。
完成评论由 `GITHUB_TOKEN` 的 Issues 写权限发布；写权限不授予 PR 检查 job。

当前实现直接读取仓库 secret。应配置仅授权 `jiying2007/audio-pipeline` 的有效
fine-grained PAT，授予 Contents 与 Pull requests 的 Read and write；只读取证
另用 `GITHUB_TOKEN`，发布令牌不需要 Administration 或 Actions 写权限。
不要把短期 GitHub App installation token 当成长效 secret 保存；采用 App 时应另行
接入逐次签发机制，本实现尚未提供该机制。PAT 的有效期和轮换需按实际基础设施管理。

缺少发布 secret 时会报告 `BLOCKED_AUTOMATION_CREDENTIAL`；凭证存在但 GitHub
拒绝认证时，报告 `401 / INVALID_CREDENTIAL`。401 不能被误判为 Contents 权限
不足，也不能仅凭状态码断定是过期、撤销还是配置值错误。403 则需要检查该接口的
权限、仓库授权和相关组织策略。原始取证仍保存在 finalizer artifact 中。
默认 `GITHUB_TOKEN` 创建的 PR 工作流需要人工批准，因此不把它作为无人值守发布
的静默降级路径。凭证不应粘贴到聊天、日志或仓库文件。

### 已验证的阻塞与恢复

2026-09-24，#409 合并后的精确 main `4801f0543080791e6100cdbcdeeb15771a42fc49`
通过 Verify `36002648022` / summary 后，自动收尾 run `36003168226` 在
`POST git/trees` 得到 `401 / INVALID_CREDENTIAL`。失败 artifact `10809142280`
的 ZIP SHA256 为 `82c06da7c3457fa64ac1d4ccc896ff5ef447cc2e1f0d3989b2e5285011467598`；
其中原始 I015 ZIP 仍与冻结摘要一致。旧工作流没有记录所选 secret 的名称，
不能从这份错误反推出当时选择了哪一个 secret，更不能宣称凭证已经修好。

有权限的仓库管理员需在 GitHub 的 Actions repository secrets 中配置/替换
`RESEARCH_AUTOMATION_TOKEN`。已认证的本地 `gh` 也可交互式提交（不把值写入命令）：

```bash
gh secret set RESEARCH_AUTOMATION_TOKEN --repo jiying2007/audio-pipeline
```

secret 更新不会自动产生本工作流监听的事件。配置后，通过 Actions 页面运行一次
**I015 Evidence Finalization**（`i015-evidence-finalization.yml`，ref 为 `main`），
或使用已支持的 API 入口：

```bash
gh api --method POST \
  repos/jiying2007/audio-pipeline/actions/workflows/i015-evidence-finalization.yml/dispatches \
  -f ref=main
```

这是只读取既有证据的收尾恢复，绝不是重新触发 I015 诊断。配置有效后，正常归档
和门禁推进无需逐轮人工操作；凭证失效仍是需要基础设施修复的异常，不能自动绕过。

## 失败恢复与停止边界

可以重试的是 **I015 Evidence Finalization**；它只读取同一个已消费 run/artifact。
绝不能重跑 **Research I015 VAD Upstream Consumption Decomposition v1**。
同一固定归档分支和精确内容保证重复取证不重复创建 PR；已经关闭的 PR、分支漂移、
证据不匹配或 main 变化会停止，不强推、不悄悄重建谱系。等待门禁不是诊断失败。

`CLOSED_DIAGNOSTIC_ONLY` 仅代表原始 I015 证据已校验并按审核结论归档。
它不允许选 lane、重加权 guard/blend、改阈值、消耗候选/确认预算或发布产品。
包内没有 raw frame trace、音频或 probe 二进制，不能声称独立重算 AUC 或核验缺失二进制。

未在此实现的能力：新实验自动授权/调度、一般代码修复的自动合并、HIL 与产品认证。
每条新研究线仍须有独立冻结契约；本控制器不会把 I015 证据变成新的训练/选型数据。

## 实现与可复核依据

冻结身份和审核解释：`.github/program/i015-finalization.json`。
执行与校验：`.github/program/i015_finalize.py`。
负例测试：`tests/validation/test_i015_finalize.py`。
工作流：`.github/workflows/i015-evidence-finalization.yml`。

GitHub 原生事件、令牌与权限语义：
- https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#workflow_run
- https://docs.github.com/en/actions/concepts/security/github_token
- https://docs.github.com/en/rest/pulls/pulls#merge-a-pull-request
