# D46 保护释放与路径失配的冻结时序归因计划

2026-10-12，experiment=FE_DEVICE_RELEASE_PATH_ATTRIBUTION_D46，kind=measurement-only，primary=adk-planning-execution-loop。总体目标“全面推进优化迭代”保持active。D45已收口且候选拒绝；D46先建立可独立复算的时序归因，不能把单例尾部线索直接写成算法修复或根因结论。本计划尚未实施或正式执行，独立审查通过后登记新task再实施。

## P1 已验证基线与新输入

D45唯一184次/505944帧、960新波形及原准入已独立审计PASS，候选DEVELOPMENT_REJECTED。D45 root=/tmp/audio-fe-device-post-ns-protection-d45-20261011，result=`0d9dbf01b21510216df648d323c501166a039a5b45d44c93d2699b8eabc4e8de`，binding=`bb0fbb8b9942e2b9ca5dbecf9a53ac1f13f38d40c7bbb574d5a438506d00cff8`。47项snapshot=`a19d6269921530b6d8890dfa4eded1340a7d9e86c1991376f9ba035a6eae21cc`，本轮恢复实际回读全部相同；CLOSEOUT=`ea6556b133296c9ca296d3f9f205930ca0f5bf0fcbe0542a5aae7d711014608f`。同thread D45 local task3797b68c76503f291e58538c已completed/open0/CP5verified，但总体native goal active。

冻结来源D25 C=`079c0bc34b605d855ce728cceeb8656204cbf86192bdeaa48724454a9e4eaeab`，Python=`26f28c5cf83fe5882d18bd2b86c7c2670b26494c20131c98556cb7c9567e02a0`。代码明确ABA仅在原样本[160000,192000)切到B再回A，合成near区间为frame[1000,1200)与[1600,1800)，echo条件near为0。这些标签只用于离线归因，禁止馈入算法。

实际只读intake probe chunkfc0fd6，对所有24个candidate/monitor return配对、168个固定分段检查NS差异与真实power计数，没有DSP或写入。固定A纯回声whole正式增幅约+.120/+.167 dB，ABA约+1.254/+1.255（primary）及+2.080/+2.114（selected）。ABA-r20纯回声frame[1210,1600)两臂375/377帧实际raised，差异能量约.253777/.476540；不是仅释放前10帧。近端例在该后续区间也有差异；先前单例50帧窗后40帧为0不能外推整个后续时段。本probe是development intake，不能冒称正式D46或独立已核验。

问题：保护差异在初始适配、B路径期间、回A后的短尾及较长后续时段如何分布？合成near与纯echo的模式是否足以区分短暂释放问题和路径失配误保护？不提出唯一根因，不仅修最坏窗，不搜索任何系数。

fresh localHEAD=`572b0e34a8a8e5663397ce16e378209ba9058d4d`，main=`c1b91e5086b0f8a3e82dc35506de4bcc1be58942`，required summary success、fast-docs skipped。#657 OPEN updated2026-10-12T06:16:12Z；open PR729/717/714/708/695。沿用既有dirty，不追随远端覆写本地冻结实验；执行前再次核远端检查及工件身份。Provider debug查询route unresolved/zero-hit，知识NEEDS_REVIEW，未持久化成功。

## P2 测量合同与数据角色

只消费D45所有非future的return来源：2个path shape×2个reference offset×3个condition×2个arm，24个candidate/monitor配对。明确排除field、repeat及future，原因是本轮专门诊断有冻结路径/near标签的return对照；不声称覆盖整批设备录音或重新完成D45全量测量。每臂必须2000帧/320000样本，配对集合和模式严格唯一一致。

原frame区间固定为[0,1000)、[1000,1200)、[1200,1210)、[1210,1600)、[1600,1800)、[1800,1810)、[1810,2000)。共168个pair-segment，各自对NS和final计算，336个stage测量。10帧只是已有释放定位的分解坐标，不是算法窗口、暖机调参或准入新增门槛。所有区间合起来覆盖原whole可对齐范围，禁止按结果重新切窗。

原input[a*160,b*160)按D45既有alignment160对应output[a*160+160,min(b*160+160,320000))。最后一段截去input末尾160样本；整段有效样本319840。首输出160样本不评分，无tail flush。报告每段原input range、实际截断后的input range、output range、样本数及tail截断数，避免把原坐标伪写为截断后坐标。

float32le显式解码并验证长度/finite；顺序float64左折叠计算candidate_energy=sum(c*c)、monitor_energy=sum(m*m)、difference_energy=sum((c-m)^2)、energy_delta=candidate_energy-monitor_energy及两边peak。可报告能量比dB仅作诊断：正能量用10log10(candidate/monitor)，任一严格0则null并给zero标志，不伪造epsilon能量。分段统计不是原准入分数，不能改写D45 decision。整段统计另直接从whole有效样本重算；分段能量求和与whole比较仅用max(1e-24,1e-12*abs(expected))，strict0保持。不得放宽源float32或独立差异能量0要求。

每配对读取两份power.csv，必须18字段、2000个顺序frame、有限合法值及frame/far/dt/count/旧统计投影保持；两模式仅actual raised允许不同，monitor actual0、candidate actual=post_would_raise。每段报告真实raised帧数、raised bin总数、positive floor帧/bin总数。power原帧坐标与对齐波形坐标分别标注；FFT/OLA意味着不能逐帧宣称两者一一因果对应。

数据角色保持development-and-synthetic-engineering，所有24配对和固定168分段完整报告。标签用于离线分组，不选新候选；无blind/validation-grade宣称。measurement_only=true、algorithm_changed=false、promotion_allowed=false、shipping_approved=false；正式出口为MEASUREMENT_VALID_ATTRIBUTION_ONLY，来源/算术/覆盖/安全失败另记失败与partial，不把测量失败当声学拒绝。

## P3 实施、验证与独立审查

新Python工具进tools.codex_assets/device_release_path_attribution.py，测试在tests/validation/frontend_evolution/test_device_release_path_attribution.py；纯标准库，不importD45测量helper、优化器或DSP，不重新执行AEC/NS/AGC/VAD，不新增第三方资产。

所有读取文件绑定D45 binding相应artifact SHA，result/binding/snapshot/CLOSEOUT/D25源显式pins；实际消费的96份PCM和48份power共144输入文件，另绑定计划/审查/工具/测试等。开始与结束SHA一致，D45快照原47文件保持。新root=/tmp/audio-fe-device-release-path-attribution-d46-20261012，不存在才可写；既有root、外部root、own/parent symlink提前拒绝。排他intent/receipt，新未知先核actualstate，不覆盖或重放。

单次formal测量预算180 s，独立只读重算180 s；每输入不超过4 MiB、新root不超过16 MiB、每输出不超过4 MiB，启动free>=512 MiB。预算用于新离线分析，不修改旧DSP、矩阵或审计预算。宿主资源不替代目标板性能。

定向known answers涵盖frame160对齐首部/尾部截断、7段完整覆盖、float32le与finite/长度、正/零能量/峰值/差异、严格零与分段sum容差、真实power mode投影/actual计数、重复/缺失/错误case集合、既有/外部/symlink root拒绝且sentinel保留。非仓cwd help/dry-run真实验证；dry-run不写、不DSP。先工具及控制独立审查，冻结源码，再唯一formal。

独立审计不import新helper、不执行DSP，从同冻结PCM/power自行解码并计算全部24对/168段/336stage及whole，核坐标/样本数/finite/zero/容差、模式投影和全部实际输入起止锁。独立测量与正式结果只按冻结容差核一致；不证明原FFT、完整噪声历史、near识别或唯一根因。源码/结果whole review、文档一致性、快照及真实Runtime final收口分别记录。

## P4 边界与退出

scope_write仅新D46 PLAN/PLAN_REVIEW/AMENDMENT（如需）/IMPLEMENTATION/RESULT/REVIEW/HANDOFF/CLOSEOUT、新tool/test、最终README追加及排他/tmp控制回执。禁止改D0–45源、裁判、失败、快照、产品默认、运行配置或设备。冻结计划通过前不正式实施；新task登记后按checkpoint推进。至少3个open items，required evidence plan/result/review；无commit/push/PR/merge/release/设备写。

完整正式测量及独立审计通过才收口本D46诊断里程碑；任何算法候选仍须另建实验身份及独立冻结原全量准入。若归因显示无法只解决尾部，则明确保存该证据而不强行推出候选。未来研究方向必须同时解释纯回声与近端后续保护，避免已有负结果循环。

claimant=root，verifier=device_capture_independent_review。stop_condition=实际验证通过后本地里程碑收口，或来源/测量缺陷replan/abort；unknown操作只对账。总体native目标不因本诊断阶段完成。真人声学、AISpeech产品链、目标板/HIL/PQ与shipping仍待各自真实证据。
