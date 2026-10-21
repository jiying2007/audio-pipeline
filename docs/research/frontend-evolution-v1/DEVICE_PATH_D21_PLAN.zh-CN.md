# D21 已知路径与固定门控：冻结实验合同

日期2026-10-11；experiment=FE_DEVICE_PATH_D21；kind=engineering diagnostic。
goal_statement：在已知线性回声路径、固定门控下检验参考坐标变化与MDF收敛响应，不将D20时序推断成算法缺陷。
本轮使用adk-planning-execution-loop及独立计划/whole-change验证；总体目标active。

## P1 冻结基线和构造

继承D18 libaudio_pipeline.a SHA eb5b0c784c316e71d6ed9f58db6cb66f190b631daa00c55a94032168d5a47aa4及原生成头/实际C_DEFINES。
D18 source的AEC函数体未改；D18仅SYNC定义改名，本轮独立AEC内部API不调用SYNC，不重新链接整条pipeline。
实际unity对象仍引用原SYNC符号，因此runner提供仅转发到D18 real函数的link bridge；计数必须0，任何调用使本轮无效。
核D18完整binding、59源码/构建/工具依赖及原119输入锁，D20 result/binding固定66126f7b6ea71347a2cdd9a18ec72f1ac5b33a96a0a5b9d6e402da1823f65180/eca1f9ac9d4276a6184a389e5eca46d8dbb99892c0a007044c8d667b62aa6c21。
live main 1be9b89af778783bdbe695c72d048b3d77eee948本轮fresh summary已success；它不认证本轮未提交研究。
数据角色synthetic-engineering，非设备/真人/独立声学数据，不参与shipping选择。
16k，160点帧，20秒320000点；原CALL的AEC mu=0.22f、taps=1536（96ms）、stride=2，enabled=1、far=1、dt=0固定。
原始信号uint32 xorshift，seed=0x12345678，每点依次xor左13/右17/左5，每步uint32截断；
raw=((state低16位)-32768)/262144，范围[-0.125,0.125)；使用过去样本，负索引严格0。
mic[n]=0.5*raw[n-path_delay]，reference[n]=raw[n-reference_offset]，无近端/噪声/量化/额外前端。
只测试path_delay={32,48,64}×reference_offset={16,20}六臂，剩余有效路径均因果且小于滤波跨度。

## P2 执行与测量

六主臂；额外三个negative均path48/ref16：disabled(enabled0)、hold(far0/dt0)、zero(reference全0/far1/dt0)。
三negative必须echo全0、residual逐float等mic、权重L2全0，不以能量下降验收。
另重复path48/ref20 normal一次；另path48/ref20 future一次，仅raw[160000:]反号，mic/ref仍由修改raw的过去点构造。
总11次完整执行，2000帧/次。repeat全部trace/CSV逐byte相同；future前160000点trace及前1000帧CSV逐byte相同。
保存mic/reference/echo/residual Float32LE，全量finite/长度/独立构造匹配；mic≈echo+residual≤1e-6。
CSV每帧读取真实返回state：frame/runtime_stride/steady_frames/adapt_phase/constrain_partition/x_head/x_power_total/weight_l2。
weight_l2为active_partitions×bins复权重平方和的double累计，不重建实际adapt次数；内部维度/status固定MDF、32点block、48 active partitions。
保存whole以及固定窗口0–2/4–6/10–12/18–20秒的mic/residual RMS、峰值、已知纯回声ERLE=10log10(mean(mic²)/max(mean(residual²),1e-20))；
输入非零，各窗至少一mic非零；float RMS floor1e-12，与canonical声学评分分开，仅此显式纯回声工程诊断。
报告每个path的offset20-offset16 residual RMS/ERLE差，不定音质阈值、不以本实验选参数或批准算法。
过程错误则MEASUREMENT_INVALID；无改善/差异/不确定均原样保留，不调mu、时长或阈值洗绿。

## P3 门禁与收口

新runner只研究入口不安装SDK；Python工具进tools.codex_assets；新/tmp输出，非仓cwd help/dry-run，无覆盖已有根。
严格C11真实编译同库宏，非法输入exit2，已知构造/negative/短长度/NaN/目录归属定向测试；source/库/输入/工具起止hash相同。
独立审计全11执行构造、窗口统计、CSV真实状态约束/负例、repeat/future、全hash及whole-change。
decision=KNOWN_PATH_COORDINATE_DIAGNOSTIC_NO_PROMOTION；completion_claim仅D21工程诊断；claimant=root；verifier=device_capture_independent_review；open_items=3。
retry_budget=2；任何锁漂移即stale/replan；命令timeout120；heartbeat真实handle；attestation起止回读；stop_condition=pass/replan/blocked/abort。
logical_task_open=true；milestone_close仅D21；Provider route unresolved为NEEDS_REVIEW，仅仓内reviewing candidate。
不改DSP函数体/产品参数/API，不SCM外写/设备写；历史REJECTED、AISpeech固定点产品链路、独立声学/ASR/KWS/HIL/E001/owner资格保持。
