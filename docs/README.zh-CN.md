# 中文文档导航

本页是 `audio-pipeline` 面向中文研发、集成、测试、实验室与发布人员的统一入口。

> **当前状态边界**：仓库已经达到 `software-commercial-ready`（软件商用集成就绪）。这表示 API/ABI、Runtime、安装 SDK、SSC305 命名产品构建契约、资源/性能回归、数据验证权限、诊断、发布供应链和认证控制面均可由仓库重复验证；**不表示** SSC305 真机 CPU/热/功耗/声学、HIL 历史或 72 小时 Product Certification 已完成。真实物理证据以 live open issue / external-evidence tracker 和实际 workflow evidence 为准。

## 按角色阅读

| 角色 | 先看 | 再看 |
| --- | --- | --- |
| 产品/应用集成 | [快速使用](QUICKSTART.zh-CN.md) | [架构](ARCHITECTURE.zh-CN.md)、[平台支持](PLATFORM_SUPPORT.md) |
| DSP/算法开发 | [开发规范](DEVELOPMENT.zh-CN.md) | [DSP_DESIGN.md](DSP_DESIGN.md)、[TUNING.md](TUNING.md) |
| Runtime/系统开发 | [架构](ARCHITECTURE.zh-CN.md) | [API_CONTRACT.md](API_CONTRACT.md)、[DIAGNOSTICS.md](DIAGNOSTICS.md) |
| CI/Release 维护 | [流程图](FLOWS.zh-CN.md) | [PRODUCT_ASSURANCE 中文版](PRODUCT_ASSURANCE.zh-CN.md)、[REPOSITORY_GOVERNANCE.md](REPOSITORY_GOVERNANCE.md) |
| 数据集自测/迭代 | [TESTING 中文版](TESTING.zh-CN.md) | [EXTENDED_REAL_VALIDATION 中文版](EXTENDED_REAL_VALIDATION.zh-CN.md)、[validation/README.md](../validation/README.md) |
| 实验室/真机 | [PCR02 真机采集](PCR02_REAL_CAPTURE.md) | [可信 Runner 中文版](TRUSTED_RUNNERS.zh-CN.md)、[lab/README.md](../lab/README.md)、[hil/README.md](../hil/README.md) |
| Product Certification | [PRODUCT_ASSURANCE 中文版](PRODUCT_ASSURANCE.zh-CN.md) | [certification/README.md](../certification/README.md) |
| 贡献者 | [CONTRIBUTING.zh-CN.md](../CONTRIBUTING.zh-CN.md) | [开发规范](DEVELOPMENT.zh-CN.md) |
| AI/Codex/自动化助手 | [AGENTS.zh-CN.md](../AGENTS.zh-CN.md) | [AGENTS.md](../AGENTS.md) |

## 中文主干文档

- [README.zh-CN.md](../README.zh-CN.md)：项目定位、能力边界、构建、验证与认证概览。
- [QUICKSTART.zh-CN.md](QUICKSTART.zh-CN.md)：从构建、安装到 Runtime、Dump/Replay 的实际使用步骤。
- [ARCHITECTURE.zh-CN.md](ARCHITECTURE.zh-CN.md)：模块、线程、内存和权限边界。
- [FLOWS.zh-CN.md](FLOWS.zh-CN.md)：音频、Runtime、数据迭代、CI/Release、E001/HIL/认证流程图。
- [DEVELOPMENT.zh-CN.md](DEVELOPMENT.zh-CN.md)：代码、实时、API、测试、版本与变更规则。
- [PRODUCT_ASSURANCE.zh-CN.md](PRODUCT_ASSURANCE.zh-CN.md)：软件商用就绪与产品认证权威链。
- [TRUSTED_RUNNERS.zh-CN.md](TRUSTED_RUNNERS.zh-CN.md)：四类 self-hosted runner 上线和失效规则。
- [TESTING.zh-CN.md](TESTING.zh-CN.md)：CI、公开数据、HIL 测试策略。
- [EXTENDED_REAL_VALIDATION.zh-CN.md](EXTENDED_REAL_VALIDATION.zh-CN.md)：真实公开数据扩展验证。
- [PCR02_REAL_CAPTURE.md](PCR02_REAL_CAPTURE.md)：PCR02/SSC305 双麦真机采集 bundle、哈希封存、离线 replay 与诊断接入流程。
- [REPOSITORY_LIFECYCLE.zh-CN.md](REPOSITORY_LIFECYCLE.zh-CN.md)：研究、候选、分支和证据生命周期。

## 英文 canonical 文档与中文层的关系

中文文档负责**商用集成、操作、维护和边界说明**；以下低层协议/机器契约继续以英文原文为 canonical truth，避免双语全文复制形成两个可能漂移的规范源：

- `docs/API_CONTRACT.md`：公开 C API、状态码、生命周期、线程契约；
- `docs/DSP_DESIGN.md`：算法公式、状态与实现细节；
- `docs/PCR02_REAL_CAPTURE.md`：PCR02 真机采集、bundle/replay/diagnosis 与证据边界；
- `docs/PERFORMANCE.md`：资源/性能机器 Gate；
- `validation/authority.json`：数据权限真相源；
- `certification/*.schema.json` 与 shipping policy：产品认证机器真相源；
- `.github/workflows/*`：CI/HIL/Release/Certification 实际执行定义。

若中文说明与上述机器契约冲突，**机器契约和英文 canonical 文档优先**，并应在同一个 PR 中修正中文文档。

## 终态维护规则

1. 任何影响公开 API/ABI、线程所有权、产品 preset、验证权限、Release 或 Product Certification 的变更，必须同步检查中文主干文档。
2. 中文文档不得把 hosted/QEMU/public-data 结果写成真机性能或 Product Qualification PASS。
3. 流程图必须只表达现有机器流程，不发明新的 authority。
4. 历史事实写入 `CHANGELOG.md` 或对应 evidence/archive；当前文档只描述当前行为。
5. 只要 Product Certification 所需真实 DUT/HIL/72 h 物理证据尚未完成，中文材料就必须继续明确 `software-commercial-ready != product-certified`；不得把该规则绑定到某个固定 issue 编号。
