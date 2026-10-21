# D20 首次分歧时序：冻结分析合同

日期2026-10-11；experiment=FE_DEVICE_TIMING_D20；kind=diagnostic。
goal_statement：利用D19已实测完整记录，检查AEC输出分歧与实际far/double-talk门控分歧的先后，缩小下一因果假设。
数据已用于D19和本轮初查，角色保持development；不称blind，不做参数选择或声学评估。

## P1 输入与分析范围

D19 result SHA31998072bdb2e2836ee87722e776919e442fe836ffee48537006579910e9cd84；
binding SHA47d4a0fe0c8e1c0a2eafb02262efd6abc449f0c6a5004557c75650356fded2a0。
核全部binding工件、依赖、59源码、执行文件与119原输入锁，读取16场景×2臂全量记录；不再执行DSP。
live main为1be9b89af778783bdbe695c72d048b3d77eee948，#657 OPEN；新main无已验证summary，不能借旧CI资格。
本轮初查已看到部分控制字段全程相同及部分差异晚于AEC输出；本合同冻结完整逐例核验，不把初查当独立结论。

## P2 固定时序测量

reference与5条stage按Float32LE逐4字节比较，报告首次bitwise差的样本/帧/帧内offset；不得动态对齐或设“显著”阈值。
全部有限、长度恰等D19前缀；8零参考场景所有trace相同，AEC输入16场景全相同。
NS/AGC trace原坐标额外报告固定160点对应输入位置；首次启动差异不因此删除。
逐CSV字段报告完整不相同帧数、首次与最后帧，连续差异区间；帧号连续，9字段严格、数值有限。
实际far/dt为0/1，frequency_enabled=1，agc_allow=!(far&&!dt)，控制与公共JSONL逐帧相同。
只定义gate_eligible=far&&!dt，来自冻结MDF do_adapt谓词的一部分；不称实际adapt次数。
实际do_adapt还需adapt_due与x_power_total，本记录没有这两个值，不重建或伪造内部滤波/步长状态。
每例把首次AEC residual差帧与首次gate_eligible差帧分为before/same-frame/after/no-gate-difference/no-output-difference。
同帧不能由本分析得到子块内部因果排序；报告CSV控制是在AEC之前决定，但不推断实际权重更新时间。
同时保留far/dt联合字段首次差和所有参考/阶段首次差；不以总次数代替时序。
所有索引仅为AP replay前缀坐标（160点/帧、16k）；秒数为该前缀坐标，不称场景PTS或物理播放时刻。

## P3 验证与收口

结果固定TIMING_DIAGNOSTIC_NO_PROMOTION；读锁/测量错误则MEASUREMENT_INVALID，不修改D19工件。
工具仅新/tmp输出，help/dry-run从非仓cwd；已存在目标不得写入，异常仅本次创建根保留失败。
定向已知答案/负例覆盖首次差/区间/零参考/非有限/短长度/目录归属。起止读锁不变，保存原输入/D19/tool/计划身份。
独立验证直接复算所有16例首次差及控制区间并核whole-change；不调用新工具分析函数自证。
completion_claim仅D20时序分析；claimant=root；verifier=device_capture_independent_review；open_items=3。
retry_budget=2；staleness_threshold任一锁漂移即replan；每命令timeout120；heartbeat记录实际进程句柄。
stop_condition=pass/replan/blocked/abort；attestation起止回读；logical_task_open=true；milestone_close仅D20。
primary=adk-planning-execution-loop；Provider route unresolved知识线NEEDS_REVIEW，仅仓内reviewing candidate。
不DSP改动/新回放/SCM外写/设备写，不改变历史REJECTED结果、shipping/API/E001及声学/物理/owner资格。
