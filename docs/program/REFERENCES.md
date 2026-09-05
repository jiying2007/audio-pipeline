# 外部实践与数据登记

研究日期：2026-09-05。以下是可核对的一手资料及本项目的**设计选择**，不是第三方算法已集成、
已运行对标或已获得量产性能证明。代码参考不等于代码复制；任何导入先固定 revision、核对
代码/模型/音频分别适用的许可与 notice，复用代码不得冒称 clean-room。

| 一手来源 | 可借鉴/可使用内容 | 本阶段决策与限制 |
| --- | --- | --- |
| [WebRTC AEC3 delay controller](https://webrtc.googlesource.com/src/+/5c532d37744ec89927e59c39d82869f12c4e8569/modules/audio_processing/aec3/render_delay_controller.cc) | alignment headroom、delay estimation/controller 分工 | 参考固定 revision 的职责与因果性；不照搬其阈值、内存和线程架构 |
| [WebRTC audio processing](https://webrtc.googlesource.com/src/+/refs/heads/main/modules/audio_processing/) | AEC/NS/AGC、测试与 dump 的模块组织 | 浏览入口不是生产依赖锁；导入或对标前必须 pin exact commit |
| [SpeexDSP manual](https://www.speex.org/docs/manual/speex-manual/node7.html) | 已呈现 render 与 capture 的时序、滤波器 tail 与同步问题 | 核查 causal margin，不把软件延时当作空间传播距离 |
| [Pyroomacoustics room simulation](https://pyroomacoustics.readthedocs.io/en/stable/pyroomacoustics.room.html) | ISM/RIR、image-source 规则性伪影、fractional-delay 全局延时 | 仿真方法参考；首轮使用显式简化一阶模型，无新运行依赖；后续固定版本后离线交叉验证 |
| [RNNoise 作者资料](https://jmvalin.ca/demo/rnnoise/) | DSP 与学习式噪声抑制结合、对下游传递不确定性 | NS 候选研究，不默认增加 neural backend；模型/训练集/算力预算未验证前不 shipping |
| [Microsoft AEC Challenge](https://github.com/microsoft/AEC-Challenge) | far/near/double-talk、真实与合成 AEC 数据 | 优先复用本仓库 AEC locks 与 canonical builder；数据有原始来源许可，repo code MIT 不等于所有音频 MIT |
| [Microsoft DNS Challenge](https://github.com/microsoft/DNS-Challenge) | speech/noise/RIR 合成、语音/噪声/总体质量分别评估 | 复用现有数据锁；代码、文档、各数据源许可分开；MOS proxy 不替代真实听评或 DUT |
| [OpenSLR SLR28](https://www.openslr.org/28) | 16kHz/16-bit 的真实/合成 RIR 与噪声；发布页标为 Apache-2.0 | 从现有 SLR28 lock 扩充；保留归属和来源，不把一次静态 RIR 当完整运动模型 |
| [AMI corpus](https://groups.inf.ed.ac.uk/ami/corpus/)、[annotations](https://groups.inf.ed.ac.uk/ami/download/) | meeting、近讲/远场与手工时间标注；CC-BY-4.0 | 复用已锁 ES2003a/ES2004a 为 regression；新 session 冻结后才可确认；transcription timing 非审计 SAD gold |
| [LibriSpeech SLR12](https://www.openslr.org/12) | 16kHz 朗读语音、speaker 分组；CC-BY-4.0 | 候选语音来源，尚未新增接入；按 speaker/source-group 划分，朗读语音不能覆盖全部机器人使用场景 |
| [GitHub Actions security](https://docs.github.com/en/actions/reference/security/securely-using-pull_request_target) | untrusted PR 与 privileged token 分离 | 当前研究 workflow contents:read，无生产写权限；不通过 pull_request_target 执行 PR 代码 |

## 接入流程

发现来源 → 审核 code/model/data 许可与可用性 → 冻结 revision/object hash → 下载后校验内容哈希 →
建立 source-group/派生关系 → 指定 development/validation/shadow/confirmation/promotion 角色 →
冻结窗口与选取规则 → 执行 → 记录曝光/退役。不能从 floating latest 直接生成晋级证据。

本目录只登记方法与决策，实际数据哈希仍由已有 dataset locks 维护。引用网页的研究日期不等于
字节级 pin。无法固定数据身份/许可证/访问条件的源保持 BLOCKED_DATA，不伪造下载或替代样本。
