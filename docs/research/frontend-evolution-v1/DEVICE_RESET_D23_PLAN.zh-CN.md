# D23 状态保持与重置：冻结收益和误触发代价合同

日期2026-10-11；experiment=FE_DEVICE_RESET_D23；kind=engineering diagnostic；总体目标active。
goal_statement：在D22同输入同时间轴上比较已知切换处full reset的恢复响应与稳定路径误reset代价。
primary=adk-planning-execution-loop；supporting=adk-verification-before-completion。

## P1 冻结基线和唯一因果操作

D22 result/binding SHA256为96c7e749eac0e435b28e9f0ffdfe4d7985adc2e7bc7e4c45b8b25ac5ac77dd78 /
fdcd9b3e4ead2e3d7767a30a1eacaefdcad8c6fe9f64e7ca88a505e48b727a19；起止完整核锁70工件及source依赖、原119输入。
继承D18真实库eb5b0c784c316e71d6ed9f58db6cb66f190b631daa00c55a94032168d5a47aa4及实际宏/头；不改DSP函数体。
16k/160点，20秒320000点；mu0.22f、taps1536、stride2、enabled1/far1/dt0固定，SYNC bridge实际调用0。
直接复用冻结D22 C构造与测量合同：xorshift seed、顺序float32三tap、static A/B及10秒A→B switch、reference16/20，禁融合。
仅新研究wrapper截获单通道内部AEC调用：keep从不reset；reset在frame1000处理前调用一次原ap_aec_backend_reset。
该API清权重及参考频域历史/prev_ref/功率，保留维度/配置并重置运行态；不是只清权重，不称检测器或完整CALL路径事件。
报告真实reset次数/帧及调用前weight_l2、返回后weight_l2/x_power_total/steady_frames/x_head，不能仅从代码推断实际reset发生。
keep的上述reset前后观测字段为null，reset实际调用帧1000、次数1，返回weight/x_power/steady均0、x_head47。
稳定A/B的同时间reset代表误通知，switch reset代表已知真事件；通知由工程fixture提供，无真实检测资格。

## P2 固定执行、比较与测量

12主臂=static-A/static-B/switch × reference16/20 × keep/reset。
三negative均A/ref16/reset：disabled、hold、zero，沿用D22门控/零参考定义，echo零/residual等mic/权重零必须。
repeat=switch/ref20/reset normal；future=switch/ref20/reset且raw后半反号，总17次完整执行。
六keep的四trace/完整CSV对D22同臂逐byte相同，证明新wrapper等价；keep/reset全程mic/reference逐byte同。
每主臂reset对keep前160000点四trace/1000帧CSV逐byte同；repeat全量同；future前半同。
所有trace长度/finite/独立完整构造/mic≈echo+residual≤1e-6、实际state CSV范围沿用D22；不能将weight_l2当适配次数。
统计whole与0–2、8–10、10–10.5、10.5–12、12–14、18–20秒固定窗口，公式/RMS floor/峰值沿用D22。
报告每shape/offset的reset-minus-keep whole/六窗ERLE与residual RMS差；稳定A/B负效应与switch收益全部原样保留。
不搜索事件时间、reset强度、参数或窗口；不设晋升质量阈值、不延时洗绿；尚无目标值，诊断结果允许差/无改善。
data_role=synthetic-engineering；decision=RESET_BENEFIT_FALSE_EVENT_COST_DIAGNOSTIC_NO_PROMOTION；promotion/shipping均false。

## P3 验证、退出与边界

scope=新研究wrapper/tool/tests/docs及README追加；work_item_kind=implementation；implementation_permission=用户已授权研究。
required_evidence=冻结计划/实现复审、严格C11真实编译、17次binding、非仓cwd help/dry-run、配对差已知答案/目录负例、独立全量audit/negative/whole-change。
新/tmp输出，保留既有dirty与工件；retry_budget=2；命令timeout120；staleness_threshold=任一锁漂移即replan；heartbeat真实handle。
attestation_readback=计划/库/源/原输入起止hash；plan_completeness=P1/P2/P3；stop_condition=pass/replan/blocked/abort。
claimant=root；verifier=device_capture_independent_review；open_items=3；completion_claim仅D23本地诊断；logical_task_open=true；milestone_close仅D23。
handoff_target=有依据的状态策略/事件可靠性研究；retention=仓内reviewing candidate与临时绑定工件。
live main 1be9b89af778783bdbe695c72d048b3d77eee948本轮fresh summary成功，#657 OPEN；它们不批准本地未提交实验。
Provider route unresolved保持NEEDS_REVIEW。不改产品API/默认或检测逻辑，不SCM外写/设备写；历史拒绝、AISpeech、真人/ASR/KWS/资源/HIL/E001/owner资格分别待验。
