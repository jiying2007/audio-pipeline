# FE09-B3-F0 — C4/16k 来源方 Render 缺席与重入的有限实际链组合

**草案状态：DRAFT_FOR_ROOT_REVIEW_NOT_EXECUTION_ADMITTED。** 身份 `FE09-B3-F0-C4-16K-RENDER-PAP-V1`。父任务 [#733](https://github.com/jiying2007/audio-pipeline/issues/733)，已批准计划 [#657](https://github.com/jiying2007/audio-pipeline/issues/657)。本文件和并列 JSON 是供 root 冻结的具体预注册提案；尚无新子 issue/branch/PR、实现或实验。本草案不自行通过审查。

## 1. 一个有限问题

在 Capture 连续、Render 由独立来源方真实报告 PRESENT/ABSENT 时，既有四路 Capture SRC/FIR33 能否与**实际不改算法的 mono CALL SDK**组合，保持 Capture 前端连续，执行实际 SYNC/Activity/DTD/AEC/frequency RES/NS/AGC/VAD，并正确处理缺席、重入、原子拒绝和固定时延记账？

固定一条图：原始 `fe09_b1b0_src`、`fe09_b1b1_single_bf` 经已存在的 `fe09_b2s3_t2b_b0_capture_only` 和 `fe09_b2s3_t2b_b1s0_owner_spsc`，进入 R0 同样的饱和 Float32→S16 边界，再调用真实 mono SDK。mono 使用 CALL/standard、16k→16k、mic_channels=1、清除 AP_STAGE_BF，实际 stage mask=0xfd、FULL/MDF/SCALAR/EMA；不得双重 BF。独立 Render SRC 只处理真实 PRESENT PCM。

这不是新的算法候选、BF/AEC 顺序比较或声学优胜筛选。源码完整锁在 `source-lock.json`，可复算的输入/控制/预算锁在 `test-contract.json`。

## 2. 固定数据与两个案例

仅 D0 第一方确定性整数合成。四麦 ULA 坐标 X=0/35/70/105mm，方向(0,1,0)，identity slots、单位 gain、零校准延时、全 mask。每帧160样本，共600帧；相同 Capture PCM 用于两个案例。

| 案例 | 来源方事件 | 下游显式通知 |
|---|---|---|
| ALL_P | 1..600 全部 PRESENT，epoch1 | 0次 |
| PAP | 1..200 PRESENT；201..240 ABSENT；241..600 PRESENT | 第201和241帧处理前各一次 RENDER_GAP，lost_frames=1 |

PAP 第241帧的真实 Render 必须携带原始 owner 合同的 RENDER_GAP、epoch2。ABSENT 仍属 epoch1，reason 必须为 source-reported，无 PCM、无 hash、无 gap flag。每次调用只让一个真实 Capture 帧前进；Render 无事件为 PENDING，不能当作缺席。

输入采用固定 LCG、640样本回声延迟、固定四分之一回声比例、独立弱噪声，161..280帧加入固定近端合成分量。精确公式、种子和 C99 整数舍入写在 JSON。PAP 表示**参考样本投递不可用**，Capture 仍含原先合成的远端回声；不声称 DAC 静音或硬件共同时钟。真实 Activity 决定门控，近端时间表不传入 DSP。生成 PCM 哈希在检查 DSP 输出之前固定；不得因结果调整信号、门控、阈值或 seed。

## 3. 最小 seam 与源码证明的提交边界

只增加私有 `bind` 和 `process_one` 两个操作。绑定要求全部状态 fresh、配置固定、arena/input/output/work/receipt 相互按合同分离；每次消费前复核来源身份/generation、有效 mono 配置、长度、边界和 alias。没有新增泛化 discontinuity/reset/rebind API。

原始 owner `process_one` 是最后一个可能正常拒绝的有状态阶段；它已对 BF/reference/tails/output 保证失败不提交。之后的 mono 尾段在冻结配置下有明确源码证明：

- `ap_pipeline_notify_stream_discontinuity` 唯一拒绝前提是空 pipeline 或零/未知 flags；本 seam 只有初始化成功的非空 pipeline 与常量合法 RENDER_GAP。
- `ap_pipeline_push_render` 唯一拒绝前提是空指针、非160长度或没有 SYNC；这些在提交前均验证，ABSENT 根本不调用。
- `ap_pipeline_process_capture` 唯一拒绝前提是空指针或非160长度；提交前验证，随后 DSP body 无失败返回。

因此普通 REJECT/PENDING/FULL 都是 precommit。**若仍出现非 AP_OK，这是 fatal COMPOSITION_INVARIANT_BREACH：立即停止该 fixture，保留部分失败证据，不称原子拒绝、不继续重试、更不算成功。** 不增加对活动 producer 原子对象的快照恢复。最小叶仅以调用者串行运行原有 owner APIs，未另行宣称新 pthread/liveness 资格。

Capture sequence 跳跃、source generation 变化必须拒绝；没有通过现有 owner API取得的 live capture/clock恢复能力。独立案例之间 fresh init 不算恢复。

## 4. Reset、参考与时延必须按真实代码解释

当前 `src/core/ap_pipeline_query.c` 对所有合法 discontinuity 都执行整个 mono 侧重置：边界 SRC、HPF、SYNC、Activity、AEC、RES、NS、AGC、VAD；`lost_frames` 当前被忽略，累计 `processed_frames` 保持。外置 Capture SRC/FIR33 不属于 mono state，PAP 的 Render 边沿不应重置它。

PAP 两次显式 notify 的实际调用/flags/lost_frames/status 由 public notify wrapper 独立观察。总 `aec_resets` 另报：SYNC 自动 route jump 可能额外重置，绝不为了凑2而关闭 tracker 或挑输入。ABSENT 期间不得调用 render push；SDK 自己因缺参考生成零 reference，是算法行为，不是新造来源 PCM。

同一配置下逐项验证：16k 输入 SRC 为 identity；FIR33 common delay22样本；公开 mono latency10ms=160样本。因此固定算法记账和为182样本/11.375ms。它不包含 queue、调度、设备 I/O 或实测端到端延时，也不允许逐例最佳对齐。

现有 APX3 one-frame合同下 ABSENT 没有 Render payload，FBS1保留 owner ID/epoch/reason；不能以全零 PRESENT 代替。本叶不增加 recorder，不把600帧塞进原24-chunk store，也不改原 APX3 writer/CRC/parser。

## 5. 三条互相独立的证据关系

1. **独立直接控制回放**：test路径直接调用原始 T2-B0 与真实 mono API，以字面固定范围201..240和边沿201/241产生预期控制，不调用新adapter的事件分类/控制/receipt逻辑。逐帧比较输出、公开metrics和前端状态台账。这是正确性对照。
2. **观察器透明性**：plain和observed连接同一原库，对相同输入逐帧PCM/metrics bitwise一致。此关系只证明观察没有改变算法，不能独自证明adapter正确。
3. **前端隔离与因果性**：ALL_P/PAP每帧Capture/BF输出及canonical前端历史相同；notify瞬间同一allocation的外置前端bytes不变。额外一条PAP仅反转241帧之后输入，前240帧输出与证据完全相同。

只读 link wrappers 调用原函数恰好一次，记录实际顺序、参数与返回。FULL+NS+RES 的实际 RES 路径在 `ap_ns_process` 中；time-domain `ap_res_process` 必须0调用。记录实际 far/DT如何传到AEC/NS/AGC；frequency_res_active必须服从真实源条件。固定案例要触达 active/inactive、DT和两个AGC许可分支；若没有触达，结论为 INCONCLUSIVE，不能后改fixture。

原 CMake 强制 UNITY_BUILD=ON，内部调用可能无法被 `--wrap` 观察。私有 parent CMake `add_subdirectory` 原项目后，仅对研究构建的 audio_pipeline target 设置 UNITY_BUILD OFF、IPO OFF；plain/observed用同一配方。不改 root CMake。观察目标继承原库真实编译定义，不能用错私有结构布局。每例 observer RAM≤256KiB，实际 sizeof计入台账，回调中只写有界RAM，事后输出文件。

## 6. 有限预算和验收

每个目标只运行11条600帧轨迹：两例plain各2重复、observed各2重复、独立直接控制各1次、未来后缀PAP1次。每目标6600帧；native、ASan/UBSan、AArch32/QEMU三个目标合计19800个成功组合process_capture帧/198音频秒。16个固定API拒绝在已到达的静止检查点或空fixture运行，不额外重放前置音频。独立负控fixture另外有每目标5次成功producer提交（N04一次Capture，N16两次Capture和两次Render），但没有SDK组合帧，必须另报，不能藏成主案例丢帧。8个receipt语义负控另行验证。清单见JSON。

**以上是每一次完整qualification invocation的预算。** 本地只有native/sanitized时只能报部分执行，不能给Arm通过；PR和新的protected main各自独立全量资格，不共享成功。每目标一次CMake配置/构建，一份原库、plain/observed两个binary；不循环构建到成功。

新增阶段共享一个300秒外层截止，所有子命令都取自身上限、外层剩余及原frontend-reference剩余时间（保留60秒归档）中的最小值。**现有15分钟job timeout不变。** 必需工具不可用或预算不足均保留BLOCKED/FAILED；不能删目标、重跑调参或放宽原workflow来取得绿灯。

验收只针对实际阶段执行、明确来源/时序/拒绝不提交、独立对照与可复算证据。输出电平、ERLE有效帧、underrun/自动reset及失败仅作描述，无dB收益阈值。完整资源资格留给定义好这条图后的T3-S3；状态、rollback/work、source queues、观测器、对照和fixture开销分别列出。没有192KiB/10ms SSC305 PASS，也没有C4优胜、公共SDK、HIL/E001或shipping通过。

## 7. 前置和收口

执行前须由root冻结此具体合同，登记独立叶身份，并观察当前protected baseline自己的Verify summary及匹配Release/convergence成功。当前81ee是源码审查身份，本文不把待完成主线门禁写成已通过。

实现使用研究私有路径，复用既有Quality/frontend-reference，不新建workflow。原始失败保留；精确候选head门禁、受保护expected-head合并、独立新main Verify/Release和原始小Artifact外部SHA读回均成立后才能关闭此叶。#733整个B3、#730、#771和其他设备/交付父范围不因此关闭。
