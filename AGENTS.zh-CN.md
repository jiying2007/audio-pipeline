# audio-pipeline 助手执行规范（中文）

[English](AGENTS.md)

本文件面向 Codex、ChatGPT、代码代理和自动化维护助手。它不授予任何新的仓库、Release、HIL 或 Product Qualification 权限。

## 当前仓库状态

**当前唯一执行定位：纯技术研究**。数据准备、算法实验、声学评测与 ARM/SSC305 类资源研究依赖可复现的科研证据和实际数据使用权，不要求 Shipping 审批、商业 SDK 发布或产品认证。既有商用就绪/E001/HIL/产品资格内容是待迁移的历史流程，**不作为研究准入门槛**；参见 [`docs/RESEARCH_ONLY_EXECUTION.md`](docs/RESEARCH_ONLY_EXECUTION.md) 和 [#882](https://github.com/jiying2007/audio-pipeline/issues/882)。历史证据保留真实原貌，不伪造真机结果。

另有用户明确授权的 **frontend-evolution-v1 开放研究与集成阶段**正在推进。先读 `docs/research/frontend-evolution-v1/README.md`、原始归档方案和 live #657。该新阶段允许有限结构实验、训练/微调、原生单/双/四麦原型以及资源/数值优化；使用新的 FE 实验身份。原方案不等于执行证明，旧阶段 candidate-zero 限制不扩展为新研究禁令。I025-I040 等历史结论、失败和归档保持不变；第三方许可、独立数据角色、API/ABI 兼容性和 E001 历史物理身份分别留存；它们不构成商业放行前置条件。

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
- 历史发布/认证文档（仅供溯源）：`docs/PRODUCT_ASSURANCE.zh-CN.md`、`certification/README.md`；
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

维护基线只为明确可重复问题引入复杂度；FE 新阶段可按已批准的研究假设和有限预算做结构实验。每轮冻结具体假设，一次只处理一个可归因变化。测量合同改变与算法改变不能在同一实验中互相证明；候选冻结后需要独立确认，没有实质收益就 KEEP BASELINE。不能以研究权限绕过第三方权利或擅自改写已冻结的研究对照基线。

### 数据集自测

严格遵守 `validation/authority.json`：development/search 与 validation/blind 分离；保存 exact dataset identity/hash/seed；重复数据只是 replay，不算 fresh independence。

### 文档

中文入口服务于科研复现、嵌入式资源测量及实验复核。API/lifecycle/preset/validation/operator command 变化时检查中文文档；历史 release/certification 只保留来源事实，不复制低层机器契约形成第二套 truth。

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
10. 科研 PR/main 检查不得自动发布产品 Release；实验快照保留精确源码/工具链/数据哈希，非运行时变更不得制造产品版本；
11. evidence 已保存后由 fail-closed GC 清终态 branch。

## 真实硬件阶段

只有当外部基础设施真的上线后，助手才能沿 live external-evidence tracker 执行：

```text
合法来源与固定实验输入
-> 可用且真实的 trusted audio-validation/audio-target runner
-> Extended Real / HIL 独立技术测量
-> CPU/RSS/功耗/延迟/声学与连续运行的真实结果
-> 带身份哈希及 NOT_RUN/FAIL 限制的研究证据
```

E001 属于历史基础设施状态，不是研究效果结论；没有真机或真实采集时保留 NOT_RUN，不能用 Hosted CI/QEMU 冒充实测。

## 停止条件

当：

- main required gates 全绿；
- 没有 open software/research PR/task；
- 仅剩真实外部物理证据；
- 没有新的明确软件缺陷或授权集成/研究需求；

助手应**停止制造软件改动**，把状态留在 fail-closed 的 external/deferred 边界，直到出现新的真实输入、授权需求或失败。
