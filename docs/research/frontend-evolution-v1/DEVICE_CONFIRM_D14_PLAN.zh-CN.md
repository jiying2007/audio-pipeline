# D14 首候选确认容差：冻结单一算法实验

日期：2026-10-11；experiment=`FE_DEVICE_CONFIRM_D14`；kind=`implementation`，仅隔离研究副本。
总目标为“全面推进优化迭代”，保持active；本里程碑不等于整体、声学或产品完成。
goal_statement：检验大跳确认首候选容差从1 ms收紧到0.5 ms，是否改善开发回放稳定性而不损害正常获取/恢复。
来源：[D12事件证据](DEVICE_EVENT_D12_RESULT.zh-CN.md)、[D13事件契约](DEVICE_CONTRACT_D13_RESULT.zh-CN.md)。
原D11 REJECTED不改变；新候选不得借用D13的PASS批准自身。

## 精确基线与唯一修改

精确D11源码、头、CMake和库作为被拒绝的研究比较对象，不是获准部署基线。
D11库=`ead75733d45f5b78c086bed9122082d410847eea0ed6b21f8bafab102a1cb0ac`；
D13 result=`c5e9722ab6c68f481517fe603a0a851e3d3fd0d12542f53767de7117d1575804`。
仅修改 `src/sync/ap_sync.c` 大跳分支传给 confirm_route_candidate 的 tolerance，
从coarse_step改为 `coarse_step / 2u ? coarse_step / 2u : 1u`：8/16kHz分别4/8samples，0.5 ms。
原1 ms coarse网格、refine、uniqueness guard/top4、0.0324/1.01门限、三次确认、20 ms大跳、
D8 40 ms history gate、drift、AEC、初始化和公共API全部不变；不新增state或alloc。
首候选容差是每次对首次保存候选的距离，不是所有候选两两距离；两个极端仍可能相隔1 ms。
仅改变确认容差，不把搜索精度和确认策略再次绑到一起。

假设依据：D12两条触发序列15/16/24与31/16/16在原±16samples簇内完成三次确认，
收紧到±8可重启这些特定簇；后续是否形成其他簇必须完整回放，不假定两事件消失。
没有真物理delay，不能把抑制迁移解释成正确对齐或声学收益。
不进行参数扫描，一版候选，失败后保留，不改输入/阈值/时长洗绿。

## 串行阶段与硬门禁

P1：独立计划审查、hash核验，复制精确D11到新/tmp；增量patch check及独立实际重放byte-exact。
strict构建/CTest14项全通过；原D8 engineering/recovery、D11 oracle21618项及新确认边界性质通过。
完整state必须仍为78,840且不超过80,000；score网格/调用上界不变，无新增alloc/TLS；不当作DUT CPU资格。

P2：不改原D13 fixture与其生成器，候选56+1新进程复跑，全部原input/config逐字节匹配。
按D13原规则独立回读：mandatory52/52；正例首次进入目标≤phase+80、exactly1jump/reset且jump本帧入truth±3，
switch前逐帧保护；steady/pulse/silence/unrelated按原规则；pulse3仍4例diagnostic，披露而不变分母。
指定repeat的input/output/CSV/config逐字节一致；任一mandatory失败立即REJECTED_EVENT_CONTRACT并停止后续候选执行。

P3：不改D9原fixture，100+1全部输入匹配原锁，mandatory26/26、末20帧truth±3不改。
所有diagnostic/未通知gap差异披露，不用这些输入升级blind；任一mandatory失败REJECTED_KNOWN_DELAY并停止。

P4：通过上述后，原tests/audio119文件锁、16场景70固定臂+2repeat全部真实执行。
原适配输入/config逐字节匹配D8/D11；34个tracker-off控制PCM/metrics与D8完全一致，default/control重复一致。
指定rpm480 far-motion tracked1不得出现172 ms误跳；任何固定臂jumps或AEC resets超过原D8均
REJECTED_DEVELOPMENT_COUNTER_REGRESSION，不能据相对D11减少就豁免。
同时比较D11全部70臂，记录jump发生时点、slips、delay集合与输出窗口RMS；无真值时不声称ERLE/人声保持。
即便全部通过，也仅DEVELOPMENT_CANDIDATE_ONLY、声学与物理资格待独立证据。

P5：冻结结果/完整身份、whole-change独立复审、中文文档和本里程碑Runtime收口。
总目标保持active，恢复台账说明下一步和所有未完成资格。

## 资源、预算和治理边界

retry_budget=一版算法候选，测量实现最多两次修正；源/库/input/config hash漂移即stale/replan。
每命令超120秒先核实际handle，不能删帧或重启未知运行；工程构建可300秒但保持进度沟通。
heartbeat按阶段；stop_condition=`pass/replan/blocked/abort`；plan_completeness=五阶段明确。
claimant=root；verifier=device_capture_independent_review；初始open_items=5；attestation必须hash回读。
required_evidence=计划/patch/源码、strict与性质/资源、57事件回执、101获取回执、72设备回放或明确early-stop、独立review。
与既有dirty保持隔离；只在授权workspace写研究patch/fixture/docs，产品src和旧实验副本不改。
live main读取=`feb2f8ebc17a25bf248a63139ea4a219de39545d`，summary/release成功；#657 OPEN，
PR #708为独立RealMAN工作、#695/#696为Dependabot，不借用主线CI认证本候选。
Provider route unresolved，仓内reviewing candidate，未正式归档；不commit/push/设备写，AISpeech/E001不变。
