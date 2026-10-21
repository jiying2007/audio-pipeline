# D44 绝对创新功率门控实测结果

2026-10-11，experiment=FE_DEVICE_INNOVATION_NOISE_GATE_D44。唯一正式矩阵和首次独立全量审计已实际完成，decision=DEVELOPMENT_REJECTED。测量有效，候选效果未通过冻结准入；promotion_allowed=false、shipping_approved=false。总体“全面推进优化迭代”保持 active；整批文档审查及本地收口另列。

## 冻结因果修改与原准入

在原 active、旧 count>=10、旧 E/R>1e-12 条件下，使用旧 E/R/Cr/Ci 计算 double q 并有限性校验、截断到 [0,1]；取原 NS 上一帧 float 噪声估计并转换为 double N。I=R*(1-q)，只有严格 I>2*N 才给出 float sqrt(1-q)，否则 floor=0。valid 不因门控关闭变为 0。monitor 观测真实新 floor，candidate 以 max(original_target,floor) 抬升 target。原 EMA、噪声更新、FFT、NS、AGC、VAD、门控、频域 RES 开关与平滑保持。

冻结 PLAN、AMENDMENT 和 PLAN_REVIEW 保持原字节。monitor 四原输出 bypass/ns/final/control 与 D43 exact；protection 仅排真实新 floor_mean，其他旧状态投影 exact。candidate bypass exact，其余波形真实新算。旧 diagnostic innovation/excess/noise_dominant 含义保持，actual floor²R 不冒充旧 excess。

原准入要求两处理臂分别满足：24 个 near 窗配对误差中位<=-3 dB，至少18窗改善；72个 no-near 固定窗最大能量增量<=+1 dB；4个 pure-echo whole 最大增量<=+1 dB。窗口、原样本坐标、160点 alignment、repeat/future角色均保持，未为通过而改判。

| 原准入统计 | primary | selected | 结论 |
| --- | --- | --- | --- |
| near 配对误差中位 dB | -1.8387263771003113 | -1.8387263772565845 | 两臂未达 -3 |
| near 改善窗数 | 20/24 | 20/24 | 达到18要求 |
| no-near 最大能量增量 dB | +1.0888155893465665 | +1.557993736663029 | 两臂超过+1 |
| pure-echo whole 最大增量 dB | +.40267284273216575 | +.649708484103023 | 两臂通过+1上限 |

相较 D42，no-near 最大增量从约3.71 dB降低，但 near 中位改善从约2.18 dB减为约1.84 dB；该局部变化不能批准整体候选。本固定2.0门控规则停止系数搜索，保留拒绝。

## 正式执行和真实回执

目录 `/tmp/audio-fe-device-innovation-noise-gate-d44-20261011`。唯一正式 session 74128 terminal exit 0；执行器517.5497677167878 s，矩阵448.5976265370846 s。46来源例×两臂×两模式=184次处理、505944帧；190条command含6条编译/自测/负例，不是190次DSP。7935来源锁，1884工件，加 binding 共1885文件，无 measurement-invalid.json。

| 工件或回执 | SHA256 |
| --- | --- |
| result.json | `ba7d97c484e4e1315f019415d33e11f1228e72119db46d3b2595f970e78155be` |
| binding.json | `3edd5471650e97700c5e51b1a86bdda46f0500881473e7224c1163e854590f6a` |
| `/tmp/audio-device-d44-execute-v1.json` | `3bcb2e57e96e4253d5607035679cd84cdfd1f5405d28181c9a37a25bbe3db67e` |
| `/tmp/audio-device-d44-negative-v1.json` | `5232b82700a46b96677ba3af4bcaa70375ed4f8c25e8487580405846f41726ab` |
| `/tmp/audio-device-d44-independent-audit-v1.json` | `7b2c0fbf5fe6ef1a0ca1e2cd827483c9c68edebad10ba675e661e202d3a4d68a` |

根保护 session45916 terminal0，15.386029498651624 s；D30/仓库/D44三个既有根请求各exit2，完整manifest前后相同。当时文件数679/2575/1885，不要求新增文档后仓库仍2575。

原算法 scoped 22000 B、observer 22616 B、测量合计44616 B；加D30原71224 B为115840 B，满足131072 B预算。最大文件2453673 B、根合计1439779159 B，满足4 MiB/1536 MiB预算。正式前 /tmp 空闲15591510016 B；单command120 s、矩阵1800 s保持。这些是宿主测量证据，不是目标板峰值内存、CPU、功耗或热资格。

## 独立全量审计

独立脚本 `/tmp/audio-device-d44-independent-audit-v1.py` SHA256=`7a46399583d9f193b6030f1235ffff4092dfe4347278543d7bae1fae1f7b82d9`，标准库加系统libm，不import项目helper、不执行DSP。自测首次exit0。首次实际审计session59897 terminal0，844.4431319795549 s；Spec/Quality/Reviewer Independence PASS，unresolved=0，独立确认同一拒绝结论。独立只读审计1200 s预算没有放宽DSP或矩阵预算。

全505944帧schema/count/range、7568快照/1944976 bin、60544汇总、34590严格零、564 inactive旧非零count检查通过。最大汇总绝对误差5.115907697472721e-13、相对误差2.7722744706560435e-15，未用double汇总容差放宽float逐位要求。

460项原输出byteexact（monitor四输出×92加candidate bypass×92）、252972 mode power投影、972488 mode bin投影、28重复文件及28未来前缀通过；9824起止锁一致。独立新算全部960组波形测量及D39差值：5760阶段统计、2592已知near统计；505944帧AGC/VAD和80951040个输出样本binary32 exact，RMS dB误差最大0，原1e-10容差保持。D44新波形评分没有继承旧候选分数。

覆盖固定快照保存操作数和全帧schema，full FFT、非快照逐bin算术、完整EMA及噪声历史独立重建均false。near是真实消费的离线合成非零样本；field没有独立near真值；future4不评分，repeat不增加独立样本。不能推导真人听感、ASR/KWS、真实motor声学、目标板/HIL/PQ或shipping资格。

## 状态边界与后续

恢复时fresh远端main已变为 `5cdf7cac5814b3ae990fec48465b2c7da2e39f03`，首批68项check为67success/1skip，required summary success；#657仍OPEN，updated2026-10-11T13:56:54Z，其body中main字段为历史70aeb4快照。开放PR为724/717/714/708/695；最新工件11705450921/11705407049/11705401151未过期，绑定其他PR head，不能代替D44证据。后续收口再按实际远端状态核验。未修改本地冻结实验基线以追随远端。

维护v2 request_ms=1791729194596，真实回执ACCEPTED_COMPLETION_UNVERIFIED，120.42880736198276 s；恢复时进程已不存在，当前Runtime maintenance.required=false，允许继续业务。保留不确定完成状态，不重发，不将自动压缩归因本请求。

Provider route unresolved，知识NEEDS_REVIEW，未声明归档成功。AISpeech固定点256/QIVW产品链路与本160点float研究分别验收。无commit/push/PR/merge/release/设备写。后续新假设须新实验身份及独立计划审查，不通过本规则参数搜索或事后选窗获得通过。
