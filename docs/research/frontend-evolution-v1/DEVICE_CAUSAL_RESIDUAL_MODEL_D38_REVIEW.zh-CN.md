# D38 全量数值契约与独立审查

2026-10-11。实验 FE_DEVICE_CAUSAL_RESIDUAL_MODEL_D38，结论为研究诊断数值契约 PASS；NO_PROMOTION，promotion_allowed=false，shipping_approved=false。总体优化迭代目标继续，本文不批准产品采用。

冻结 PLAN、实现与独立 whole v2 审查分别得到 Spec PASS、Quality PASS、independent=true、unresolved=0。唯一数值变化为六类160点点积/能量项采用 math.fsum；保持原滞后、历史拟合、逐点预测、创新、除法、字段、标志与统计。D37 的 NUMERICAL_CONTRACT_FAILED_REPLAN 及失败回执保留，未放宽其旧阈值或改判。

实际非仓目录 help、deep dry-run、13项唯一单测、主矩阵执行均 exit 0。主测量覆盖46项、126486帧、240个整窗，完整重复一致，未来扰动1247帧前缀一致；主执行44.47986630629748秒。三个负路径实际 exit 2，对照完整文件清单无变化。负路径由主代理执行，独立审查核回执，不冒称独立重跑。

独立裁判首次全量执行 exit 0，130.04858053382486秒。以 Decimal.from_float 对已计算 binary64 项进行精确反向求和，precision=2200，并启用 Inexact/Rounded traps，最后一次舍入；不导入项目测量辅助函数，不以 fsum 自证。覆盖46项、126486帧、240整窗、1897290次字段精确断言、3953次来源/起止哈希核验，重复与未来前缀亦通过。AEC调用0、滞后搜索0。ratio>1共32698次包含重复及未来扰动，不能解释为仅主矩阵数量。

纯回声 explained_fraction 中位数约0.415至0.443；混合首轮近端窗口的创新能量比中位数约1.078，200帧中192/193帧大于1；ABA返回近端窗口约0.836至0.838，200帧中22/21帧大于1。创新不等于真实近端、预测不等于真实回声。该结果不支持将标量近端保护器升级为产品算法，也不证明声学收益或板端实时资源资格。现有输入属于已复用 development/synthetic 数据，独立裁判不改变其数据角色。

第一次 whole 审查发现待用 Runtime 收口脚本 MAJOR-1：旧操作回执/中断后重启可能先重复发送，再在写回执时失败。原 writer 与原30项快照保持，未执行；v2在发送前排除整批旧/新 intent 与 receipt，每项先以独占创建保存请求意图，异常先保存空退出码与部分输出，禁止未知重发。fresh whole v2 审查确认 MAJOR-1 closed，Spec/Quality PASS、unresolved=0。当前43项 review-snapshot-v2 全匹配，SHA256为03b6a1398432b8c43ffc8acf9fb5b211b66faf84ee55b4d7e66e575932094a19。

上下文维护对账：D38 native-v1 唯一请求 request_ms=1791703391544 已受理，120.41056999377906秒观察回执仍为 ACCEPTED_COMPLETION_UNVERIFIED；不覆盖、不重发、不将宿主实际压缩归因给该请求。2026-10-11T07:26:00.716629Z fresh Runtime steady 实际 exit 0，host_context_maintenance.required=false、context_ratio=0、recommended_action=continue。compaction_completion_verified=false保持真实值；当前维护解除与请求完成证明分别报告。

证据根为 /tmp/audio-fe-device-causal-residual-model-d38-20261011；result SHA256=4cb3d3273391a3a6b9e34348a060bb4a423e2184a2d8f5e42b097e711d6946c4，binding SHA256=4c51efdd4cfa863fdac15dc58b2f2849fa62114d93c485fbd0ef87614ebe08c8；独立 audit receipt 为 /tmp/audio-device-d38-independent-audit.json，SHA256=e4ccc8e4e4e857266b74cd4f0e36d0308ba6452f15a6ad0b68601a80ceb0ad16。

下一步仅执行已审 finalcheck-v2、核验新回执后执行 closeout-v2，并独立附核实际14项 Runtime 终态。本文创建时这些命令尚未执行；其实际结果以绑定本文哈希的回执为准。Runtime conformance 仅收口D38本地诊断里程碑，不等于产品放行、第三方授权、真实板端/HIL或总体目标完成。
