# D36 前帧延迟预测相关性冻结计划

日期2026-10-11；experiment=FE_DEVICE_HELD_LAG_D36；primary=adk-planning-execution-loop。
goal_statement=全面推进优化迭代；claimant=root；verifier=device_capture_independent_review；总体native目标active。
上一轮D35为progress：全量历史参考诊断闭合，零延迟遗漏回声信息，但ABA首near与echo重叠；本轮只检验时间预测信息，不批准保护算法。

## P1 来源、授权与假设

kind=bounded first-party causal feature diagnostic；implementation_permission=新Python工具/tests/PLAN/RESULT/REVIEW及README入口；无产品default/API/设备写。
local HEAD=572b0e34a8a8e5663397ce16e378209ba9058d4d，保留旧dirty、D0-D35专属源码和证据。
fresh live main=d3f89e54beed483fcc0f8ce59e74b28533ed19b5，77checks完成、summary/release/convergence成功；PR721/717/714/708/695仍独立open，#657 OPEN updated2026-10-10T11:33:28Z。
最新三nonexpired artifacts=11693875016/11693720104/11693561872，head f495801f1d5782d8ace8b67abb0f18ec2b53cd36；不借远端证据批准本地实验。
Provider route unresolved/current为空，知识线NEEDS_REVIEW，无正式归档。初次远端查询误用仓属返回404，按实际git remote核实jiying2007/audio-pipeline后查询成功；不据404推断远端不可用。
D35 result/binding SHA256=a18f8b4e678410a043dcbb4b5e2d8ebb68df70156f52ec6f18fad02d09cf58dc / a913b140255a0a84b75e3604517536d0644c4895093d071f359fe25b5b76a6ca；D35 REVIEW=3d4e172f2d9b5531f54a415a26d982c05cda3358d3d51f8c48ecea3b93b54e23。
开始/结束核D35全部source/input/artifact、两独立audit及REVIEW精确字节；消费原D30 reference/primary_residual、D35逐帧chosen lag、D32原monitor guard，均须已锁。
question=前帧峰值延迟在下一帧是否仍可解释残差，还是D35短帧最大值主要来自本帧重新搜索？
hypothesis=纯echo具有可延续延迟，非相干near的本帧最大值不易跨帧复现；混合near/echo、多个反射及路径切换仍可能重叠。失败/无增量必须保留并replan，不无限生成相近诊断。
数据固定原46例126486帧，32field/12return/repeat/future；已查看development与合成engineering、adaptive reuse，不新增独立validation/blind或真人声学资格。

## P2 唯一变化与测量合同

每帧f只取D35帧f-1的chosen_lag；帧0无前帧，previous valid_lags==0则无延迟；无保持旧有效值、oracle或当前帧重新选lag。
窗口仍固定当前160samples；lag范围仍0..1535。可用前帧lag天然不超过当前帧起点，完整历史索引逐帧核；不补零、不扣均值、重采样或取未来样本。
Python Float32解码后用double正向顺序累加 rr=sum(residual²)、xx=sum(reference[t-lag]²)、rx=sum(residual*reference[t-lag])，held_cos2=rx²/(rr*xx)。本轮不运行AEC/DSP或D35全lag搜索。
rr/xx为0无效；原因固定0有效、1帧0、2前帧无效、3当前残差零、4当前该lag参考零，先检查前帧存在、再rr、再xx。
CSV固定frame,past_lag,held_valid,reason,residual_energy,reference_energy,held_cos2,current_max_cos2,max_minus_held,lag_changed。
无前帧/前帧无效past_lag=-1、reference_energy=-1；仍报告当前rr；有过去lag则报告真实xx。无效held_cos2/max_minus_held/lag_changed=-1，held_valid=0，不用0冒充相关性。
current_max_cos2直接读取D35当前帧；held有效时current最大也须有效，max_minus_held=current_max-held，允许仅1e-12数值误差内负值，不clamp；lag_changed为past_lag!=D35当前chosen_lag的0/1，仅held有效时可比。
输出特征在当前帧结束可用，若未来控制最早下一帧；前帧lag来自封存未保护D30状态，没有模拟它已在反馈候选中可用。
完整46例逐帧输出；非future只原240 whole/window向内完整160点帧，保留边界丢弃；固定nearest-rank p10/p50/p90，null不进入valid集合。
分别统计held_cos2、原current_max、max_minus_held、past_lag、lag可比/变化计数及五种reason计数。原D32 guard触发f仅事后选新特征f-1，首帧guard必须0，不回填当前控制。
return near只从原near Float32非零帧事后重建[1000,1200)/[1600,1800)，mixed来源其余帧只称no-near，不当独立pureecho。
field无near标签，零参考不可辨识单列；repeat全量exact，future只核notify1247之前前缀，不summary/score/选择。
decision固定HELD_LAG_DIAGNOSTIC_NO_PROMOTION，promotion_allowed/shipping_approved=false；无阈值/分类器/候选或声学新裁判。

## P3 执行、独立验收与失败边界

PLAN独立PASS后实现，fresh实施PASS后首次实际运行；Python3.8兼容，工具进tools.codex_assets；非仓cwd help/deep dry-run/selftests/main依次执行。
纯Python stdlib诊断，不编译新C或链接DSP，不声明allocation-free/实时/目标资源。主父wrapper整体timeout=None，预检/负例timeout120；retry_budget2。
输出只fresh direct /tmp/audio-fe-device-held-lag-d36-20261011；拒绝旧D35根/仓根/已有D36根，全部三根完整manifest前后相等，不抽样。
独立verifier不import新tool/helper，用反向样本累加全46例126486帧复算rr/xx/rx和因果前帧索引；余弦/gap abs<=1e-12、能量相对<=1e-12，零能量和-1 sentinel精确相等，整数/reason/null精确。
独立用已有封存D35数值复算240原窗/near/no-near/guard前帧统计、nearest-rank和repeat/futureprefix，全部来源及新audit源码起止锁。统计可基于已独立核过的导出值，不能绕过逐帧数值复核。
必须运行known-answer：前帧lag延续反相、当前最优lag变化但past_lag固定、前帧无效不保持、零res/零ref、帧0、非有限/shape/缺CSV字段；工程fixture不作真人或设备证据。
异常/失败有不覆盖回执；先写command/exit/elapsed/部分输出，再失败传播，mock不当实际超时证明。不得追宽容差或挑窗口/lag/阈值获取PASS。
独立whole-change、REVIEW后docs/gitdiff复验及Runtime final分别收口；旧D35 README快照随追加入口历史化，专属source/input/artifact不改。

## P4 资源、接力与停止条件

资源矩阵=主诊断→三根negative→独立audit串行；独立audit准备可并行，禁止对共享输出重跑写入。
staleness_threshold=120s无输出仅观察同一真实handle，不把poll超时当终态重启；heartbeat=实际进程/Runtime；attestation_readback=起止锁/runner无DSP执行。
open_items3，plan_completeness=P1/P2/P3/P4，logical_task_open=true，milestone_close仅前帧预测诊断，session_handoff_required=PLAN/RESULT/REVIEW与回执。
required_evidence=独立计划/实施/全数值/whole-change审查、真实执行/负例/文档/身份锁；completion_claim未成立。
stop_condition=pass/replan/blocked/abort；身份漂移、两次未知失败或无信息增量必须replan；不继续同类观测扫参。
handoff_target=判断历史峰值是否有时间预测性，决定是否有理由进入新因果结构；若混合near仍不可分，转向可解释残差模型而不是阈值寻优。
rollback_path=停用D36诊断入口，旧库/数据/算法/失败记录和用户dirty保持。
AISpeech整链/真人near/KWS/SSC305 CPU/RSS/栈/热/功耗/HIL/E001/PQ/第三方权利/owner分别未闭合，无commit/push/PR/merge/发布/设备写。
