# D32 因果近端保护反馈候选合同

日期2026-10-11；experiment=FE_DEVICE_CAUSAL_GUARD_D32；上一轮progress；总体native优化目标active。
primary=adk-planning-execution-loop；claimant=root；verifier=device_capture_independent_review。

## P1 身份、因果改动与数据角色

kind=bounded first-party research algorithm candidate；implementation_permission=独立研究C/header/tool/tests及中文记录，不改产品算法/default/API。
local HEAD572b0e34a8a8e5663397ce16e378209ba9058d4d；原D0-D31专属源/库/工件和用户dirty保留，README只追加新入口。
fresh live main=d3f89e54beed483fcc0f8ce59e74b28533ed19b5，当前66checks中64completed/2in_progress且summary未见，不声明main全绿。
#657 OPEN updated2026-10-10T11:33:28Z；独立远端PR717/714/708/695不批准本地实验。
Provider task-type=debug返回route unresolved/current为空，知识线NEEDS_REVIEW；仓内reviewing candidate，不正式归档。
D30 result/binding=e0b74142093d4579615be9ffe047335b4618f46aa1116f0b24941bb921de470d / 2558d74e0e8377087bcb1a44fc3e13d890c4da9b641b579db9d670e207083956。
D31接受根=/tmp/audio-fe-device-observability-d31-attempt1-20261011；result/binding=d1465d24fb2b26d378dd2e6590c661f2a67d5e23ca1255ab7f6bd5970961aee2 / 04990be63adfb174d37f6483fa6e1d3e0679276ee6581577eba59baf30cdc506。
只链接原D18库SHA eb5b0c784c316e71d6ed9f58db6cb66f190b631daa00c55a94032168d5a47aa4，不重编/修改DSP库。
question=加入上一帧primary输出的因果多特征保护，是否改善能量门控遗漏near，同时保持纯路径切换恢复？
唯一算法改动=原Activity的dt与独立causal guard取OR作为两AEC和选择器本帧dt；原Activity参数、AEC参数、路径通知/双状态/保持/过渡全部冻结。
仅反馈上一帧primary echo/residual，不用selected/shadow/当前帧处理后结果作本帧控制。无标签输入、无前视，不调用不存在的AEC preview接口。
32field已查看development、12return合成（4echo、4dt、4unguarded），D31已披露数据用于开发假设；不是独立validation或blind。
阈值为D31之后的开发候选设计，明确adaptive reuse；本轮只一个冻结候选，不扫描/重调阈值、时长或裁判。

## P2 候选状态及实际处理顺序

double顺序累加当前primary输出的mic/echo/residual平方与mic-echo、residual-echo交叉积；沿用D31零时延非去均值C公式。
Cme=C(mic,primary_echo)、Cre=C(primary_residual,primary_echo)、Q=primary_residual能量/mic能量。
me/re分母零分别标valid_me/valid_re=0，数值CSV用-1哨兵表示未定义，不当低相关；Q分母mic零用-1。
观察发生于本帧primary/shadow处理后、选择/输出完成后；状态只供下一帧读取。
稳定计数：far且原detected_dt=0、valid_me、Cme>0.95、0<=Q<0.05时计数累加上限100，否则归零；达到100后armed=1。
armed只是历史收敛迹象，不是路径真值/声学可信认证。它保持至far=0，路径通知不重置guard/Activity；不新增通知豁免或临时采样窗。
本帧先实际原Activity；far=0清guard状态并输出guard0；far=1时，读取上一帧状态。
onset=armed && valid_me && valid_re && 0.2<Cme<0.9 && Cre<0.1 && Q>0.2；onset时hold=3，否则已有hold减1；guard=hold>0。
used_dt=detected_dt OR guard（feedback模式），monitor模式仅使用detected_dt。两模式每帧都执行同一个observer和guard状态机，monitor不会影响原DSP。
原activity.csv始终记录原detected_dt，必须在所有执行中逐byte复现D30；selector/transition实际dt记录used_dt。
新增guard.csv记录frame/mode/detected_dt/guard/used_dt、gate前armed/stable、gate后hold、当前观察三特征/valid flags和观察后armed/stable。
不改原Float32 Activity运算或参数；guard观察是double研究实现，不声明部署数值/性能资格。

## P3 执行、测量与接受条件

46源（44normal+repeat/future）×monitor/feedback两模式=92次真实C回放，252972帧；不把observer-only或工具拒绝算DSP执行。
monitor原12输出全部逐byte复现D30；feedback原mic/ref/activity.csv必须同D30，原score/窗口/null由既有D26/D25权威函数计算。
每模式repeat全部13输出byteeq、future通知1247帧前全部13输出前缀byteeq；future不评分/选型。
独立核实际Activity、guard三特征/递推、selector/mix、actual counts、finite与mic代数<=1e-6；不以主退出0替代独立验证。
return near真值只在事后从原near.f32le非零帧重建，不用旧dt标签冒充：dt与unguarded共8来源均有[1000,1200)、[1600,1800)近端，echo共4来源无near。
工程接受条件同时满足：8near来源的每个200帧区间used_dt至少180帧；静态A每段near onset首次used_dt延迟<=2帧；4纯echo来源[800,2000)guard帧数0。
每个return原whole/windows的selected known-near error相对D30增加<=0.5dB（包括near absent）；field各主例switch_count不超过D30。
这些仅冻结开发工程准入，不是新声学评分。任一失败decision=CAUSAL_GUARD_DEVELOPMENT_REJECTED；全满足仅CAUSAL_GUARD_DEVELOPMENT_CANDIDATE_ONLY。
promotion_allowed=false、shipping_approved=false在两种结果均保持；保留每例失败，不调宽门槛或掩盖局部退化。
资源计数=原71224B加实际sizeof guard state，局部预算128KiB；B0 50000B不改，两AEC超限继续保持。
未包含完整栈/stdio/库/总进程资源；Host不等于SSC305 CPU/RSS/热/功耗/声学/HIL/PQ。

## P4 验证与收口

scope_write=新D32 PLAN/header/C/tool/tests/RESULT/REVIEW、README；源工具及基线D30/D31只读。
输出根=/tmp/audio-fe-device-causal-guard-d32-20261011；拒绝已有输出、旧输入根/仓根，不覆盖。
strict C11/O2/Wall/Wextra/Werror/Wconversion/Wshadow/pedantic/ffp-contract=off，原D18 flags/includes/lib锁定。
自测覆盖100帧arming、下一帧onset、hold消退、far0 reset、零分母不触发、原Activity/组合；Python定向参考同一状态合同，不拟合检测器。
argc/非法frames/notify/future/mode/feedback参数在打开输入/输出前拒绝，13sentinel保持、AEC/Activity/observer调用0。
非仓help/dry-run/tests；旧D30根/仓根/已有输出三个工具负例均exit2且对应完整manifest保持。
retry_budget2；子命令timeout120；父编排观察同一live handle，不因观察超时重启；依赖字节漂移即replan。
资源矩阵=主92回放/检查串行，主根终态冻结后独立stdlib audit/negative，root不并发写被审计根。
计划审查→实施fresh PASS后才执行→独立全量重算/负例→whole-change→REVIEW后复验→本地Runtime final；原D31顺序偏差不重演。
verifier不import新候选工具、无需重跑DSP，可复用已冻结的标准库评分辅助定义但必须记录其身份与零顶层副作用。
open_items3；plan_completeness=P1/P2/P3/P4；attestation=起止绑定；heartbeat=真实handle/Runtime；stop_condition=pass/replan/blocked/abort。
logical_task_open=true；milestone_close仅候选工程结论；handoff_target=保留有效/拒绝结果后冻结下一因果假设及完整后处理/真人/目标资源。
rollback=停用feedback入口，monitor须复制原D30；无产品API/default变化，无commit/push/PR/merge/发布/设备写，总体native active。
