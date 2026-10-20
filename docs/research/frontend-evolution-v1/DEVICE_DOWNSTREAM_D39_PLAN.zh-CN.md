# D39 冻结下游接续实验合同

2026-10-11，experiment=FE_DEVICE_DOWNSTREAM_D39。goal_statement=全面推进优化迭代；当前D38完成不等于总体目标完成。primary=adk-planning-execution-loop，supporting=adk-verification-before-completion。前轮分类progress。

## P1 基线、问题与单一变化

kind=bounded research integration；question=在冻结的实际Activity/双AEC/保持选择/过渡输出之后，接续canonical CALL/FULL NS联合频域RES、受控AGC和VAD时，原primary与selected各自匹配回声估计是否能正确连续传播，原近端/恢复窗口代价怎样变化。
唯一集成变化为接续已有下游算法；不修改算法、门控、选择器、过渡、默认、API或第三方依赖。不是重跑AEC、不是已安装SDK完整集成，也不是新near检测器。当前D30已保存的selected残差与echo共同过渡，mic=echo+residual误差受旧合同约束；本轮不重新选择bank或根据结果调参。
local HEAD572b0e34a8a8e5663397ce16e378209ba9058d4d；保留用户dirty及D0–D38。
fresh live main d3f89e54beed483fcc0f8ce59e74b28533ed19b5，77checks全部completed，无failed/incomplete；open PR721/717/714/708/695独立，不批准本地。#657仍为研究总tracker。
输入D30根/tmp/audio-fe-device-activity-d30-20261011，result SHA256=e0b74142093d4579615be9ffe047335b4618f46aa1116f0b24941bb921de470d，binding SHA256=2558d74e0e8377087bcb1a44fc3e13d890c4da9b641b579db9d670e207083956。完整source/input/artifact起止身份核验，不强锁可追加的README历史字节。
链接原D18静态库eb5b0c784c316e71d6ed9f58db6cb66f190b631daa00c55a94032168d5a47aa4及其实际flags/generated headers，不重编库。核其canonical pipeline/enhance/NS/AGC/VAD等原source身份与D30依赖，不使用漂移的当前源码替换旧库。
32已查看field、12synthetic主case，另原repeat/future，共46输入；数据角色保持development-and-synthetic-engineering，独立裁判不改变数据角色。无搜索/优化/新声学裁判，NO_PROMOTION。

## P2 固定矩阵与处理、测量

每输入两个独立下游臂primary和selected，共92次实际C执行，各自产生bypass.f32le、ns.f32le、final.f32le、control.csv。每臂只有一套持续NS/AGC/VAD状态，bank切换不重置下游历史；两臂不共享状态。primary输入primary_echo/primary_residual，selected输入echo/residual；actual far/dt只由原D30 activity.csv逐帧转为2字节gate，并核帧号和0/1，不从near标签推导。
16000Hz/160点；ap_ns_init160；ap_ns_process(AP_ENHANCE_FULL,ns_floor=.12f,frequency_enabled=1,far,dt)；按canonical配置不执行时域ap_res_process，res_calls=0；AGC(-20dBFS,limiter-2dBFS)，allow=!(far&&!dt)；VAD接收本帧final及本次NS probability/use_upstream=1。没有额外尾帧、预读未来、跨case历史或后处理reset。
旁路必须逐byte复制输入残差。control.csv记录frame、far/dt、frequency_active、NS speech_probability/noise_rms_dbfs/residual_gain、agc_allow/gain_before/gain_after、VAD probability/active/noise_rms/hangover；finite/range/实际调用计数及AGC禁止增益增长严格检查，frequency_active=far&&!dt。input/gate/ns/final样本数一致且无隐式截断；f32 LE。
原46输入包含完整repeat与future，共92执行：两臂repeat所有输出全量逐byte同；两臂future所有输出通知前1247帧前缀逐byte同，未来不评分。field零参考状态保持真实，不伪造声学回声或真人标签。
保留原whole及240个fixed windows。后处理NS OLA固定一帧/160点历史：明确input_range=[a,min(b,N-160)]、output_range=[a+160,min(b+160,N)]，空区间null且披露tail截断；原区间另存不覆写，不逐case寻优延迟。不追加尾帧，不评估丢失最后一帧。现有rms_peak仅用于工程RMS/peak与synthetic已知near差值，非独立音质/KWS/ASR裁判。对齐近端误差用原near在input_range、输出在output_range。原AEC-input error作为分开基线，不能与未对齐后处理直接求声学收益。
两臂相同对齐区间逐窗final能量与known-near误差差值保留，不以whole改善覆盖near或退回代价。原D30事件计数只引用，不能声称本轮重跑AEC。VAD只报告actual active计数/概率与固定合成near窗重叠，不声称真人准确率。
实际sizeof NS/AGC/VAD/framebuffers分别报告，追加下游局部预算65536B，合计D30 scoped71224B加下游state与显式buffer须<=131072B；B0 50000B不改，不以局部预算替代目标线程栈/RSS/CPU/p99/热功耗。C临时FFT栈及stdio非全资源声明。

## P3 验收、责任与停止

scope_write仅新D39 PLAN/C/tool/tests/RESULT/REVIEW与README入口，原D0–D38只读。implementation_permission=用户研究授权，计划独立PASS后实施；claimant=root，verifier=device_capture_independent_review。
exit_gate=92 actual执行/旁路exact/控制顺序和字段/原库与输入起止hash/输出finite及同长度/实际计数sizeof/两臂repeat/future/原区间及固定160点对齐披露/负路径保护/独立审计/whole review/中文docs与Runtime final。
编译strict C11 O2 Wall/Wextra/Werror/Wconversion/Wshadow/pedantic/ffp-contract=off，原定义与库；从非仓cwd实际help/deepdry及定向测试；argc/frames/mode/gates非法在打开输出前拒绝，sentinel保持；新工具对已有D30根/仓根/已有D39根必须拒绝且完整manifest不变。
子命令timeout120s，主执行预算1800s，最多一次正式矩阵；retry_budget2仅修明确契约失败后新身份/根，不因观察超时重启live session。新/tmp根拒绝已有目录；工具失败保存measurement-invalid，不覆写旧根。逐case数组释放，不整批积累PCM。
独立审计不导入D39 measurement helper；完整回读92输出、count/flags、输入旁路与起止锁、重复/future、延迟区间及工程统计。工程float日志9位可恢复f32；能量rms依已有rms_peak，独立反向复算明确abs tolerance=1e-10 dB、peak exact，不遇失败放宽。
measurement任何不符MEASUREMENT_INVALID→replan保留失败；测量有效固定DOWNSTREAM_INTEGRATION_DIAGNOSTIC_NO_PROMOTION，无产品晋升门槛。promotion_allowed=false、shipping_approved=false。
logical_task_open=true；open_items3；completion_claim仅冻结下游接续与其工程代价诊断；plan_completeness=P1/P2/P3；attestation_readback=source/input起止哈希与真实回执；staleness_threshold=冻结依赖漂移立即replan；heartbeat=actual handles/Runtime；stop_condition=pass/replan/blocked/abort。
resource_matrix=root主矩阵写新根，终态后冻结；audit只读，不并行修改共享源/库/输出；handoff_target=已安装完整SDK/独立真人效果与目标板资源资格。Provider route unresolved，知识NEEDS_REVIEW，仅仓内reviewing材料，不冒称已归档。不commit/push/PR/merge/release/设备写。
