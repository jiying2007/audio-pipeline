# D37 因果残差模型冻结计划

2026-10-11；experiment=FE_DEVICE_CAUSAL_RESIDUAL_MODEL_D37；primary=adk-planning-execution-loop。
goal_statement=全面推进优化迭代；claimant=root；verifier=device_capture_independent_review；总体native目标active，无token上限。
上一轮分类progress：D36真实46例/126486帧独立复算闭合，并证实混合near仍有稳定echo；本轮按其停止条件replan，不继续相近相关性诊断或阈值寻优。

## P1 基线、来源与假设

kind=first-party causal residual-model research；implementation_permission=新Python模型工具/tests/PLAN/RESULT/REVIEW及中文README入口，无产品default/API/设备写。
local HEAD=572b0e34a8a8e5663397ce16e378209ba9058d4d；保留旧dirty和D0–D36专属source/input/artifact。
fresh main=d3f89e54beed483fcc0f8ce59e74b28533ed19b5，77checks完成76success/1skip、summary/release/convergence成功；PR721/717/714/708/695独立open。
#657 OPEN updated2026-10-10T11:33:28Z；最新nonexpired artifacts11693875016/11693720104/11693561872均head f495801f1d5782d8ace8b67abb0f18ec2b53cd36，不批准本地研究。
已读不可变授权方案与live tracker；Provider route unresolved/current为空，知识线NEEDS_REVIEW，不采用不同AISpeech reviewing归档作为本地当前事实。
D36 result/binding SHA256=8b1123301e08caa8e695188e8005a1022e0f023500e5151046454bb90f28c8b9 / 800b73b466054e606eeb6a70210d0027e01fde3eb1d225738ea84ff4bf09820e。
D36 REVIEW=4af6a9db121ea7c70bd727a3993d8e95ff55e9d6bf6886f9ea1803440a38eea3；全部source/input/artifact起止核，锁独立audit源码/回执及REVIEW。
数据固定原46例126486帧：32field/12return/repeat/future，消费D30 reference/未保护primary残差、D35 chosen_lag、D32 monitor guard及near原Float32，全部已锁；inspected development/synthetic engineering、adaptive reuse，无validation/blind/真人资格。
question=过去帧拟合的有符号残差echo模型能否在下一帧预测稳定echo，并保留混合near创新与路径失配的失败？
hypothesis=稳定echo可能被过去系数预测，混合near有剩余创新；单lag模型遗漏多反射、幅度改变/lag改变可导致创新增加甚至超过原残差，必须如实保留，不把创新命名为真near。

## P2 唯一结构与测量合同

仅改变从相关性观测到“过去拟合→当前预测”的可解释模型；不运行旧AEC/DSP或本帧lag搜索，不生成保护阈值/分类器/反馈候选。
每帧f取D35 f-1 valid_lags>0的chosen_lag L；否则无模型，不保持更早有效状态。f=0无模型。
在过去完整160点帧f-1，以其自身chosen_lag的参考计算 fit_xx=sum(x[t-L]^2)、fit_rx=sum(r[t]*x[t-L])，beta=fit_rx/fit_xx。逐点Float32解码后double正向累加；beta保留正负。
过去chosen_lag保证0<=L<=1535且L<=160*(f-1)，fit_xx必须>0；不扣均值/补零/重采样/平滑/epsilon/正则/绝对值化或当前拟合。
模型应用当前f：prediction[t]=beta*x[t-L]；innovation[t]=r[t]-prediction[t]。分别正向累加 rr=sum(r²)、xx=sum(xlag²)、prediction_energy=sum(prediction²)、innovation_energy=sum(innovation²)，不采用可能抵消的能量差公式代替逐点创新。
模型可用时即使当前xx=0或rr=0也输出真实prediction/innovation；rr=0时归一化无效，不能丢弃模型或伪造ratio0。
CSV固定15列：frame,past_lag,model_valid,reason,normalized_valid,beta,fit_reference_energy,fit_cross_energy,residual_energy,reference_energy,prediction_energy,innovation_energy,innovation_ratio,explained_fraction,held_cos2。
reason=0有模型、1帧0、2前帧无效；model_valid=(reason==0)；normalized_valid=model_valid且rr>0。
无模型past_lag=-1，beta/fit_reference_energy/fit_cross_energy/reference_energy/prediction_energy/innovation_energy/innovation_ratio/explained_fraction/held_cos2均-1，仍报告真实rr。
有模型beta和fit_cross可为负且不能以-1当无效判据；xx/prediction/innovation允许真实0。归一化有效时innovation_ratio=innovation_energy/rr、explained_fraction=1-innovation_ratio；ratio不限定<=1，fraction可负，不clamp或删失败。
held_cos2直接读取D36本帧字段，保留其自身valid/null，不因model/normalized改变对照集合；不用于拟合或选择。
全部生成值须finite；极端幅度导致非有限时fail-closed保存异常回执，不补floor或缩放使其通过。
模型在f开始使用f-1状态，创新仅f结束可用，若用于控制最早f+1；fit与预测不重叠。lag仍来自封存未保护D30/D35，不假装反馈候选已经拥有它。
只导出CSV及能量/统计，不输出新产品音频或把prediction称真估计echo、innovation称near truth。没有AEC ERLE/声学新裁判或降能量即收益的判据。
selected统计：beta、prediction_energy、innovation_energy按model_valid；innovation_ratio/explained_fraction按normalized_valid；held_cos2自身>=0有效。reason0/1/2计数、model/normalized有效数、ratio>1的失配帧计数；nearest-rank p10/p50/p90/min/max。
原240 whole/window inward完整160点帧与边界丢弃；monitor guard触发f只事后选新特征f-1且首帧guard=0；near仅原Float32非零[1000,1200)/[1600,1800)，其余mixed来源只称no-near。
field无near truth/零参考null单列；repeat全部CSV exact、future仅通知前1247帧前缀exact且measurement=null。
固定decision=CAUSAL_RESIDUAL_MODEL_DIAGNOSTIC_NO_PROMOTION、promotion_allowed/shipping_approved=false；诊断模型不是shipping算法或near检测器。

## P3 执行与独立验收

PLAN独立PASS后实现tools.codex_assets/device_causal_residual_model.py及对应test；fresh实施PASS后首次真实运行。
纯stdlib Python3.8，无新C编译/第三方依赖，不声明allocation-free/实时/目标资源；原全链资源预算与超限保持。
输出仅fresh direct /tmp/audio-fe-device-causal-residual-model-d37-20261011；非仓cwd顺序help/deep dry-run/tests/main，主wrappertimeout=None、其他120s，retry_budget2。
拒绝旧D36根/仓根/已有D37根，三根完整manifest前后exact，不抽样；异常先写command/exit=null/type/elapsed/部分输出，再传播且不覆盖失败。
known-answer必须覆盖：正/负beta、非零lag跨帧预测、真实路径幅度改变导致ratio>1/fraction负、near创新、当前rr0但模型仍有效且ratio无效、当前参考零、前帧无效不保持、f0、shape/NaN/CSV缺字段、未来前缀无影响。
独立verifier不import新tool/helper，以reverse160样本全46/126486逐帧复算fit/beta/prediction/innovation/归一化，past整数/reason/valid/null与held直接值exact。
零energy/无效sentinel精确；fit_cross可负，按model_valid判断。非零energy及fit_cross/beta相对误差<=1e-12（若expected为0须exact），ratio/fraction abs<=1e-12。若近零fit_cross反向累加相对不稳则保留失败并replan数值合同，不能事后放宽。
独立统计可基于已逐帧核过的导出值复算全部240窗/near/no-near/guard前帧/repeat/future；audit源码/全部来源与新result/binding起止锁。
主/negative/audit串行资源矩阵；audit准备可并行、禁止重复写共享输出。源码/helper复用须锁，禁止修改旧measurement或用新裁判批准新产品算法。
whole-change独立PASS后REVIEW，再docs/gitdiff复验/Runtime final独立附核；README追加使旧D36README快照历史化，旧专属身份不改。

## P4 连续性与停止条件

open_items3；plan_completeness=P1/P2/P3/P4；logical_task_open=true；completion_claim未成立；milestone_close仅因果残差模型研究，session_handoff_required=PLAN/RESULT/REVIEW/实际回执。
required_evidence=独立计划/实施/全数值/whole-change/最终附核、实际主/negative/docs/来源锁；success_criterion=device-d37-model-verified，不等同声学晋升。
staleness_threshold=120s无输出仅核同一已确认live handle，不因观察超时重启；heartbeat=真实进程/Runtime；attestation_readback=起止来源/拟合时间/无DSP或搜索。
stop_condition=pass/replan/blocked/abort；身份漂移、两次未知失败、数值合同失效或模型无新信息必须replan，不通过增加fit窗口、阈值或选择near数据换PASS。
handoff_target=决定过去有符号残差模型是否提供可解释成分与创新，以及其失配边界；多路径/near混淆仍在则提出新的结构假设和独立数据需求，不批准标量预测器为产品保护器。
rollback_path=停用D37研究入口，旧算法/库/数据/用户dirty保持。AISpeech整链、真人near/KWS、SSC305 CPU/RSS/栈/热/功耗/HIL/E001/PQ/第三方权利/owner独立未闭合。
原生goal无预算上限；Runtime本地预算仅任务控制，不替代总体目标。维护压力按canonical decision处理，不计业务blocked；v3原生控制未修未用，不恢复其compact路径。
本轮入口纠错保留：本机gate不支持replan、goal子命令不支持ensure，两次CLI实际exit2且未改变任务；改用已验证snapshot steady实际pass及顶层ensure help，禁止继续猜接口。
