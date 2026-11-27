# dEchorate 实测 RIR 的有限支撑差距诊断 V1

新身份 `FE-SIM-RIR-SUPPORT-GAP-V1`，执行总项 [#968](https://github.com/jiying2007/audio-pipeline/issues/968)。
本页与[机器合同](../../../.github/research/frontend-evolution-v1/dechorate-rir-gap-v1.json)
是执行前方法，不是声学结果。主线基线为 `4eec2329be9f2138c7ac73e8dd59026f3dc0a3ba`。
真实 RIR 的能量分析须在独立审阅和公开冻结源码后执行；源码/元数据准备与 tiny 测试可以先完成。
本实验不重开 S003 或 I025–I040，不改变 motion-v2、历史锁、分数或算法候选。

## 问题与独立观测

现有 motion-v2 使用直达声与六个一阶墙面镜像、16 kHz 两抽头线性分数延迟。
它没有扩散晚尾，也没有真实换能器的完整响应。本实验量化：在同一已披露物理房间中，
即使允许任意整体时移和任意路径幅度，这类**预声明 c=343 m/s 模型**的有限时间支撑
至多能覆盖多少原 RIR 能量？结论只适用于该模型族；343 不是本次实测声速或普遍物理下限。

观测必须是原 SOFA 的 `Data.IR`。`dEchorate_annotations.h5` 中的 `echo_toa/echo_amp`，
以及 SOFA `EchoTimings`（若存在），不是本实验的独立观测。
官方固定 revision `d3e664f1e7a7d46241d7f7b3b3761448686b9537` 的
`main_geometry_from_echo_calibration.py` 从经声学回推校准的坐标生成镜像与这些注释。
原论文 §2.3 也说明几何与峰标注经过迭代校准。用同一公式比较这些注释会造成自证。
本实验不读取这些到达时间/幅度数组来评分，也不使用回推坐标作独立几何真值。

## 原件、房间和元数据边界

复用原[12 对象锁](../../../.github/research/continuous-optimization/development-v3/dechorate-source-qualification-v1.json)：
11 个 `src1/arr1/mics1-5` SOFA 与原 annotations HDF5，总计 **19,403,164 B**，逐对象原大小/SHA256不变。
下载入口为 [原 SOFA 目录](https://www.sofaconventions.org/data/database/dechorate/)，
当前官方镜像为 [sofacoustics](https://sofacoustics.org/data/database/dechorate/)。
数据来自 [固定 Zenodo 记录](https://zenodo.org/records/5562386)，按原 CC-BY-4.0 声明保留出处与
[论文](https://doi.org/10.1186/s13636-021-00229-0)；SOFA 内嵌 MIT notice 也原样保留。
这些许可不推导 WSJ 语音、任意新录音或训练用途。

11 个文件名 token 是同一物理长方体房间、相同 source/array 的相关壁面状态，包含家具状态。
它们不是 11 个独立房间。旧 S003 已消费这组材料，本次角色仍为
`disclosed-development-diagnostic`，不生成新 holdout 或新的说话人数据。
原 reader 材料化并检查 11×5=55 条 native RIR 的有限性；仅固定前两麦的 **22 条视图**计分。
不按观测选择状态、麦克风或窗口，不把两麦视图和多状态当作独立样本计置信区间。

本轮只读结构检查发现并保留以下原件事实：

- 每份 `Data.IR` 均为 `[1,5,48000]`、float64、48 kHz，`Data.Delay` 全零。
- `ReceiverPosition` 数值等于 annotations 的全局 `microphones`；官方 exporter 直接写入这些值。
  本文件组不能再次叠加 ListenerPosition 或 ListenerView/Up 旋转。该事实用于来源审计，
  不把这些经声学校准的坐标提升为独立真值。
- 文件名/Title 为 src1/arr1，实际 `SourceShortName=loudspeaker_id:1`、
  `ListenerShortName=array_id:0`。保留此编号，不按字面索引猜测另一个 source/array。
- 11 份 `RoomDescription` 都写成 `room_code:020002...`，与其它十个文件名状态不符。
  `RoomTemperature=0 kelvin`、`RoomVolume=0` 是占位值。保留矛盾，以冻结文件名作分层标识，
  不由这些字段作逐墙因果或温度估计。

只用原 `RoomCornerA/B` 与 annotations 一致的名义尺寸 `[5.705,5.965,2.355] m` 限定模型族。
原 bIPS 坐标与墙原点的转换不参与评分；官方 346.98 m/s 只留在来源背景，**不扫描其它声速**。

## 固定支撑界与唯一主指标

对长方体内部任意源位置 $s$、麦位置 $r$ 和任意一阶墙镜像 $s'$，由三角不等式：

$$
\lVert r-s'\rVert-\lVert r-s\rVert\leq\lVert s'-s\rVert
\leq 2\max(D_x,D_y,D_z).
$$

因此无需确定某个回推坐标、最强峰或实际 sample-zero，就能给该固定模型族一个保守支撑跨度。
全部六个墙面均保留，吸声/家具标签不改变窗口。再保守加入原 16 kHz 两抽头插值核的
完整 `2/16000 s` 支撑和一个 native 端点 bin：

$$
L=\left\lceil\left(\frac{2\max(D)}{343}+\frac{2}{16000}\right)48000\right\rceil+1
=1677\ \text{samples}.
$$

对每条原始 48000-sample RIR，冻结：

$$
E=\sum_{n=0}^{N-1}h[n]^2,\quad
C=\max_{0\leq a\leq N-L}\frac{\sum_{n=a}^{a+L-1}h[n]^2}{E},\quad U=\max(0,1-C).
$$

`C` 是**预声明的 oracle 能量覆盖上界**，确实允许从波形选最佳整体时间位置；并列取最早位置。
它不是 SI-SDR 对齐、直接声标注、传输 lag、七抽头拟合或候选选择。
连续区间比真正七个稀疏路径更宽松，所以 `U` 给出该有限支撑族在原有限记录中仍无法覆盖的能量下界，
在明确的浮点舍入精度内解释。即使 `U=0`，也不证明七路径能拟合该 RIR。
不以正负门槛判定声学 PASS，不调整 L、声速或参数使结果有利。

原记录上的 `[0,5),[5,20),[20,50),[50,100),[100,200),[200,1000) ms` 六窗仅记录能量分配，
以归档 sample-zero 为坐标；不擅自命名为直达/早反射/晚混响。
`Data.Delay=0` 不证明 ESS 反卷积和旧 recording-offset 补偿后的物理激励原点。
绝对 t0 保持 **UNKNOWN**，到达误差为 `null`，不从真实 RIR 拟合 t0。

未覆盖能量可能来自高阶/扩散房间响应、换能器响应、测量链、录音噪声和有限记录。
不将其全归因于混响，不作绝对 SPL、设备 gain、独立房间泛化、听感或算法效果结论。
零总能量、非有限/溢出、短于 L 的 IR 均失败；不补尾、不重采样、不归一化、不减噪声。

## 复用、命令与证据

复用 `build_dechorate_artifact_exclusion_corpus.load_frozen_rirs` 的原 hash/采样率/有限性/两麦选择；
其 `build_validation_corpus` 依赖与 motion-v2 原文件均精确 pin。
不调用旧 S003 builder、旧 qualification 工作流或 motion-v2 的场景生成。
motion-v2 的 `path_state` 固定近距刚性设备，不能直接冒充本数据的任意阵列几何；此处使用上面的
小型解析支撑界。tiny 另直接检查原 `sample()` 的两抽头支持与 343/16k 常量。

```sh
python3 -B tests/validation/frontend_evolution/test_dechorate_rir_gap.py

# 仅在方法公开冻结后，在精确源码的干净检出执行一次：
python3 -B tests/validation/frontend_evolution/dechorate_rir_gap.py run \
  --input-dir /absolute/original-12-objects \
  --output /absolute/new/rir-support-gap \
  --execution-source "$actual_frozen_source_sha"

python3 -B tests/validation/frontend_evolution/dechorate_rir_gap.py verify \
  --output /absolute/new/rir-support-gap
```

tiny 仅使用显式 synthetic 数值/运输反例，支持 Python 3.8 语法，不读取真实 IR；真实 HDF5 入口需
NumPy/h5py，记录实际 Python、依赖/HDF5 版本及已加载 native module hash。
本次准备宿主使用 NumPy 2.3.5/h5py 3.15.1；这不是其它宿主已执行的证据。

单次分析预算 **90 s**，CLI 用 Unix wall timer 限时；0 自动重试、0 DSP 候选、0 搜参。
输出必须为 checkout/input 之外的新目录。
包内保留原12对象、完整测量代码闭包、source SHA、metadata矛盾、22逐条结果、runtime与全量manifest。
独立 `verify` 从原 Data.IR 重算全部指标、样本/状态/麦角色与结论；修改 score 或外围manifest不能
替代原输入/源码 hash。失败留下 `failure.json` 和部分材料；即使重新封外围manifest，也拒绝把失败包
回读为成功。失败后不改窗口或声速重跑这个身份。

唯一成功含义为 `MEASURED_DESCRIPTIVE_RIR_SUPPORT_GAP` / `VERIFIED_DESCRIPTIVE_RIR_SUPPORT_GAP`，
决定保持 `DESCRIPTIVE_ONLY_NO_PROMOTION_NO_MODEL_FIT`。
这项数据侧诊断可为下一份仿真合同提供真实差距，不声称现有仿真已完成物理校准。
