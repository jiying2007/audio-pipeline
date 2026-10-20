# 设备采集D4：大跳变唯一性检查单项实验

日期：2026-10-10；状态：EXECUTED_REJECTED_REAL_ROUTE_RECOVERY_REGRESSION；角色development；promotion_allowed=false。
冻结先于执行；结果与保留的失败见DEVICE_SYNC_D4_RESULT.zh-CN.md。
用户授权：继续推荐优化及本轮执行预算；不包含提交/推送/合并/设备部署。
逻辑目标：验证SYNC大跳变绕过已有唯一性检查是否参与172ms误跳。
原产品源码和D3结果保持不变，候选仅在本轮临时源码快照中编译。

## Phase A：冻结与隔离
kind=research；scope=临时第一方源码快照、原公共API运行器；base=本地572b0e34a8a8e5663397ce16e378209ba9058d4d及D3source lock。
live main=39a445d4c21d2f716e6602450a0bf944f248383b；新增A2与共享docs gate，未自动更新当前检出。
单变量：在raw_jump>sample_rate/50的大跳变路径进入三次确认前，增加现有ap_sync_peak_is_unique检查；
未通过时清候选确认数并撤销delay_observed。相关阈值、窗口、三次确认、drift/AEC/NS/AGC均不改。
exit_gate=原source hash与冻结D3逐文件一致，精确一次代码替换，无产品树修改。
rights=第一方本仓代码；data_role=已查看设备development，非独立验证/盲测。

## Phase B：执行与保留失败
16轮全部以tracked1/fixed1回放，共32执行；仅tracked1用于观测候选影响，fixed1为变更不生效逐点控制。
与已封存D3相同配置、输入PCM、样本数和metrics协议比较；不新增指标或变更诊断窗口。
额外完整候选CTest必须保留真实路径切换/漂移恢复；其通过不等于真实声学质量。
记录candidate源码/输入/编译库/运行器/输出hash、全部退出码与失败，不覆盖D3。
exit_gate=32执行和固定控制一致、14 CTest、无样本缺失/非有限metrics。
无效或恢复退化允许诚实关闭为负结果；不为了成功再调阈值。

## Phase C：结果与后续
kind=review；verifier=现有契约/真实PCM回读，独立owner review仍待。
验收：分别报告172ms事件、估计delay集合、输出窗口变化、真实路径恢复及固定控制。
root_cause只能在对照支持时限定陈述，不宣称ERLE/KWS/产品通过。
后续NS→AGC→VAD、SSC305/独立声学、Provider路由沿原验收线。
retry_budget=同类失败2次；staleness=live移动即核对交叉；stop_condition=pass/replan/blocked。
本轮Runtime预算5000000/43200秒；达到强制停止时只保留已验证成果与接续事项。
