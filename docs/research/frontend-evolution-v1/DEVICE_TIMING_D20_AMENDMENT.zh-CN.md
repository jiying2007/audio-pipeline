# D20 非仓目录预检修正

日期2026-10-11；对应[D20计划](DEVICE_TIMING_D20_PLAN.zh-CN.md)。
首次从/tmp执行dry-run实际exit2：D19 binding中一项工具身份是仓库相对路径，初版分析器按cwd解析而拒绝。
该拒绝未创建输出目录；真实失败命令回执保留`/tmp/audio-device-d20-portability-failure.json`。
仓cwd初次完整分析工件保留`/tmp/audio-fe-device-timing-d20-20261011`，不覆盖；它的分析结果不作为非仓cwd可复跑证据。

修正版对基线的绝对依赖路径保持原样，相对路径严格由明确ROOT与safe_file解析；新工具身份固定绝对路径。
这项修正不修改D19 binding，不猜测另一个仓根，不改变trace/窗口/门控判定或输入prefix。
修正版输出使用新的`/tmp/audio-fe-device-timing-d20-r1-20261011`，从/tmp完成help/dry-run和完整分析。
两次完整分析结果逐字节比较，验证路径修正保持分析结果；本轮DSP执行次数始终0。
首次失败与修正消耗1次retry；没有修改门限、算法、默认值或历史拒绝。
