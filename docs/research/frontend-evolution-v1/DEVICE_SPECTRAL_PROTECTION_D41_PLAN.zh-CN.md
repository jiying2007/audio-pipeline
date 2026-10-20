# D41 因果频带创新保护计划

2026-10-11，experiment=FE_DEVICE_SPECTRAL_PROTECTION_D41，kind=bounded first-party structural research candidate。goal_statement=全面推进优化迭代，primary=adk-planning-execution-loop；计划先独立审查再实施，未声明执行或效果。

## P1 原因、基线与唯一变化

D40正式92执行和独立全量审计完成：关闭频域RES使合成含near配对误差中位下降6.1926dB，但无near残余能量中位增加16.7177dB，所有72窗/arm退化。全局关闭不是可采用方案。D32–D38保留整帧同帧相关、历史lag及因果模型的混合near/路径失配歧义；不继续扫描这些标量的相近阈值。

假设：多帧频带级线性关系可以提供比整帧标量更细的保护。唯一算法变化是在原频域RES的每bin target上加入由过去帧复数交叉谱统计给出的gain下限；ordinary NS、实际Activity/allow、AGC/VAD、AEC/选择/过渡及D30输入不变。保护不反馈AEC/Activity，不使用near标签，不称为完整双讲检测器。它可能把路径切换创新误作near，必须保留对应纯echo窗口代价。

基线D39 result/binding SHA256=3bf15108885f0b356e0ebcc1f799a2de6178a12665b71aa13ffa79d1774f93fc / 26a53260fcd4662a90bb1a8649dbb47931b2e1474e534b613de80eea83639663。D40 result/binding=333d6a42b9dfc96f527f76e99ec177ab8a8407389cc1dfad3e02a86127e7d3e6 / ea98a23e0cb66d390b0b94a36634a6e1d80937725a5e7b0619613e3f9e6a4f4f，最终snapshot65106abad5437ba1e2d44ad3640fcc3690b6a6db1a379bed382287a93850ded9只读。

原D18 lib eb5b0c784c316e71d6ed9f58db6cb66f190b631daa00c55a94032168d5a47aa4保持，不重编库。独立研究NS函数由D18 first-party ap_ns.c逐字节来源派生、新符号编译，并记录源hash及完整diff；原NS符号/库不替换。新函数monitor关闭新保护必须全输出逐byte复现D39；candidate仅启用新target下限，两种执行各自独立持续状态。

localHEAD572b0e34a8a8e5663397ce16e378209ba9058d4d，fresh main d3f89e54beed483fcc0f8ce59e74b28533ed19b5；77checks completed，76success/1skip，summary success。#657 OPEN updated2026-10-10T11:33:28Z；721/717/714/708/695远端head与最新3artifact只读刷新，均不批准本地研究。Provider route unresolved、返回无关reviewing记录，知识NEEDS_REVIEW，不据其推断项目事实。

## P2 固定频带状态与因果规则

16000Hz、160samples/frame、原nfft512/bins257、原window/OLA和float DSP保持。新增每bin binary64 EMA四状态 E、R、Cr、Ci，以及当前echo复数bin scratch float32两数组；count为连续freq_res有效帧的公共计数，上限10。所有新增状态初始化为0，原频域支路inactive时清新增EMA/count，不修改原residual_gain_bins释放机制。

当原freq_res=true时，保留原echo FFT的复数bin到scratch；完成原residual FFT后逐bin读取新增旧状态，先计算保护再更新EMA。因此本帧保护只依赖到上一帧的完整统计，与当前/未来标签无关。旧count>=10且E>1e-12、R>1e-12方valid；otherwise下限0、不修改原target。valid时 coherence=clamp((Cr*Cr+Ci*Ci)/(E*R),0,1)，innovation_fraction=1-coherence，floor=float32(sqrt(innovation_fraction))。candidate的target=max(original_target,floor)，monitor仍original_target。后续原0.55/0.45 attack、0.92/0.08 release及NS增益流程全部保持。

EMA固定alpha=0.2（以binary64字面量运算），更新顺序E,R,Cr,Ci，new=0.8*old+0.2*current；currentE=er*er+ei*ei，currentR=rr*rr+ri*ri，currentCr=rr*er+ri*ei，currentCi=ri*er-rr*ei，所有乘加由恢复到binary64的原FFT float32分量执行，ffp-contract=off。没有本帧统计更新后回读、二次DSP、lookahead、lag搜索、阈值寻优、标签反馈或新增floor上限选择。

新增保护汇总trace逐frame记录count_before/after、valid_bins、raised_bins、floor_mean和far/dt；finite/range/顺序及count规则可全帧审计。NSFFT不独立重算；不能将汇总合法性当作每bin波形或声学资格，新增EMA/下限算术须以独立已知答案验证，并公开此覆盖边界。

## P3 矩阵、测量和验收

冻结原D30 46来源，两臂primary/selected × monitor/candidate=184次新C执行、505944帧。旧D39/D40不重跑。32field已查看development、12return合成及repeat/future；adaptive reuse，非独立validation/blind。保护只接收echo/residual和原gate，不传near/窗标签。

monitor四原输出必须逐byte复现D39；candidate bypass/gates/allow/普通NS speech_probability和noise_rms_dbfs与D39 exact。两模式各arm repeat四输出与保护trace全量byteeq，future通知前1247frame及CSV1248行eq，future不评分。原每arm45whole+195fixed，两个模式×两臂总180whole+780fixed=960测量组；保持原160点测量坐标/tail/null/no-flush，候选各stage对D39同窗配对差值，不建立第二声学裁判。

本轮冻结开发研究准入（不来自独立数据）：candidate每臂含near24fixed的配对final known-near error中位<=-3dB，至少18/24严格改善；candidate所有无near72fixed/arm及其whole的final energy对D39增加均<=1dB；field不设声学优胜门槛，逐例披露。任一条件不满足固定SPECTRAL_PROTECTION_DEVELOPMENT_REJECTED，全满足仅SPECTRAL_PROTECTION_DEVELOPMENT_CANDIDATE_ONLY；两种结果promotion_allowed=false、shipping_approved=false。不调宽准入、timeout或数值要求换PASS，不用whole代替near/恢复窗。

scoped下游<=65536B，与D30原71224B合计<=131072B；B0 50000B保持、不推目标板资格。新增EMA/scratch实际sizeof计入，不把双模式状态相加当单线程；编译/主墙时与资源分别记录。严格原FLAGS及D18defs/includes/lib；每命令timeout120s、唯一正式主预算1800s。live观察超时继续核同handle，既有根/intent拒绝重放。

## P4 实施、验证与停止

scope_write仅新D41 PLAN/PLAN_REVIEW/NS/header/C/tool/tests/IMPLEMENTATION/RESULT/REVIEW/CLOSEOUT及最后README入口；手改apply_patch，原D0–D40/用户dirty保留。输出root=/tmp/audio-fe-device-spectral-protection-d41-20261011，先深preflight锁D30/D39/D40/D18源码生成头/flags/lib、来源角色与所有依赖起止hash。

计划独立PASS→实施→known-answer：相干复数比例floor0、正交平均floor1、零能量无效、count9/10边界、inactive清状态、float边界与coherenceclamp、过去状态因果/不同未来前缀；新增算术独立binary64参考，C真实自测，monitor等价实际全矩阵。非法argc/frames/mode/gates及sentinel保护；非仓cwd help/deepdry/定向测试；已有D30根/仓根/新输出根三负例完整manifest保护。

独立audit不import新measurementhelper、不复跑DSP：所有184cases/PCM、AGC/VAD binary32递推、960测量组、candidate配对差值/开发准入、ordinaryNS exact、monitor四输出exact、trace范围/count/causality、源输入制品起止锁。RMSabs tolerance1e-10dB、peakexact保持；NSFFT/EMA实际所有bin不独立重算的边界披露，不能扩大已知答案覆盖声明。任何来源/数值/measurement合同失败固定MEASUREMENT_INVALID_REPLAN，保留失败根/回执，以新身份修复，不能重放原根。

claimant=root，verifier=device_capture_independent_review，required_evidence=plan/result/review，open_items3，logical_task_open=true，milestone_close仅D41开发结果；retry_budget2仅明确缺陷后新身份，staleness_threshold=冻结依赖漂移即replan，attestation_readback=起止SHA/真实terminal，heartbeat=实际阶段及livehandle，stop_condition=pass/replan/blocked/abort，plan_completeness=P1/P2/P3/P4。资源矩阵=实施源码单owner、主根写终态后审计只读；独立reviewer只写/tmp审计，sharedcontract串行。

后续handoff=保留候选有效/拒绝结果后研究独立真人混合及AISpeech可借鉴边界，不自动替换产品；SDK/fullfrontend、真人识别、目标CPU/RAM/功耗/HIL、rights/owner/shipping分别待证。无commit/push/PR/merge/release/设备写；总体native优化目标active且无预算上限。
