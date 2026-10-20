# D26 设备开发数据双状态回放：冻结合同

日期2026-10-11；experiment=FE_DEVICE_FIELD_D26；kind=engineering integration diagnostic；总体目标active。
primary=adk-planning-execution-loop；supporting=adk-verification-before-completion。
目标：把冻结D24双状态选择器用于设备development AEC输入/实际参考/原Activity门控，核既有拒绝事件时间上的行为。

## P1 基线、权限和假设

D25 result/binding SHA256 5ceae16bc4e9587e669aac90c9f8fa8be55a60077b98733606190e7ea2a466d6 /
d5b5e273b311bb38d91d3a68b16986a12f6c548af83d721ded774b6a2e6f626e；D24 selector原header/规则不改。
D19 r1 result/binding SHA256 31998072bdb2e2836ee87722e776919e442fe836ffee48537006579910e9cd84 /
47d4a0fe0c8e1c0a2eafb02262efd6abc449f0c6a5004557c75650356fded2a0，原32臂AEC input/reference/echo/residual/control为回放来源。
D18原MDF库eb5b0c784c316e71d6ed9f58db6cb66f190b631daa00c55a94032168d5a47aa4、实际宏/头；D19只改符号的观测库仍与它身份分离。
继承119设备输入锁、D18/19完整源/工件身份及D25依赖；不重新编译产品或D19，不改变其PCM和旧结论。
本地HEAD572b0e34a8a8e5663397ce16e378209ba9058d4d与dirty保留；live main373008e89f2ebaabc298d2c9613420b1d4811c78，未见本轮required summary成功证据。
#657 OPEN，PR714/708/695独立；线上未批准本地工件。Provider route unresolved，知识线NEEDS_REVIEW。

假设：在原真实开发输入上保留旧状态，可观察受控reset后是否接管/退回及其能量变化；没有clean target，任何能量下降不批准声学收益。
research_algorithm_changed=false、shipping_algorithm_changed=false；仅新的research fixture/tool/tests/docs和README入口，原selector不调参。
完整双麦CALL已有D19观测，本轮只执行内部单通道AEC和选择器，不把其结果当完整NS/RES/AGC/QIVW输出或AISpeech集成。

## P2 来源、通知时间和固定测量

16个原development场景×fixed1/used0×keep/shadow=64次；另case07/used0/shadow新进程repeat与future，共66次实际执行。
每臂输入直接读D19 aec_input.f32le及对应reference.f32le；far/dt读同臂control.csv，序列与原JSONL核一致。
不转换回S16、不重新做BF/HPF/SYNC、不用录音左右麦猜AEC mono；原gate是该同输入Activity实际输出，不是独立人声真值。
16k/160点，init1536taps/stride2、enabled1/mu0.22f，primary实际echo/residual必须对D19完整逐byte相同，keep selected同primary。

reset通知来源为冻结D16 rejected候选replay/case-NN/default.jsonl实际counter序列：
逐帧核aec_resets/delay_jumps非降且同帧各增1，保存全部事件；每场景只取第一个原reset帧作为本轮外部控制时间。
没有原事件则schedule=null，shadow臂也不激活；其他原事件如有只保留诊断，不重复重置，不事后挑选某事件。
通知不是设备物理路径真值，不改变D16 REJECTED，也不声称fixed坐标下应当跟踪到该delay。
keep不reset；shadow在通知帧处理前复制primary并仅full reset第二状态，之后持续同输入/参数/gate；primary从不reset。
选择仍为当前帧double顺序残差能量、eligible=far&&!dt、另一能量严格<0.8×当前且当前>1e-20、连续3帧、双向、无crossfade。
无新探测器或参数搜索；primary/shadowcalls、resetcalls、SYNC实际calls0、sizeof真实计数。

输出6条trace：selected echo/residual、primary echo/residual、shadow echo/residual；selector.csv记录frame/active/far/dt/bank/streak/change/两能量。
state.csv保存primary同D22八字段；源AEC input/reference为显式source hash，不制造第二份输入；全部finite/固定样本数。
逐帧核能量/选择器/gates/selected字节、AEC代数≤1e-6、范围/计数；keep/shadow primary trace/state.csv全量同。
通知前selected/primary前缀同；无通知臂shadow两trace全0且selected全primary；8零reference场景两坐标原输出必须同且不被本轮激活。
repeat全部8文件逐byte同；future只将case07/used0原mic/ref从通知帧样本起反号，gate/通知不变，前缀trace及两CSV同。
future后半不冒称真实Activity结果，仅有限前缀因果控制，不参与现场选择。

whole及原PTS三个固定窗口（由device_capture contract继承，offset0）统计selected/primary/shadow残差RMS/peak、估计echo RMS/peak；
shadow只有整个窗口均active才评分，否则null；无通知/keep全shadow统计null，无active-only whole。
保留各原场景窗口的精确sample_range及样本数；不增加事件居中声学窗口、不称ERLE或近端误差。
报告shadow-minus-keep残差RMS差、每次输出切换帧/方向、eligible/dt/far帧数、事件相邻样本差与两bank首样本差。
所有变化、无改善或退化保留，不能用能量选择器自证音质。decision=FIELD_SHADOW_DIAGNOSTIC_NO_PROMOTION，promotion/shipping=false。
事件对照为研究外部通知，不重新执行D16 tracker或改其jump/reset验收；当前资源只sizeof/calls，非DUT CPU/peak/热。

## P3 依赖、验收与收口

scope_write=新D26 C/tool/tests/PLAN/RESULT/REVIEW及README本轮入口；既有dirty、D16至D25与产品源不改。
先独立计划/实施审查，严格编译、完整非法参数拒绝并确认预置8文件不变，再66真实执行、非仓cwd help/dryrun及定向测试。
新/tmp根；原输入/库/事件/源起止hash核，baseline不等价立即MEASUREMENT_INVALID停止，不削弱逐byte要求或换库。
每独立编译/runner命令timeout120秒；66组整体编排仅观察live handle，不对总回放另设120秒截断。
独立actual audit不导入新测量器、不重DSP：核所有工件/输入来源/旧依赖、逐帧gate/选择/输出/窗口/差值/事件。
missing/real input×旧D25/新D26/仓根工具负例均拒绝且原工件manifest不变；完整错误参数在任何fopen前拒绝。
retry_budget=2，失败保留并回计划审查；staleness_threshold=任一锁漂移即replan；真实handle heartbeat/attestation起止hash。
claimant=root；verifier=device_capture_independent_review；open_items3；plan_completeness=P1/P2/P3；stop_condition=pass/replan/blocked/abort。
completion_claim仅本轮开发诊断；logical_task_open=true；handoff_target=真人/真实检测与输出边界、后处理及目标资源；retention=仓内reviewing candidate。
无SCM外写、设备写或正式归档；AISpeech产品、ASR/KWS、真实声学/对齐、HIL/E001/owner资格独立未闭合。
