# 双麦 D2：原状态轨迹上的有效增益顺序分解

冻结日期：2026-11-07（Asia/Shanghai）。experiment=`FE-DUALMIC-GAIN-D2`，任务 #922。
必须先远程冻结本合同与输入锁，经独立方法审查后才执行；它是由已验证 D1 结果
支持的新测量身份，不是 NS/频域 RES-off，不是候选算法或已关闭 frontier 的复活。

## 原因与待证问题

D1 exact source `31b949c14d473fe8221a4125adf896a75e785644` 的真实 60 例已完成，
独立首次原件复核通过（7,401,395 checks / 27.477176 秒）。A 的 16 个 nominal/weak
双讲公共跨度 NS 联合级增量全正；pair 0 的显著 SI-SDR 下降出现在 AGC。near-only
没有 allow 翻转也有下降，不能直接归因 gate；现有 gain_after 只是状态增益，后面
还经过 unity gate cap、整帧 peak cap 和逐样本 clamp。C 的能量结果不能代替波形
恒等或近端质量结论。

问题是：D1 的指标变化在上述有序算子的哪一步出现？静音状态预充、时变增益、
gate 瞬时限制、peak 限制及硬 clamp 不是同一个原因。D2 不挑其中一个先改算法。
仅做原状态轨迹上的有序条件分解，不将各步差值称为互相独立的因果贡献。

## 父数据与冻结输入

生产字节基线仍为 `4daa7e239eebda11f6c7066df2e851269021112f` / 2.3.63。首次父工件
来自 Frontend Research `42318230362/a1`，artifact `13552165963`，完整 ZIP 404327625
字节，SHA256 `2d72315f28a5801aa6a753bdaefa7c7460c409863430843dbb074cae0efb167e`。

`dualmic-gain-d2-input-lock.json` 从这个已独立通过的原件生成，固定全部 60 case
catalog、顺序、profile、原事件、帧数，以及每例 pre-AGC=`ns_output.f32le`、原
post-AGC=`agc_output.f32le`、`control.csv` 和 A 的 clean-near 参考的精确字节/hash。
同时固定 D1 的 11 个测量依赖身份。数据继续是 disclosed regression，不是新 holdout。

为复用现有测量入口，在新 head/main 的 D1 run+verify 完成后直接使用其相同 taps
和普通库。新父数据的每项必须与上述锁相同，D1 核心实现保持固定，生产目录与
4daa7e2 逐 blob 不变。新父执行 SHA、D2 driver SHA 和首次父来源分别记录，不能
把新父证据重标为旧31b或把旧 D1 的 CI 资格借给新 head。

矩阵不变：A56+C4=60，35,916 帧、5,746,560 样点。每帧160，完整流，不能裁窗
重新初始化。只重放 AGC，不额外执行 AEC/NS，不重生成音频输入或重跑 ASR/KWS。

## 实现和硬前提

直接链接该 fresh D1 plain 的原 `libaudio_pipeline.a`，使用实际 generated header、
库 C_DEFINES/C_FLAGS/C_INCLUDES；实际编译器/flags、程序/库/hash 全部记录。不能
使用五函数重命名的 observer 库。生产 AGC 和配置不改，参数取原 CALL/ASSISTANT
defaults：target=-20/-18 dBFS、limiter=-2 dBFS，并核其真实读取值。

Python 把原控制轨迹精确转为每帧16字节小端记录：allow(uint32)、reset(uint32)、
gain_before(float32)、gain_after(float32)。原九位十进制 round-trip 成 Float32；
禁止用近似容差代替原状态匹配。reset 只来自原 `cli_discontinuity`，在 frame300
处理前交付；echo_path_change 不 reset AGC，不按 AEC reset 或 gate 翻转 reset，
不额外喂 lost_frames 个零帧。

每帧真实 `ap_agc_process_controlled` 恰好调用一次。before/after 状态和最终 Float32
输出必须逐字节复现 D1，完整60例都通过才允许解释分解。重建的目标/alpha/预计
状态只作只读观察，按原运算顺序和编译 flags 与真实状态核对；不写回真实状态。

同一条真实状态轨迹上保存四个 Float32LE 视图：

1. `state_only`：pre-AGC × 原本更新后的 state gain。
2. `gate_capped`：使用原 allow 后的应用增益上限。
3. `peak_capped`：再施加原整帧 peak ceiling。
4. `replay_final`：真实库的最终输出，包含原逐样本安全 clamp。

这些是有序观察视图，不是四个独立适应的处理器或四个可部署候选。特别是第一步
的真实状态已受到原 allow 对 target 的限制，不能把 state_only 称为完全无 gate。
中间视图允许幅度超过1，不做S16量化或响度归一，不当可播放/可发布输出。

逐帧分别记录 input RMS/peak、原 target、allow-capped target、alpha、state before/after、gate-capped gain、
peak-capped applied gain、cap 标志、最终 clamp 计数；非有限值、错误长度/顺序/
标志、状态或最终输出不等都失败，保留失败而不更换输入或增加容差。

## 测量定义和判读

所有 AGC 输入/视图都保持 D1 的160样点处理偏移，共同比较物理跨度 `[0,N-160)`，
buffer 使用 `[160,N)`，完整固定每秒窗、最后一窗截于N-160。没有新 lag 搜索。
只调用已冻结 D1 `measure_lane` / `stage_delta`，其中 SI-SDR 来源仍为唯一 canonical
`si_sdr_span`、RMS/peak 仍为 D19 方法；不复制新的声学评分器。

A 使用原 clean-near/32768，零能量为null。C只报能量、峰值和实际增益控制，
不使用混合 duplex_mono 冒充 clean truth，也不输出新 CER、FRR/FAR、时延或听评。
原 D1 分数和旧全链 canonical/中文模型输出保持原样。

依次比较 pre→state→gate→peak→final，每步的数值差只在这个固定顺序、原状态
条件下成立。若最终 clamp 不改变样本，不能叫硬削波；若 gate 不改变所选帧的
应用 gain，不能叫 gate 造成其差异；状态增益的时变也可能是预期电平控制，
SI-SDR 的下降不自动等于识别/听感损失，更不自动支持移除 AGC。

后继结构干预需另冻结，不能由这份新增测量方法同时批准候选。禁止重扫旧 lower
paired AGC/limiter、15 dB global cap、error-adaptive release，或修改本轮原阈值。

## 预算、独立验收和落地

D2 build、全部60例 run、analysis、verify、独立原件readback各300秒；每一完整
阶段包含哈希与末端写盘的 deadline guard。复用现有 Frontend Research job，
**原总20分钟预算不增加**；D1已冻结的各阶段预算也不变。实际C/DSP只在Actions
执行，不启动新Codex任务。CI保存lock、父数据绑定、实际构建证明、全部views/
控制/命令/结果/失败；D1的完整原件仍保留。

通过条件仅为 `GAIN_DECOMPOSITION_VALID_NO_PROMOTION`：父输入锁完整、原状态和
输出全byte复现、顺序算子重建、样本/计数/预算全部有效，并经独立原件审查。
任一测量失败为 `MEASUREMENT_INVALID`，不得把它改判为算法拒绝或质量通过。
合并前检查实际head/base/适用checks/required summary，protected squash后新main
重验。没有真机、真实WAN、MOS、泛化质量晋升、发布或tag。
