# audio-pipeline 助手执行规范（中文）

[English](AGENTS.md)

本文件面向 Codex、ChatGPT、代码代理和自动化维护助手。它不授予任何新的仓库、Release、HIL 或 Product Qualification 权限。

## 当前仓库状态

仓库当前处于 **software-commercial-ready 稳定维护状态**：软件/public-data program 已无 READY task；E001 仍为 external/deferred。真实产品资格由 Issue #58 跟踪。

默认行为因此不是“继续找新算法优化”，而是：

1. 先重新读取 live `main`、open PR/issue 与当前 workflow evidence；
2. 有明确缺陷、回归、集成需求或真实外部基础设施失败时才创建软件变更；
3. 没有新的可证问题时保持稳定基线，不为了“100%/终态”制造新复杂度。

## 开始工作前

按任务类型读取：

- 中文总入口：`docs/README.zh-CN.md`；
- 使用/集成：`docs/QUICKSTART.zh-CN.md`；
- 架构：`docs/ARCHITECTURE.zh-CN.md` + `docs/ARCHITECTURE.md`；
- 开发：`docs/DEVELOPMENT.zh-CN.md` + `docs/DEVELOPMENT.md`；
- 数据迭代：`validation/authority.json`、`docs/TESTING.zh-CN.md`；
- Release/认证：`docs/PRODUCT_ASSURANCE.zh-CN.md`、`certification/README.md`；
- 实验室：`docs/TRUSTED_RUNNERS.zh-CN.md`、`lab/README.md`；
- 历史 software program：只有需要解释既有 research evidence 时再读 `docs/program/*`。

不要从聊天记忆假设仓库状态；live GitHub 与 committed machine contract 优先。

## 绝对边界

- 不伪造或模拟 runner availability、DUT route、sensor、真实 corpus、shipping toolchain、soak duration、archive receipt、HIL/PQ/Product Certification PASS；
- 不通过提高/降低 threshold、timeout、sample budget、allow-failure 或 skip 来获得绿色；
- 不直接 push main；
- 不 force-update tag；
- 不删除未分类 ref；
- 不把 Hosted CI/QEMU/public-data 指标描述成真机性能；
- 不让 validation-grade/blind 数据进入 optimizer feedback；
- 不从一次 dispatch/workflow success 直接推导 task CLOSED 或 product-certified。

## 变更原则

### 软件缺陷/回归

先确定失败层级和 root cause，再改代码。冻结 base、输入、measurement、接受规则。优先最小修复，并增加能证明问题的 targeted/negative test。

### DSP/算法

只有明确的可重复失败才能引入新复杂度。一次只处理一个根因。measurement change 与 shipping algorithm change 不得在同一实验中互相批准。候选冻结后需要独立确认；没有实质收益就 KEEP BASELINE。

### 数据集自测

严格遵守 `validation/authority.json`：development/search 与 validation/blind 分离；保存 exact dataset identity/hash/seed；重复数据只是 replay，不算 fresh independence。

### 文档

中文商用入口属于交付面。API/lifecycle/preset/validation/release/certification/operator command 变化时检查中文文档；不要复制低层机器契约形成第二套 truth。

## PR / CI / Merge

1. 从 exact live main 建分支；
2. scope/non-goals 明确；
3. targeted/self/negative tests；
4. 使用已有 canonical evaluator/tool；
5. exact-head full applicable CI；
6. required `summary=success` 后才能合并；
7. HEAD 移动后旧证据失效；
8. protected squash merge；
9. exact-main 再验证；
10. release-bearing 变化走 governed Release，release-neutral 变化不得制造新版本；
11. evidence 已保存后由 fail-closed GC 清终态 branch。

## 真实硬件阶段

只有当外部基础设施真的上线后，助手才能沿 #58 执行：

```text
四类 trusted runner READY
-> Extended Real / HIL 真实验证
-> activation variables enable
-> E001 Activation Preflight
-> HIL 历史
-> >=72 h Product Certification
-> immutable product-lifecycle receipt
```

E001 READY 仍不是 Product Certification PASS。

## 停止条件

当：

- main required gates 全绿；
- 没有 open software PR/task；
- 仅剩真实外部物理证据；
- 没有新的明确软件缺陷；

助手应**停止制造软件改动**，把状态留在 fail-closed 的 external/deferred 边界，直到出现新的真实输入或失败。
