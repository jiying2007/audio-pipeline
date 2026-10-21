# D14 确认容差候选结果：工程契约通过，现场稳定性仍拒绝

日期：2026-10-11；experiment=`FE_DEVICE_CONFIRM_D14`；[冻结计划](DEVICE_CONFIRM_D14_PLAN.zh-CN.md)。
最终决定 **REJECTED_DEVELOPMENT_COUNTER_REGRESSION**，selection=`REJECTED`；
`promotion_allowed=false`、`shipping_approved=false`；总目标“全面推进优化迭代”仍为active。
收紧首候选确认容差没有消除原D11两个场景的新增jump/reset，仅延后其发生。
本里程碑完成单候选实测与拒绝，不代表总体优化、声学、设备或产品闭环完成。

## 单一改动与工程结果

精确D11研究源码作为比较基线，只有大跳确认器的容差实参从coarse_step改为
`coarse_step / 2u ? coarse_step / 2u : 1u`，在8/16 kHz分别为4/8 samples，即0.5 ms。
仍以首次保存候选为锚，容差包含端点；不是所有候选两两距离。
[增量patch](../../../.github/research/frontend-evolution-v1/device-confirm-d14.patch)独立check/实际重放通过，
重放源码与候选逐字节相同。搜索网格/refine/guard、相关门限、三次确认、history、drift和AEC不改。
候选仅位于 `/tmp/audio-fe-device-confirm-d14-20261011/source`；产品src、API和default不改。

| 验证 | 实际结果 | 资格范围 |
| --- | --- | --- |
| strict构建与CTest | 14/14通过 | Host工程 |
| 原D8 engineering/recovery | 全通过 | 已冻结直接SYNC与公共恢复契约 |
| 原D11唯一峰oracle | 21,618项通过 | 搜索性质 |
| 新确认边界fixture | 两采样率端点/越界重启/三次清零/整数边界/历史序列通过 | 确认状态性质 |
| 完整pipeline state | 78,840 / 80,000 bytes，sync=33,464 | Host编译结构大小 |
| D13事件矩阵 | 56+1实际运行，mandatory 52/52通过 | 有真值工程契约 |
| D9获取矩阵 | 100+1实际运行，mandatory 26/26通过 | 固定已知延迟工程契约 |
| 原设备开发回放 | 16场景，70固定臂+2重复，receipt verifier通过 | 开发测量身份；候选仍拒绝 |

未新增state/alloc；score网格和调用上界不变，但未测DUT CPU、功耗或热。
工程编排统一使用300秒进程timeout，未发生超时；计划的120秒观测要求由实际handle/进度跟踪满足，
没有删帧、重启未知运行、改变验收或延长失败实验取得PASS。

## 正常获取与恢复没有被这版收紧破坏

D13原fixture、生成器和原冻结evaluator保持字节不变。
56种input/config与原D13/D11逐字节一致；指定新进程repeat四文件一致。
52个mandatory覆盖获取12、持续路径切换12、稳态12、短pulse8、silence4、unrelated4。
正例仍在生成器第39帧获取、第149帧切换恢复，exactly1jump/reset、本帧入truth±3 ms、
末20帧和切换前120帧保护均通过；这些时点不是产品实测延迟。
短pulse10/20帧没有jump/reset；4个pulse3仍为diagnostic，不改变分母：
8 kHz两个seed无jump，16 kHz两个seed均第149/179帧跳80 ms再回40 ms。
不能根据这些已查看的合成分量声称真实抗干扰效果。

D9全部100例输入匹配原D11锁，CSV帧集合、first/last20/final/counters实际回读一致，
指定新进程repeat输入/输出/CSV一致。26个mandatory全部通过。
诊断周期/低参考各24/24末窗入带；合成双讲仍0/24。
宽带28例中26例末窗入带，另两例未通知gap仍不入带；不把保持40 ms称为恢复正确。

## 设备开发回放：收紧容差只是延后事件

原tests/audio的119文件锁、plan、16场景、适配mic/render和所有配置保持一致。
工程构建库与实际replay库逐字节一致。34个关闭tracker的控制PCM/metrics与D8/D11完全一致，
同配置default/sync-default-control也一致。
70固定臂相对D8有42臂逐字节一致；相对D11有65臂一致，5臂改变，涉及4个场景。

以下三个执行臂仍各有一次jump和一次AEC reset，而D8均为0/0，触发预先冻结的拒绝条件。
它们对应两个采集场景和6条counter差异，不是六个独立场景。

| 场景 / 执行臂 | D8 jumps/resets | D11事件帧 | D14事件帧 | D14 jumps/resets |
| --- | --- | ---: | ---: | --- |
| rpm240 far-motion，run-2908630469-2466，default | 0/0 | 457 | 727 | 1/1 |
| 同场景，sync-default-control | 0/0 | 457 | 727 | 1/1 |
| rpm480 double-talk-motion，run-4874838670-2672，default | 0/0 | 617 | 1247 | 1/1 |

实际JSONL以0为起始帧，10 ms/帧；按完成该帧的处理时间，分别从4.58→7.28 s、6.18→12.48 s。
这是适配回放处理时间，不是有独立校准的设备采集/声学时间轴。
D12旧触发三元组被新容差打断，并不能保证后续没有新簇完成确认；全长回放已经否定“收紧即可消除事件”。
当前证据未直接观测D14新簇的每次搜索候选，不能从jump终态编造后续三元组。

另外两个已有jump的rpm240场景也延后：run-2729896222-2438 default从457→1057帧，
run-2966042313-2478 default从547→1977帧；都仍是一次jump/reset，不是新增失败场景。
这两臂slips由28→22、29→13；上述两个拒绝场景slips分别24→20、22→18。
计数降低或事件延后不足以证明物理对齐更正确，也不能覆盖已冻结的硬失败。

指定rpm480 far-motion tracked1仍无172 ms跳变，jump/reset=0/0。
与D11输出/metrics逐字节相同，delay集合0/1 ms、slips29；该单项通过不能晋升整版候选。
全部70臂D8/D11/D14的counter变化时点、delay集合、slips、rail samples和窗口RMS已记录。
例如两个拒绝场景19–21 s窗口的D14相对D11 RMS变化为+1.234296和-2.957075 dB；
缺少clean target/独立人声标签，RMS无法区分残回、人声与噪声，不声明ERLE、保真或听感收益。

## 身份、证据与恢复

工件根 `/tmp/audio-fe-device-confirm-d14-20261011`，保留候选源码、build、原始CSV/JSONL/PCM、
输入/config、命令stdout/stderr/exit、repeat、patch独立重放和所有失败结论。

| 工件 | SHA256 |
| --- | --- |
| 实际候选libaudio_pipeline.a | `736815d2050d49f5a1ebcf254abd140b2c39edfff2f5ae43d27b06c0282a95f3` |
| engineering-result.json | `70ec936229b94a97eeb32d49805609bdf82fa0221b4bb1a42a3783b4d5f0c469` |
| engineering-binding.json | `b65212c87d6eeaf38b3421c8c863300458b02adacbf364d30228fe1557db5d96` |
| replay/receipt.json | `bd78f3151f3052c5ce62c1984455caf11f6235b1ccd8f4723d42c72775246807` |
| comparison.json | `d0d9788a3772b66848dae067283ed49f60d17bf076f99e670a1a51fda5d08820` |
| final-binding.json | `afdf4a34f18cbe049add927436c3a2c189dc613b9be3a457c4396970f2237825` |

engineering-binding锁源/依赖/计划/fixture及832项工件；final-binding追加完整回放和比较脚本，
绑定1184项工件。独立复审另锁文档快照；不存在把main CI作为候选通过的授权链。
tmp不是永久证据仓，恢复先逐hash核验；工件消失/漂移应标stale，不能只凭本文声称可复现。
Provider route unresolved，仓内reviewing candidate，未正式归档。无commit/push或设备写。
AISpeech产品链路、E001、历史I025–I040结论不变；Host实验不替代真实物理对齐、HIL、owner或产品资格。

## 总体接续

本版不部署，不继续在同一实验缩小容差或改门限求绿。
下一步先冻结独立诊断：核D14延后事件的完整候选簇与short/history支持，
检验“候选重复稳定”是否仍不足以代表持续路径成立，并同时保留D13正常获取/切换保护。
已有输入属于development，不能用于独立验证或blind验收。
真实声学收益仍需同步render时间轴、延迟真值、独立人声标注、独立数据与目标板验证。
总体goal保持active；仅本轮实验及其证据/复审可阶段收口。
