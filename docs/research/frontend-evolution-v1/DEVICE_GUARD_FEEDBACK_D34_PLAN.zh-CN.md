# D34 保护反馈隔离诊断冻结计划

日期2026-10-11；experiment=FE_DEVICE_GUARD_FEEDBACK_D34；primary=adk-planning-execution-loop。
goal_statement=全面推进优化迭代；本里程碑只判断反馈耦合机制，不批准候选；claimant=root；verifier=device_capture_independent_review。
上一轮D33完成真实执行、独立审计及收口，属于progress；总体native目标保持active。

## P1 授权、精确基线与问题

kind=first-party frozen-trace diagnostic；implementation_permission=新D34工具、测试、PLAN/RESULT/REVIEW和README追加入口。
local HEAD=572b0e34a8a8e5663397ce16e378209ba9058d4d；旧dirty、D0-D33源码及封存工件不改。
fresh live main=d3f89e54beed483fcc0f8ce59e74b28533ed19b5；77checks完成、76success/1skipped，summary/release/convergence成功。
#657仍OPEN，updated2026-10-10T11:33:28Z；PR721/717/714/708/695仍独立open，最新三个nonexpired远端artifact为11693386608/11693380927/11693361221，同head b797e4706eba9f6fe088c2e1e6853f447224be4f；不能批准本地D34。
Provider debug route unresolved/current为空，知识线NEEDS_REVIEW，仓内reviewing candidate；无正式归档。
question=相同输入、原阈值下，未施加保护的D32 monitor是否也持续产生纯echo误保护？实际feedback与monitor首次分歧和持续差异是否支持反馈自维持，而非仅由初始误触发解释？
hypothesis=保护反馈阻止primary适配，使依赖primary残差的保护证据持续；monitor的潜在保护若自行消退，支持隔离观测AEC作为下一结构实验，反之此改动不足。不是预判结论。
固定三臂=D32 monitor、D32 feedback、D33 feedback；每臂46例126486帧，共138个case-arm/379458状态帧，不执行DSP。
D30 result/binding=e0b74142093d4579615be9ffe047335b4618f46aa1116f0b24941bb921de470d / 2558d74e0e8377087bcb1a44fc3e13d890c4da9b641b579db9d670e207083956。
D32 result/binding=a9e8d6f1120c420361d10daae103f207679638439da4ff65d01fa621af8b477a / d6a49352c331734bd4015b2c2e56ba3fa0a1f4c36a957b968566ae0d03ce80fe。
D33 result/binding=09cc3b8156436c033adf353d03a9db5079a660c14ab89a574b8238f84596af72 / fe9d21710ed6a2ca35ed9b7b7eba8579ea64d46d57ed8cf4012cda4d3cb0cf79。
D33当前REVIEW=edb6bd437e5c850f7f61824da2a91231e94704d9d5bb2a6170270ca11d3c9536；旧研究结果拒绝状态不改。
data_role=已查看设备development与合成工程对照，adaptive reuse披露；32field+12return+repeat/future。field无near真值，不制造标签；return的near真值仅事后读取原near文件。

## P2 测量合同与禁止推论

不改算法、参数、阈值、通知或裁判；不新增AEC或重新运行C/DSP，不重算声学评分。
先验证D30/D32/D33 result/binding精确hash及各source_files/input_files/artifacts全部当前字节，再核三臂case集合/frames/输入/通知/Activity相同。
从封存guard.csv读15字段；保留gate用上一帧特征、日志cme/cre/ratio为本帧observer之后值的时间语义。
逐帧核D32原gate/100stable/3hold递推与D33真实notify清零；far与detected_dt来自封存Activity，通知来源来自精确case合同。
monitor的actual_used_dt仅detected_dt；另记录potential_dt=detected_dt OR guard，明确它从未在monitor执行中施加保护。
两feedback的potential_dt与实际used_dt一致；不把monitor潜在触发次数当隔离观测AEC的实际输出或near保护效果。
逐臂输出guard、actual_used_dt、potential_dt完整连续区间/计数，三臂状态字段逐项分歧计数/首次帧/完整连续区间。
near原[1000,1200)/[1600,1800)两个区间分别报告actual与potential覆盖、首次触发延迟；全部return额外报告[800,2000)触发，不将有near来源此段计数称false guard。
纯echo四来源此段可报告误保护；所有原测量whole/windows按原sample_range内完整160点帧计数，保留边界丢弃样本，无新窗口选优。
future只核通知1247前前缀与因果控制，不汇总未来段、不评分、不选型；repeat全量等normal。
同输入前提下比较反馈状态分歧，不能直接认定保护自维持唯一根因，也不认定第三AEC可满足五项原准入。
decision固定GUARD_FEEDBACK_DIAGNOSTIC_NO_PROMOTION；promotion_allowed/shipping_approved=false；不产生新候选接受条件。

## P3 实现、验证与独立复核

PLAN先独立审查，再实现；实施fresh PASS后执行诊断。
新Python工具进入tools.codex_assets；从非仓cwd核help/dry-run/定向测试，输出仅fresh direct /tmp/audio-fe-device-guard-feedback-d34-20261011。
测试覆盖actual/potential分离、连续区间/null延迟、D33通知清零、原递推/错误日志拒绝、未来前缀、不合法输出/非有限/重复JSON拒绝；不以fixture代替实际状态诊断。
非法输出在写前拒绝，旧D32/D33/仓根/已有输出根分别负例并完整manifest比对；所有新产物写前不存在。
输入/source锁起止一致、精确138case-arm/379458frame、完整日志、repeat与未来前缀为测量有效性门禁；失败保留，不改要求追绿。
verifier以独立stdlib脚本直接读封存三臂状态和near波形，独立复算全部计数/连续区间/分歧/原窗与case角色，不能import新工具或重跑DSP。
whole-change审查后新增REVIEW、定向docs/git diff复验，再本地Runtime final；各层声明独立。

## P4 执行与接力边界

retry_budget2；staleness_threshold=真实进程handle120s观察无输出后poll同handle，不重启；主诊断、输出负例、独立audit顺序执行。
CPU/内存只为Host离线逐case日志解析，不替代SSC305资源；预算保持原研究128KiB/B0 50000B，本轮无部署状态新增。
open_items3；plan_completeness=P1/P2/P3/P4；heartbeat=实际handle/Runtime；attestation_readback=锁与实际回执回读。
logical_task_open=true；milestone_close仅诊断证据；session_handoff_required=跨阶段以PLAN/RESULT/REVIEW与实际回执接力。
stop_condition=pass/replan/blocked/abort；输入漂移、复核不一致或无新信息必须replan，不反复扩大同类参数扫描。
rollback_path=停用新诊断工具，旧算法与工件完整保留；handoff_target=依据未反馈观测是否消退/near潜在覆盖，冻结下一结构实验或放弃该机制。
required_evidence=独立计划/实施/数值/whole-change审查、主执行终态/负例/文档复验/锁；completion_claim尚未成立。
第三方权利、真人near/KWS、产品default/API、目标HIL/E001/PQ及owner资格分别未闭合；无commit/push/PR/merge/发布/设备写。
