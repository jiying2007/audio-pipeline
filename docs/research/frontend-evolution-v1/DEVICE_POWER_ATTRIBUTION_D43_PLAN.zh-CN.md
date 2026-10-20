# D43 过去功率来源与恢复过程诊断计划

2026-10-11，experiment=FE_DEVICE_POWER_ATTRIBUTION_D43，kind=measurement-only first-party diagnostic。goal_statement=全面推进优化迭代，primary=adk-planning-execution-loop。先冻结并独立审查本计划，再实施；当前未声明新诊断已执行。D42工程闭环及候选拒绝保持，不能通过新测量批准原候选。

## P1 问题、边界与冻结身份

D42从过去帧创新比例扣除原NS上一帧噪声估计N/R后，纯echo整例最大能量增加收窄到+.38711/+.54046 dB，满足原1 dB限制；但near误差配对中位仅-2.18247 dB，未达-3 dB，no-near fixed最大+3.70940 dB、primary22/72及selected24/72超限。最坏窗为静态A-r20-dt/unguarded-shadow原坐标[200000,224000)，即近端12s结束后的12.5–14s。原observer仅有count/valid/raised/floor_mean，不能解释旧噪声估计与创新功率各自约束了多少bin、哪些阶段还被保护。

研究问题：在同一D42处理状态下，过去非相干创新功率、原NS旧噪声估计、剩余创新和target抬升的观测如何随固定近端/恢复窗口变化？只诊断已有失败，不新增算法、阈值、噪声估计器或near输入，不选择候选。创新不等于near、N不等于已知背景真值，观测相关性不证明唯一因果。现有near是合成工程信号，不是真人语音；field无near真值。

D42 result/binding SHA256=`a2b839fbc635d1f1664d4c98d0406186e481b52aaef0a2a4fd4f4285902f31e2` / `291d91f48162fa5fcab3f7deff25ec8c9baff77cbe7e39cd78004108f52883f0`；review snapshot=`3faf06d95b908ea2debe20fb3048cfe06c8d4bf991a7c855dece1e50a144a892`。实际重新读回40项冻结文件全部当前相同。只锁历史snapshot本身，不要求其README在新入口追加后永远等于当前。D42全部源/依赖/工件锁均继承，原D18lib `eb5b0c784c316e71d6ed9f58db6cb66f190b631daa00c55a94032168d5a47aa4`不重编。

fresh localHEAD=572b0e34a8a8e5663397ce16e378209ba9058d4d，远端main=d3f89e54beed483fcc0f8ce59e74b28533ed19b5，77completed/76success/1skip/summarysuccess；#657 OPEN、updated2026-10-10T11:33:28Z，openPR721/717/714/708/695，最新三工件来自f495801f...，不批准本地研究。Provider query零命中/route unresolved，检索返回的PCR02大文件诊断reviewing候选与本实验不匹配，不作authority，知识NEEDS_REVIEW，未归档成功。

## P2 测量契约和唯一变动

从D42 first-party NS fork派生新ap_ns_process_d43，只增加observer指针和只读捕获；保持全部实际算术表达式、执行顺序、D42guard/header、NS/噪声tracker更新、OLA、保护target、AGC/VAD及frequency_res enable1。observer不写回算法状态；NULL observer自测可用。沿用D42两模式monitor/candidate作为冻结算法控制，不产生新的候选臂。新测量原五输出bypass/ns/final/control/protection必须与D42每个同名执行逐byte完全一致，不接受epsilon。

每bin在当前guard更新和原noise_tracker更新之前捕获旧E/R/Cr/Ci/N、当前echo/residual复数FFT、当前power/echo_power；捕获floor/valid、原target、active分支实际old gain、applied target及实际res gain。旧N是float恢复double，不能改读当前更新值。inactive的保护/target/gain测量字段标0并显式far/dt，当前residual FFT可观测，echo FFT未计算则标0；不把未计算的echo说成物理零。

每帧输出power.csv：frame/far/dt/count_before/valid_bins/noise_dominant_bins/positive_floor_bins/would_raise_bins/raised_bins/q_mean/echo_sum/residual_sum/innovation_sum/noise_sum/excess_sum/floor_mean/floor2_residual_sum。统计只在active且valid的bin上汇总：q=clamp((Cr²+Ci²)/(E*R),0,1)，raw_fraction=1-q-N/R，noise_dominant以raw_fraction<=0判定，innovation=R*(1-q)，excess=R*max(raw_fraction,0)，floor2_residual=floor²*R；floor_mean是实际全部257bin floor之和/257。would_raise是floor>原target，即使monitor也观测；raised仅实际candidate抬升。q_mean除以valid数，valid0取0；所有非法值拒绝。噪声主导与float32 floor正值不强求在极小量下形成精确互补分区。

固定稀疏全bin快照bins.csv，不事后挑帧：frame%100==0，另外frame属于{1,9,10,11,999,1001,1199,1200,1201,1599,1600,1601,1799,1800,1801}，以及实际末帧；集合去重并只取frame<frames。每个选定帧输出k=0..256的完整22字段：frame/bin/far/dt/count_before/valid/E/R/Cr/Ci/N/er/ei/rr/ri/power/echo_power/original_target/old_gain/floor/applied_target/res_gain。double用17有效数字，float用9有效数字，保持binary64/binary32往返。快照稀疏，不能声称全部帧bin状态独立复算。

字段阶段语义、合法范围、顺序、数量和固定选帧集合是测量验收，不设置声学胜出门槛。q/innovation/noise/excess是算法估计功率；不同统计时间尺度、NS正则和窗口导致N与R不完全相同。它们的比值和分组描述不作物理来源真值、ERLE或真人效果。

## P3 固定矩阵、预算、验证与诊断输出

保持D30全部46来源×两臂×两模式=184新观测执行/505944帧，覆盖field、12return、repeat/future；不是重跑旧D42root或重新选择算法。只有D43observer的新C执行，旧AEC/D39/D41/D42不重跑，全部原五输出对已冻结D42 byteexact。四mode/arm各45whole+195fixed=960组，原160点坐标、tail/null/no-flush及既有near标签保持。future不评分，repeat不算新增独立样本，development与合成engineered role保持。

power.csv全帧，bins.csv仅固定稀疏帧；两模式observer除实际raised/applied/resgain及old_gain外相同（其余统计不受抑制输出反馈），重复与future前1247帧所有诊断记录前缀相同。old_gain继承前帧实际保护gain，不能要求两模式相同。将实际near波形标签仅用于离线固定窗描述：near、near后恢复、纯echo、field分别报告旧N/R、innovation/excess和would_raise的分布及来源，不把stage label喂回DSP。描述分组必须披露全部固定窗口，不挑最坏/最好窗形成新准入。

只接受POWER_ATTRIBUTION_DIAGNOSTIC_NO_PROMOTION，promotion_allowed=false、shipping_approved=false；D42准入拒绝原样附带，不重评或批准。输出不等价、非法数值/身份/测量失败固定MEASUREMENT_INVALID_REPLAN，保留失败root/真实partial receipt，以新身份修复，不在同root重放。

单命令timeout120s、主预算1800s保持。observer实际sizeof单列，原算法scoped22000 B不变；含observer测量scoped<=65536 B，加D30原71224 B<=131072 B，B0 50000 B资格不变。单工件<=4MiB，output root总量<=1536MiB，启动前可用磁盘>=3GiB；当前/tmp实际可用约16GiB，只作本次预查，执行前复核。真实编译/执行墙时与资源分别记录，不当目标CPU/RAM/热/功耗资格。

定向tests验证固定选帧、非法数值/模式/计数及immutable D42拒绝、篡改观测/缺行/重复bin/字段和future未评分负例；strict C编译、真实known-answer自测含NULL observer等价、采集顺序和zero/暖机/inactive分支，原AGC及D42known-answer保持。非仓cwdhelp/deepdry写入False、既有D30/仓库/D43root三负例完整manifest保护，原非法argc/frames/mode/gates及sentinel保持。

独立audit不import本轮measurementhelper、不重跑DSP：核184五输出D42byteexact、所有trace帧/稀疏选帧bin集合、快照的实际旧state→q/raw_fraction/floor/originaltarget/appliedtarget/resgain算术（double及binary32）、选帧汇总与power.csv、双mode控制、repeat/future/near标签和来源锁。原960测量可直接要求与D42完全相同并继承已完成的全量波形审计，不能冒称新重算；独立只读核新描述摘要。全部帧FFT、bin EMA和oldnoise真实内部状态不独立全量重算，采样快照内部公式核验也不能升级成该覆盖。

## P4 实施边界、阶段和停止

scope_write仅新D43 PLAN/PLAN_REVIEW/header/NSfork/C/tool/tests/IMPLEMENTATION/RESULT/REVIEW/HANDOFF/CLOSEOUT和最终README追加；手改apply_patch，Python工具进tools.codex_assets。原D0–D42/dirty不改，shared contract串行。正式root=/tmp/audio-fe-device-power-attribution-d43-20261011，排他intent/receipt；观测超时仅核同handle，未知对账不重发。

阶段：计划独立审查→最小测量实现与定向验证→实施独立审查/冻结source与唯一writer→fresh Runtime允许后正式矩阵→根保护负例及独立观测审计→真实结果/中文入口/whole review→本地最终收口。claimant=root，verifier=device_capture_independent_review；task-package v2 kind=implementation，question=功率估计与恢复超限关系，permission=已授权first-party测量实现，evidence=plan/result/review，exit=测量等价且拒绝/边界披露准确，handoff=root，retention=锁定脱敏结果和失败。

required_evidence=plan/result/review，open_items3，logical_task_open=true，milestone_close仅D43诊断，不完成总体native目标。retry_budget2只用于明确缺陷后新身份，staleness_threshold=任何冻结来源漂移立即replan；heartbeat依据实际阶段与livehandle，不把等待或心跳当测量进展；attestation_readback=真实terminal/起止SHA/独立审计。plan_completeness=P1/P2/P3/P4，stop_condition=pass/replan/blocked/abort；连续两轮新major/findingclass回计划审查，未知执行不重放。

AISpeech固定点/QIVW、真人效果、外部数据/rights、目标板与E001/HIL/shipping独立待证；知识NEEDS_REVIEW，不从路径猜归档成功。无commit/push/PR/merge/release/设备写。总体目标继续active且无token上限。
