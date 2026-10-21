# D27 双状态最短保持实验：冻结合同

日期2026-10-11；experiment=FE_DEVICE_DWELL_D27；总体目标active。
primary=adk-planning-execution-loop；supporting=adk-verification-before-completion。
kind=bounded research algorithm experiment；question=只增加切换后的最短保持，能否减少D26往返切换而保持既有工程路径恢复/退回与近端门控。

## P1 基线、边界与单因果假设

本地HEAD572b0e34a8a8e5663397ce16e378209ba9058d4d，既有dirty保留。
fresh live main373008e89f2ebaabc298d2c9613420b1d4811c78，required summary completed/success；这是线上main证据，不批准本地D27。
#657 OPEN；PR717/714/708/695独立，不改远端。Provider route unresolved，知识线NEEDS_REVIEW。
D26 result/binding=51c2007f9dfa74a8f6ea032dd8caba79137b34a0379da55c79e69dac016ef42c / 4dc0a3459d686abc5a86b6c7ad423bfa4294102ee5dfbbc0b63451ae2a097309。
D25 result/binding=5ceae16bc4e9587e669aac90c9f8fa8be55a60077b98733606190e7ea2a466d6 / d5b5e273b311bb38d91d3a68b16986a12f6c548af83d721ded774b6a2e6f626e。
冻结D24比例0.8/三帧确认、当前帧double順序能量、eligible=far&&!dt、双向、无crossfade。
仅新增研究选择器的固定dwell=50帧（500 ms），无参数网格或第二候选，产品AEC/SYNC/Activity/RES/NS/AGC/API/default不改。
research_algorithm_changed=true、shipping_algorithm_changed=false；不使用独立验证或blind数据选型。

两AEC状态的演进独立于输出bank选择，故本轮直接读取冻结D26/D25的四条primary/shadow估计回声/残差trace，不重跑AEC、不改变状态或输入。
这是对这些固定状态轨迹的因果输出选择实验，未证明新闭环检测、产品整链或运行时集成。
假设与选择依据：保持500 ms对应控制输出至多约2次/秒的工程稳定性要求；避免首次接管延迟，并显式检验短路径退回。
不能把少切换自动解释成更好音质，保持旧bank期间的能量代价必须一起报告。

## P2 确切算法、矩阵与测量

初始bank=0、streak=0、has_last=false；未active时bank/streak及has_last清零。
若active且已切换且frame-last_switch<50，则保持bank，streak清零，不累计确认；依然校验有限非负两能量。
其余帧执行冻结D24规则；切换当帧输出新bank，并记录last_switch。
hold_remaining为切换后50减当前距上次切换帧数，下限0；未active或无历史切换为0。
因此首次切换与legacy相同，相邻切换最短52帧（520 ms：解锁帧重新开始三帧确认）。far/dt不暂停帧时钟；失去eligible仍清streak。
legacy模式dwell=0必须逐帧复现冻结D24，不变更输入能量顺序、输出时机或D24文件。

32个D26主shadow源（16场景×fixed1/used0）和12个D25主shadow源（A/ABA×r16/r20×echo/dt/unguarded），各legacy/dwell=88次真实C选择器执行。
不挑有利设备场景：8无通知场景均纳入；D25已知独立噪声及oracle dt保持工程身份，不称真人。
额外case07-used0-dwell重复与有限未来控制2次，共90次；不纳入原D25/D26 repeat/future作为主矩阵。
D26 active/far/dt逐帧从原selector.csv读取并与原gates.bin核一致；D25 active/dt读原selector.csv，far固定1（原fixture语义）。
四条trace直接读取float32LE原字节、160 samples/帧；gate转换为active/far/dt三个显式byte并绑定hash。
输出selected echo/residual及selector.csv十字段（frame,active,far,dt,bank,streak,change,primary_energy,shadow_energy,hold_remaining）。
新C只执行选择器，不链接AEC库；报告真实sizeof选择器与调用次数，不包装成DUT RAM/CPU/热预算。

legacy两输出必须全量逐byte等原selected输出，selector前九字段投影等原D26；D25排除far/hold后的投影等旧八字段。
Python复核两模式完整逐帧递推/能量/gate/selected字节/计数、首次切换、最短间隔、无通知与稳定不切换、通知前前缀。
使用原D26/D25已冻结的窗口、范围、RMS/peak算法与shadow null资格：D26 whole及4-6/10-12/19-21s；D25 whole及原八窗。
逐窗输出新selected与原selected残差能量差；D25另报告相对原selected的known near error差与原有known echo指标资格。
所有增加、下降、无变化均保留；D26没有clean target，不称ERLE/残回改善/人声损伤。
逐事件记录帧、方向、相邻样本边界差及两bank首样本差；不新加事件居中声学窗、不声称无点击。

repeat三文件全量逐byte同。
未来控制从case07原通知帧起在C内将primary两trace乘1.125f、shadow两trace乘-0.875f，gate/通知保持；仅控制样本变换，不声称真实AEC或代数成立。
前缀三文件逐byte相同；后半只核有限输出与递推，不计入设备/近端测量选型，不据冻结gate声称新Activity结果。

## P3 验收、预算与收口

测量有效性硬门：旧依赖全hash及起止一致，legacy输出/selector投影等价，C/Python逐帧一致，有限/长度/窗口/null/负例/重复/前缀；失败即MEASUREMENT_INVALID，不改阈值。
工程候选准入独立于测量有效性：D26主激活16臂总切换至少降低25%（538→不超过403）；每臂首次切换不延迟，间隔至少52帧；稳定/无通知对照输出不变。
D25 A稳定输出全量不变；ABA echo/unguarded保留首次接管1002帧及退回1202帧，两坐标均验；dt保持无切换。
D25所有原有窗口selected known-near error相对旧shadow增加不得超过0.5dB；值来自既有工程目标，不是独立真人或质量阈值。
任一候选条件失败，decision=DWELL_DEVELOPMENT_REJECTED；全部满足则DWELL_DEVELOPMENT_CANDIDATE_ONLY；两者promotion_allowed=false、shipping_approved=false。
仅一个候选，不在结果后改500ms、25%、0.5dB或窗口来通过门禁。

scope_write=新D27 PLAN/C/header/tool/tests/RESULT/REVIEW及README对应入口；D24-D26、产品源与既有dirty不改。
先独立计划与实施审查，再严格编译/C self-test、完整参数sentinel拒绝、90真实选择器执行、非仓cwd help/dryrun和定向正负测试。
每命令timeout120秒；父编排观察同live handle，不因观察超时重跑；retry_budget=2，任何失败保留，回计划审查。
新/tmp根；missing/真实input×旧D26/新D27/仓根六工具负例均拒绝且原根完整manifest不变。
独立actual审计不导入新工具、不重AEC或新C：核源hash/旧工件/所有gate/trace/selector/窗口/差值/事件/验收结论。
staleness_threshold=任一冻结源/依赖漂移即replan；heartbeat=实际运行handle/Runtime；attestation=源/依赖起止hash回读。
claimant=root；verifier=device_capture_independent_review；open_items3；plan_completeness=P1/P2/P3；stop_condition=pass/replan/blocked/abort。
completion_claim仅D27有界工程候选实验；logical_task_open=true；handoff_target=独立真人/切换边界/完整后处理/目标资源；retention=仓内reviewing candidate。
无commit/push/merge、设备写或正式归档；AISpeech产品及KWS/ASR/HIL/E001/owner资格保持独立未闭合。
