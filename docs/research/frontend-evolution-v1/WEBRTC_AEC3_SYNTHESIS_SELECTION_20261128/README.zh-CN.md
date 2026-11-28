# AEC3 合成输入选择：单次 force-E 在披露主窗未获改善

**`NOT_SUPPORTED_IN_DISCLOSED_WINDOW`；科学阶段按冻结条件完成，`NO_PROMOTION`。** 主窗 451 个 OLA 支撑块全部选择 Y，按预登记规则允许并实际执行一次 force-E。相对原选择 final，主窗 SI-SDR **下降 0.021467133537 dB**、归一化 MSE **增加 0.000480244201336**，两项均向不利方向变化。

整条 final 输出的 **16936/256000 个 S16 样点改变**，说明局部选择干预有非零输出影响，但单独 force-E 未修复此预登记主窗。该结果不能解释为“选择器没有作用”，也不能据此单独归因 RES、抑制增益或舒适噪声。

实验 `FE04-WEBRTC-AEC3-SYNTHESIS-SELECTION-V1`；[冻结方法](../WEBRTC_AEC3_SYNTHESIS_SELECTION_V1.zh-CN.md)、[原始机器结果](result.json)、[独立回读](independent-readback.json)。整合与交付收口见 [#977](https://github.com/jiying2007/audio-pipeline/issues/977) / [PR #978](https://github.com/jiying2007/audio-pipeline/pull/978)。

## 冻结问题与主结果

假说是：最终合成阶段默认 E/Y 输入选择对已披露的 p1-none `double-before` 退化有贡献；仅在精确合成支撑内观察到 Y，才执行一次局部 force-E。E 为既有线性残差分支，Y 为该阶段捕获分支；干预只改最终合成输入的局部选择，不改 `AecState` getter 或共享状态。

唯一条件为原 F07 `p1-ula4-70-fir33-none`，16 kHz 单通道、16 秒。每次实际完成 **1600 个 API 帧、4000 个内部块**；原选择整段为 **4000 Y / 0 E**，主支撑 `[1525,1976)` 为 **451 Y / 0 E**。顺序为一次 observe → 写入 support gate → 一次 force-linear，原选择状态在第二次中仍为 Y。没有 all-E 提前停止，也没有额外变体。

主目标窗固定 `[97600,126400)`（6.1–7.9 秒），28800 样点。final 固定延迟 128 样点，linear 为 64 样点；上述 451 块包含所需前一 OLA 块。没有新 lag 搜索、幅度拟合或事后窗口调整。

| 主窗视图 | SI-SDR（dB） | 归一化 MSE |
| --- | ---: | ---: |
| 原选择 final（observe） | -4.784093017112 | 0.781266469301 |
| force-E 后 final | -4.805560150649 | 0.781746713503 |
| linear（两次逐字节相同） | 16.407677261935 | 0.022612232836 |

精确 candidate-minus-observe delta 为 `-0.02146713353725893 dB` 与 `+0.0004802442013360775`。两个 final 投影目标能量分别为 `0.003932996378698194` 和 `0.0039267759651274705`，均有限且大于冻结的 `1e-12` 可识别性界限。本次满足冻结负向规则“SI-SDR delta ≤ 0 且候选 MSE ≥ 原值”。表格仅舍入展示，原始数值与规范 floor 完整保留；不作统计显著性或听感判断。

## 控制量与其它固定结果

- observe 的完整 final S16、linear F32 与 F07 原件逐字节相同；两次科学调用的完整 linear 也逐字节相同。所有已记录上游控制字逐块一致：原 `source_linear`、`capture_output_used`、65 个 `gain_bits`、`high_bands_gain_bits`、`dominant_nearend_after_gain`。这不声称已导出所有隐藏内部状态。
- 原 RES、nearend、增益计算及历史、CNG、FFT/窗/OLA 和 S16 转换保持实现。主支撑 29315 个 gain 值的预登记等权摘要为 min `0.0007260758429765701`、max `1.0`、mean(G²) `0.03734942424540729`；post-GetGain nearend 为 true 的块为 **0/451**。这些描述不直接识别声学因果；post-GetGain 标志不能代替此前 RES 使用状态。
- 固定次要 `double-after` 的 SI-SDR delta 为 `+0.0026145542124480503 dB`、MSE delta 为 `-0.0000635005821963408`；near-initial、near-final 的指标不变。共同跨度 `[0,255872)` 的对应 delta 为 `-0.0009834644414139504 dB`、`+0.000049381270177395464`。次要改善不替换预登记主窗结论。
- 固定 far-only `[192000,222400)` 保留全部 **19 个 1600 样点块**。final 聚合 echo/output 能量比 `27.512950467837094 → 27.557900086780514 dB`；逐块 **12 个上升、7 个下降、0 个相同、0 个 null**。linear 聚合值两次均为 `10.014981867328355 dB`。这是 far-only 能量比，不能写成双讲 ERLE。机器结果保留全部四近端窗、19 远端块、共同跨度、幅值/端点和可识别性字段。

## 实际预算、来源与回读

科学阶段实际为 **observe 1 次 + 条件 force-E 1 次，各 16 秒；合计 2 次、32 秒、3200 API 帧、8000 内部块、0 声学重试**。有效独特条件只有 1；数据角色 `DISCLOSED_DEVELOPMENT_DIAGNOSTIC_NOT_HOLDOUT`，`independent_confirmation=false`。未使用 F05 保留数据，没有训练、参数搜索或本地编译。同宿主前置工程另有 14 个合成进程，有效处理 64000 样点（4 秒），8 项请求在 DSP 前拒绝，`PASS_SELECTION_ENGINEERING_ONLY`，不计作新科学语音证据。

实际科学源码 **`dd2a416a155cc34164ccf86ace5fe110bca03992`**，tree **`859eb10c94e71c44a1bb8130d6472b311c77332c`**；[该 source 的冻结计划](https://github.com/jiying2007/audio-pipeline/blob/dd2a416a155cc34164ccf86ace5fe110bca03992/.github/research/frontend-evolution-v1/webrtc-aec3-synthesis-selection-v1.json)。上游固定 `webrtc-audio-processing-2.1` / `846fe90a289f58b7c9303a635142aa2c7caa93e5`；本次使用独立识别的研究派生版本，pristine 与 patch 原件保留。

**首次 CI 失败保留：**初次公开方法 `b50ef4fcafe8f2f0b46361a9c348906fd0721da1` 的 [Verify 46100428395 / attempt 1](https://github.com/jiying2007/audio-pipeline/actions/runs/46100428395) 在 impact `140841379416` 因新方法文件 `:548: new blank line at EOF` 失败。观察新科学 trace 前，直接后继 dd2 只删除该末尾一个 LF；冻结计划、方法语义、checker/政策和历史原件不变，完整 protected-base 检查 `STRICT_PASS` / 0 exceptions，15 项方法测试通过。首次 CI 失败及 b50 成功原生工程继续保留。

修正后的 [Frontend Research 46100892912 / attempt 1](https://github.com/jiying2007/audio-pipeline/actions/runs/46100892912) 真实工程 artifact **15245183893** 经准入后用于宿主工程与科学：ZIP **11485326 bytes**，内部工程 tar.gz **5034548 bytes**。科学执行完成于 2026-11-28 11:05（北京时间，UTC+8）。

冻结方法回读为 `PASS_INDEPENDENT_SELECTION_READBACK`；另一个预封存 stdlib reader 首次执行为 **`PASS_INDEPENDENT_RAW_RECALCULATION`**，从 JSON/trace/PCM 重算全部已报告指标，**数值容差 0**，核对 **2485 个 manifest 成员、45 个源码控制文件**及完整 F07/来源/预算。无项目评分函数导入，SDK、编译器、codec、ldd、native metric 和子进程/网络调用均为 0；独立外层一次调用见证也通过。独立字节回读不构成新的独立数据确认。

| 原件 | SHA256 |
| --- | --- |
| 冻结计划 | `42f650eec3f9dd793cf9d859fc973d831a7aa62224f6023eceb8f83ad2b93d5c` |
| 科学 result.json（133004 bytes） | `d099931f9c526db499912a62e14237602d598f74377b8c4dad8efb9751e0827d` |
| 科学 manifest.json（403363 bytes） | `9ca7385bd0374f4feb80bc100b67f42b17be11527afbd298bcb0b9e0dc82fee5` |
| independent-readback.json | `b718f9a2aa5d4b83f60c04d7daf7cd89ffb6b60b5dffc648e9f5d8651797516d` |

处置保持 `DIAGNOSTIC_DIRECTION_ONLY_NO_PROMOTION`；本页记录该有限科学阶段，不产生默认推广、物理机器人或 SSC305 资格。最终整合与证据交付事实由 #977 分别记录。
