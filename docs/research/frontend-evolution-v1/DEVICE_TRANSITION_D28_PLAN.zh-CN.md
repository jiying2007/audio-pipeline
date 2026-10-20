# D28 固定输出过渡实验：冻结合同

日期2026-10-11；experiment=FE_DEVICE_TRANSITION_D28；总体目标active。
primary=adk-planning-execution-loop；supporting=adk-verification-before-completion。
kind=bounded research algorithm experiment；question=仅平滑D27输出切换，能否消除起点附加跳变且不以过渡区能量/已知近端损伤换取改善。

## P1 身份、范围与单因果假设

local HEAD572b0e34a8a8e5663397ce16e378209ba9058d4d及既有dirty保留。
fresh live main373008e89f2ebaabc298d2c9613420b1d4811c78，required summary completed/success；线上证据不批准本地实验。
#657 OPEN；PR719/717/714/708/695独立；Provider route unresolved，知识线NEEDS_REVIEW。
D27 result/binding=c8b7cf96ee67facb504e502a2b5ec5a13f5c6f06eb84c6436ff5aad0d5513985 / c1d340bfea936ba6c01661245097eaa3621994479100803d0d201243348d1b4f。
继承D27已冻结的44个主dwell来源、原四bank轨迹与逐帧控制决定，不重选择器或AEC，不改D24/D27/产品源码。
只新增固定320点线性crossfade（16k下20ms、两帧）；无参数网格，不更改50帧保持/0.8/三帧确认或切换事件。
20ms为本轮有界工程假设而非最佳音质时长；初始通知/控制不代表物理路径真值。
research_algorithm_changed=true、shipping_algorithm_changed=false，promotion_allowed=false、shipping_approved=false。
设备数据为已查看development，D25合成噪声/oracle dt为工程对照；独立验证/blind不参与选择。

## P2 确切混合、控制、矩阵及测量

同帧两bank的echo与residual分别混合，权重完全相同，原麦输入、gate和bank演进均不变。
事件帧处理前保存from_bank并接受冻结new_bank，随后样本j=0..319，alpha=double(j)/319。
输出为float32(double(old)+alpha*(double(new)-double(old)))；alpha=0直接返回old原float，alpha=1直接返回new原float。
两路输出共用alpha，样本后推进一次；第0样本完全old、第319样本完全new，此后当前bank原字节直通。
没有lookahead或额外音频缓存；20ms是混合完成时长，不能说输出立即全量新bank或无可闻点击。
剩余过渡不因far/dt暂停；控制事件仍来自冻结D27 eligible规则。inactive清空过渡回primary，重叠事件必须在状态改变前原子拒绝。
实际矩阵无中途inactive或重叠，生命周期行为用明确正负自测覆盖，不伪称设备场景已覆盖。
硬切hard模式保持D27两selected输出完整逐byte等价；控制bank/change/active/far/dt投影必须全量同。

32个D26设备来源和12个D25来源各hard/fade=88次真实C输出处理；case07-used0-fade新进程repeat及future2次，共90次。
control.bin为active/far/dt/bank/change五byte每帧，显式转换冻结D27 selector.csv并绑定hash；不复制或重新推断gate。
输入四条bank原float32LE，160样本/帧；输出echo.f32le/residual.f32le和九字段CSV：frame,active,far,dt,bank,change,remaining_after_frame,alpha_first,alpha_last。
报告真实过渡状态sizeof和混合样本数；不链接AEC/选择器库，不报告DUT CPU/总RAM/功耗/热。

复核全部样本浮点混合、端点和过渡外byteeq、控制时机/剩余计数/alpha、输出长度/有限性。
正常输入全样本核estimated echo+residual与原mic相等至1e-6；field mic用原D19 AEC输入，return mic用D25原mic，显式源hash。
测量继续使用D26/D25原whole/固定窗口、RMS/peak与shadow null资格；报告fade-minus-hard selected能量及D25 known-near error差。
不增加事件居中声学评分窗口，不称设备ERLE/人声损伤；两状态输出混合也不代表完整NS/RES/AGC/KWS链。

事件工程边界单独记录：start_sample=frame*160、end_sample=start+319；起点输出与同刻old bank的差（附加跳变）；实际相邻样本差；hard同项；端点new原字节。
过渡区一阶差分平方和为math.fsum((y[k]-y[k-1])**2 for k=start..end)，包括起点前样本；hard在同样区间计算。
记录每事件hard/fade值和所有主设备事件合并和，不解释为感知音质或click-free；这是预先冻结的工程边界指标，不是新声学裁判。
原有whole/固定窗始终完整报告，避免只展示起点而隐藏320点内代价。

repeat三文件全量同。future从case07原通知帧起primary两trace乘1.125f、shadow两trace乘-0.875f，冻结控制不变。
通知前三文件前缀同；future后半只核有限/混合/时机，不核原mic代数、不评分/不参加候选准入、不冒称新真实AEC或D27重新选择结果。

## P3 验收、预算与收口

测量有效性：D27及旧依赖全hash/起止同，hard输出完整等价、控制投影同、精确混合/端点/过渡外同、样本数/有限/代数/窗口/null/重复/前缀/负例通过。
失败即MEASUREMENT_INVALID，保留失败不放宽要求。
工程候选准入：所有主事件fade起点附加跳变绝对值<=1e-8；设备243个主事件的合并一阶差分平方和不高于hard；D25所有原窗口known-near error增加<=0.5dB。
所有无事件来源输出全量不变、D27控制事件帧/方向/次数不变（设备243、D25共8），为硬契约而非声学保护证明。
任一候选条件失败则TRANSITION_DEVELOPMENT_REJECTED；全部满足则TRANSITION_DEVELOPMENT_CANDIDATE_ONLY；均promotion/shipping=false。
仅一个20ms候选，结果后不改时长、指标、0.5dB、窗口或挑选事件以通过；失败保留D27候选，后续转向真实近端/闭环证据。

scope_write=新D28 PLAN/C/header/tool/tests/RESULT/REVIEW及README本轮入口；旧源码/工件/dirty保留。
独立计划/实施审查后严格编译/生命周期和端点自测/完整非法参数sentinel/90真实执行；非仓cwd help/dryrun/定向正负测试。
每命令timeout120秒；父编排只观察同live handle；retry_budget=2；失败保留并回计划审查，不因观察超时重跑。
新/tmp根；missing/真实input×旧D27/新D28/仓根六工具负例均拒绝，完整原根manifest起止相同。
独立actual审计不导入新工具或执行C/AEC：核所有source/input/control/输出/alpha/事件/原window/null/代数/候选准入、真实失败历史。
staleness_threshold=任一冻结依赖漂移即replan；heartbeat=实际live handle/Runtime；attestation=起止hash回读。
claimant=root；verifier=device_capture_independent_review；open_items3；plan_completeness=P1/P2/P3；stop_condition=pass/replan/blocked/abort。
completion_claim仅固定轨迹过渡工程实验；logical_task_open=true；handoff_target=真实近端/检测闭环/完整后处理/目标资源；retention=仓内reviewing candidate。
无commit/push/merge、设备写或正式归档；AISpeech产品、KWS/ASR、独立真人声学/HIL/E001/owner资格独立未闭合。
