# D30 实际Activity与双状态AEC集成合同

日期2026-10-11；experiment=FE_DEVICE_ACTIVITY_D30；总体目标全面推进优化迭代，native active。
primary=adk-planning-execution-loop；supporting=adk-verification-before-completion；上一轮分类progress。

## P1 身份、假设与因果边界

kind=bounded research integration；question=逐帧执行原Activity，以实际输入能量产生far/dt，再驱动已验证双状态AEC/保持选择/过渡，设备原轨迹是否复现，合成oracle门控依赖在哪里。
local HEAD572b0e34a8a8e5663397ce16e378209ba9058d4d；用户dirty及原D0-D29源/工件保留。
fresh live main373008e89f2ebaabc298d2c9613420b1d4811c78，76checks=75success/1skip，summarysuccess；#657 OPEN updated2026-10-10T11:33:28Z。
开放PR719/717/714/708/695及其独立工件不批准本地D30。Provider route unresolved/current为空，知识线NEEDS_REVIEW，不正式归档。
D29 result/binding SHA256=9ed85b81ee3487919b00cf441e84757c1fc7c72deb611cfdedf8c1944e0fa4ab / 2120e2e139584972311fa2ac9a47b5984acf1159fb21d8234438846e49078520。
D29完整快照68f6168c8e6a7cc719947fcd3960d7fa682a70042c97bb34e2b5cfa18f81807e及REVIEW53ec862af524d08ec6ec6493db325116e284d68c77f6a3888804678a26f1936c用于连续性；本轮不强锁后续允许更新的README历史字节。
只链接原D18 actual MDF/Activity库eb5b0c784c316e71d6ed9f58db6cb66f190b631daa00c55a94032168d5a47aa4，读取其实际source/flags；不重编或修改原库。
唯一集成改变是以原Activity实际调用替代外部gate作为处理控制；research_algorithm_changed=false、integration_changed=true、shipping_algorithm_changed=false。
原Activity阈值1e-7f/ratio1.5f/hold3；能量按原pipeline float顺序以1e-12f初始化、累加160点平方、除160；先Activity再AEC。
原实现无AEC输出反馈，不能构造不存在的selected残差反馈实验；shadow通知不等于公共pipeline路径重置，本轮不reset Activity。
双状态指单路AEC-input/ref上的primary/shadow，不是双麦逐路AEC；上游BF/SYNC和下游NS/RES/AGC/VAD/KWS未新执行。
32设备已查看development、12合成/oracle工程；独立validation/blind不参与选择；无阈值搜索或新声学裁判。

## P2 冻结执行矩阵与测量

沿用D29的44主来源及case07-used0新进程repeat/future，共46次真实C回放。
actual Activity每帧恰一次；外部gates不输入实际C处理，只用于回放后差异对照；near/true_echo仅用于原评分，不能输入实际Activity/AEC/selector。
输入原mic/ref，通知及future从1247帧mic/ref同时取负沿用D29；不新增前视或标签。
原MDF160/1536/stride2、mu.22、48partitions/block32；通知复制primary然后完整reset一次shadow；D27 0.8/3确认/50帧保持；D28 320点/共alpha不变。
8条Float32及原state/selector/transition CSV保持原字段，另新增activity.csv，记录frame、mic/ref float能量、EMA、hangovers及实际far/dt。
32field主来源及repeat/future的原11输出必须逐byte复现D29；实际far/dt逐帧等于原D19/D26门控。
12return不要求等于oracle控制下的D29；记录逐帧far/dt disagreement、输出/事件差异、原whole/固定窗/null及known-near误差变化。
这仅诊断原oracle gate依赖，不能称真实检测准确率/语音保护或以更低能量宣布效果。
新selector/transition按实际bank能量及门控独立递推；所有音频finite、原mic代数<=1e-6、端点及过渡外精确核验。
normal44+repeat评分复用原D26/D25窗口与函数，不新裁判；future不评分/候选，只核实际输入/递推/因果前缀/代数。
repeat全部12输出全量同；future通知前12输出前缀同，实际Activity整轨迹与normal同（输入平方不受符号变换影响）。
报告逐例实际AEC/Activity/selector/transition/reset/sync计数；sync0；本轮没有候选选择或promotion条件。
局部资源原71196B加实际sizeof(Activity)=28B，预计71224B，需真实sizeof核；局部预算128KiB，B0 50000B不改，两AEC状态超限保持。
不包含其它局部变量、stdio、库、完整线程栈/进程总资源，不报告DUT CPU/RSS/热/功耗。

## P3 验收与收口

measurement gate=起止hash/46真实执行/设备原轨迹byteeq/实际Activity独立Float32递推/selector+mix/finite+代数/原窗+null/重复与future/拒绝保护/资源计数。
任一合同失败MEASUREMENT_INVALID，保留失败，回计划；不放宽字节、阈值、窗口、预算或超时。
测量有效的固定decision=ACTIVITY_INTEGRATION_DIAGNOSTIC_NO_PROMOTION；return差异不作为测量失败，也不作为晋升门槛。
promotion_allowed=false/shipping_approved=false，无新声学准入或默认修改。
scope_write=新D30 PLAN/C/tool/tests/RESULT/REVIEW及README入口；原D29 C/tool等只读。
strict C11/O2/Wall/Wextra/Werror/Wconversion/Wshadow/pedantic/ffp-contract=off，原库不重编。
非仓help/dry-run/输入契约测试；实际Activity低/高能量与hangover确定性自测；非法frames/notify/mode/future需所有输出sentinel保持及AEC/Activity调用0，argc拒绝另列。
missing/真实input×旧D29/新D30/仓根六工具负例均拒绝；两根完整manifest起止同，仓仅潜在回执路径。
子命令timeout120，父编排仅观察同live handle，不因观察超时重启；retry_budget2。
资源矩阵=root主run和postcheck串行，终态后冻结根，独立audit/negative不执行C/AEC/Activity，与root主根写互斥。
独立verifier使用stdlib，复核原库身份及actual Activity Float32能量/EMA/hangover/flags、设备byteeq、return原评分/null及差值、控制与混合、actual calls/资源及负例。
claimant=root；verifier=device_capture_independent_review；open_items3；plan_completeness=P1/P2/P3；staleness_threshold=冻结依赖漂移即replan；heartbeat=实际handle/Runtime；attestation=起止hash回读。
stop_condition=pass/replan/blocked/abort；logical_task_open=true；completion_claim仅实际Activity-AEC-选择-过渡集成及oracle依赖诊断。
执行前计划/实施独立审查→实际回放/定向检查→独立audit/negative→whole-change review→REVIEW后复验→本地Runtime收口；总体native active。
handoff_target=完整前后处理/真人独立检测资格/目标资源；retention=仓内reviewing candidate；不commit/push/PR/merge/发布/设备写。
