# D44 逐频点创新噪声比保护门控计划

2026-10-11，experiment=FE_DEVICE_INNOVATION_NOISE_GATE_D44，kind=first-party structural algorithm experiment。goal_statement=全面推进优化迭代；primary=adk-planning-execution-loop。本计划在新实验执行前冻结，尚未实现或执行新候选；独立计划审查通过后才实施。D0–D43 历史结果和拒绝保持，shipping_approved=false、promotion_allowed=false。

## P1 证据、假设与冻结基线

D43 已完成 184 次 / 505944 帧、独立快照数值及全 960 组描述审计、整批审查和本地收口，原五输出逐字节等于 D42。D43 result/binding SHA256=`3642acfaa5ccf2e9c452c013bae0ca5539e0ef70a418eb69862b7eaaa64d6d1f` / `f6ed4dbcd4cbfc9e7a0aa4351ac00117afc63d8f966d443d30a54a799299a87b`；38 项 snapshot=`b00d2bbb92e733dda91c0440b96269ab1d14c4096d50cdcb45ca069a91f878b3`，当前再次实际读回全相同。D43 CLOSEOUT SHA256=`d56e26e43745197fd14a7e6335867c8e79c55558768542b0f352c819009a3290`，与 snapshot 分开锁，不覆写该旧快照。

D42 候选仍拒绝：near 配对误差中位约 -2.18 dB 未达 -3 dB；no-near 最大 +3.71 dB 超过 +1 dB。D43 的既有最坏 near 后窗口 [200000,224000) 中，noise_dominant 比例约 .6293，仍约 .3348 有效 bin 抬升 target。全部 near 后 fixed 窗整体 N/R 中位约 1.0027，但逐 bin excess/R 中位 .1277/.1444；near fixed 中位 innovation/R 约 .8765、N/R 约 .3667。总量比值不能替代逐 bin 判定，算法估计不等于声源真值。

假设：把连续噪声扣除的保护幅度规则替换为固定逐 bin 创新噪声比门控，可能在保留强创新保护时减少弱创新残留保护，改善 near / near 后权衡。只检验下面完整映射作为一个因果修改，不分别声称门控或幅度取消扣除的独立收益。弱 near 漏保、频点开关、noise 估计偏差和非线性 echo 误保护是明确失败风险。

只使用已查看 development 和合成工程数据；这是一项由 D43 描述启发的新开发假设，不是盲测或独立效果确认。无新第三方源码、数据、系数、模型或权重引入。保留 D30 46 来源和 D18 exact 原库、build defines、FFT/NS/AGC/VAD 实现与 D39 对照身份；D42/D43 的全部来源/工件锁及 snapshot/CLOSEOUT 固定。历史 snapshot 内 README 只代表当时身份，不要求后续追加入口等于旧 README。

本轮 fresh local HEAD=572b0e34a8a8e5663397ce16e378209ba9058d4d，main=70aeb4aa1458e20917ac551d1fe5f7468df721e2；78 check runs 无 pending，required summary completed/success。#657 OPEN、updated2026-10-10T11:33:28Z；PR717/714/708/695 OPEN，head 分别79f1f2d4fc27939fbbe70e6e425267d7e0298b33 / 0dde28b8632113455c402ea61add8736339a6a31 / 9c45aec010457d9ef7b1355fc2a0b22a480cf0e3 / 61f195075fe31da45413db33f2390d791aef00df。最新实读工件11701995180 / 11701595007 / 11701555278未过期，分别对应PR714 / 当前main / 当前main，不作新候选资格。Provider validation query route unresolved / zero-hit，知识 NEEDS_REVIEW，未归档成功。

## P2 唯一候选规则与精确生命周期

从冻结 D43 first-party instrumented NS fork 派生新符号，只替换 guard floor 的映射；不改变 EMA、旧噪声读取阶段、当前 FFT、NS tracker、频域原 target、平滑增益、OLA、AGC/VAD、原 gates 或 enable_frequency_res=1。全部门控只使用处理时已有状态，不读 near、窗口标签、未来、运动标签或额外 oracle。

旧状态 E/R/Cr/Ci/count、原 NS 上一帧 binary32 estimate 转 double 的 N，与 D42 完全同阶段。先执行原有限值/范围检查；count<10 或 E<=1e-12 或 R<=1e-12 时 floor=0、valid=0。其余 valid=1，按以下固定顺序计算：

1. q=(Cr*Cr+Ci*Ci)/(E*R)，非 finite 拒绝，然后 clamp 到 [0,1]。
2. innovation_fraction=1.0-q；I=R*innovation_fraction；bound=2.0*N，均按 binary64，任何非法或非 finite 拒绝。
3. 若 I>bound，floor=(float)sqrt(innovation_fraction)；否则 floor=0.0f。严格大于；I==2N 不保护。N=0 且 I>0 时允许保护，I=N=0 时不保护。系数只有 2.0，固定一次，不搜索其他系数/阈值。
4. 监测与候选均计算同一 floor/valid 并更新原 .8/.2 EMA；monitor 不抬升 target，candidate 仅 target=max(original_target,floor)，维持原 .55/.45 或 .92/.08 binary32 平滑。inactive 保留原 reset 及 count_before 的旧值语义。

该两倍边界是预声明的算法功率比条件，不是物理 near 检测真值、声学准入门槛或已验证最优参数。新映射不含连续减 N 幅度规则；整套映射作为一个候选检验，不用此次数据分别归因门控和幅度的贡献。

ffp-contract=off，IEEE float32/double64、FLT_EVAL_METHOD=0，所有 double/float 操作按冻结顺序；新 guard 保持 D42 状态布局/大小，不增加跨帧状态。严格 C known answers 包含 I<2N、I==2N、I>2N、N=0、q=0/1、warmup、低功率、inactive、NaN/Inf/负值、非法 count，以及固定 guard EMA 更新和 observed-vs-NULL 等价。对临界输入必须以实际 double 比较验证，不能用近似声学阈值测试替代。

## P3 原裁判、对照、观测与预算

矩阵保持 D30 全 46 来源 × primary/selected × monitor/candidate=184 执行 / 505944 帧。monitor 原五输出必须与 D43 同名 monitor 逐 byte 相同；candidate bypass 必须与 D43 同名 candidate exact，候选 ns/final/control/protection 按新保护自然变化，不要求伪等价。原 AEC 不重新执行，D18 库不重编；不是在旧实验 root 重跑或改判 D42。

所有声学开发测量直接复用冻结 D42 observe / development_admission 及原 D39 比较对象，不修改其任何计算、对齐、窗口、RMS 规则或门槛。每臂：24 个 near fixed 的 final 已知合成 near 误差配对中位<=-3 dB，至少18个误差下降；72 个 no-near fixed 的 final RMS 配对最大<=+1 dB；4 个 pure-echo whole 的 final RMS 最大<=+1 dB。两臂均满足才记录 DEVELOPMENT_CANDIDATE_ONLY；任一失败 DEVELOPMENT_REJECTED。候选-only 仍 promotion_allowed=false、shipping_approved=false。measurement/identity/numeric failure 独立标 MEASUREMENT_INVALID_REPLAN，不伪装为声学拒绝或通过。

保留 D43 power.csv 与固定稀疏 bins.csv 的字段、选帧、汇总运算和格式；没有新的评估器。power 中 innovation_sum 和 excess_sum 仍分别为旧 R*(1-q) 与旧 R*max((1-q)-N/R,0)，noise_dominant 仍是该扣除式<=0的诊断计数，不改为两倍门控计数。positive_floor / would_raise / raised / floor_mean / floor2_residual_sum 记录实际新 floor，故不要求与旧 excess_sum 相等，也不以这些值作新增准入。

与 D43 同例的 q/旧 E/R/Cr/Ci/N、当前 FFT/power/echo_power、原 target、valid/count/gates 仍 exact，独立验证无 feedback；允许实际 floor/old_gain/applied_target/res_gain 变化。两模式投影排除实际 raised 及 old_gain/applied_target/res_gain，其余诊断 exact；重复 7 文件 exact、future 前1247帧 PCM/CSV/bin 前缀 exact，4 个 future 不评分，repeat 不算新增独立样本。固定快照集合与原 D43 相同，不事后挑帧或窗口。

独立 audit 不 import 新 helper、不执行 DSP：核184来源/工件起止锁、monitor原五byteexact/candidatebypass、选帧旧操作数→严格两倍门控/floor bitexact→原target/applied/平滑gain bitexact；全帧schema/count/range、快照汇总、mode/repeat/future；候选 final 实际波形的原固定960组测量及两臂原准入由独立实现复算，不能继承 D43 候选改变后的波形分数。原RMS比较容差仍1e-10 dB，不能改门槛。全部帧 FFT/完整 EMA/噪声历史仍不独立全量重建。

D43 的描叙工具不自动批准候选；若需要新结果描述，必须保持全960窗口/离线near标签及独立全量复算，不做新窗口选择。scope 内不能修改 D42/D43裁判、已通过测量工具或既有失败记录。

保持单命令120s / 主矩阵1800s；原算法scoped22000 B，观测结构预期与D43相同但实际sizeof重新记录，measurement_scoped<=65536 B，加D30 71224 B<=131072 B；单工件4MiB / root1536MiB /启动free>=3GiB。实际预查/tmp free15628615680 B，仅为当前读值，正式前复核。宿主资源不等于目标板资源。

## P4 执行、退出与接力

scope_write仅新 D44 PLAN/PLAN_REVIEW/AMENDMENT（如需）、header/NSfork/C、tools.codex_assets/device_innovation_noise_gate.py、对应test、IMPLEMENTATION/RESULT/REVIEW/HANDOFF/CLOSEOUT及最终 README 追加。先独立计划审查、登记新本地task/attestation/checkpoint，再实现、定向/严格构建与负例、fresh实施审查、冻结source、唯一正式执行、独立全量核验、整批review、冻结/本地收口。

正式 root=/tmp/audio-fe-device-innovation-noise-gate-d44-20261011，当前不存在。主执行器 intent/receipt排他；同handle未知先对账，不重放。任何identity/measurement失败保留root和partial，以新身份修复；候选准入失败保存完整结果并停止该规则的参数搜索，后续重新冻结假设。无commit/push/PR/merge/release/设备写。

task-package v2：kind=implementation，question=固定逐频点门控能否同时改善near保护和无near恢复，permission=用户已授权first-party结构研究，evidence=冻结计划/实测/独立审计，exit=原准入/测量门禁明确终态，handoff=root，retention=真实失败与脱敏证据。claimant=root，verifier=device_capture_independent_review。

required_evidence=plan/result/review，logical_task_open=true、open_items3；retry_budget2仅用于明确测量缺陷后新身份，staleness_threshold=来源/contract漂移立即replan；heartbeat绑定实际进展/livehandle，停止条件pass/replan/blocked/abort。P1/P2/P3/P4为完整阶段，review finding闭合前不进入依赖步骤。单个D44里程碑完成不完成总体native目标。

AISpeech固定点256点/QIVW、真人语音、目标板、HIL/E001/≥72h PQ及第三方权利保持独立资格。知识NEEDS_REVIEW，不推断归档成功；既有dirty不回退或清理。总体native目标 active、无token上限。
