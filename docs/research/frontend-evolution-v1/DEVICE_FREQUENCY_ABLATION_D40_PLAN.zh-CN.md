# D40 频域 RES 单因果对照计划

2026-10-11，experiment=FE_DEVICE_FREQUENCY_ABLATION_D40，kind=bounded research causal integration。goal_statement=全面推进优化迭代；D39本地完成不完成总体目标。primary=adk-planning-execution-loop。当前仅冻结计划，不代表实现、执行或PASS；独立计划审查通过后实施。

## P1 原因、身份和唯一变化

D39实际接续完整下游后，合成含near固定窗口每臂24组，final对bypass的已知near工程误差中位+9.3418dB；每臂3200输出帧原far=1/dt=0，频域RES持续启用。尚未隔离是普通NS还是频域RES对近端代价占主因，不能凭观察调双讲阈值或shipping算法。D40假设：关闭频域RES会减少部分near失真，同时暴露纯echo残余代价；无预期PASS效果阈值、不寻优参数。

基线严格为D39正式result SHA256=3bf15108885f0b356e0ebcc1f799a2de6178a12665b71aa13ffa79d1774f93fc、binding SHA256=26a53260fcd4662a90bb1a8649dbb47931b2e1474e534b613de80eea83639663；D39独立全量audit PASS，REVIEW SHA256=c7c3aff01ab095cf8cb50c9138d221eb402fdaf7c00c05a761080e6d07e14769、42项最终snapshot SHA256=badfd178be30df3f39cf992769d6d59a2e0e5756108224611516062f2529c71d。D39实际14项localcloseout exit0；其独立终态核验单列，不借本计划替代。

原D30匹配echo/residual、实际Activity gates、46输入与两臂独立持续状态保持。唯一DSP配置变化为ap_ns_process的enable_frequency_res由1改0，对所有帧统一关闭，不从near标签选择帧、不修改far/dt、普通NS floor .12、FULL模式、AGC target-20/limiter-2、allow=!(far&&!dt)、VAD、过渡或AEC。仍链接D18原库，不重编库或AEC。原source ap_ns.c中noise_tracker使用抑制前spectrum power；freq_res只改变echo分析/残余gain与输出，提供可核的同输入普通NS统计对照。关闭支路不代表推荐产品关闭RES。

## P2 固定测量、已知答案和预算

新root拟为 `/tmp/audio-fe-device-frequency-ablation-d40-20261011`，92次新C执行，D39作为锁定对照不重跑。46输入包括32field、12合成、repeat、future；数据角色development-and-synthetic-engineering。两臂不共享状态、不reset，不追加flush。16000Hz/160samples，4输出bypass/ns/final/control；新增身份的C/tool/tests，原D0–D39只读。

全部bypass必须对原输入及D39逐byte同；Activity gates与allow保持；frequency_active全部0、frequency RES reported residual_gain全部1。D39/D40每帧普通NS speech_probability和noise_rms_dbfs必须恢复float32后exact相同，不能因代价不符合预期放宽。原频域从未激活的现场case，其全部4输出须与D39逐byte同；若该原case实际存在激活帧，按实际回读标记，不擅自宣称该已知答案适用。两臂repeat全量、future通知前1247帧及CSV前缀逐byte同。

原nonfuture每臂45whole+195fixed，两臂90whole+390fixed=480总测量组；固定原sample_range及input/output160点坐标、tail截断/empty/null与D39一致。各stage RMS/peak及合成known-near error分别重算，并与D39同坐标作差；固定near/no-near类别由原标签用于描述分组，不反馈算法或选候选。只报告工程误差、能量与VAD控制重叠，不增加真人音质/KWS/ASR资格。不把whole改善替代near/退回各窗代价。

sizeof预算保持下游<=65536B、加D30 scoped71224B合计<=131072B，B0 50000B保持；真实编译、执行时间、状态sizeof分开记录，不宣称整线程/目标板资源。子命令timeout120s，主正式矩阵最多一次/预算1800s；live观察超时核同handle，禁止重启。

## P3 验收、审查和停止

scope_write仅新D40 PLAN/C/tool/tests/RESULT/REVIEW/CLOSEOUT，最终审查时再追加README入口；用户dirty与D0–D39保持。计划独立PASS后实施，strict原CFLAGS及原D18defs/lib、非仓cwd help/deepdry、定向真实测试、非法argc/frames/mode/gates保护与已有root完整manifest保护；命令先xintent，异常保存真实null exit/partials且拒绝重放。

独立audit不importD40 measurement helper、不复跑DSP；覆盖全部92执行/PCM、真实gate/普通NS统计exact对照、effectivegain逐sample/AGC及VAD float32递推、全部480测量组与fixedrange、repeat/future/预算/源输入制品起止锁。RMS反算abs tolerance1e-10dB、peak exact；NSFFT不独立重算边界保留。任何身份、数值或measurement合同失败→MEASUREMENT_INVALID_REPLAN，保留失败根与回执；不改阈值、造窗或重跑同根。retry_budget2仅明确缺陷后新身份/新根。

有效测量固定decision=FREQUENCY_ABLATION_DIAGNOSTIC_NO_PROMOTION，promotion_allowed=false、shipping_approved=false，无效果晋升阈值。普通NS仍可能带来近端代价，实际无改善也须保留；只有完成单因果对照才能归因其配置影响，不把禁用支路建议升级成产品默认。独立whole review、中文docs和localRuntime终态分别核验。

claimant=root，verifier=device_capture_independent_review；logical_task_open=true，open_items3；completion_claim仅本轮因果对照；plan_completeness=P1/P2/P3；staleness_threshold=冻结依赖漂移立即replan；attestation_readback=输入/来源起止SHA与actualreceipts；heartbeat=实际阶段进展/已确认live handle；stop_condition=pass/replan/blocked/abort；resource_matrix=主新根写终态后audit只读、共享库与source不并行改。

handoff_target=解释完整下游near代价后，再决定是否有足够证据设计非oracle双讲保护研究；不恢复相似相关性标量阈值反复寻优。完整SDK、AISpeech固定点链路、真人near/QIVW和目标板资格独立待证。Provider route unresolved、知识NEEDS_REVIEW；不冒称归档成功、不commit/push/PR/merge/release/设备写。总体nativegoal继续active。
