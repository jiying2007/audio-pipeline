# 双用途 profile 接入：实施前矩阵冻结

日期：2026-11-06。身份：`FE-C2-DUAL-USE-PROFILE-REPLAY-V1`。
本文件先于本工作包代码修改与候选执行保存；不是运行结果。

## 来源与范围

- DSP/CLI 基线：`438fe09d79ff768306c00573849517bcd91cbc6e`。
- 共同合同提交：`6056682486c1a2a2c84d77135de8118e07fc8cf3`，见
  [首轮实施合同](DUALMIC_INTERACTION_INTERCOM_V1_PLAN.zh-CN.md)。
- 本工作包只改变现有 `ap_process_pcm` 的 preset 选择和新增研究回放接入；
  不修改任何 DSP 算法、公共 C API、历史 runner、canonical 指标或旧声学阈值。
- `--profile call|assistant` 缺省为 call；显式 tuning 只覆盖相应 mask 位。
  `--capture-profile` 保持原有 stage-isolation 含义。
- 所有新信号为第一方确定性工程信号；不是真人、中文 KWS、真实对讲或 SSC305 测量。

## 固定双麦矩阵

每个信号 16 kHz、2 麦交织 S16LE、35 mm 名义间距、6 秒，即每通道
96,000 样点、600 个完整 10 ms 帧。输出为单声道 96,000 样点。
只用现有 `build_validation_corpus` 的信号/文件函数和
`build_quality_validation_corpus` 的物理 TDOA/fractional-delay 函数。
近端目标为 broadside、两麦同相；回声第二路使用 35 mm、60 度对应的
1.4139 样点左右的相对延迟，准确值由原物理函数计算，不扩展合法几何范围。

固定 seeds 为 `5107`、`6107`、`7107`；每个 seed 均为已曝光的
`regression` 数据角色，不能改称独立盲测或用于候选选择。
每 seed 7 个场景，每场景分别 CALL/ASSISTANT，共 **42 case / 252 秒输出**。
两个 profile 在同一 seed/场景下必须读取完全相同的输入与真值文件。

| 场景 | 输入与事件 | 可报告的已有指标 |
|---|---|---|
| near-only | 有停顿近端，无 render | near SI-SDR、projection gain、VAD、clip/DC/level |
| silent-render | 与 near-only 相同 capture，完整零 render | 同上，完整链保护与输出连续性 |
| far-only | render 和已知 echo，无 near | ERLE、回声相关性、收敛与输出 level |
| doubletalk-nominal | 近端增益 1.0 + 已知 echo | near SI-SDR/projection、interference projection、VAD |
| doubletalk-weak | 近端增益 0.55 + 同一 echo | 同上，弱近端保护描述 |
| path-change | 3 秒处切换已知 echo path，并通知 frame 300 | far-only ERLE、收敛、事件后恢复 |
| render-gap | frame 300 起 4 帧 render 为零，通知 render-gap/lost=4 | far-only 残余、恢复、连续性 |

近端使用现有 quality corpus 的活动时间段与幅度；render/echo 使用同一组
既有生成函数与 path taps。新 case `expected={}`，只有工程完整性独立判定；
所有声学数值保持原函数定义并明确为描述值。旧质量集/旧 policy 仍单独按原阈值回归，
不能用本矩阵的空声学阈值替换旧门禁。不得据本矩阵宣布任一 profile/算法胜出。

## 执行与验收边界

1. 新 C 测试执行实际 CLI 翻译单元，拦截真实初始化并通过公共
   `get_config/get_tuning` 读回；各 profile 的 PCM 与同配置直接 API oracle 逐字节相等。
2. 两 profile、capture-only/duplex、8/16 kHz（构建允许时）、mask override 顺序、
   非法/缺参拒绝、默认 tuning JSON、短/空 render 与完整输出帧均覆盖。
   无 `--profile` 与显式 call 的 PCM/metrics 必须逐字节相同。
3. CLI-only 阶段运行固定 21 个 CALL 输入，对精确基线处理器的缺省输出，
   新缺省与显式 CALL 的输出/metrics 均要求逐字节相等。
   ASSISTANT 不与 CALL 要求波形一致，实际读回配置必须正确。
4. 新 adapter 复用 canonical/quality semantics，不传入未指定 tuning，不修改全局
   evaluator。缺省 profile 分支直接委托原 invoke；新增分支保持原事件参数。
5. 独立检查每 case capture/mono output 样点数、连续 JSONL frame 编号与 600 帧计数；
   任一不完整输出失败，不能以 canonical 的最短长度裁剪掩盖缺帧。
   VAD 只是遥测，不触发 PCM 丢弃。
6. 新 runner 保留输入/source manifest、输出 PCM、metrics、配置/构建身份和
   processor/evaluator/adapter/生成器 hash。只报告 regression/描述；
   KWS FAR/FRR、主观对讲质量、真实双麦房间与物理 SSC305 状态为 `NOT_RUN`。
7. 每次构建、定向测试与矩阵执行各以 300 秒上限约束；没有候选搜索、训练、
   付费任务、新 workflow、推送或 PR。本轮只作本地提交交付根工作树集成。

新增实现的第一次负例、失败与修正须记录，不改本冻结规则来获得通过。
最终合并和 source version 2.3.62 由共同集成工作包统一处理。
