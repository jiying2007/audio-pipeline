# audio-pipeline 助手执行规范（中文）

[English](AGENTS.md)

本文件面向 Codex、ChatGPT、代码代理和自动化维护助手。它不授予任何新的仓库、Release、HIL 或 Product Qualification 权限。

## 当前仓库状态

已发布 SDK 保持 **software-commercial-ready 稳定维护基线**：历史软件/public-data program 已无 READY task；E001 仍为 external/deferred。真实产品资格由 live open issue / external-evidence tracker 跟踪，而不是由本文件硬编码某个 issue 编号。

另有用户明确授权的 **frontend-evolution-v1 开放研究与集成阶段**正在推进。先读 `docs/research/frontend-evolution-v1/README.md`、原始归档方案和 live #657。该新阶段允许有限结构实验、训练/微调、原生单/双/四麦原型以及资源/数值优化；使用新的 FE 实验身份。原方案不等于执行证明，旧阶段 candidate-zero 限制不扩展为新研究禁令。I025-I040 等历史结论、失败和归档保持不变；第三方许可、独立数据角色、shipping 默认/API 资格和 E001 物理身份仍分别验收。

默认行为不是无依据地“继续找新算法优化”，而是：

1. 先重新读取 live `main`、open PR/issue 与当前 workflow evidence；
2. 有明确缺陷、回归、集成需求、已授权研究任务或真实外部基础设施失败时才创建软件变更；
3. 没有新的可证问题或已授权任务时保持稳定基线，不为了“100%/终态”制造新复杂度。

## 开始工作前

按任务类型读取：

- 中文总入口：`docs/README.zh-CN.md`；
- 使用/集成：`docs/QUICKSTART.zh-CN.md`；
- 架构：`docs/ARCHITECTURE.zh-CN.md` + `docs/ARCHITECTURE.md`；
- 开发：`docs/DEVELOPMENT.zh-CN.md` + `docs/DEVELOPMENT.md`；
- 数据迭代：`validation/authority.json`、`docs/TESTING.zh-CN.md`；
- 新 FE 研究：`docs/research/frontend-evolution-v1/README.md` 和 live #657；
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

维护基线只为明确可重复问题引入复杂度；FE 新阶段可按已批准的研究假设和有限预算做结构实验。每轮冻结具体假设，一次只处理一个可归因变化。measurement change 与 shipping algorithm change 不得在同一实验中互相批准。候选冻结后需要独立确认；没有实质收益就 KEEP BASELINE。不能把新研究权限当成自动修改产品默认或复制未授权第三方资源的权限。

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

只有当外部基础设施真的上线后，助手才能沿 live external-evidence tracker 执行：

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
- 没有 open software/research PR/task；
- 仅剩真实外部物理证据；
- 没有新的明确软件缺陷或授权集成/研究需求；

助手应**停止制造软件改动**，把状态留在 fail-closed 的 external/deferred 边界，直到出现新的真实输入、授权需求或失败。
