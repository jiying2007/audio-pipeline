# D10 短延迟 tracker 有限观测计划

日期：2026-10-10；experiment=`FE_DEVICE_TRACKER_D10`；状态=FROZEN_MEASUREMENT_PLAN。
授权=用户“继续推进”，承接 D9 明确的内部定位下一项；primary=`adk-planning-execution-loop`。
goal_statement=区分短延迟失败发生于 coarse/refine 搜索、候选确认或 D8 长窗拒绝。
live main=`025e266c2ade3a1923ae10f5c8759ee49a437ea5`，其 checks 读取时为空，不继承先前 main 检查。
tracker #657 OPEN；open PR #695/#696 独立。当前实验仍固定 D6/D8 身份，不更新产品源码。

## Phase A：冻结观测合同

kind=measurement；implementation_permission=仅第一方观测 fixture、隔离编译与文档；不修改算法或 shipping。
base=D9 result `564a2d3d6b6200c728ad09469b455b0595a584286d56ea2c0fd3899e1a9624b6`；
baseline/candidate source 分别匹配 D6/D8 receipt，D9 原输入/输出/metrics 保留。
data_role=已查看的合成 development 工程输入，不是真人、独立验证、blind 或声学评估。

固定 7 个既有 D9 用例：8/16 kHz、seed1、宽带 acquire、目标 1/7/80 ms 共 6 例；
另加已披露基线最终 10 ms 的 16 kHz/seed2/宽带/acquire/1 ms 一例。
两版本各 7 例，读取 D9 保存的输入，不重新生成信号，不重跑整个 D9 矩阵。
每例 300 个 10 ms 帧，原 initial40/max100、delay/drift 启用及数值缩放不变。

同一新 C 观测 translation unit 直接 include 各自**字节不变**的 `src/sync/ap_sync.c`，
实际执行原 `ap_sync_push_render` 与 `ap_sync_track_delay`，只读取内部状态。
它不是新增算法、公共 API 或声学评估器；实际 tracker 与旁路观测要分别标识。
旁路在每个实际 tracker 更新前，调用原静态 score 函数，按原 coarse/refine 顺序记录 winner、
分数、refine 区间及已知生成器 true-lag 的分数；只观测已知真值，不以分数优化候选。
确认计数、候选延迟和实际 event 在原 tracker 调用后读取。
D8 长窗 score 在 tracker 更新 history 后只读计算；不得把调用前尚未追加的 history 当作实际 gate。
旁路观测前后整个状态必须 byte-exact 不变，不把额外观测 CPU 当作部署性能。

## Phase B：有效性、判因与停止条件

kind=validation；预算=两次观测编译、14 次既有输入 replay，不构建算法候选、不搜索参数。
每个 capture 帧的 delay_ms、累计 jumps/slips 必须逐点匹配 D9 原公共 API metrics，
原 resets 必须为 0；不匹配时标记 OBSERVER_NOT_EQUIVALENT，停止因果声明。
全部输入 SHA 必须匹配 D9 binding；实际源码、生成头、编译命令、输入、CSV、summary 均绑定 hash。
固定末窗与失败条件不变，不允许重新选择用例、增加帧数或改门限得到成功。

只对这些输入作有限判因：true-lag 得分充分而 coarse winner 的 refine 区间排除 true-lag，
属于搜索覆盖不足；若进入真值但连续确认不足，分别记录确认不稳定；D8 gate 拒绝单独记录。
多种机制可以共同存在，不能以少数帧归因全部失败，也不能声称已经证明适用于真实声学。
若证据不足，明确 INCONCLUSIVE；下一算法修复需新冻结合同，不能与本测量互相批准。

## Phase C：独立审查与收口

kind=review；claimant=root；verifier=已授权独立审查者；review_mode=whole-change。
required_evidence=冻结计划、fixture、source/input/trace bindings、D9逐点等价、判因计数及独立复审。
open_items=观测实现/实际执行/独立审查三项；logical_task_open=true。
retry_budget=同类失败2次后replan；staleness=fixture/源码/数据/合同任何变化需重锁；
heartbeat=阶段完成；stop_condition=pass/replan/blocked；attestation_readback=hash与逐帧实际证据复算。
结论仅 ENGINEERING_DIAGNOSTIC，不批准 D8、AISpeech 替换、HIL、E001 或 PQ。
Provider route unresolved，仓内文档为 reviewing candidate；不正式归档、不执行 SCM 或设备写。
