# D49 当前预测残差幅度下界保护冻结计划

2026-10-15，experiment=FE_DEVICE_MAGNITUDE_LOWER_BOUND_D49，kind=first-party structural algorithm experiment，primary=adk-planning-execution-loop。总体目标“全面推进优化迭代”保持active。前轮D48已真实完成测量合同修复、独立全量审计、整批回读和本地收口；本轮先冻结新假设并独立计划审查，再登记新逻辑任务/CP1后实施。本文件不是实施或执行证据。

## P1 基线、已知失败与唯一假设

D48测量结论MEASUREMENT_CONTRACT_VERIFIED_NO_PROMOTION，固定D47算法原开发准入两臂accepted=false：24near误差中位约-5.5495dB、20/24改善；72no-near最大+16.872746384480372dB，4pureecho whole最大primary+2.3946506830306262/selected+2.7978050756589425dB。近端收益未覆盖无near/纯echo退化，不在原映射上搜索系数。

冻结D48 result=d8c80ee2c612fccd62de1bae86bf107e71062e95c1609cddf7abe5714992a6cf；binding=5f8fa795e386e32c83743f66ffdc1361bf48cc00705f13f11efa7238c0d3e9ff；独立数值audit=a583e4d2097b298f6c57f1833b8a4521dbbe328bd0f146d62cd40545563060a9；whole-v2=288482d7954f45e46d3be0ff6f31d1f988257e87719fa04b0f474956a4db546b；final snapshot=ad1482fce4bf777f65cea0d13c46f58fb7799c6247366e80a349f1d48f6db131，13671项身份。D48 final gate receipt=e1405f5a98cb22f01bd362b8bc72eff57bb556ffbadbf38cfae77aa765d07838、终态status receipt=000a4f17267846d5320715980a9960ca3bdcf27162206c466669ff319d42bc79；本地task-fe8e96504fd58d9d71dd496b已completed于2026-10-15T14:56:17.053799Z/open0/CP9 verified/events834，经独立实际附核。旧whole-v1 exit124及内部receipt缺失、旧D47测量耦合失败保持，不重放或改写。

当前冻结D47 header的源码定义：更新前复数拟合H=(Cr+iCi)/E，当前预测p=H*echo，当前残差r，P=|r|²，J=|r-p|²，旧保护严格J>2N后sqrt(clamp(J/P,0,1))。当预测失配导致J>P时，保护可能饱和为1；这不证明J是近端语音，亦未证明该机制是全部退化的唯一根因。

新假设仅改变保护量：使用预测残差幅度下界 L=max(sqrt(P)-hypot(pr,pi),0)² 替代J进入保护门控及归一化。由反三角不等式，实数精确运算下0<=L<=|r-p|²且L<=P；这是相对于模型预测的残差下界，不是相对于真实echo的近端真值下界。若预测幅度已不小于观测幅度，L=0，避免仅由预测方向/过大幅度造成的创新保护；若模型低估实际echo，L仍可为正而误保护。近端叠加发生相消时也可能被漏保。是否守住原near/no-near全部条件只由新波形和独立原准入决定，不预设成功或性能收益。

## P2 固定映射、时序与数值

原valid条件、count10 warmup、更新前double E/R/Cr/Ci、旧float noise转double N、当前FFT float er/ei/rr/ri全部保持。先按原有序double计算H、pr/pi、原P/J并核所有中间finite，保留P0/J正、J>P与raw overshoot语义；不因新保护关闭改model valid。

固定binary64操作顺序：rmag=sqrt(P)；pmag=hypot(pr,pi)（同一libm double hypot）；d=rmag-pmag；若d>0则L=d*d，否则L=0。所有新值须finite且非负；不加epsilon、不截系数、不放宽数值容差，真实溢出作为measurement-invalid保留。hypot避免直接计算预测平方和的额外中间溢出；独立审计以显式libm接口和相同规定顺序复算，不用不明精度的近似替代。

仅P>1e-12且严格L>2.0*N时 floor=(float)sqrt(clamp(L/P,0,1))，否则floor0。原2N数值、严格比较、P门槛及float cast保持；唯一结构变化是保护估计量J→L，门控与归一化必须同时使用该同一量，不拆成参数试验。count<10或E/R退化仍valid0/floor0；有效模型P0/J正仍valid1、L0/floor0；原J原样保留作诊断。

floor仍在旧EMA/noise状态更新之前算；.8/.2 EMA、far/dt/reset、原NS tracker、RES target/平滑、post-NS max位置、FFT/OLA/AGC/VAD全部保持。monitor只观测、candidate只在原post位置应用floor；拟合输入不受候选反馈。在线不读near/window/路径标签、rpm、音量、未来通知，不新增gate/smoothing、lag或频带搜索。

数学L<=J/P的关系不能直接升级为浮点逐位跨算法单调约束或声学输出单调保证；不重复D47把算法专有性质塞入通用observe的缺陷。主验收为规定操作数的独立数值复算和原声学准入。新double sqrt/hypot可能增加计算成本，host预算通过不代表目标板CPU/实时性通过；没有板端证据时保持unknown。

## P3 数据、测量合同与独立准入

仍使用D30原46来源、184路/505944帧：32已看field、12合成return及repeat/future，development-and-synthetic-engineering/adaptive reuse；repeat不独立，4future不评分。80/100仅用户确认音量，运动/物理mic/真人标签不足保持unknown，不把field当有近端真值。

新preflight先literal pin冻结D48 tool/test、D47 C/NS/header、D48 result/binding/snapshot及真实closeout链，再读完整继承依赖。保留原D48的11744输入，合并其全部1884工件、D48最终13671快照完整映射和本轮新增源/计划/审查/实施；同路径不同SHA拒绝，不删旧domain或语义校验。D48最终README版本0f4c9163825021798fd655bcdab6f20f0c2e9825aca0c145d24155980ae9295f若将来追加，必须先精确完整字节另存新显式映射；原ac998及更旧625af备份不覆写。

monitor四输出与D48 monitor byteexact，candidate bypass exact；两臂、两模式原普通NS/RES/过去状态及current P/J/overshoot原义保持，仅实际floor派生字段和候选自然下游可变。power保持原18历史字段+3 current字段：历史innovation_sum仍R*(1-q)，current_innovation_sum仍原J，不偷换L；snapshot原25字段已包含重建H/p/L所需全部操作数，不新增测量列来选择候选。保护量L由固定snapshot独立导出，完整FFT/全帧bin/EMA/noise历史重建仍false。

采用冻结D48通用observe与原D42 development_admission，保留960组whole/fixed评分、160点OLA alignment、原D39比较对象和全部窗口；D48历史floor诊断仍准确单列，不进入准入。两臂分别要求24near误差中位<=-3dB且至少18改善；72no-near固定窗final最大增量<=+1dB；4pureecho whole最大<=+1dB，全部共同满足才DEVELOPMENT_CANDIDATE_ONLY，否则DEVELOPMENT_REJECTED。算法rejection、measurement-invalid和工具/身份失败分别保存；任何结果promotion_allowed=false/shipping_approved=false，不得以局部变好或更保守映射批准候选。

独立审计不import生产measurement helper、不DSP，复算960组、原准入、AGC/VAD binary32、snapshot的原H/P/J与新L/floor/postmax、全帧状态/历史诊断、七输出repeat全量和通知前1247帧future前缀。RMS容差1e-10dB、float exact、double汇总max(1e-24,1e-12*abs(expected))、expected0严格0均保持。原D48 baseline decision为MEASUREMENT_CONTRACT_VERIFIED_NO_PROMOTION而非算法DEVELOPMENT_REJECTED；新控制须核这一真实身份及其accepted=false，不假设旧D45 decision文本适用于新基线。

## P4 验证、预算与退出

主C known answers必须独立给定：完全可预测echo、预测幅度相等而方向反转/正负虚旋转得到L0但原J可大、预测幅度超过当前得到L0并保留rawJ/P0、预测幅度小于当前的确定幅度差、echo0、P0/J正、warmup/退化、N0、严格2N相等及相邻double两侧、NaN/Inf/中间溢出。observer-vs-NULL状态/输出exact、inactive reset/pastcount10合法、pre-update-noise、原NS统计、schema/模式/坐标/非法argc/gates/root/sentinel及非仓cwd help/deepdry保持。新公式fixture不能使用真实案例调参或新near标签。

单命令120秒、正式矩阵1800秒、独立全量审计1800秒、整批机械回读180秒；scoped22000B、observer26728B、measurement<=65536B且加D30 71224B<=131072B，单工件4MiB/root1536MiB/启动free>=3GiB保持。新算法不新增持久状态，栈/CPU/板资源不凭sizeof推断。完整source/input起止hash、排他intent与terminal receipt、源/命令/输入身份绑定保持，unknown先同handle/实际状态对账，不重启。成功旧C/audit/DSP/whole/selftest不为收口重跑；新正式编译/自检仅为新结果绑定身份。

新正式根仅 `/tmp/audio-fe-device-magnitude-lower-bound-d49-20261015`，必须不存在且无own/parent symlink；旧根/仓根/已存在新根先拒绝。算法/helper/测试/独立执行控制通过fresh审查并冻结IMPLEMENTATION后，唯一正式矩阵；真实终态后独立全量审计，再whole/snapshot/本地收口。若原准入失败，停止本映射系数搜索，下一结构假设新身份；不只围绕最坏短尾或某个窗口优化。

scope_write只允许新D49 PLAN/PLAN_REVIEW/IMPLEMENTATION/RESULT/REVIEW/HANDOFF/AMENDMENT/CLOSEOUT、新C/NS/header fork、tools.codex_assets新helper及测试、排他/tmp控制和最终README追加。D0–48源/结果/失败/裁判/root/快照只读，产品默认/API/ABI/第三方库/运行配置/设备不改。claimant=root，verifier=device_capture_independent_review；本轮required_evidence=plan/result/review，open3，success=device-d49-magnitude-lower-bound-verified。先计划独立PASS再新任务登记/CP1，不能把计划或归档建议当实施证据。

当前localHEAD572b0e34a8a8e5663397ce16e378209ba9058d4d，保留既有dirty。fresh main6fafcc868c5d3a0c4aa328e3d6ab54109cf5a741，68checks=67success+1skip，summarysuccess；open PR714/625c059de6066db73223ed5d90ecd69aa1ed0c2a、695/5dfe8d9146a70ddc7ff4465e0440b64a04b192e4，#657 OPEN。最新3artifact11983680073/11983530061/11983210367属于main，非本轮证据。Provider WORKSPACE_UNBOUND/route unresolved保持NEEDS_REVIEW，无归档成功，不猜主体；无commit/push/PR/merge/release/设备写。AISpeech固定点256/QIVW、真人ASR/KWS、HIL/E001与至少72小时PQ继续分别验收，总体native目标不因本阶段完成而完成。
