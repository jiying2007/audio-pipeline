# D9：禁止增益上升时的状态回升抑制

执行前冻结，候选数 1。基线 main `8f282f0b8b55cf71285bf77b76598e101f9ba3c0`。
本轮为公开开发诊断数据上的隔离 AGC 因果实验，不是生产修复、盲测或端到端晋升。

## 假设与唯一变化

D2 定位部分英文退化已在时变 AGC state gain 出现；D5 删除 unity target cap
提高远端能量，D6 帧内 ramp 和 D8 broadside 均关闭。不得重跑这些候选。
当前 `allow_gain_increase=0` 仅将 target cap 为 1：当历史 state gain 小于 1 时，
仍可回升。D9 在原 target cap 后增加 `target_gain <= state->gain`（仅 allow=0）。
原 output unity cap、peak cap、sample clamp、alpha、初始化、profile 和 reset 全部保留。
这不是已证明的缺陷：旗标可能只表示禁止超过单位增益，需要实验确认取舍。

## 输入、评价与边界

复用原 D2 artifact13553232106，474165229 bytes，SHA256
`a3ab7823fdcd7586c3b72eb214b5536dcfb7531fdf0b1611d49e1575a29b2c3d`。
锁定既有 `dualmic-gain-d2-input-lock.json` 的全部 60 例、35916 帧、5746560 样本、
362 固定窗口和 8 reset。每例原 NS 输出、控制、AGC 输出与 clean-near 逐 hash 校验。
使用真实 C 基线及生成的 C 候选，两臂各自连续演化 gain；上游和控制固定。
基线每帧状态与原 control、全部 float PCM 必须逐 byte 等于原 D2。
候选逐帧有限，allow=0 的 state 不得上升；allow 恒真案例必须完全相同。
重复执行须 bit-exact；不改变 canonical D1 measure_lane、160 样本 offset、全部窗口、null。
报告原 Float32 AGC 输出口径，而非重新量化的终端 S16，也不声称 ASR/KWS/MOS 或真机。

继续条件：全部 32 个有参考 common span 及全部可评分固定窗 SI-SDR 不降低；
16 个双讲 common 至少一个改善 >= 1 dB；全部 24 远端相关及 4 C 例 native/common/window
RMS、peak 不增加；全部 clip count 不增加。任一有效失败为 NO_ADVANCE，关闭本候选。
有限性、数据身份、baseline 或控制失败为 MEASUREMENT_INVALID，不按新容差重试。
不调阈值、不扫描第二参数、不因结果选择窗口。研发价值可以是保存负结果。

## 预算与性能

本地免费已提供云执行环境，单阶段 300 秒，完整首次试验最多 20 分钟；
ZIP <= 474165229 bytes，解压逻辑 861385743 bytes，输出 <= 256 MiB。
每例 baseline/candidate 各 7 次 C thread CPU 计时，交替先后，每次处理原完整连续流；
计时包括 C 内 memcpy/状态重置，不含磁盘 IO、Python、编译。报告每例及整体中位比，
不作为 SSC305 结论；候选总 CPU 中位数不得比基线高 10%。
唯一 native 编译 `cc -std=c11 -O2 -fPIC -shared -ffp-contract=off`，不使用 fast-math。
工程对照包括允许上升、禁止上升、强信号下降、初始化/reset、peak/clamp、非有限输入拒绝。
本地结果与后续 PR/main 检查身份分别记录，禁止复用 CI 资格或直接推 main。

## 执行前工程澄清（尚无科学执行）

实现采用独立 CLI 而不是 Python 加载 shared library。准确编译为
`cc -std=c11 -O2 -ffp-contract=off -DAP_BUILD_STAGE_AGC=1 -I<output> baseline.c candidate.c driver.c -lm -o replay`。
取消初稿未实施的 `-fPIC -shared`，算法/数据/判据不变。性能计时包含同驱动的
baseline 原控制匹配与 candidate 禁止回升检查，属于带检测开销的原生 AGC 微基准，
不是完整流水线性能，也不是绝对 CPU 净耗时。Python 独立重建连续状态及每个输出样本，
保留真实末端 clamp 改变样本计数。全部 7 次实际 C 重复都比较原 PCM，报告全部时值。

D39–D49 的历史测试允许受限阶段从小于单位增益恢复，因此 D9 是不同研究取舍，
不是修正历史错误；不修改或删除既有测试。必须保留可能衰减锁死、近端恢复变慢的失败。
本轮借原窗口分数暴露恢复阶段风险，尚不增加新的恢复时间评价方法或推广结论。
