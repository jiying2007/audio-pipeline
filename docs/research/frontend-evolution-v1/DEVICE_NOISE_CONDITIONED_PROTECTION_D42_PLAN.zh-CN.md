# D42 过去噪声功率约束的频带创新保护计划

2026-10-11，experiment=FE_DEVICE_NOISE_CONDITIONED_PROTECTION_D42，kind=bounded first-party structural research candidate。goal_statement=全面推进优化迭代，primary=adk-planning-execution-loop。本计划先独立审查，再实施；不声明执行或效果。上一轮D41正式184执行及独立审计/里程碑完成，候选拒绝和冻结文件保持。

## P1 原因、假设与身份

D41 near固定窗配对误差中位约-5.15 dB、两臂20/24改善，但72个no-near窗全部增加能量，中位+14.1051 dB、最大+16.5907 dB；pureecho whole最大+2.1732/+2.1080 dB超过冻结1 dB。静态纯echo末窗也退化，不能只归因路径切换或near恢复。归一化非相干比例直接生成高gain下限，不能区分背景/残余非相干量与near。

新假设：从过去帧创新功率扣除原NS已估计的噪声功率，可以减少低能量非相干残余的误保护，同时保留超过噪声的near创新。它可能把near也归入原噪声估计而损伤near，或未解释残余echo；必须按原冻结开发准入拒绝不合格结果。本轮只改变保护下限公式，不新增噪声估计器、阈值搜索、标签输入或反馈AEC/Activity。

D39比较基线result/binding SHA256=3bf15108885f0b356e0ebcc1f799a2de6178a12665b71aa13ffa79d1774f93fc / 26a53260fcd4662a90bb1a8649dbb47931b2e1474e534b613de80eea83639663。D41锁定result/binding=38d6f5eab2e3c3f6c8d9bea66f267015f7f02cde5ce73e5f3db29d32c1e3ce47 / a61625805a15ac877724064c1777bd2681751b1398b4cb86f1d206d35160a35f，snapshot=aedf5529766fbe90e5260b75cff3e092cda942314a53f7dc171201fe88cce3b4；D41近端收益不能授权本轮效果。

localHEAD=572b0e34a8a8e5663397ce16e378209ba9058d4d，fresh main=d3f89e54beed483fcc0f8ce59e74b28533ed19b5，77checks completed/76success/1skip/summarysuccess。#657 OPEN updated2026-10-10T11:33:28Z，open721/717/714/708/695及最新三制品只读刷新；不批准本地研究。Provider零命中/route unresolved，知识NEEDS_REVIEW，不能猜项目归档或主体。

[Speex预处理源码](https://github.com/xiph/speexdsp/blob/master/libspeexdsp/preprocess.c)分别维护背景噪声与残余echo估计，说明功率来源分离的设计价值；这里只作外部设计参考，不导入源码、库、参数或第三方执行资格。本轮公式为first-party研究假设，不能借外部实现批准效果。

## P2 唯一公式、状态顺序与不变量

沿用D41每bin过去帧binary64 EMA E/R/Cr/Ci、0.8old+0.2current、连续active count上限10，inactive清新增guard、原NSrelease保持。echo/residual FFT、512nfft/257bins、160samples/frame、window/OLA不变；ffp-contract=off。新增公式读取原NS noise_tracker.estimate[k]的上一帧binary32值，恢复到binary64 N；必须在当前bin原ap_noise_tracker_update之前读取。噪声状态本来就是pre-RES输入驱动，不读抑制后的输出，不改变noise_tracker初始化/更新/next_frame及ordinary NS统计。

当旧count>=10且E>1e-12、R>1e-12时，q=clamp((Cr²+Ci²)/(E*R),0,1)，fraction=max(0,1-q-N/R)，floor=float32(sqrt(fraction))。其他count/energy无效时floor0；N=0退化为D41原floor，N>=R*(1-q)时floor0，N只允许finite非负。全部输入/中间量非有限或非法拒绝，不能clamp NaN/Inf取得绿灯。原target与后续attack/release保持，candidate target=max(original_target,floor)，monitor仍original_target。

先旧EMA/旧count/原旧noise估计取floor，再更新guard的当前FFT统计，最后原noise_tracker更新；不读当前噪声估计或未来。两模式同输入同统计，observer除raised_bins全部exact。相同case/arm下本轮每帧floor_mean必须<=D41原floor_mean（不加容差），是新公式的单调不变量，不是声学胜出门槛；count/valid_bins必须与D41相同，N不改变valid定义。trace schema仍frame/far/dt/count_before/count_after/valid_bins/raised_bins/floor_mean。

原AEC/D30匹配echo/residual、原Activity/allow、ordinaryNS(.12 FULL)、AGC(-20/-2及!(far&&!dt))、VAD和选择/过渡不变，frequency_res enable1不全局关闭。新研究符号/文件派生D41，不替换原D18 NS符号或原库；D18原lib eb5b0c784c316e71d6ed9f58db6cb66f190b631daa00c55a94032168d5a47aa4保持，不重编。

## P3 固定矩阵、测量与开发准入

原D30 46来源×primary/selected×monitor/candidate=184次新C执行、505944帧；32field是已查看development，12return合成及repeat/future为工程控制，adaptive reuse、非validation/blind。无near标签进入算法，不搜索参数。

monitor四原输出必须逐byte复现D39，也与D41monitor相同；candidate bypass/gates/allow和普通NS speech_probability/noise_rms_dbfs恢复binary32后与D39 exact。五输出repeat全量byteexact、future前1247帧/CSV1248行exact、四个future不评分。四mode/arm各45whole+195fixed，共180whole+780fixed=960组，原160点坐标/tail/null/no-flush和D39同窗差值保持；whole不能替代fixed。

准入完全沿用D41及其AMENDMENT：仅每candidatearm12个非future return的24near/72no-near fixed，以及四个near全轨迹zero来源return-A-r16-echo-shadow、return-A-r20-echo-shadow、return-ABA-r16-echo-shadow、return-ABA-r20-echo-shadow的whole。near final known-near配对误差中位<=-3 dB且至少18/24严格改善；72no-near fixed和四pureecho whole的final能量增加每个<=1 dB。field/repeat/future和含nearwhole不入准入。

两臂均满足仅NOISE_CONDITIONED_PROTECTION_DEVELOPMENT_CANDIDATE_ONLY；任一失败NOISE_CONDITIONED_PROTECTION_DEVELOPMENT_REJECTED；promotion_allowed=false、shipping_approved=false。measurement/source/numeric合同失败MEASUREMENT_INVALID_REPLAN，保留失败根，以新身份修复，不改判或重放。

原单命令timeout120s、主预算1800s保持；scoped下游<=65536 B，加D30原71224 B<=131072 B，原B0 50000 B仍保持。真实sizeof、编译/主墙时分别披露，不称为整线程/目标CPU/RAM/功耗/热资格。live观察超时只核同handle，既有root/intent拒绝重放。

## P4 实施、验证、审查与停止

scope_write仅新D42 PLAN/PLAN_REVIEW/header/NSfork/C/tool/tests/IMPLEMENTATION/RESULT/REVIEW/HANDOFF/CLOSEOUT及最终README入口；手改apply_patch，工具进tools.codex_assets，不动原D0–D41或用户dirty。root=/tmp/audio-fe-device-noise-conditioned-protection-d42-20261011。preflight继承D30/D39/D40/D18锁并新增D41完整locked_files/artifacts及result/binding身份；冻结本轮源和计划，所有来源/工件起止校验。

计划独立PASS后实施。known-answer新增N=0退化D41、正交R=1/N=.75得到floor=.5、N>=innovation归零、qclamp、N负/NaN/Inf拒绝、输入功率共同缩放、warmup/zeroenergy/实际inactive清状态；保持原AGC/complexcross测试。实际C自测+定向unit/negative，非仓cwdhelp/deepdry；原D30根/仓根/新根三负例fullmanifest保护，原非法argc/frames/mode/gates/sentinel保持。

首次独立audit不import本轮measurementhelper、不重跑DSP：全部184cases/PCM、AGC/VAD binary32递推、960测量组、D39实际同坐标差值、24/72/4独立标签和开发准入，普通NS/monitor等价、tracecount/range及D41floor单调不变量、repeat/future/源锁。RMSabs容差1e-10 dB、peakexact不变。NSFFT/全部实际perbinEMA及旧noise逐bin状态不独立全量重算，known-answer/source顺序及全帧汇总不扩大覆盖；这是明确剩余边界，不是声学资格。

claimant=root，verifier=device_capture_independent_review；required_evidence=plan/result/review，open_items3，logical_task_open=true，milestone_close仅D42开发研究结果。retry_budget2只允许明确缺陷后新身份；staleness_threshold=任何冻结依赖漂移即replan，attestation_readback=实际terminal/起止SHA，heartbeat=实际阶段/livehandle，stop_condition=pass/replan/blocked/abort，plan_completeness=P1/P2/P3/P4。源码singleowner、主根终态后独立只读，reviewer仅写/tmp审计，sharedcontract串行。

后续按真实candidate或reject结果决定新研究，不直接替换AISpeech固定点/QIVW产品；真人混合、完整SDK、真实识别、目标板/HIL、rights/owner/shipping分别待证。无commit/push/PR/merge/release/设备写，总体native目标active且无预算上限。
