# 中文文档导航

本页是 `audio-pipeline` 面向中文算法研究、嵌入式系统、数据评测和真实设备实验的统一入口。

> **当前状态边界：纯技术研究。** 仓库提供可复现的 BF/AEC/NS/AGC/VAD、Runtime、公共 C API、1/2/4 麦及 ARM/SSC305 类资源实验。研究准入取决于来源与许可、角色隔离、算法回归和真实测量，不需要商业发布、SKU 审批、产品认证或固定 72 小时真机老化。Hosted/QEMU 结果不是物理设备数据；真实 HIL/声学/功耗/温升等证据缺失时应标记 `NOT_RUN`/`BLOCKED`。旧软件商用就绪和产品资格声明仅属历史档案，详见 [研究执行边界](RESEARCH_ONLY_EXECUTION.md) 与 [#882](https://github.com/jiying2007/audio-pipeline/issues/882)。

## 当前双麦识别交互与语音对讲

[双麦首轮实施与证据索引](research/frontend-evolution-v1/README.md#2026-11-06-双麦识别交互与语音对讲)覆盖 SYNC 实际观察间隔、LITE/固定方向健康保护、SAFE 计数生命周期，以及同一公共前端的 CALL / ASSISTANT 配置回放。使用现有 [PCM 入口](OFFLINE_PCM_IO.md) 的 `--profile call|assistant` 显式选择用途；不指定时仍为 CALL。工程连续性、声学效果、KWS 与物理目标结果分别依其实际证据判断；保留已发现的近端幅度损失和切换边界问题。

## 双/四麦历史研究接续

[C4 软件资格与缺口清单](research/frontend-evolution-v1/C4_SOFTWARE_GAP_INVENTORY_20261020.md) 顶部记录已核实的阶段收口，并保留原始盘点：A1 非零左锚点根、v2.3.56 Runtime/CI 六项修复、无损证据运输，以及 A2-F0 固定前缀退休与外部锚定的 hosted 进程恢复已完成。B3-F0 [#837](https://github.com/jiying2007/audio-pipeline/issues/837) 已完成固定 C4/16kHz 实际 CALL 的 Render PRESENT/ABSENT/重入功能组合；[T3-S3-F0 资源测量](research/frontend-evolution-v1/FE09_T3S3_F0_RESOURCE_PREREGISTRATION_20261024/README.md) 需取得自身独立主线原件与门禁后才能作为有限测量完成。连续滚动、整机冷启动、完整线程栈/设备资源和公共 C4 SDK 仍须分别推进。当前任务以 [研究总索引 #657](https://github.com/jiying2007/audio-pipeline/issues/657) 及具体子任务的最新收口记录为准；历史预注册的待完成状态不覆盖后续 completed 子任务，也不等于父计划已完成。

## 按角色阅读

| 角色 | 先看 | 再看 |
| --- | --- | --- |
| 嵌入式/应用研究 | [快速使用](QUICKSTART.zh-CN.md) | [架构](ARCHITECTURE.zh-CN.md)、[平台支持](PLATFORM_SUPPORT.md) |
| DSP/算法开发 | [开发规范](DEVELOPMENT.zh-CN.md) | [DSP_DESIGN.md](DSP_DESIGN.md)、[TUNING.md](TUNING.md) |
| Runtime/系统开发 | [架构](ARCHITECTURE.zh-CN.md) | [API_CONTRACT.md](API_CONTRACT.md)、[DIAGNOSTICS.md](DIAGNOSTICS.md) |
| CI/研究证据维护 | [研究执行边界](RESEARCH_ONLY_EXECUTION.md) | [流程图](FLOWS.zh-CN.md)、[REPOSITORY_GOVERNANCE.md](REPOSITORY_GOVERNANCE.md) |
| #714 元数据故障定位 | [只读 HTTP/网络诊断](BOT714_METADATA_DIAGNOSTICS.zh-CN.md) | 保留原维护拒绝、独立记录当前请求和三个 SHA |
| 数据集自测/迭代 | [TESTING 中文版](TESTING.zh-CN.md) | [EXTENDED_REAL_VALIDATION 中文版](EXTENDED_REAL_VALIDATION.zh-CN.md)、[validation/README.md](../validation/README.md) |
| 实验室/真机 | [PCR02 真机采集](PCR02_REAL_CAPTURE.md) | [可信 Runner 中文版](TRUSTED_RUNNERS.zh-CN.md)、[lab/README.md](../lab/README.md)、[hil/README.md](../hil/README.md) |
| 历史认证记录（只读） | [PRODUCT_ASSURANCE 中文版](PRODUCT_ASSURANCE.zh-CN.md) | [certification/README.md](../certification/README.md)；不作为当前研究门禁 |
| 贡献者 | [CONTRIBUTING.zh-CN.md](../CONTRIBUTING.zh-CN.md) | [开发规范](DEVELOPMENT.zh-CN.md) |
| AI/Codex/自动化助手 | [AGENTS.zh-CN.md](../AGENTS.zh-CN.md) | [AGENTS.md](../AGENTS.md) |

## 中文主干文档

- [README.zh-CN.md](../README.zh-CN.md)：研究定位、能力边界、构建与验证入口。
- [QUICKSTART.zh-CN.md](QUICKSTART.zh-CN.md)：从构建、安装到 Runtime、Dump/Replay 的实际使用步骤。
- [ARCHITECTURE.zh-CN.md](ARCHITECTURE.zh-CN.md)：模块、线程、内存和权限边界。
- [FLOWS.zh-CN.md](FLOWS.zh-CN.md)：音频、Runtime、数据迭代及历史 CI/Release、E001/HIL/认证流程图（历史部分不是研究准入）。
- [DEVELOPMENT.zh-CN.md](DEVELOPMENT.zh-CN.md)：代码、实时、API、测试、版本与变更规则。
- [PRODUCT_ASSURANCE.zh-CN.md](PRODUCT_ASSURANCE.zh-CN.md)：历史产品认证权威链（仅用于溯源，不是研究执行指令）。
- [TRUSTED_RUNNERS.zh-CN.md](TRUSTED_RUNNERS.zh-CN.md)：四类 self-hosted runner 上线和失效规则。
- [TESTING.zh-CN.md](TESTING.zh-CN.md)：CI、公开数据、HIL 测试策略。
- [EXTENDED_REAL_VALIDATION.zh-CN.md](EXTENDED_REAL_VALIDATION.zh-CN.md)：真实公开数据扩展验证。
- [PCR02_REAL_CAPTURE.md](PCR02_REAL_CAPTURE.md)：PCR02/SSC305 双麦真机采集 bundle、哈希封存、离线 replay 与诊断接入流程。
- [REPOSITORY_LIFECYCLE.zh-CN.md](REPOSITORY_LIFECYCLE.zh-CN.md)：研究、候选、分支和证据生命周期。

## 英文 canonical 文档与中文层的关系

中文文档负责**科研操作、可复现性、维护和证据边界说明**；以下低层协议/机器契约继续以英文原文为 canonical truth，避免双语全文复制形成两个可能漂移的规范源：

- `docs/API_CONTRACT.md`：公开 C API、状态码、生命周期、线程契约；
- `docs/DSP_DESIGN.md`：算法公式、状态与实现细节；
- `docs/PCR02_REAL_CAPTURE.md`：PCR02 真机采集、bundle/replay/diagnosis 与证据边界；
- `docs/PERFORMANCE.md`：资源/性能机器 Gate；
- `validation/research-authority.json`：数据权限真相源；
- `certification/*.schema.json` 与旧 shipping policy：仅为历史认证源与存档校验使用，不决定当前科研是否可执行；
- `.github/workflows/*`：当前 CI/研究实验定义；已退役的 Release/Certification 工作流只能从 Git 历史查证。

若中文说明与上述机器契约冲突，**机器契约和英文 canonical 文档优先**，并应在同一个 PR 中修正中文文档。

## 终态维护规则

1. 任何影响公开 API/ABI、线程所有权、研究 preset、数据验证权限、实验运行流程或历史发布/认证引用的变更，必须同步检查中文主干文档。
2. 中文文档不得把 hosted/QEMU/public-data 结果写成独立真机性能或已完成的真实设备验收。
3. 流程图必须只表达现有机器流程，不发明新的 authority。
4. 历史事实写入 `CHANGELOG.md` 或对应 evidence/archive；当前文档只描述当前行为。
5. 真机、现场人声和长时间稳定性等物理证据缺失时必须如实报告 `NOT_RUN`/`BLOCKED`；不得把商业资格或固定 72 小时认证变成科研准入条件，亦不得将历史证据重标为当前 PASS。
