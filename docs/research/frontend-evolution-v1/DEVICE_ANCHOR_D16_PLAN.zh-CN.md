# D16 实际提交锚支持：冻结单因果候选

日期：2026-10-11；experiment=`FE_DEVICE_ANCHOR_D16`；kind=`implementation`，仅隔离研究副本。
goal_statement：在大跳第三次确认即将写入首候选锚时，核验该实际提交对象的原40 ms history支持。
依据：[D15独立诊断](DEVICE_PERSISTENCE_D15_RESULT.zh-CN.md)。
总目标“全面推进优化迭代”仍active；本实验完成不等于声学、设备或总体落地完成。
D11/D14原REJECTED保持，不借测量PASS批准候选。

## 精确基线、唯一修改与假设

从精确D14源码复制新/tmp候选；基线库
`736815d2050d49f5a1ebcf254abd140b2c39edfff2f5ae43d27b06c0282a95f3`；
D15 result=`4f23dbb3769aeb577fac0b3f255598705e3bb0dcfda9034abfb853ede76e37c7`。
唯一算法修改：confirm返回third完成、best_delay取保存anchor之后，
提交delay/drift/AEC route_jump之前，用原ap_sync_route_history_score(s,...,best_delay)
与原0.0324门限再检查一次；不足则delay_observed=0、return，不提交jump。
confirm已经清零，保留该语义，不增加状态、不改后续锚选择/重启/次数。
不要求通过者改写为当前refined，不扩门限、不改事件验收、不加100/200 ms窗口。
搜索/guard、原当前候选40 ms gate、0.5 ms容差、三次确认、drift/AEC/API/default均不改。

假设是“被提交锚的支持应与已声明history条件一致”，而不是“更高分就是真物理路径”。
D15已证明rpm480最后refined与anchor均16且history强，新检查不承诺解决该事件。
即使工程契约改善，原D8稳定性硬门禁仍逐臂执行，任何剩余新增jump/reset都拒绝候选。
一版候选，不在结果后追加其他策略求绿。

## P1：计划/身份、精确patch与定向工程

独立计划审查后复制精确D14；所有source逐hash核，只有这五行插入允许。
增量patch check和独立实际重放byte-exact；strict build/CTest14、原D8 engineering/recovery、
D11 oracle21618、D14确认性质全部通过。
新增anchor fixture实际调用原tracker（不mock score）：8/16 kHz真实宽带render、匹配mic/history，
预置2/3锚确认；有效当前候选但弱锚，原D14应提交弱锚而D16拒绝；同候选/锚强支持两版均提交。
拒绝保持旧delay、无route_jump/observed、确认清零；通过提交实际锚、drift清零/错误观测保持契约。
全state仍78840/80000，无新增alloc；追加最多一次40 ms/stride4相关，仅在third完成路径，
8/16k分别80/160点；不能据Host结构预算推导DUT CPU/p99/功耗资格。
工程fixture任一失败停止并保留。

## P2：原D13事件契约与P3：原D9获取

原D13 fixture/生成器/evaluator字节不变，56+1实际运行，全部input/config与原D13锁相同。
按原规则mandatory52/52，正例exactly1jump/reset、首次/末窗/本帧入带、切换前保护不变；
4例pulse3仍diagnostic。任一失败REJECTED_EVENT_CONTRACT，停止后续候选执行。
原D9 fixture不改，100+1，输入与D14/D11原锁相同；mandatory26/26末20帧±3 ms不变，
无通知gap、双讲和其他diagnostic披露。任一失败REJECTED_KNOWN_DELAY，停止后续。
指定新进程repeat原input/output/metrics/config逐字节一致，不能只验证summary。

## P4：原设备数据完整回放

原119文件锁、16场景、70固定臂+2repeat，原receipt verifier；输入/config与D8/D11/D14 byte-exact。
工程库与实际replay库逐字节匹配；34个tracker-off控制与原库PCM/metrics相同，default/control等价。
目标tracked1不得出现172 ms；任何固定臂jump/reset超过原D8都
REJECTED_DEVELOPMENT_COUNTER_REGRESSION，不据相比D14减少或单帧拒绝就豁免。
与D14全70臂比较counter/delay/事件时点/slips及原窗口RMS，完整披露后续新簇或延后事件。
全部通过也仅DEVELOPMENT_CANDIDATE_ONLY，真实对齐和声学仍不确定。
输入是已查看development，不升级为blind或独立验证。

## P5：whole-change复审与阶段收口

锁source/库/input/config、原文命令exit、工程矩阵、完整回放/comparison、binding及文档snapshot。
独立review核本轮工程与原D8拒绝规则，中文入口/文档检查，Runtime仅D16阶段。
completion_claim=本版候选实验及决定完成；claimant=root；verifier=device_capture_independent_review。
open_items=5；attestation须hash回读；retry_budget=一版算法、测量实现最多两次修正。
staleness_threshold=源/库/input/config任一漂移即stale/replan；heartbeat按阶段且持续实际handle。
每命令timeout120秒、build允许300秒；观察超时不重启未知运行。
stop_condition=pass/replan/blocked/abort；plan_completeness=五阶段明确。
不清理已有dirty/raw，不SCM外写/设备写，Provider route unresolved仅仓内reviewing candidate。
AISpeech/E001/历史I025–I040和shipping资格不变。
本轮live main=feb2f8ebc17a25bf248a63139ea4a219de39545d，summary/Verify/Release成功，HIL失败可见；
研究artifact11675081856未过期，仅metadata；#657 OPEN，#712/#708为独立RealMAN，#695/#696 Dependabot。
