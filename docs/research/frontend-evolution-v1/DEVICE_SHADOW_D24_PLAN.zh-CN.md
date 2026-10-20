# D24 保留旧状态的旁路重置原型：冻结合同

日期2026-10-11；experiment=FE_DEVICE_SHADOW_D24；kind=research prototype；总体目标active。
goal_statement：以双状态研究原型保留D23误reset的旧状态，验证固定因果选择器的真切换响应和误事件代价。
primary=adk-planning-execution-loop；supporting=adk-verification-before-completion；这是研究算法改动，不改产品DSP或默认。

## P1 精确基线、假设与权限

D23 result/binding=34999146de3ef13d1364d289165cc5381c420fb4e4f40a40cc31d0d484803f60 /
e5e7ce39b20a9a077439cb2417dbd0eb26065c0248c09e9c011821d88167859a，D22保持状态基线及完整旧依赖/119输入锁起止核。
仍用D18真实MDF库eb5b0c784c316e71d6ed9f58db6cb66f190b631daa00c55a94032168d5a47aa4及宏/头。
直接include冻结D22 C fixture：16k/160点、20秒、A/B/switch、ref16/20、mu0.22f/taps1536/stride2、原信号/顺序float32/固定门控不变。
假设：保留原状态和可逆输出选择能避免直接full reset丢弃唯一已收敛路径；未证明人声保护、听感、检测可靠性或设备资源。
授权范围仅新研究wrapper/selector/tool/tests/docs及README；work_item_kind=prototype，implementation_permission=用户授权FE研究。
prototype_evidence=双状态真实原库执行、源等价/状态/选择器逐帧/固定统计/实际sizeof及处理调用计数；shipping_algorithm_changed=false。

## P2 因果原型与固定测量

keep只运行primary。shadow在frame1000处理前复制primary的配置/状态到第二状态，调用原full reset一次，只影响第二状态。
primary持续原过程；shadow从1000帧起每帧接收同一mic/reference/参数/门控；两状态一直保留，primary从不reset。
初始selected_bank=0(primary)、streak=0；每帧先处理两个可用状态，再以当前帧double顺序累计residual平方和比较。
只有shadow已激活且enabled/far/!dt成立，当前选中能量>1e-20，另一状态能量严格<0.8×当前选中能量，才streak++；否则streak=0。
达到3个连续满足帧时翻转selected_bank，并streak清0；双向规则相同，选择在本帧输出前生效。
0.8/3是本轮预评分冻结开发启发式，不搜索、不优化，不是声学晋升阈值。当前API已收160点帧，未读取未来帧。
本原型直接选一状态echo/residual，无crossfade；切换边界听感/人声和性能未资格化，不隐藏该边界。
额外保存primary_echo/residual、shadow_echo/residual四trace；shadow激活前全0且selector CSV显式active0，不能当有效残差。
原四trace为mic/reference/selected echo/residual，原state.csv仅primary真实状态；selector.csv保存frame/active/bank/streak/change/两能量。
摘要记录primary_calls2000、shadow_calls0或1000、shadow_reset_calls0或1、switch_count、真实sizeof(ap_aec_state_t)。
资源只报告新增shadow状态字节及处理次数；非全进程峰值、非CPU基准、非目标板RAM/周期预算。

17次=12主臂A/B/switch×ref16/20×keep/shadow；3negative A/ref16/shadow(disabled/hold/zero)；repeat/future均switch/ref20/shadow。
六keep的原四trace/CSV对D22逐byte同；六shadow的mic/ref/primary echo/residual/primary CSV对D22全量同。
shadow激活后echo/residual对D23同臂reset后半逐byte同，证明两个真实状态而非合成原库结果；激活前四旁路trace按标签解释。
17例8trace全量finite/长度正确；primary及selected满足mic≈echo+residual≤1e-6；shadow关系仅active区间验；selector逐帧独立重算。
shadow主臂对keep事件前selected四trace/primary CSV同；repeat全10文件逐byte同、future前半trace/CSV同。
三negative selected echo零/residual等mic、旁路echo零及primary权重零；不以事件数零替代这些输出检查。
冻结D23 whole及六窗RMS/peak/纯回声工程ERLE；报告每shape/ref shadow-minus-keep whole/六窗差，选择次数和首帧均保留。
只有工程合同/等价/finite/因果门禁；效果无改善、误事件损失或频繁翻转均原样保留，不调整比率/确认/窗口洗绿。
data_role=synthetic-engineering；decision=PROTECTED_SHADOW_PROTOTYPE_NO_PROMOTION；promotion/shipping=false。

## P3 验证与收口

required_evidence=计划/实现独立审查、严格C11/-ffp-contract=off编译、17真实执行binding、非仓cwd help/dry-run、selector已知答案/negative、独立全量audit/拒绝/whole-change。
新/tmp输出；retry_budget=2；命令timeout120；staleness_threshold=任一锁漂移即replan；heartbeat真实handle；attestation_readback=起止hash。
claimant=root；verifier=device_capture_independent_review；open_items=3；plan_completeness=P1/P2/P3；stop_condition=pass/replan/blocked/abort。
completion_claim仅D24工程原型；logical_task_open=true；milestone_close仅D24；handoff_target=人声/切换边界/资源和真实开发对照；retention=仓内reviewing candidate。
本轮live main 1be9b89af778783bdbe695c72d048b3d77eee948，#657 OPEN；本地未提交原型不由main CI批准。
无SCM外写/设备写。Provider route unresolved保持NEEDS_REVIEW；历史拒绝、AISpeech、真人/ASR/KWS/目标资源/HIL/E001/owner资格仍独立。
