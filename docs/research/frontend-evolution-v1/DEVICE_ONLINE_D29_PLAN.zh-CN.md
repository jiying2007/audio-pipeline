# D29 双AEC、保持期与过渡的在线研究集成合同

日期2026-10-11；experiment=FE_DEVICE_ONLINE_D29；总体native goal=全面推进优化迭代，active。
primary=adk-planning-execution-loop；supporting=adk-verification-before-completion；上一轮分类progress。

## P1 身份、假设与授权边界

kind=bounded research integration；question=实际逐160点产生双AEC输出、计算D27选择并执行D28过渡，能否完整复现离线组合结果且不改变两bank演进。
这是明确的集成缺口，不新增时长/阈值搜索或声学裁判。online指本机逐帧C处理，不是设备、网络服务或真实Activity检测闭环。
local HEAD572b0e34a8a8e5663397ce16e378209ba9058d4d；既有dirty保留。
fresh live main373008e89f2ebaabc298d2c9613420b1d4811c78，summary completed/success；#657 OPEN、updated2026-10-10T11:33:28Z。
PR719/717/714/708/695独立，线上checks/artifacts不批准本地D29，旧issue正文快照不作live-main authority。
Provider context route unresolved/current为空，知识线NEEDS_REVIEW；此前task-type debugging CLI拒绝已更正为debug，不作D29算法失败或归档成功。
D28 result/binding=67b5a3f3a11b27a167e1d4ac7e59211cc7f92f9c865f4f891ae8ee49cd7175ae / d34ca0be4f597297de80a16f78940146b276bdde648a03fc2dbfb5187bea2102。
D28最终v2快照518d0f490e93377b181f659a89768103ef244dc550ac3e05182ea6bf52d249ec；源码/输入/工件均须起止核hash，旧D0-D28不改。
只链接原D18 actual MDF library：eb5b0c784c316e71d6ed9f58db6cb66f190b631daa00c55a94032168d5a47aa4；编译definitions/includes/flags取原flags.make与冻结库。
复用原D27/D28私有头，不改其字节；research_algorithm_changed=false、integration_changed=true、shipping_algorithm_changed=false、promotion/shipping=false。
32设备来源是已查看development，12路径/近端来源为合成工程与oracle标签；独立验证/blind不参与选择。

## P2 一次集成及矩阵

44个原主来源各实际集成一次；case07-used0的新进程repeat/future两次，共46个真实C回放，不能用离线bank复制代替AEC执行。
输入原mic/ref Float32LE及far/dt两byte每帧；field路径来自原D19、notify取原D26，return使用D25原mic/reference、notify1000、far1/dt原标签。
normal四bank输出与原D26/D25全部逐byte同，primary状态CSV与原源全byte同；init160/filter1536/stride2、mu0.22、48partitions、32block不变。
通知时shadow=primary后完整reset，一次且仅一次；没有通知不启shadow；两bank独立演进不受selected输出反馈。
每帧实际残差按原顺序double求能量；调用原D27 choose，0.8比例/3帧确认/50帧保持不变；selector CSV逐byte复现原D27 normal。
随后调用原D28 begin/mix/advance：两输出同alpha、一次推进、320点端点直通；transition CSV及两selected输出逐byte复现D28 normal fade。
不输入旧选择control.bin、不复制旧输出；原gates仍由外部冻结输入，不冒称Activity/DTD、SYNC、NS/RES/AGC/KWS或AISpeech产品链闭环。
输出8条Float32LE：mic/reference/echo/residual/primary_echo/primary_residual/shadow_echo/shadow_residual；state.csv、selector.csv、transition.csv。
gate文件由原来源显式生成并hash绑定；真值near/true_echo只由原D25用于评分，不能输入实际选择。
全部normal逐样本finite、原mic代数<=1e-6；原D26/D25 whole/固定窗/null沿用原score，必须与D28 fade全部精确相同，不增加新声学窗或改分数定义。
重判D28原候选条件并保留其55事件代价、设备窗口/near代价，不能以集成通过升级旧声学资格。

repeat全部8音频和3CSV全量同。future只对case07从原notify1247起实际mic/ref取负，gates不变；通知前11文件前缀同。
future四bank/state.csv全量逐byte复现D26原future，真实D27选择和D28过渡按新bank轨迹独立复算，不能套D28的离线增益future控制。
future可核变换后的实际mic代数；不评分、不参加候选、不能重选参数；其prefix只是本次有限输入因果证据。
primary/shadow/process/reset/selector/transition/sync计数实际回报并按frames/notify核；sync_calls必须0。
资源仅报告真实sizeof双AEC状态、20Bselector、16Btransition、8个160点frame buffers与其合计，含义分别明确。
研究局部state+上述buffers预算128KiB，不能改变B0 50,000B arena；双AEC状态本身66,040B已高于该B0上限，不能标保守SSC305部署候选。
不报告DUT CPU/RSS/完整线程栈/功耗/热；stdio/库/其它局部变量/进程开销不包含在该局部预算中。

## P3 验收、验证与收口

measurement gate=全hash/真实46执行/正常四bank+primary state/selector/transition/selected逐byte同/全部finite/混合与计数/代数/原window/null/重复/future/negative。
任一失败MEASUREMENT_INVALID，保留失败且停止、回计划；不放宽byteeq、预算、窗口、超时或输出要求。
集成准入=上述全通过且局部state+buffers<=128KiB；decision=ONLINE_INTEGRATION_ENGINEERING_PASS_NO_PROMOTION。
即使成功仍promotion_allowed=false/shipping_approved=false；不新增独立音质、真人保护、owner/E001资格。
scope_write=新D29 PLAN/C/tool/tests/RESULT/REVIEW及README入口；依赖旧头/C/库只读。
strict C11/O2/Wall/Wextra/Werror/Wconversion/Wshadow/pedantic/ffp-contract=off；复用原库，禁止重编DSP或隐藏替换library。
完整非法frames/notify/mode/future参数需所有输出sentinel不变、primary/shadow调用0；argc拒绝另列；端点/inactive/atomic-overlap已有原头自测，本轮加集成时序自测。
非仓cwd help/dry-run/正负契约测试；missing/真实input×旧D28/新D29/仓根六工具拒绝，原两根完整manifest起止同，仓仅工具潜在回执路径。
每子命令timeout120；父编排只观察同live handle，不因观察超时重跑；retry_budget2，真实失败记录/原版保留。
资源矩阵：root主run和postcheck串行；独立actual审计只在其终态、工件根冻结后开始；audit与negative不执行C/AEC，无共享根写。
独立verifier不导入新measurement，不执行DSP；可复用锁定D19 stdlib helper，独立核normal/future轨迹和时序、原window/null、数值/计数及候选限制。
claimant=root；verifier=device_capture_independent_review；open_items3；plan_completeness=P1/P2/P3；staleness_threshold=任一冻结依赖漂移即replan。
heartbeat=实际livehandle/Runtime；attestation=起止hash回读；stop_condition=pass/replan/blocked/abort。
本地里程碑按freeze→implement→targeted/self/negative→actual independent audit→whole-change fresh review→REVIEW后复验→Runtime final闭合。
logical_task_open=true；completion_claim仅实际AEC-选择-过渡集成等价，handoff_target=真实近端/Activity检测/完整后处理/目标资源与产品链，retention=本地reviewing candidate。
不commit/push/PR/merge/发布/设备写，不正式归档；原失败与历史I025-I040不改；native总体目标保持active。
