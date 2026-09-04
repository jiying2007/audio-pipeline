# 仓库生命周期

本文定义产品代码之外的仓库级生命周期：研究、验证权威资格、发布准备、不可变发布、外部实验室资格以及证据保留。

## 研究生命周期

`research/*` 分支是临时执行面，不是长期证据库。长期 lineage 统一记录在 `.github/research/evidence-index.json`。

状态统一为 `ACTIVE`、`ACCEPTED`、`REJECTED`、`SUPERSEDED`、`ABANDONED`、`UNCLASSIFIED`。只有终态记录同时绑定精确 branch-head SHA 和封存证据后，才能设置 `gc_eligible=true`；自动清理还要求 `auto_gc=true`、远端 ref SHA 仍与 registry 一致且不存在 open PR。

`Research Branch GC` 默认 fail-closed。受保护 main 合并后，只能自动删除 registry 中明确 `auto_gc` 的精确 ref；任何 SHA 漂移或 open PR 都会在删除前阻断整次 apply。手工 apply 必须输入 `DELETE_GC_ELIGIBLE_REFS`。

## Validation Authority Qualification

一次性 holdout 使用 `Validation Authority Qualification`。调用者必须提供 40 位精确 candidate SHA，并确认 `ONE_WAY_HOLDOUT`。工作流先冻结 canonical evaluator、exact correlation backend、Hosted AEC policy 与 dataset lock 的 fingerprint，再用该精确 SHA 调用可复用 Hosted Real AEC。

真实 acoustic holdout 失败即拒绝 candidate；禁止根据 holdout 结果调整阈值、搜索或 metric。仅 compiler/import/infrastructure wiring 类错误允许在不改变 acoustic candidate 语义的前提下修复。

普通 PR、main push 和 schedule 的 Hosted Real AEC 行为保持不变。

## 发布准备

`scripts/prepare_release.py` 是统一 release metadata 工具，只修改 CMake project VERSION 并在 CHANGELOG 顶部增加新版本段。使用 `--base-ref` 时，会验证新版本标题以下的历史 CHANGELOG 与 base 完全逐字节一致。

release-bearing authority 仍由 `scripts/ci_impact.py` 管理。仅修改 CMake project VERSION token 的变化在 PR 矩阵选择中识别为 `VERSION_ONLY`；main push 仍强制完整 FULL Verify。

## 不可变发行证据

后续 Release 将通过 `scripts/release_manifest.py` 生成机器可读 release evidence manifest，绑定 exact source commit/tree、merged PR lineage、main Verify run、validation authority 哈希、发行资产摘要以及外部实验室初始可用状态。

该 manifest 不降低任何发行门禁。新版本仍只能在 main-push Verify 成功后，由现有 exact-SHA Release workflow 和不可变 tag/release 治理发布。

v2.3.6 早于集成 manifest asset，因此不修改其 immutable Release，而是在 `docs/releases/v2.3.6-evidence.json` 中补充审计索引。

## 外部实验室状态

软件 Release 与外部实验室 Qualification 是两个独立状态域。Release 后 HIL 和 Extended Real 继续 fail-visible；基础设施未就绪时绝不能伪 PASS。

统一状态：`PASS`、`FAIL`、`BLOCKED_RUNNER`、`BLOCKED_CONFIG`、`PENDING`、`UNKNOWN`。`Post Release Qualification Summary` 会生成 JSON artifact 和 Actions Summary，明确区分软件回归与外部实验室不可用。

## 证据保留与分支保留

删除终态 research branch 不等于删除证据。被引用的 commit、Actions artifact、PR 讨论、Release 资产、不可变 tag 和 registry lineage 仍然独立存在，因此长期证据权威不再依赖远端分支名。
