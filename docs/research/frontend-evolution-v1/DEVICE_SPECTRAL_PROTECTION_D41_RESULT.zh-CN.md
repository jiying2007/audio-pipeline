# D41 因果频带创新保护结果

2026-10-11，experiment=FE_DEVICE_SPECTRAL_PROTECTION_D41。唯一正式矩阵和首次独立全量审计均真实完成，工程测量通过，固定开发准入结果为 SPECTRAL_PROTECTION_DEVELOPMENT_REJECTED。whole review与本地Runtime收口分别核验，不把测量PASS写成候选批准。总体目标“全面推进优化迭代”继续 active。

## 结果和解释

D41只在原频域RES每bin target上加入由过去帧复数交叉谱EMA计算的创新gain下限。monitor关闭新保护，candidate启用下限；原AEC/Activity、ordinary NS、AGC/VAD及频域RES开关保持。没有near标签输入、阈值寻优或反馈AEC。该创新量尚不能可靠区分near、路径失配及其他非相干残余。

| 冻结开发准入 | primary | selected | 门槛与结果 |
| --- | --- | --- | --- |
| 24个含near固定窗口，final已知near配对误差中位 D41-D39 | -5.150823954 dB | -5.150823955 dB | <=-3 dB，满足 |
| 含near严格改善窗口 | 20/24 | 20/24 | >=18/24，满足 |
| 72个无near固定窗口，final能量增加最大值 | +16.590692197 dB | +16.590692197 dB | 每个<=1 dB，失败 |
| 四个纯echo整例，final能量增加最大值 | +2.173229320 dB | +2.108026504 dB | 每个<=1 dB，失败 |

两臂均拒绝，不能以含near收益覆盖纯回声代价。72个无near固定窗口全部增加能量，中位 +14.105056932 dB，范围 +0.549279440 至 +16.590692197 dB。D41 final对bypass仍有中位 -7.803232075 dB抑制；这是冻结合成工程测量，不是现场ERLE。

含near的final对bypass误差中位仍为 +4.054722099/+4.054722098 dB，两臂各16/24高于bypass；本轮改善尚未消除下游代价。该批near窗口NS与final误差统计相同，不能把差值归因于AGC。所有中位均是逐窗配对差值的中位，不用两组中位相减替代。

现场固定窗口每臂99组，含重复控制；candidate final能量 D41-D39中位均 +0.927009985 dB，各51/99增加，最大 +2.809053862 dB。现场没有已知near真值，能量增加不能直接写成语音改善或回声退化。repeat不作为新增独立样本，future不评分。

拒绝不限于路径切换或near后的恢复：primary静态A纯echo整例增加约0.718/0.768 dB，ABA纯echo整例增加约2.166/2.173 dB；静态A纯echo末段固定窗也可增加约16 dB。归一化创新比例直接变成gain下限，缺少绝对创新量与可解释残余来源约束；这是本轮结果支持的后续研究问题，不是已证明的唯一根因。后续先核低能量非相干残余与near的可辨识性，不继续扫描相近coherence阈值或放宽1 dB门槛。

## 执行与制品身份

唯一主wrapper `/tmp/audio-device-d41-execute.py`，session93203真实terminal exit0，elapsed_seconds=279.56960721872747。输出根 `/tmp/audio-fe-device-spectral-protection-d41-20261011`；46来源×两臂×两模式=184次新C执行、505944帧。旧D39/D40及AEC不重跑，D18原库不重编。

result SHA256=`38d6f5eab2e3c3f6c8d9bea66f267015f7f02cde5ce73e5f3db29d32c1e3ce47`；binding SHA256=`a61625805a15ac877724064c1777bd2681751b1398b4cb86f1d206d35160a35f`。3001个来源/依赖锁起止一致，binding记录1510个工件，binding自身另计。原D30/D39/D40身份保持。

monitor所有92个执行的四原输出逐byte复现D39；两模式ordinary NS speech_probability/noise_rms_dbfs恢复binary32后exact，gates/allow与bypass exact。原频域从未激活的16个field/arm，两模式四输出均复现D39。两模式保护observer除raised_bins外逐字段exact；五输出repeat全量相同，future前1247帧/CSV1248行相同。保护count使用上一帧状态、连续active十帧warmup、inactive清新增状态；它不是严格十帧滑动窗。

四个mode/arm分组各45whole+195fixed，共180whole+780fixed=960组；保留原160点坐标、tail/null/no-flush及D39同坐标差值。准入仅candidate每臂24near/72no-near固定窗和AMENDMENT明确的四个纯echowhole，不含field/repeat/future或含nearwhole。

## 验证与剩余边界

14项定向测试通过；strict C编译、真实known-answer自测、非仓cwd help/deepdry通过，46cases/3001locks/writesFalse。矩阵内非法argc/frames/mode/gates及既有sentinel保护通过。NS真实自测覆盖warmup和inactive污染状态清零，已知答案覆盖复数交叉谱、coherence边界及非有限拒绝；它们不替代全部实际频带EMA或NSFFT独立重算。

已有根负例session19895真实terminal0，D30/仓库/D41三个命令各exit2，完整文件manifest起止相同；回执 `/tmp/audio-device-d41-negative.json` SHA256=`541a5459121e9e9782443256b1ef77b074e04cc393d65b5d40528f4c1b62ceda`，18.83710180129856s。该次历史manifest计数分别679/2531/1511；后续新增文档不冒称该历史全仓manifest仍是当前总树身份。

描述摘要实际exit0，`/tmp/audio-device-d41-observations.json` SHA256=`fbe2f7d1f161f9ebe60fc01a51bf8701bc841064731004112a3b98a73860ceb8`，80组摘要、四mode/arm分组，未反馈算法或准入。独立描述审计首次真实exit0，0.984058303758502s，80组summary exact、384个near标签按原轨迹核对；回执 `/tmp/audio-device-d41-observation-audit.json` SHA256=`6257806818f9b8389054da1d007ea5ef5371d654f331af2374dbcc93223c978f`。摘要核验不替代下面的全量波形复算。

独立全量audit `/tmp/audio-device-d41-independent-audit.py` SHA256=`9246e33722ba66e9b4f097dc2ca12a82d157515ff015a86d543473e4a90b332c`，唯一首次session52581真实terminal exit0/PASS、retry0，491.47727013379335s。回执 `/tmp/audio-device-d41-independent-audit.json` SHA256=`93ee3a4a26426bc65db01802d5b370e23dfd249abe0f77ced4fade56b90200fe`。独立实现不import新测量helper、不执行DSP，实际核184执行/505944帧/552条PCM/80951040个AGC输出sample，AGC/VAD binary32 exact；960测量组/2880stage统计/1296已知near统计/960组D39同坐标差值全复算，最大RMS误差0 dB。4512个合并来源/输入/工件路径起止锁相等；monitor92个四原输出复现D39，64个两模式inactive控制相同，505944帧普通NS统计exact，92个observer配对及五输出repeat/future前缀通过，四个future不评分。

独立审计按实际near波形判标签，分别重算每candidatearm的24/72/4集合和准入；最终拒绝与主结果精确相同。全部实际bin EMA及NSFFT未独立重算，回执两个覆盖字段明确false；known-answer、monitor等价和汇总trace合法性不扩大成该全量资格或真人/设备资格。

实际sizeof下游scoped22000 B，加D30原71224 B为93224 B，满足本实验65536/131072 B预算；新增状态已计入。原B0 50000 B保持未满足；该值不是完整SDK/整线程或目标板RAM资格。CPU、功耗、热、真人音质/识别率与AISpeech固定点/QIVW集成分别待证。

promotion_allowed=false、shipping_approved=false。Provider当前route unresolved、零命中且仅reviewing回退记录，知识NEEDS_REVIEW；未声明归档成功。无commit/push/PR/merge/release/设备写。
