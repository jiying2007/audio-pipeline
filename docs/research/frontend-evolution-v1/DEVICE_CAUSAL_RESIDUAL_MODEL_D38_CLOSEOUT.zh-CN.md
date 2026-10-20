# D38 实际收口与后续集成边界

2026-10-11。D38 全量数值诊断 PASS，独立 whole v2 及恢复 v3 控制审查 Spec/Quality PASS、independent、unresolved=0。执行 v3 的实际 session55253 terminal exit0；原v2 index0与v3 index1至13共14项成功操作，另有v2 index1真实exit2失败，保持不可变证据身份冲突的历史，不将整段执行说成无失败。

实际 final 在2026-10-11T07:29:52.642684Z返回exit0/status=pass、completion_allowed=true、missing_evidence=[]、missing_artifacts=[]、host_context_maintenance.required=false。本地goal task-f549a2d7016352e32a8c0c60 completed/open0。原device-d38-result固定原快照身份，新device-d38-result-v2固定43项扩展快照，repo artifact绑定新身份；build与review分别绑定真实binding及REVIEW。该状态仅闭合D38本地里程碑；线程总体目标“全面推进优化迭代”仍active。NO_PROMOTION、promotion_allowed=false、shipping_approved=false。

证据位置为/tmp/audio-fe-device-causal-residual-model-d38-20261011/runtime-closeout-v2-0.json与runtime-closeout-v3-1.json至13.json，并分别有发送前intent；失败为runtime-closeout-v2-1.json。REVIEW SHA256=1da9d5ee6a841ee60dd97ba5663b5155bb67503199cd4291d7acdfbe82c10b52；resume-v3 writer SHA256=a209b94f7cf5ae9341dd7f901bddc0962d45794527c229af25879fc10d2c038a。终态独立附核以实际回读为准，本文不替代裁判。

下一工作项属于完整下游集成，不再以相近标量诊断或阈值寻优批准近端保护。当前只读代码确认device_activity_d30.c执行Activity、双AEC、选择和输出过渡；src/core/ap_pipeline.c定义AEC之后的RES条件分支、NS联合频域RES、controlled AGC及VAD。前级创新与真实近端混淆已由D35/D36/D38揭示，D32/D33保护方案失败继续保留。

新实验实现前须独立冻结新身份和PLAN：固定D30输入/原Activity/选择/过渡；明确过渡期间残差与匹配回声估计的共同传播，保证NS频域RES不借用另一bank估计；遵循canonical RES与NS条件避免重复抑制；保持受控AGC门控、OLA历史和VAD输入顺序。先建立旁路逐字节等价基线，再单独检验完整下游集成，不将改变观测契约与产品算法互相批准。必须保留原240窗与known-near分段误差、静态/路径退回代价、重复与未来前缀、输入/source/config/output身份、全局状态/缓冲资源及失败负例。有限预算、数据角色、测量契约、准入和停止条件冻结且独立审查后才实现；本文仅交接这些约束，不是批准的下一实验PLAN或已执行结果。

设备已查看数据仍development；独立算法裁判不使其成为blind/validation。真实近端语音、机器人运动/房间独立信号、目标板CPU/p99/RAM/热功耗、HIL和产品资格继续分别验收。Knowledge Provider当前route unresolved，只能NEEDS_REVIEW，未宣称耐久知识归档成功；没有commit/push/PR/merge/release或设备写入。
