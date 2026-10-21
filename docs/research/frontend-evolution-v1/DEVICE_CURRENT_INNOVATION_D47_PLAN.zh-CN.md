# D47 过去复数拟合与当前创新保护冻结计划

2026-10-13，experiment=FE_DEVICE_CURRENT_INNOVATION_D47，kind=first-party structural algorithm experiment，primary=adk-planning-execution-loop。总体目标“全面推进优化迭代”保持active；前轮分类progress：D46实际完成正式归因、独立复算、历史输入保存、247项快照和本地收口。本计划先冻结结构、裁判、数据角色和预算，独立计划审查通过并登记新任务后实施；尚未实施或正式执行。

## P1 基线、假设与来源

D45候选DEVELOPMENT_REJECTED：near配对误差中位约-3.270 dB，no-near最大+6.552 dB，pure-echo whole最大+1.255/+2.114 dB。D46全部24配对、168固定段及384项stage/whole统计独立复算绝对误差0，确认ABA纯echo回A后的1210–1600帧仍有375/377帧实际保护抬升；不能只修near结束短尾或把单例尾部定位外推整个后续区间。

冻结D45 result=`0d9dbf01b21510216df648d323c501166a039a5b45d44c93d2699b8eabc4e8de`，binding=`bb0fbb8b9942e2b9ca5dbecf9a53ac1f13f38d40c7bbb574d5a438506d00cff8`。D46 result=`562057335c9e6b49aad19519a799da1f466b47d51f1248bec778600af043f94d`，binding=`4feead7e4982576ee7cbb450179de87a26fb64618435064708d69946c536f22b`，最终snapshot=`74ad422a054e9ba245025b1b59dfecd9560bfb85893d29090f5934deb48b568b`，CLOSEOUT=`27ad3165311d15c9cf00a22bfa57e42b5104f3885caf341070f1af1cbe9a982a`。上述历史结果、失败、source、工件和快照不覆写，不重新运行D45/D46正式测量或已成功审计。

本轮只读intake session95981真实terminal0（chunk7d7a37）：冻结D45 preflight返回46来源/9829锁，无DSP/新工件或测试重跑。实际回读五源码SHA：C=`101ba4441794d8845b82904a8c524db4ea88fea746f29b9d0cb08b967baa048a`，NS=`ba6c427a2ea01d0a540bc21a14e6ce6a7c172ed278120b9ae1359ae27ff07724`，header=`82458adbab6fb83708ab89f3cd24b99ccde02f83df1680933b455f74594d570d`，test=`3f6ca5da374fec4afafbc77dd7f44198bf7d79b1241e20bd12bbc08b038bbca0`，tool=`84ae3a41685e46a71769017e17b0ab277c1ef68e3c28e9bd722c5f9872831c17`。新preflight须先核这五项冻结身份再调用只读旧preflight；不能让旧helper的动态自hash代替基线pin。

实际D45源码读取显示floor使用更新前E/R/Cr/Ci和旧noise，I=R*(1-q)为过去统计的创新代理；当前echo/residual FFT复数已经保存，却没有用于逐点预测。D38过去单lag时域模型已保留混合near与echo重叠及prediction失配，不能将创新天然称为near。新假设：把过去复数拟合应用到当前echo，再直接计算当前创新，可能更及时地解释稳定线性echo并释放旧能量保护；路径变化导致预测失配也可能增加创新或放大误保护。是否同时守住原near/no-near准入只由本轮真实新波形和独立旧裁判决定，不预设成功。

唯一结构变化为floor估计器从过去协方差代理切到过去拟合→当前创新映射。原.8/.2 EMA、10帧warmup、far/dt/reset、2N严格门控、post-NS保护位置、NS/RES原状态、AGC/VAD、FFT/OLA、双AEC来源和全部评分参数保持。没有新reference输入、lag搜索、第三方源码/模型/权重、频带mask、额外平滑或系数搜索。模型来自更新前统计；不在本帧重新拟合后再评自己。

当前localHEAD=`572b0e34a8a8e5663397ce16e378209ba9058d4d`，保留已有dirty；fresh main=`6fcb74f5f498dc68fab6127d8bf9bf35411f7d61`，76检查74success/2skip、required summary成功，open PR714/695。#657仍OPEN、updated2026-10-12T12:11:42Z；body较旧checkpoint不是当前main。最新3非过期artifact11784055193/11783605848/11783587146绑定该main，不是本地D47证据。执行前重新核远端与工件，不能借CI批准本地实验。

数据仍为D30原46来源：32已查看field、12合成return、repeat/future；development-and-synthetic-engineering、adaptive reuse。field无near真值，repeat不是独立样本，future不评分。80/100为用户确认音量；运动/物理通道/真人真值不从文件名推造。D18原静态库、D30输入、D39比较对象和D42原observe/admission继续精确绑定。

## P2 唯一算法映射、时序与数值

每active bin保存更新前double E/R/Cr/Ci、旧float noise转double N，当前echo FFT float er/ei及当前residual FFT float rr/ri。finite、N>=0、E/R>=0、count<=10检查保持；count<10或E/R<=1e-12时valid0/floor0。有效模型保留valid1，与保护是否关闭分离。

严格double有序计算：hr=Cr/E，hi=Ci/E；pr=hr*er-hi*ei，pi=hr*ei+hi*er；ir=rr-pr，ii=ri-pi；J=ir*ir+ii*ii，P=rr*rr+ri*ri。复数约定来自旧Cr/Ci更新，即residual*conj(echo)，不得交换符号。所有乘法/加减/除法中间值须finite；溢出保存测量失败，不补epsilon、改精度或截系数求通过。ffp-contract=off、binary32输入/输出、binary64模型及FLT_EVAL_METHOD=0保持。

只在P>1e-12且严格J>2.0*N时floor=(float)sqrt(clamp(J/P,0,1))，否则floor0。这个P门槛仅约束本帧gain的归一化，不改模型valid；真实P=0而J>0仍保留J和overshoot，不伪造J=0或ratio0。J/P可>1，原始值不在诊断中clamp；只有gain限定到[0,1]。J可能大于P，不沿用旧创新<=过去R的字段约束。

floor计算之后才执行原ap_noise_conditioned_update_d42，旧E/R/Cr/Ci和count在monitor/candidate逐帧exact。原NS tracker更新、ordinary gain、原RES target及平滑照算；candidate在原post位置max(combined_gain_before,floor)，monitor只观测。原far/dt inactive reset保留。新增映射不读取near/window/路径标签、rpm、音量或未来通知，也不改变AEC/选择器或让候选反馈改变拟合输入。

## P3 测量合同、独立旧准入与预算

原46例×primary/selected×monitor/candidate=184次、505944帧。monitor四波形/control与D45 monitor逐byte同；candidate bypass exact。两模式原NS speech/noise、原RES路径及更新前/后模型状态exact；只有新floor及其派生保护计数、候选NS/final/AGC/VAD允许自然变化。与D45 monitor核旧FFT/EMA/noise/RES操作数投影，排floor及floor派生字段，明确不能要求新floor等旧floor。

原D42 observe/development_admission保持原字节、240窗口、固定160点OLA alignment及RMS计算。两臂各24near固定窗误差中位<=-3 dB且至少18改善；72no-near固定窗final RMS最大增量<=+1 dB；4pure-echo whole最大<=+1 dB。两臂全部满足才记DEVELOPMENT_CANDIDATE_ONLY，否则DEVELOPMENT_REJECTED；measurement/numeric/identity失败另记MEASUREMENT_INVALID_REPLAN。任何结论promotion_allowed=false/shipping_approved=false；新诊断字段不批准候选或替换声学裁判。

原power.csv的18字段保留其历史含义：q/echo_sum/residual_sum/innovation_sum等仍为过去统计，其中innovation_sum仍是R*(1-q)，不偷换为J。floor_mean、positive_floor/would_raise/post_would_raise、floor2_residual_sum仍报告实际新floor，后者明确仍乘过去R。末尾仅追加current_residual_sum=sum(P)、current_innovation_sum=sum(J)、prediction_overshoot_bins=count(J>P)，都在新valid集按bin升序double左折叠；empty集严格0。P/J是当前模型诊断，不能称独立near真值。

bins.csv保持原25字段及D43固定选帧全257bin；保存的更新前E/R/Cr/Ci/N和当前er/ei/rr/ri足以独立重建H/prediction/J/P/newfloor，不新增observer算法状态。无需重复保存可由这些操作数重建的字段。独立审计复算所保存每bin的全部新映射、原binary32组合gain、power汇总、mode/count/生命周期，分别报告固定snapshot覆盖；完整FFT/全帧bin/EMA/noise历史重建仍false，不能据快照冒称每bin每frame全审计。

原七输出repeat全量exact，future通知前1247帧前缀exact且4future不评分。独立全量回读184次输出、960组旧评分及原准入，不import新候选measurement helper，不DSP。RMS容差1e-10 dB、float字段exact、double汇总max(1e-24,1e-12*abs(expected))且expected0严格0保持；不得遇失败放宽。

预算保持单命令120 s、正式矩阵1800 s、独立全量审计1800 s；算法scoped22000 B、measurement_scoped<=65536 B且加D30 71224 B<=131072 B。状态/observer结构不增加，以实际sizeof验证；host局部不替代目标板栈/RSS/CPU/热功耗。单工件4MiB/root1536MiB/启动free>=3GiB不放宽；追加字段若超预算是测量缺陷，停止并保留失败，不删锁或改变限制。

正式根固定 `/tmp/audio-fe-device-current-innovation-d47-20261013`，必须不存在且无own/parent symlink；旧D45根/仓根/已存在新根提前拒绝并核完整manifest。每正式控制排他intent先于操作、终态receipt绑定source/command/输入；异常保存null/partial，不把观察超时当重启许可。只运行一次已审正式矩阵，unknown先同handle/actualstate对账，不覆盖或重放。

## P4 实施、边界、审查与退出

scope_write仅新D47 PLAN/PLAN_REVIEW/IMPLEMENTATION/RESULT/REVIEW/HANDOFF/AMENDMENT/CLOSEOUT，新C/header/NSfork、tools.codex_assets/device_current_innovation.py及对应test、最终README追加和排他/tmp控制。旧D0–46源、裁判、失败/快照、产品默认和运行配置只读。计划PASS后新task登记、CP1后实施；实施/定向验证与执行控制fresh独立PASS、source冻结后才能正式矩阵。

known answers覆盖：实数/负系数/正负虚系数复数预测；当前可预测echo得J0；新增创新；预测失配J>P与gain上限；P0/J正仍保留、当前echo0、旧E/R退化及warmup、N0和严格2N两侧/相等、非法count/NaN/Inf/中间溢出；observer-vs-NULL状态/输出exact、inactive reset和pastcount10合法；schema/派生投影/非法root/长度/gates/sentinel。非仓cwd help/dry-run真实验证。资源、输入起止hash、measurement failure、algorithm rejection分别报告。

最终README不作为新算法消费输入锁。D46历史247snapshot仅保持其原身份；若最终追加影响其中README，执行前先按精确ac998973新版身份排他保存完整字节和显式映射，经独立回读成功后才追加。原D46 snapshot、625af26c更旧备份及本轮domain source/input locks不改，禁止任意漂移fallback。当前README独立进入D47最终snapshot；不能宣称旧247路径永远匹配当前追加版。

claimant=root，verifier=device_capture_independent_review。required_evidence=plan/result/review，open_items3，success criterion=device-d47-current-innovation-verified，预算仅本地控制，不缩小总体目标。流程为计划→实施→定向/负例→唯一正式矩阵→独立全量审计→whole review→快照/文档/Runtime final→终态独立附核。旧拒绝保留；若原准入失败，停止该映射系数搜索，下一结构假设须新身份和独立冻结，不能只优化最坏短尾。

Provider route unresolved/zero-hit，知识NEEDS_REVIEW，无耐久归档成功。AISpeech固定点256/QIVW、真人/KWS/ASR、目标板/HIL/E001/至少72小时Product Certification和第三方rights分别验收。不commit/push/PR/merge/release/设备写；本轮里程碑不完成总体native目标。
