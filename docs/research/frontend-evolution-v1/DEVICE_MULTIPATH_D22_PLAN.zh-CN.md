# D22 多反射与路径切换：冻结工程实验合同

日期2026-10-11；experiment=FE_DEVICE_MULTIPATH_D22；kind=engineering diagnostic。
goal_statement：以已知多反射及一次路径切换检验冻结MDF的坐标响应和恢复过程，接续D21简单路径结果。
本轮primary=adk-planning-execution-loop，supporting=adk-verification-before-completion；总体目标active。

## P1 基线、假设和构造

D21 result/binding SHA256分别为7441e49b516a810fdda0f7acc91095771ddb29a4c9fd2fab5b376205bd4c55c0 /
a368f3f69ffbfe1a567343e4be96c8c06fbfdc5de97f80e49a59b025ff4539d9；起止核全绑定。
继承D18真实libaudio_pipeline.a SHA256 eb5b0c784c316e71d6ed9f58db6cb66f190b631daa00c55a94032168d5a47aa4、生成头和实际C_DEFINES。
独立单通道AEC内部API、16k/160点、20秒320000点/2000帧；mu0.22f、taps1536、stride2，enabled1/far1/dt0固定。
SYNC链接桥仅转发真实D18函数，实际调用必须0。AEC函数体、产品参数和完整CALL链路均不改。
沿用D21的uint32 xorshift seed0x12345678、逐步截断及低16位/262144归一化；future仅raw[160000:]反号。
两条路径按下表顺序float32乘加：每次乘法和累加均float32舍入，负索引项为+0；三个延迟全部落在1536点跨度内。

| path | 按顺序的(delay samples, gain) |
| --- | --- |
| A | (48,0.5), (176,-0.25), (400,0.125) |
| B | (80,0.375), (240,-0.125), (560,0.25) |

static-A始终A；static-B始终B；switch在n<160000时A、n≥160000时B，所有分量从绝对时间轴过去raw取值。
reference[n]=raw[n-offset]，offset仅16/20；mic无近端、噪声、房间录音或非线性；data_role=synthetic-engineering。
假设：单延迟收敛不足以说明多反射及切换恢复；固定两坐标可能表现出不同但非单向的工程响应。
本实验是测量诊断，无参数搜索、质量晋升阈值或候选选择；无改善或恢复不足均原样保留。

## P2 执行与固定测量

六主臂static-A/static-B/switch × offset16/20；三个negative均static-A/ref16：disabled enabled0、hold far0、zero reference全0。
repeat为switch/ref20 normal；future为switch/ref20且raw后半反号，总11次实际执行。
三negative必须echo全0、residual等mic、weight_l2全0；repeat全trace/CSV逐byte相同；future前160000点trace/1000帧CSV逐byte相同。
switch对同坐标static-A前160000点四trace/1000帧CSV逐byte同；switch后半mic/reference对static-B逐byte同，输出/state不要求同。
静态及switch各坐标配对mic逐byte同；所有trace长度/finite/完整独立构造、mic≈echo+residual≤1e-6；实际CSV与D21同字段/范围。
保存whole和固定窗口0–2、8–10、10–10.5、10.5–12、12–14、18–20秒的RMS/peak/已知纯回声工程ERLE。
公式沿用D21：ERLE=10log10(mean(mic²)/max(mean(residual²),1e-20))；RMS floor1e-12。
报告三组offset20-offset16 whole/所有窗差；另报告switch-minus-static-B在四个切换后窗口的差，禁止把冷启动B状态当真实设备稳态。
固定窗口反映切换瞬态与后续恢复，不移动窗口、加时或调整门限获得改善；不从工程ERLE推声学收益。

## P3 门禁、边界与接续

work_item_kind=implementation；implementation_permission=用户已授权研究；scope仅新研究runner/tool/tests/docs及README追加。
required_evidence=冻结合同、真实严格C11编译、11次执行binding、非仓cwd help/dry-run、定向已知答案/negative、独立全量audit/whole-change。
输入继承原119锁及D18/D19/D20完整依赖，D21全部70工件/源hash起止核，任何漂移停止replan；新/tmp输出不覆盖原目录。
retry_budget=2；staleness_threshold=任一锁变化；命令timeout120；heartbeat绑定实际进程；attestation_readback=起止全锁与计划hash。
plan_completeness=P1/P2/P3均有合同/退出；stop_condition=pass/replan/blocked/abort；claimant=root；verifier=device_capture_independent_review；open_items=3。
completion_claim仅D22诊断；logical_task_open=true；milestone_close仅D22；handoff_target=后续受控诊断；retention=仓内reviewing candidate及临时绑定工件。
当前live main 1be9b89af778783bdbe695c72d048b3d77eee948的summary成功；#657 OPEN，新PR#715等独立研究不与本轮混用。
不SCM外写/设备写，不批准产品默认、AISpeech、ASR/KWS、真人/物理/HIL/E001/owner资格；Provider route unresolved仍NEEDS_REVIEW。
