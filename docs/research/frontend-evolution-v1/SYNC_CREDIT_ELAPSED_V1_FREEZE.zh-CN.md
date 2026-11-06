# SYNC credit 有效观测时基修复：冻结合同 V1

执行起点：2026-11-06 08:26:58 UTC；整体实现、测试与证据封存预算 600 秒，
每次构建/测试上限 300 秒，超时保留失败。唯一候选，不搜索或调参。

## 精确基线与新增实证

实际失败 merge：`5728a4f1b43d9d66f6cea8467ac3443efe14297e`；PR head
`b1f40864fb0fc941561950a656041ade6e8b9b89`，protected base
`a920beed8e2c66ea9d90442d31af9632f5c75a23`。原 Verify 42186062706 的
composition-tiny job 127787874362 在未修改的 `tests/test_drift_res.c:66` 失败。
该测试在 protected base 通过，候选精确复现 SIGABRT。

同输入下两端接受的 21 个时刻与 best_delay 一致，内部 8 kHz 的相邻间隔为
16×3200 样点和 4×10400 样点，共11.6秒；credit 仍只累计20×100ms。
候选最终 credit 0.219664231、slips 0；旧版 slips 1。已修正的速率与未修正的
积分时基耦合，不能只放宽测试。此前诊断原日志、命令、冻结与trace原字节保留。

## 唯一生产变更及生命周期政策

在 `ap_sync_apply_drift` 内复用有效相邻 capture observation 的 elapsed 样点数，
让 credit 也按这个时间积分。正常100ms严格保留旧乘除顺序。
**没有前一个有效 basis 时保留旧 nominal100ms credit 路径**；disable、reset、
timestamp、rate-change、counter rollover 后不得回填失效前或未知区间的时间。
route anchor 继续沿用已有有效 basis 政策。不新增逐帧演化或驻留状态。

EMA、ppm clamp、误差反馈、每次最多4个slip、插值、route确认和既有生命周期
失效点均不改变。不修改 `tests/test_drift_res.c`、CMake、版本或公共API文档。

## 固定验收

- 扩展现有 `test_sync_observation_time.c`，实际相关搜索驱动8/16k、正/负、
  silence/periodic 拒绝、0.4/1.0/1.3秒间隔；从临界 credit ±0.98 出发，
  单样点变化的0.05 EMA冲量必须跨过一个slip并保留约±0.03 credit。
  同一新测试必须先在旧 credit 源码失败，再在唯一候选通过。
- 保留稀疏大credit时单次4-slip限额；disabled重启与非递增counter重建
  必须沿用nominal100ms，不把无效区间计入credit。原reset/timestamp/rate/route
  测试完整保留。
- 同一个扩展测试在正常100ms模式记录完整opaque模块状态和reference字节，
  旧/新实现逐字节一致；现有可读ppm/delay/slip输出也一致。
- 默认构建和真实 `composition-tiny` 的原完整CTest均通过；tiny原漂移断言
  不修改。8k专门观察测试必须执行。每次构建/测试受300秒上限及剩余总预算约束。
- 不重跑ARM、声学矩阵、训练或无关组合；不把工程回归写成真实设备/声学收益。

## 证据

保存失败CI身份、原诊断日志/trace、新测试before失败、after通过、default/tiny
完整CTest、正常节拍字节对照哈希、状态尺寸与最终工作树检查。只有一项生产
因果修改，任何测试失败或预算超限均保留，不增加门槛或改变期望求绿。
