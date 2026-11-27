# 2026-11-28 科研平台审查落地与完成边界

本轮把来源、数据角色、仿真、算法参考、固定评估、失败复现和长期原件回读接成实际可执行链，
完成原审查 F01–F08 中的具体修复、关键原件恢复和三项有界研究执行。
**真实执行与回读已完成，不等于新算法改善、全部历史迁移或全部长期研究目标完成。**
此文是随结果提交的不可变研究记录；最终 PR head、受保护 squash 与新 main 自身 CI 的实际状态，
以 [#968 最终闭环回执](https://github.com/jiying2007/audio-pipeline/issues/968) 为准。
不能借用旧 head 的绿灯，也不能把本文发布时尚未发生的合并写成已完成。

## 1. 原审查逐项落地

| 审查项 | 本轮实际完成 | 完成的准确范围与余项 |
| --- | --- | --- |
| F01：authority 身份错绑 | [方法修复 #970](https://github.com/jiying2007/audio-pipeline/pull/970)将报告、baseline reuse 绑定到本次实际加载路径及原字节；custom path、同语义不同字节、错误绑定等负例通过。 | 修复具体执行/报告身份缺陷；保留历史 v1、原实验与评分器，不据此宣布所有历史结果无效。 |
| F02：WAV 与同 basename 失败复现 | 复用 canonical stage_audio/build_invoke；按角色保留原件和解码 PCM 双 SHA，校验包内快照后导入。搬移复现、同名不覆盖与失败码验证完成。 | 修复实际输入运输错误；未新增另一套评分或泛化复现框架。 |
| F03：证据依赖短期 Actions/tmp | [原 D1/D2 恢复](DUALMIC_ARCHIVE_RECOVERY.zh-CN.md)取得原 474,165,229 B ZIP，3551 成员、60 例、35916 帧经原 D2 reader 回读，31.741358 s、0 DSP；本轮 AEC3/RIR/F05 又各有完整原件和独立回读。 | 已恢复影响本轮决策的关键 lineage；33/37 历史模块的 tmp 依赖没有整体迁移，不能宣称所有历史环境可离线重建。缺失原件须逐项记缺失，不能重跑已拒绝候选代替原证据。 |
| F04：设备数据公开事实漂移 | 追加纠正 public main 已有 119 文件、68 WAV 的事实；[材料审计](F05_READINESS_20261128/README.zh-CN.md)核对全部原件 SHA。 | 文档事实缺陷关闭；来源仍为 development / not_assessed，公开可见不自动产生授权、说话人/几何/时钟真值。 |
| F05：来源暴露与双麦覆盖 | 审计 852 可达 commits、4468 历史文本 blobs；68 WAV 为 56 独特 SHA。两处 WAV block_align 仅作派生头修正，PCM 不变。取得排除既往可见 16 人后的 8 人 32 完整原句，327.605 s；[固定双麦研究](F05_DUALMIC_VALIDATION_20261128/README.zh-CN.md)已完成 128 次处理和独立回读。 | 本轮来源审计、来源运输和固定整链测量闭环；数据仍 NOT_BLIND，128 输出相关。含双讲两 profile 的 8 speaker 均值全负，无晋级。新独立房间、真实阵列、听评和 ASR/KWS 未由此补齐。 |
| F06：专项资格与归档重复 | [运行手册](LONG_TERM_RESEARCH_PLATFORM.zh-CN.md)复用五权、canonical 材料化/指标、固定源与原件恢复；AEC3、RIR、F05 三个不同任务实际走通 run/verify/归档。AP [可搬移工程包](AP_CURRENT_PORTABLE_V1.zh-CN.md)绑定 CI 构建、运行时观察、宿主工程和原二进制。 | 共同研究路径已有真实执行证据；70 个 workflow 和大量冻结专项没有整体改造为通用编排器。下一真实任务出现可证明的重复时再抽取，不能改写历史合同凑统一。 |
| F07：重复固定后置/简单 AGC/BF | AEC3/APM 新参考完成实际构建、工程、6 例 / 12 次 development 执行与回读；实测 RIR 完成固定模型支撑诊断。下一项 linear tap / final 假设已基于这些 development 证据选定，见下节。 | 外部参考与有限诊断已完成；新的结构候选、linear tap 实现和声学比较尚未执行，状态 NOT_RUN。没有重开旧拒绝或以它们训练/选优。 |
| F08：历史分支保全未分类 | 三条历史 refs 逐 SHA 分类为一条 ACCEPTED、两条 SUPERSEDED，原 81 条记录和 GC 候选不变；再追加本轮 AEC3 与总集成保全，共 86 条。均按保留语义，不删除 refs。 | 保留型身份分类完成；精确 live inventory 与 PR 收口另见 #968。状态分类不自动授权 GC、分支删除或历史科学问题关闭。 |

## 2. 三项实际研究回答了什么

| 研究 | 实际执行源码 | 结果与解释边界 |
| --- | --- | --- |
| AEC3/APM 六例参考 | `819849ee3ed6b269b8417ef8700eecfcf29f7958` | [原结果](WEBRTC_AEC3_RESULT_20261128.zh-CN.md)：post-BF mono、两组材料的 6 个相关 development 案例。固定 AEC3 远端能量抑制均值 33.4854 dB，但双讲保持不支持默认替换。历史 AP/Speex 对照为 e367 原输出，不伪称当前 main 整链公平排名。 |
| 单房间 RIR 有限支撑诊断 | `a058b02582962875ac10e6bb42b928c46c405213` | [原结果](DECHORATE_RIR_GAP_20261128/RESULT.zh-CN.md)：12 原对象、1 房间、11 相关状态、22 通道视图。固定 1677 samples / 48 kHz 的放宽 oracle 支撑窗下，未覆盖有限记录能量下界 0.975639%–32.336418%，中位 2.348868%。不是纯混响比例、完整模型拟合误差或算法音质损失。 |
| 新来源 F05 双麦描述性验证 | `637643753166dee42efd325bed76b7fd8e7237c4` | [原结果与回读](F05_DUALMIC_VALIDATION_20261128/README.zh-CN.md)：8 人、32 完整原句、4 配对、128 相关输出。含双讲固定延迟主 Δ 的 speaker 均值中位 CALL −5.648875 / ASSISTANT −5.283438 dB；纯近端 identity 数值单独解释。无训练、搜索、盲测或晋级。 |

三项都保留不利值与 null，没有根据结果移动时间窗、换延迟、替换来源、改阈值或增加随机 seed。
来源准备、工程 PASS、数学回读有效、描述性声学结果和算法晋级分别记账。

## 3. 工程失败如何闭环

原失败仍在各自执行 SHA、Actions run/job 和完整日志下保留。实际修复仅覆盖已经出现的运输或接线缺陷。
以下不是声学失败的豁免，也不是允许扩大复跑预算。

| 真实故障 | 修复与保留 |
| --- | --- |
| S2-A / B2-S2 / BA2 原 artifact 运输与原件读回 | [S2-A](CI_S2A_ARTIFACT_READBACK_20261128.zh-CN.md)、[B2/BA2](CI_B2S2_BA2_ARCHIVE_READBACK_20261128.zh-CN.md)保留原失败 ZIP；用有界端点请求和已保存原 ZIP 进入原 reader。BA2 实际一次 404 后的既定有界恢复保留，不改科学门槛。 |
| frontend-speech 被 Microsoft APT InRelease 403 阻断 | [精确来源说明](CI_SPEECH_UBUNTU_SOURCE_20261128.zh-CN.md)：只对该步骤现有 ffmpeg 安装命令选择 runner 原 Ubuntu deb822 sources，原签名校验/安全源保留，不改系统全局源。实际后继执行证据以最终 head/main 为准。 |
| 83fa AP helper 被旧运行时观察器拒绝 | 真实 C 编译成功，但工程调用前失败；原 ZIP/ELF/完整失败日志保留。仅为已封存数学 helper 提供可证明的无 DT_NEEDED ELF 严格分支，校验实际 ELF/dynsym/export/弱符号与原 ldd，并检查本进程映射；SDK 非空依赖仍严格验证。 |
| fast-code 旧 Git 读取失败与后继外来 context 拒绝 | 83fa 原 exit128 的 fatal stderr 未保存，不能事后编造；637 后继 R11 明确拒绝 step-wide 外来 Git 配置。修复将精确 safe.directory 限定在五条研究 tiny 的 subshell，保留旧 R11 拒绝。 |
| e118 宿主 workspace 与容器路径不同 | 原日志明确配置 `/home/runner/work/...`，实际检出 `/__w/...`，前检 exit128；R11 已通过。后继仅使用经当前物理 cwd 核对的容器 workspace 精确目录，保留五命令作用域及失败传播；不能设通配或降低 gate。 |
| 独立 F05 外层 wrapper 属性名预检失败 | 原错误在真正 verifier 前发生，原脚本和日志保留；仅修正外层 `_NATIVE_STATE` 引用。真正原 verifier 首次执行 386.974969 s 通过，0 SDK/codec/compiler，没有重跑矩阵。 |

59 个 DSP/build/CLI 固定文件与 3 个 canonical 数学文件保持原字节。后续 CI 接线和结果提交不能重标 637 测量身份。
最终集成仍须在受保护 main 上使用严格 `summary` App 15368、精确 head/base、适用 checks 与审查状态；
按 squash 合并后，再取得**实际新 main** 的完整适用结果。此前 main 4eec 的真实 Verify 失败不改写为成功。

## 4. 长期使用路径与归档边界

新的研究先选择单一问题，再按既有 authority 确认代码/权重/输入/执行/发布角色，冻结来源、假设、
算法边界、时轴、指标、预算和停止条件。C/C++ 仅在 GitHub Actions 构建；之后使用对应 CI 原件做
明确授权的宿主工程与固定研究。输出失败码、完整日志、负值/null、原来源和完整依赖与成功结果一起封存。
由独立进程读回确切源码、原输入、输出和数学定义，最后再写研究结论与下一问题。

已有长期原件包包括 D1/D2、F05 材料审计、AEC3、RIR、F05 完整来源和本次 F05 双麦证据。
新 F05 包还保留成功 AP 原 ZIP/inner tar、宿主工程、CI helper、一次性执行日志、独立回读、
wrapper 预检失败和带前提的原 Git 增量。它不复制整个仓库或操作系统，也不宣称无条件全环境离线重建。
保存定位、最终大小/SHA、最后 head/main 与 CI 失败/成功完整回执集中记于 [#968](https://github.com/jiying2007/audio-pipeline/issues/968)。

数据角色仍有清楚的边界：F05 专用 harness 只提供固定描述性矩阵，不提供优化入口；
通用 optimizer 对 validation-grade 的旧准入尚不等于跨所有工具不可绕过的角色隔离。
如果后续确需跨工具研究，应先迁移并证明该处显式 data_use 传播，不能把 `sealed_data` 误称为盲集。


## 5. F07：外部参考与诊断已完成，下一项内部结构研究为 NOT_RUN

本轮已完成固定 AEC3/APM 的源码与权利准入、实际构建及跨宿主工程复验、一次冻结的六例 development 对照和独立读回；同时完成单房间实测 RIR 的有限支撑差距诊断。两者支持选择下一项问题，但不构成新算法通过或默认实现替换依据。已披露的六例来自两个材料对的相关事件变体，并从原 post-BF 单通道边界开始：AEC3 的固定远端能量抑制比均值为 33.49 dB，但 p1 的三个 double-before 窗口 SI-SDR 均为 −4.78 dB。这个矛盾优先要求定位近端信息在哪个处理阶段丢失。RIR 诊断则只说明所声明有限支撑模型族的覆盖边界：1 个房间、11 个相关墙状态、22 条固定前两麦视图，在固定约 34.94 ms 支撑下的未覆盖有限记录能量下界为 0.975639%–32.336418%；不能据此解释旧六例的具体双讲损失，或推断 64 ms MDF 尾长不足。[六例原结果](WEBRTC_AEC3_RESULT_20261128.zh-CN.md)；[RIR 原结果与解释边界](DECHORATE_RIR_GAP_20261128/RESULT.zh-CN.md)。

**下一项单一、可证伪的假设是：在已披露的劣化双讲窗口中，AEC3 的线性残余观测仍保留了比 final 输出更好的近端保真信息，主要损失发生于该观测之后的联合输出路径。** 最小 development 研究拟保持原六例、固定 AEC3 配置和原声明窗口，从同一次处理实例同时保存 linear tap 与 final，比较预声明的近端保真指标及幅值敏感误差，并完整保留不利结果。若线性观测也已同样受损，或差值不支持其保留优势，就不再沿用“信息主要在该观测之后丢失”的解释；差值判据、转换规则和预算须在后续独立合同中先冻结，本节不新增数值通过门槛。选择该问题不依赖 F05 reserved-validation 的任何结果，也不允许用其结果反向选择窗口、指标、参数或架构。

固定分发源码已经提供 `echo_canceller.export_linear_aec_output` 和 `GetLinearAecOutput`；后者导出最近约 10 ms、16 kHz 的线性观测。源码先由 `FormLinearFilterOutput` 形成 refined/coarse 残余及其过渡并复制到导出 tap，随后更新状态、在 `E/Y` 间选择输出、估计 residual echo、计算抑制增益并加入 comfort noise。因此，linear tap 对 final 的差值只能解释为 **output selection / residual suppression / comfort noise 联合路径** 的变化，不能单独因果归于 RES；该 tap 也不是固定线性时不变算子的“纯线性真值”。工程先验证 export 开关两侧 final PCM 逐字节相同，再允许声学比较；若不相同，应停止把它当作仅增加观测的比较。linear tap 的幅值单位、转换方法及信号延迟必须依据上游 frame/block 运输路径独立定义，并在声学输入前用有限 near-only 合成 fixture 验证。不能把 API 的 10 ms 帧量当作总延迟，不能直接套用旧 final 的 128 样点补偿，更不能对语音 target 搜索最佳 lag。源码依据见下列固定 commit 链接。

这一选择增加的是处理阶段的信息观测，不重开 GTCRN/UL-UNAS 已拒绝的固定 AP 后置配置，也不换名重试已关闭的简单 AGC/BF 变体。给同一已损伤输出继续换固定后置或增益参数，无法先回答损失发生在哪里；这不是对全部神经模型、增益结构或波束形成方法作普遍否定。[已执行外部配置及关闭范围](EXTERNAL_BASELINES.md)；[D5/D6/D8/D9 等既有边界](LONG_TERM_RESEARCH_PLATFORM.zh-CN.md#8-已关闭范围与下一阶段真实缺口)；[已有 BF/AEC 顺序诊断](BF_AEC_ORDER.md)。

| F07 分项 | 本轮可陈述状态 |
| --- | --- |
| 固定外部参考、原件与独立读回 | 已完成，保留描述性、无晋级处置；不是公共双麦/四麦整链或 SSC305 质量资格。 |
| 原 RIR 有限支撑差距诊断 | 已完成限定诊断；不是模型拟合完成、逐墙因果结论或真实设备校准。 |
| linear tap / final 的工程等价性、独立延迟定义及固定 development 比较 | **NOT_RUN：已选择下一项假设，尚未实现或执行，不冒充新候选已落地。** |
| 根据观测设计新的控制结构、实测 RIR 约束下的模型扩展 | **NOT_RUN：后续内部科研任务，需各自新合同；本轮未生成、调参或晋级候选。** |
| 真实双麦/四麦校准、采样钟与非线性换能链路、SSC305 deadline/RSS/功耗/热稳态 | 独立物理资格边界，仍需实际设备证据；不以缺少设备阻止前述可在内部完成的观测与结构研究。 |

### 固定上游源码依据 / Pinned upstream source anchors

以下依据来自已验收的 freedesktop `webrtc-audio-processing` v2.1 分发 commit `846fe90a289f58b7c9303a635142aa2c7caa93e5`，不把分发 commit 当作原版 WebRTC commit，不声称重新检查了这些网址的当前在线状态。归档与源码身份见 [源锁](../../../.github/research/frontend-evolution-v1/webrtc-aec3-source-lock.json) 和 [分发来源说明](WEBRTC_AEC3_SOURCE.zh-CN.md)。

- [`webrtc/api/audio/audio_processing.h`](https://gitlab.freedesktop.org/pulseaudio/webrtc-audio-processing/-/blob/846fe90a289f58b7c9303a635142aa2c7caa93e5/webrtc/api/audio/audio_processing.h#L203)：`EchoCanceller::export_linear_aec_output`；同文件 `GetLinearAecOutput` 接口及约 10 ms / 16 kHz 说明位于 588–593 行。本拟议比较只延续既有 mono 边界，不外推多通道 getter 资格。
- [`webrtc/modules/audio_processing/aec3/echo_remover.cc`](https://gitlab.freedesktop.org/pulseaudio/webrtc-audio-processing/-/blob/846fe90a289f58b7c9303a635142aa2c7caa93e5/webrtc/modules/audio_processing/aec3/echo_remover.cc#L369)：残余形成与导出在 369–389 行；状态更新、`UseLinearFilterOutput`、残余估计与带 comfort noise 的 `ApplyGain` 在 391–443 行；refined/coarse 选择和 `SignalTransition` 在 477–510 行。
- [`webrtc/modules/audio_processing/audio_processing_impl.cc`](https://gitlab.freedesktop.org/pulseaudio/webrtc-audio-processing/-/blob/846fe90a289f58b7c9303a635142aa2c7caa93e5/webrtc/modules/audio_processing/audio_processing_impl.cc#L1680)：getter 读取独立 linear buffer，经 `FloatS16ToFloat` 输出，不能暗中把返回 float 当作原 S16 样本单位。


## 6. 本轮收口与长期项目的关系

本轮可以关闭具体方法缺陷、关键原件恢复、固定参考和诊断、F05 冻结整链执行与回读、
保留型分支分类及其最终工程集成。下一项内部研究明确为 NOT_RUN；真实几何/时钟/权利原记录、
独立物理房间和 SSC305 资源属于对应数据或设备条件，分别记账，不把全部后续工作笼统写为 blocked。

长期父项 [#657](https://github.com/jiying2007/audio-pipeline/issues/657)继续保留，
不因本次审查闭环而将全部 FE 目标、历史候选或物理资格标成完成。
PR #969 / #971 / #972 的重复承载项只在最终集成主线通过后按“已纳入”关闭，原分支及证据保留。
整个任务的可变工程状态与精确 SHA 以 #968 的实际回执为准，本文不预写未来检查结果。
