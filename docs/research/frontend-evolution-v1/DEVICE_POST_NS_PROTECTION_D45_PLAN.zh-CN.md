# D45 NS与RES合成增益后的创新保护计划

2026-10-11，experiment=FE_DEVICE_POST_NS_PROTECTION_D45，kind=first-party structural algorithm experiment。goal_statement=全面推进优化迭代，primary=adk-planning-execution-loop。本计划冻结新实验的唯一因果映射，尚未实现或执行；独立计划审查通过后才实施。D0–D44历史结果及拒绝保持；promotion_allowed=false、shipping_approved=false。

## P1 证据、假设与冻结基线

D44已真实收口，候选DEVELOPMENT_REJECTED：两臂near配对误差中位约-1.839 dB未达-3 dB，no-near最大约+1.089/+1.558 dB超过+1 dB。正式184次/505944帧及960组新波形评分已由首次独立审计复算。本轮实际重新回读35项snapshot全部相同：snapshot SHA256=`0cf2c83f9c556416d464a765c6d86806d4aa161d8539a6afcc5719f349b2aea5`；D44 CLOSEOUT=`c6397cffae756f628d398bfd1f705ba8ca7db752b0509dba5b9413d638d2631d`；result/binding=`ba7d97c484e4e1315f019415d33e11f1228e72119db46d3b2595f970e78155be` / `3edd5471650e97700c5e51b1a86bdda46f0500881473e7224c1163e854590f6a`。

实际只读全部960组D44已有统计：567组NS/final阶段统计相同；全部216组合成candidate的NS与final配对变化相同。因此这批合成候选的工程代价不能归给AGC。该检查仅核已有已独立审计的字段，不是新声学评分或AGC消融。此前D39也明确含near窗final与NS变化相同。

源码 `device_innovation_ns_d44.c` SHA256=`eec670092988145e01d473c55b71d049c9e282ba90c37f755e8c897063aa8045` 显示：floor仅抬升频域RES target，随后实际频谱gain仍为ordinary_ns_gain*res_gain。假设：保护下限被普通NS因子再次压低可能限制近端收益。D45将同一D44 floor从RES target移到NS与RES合成后的频谱gain，检验这套位置改变是否同时满足原near/no-near准入。不能据代码乘法或上述相关性宣称已证明唯一根因。

这是开发数据启发的新结构假设，不是D44固定门控系数搜索，不搜索2.0、warmup、EMA或任何其他参数。明确风险是保护更多噪声/非线性echo、增益突变及扩大no-near能量；任一原准入失败保存拒绝。无新第三方源码、系数、模型、权重或数据。

保留D30的46冻结来源、D18原库/build defines/FFT/NS tracker/AGC/VAD、D39原比较对象、D42原observe/admission及全部D43/D44来源/工件/snapshot/CLOSEOUT身份。旧snapshot里的README是当时绑定；当前README SHA=`041467cf41d6a622a3cdc0990e2e2a49154ee3046a8f6d9915d356435709784b`，直到本轮结果追加前不覆写旧snapshot。

本轮fresh localHEAD=`572b0e34a8a8e5663397ce16e378209ba9058d4d`，main=`ef1fb54cdd326c280c30889646a3592c17c10d50`；65check中63success/1skip/1frontend-spatial in_progress，required summary尚未出现，不能继承上一main的green。#657 OPEN、updated2026-10-11T13:56:54Z，body中的70aeb4是历史快照。开放PR717/714/708/695，当前heads分别79f1f2d4fc27939fbbe70e6e425267d7e0298b33 / a1ce91c432f092180ed8e8cdd69db751218eb170 / 9c45aec010457d9ef7b1355fc2a0b22a480cf0e3 / 61f195075fe31da45413db33f2390d791aef00df；工件11706660335/11706645496/11706645329未过期，分别绑定PR714/main/PR714，不作D45执行证据。后续apply/执行前再次fresh读取。

Provider validation查询route unresolved/zero-hit，知识NEEDS_REVIEW，无归档成功。仍使用已查看development与离线合成near；field没有独立near真值，repeat不是独立新增样本，future不评分，不升级为validation-grade或blind。

## P2 唯一候选映射与生命周期

从冻结D44 NS fork派生新D45符号，唯一算法变化是保护下限的应用位置。保留D44 q/floor函数：旧E/R/Cr/Ci/count及同读取阶段旧float noise转double N；count<10或E/R<=1e-12时valid0/floor0，有限性和range检查保持；q=clamp((Cr²+Ci²)/(E*R),0,1)，严格double I=R*(1-q)>2.0*N才给float sqrt(1-q)，否则floor0。valid不因门控关闭变0。原.8/.2 EMA、原noise更新、FFT、OLA和active/inactive reset保持，不增加算法跨帧状态，不读取near/窗口/运动/未来标签。

每bin按固定顺序：

1. 原current power、echo_power和FULL的beta=1.4f/res_floor=.10f原target照算；D45两模式都不再用floor抬升这个target。原.55/.45或.92/.08 binary32平滑仍执行，old_gain/res_gain保存原路径状态，active和inactive分支完全保持。
2. 原noise_tracker_update照算，保留更新后的float noise/speech；post=power/(noise+1e-12f)，ordinary gain为post>1时sqrtf((post-1)/post)，否则0，clamp到原floor_gain=.12f至1后乘原res_gain。原SAFE加.06f/clamp分支保持，正式模式固定FULL。
3. 保存上述结果为combined_gain_before；只有freq_res active且candidate且floor>combined_gain_before时设置gain=floor并计actual raised_bins；其他条件gain不变。monitor只观测不抬升。保存combined_gain_after后，用该gain乘正频谱及镜像频谱，再按原IFFT/OLA输出。
4. 原下游controlled AGC和VAD保持，允许输出变化自然传播，不重置下游，不重跑AEC/时域RES，不改变原far/dt/enable_frequency_res=1。

所有float操作逐步binary32，ffp-contract=off、IEEE width、FLT_EVAL_METHOD=0及little-endian保持；double顺序保持D44。将旧保护撤离RES target再移到最终频谱gain是一个完整因果映射，不分别把两步当独立收益。新规则不附加平滑、迟滞、band mask、权重或系数搜索。

## P3 测量、数值、准入与预算

仍46例×primary/selected×monitor/candidate=184次/505944帧。D45 monitor原bypass/ns/final/control四输出与D44同名monitor byteexact；candidate bypass exact。原NS speech/noise汇总与monitor exact，residual_echo_gain与monitor原RES路径exact，AGC/VAD其余字段按实际新波形检查。候选输出真实重新评分，不继承D44候选分数。

原D42 observe/development_admission不改任何字节、窗口、alignment、RMS或门槛：两臂各24near固定窗误差配对中位<=-3 dB且至少18改善；72no-near固定窗final RMS最大增量<=+1 dB；4pure-echo whole最大<=+1 dB。两臂均满足才记录DEVELOPMENT_CANDIDATE_ONLY，否则DEVELOPMENT_REJECTED；都不晋升shipping。identity/numeric/measurement失败另记MEASUREMENT_INVALID_REPLAN，不冒充声学失败。

原power.csv 17字段保持，并末尾追加post_would_raise_bins：全bin在freq_res时floor>combined_gain_before的计数，两模式都真实测量；actual raised_bins在monitor为0，candidate等于post_would_raise_bins。旧would_raise_bins明确仍是floor>original RES target的历史诊断，仅用于跨D44投影，不代表D45实际抬升。旧noise_dominant/excess/innovation含义不改。q_mean/echo_sum/residual_sum/innovation_sum/noise_sum/excess_sum/floor_mean/floor2_residual_sum仍按原有效集和ascending double左折叠规则，不做新评分。

bins.csv保留原22字段，末尾追加updated_noise、combined_gain_before、combined_gain_after三float字段；仅固定原D43选帧全257bin。扩展observer与D43 base分开，仅保存处理时操作数，observer=NULL时算法行为不受影响，不将observer加入算法状态。旧双精度17有效数字、float9有效数字格式保持。updated_noise是原tracker当前结果，不称独立背景真值。

D45两模式旧E/R/Cr/Ci/N、q/valid/count、current FFT/power/echo_power、原target、old_gain/applied_target/res_gain、updated_noise/combined_gain_before及旧功率字段exact；mode投影仅排actual raised和combined_gain_after。与D44 monitor的旧字段投影亦exact，排actual raised及新增字段；protection投影排actual raised，其余exact。不能要求候选res_gain与D44 candidate保护后的状态exact，也不能把新combined_gain_after伪写旧值。重复七输出exact；future前1247帧PCM/CSV/bins前缀exact，4future不评分，repeat不增加独立样本。

独立审计不import新helper、不执行DSP：核来源/工件起止锁、monitor四byteexact/candidate bypass、全帧schema/count/range、固定快照旧q/floor严格映射、原target/平滑gain、用保存updated_noise复算combined_gain_before及新max位置的binary32 exact、power汇总/actual计数、mode/repeat/future、AGC/VAD和新960组原波形评分及两臂准入。新观测字段只服务算术核验，不能自批准候选；原RMS容差1e-10 dB、double汇总容差max(1e-24,1e-12*abs(expected))及expected0严格零保持，不放宽float exact。完整FFT、全帧bin算术、完整EMA/noise历史独立重建仍false。

定向known answers必须包含D44严格2N/q端点/N0/warm/power/非法值原例；新应用位置含combined<floor/相等/>floor、floor0、monitor/ inactive不抬升、合法弱NS与RES乘积受新floor保护而原RES状态不变；40帧observer-vs-NULL原状态/输出exact；新diag宽度/旧列投影、repeat/future、非法argc/长度/非finite/gates、已存在根/外部根/symlink fail-closed。从非repo cwd验证help/dry-run。先源码及执行控制独立审查再正式运行。

保持单command120 s/矩阵1800 s；算法scoped22000 B不增加，observer三float×257可能增加约3 KiB，但以实际sizeof复测为准；measurement_scoped<=65536 B，加D30 71224 B<=131072 B。单工件4MiB/root1536MiB/启动free>=3GiB，正式前实读。扩列若超预算作为测量缺陷replan，不删锁/改限以通过。宿主资源不替代目标板RSS/CPU/p99/热/功耗。

## P4 执行、退出与接力

scope_write仅D45新PLAN/PLAN_REVIEW/AMENDMENT（若需）、header/NSfork/C、tools.codex_assets/device_post_ns_protection.py及对应test、IMPLEMENTATION/RESULT/REVIEW/HANDOFF/CLOSEOUT、最终README追加，以及排他/tmp控制与回执。不修改旧D0–44源码/裁判/失败/绑定或产品默认。先独立计划审查，登记新task/attestation/checkpoint，再实现、定向及strict/negative/fresh实施审查、source冻结、唯一正式矩阵、独立全量核验、whole review、freeze和本地收口。

正式root=/tmp/audio-fe-device-post-ns-protection-d45-20261011，目前不存在。intent/receipt排他，未知先核同handle和actualstate，不重放。任何测量缺陷保留partial及失败并用新身份；候选原准入失败保存结果并停止该映射参数搜索。知识和活动未持久化，不推断主体；无commit/push/PR/merge/release/设备写。

task-package v2：kind=implementation，question=同一floor的保护位置能否改善near而守住no-near，permission=用户已授权first-party结构研究，evidence=冻结计划/真实新波形/独立审计，exit=原准入和测量门禁真实终态，handoff=root，retention=真实失败与脱敏证据。claimant=root，verifier=device_capture_independent_review。

required_evidence=plan/result/review；P1–P4为完整阶段，logical_task_open=true/open_items3；retry_budget2仅新测量缺陷身份，staleness_threshold=来源/contract漂移立即replan；heartbeat绑定实质进展/livehandle；stop_condition=pass/replan/blocked/abort。独立major闭合前不执行依赖步骤。单D45里程碑不完成总体native目标。

AISpeech固定点256/QIVW产品链路、真人下游、目标板、HIL/E001/≥72h PQ及第三方权利保持独立资格。原dirty保留，Provider知识NEEDS_REVIEW；总体native目标继续active、无token上限。
