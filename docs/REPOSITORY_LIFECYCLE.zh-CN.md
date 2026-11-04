# 仓库生命周期

本文定义纯技术研究仓库生命周期：实验、独立验证、受保护合并、可复现证据、可选真机实验与历史归档。旧商业发布与产品认证流程仅属不可变历史证据，不是当前操作指引。

## 研究生命周期

`research/*` 分支是临时执行面，不是长期证据库。长期 lineage 统一记录在 `.github/research/evidence-index.json`。

状态统一为 `ACTIVE`、`ACCEPTED`、`REJECTED`、`SUPERSEDED`、`ABANDONED`、`UNCLASSIFIED`。只有终态记录同时绑定精确 branch-head SHA 和封存证据后，才能设置 `gc_eligible=true`；自动清理还要求 `auto_gc=true`、远端 ref SHA 仍与 registry 一致且不存在 open PR。

`Research Branch GC` 默认 fail-closed。受保护 main 合并后，只能自动删除 registry 中明确 `auto_gc` 的精确 ref；任何 SHA 漂移或 open PR 都会在删除前阻断整次 apply。手工 apply 必须输入 `DELETE_GC_ELIGIBLE_REFS`。

## 声学候选终止登记

声学候选的 canonical 终止注册表是 `.github/program/acoustic_terminal_registry.json`，校验入口是 `.github/program/acoustic_terminal_registry.py`。身份由 `source_revision + candidate_id` 共同确定：相同 tuning 在不同 source 上不是同一个候选，但“未命中终止表”也不代表已经获得新的实验、数据权限或结果晋级授权。

注册表必须非空，并完整覆盖 `docs/program/evidence/acoustic-candidate-*/**/terminal.json` 中现存的声学终止记录。每一条登记都要验证其证据；反过来，每一份声学终止证据也必须有对应登记。空表、非空漏项、重复身份、缺失证据或非 canonical 路径替换都会停止，不能把漏登记解释成候选重新可用。

以下命令只读取登记或运行临时元数据自测，不执行音频实验：

```bash
python3 .github/program/acoustic_terminal_registry.py --self-test
python3 .github/program/acoustic_terminal_registry.py --check
```

Validation Grade 的 candidate resolver 在进入候选公开验证前，使用 `--assert-not-terminal` 与精确 `--source-revision` 查询；命中终止身份时以退出码 `3` 拒绝执行。覆盖校验失败时，应核对并恢复原有证据与登记，不能删除失败证据、清空表、替换 source 或放宽声学阈值来恢复流程。终止保护由既有 Verify 和 Acoustic Candidate Terminal Guard 持续检查。

## Validation Authority Qualification

一次性 holdout 使用 `Validation Authority Qualification`。调用者必须提供 40 位精确 candidate SHA，并确认 `ONE_WAY_HOLDOUT`。工作流先冻结 canonical evaluator、exact correlation backend、Hosted AEC policy 与 dataset lock 的 fingerprint，再用该精确 SHA 调用可复用 Hosted Real AEC。

真实 acoustic holdout 失败即拒绝 candidate；禁止根据 holdout 结果调整阈值、搜索或 metric。仅 compiler/import/infrastructure wiring 类错误允许在不改变 acoustic candidate 语义的前提下修复。

普通 PR、main push 和 schedule 的 Hosted Real AEC 行为保持不变。

## 科研变更与版本身份

`scripts/ci_impact.py` 只决定实际验证范围；受保护 PR 及 fresh-main `summary` 成功用于证明该源码上的测试执行，不能转换为商用发布、产品资格或真实声学/设备结果。变更必须明确源码/数据角色、单变量比较、测量预算、失败原因和可复现收据。

## 历史版本与源码归档

历史 `scripts/prepare_release.py`、`scripts/release_manifest.py`、不可变 Release、tag、SemVer 和 `docs/releases/*` 是既有证据的审计入口。**自动 GitHub Release/产品认证工作流已退役**；不得因普通研究合并或历史文档更新而新建版本、发布 SDK 或伪造旧版结果。

## 外部实验室研究状态

Extended Real 的合法数据/许可和实时 target HIL 是不同证据域。HIL 只能手动指定精确源码 SHA、真实目标板与隔离 runner，使用按实验目的选择的持续时长（可选 72 小时）；缺少实际输入一律为 `NOT_RUN`、`BLOCKED_RUNNER` 或 `BLOCKED_CONFIG`，绝不写成 PASS。观测失败真实记录为 FAIL。历史 `Post Release Qualification Summary` 是只读资料，已不再执行发布后的自动产品认证。

## 证据保留与分支保留

删除终态 research branch 不等于删除证据。被引用的 commit、Actions artifact、PR 讨论、历史 Release 资产、不可变 tag 和 registry lineage 仍然独立存在，因此长期证据权威不再依赖远端分支名。
