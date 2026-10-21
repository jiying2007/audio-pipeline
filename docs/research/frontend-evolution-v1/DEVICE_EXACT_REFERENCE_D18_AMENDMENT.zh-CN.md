# D18 执行前澄清：启动欠载与JSONL字段范围

日期2026-10-11；独立计划审查QUESTION-1；P1/P2尚未执行，无结果后调整验收。
[原计划](DEVICE_EXACT_REFERENCE_D18_PLAN.zh-CN.md)保持原字节。

P2零参考控制的“metrics只允许estimated_delay_ms不同”限定为原device_capture_runner的JSONL字段，
这些字段不包含SDK ap_metrics_t.render_underruns；不能称所有SDK公共指标相同。
fixed1首帧get_reference的start=-16，欠历史返回1；used0首帧start=0，返回0。
因此实际SDK render_underruns预期fixed1=1、used0=0，后续完整连续帧保持该累计值。
这项启动历史可用性差异属于显式适配语义，单独逐帧断言并在runner终态摘要记录，不隐藏或清零。
JSONL保留原schema以核原10场景及zero控制；完整指标相同的宽泛解释撤销。

原数据、两臂、4点参考差异、库、36执行/逐reference核验、RMS窗口及禁止晋升不变。
没有算法候选、门限/timeout变更；这是执行前精确合同澄清，不占结果后测量修正budget。
