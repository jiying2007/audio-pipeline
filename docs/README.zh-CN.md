# 中文文档导航

本页是 `audio-pipeline` 面向技术研究、嵌入式集成、测试与实验室复核的中文入口。当前研究执行真相源为 [`RESEARCH_ONLY_EXECUTION.md`](RESEARCH_ONLY_EXECUTION.md)。

> **当前定位：纯技术研究**。默认 CI 验证 API/ABI、Runtime、ARM/QEMU、DSP、声学回归及资源合同；它不要求产品 Release、商用就绪或物理认证。历史商业发布/产品认证结论保留在对应档案，**不是当前研究准入权限**。真实 SSC305 CPU/温度/功耗、实际声学及长时运行仍只接受独立实测证据，未测时保持 NOT_RUN。

## 双/四麦研究接续

[C4 软件资格与缺口清单](research/frontend-evolution-v1/C4_SOFTWARE_GAP_INVENTORY_20261020.md) 顶部记录已核实的阶段收口，并保留原始盘点：A1 非零左锚点根、v2.3.56 Runtime/CI 六项修复、无损证据运输，以及 A2-F0 固定前缀退休与外部锚定的 hosted 进程恢复已完成。B3-F0 [#837](https://github.com/jiying2007/audio-pipeline/issues/837) 已完成固定 C4/16kHz 实际 CALL 的 Render PRESENT/ABSENT/重入功能组合；[T3-S3-F0 资源测量](research/frontend-evolution-v1/FE09_T3S3_F0_RESOURCE_PREREGISTRATION_20261024/README.md) 需取得自身独立主线原件与门禁后才能作为有限测量完成。连续滚动、整机冷启动、完整线程栈/设备资源和公共 C4 SDK 仍须分别推进。当前任务以 [研究总索引 #657](https://github.com/jiying2007/audio-pipeline/issues/657) 及具体子任务的最新收口记录为准；历史预注册的待完成状态不覆盖后续 completed 子任务，也不等于父计划已完成。

## 按角色阅读

| 角色 | 先看 | 再看 |
| --- | --- | --- |
| 产品/应用集成 | [快速使用](QUICKSTART.zh-CN.md) | [架构](ARCHITECTURE.zh-CN.md)、[平台支持](PLATFORM_SUPPORT.md) |
| DSP/算法开发 | [开发规范](DEVELOPMENT.zh-CN.md) | [DSP_DESIGN.md](DSP_DESIGN.md)、[TUNING.md](TUNING.md) |
| Runtime/系统开发 | [架构](ARCHITECTURE.zh-CN.md) | [API_CONTRACT.md](API_CONTRACT.md)、[DIAGNOSTICS.md](DIAGNOSTICS.md) |
| CI/研究验证维护 | [流程图](FLOWS.zh-CN.md) | [研究执行边界](RESEARCH_ONLY_EXECUTION.md)、[REPOSITORY_GOVERNANCE.md](REPOSITORY_GOVERNANCE.md) |
| #714 元数据故障定位 | [只读 HTTP/网络诊断](BOT714_METADATA_DIAGNOSTICS.zh-CN.md) | 保留原维护拒绝、独立记录当前请求和三个 SHA |
| 数据集自测/迭代 | [TESTING 中文版](TESTING.zh-CN.md) | [EXTENDED_REAL_VALIDATION 中文版](EXTENDED_REAL_VALIDATION.zh-CN.md)、[validation/README.md](../validation/README.md) |
| 实验室/真机 | [PCR02 真机采集](PCR02_REAL_CAPTURE.md) | [可信 Runner 中文版](TRUSTED_RUNNERS.zh-CN.md)、[lab/README.md](../lab/README.md)、[hil/README.md](../hil/README.md) |
| 历史产品认证记录（只读） | [PRODUCT_ASSURANCE 中文版](PRODUCT_ASSURANCE.zh-CN.md) | [certification/README.md](../certification/README.md) |
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

中文文档负责**研究复现、嵌入式集成、操作与证据边界说明**；以下低层协议/机器契约继续以英文原文为 canonical truth，避免双语全文复制形成两个可能漂移的规范源：

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
5. 中文材料不得将 Hosted CI、QEMU 或合成音频解释为真实人声、真实 AFE、DUT 或 SSC305 物理性能；历史产品认证条款只在历史文档中呈现，不再限制当前科研推进。
