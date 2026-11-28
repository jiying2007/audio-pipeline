# FE04 AEC3 最终合成输入选择：合同草稿

实验身份：`FE04-WEBRTC-AEC3-SYNTHESIS-SELECTION-V1`。日期：2026-11-28，北京时间。
跟踪：[#977](https://github.com/jiying2007/audio-pipeline/issues/977)。基线为受保护 main
`9d2cfef495ac8e34d03a55538777c16010ac3b14`。
本草稿只完成方法设计；尚未公开冻结，新增科学、工程 DSP、编译调用均为 **0**。
机器合同见同目录 `webrtc-aec3-synthesis-selection-v1.draft.json`，静态源码摘要见 `source-time-axis-review.json`。

## 问题与单一干预

检验原 p1-none / double-before 窗口的近端损伤是否包含最终合成前 E/Y 选择的贡献。
数据仍为公开开发诊断，唯一主条件数为 1；F05 reserved 不参与选择，不能形成独立确认或晋级。
F07 原方法、原六例、结果、失败和原始 PCM 全部保持不变。

改编源继续固定 `webrtc-audio-processing-2.1` 分发 commit
`846fe90a289f58b7c9303a635142aa2c7caa93e5`。
只在独立研究变体中增加默认 false 的
`research_synthesis_selection.observe / force_linear`，并在 `echo_remover.cc` 最后局部
`Y_fft` 选择处使用 `source_linear || force_linear`。
**不得修改 `UseLinearFilterOutput()` 或 `UsableLinearEstimate()`**，否则会连带改变残余估计路径。
所有自适应、refined/coarse 选择、状态、残余估计、GetGain、CNG、FFT/OLA、量化和时序保留原代码。
原分发源与补丁后源分别记录哈希，不能把修改后的库称为原版参考。
保留原宏 `WEBRTC_APM_DEBUG_DUMP=0`、`NDEBUG`；不借开启 debug dump 获取观察。

## 严格顺序与停止规则

1. 公开冻结精确方法、实现和预算；Actions 新工程、当前宿主新工程及来源/二进制核验完成。
2. **仅一次**处理原 `p1-ula4-70-fir33-none` 的 16 秒输入，模式 `observe`。
   完整 final S16 与 linear F32 必须逐字节等于 F07 原件；不相同则立即方法失败，不查看分数救活方法。
3. 核验全 4000 条状态，再检查主窗口的 451 条合成支持状态。
   全部默认选 E 时记录 `NO_SELECTOR_Y_EXPOSURE_IN_PRIMARY_SUPPORT`，**不执行 force-linear**，本阶段科学问题收口。
   这只排除本次主窗口局部合成 E/Y 的作用，不能排除 refined/coarse 或同状态驱动的估计器选择。
4. 只有支持范围出现 Y，才允许同一二进制、同一输入再执行 **一次** `force-linear`。
   完整 linear、4000 块 source flag、G 位、high-band gain 位和 nearend flag 必须与 observe 相同。
   保留所有原固定窗口的候选与观察输出差值、远端代价和 null；不追加案例、不搜索参数。
5. 独立原件读回不执行 SDK、codec、compiler、native metric 或 ldd；输出缺失、身份漂移、丢块均不能标 PASS。

## 精确时轴及 OLA 前驱

FrameBlocker 初始为空，把两个 80 点子帧拆成连续 64 点块；1600 个 160 点 API 帧形成 4000 块。
每块 k 的 FFT 使用前块与当前块 `[k-1,k]`；ApplyGain 输出 `z_k` 由本次 IFFT 前半与上次 IFFT 后半相加。
它名义上对应目标块 k-1；BlockFramer 初始 64 个零再增加 64 点。
因此 linear 固定延迟 64、final 固定延迟 128，不能从语音目标搜索 lag。

| 对象 | 半开区间 |
| --- | --- |
| 主目标样本 | [97600,126400) |
| 对齐 final 样本 | [97728,126528) |
| 目标 64 点块 q | [1525,1975) |
| 产生这些样本的 z_k | [1526,1976) |
| 当前和前驱选择状态并集 | **[1525,1976)，451 条** |

最后一块 1975 和第一块 1525 都不能遗漏。
`block_index=block_counter_-1`，全 trace 必须从 0 连续到 3999。
其 API frame index 可由 `floor(((k+1)*64-1)/160)` 推导，无需再引入独立计数时基。
该证明只覆盖局部合成选择的影响支持，不表示全自适应历史只有两个块。

## Trace 与中性证明

每行原始 stderr JSON 固定九键：
`kind, block_index, source_linear, applied_linear, forced, capture_output_used, gain_bits, high_bands_gain_bits, dominant_nearend_after_gain`。
`forced` 指该块实际由默认 Y 改选 E，不是模式开关；因此 force 模式下它等于 `!source_linear`。

G 的 65 个 binary32 原始位与 high-band gain 使用 `memcpy` 到 uint32，不能数值转换、重算 GetGain 或修改状态。
读取发生于 GetGain 后、ApplyGain 前；`dominant_nearend_after_gain` 也是更新后的状态。
**本块 ResidualEchoEstimator::Estimate 在更早位置消费的是 GetGain 前状态，不能混称。**
这些副观察只用于精确中性见证和保留后续研究材料，不增加主判据或自动选择参数。
预登记的副摘要仅为固定 451 块×65 个 G 的等权最小/最大/均方，以及该 451 块的 nearend true 计数；不作为声学效果。

拒绝缺块、重号、乱序、重复 JSON 键、未知字段、bool 冒充整数、非法 uint32、非有限或越界 gain，以及 capture_output_used=false。
若 capture output 未使用，原生代码不得读取未初始化 G/high gain；该科学调用应按真实失败保留。
每次 stderr 上限固定为 16 MiB。只读 trace 位相同是补充证据，不能代替局部无反馈源码证明。

## 指标、工程和预算

条件候选与 observe final 都使用原固定 128 点延迟。沿用 F07 canonical SI-SDR、无增益拟合 NMSE、1e-12 可识别性地板、
四个 near 窗口、[192000,222400) 的 19 个 far 块，以及 [0,255872) 共同区间。
主窗口仅在 SI-SDR 增大且 NMSE 减小时得到描述性支持；反向或混合按原方向规则保留，无新增声学数值门槛。
缺失尾部不补零，不改旧计划。all-E 停止分支不能虚构候选输出或候选声学分数。

新 tiny 工程：6 个有效进程共 4 秒，8 个 DSP 前拒绝请求；其中 overlength 真实负例为 16.01 秒。
所以全部请求预算为 **20.08 秒/321280 点**，实际 DSP 预算仅 **4 秒/64000 点**；14 进程、120 秒墙钟、0 重试。
验证 off/observe 中性、force 仅改 selector、逐块状态位相同、重复确定性、前缀因果、无重置及异常输入拒绝。
不重跑历史 62/25 个工程调用，也不重跑旧六例科学矩阵。

科学上限为 observe 1 次 + 条件 force 1 次：最多 32 秒输入、3200 API 帧、8000 内部块；每次 30 秒、整阶段 300 秒、0 重试。
全 E 时实际只有 16 秒/1600 帧/4000 块。独立读回 300 秒；C/C++ 构建仅在既有免费 Actions 路径。

## 来源与交付

执行前后绑定公开精确源码、完整方法控制文件、冻结合同、原始输入、补丁前后源、runner、库和实际宿主动态依赖。
保留 CI run/attempt/artifact/API hash、真实命令、独占输出和仅一次调用见证。
受保护 PR head 适用检查通过后 squash，随后验收真实 main；科学原件与独立读回分别归档。
负结果或无暴露停止均可完成本阶段；真实阵列、SSC305、产品默认、听感和识别资格不由此成立。
