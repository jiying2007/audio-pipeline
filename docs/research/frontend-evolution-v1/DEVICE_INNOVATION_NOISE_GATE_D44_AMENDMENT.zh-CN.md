# D44 monitor 保护日志等价合同修订

2026-10-11，experiment=FE_DEVICE_INNOVATION_NOISE_GATE_D44。原 PLAN SHA256=`844bcdf4e5904577e08ae3d33cb8a93381cca272f7e33e49c6e0cf5b2ab5874b` 字节保持。首次独立计划审查发现 MAJOR-1：monitor 也计算新 floor，原 protection.csv 记录实际 floor_mean，因此该文件通常不能同时逐 byte 等于 D43。当前尚未实现或执行新候选，不修改任何旧结果。

## 修订后的准确对照合同

原 PLAN P3 中“monitor 原五输出与 D43 byteexact”以及独立 audit 中同义要求，以本修订替换为：

- 全部 92 个 monitor 执行的 bypass.f32le / ns.f32le / final.f32le / control.csv 四个原输出必须与 D43 同名 monitor 逐字节相同。
- monitor protection.csv 字段、帧集合、gates/count/valid/raised 的投影必须与 D43 同名 monitor exact；只排除实际 floor_mean 字段。monitor raised 仍严格为零。真实新 floor_mean 由固定快照实际 floor 汇总独立复算，与新 bin trace 和 power trace 对应，不允许为等价测试假写旧值。
- 两模式 floor_mean 与其余不受实际增益反馈影响的诊断依原模式投影保持 exact。candidate protection.csv 允许真实 raised/floor_mean 变化，但仍核全部 schema/count/state 与独立选帧算术。
- candidate bypass 仍与 D43 同名执行 exact。候选变化后的 ns/final/control/protection/诊断按新规则真实记录，全部原固定窗口指标和准入由原裁判计算并独立重算。

只更正日志对照，保留单一 floor 映射、固定 2.0 严格大于、原 .8/.2 EMA、旧 N 读取阶段、184 次 / 505944 帧、24/72/4 原准入集合与门槛、预算和失败保留。音频原输出等价不会被日志排除项豁免。快照外 floor_mean 的独立覆盖仅为 schema/range、D44 两模式/重复/future 和来源身份，不冒称全帧 bin 算术重建。

MAJOR-1 待独立复审；修订复审通过前不登记计划 PASS、不实施或执行新 DSP。promotion_allowed=false、shipping_approved=false；总体 native 目标继续 active。
