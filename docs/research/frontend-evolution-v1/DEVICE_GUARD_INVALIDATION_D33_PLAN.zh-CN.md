# D33 路径通知时保护历史失效的因果消融

日期2026-10-11；experiment=FE_DEVICE_GUARD_INVALIDATION_D33；总体native优化目标active。
primary=adk-planning-execution-loop；claimant=root；verifier=device_capture_independent_review。
上一轮D32为progress：主测量/独立审计/whole-change/Runtime本地闭合，候选REJECTED，不把局部里程碑当总体完成。

## P1 身份、问题、角色与授权

local HEAD=572b0e34a8a8e5663397ce16e378209ba9058d4d；用户旧dirty、D0-D32专属源码/工件不改；README仅追加入口。
fresh live main=d3f89e54beed483fcc0f8ce59e74b28533ed19b5，77checks全部completed，76success/1skipped，summary/release成功；这些CI不批准本地新候选。
#657 OPEN updated2026-10-10T11:33:28Z；live PR721/717/714/708/695独立，不借其结果批准本地实验。
最新三个远端artifact来源head f495801f... / b797e470... / de235a77...，nonexpired，不当本地DUT证据。
Provider debug route unresolved/current为空，知识线NEEDS_REVIEW；本地reviewing candidate，不正式归档。
kind=bounded first-party research algorithm ablation；implementation_permission=新D33 C/header/tool/tests/PLAN/RESULT/REVIEW、README入口，产品default/API与原算法库不改。
question=实际路径通知时使历史保护状态失效，是否消除D32路径失配误保护/恢复冻结，并保留静态与切换期间近端保护？
D32纯echo ABA在唯一通知1000之后1087首次guard、连续最长803/814帧，窗口error最高+33.136973dB；1200路径返回并无第二次通知。
这是历史armed与反馈耦合的机制假设，D32时序相关性尚未证明根因，本轮消融不能预判收益。
D32 baseline根=/tmp/audio-fe-device-causal-guard-d32-20261011；result/binding SHA256=a9e8d6f1120c420361d10daae103f207679638439da4ff65d01fa621af8b477a / d6a49352c331734bd4015b2c2e56ba3fa0a1f4c36a957b968566ae0d03ce80fe。
D32独立audit及v2review快照保留；原D30评分基线/原D31观测与D18库依赖仍完整核验，不重新解释历史结果。
原D18 lib SHA256=eb5b0c784c316e71d6ed9f58db6cb66f190b631daa00c55a94032168d5a47aa4，只链接、不重编。
数据=32已查看设备development+12合成return，adaptive reuse明确；不能当validation/blind或真人双讲资格。
不引入第三方源/模型/新数据，不选阈值或窗口，不修改权威评分器。

## P2 唯一因果改动与生命周期

monitor完整沿用D32，不清保护历史。
feedback仅在实际has_notify && frame==notify时，在本帧Activity/guard gate之前将全部40B guard状态清零。
清零对象=三double特征、两个valid、stable、armed、hold；不保留旧特征供当前gate。无通知帧行为与D32一致。
guard.csv原15字段不改；armed_before/stable_before定义为本帧任何通知失效操作之后、gate之前的实际状态。
原Activity不reset，不改变其Float32递推、参数或CSV；原shadow copy/reset只在同一唯一notify执行，primary不reset；selector/transition不额外reset。
本帧原Activity→通知后guard gate→primary/shadow→原选择/过渡→currentprimary observer供下一帧。
通知clear可在Activity之前完成，因为两者状态独立；不读取当前处理后输出、selected/shadow或near标签生成控制。
其余完全冻结D32：100帧稳定armed、原阈值与3帧hold、far0清零、零分母-1/valid0、guard OR原dt。
重新armed仍要求100个连续原stable帧；不会基于通知时间、near truth或回A真值临时豁免/加速。
因此预期可能丢失切换后的首段near；必须测量并保留，不为让消融通过而改准入。
ABA返回1200没有新通知，不在此帧强行清零；不能把已知合成路径truth变为额外通知。
40B状态、原71,264B局部状态/缓冲保持；研究局部预算128KiB，B0 50,000B不变、双AEC超B0保持。
同单路输入两套AEC研究状态，不是双麦逐路处理；不认证总RSS/栈、SSC305性能/热/功耗。

## P3 实际执行、比较与验收

44主源加case07-used0 repeat/future，每模式46次，共92真实C/252972帧；不把自测或拒绝当矩阵执行。
monitor全部13输出byteeqD32 monitor；其原12同时byteeqD30；feedback mic/ref/activity.csv仍byteeqD30。
feedback无notify来源全部13byteeqD32 feedback；有notify来源13文件在通知之前全前缀byteeqD32 feedback。
两模式repeat13全量byteeq，future1247帧之前13前缀byteeq，future不评分/选型。
实际observer/gate/原Activity/selector/transition/资源/代数/finite与原window/null按冻结工具核验；原whole/windows由既有D26/D25评分函数计算。
near真值事后从near.f32le非零帧重建，dt/unguarded均为near来源；8near/4echo/32field角色不变。
候选五项准入完全沿用D32/D30对照：每个near200帧区间used_dt>=180；静态A onset<=2帧；四纯echo[800,2000)guard0；12return原whole/windows selected error对D30增加<=0.5dB；32field各switch_count<=D30。
任一失败decision=GUARD_INVALIDATION_DEVELOPMENT_REJECTED；全通过仅GUARD_INVALIDATION_DEVELOPMENT_CANDIDATE_ONLY；两结果promotion_allowed/shipping_approved=false。
同时报告D32→D33原窗口selected error差、pureecho误保护变化及near覆盖变化，作为本轮因果消融证据，不用这些改原准入。
负结果和不同source tradeoff分别保留；消融消除误保护也不能证明通知可靠、完整near检测或产品保护已合格。

## P4 验证、审查、停止与接力

PLAN先独立审查，再实现/严格预编译/定向测试；实施fresh PASS后才启动主矩阵。
strict C11/O2/Wall/Wextra/Werror/Wconversion/Wshadow/pedantic/ffp-contract=off；C self-test含monitor不清、feedback清全部状态/消除旧hold与100帧重新armed。
Python针对失效/重arming与完整observe路径测试；fixture解析证据不是DSP/声学。
非仓cwd help/dry-run/tests；--root明确为repo/tests/audio，--output=/tmp/audio-fe-device-guard-invalidation-d33-20261011。
拒绝旧D32根/仓根/已有根，完整manifest比较保持；argc/非法frames/notify/future/mode/feedback在打开输入/输出之前拒绝，13sentinel保持、DSP/Activity/observer调用0。
父wrapper不设置整体执行超时，子命令timeout120；retry_budget2，观察超时只poll同一live handle，不重启。源/输入/库漂移即replan。
资源矩阵=主矩阵/负例串行，共用主根终态冻结后stdlib-only audit；root不写其封存artifact/source。
verifier不import新tool/helper、不重跑DSP，独立逐帧失效/guard/Activity/selector/transition/原窗口重算及准入；repeat/future/equivalence/依赖起止全核。
whole-change fresh→REVIEW后复验→本地Runtime final；owner/声学/设备/Provider资格分别披露。
open_items3；plan_completeness=P1/P2/P3/P4；heartbeat=实际handle/Runtime；attestation=起止source/input锁；stop_condition=pass/replan/blocked/abort。
logical_task_open=true；milestone_close仅消融/候选工程证据，native总体active。无commit/push/PR/merge/发布/设备写。
rollback=停用D33 feedback，原D32/D30库和工件保留；handoff_target=结合误保护、恢复和near缺口决定下一单一因果假设，不能泛化为真人/产品合格。
