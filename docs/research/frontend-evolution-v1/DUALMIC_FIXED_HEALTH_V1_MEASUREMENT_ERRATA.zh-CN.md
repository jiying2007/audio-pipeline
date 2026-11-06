# FE-C2-FIXED-DIRECTION-HEALTH-V1：测量起点勘误

日期：2026-11-06。此勘误经总集成审查同意后登记；不改原计划、实施冻结记录或 BF 候选阈值。

## 保留的首次执行

初版 BF-only 公共 pipeline 测试将 stages 限定为 BF，却遗漏关闭默认 SYNC tracking/clock-compensation flags。四个 rate/profile 配置因此被原 API 正确拒绝；该配置拒绝不能算作 BF 缺陷。修正测试配置为合法 BF-only 后重新执行精确原始基线，fixed hard 不进入、切换丢 hard 及公共 LITE 输出退化仍实际失败。两份原始日志分别保留。

首版候选的 24 个 hard 正例全部在 frame 24 进入；12 个 BF-only 分组在 frame 108 恢复，12 个 HPF→BF 分组在 frame 112 恢复。原断言以 raw 输入在 frame 80 切回 clean 为起点，要求 frame <112，因而产生 **12 个实际失败**。这些结果不是“原始验收全通过”。

输入切换时，原 HPF 带有上一污染段状态。frame 80 的 HPF 输出尚不满足既定恢复 roughness 条件；首个满足条件的观察为 frame 84。frame 84/88/92/96/100/104/108/112 才构成八次有效恢复观察。BF-only 则从 frame 80 起已有有效证据，八次观察为 frame 80 至108。

## 测量修正，不放宽算法

维持原 `8 次连续有效恢复观察`、能量/roughness 阈值、每四帧节拍和候选源码。测试改为独立检查预先固定的 BF 输入特征与时间点，不能根据候选实际退出时刻产生预期：

- BF-only：首有效 frame 80，退出 frame 108，含首尾输入帧的 raw→退出计数为 29。
- HPF→BF：首有效 frame 84，退出 frame 112，raw→退出计数为 **33 帧 / 330 ms 音频**。这比原 raw 起点断言的 32 帧上限多一帧，保留为真实级联恢复边界。
- 每个冻结有效观察前后检查恢复计数；七次不得退出，第八次才退出；静音中断后重新累计。
- 单独打印路由切换相对旧路由的首采样附加变化、相邻帧边界变化和恢复窗口 RMS。不添加 crossfade，不宣称无点击、真人对讲改善或硬件端到端时延。

新增独立双精度输入特征检查只核实这些固定样本上的恢复资格，不参与 DSP 决策、不改变真值角色。此修正解释测量起点，不能把原 raw→退出 33 帧重写为 ≤32 帧。

## 原始日志

`evidence/dualmic-fixed-health-v1/base-initial-config-rejected.log` 保存最初配置拒绝；`base-corrected-config.log` 保存合法配置后的原始算法失败；`candidate-initial-recovery-fail.log` 保存候选首跑的全部输出与12个恢复断言失败。所有信号仍为开发/回归工程数据，没有独立真人或目标板证据。
