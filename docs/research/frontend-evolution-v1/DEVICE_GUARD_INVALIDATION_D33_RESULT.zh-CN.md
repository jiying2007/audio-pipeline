# D33 路径通知时保护历史失效消融结果

日期2026-10-11；experiment=FE_DEVICE_GUARD_INVALIDATION_D33；数据角色=已查看development设备采集和合成工程对照，adaptive reuse已披露。
主测量首次真实terminal exit0，92次C/252972帧；decision=GUARD_INVALIDATION_DEVELOPMENT_REJECTED。
失效操作消除了D32纯回声误保护和额外恢复退化，同时使所有near首段保护归零，包括静态A的误通知对照；不批准产品候选。

## 身份与单一因果改动

[原冻结计划](DEVICE_GUARD_INVALIDATION_D33_PLAN.zh-CN.md)SHA256=9091611aa194268ec4f475e84a37ac07d5900fabb5d800c887874e4d3b842116。
接受根=/tmp/audio-fe-device-guard-invalidation-d33-20261011。
result/binding SHA256=09cc3b8156436c033adf353d03a9db5079a660c14ab89a574b8238f84596af72 / fe9d21710ed6a2ca35ed9b7b7eba8579ea64d46d57ed8cf4012cda4d3cb0cf79。
原D32拒绝、D30权威评分基线、D31观察和D18库/source依赖完整保留，只链接原D18库、不重编DSP。
唯一算法改动是feedback在实际通知帧、Activity与guard gate之前清零全部40B保护历史；monitor完全沿用D32。
特征、valid、stable、armed、hold和padding均清零；guard.csv before字段记录失效之后的gate前状态。
Activity/primary/selector/transition无新增reset，shadow仍原一次通知copy/reset；阈值、100稳定帧重arming、3帧hold、far0处理、原评分和准入不改。
所有return来源实际notify1000；静态A真路径不变，因此其通知是原预置误通知对照。ABA在1000切B、1200返回A但没有第二次通知；本轮未制造额外通知。
near只在测量后从原near.f32le非零帧重建，不以dt标签或路径truth生成控制。

## 冻结准入与近端代价

| 条件 | 结果 | 实测 |
| --- | --- | --- |
| 8near各200帧区间used_dt>=180 | FAIL | 所有首次[1000,1200)均0帧 |
| 静态A onset<=2帧 | FAIL | 四near来源首段均无触发，延迟null |
| 四纯echo[800,2000)guard0 | PASS | 全部0 |
| 12return原whole/windows selected error对D30增加<=0.5dB | PASS | 每例原各窗最大增量0dB，保留后续改善 |
| 32field switch_count不超过D30 | PASS | 无新增 |

| near来源（每行含dt/unguarded两个） | D32首段覆盖/延迟 | D33首段覆盖/延迟 | D33第二段覆盖/延迟 |
| --- | --- | --- | --- |
| A-r16 | 199/1 | 0/null | 199/1 |
| A-r20 | 199/1 | 0/null | 199/1 |
| ABA-r16 | 68/87 | 0/null | 199/1 |
| ABA-r20 | 68/108 | 0/null | 199/1 |

null表示整段没有used_dt，不填0延迟。第二段重新保护不能补偿首次2秒near完全遗漏。
静态A原10–10.5s error相对D32增加约12.30–12.31dB、10.5–12s增加15.64–15.69dB；12.5–14s最高增加21.015872dB。
静态A第二段虽然同为199帧保护，原16–18s error对D32仍增加约1.89–1.94dB，说明覆盖计数也不能替代状态污染后的误差。
以上只属于合成开发对照，不是真人近端或主观听感结论。

## 纯回声恢复与消融解释

| 来源 | D32误保护帧[800,2000) | D33误保护帧 | D33 whole error对D32增量dB | D33 18–20s error对D32增量dB |
| --- | --- | --- | --- | --- |
| A-r16 | 0 | 0 | 0.000000 | 0.000000 |
| A-r20 | 0 | 0 | 0.000000 | 0.000000 |
| ABA-r16 | 895 | 0 | -7.700908 | -33.016651 |
| ABA-r20 | 892 | 0 | -7.568456 | -33.136973 |

四纯echo所有原whole/windows selected error均与D30相同；D32新增的恢复退化在本组消融中消除。
ABA有near来源18–20s error对D32改善约23.78dB，但其首段near仍完全未保护；不可据恢复改善晋升。
单一历史失效改动支持D32通知后沿用旧保护状态对误保护/恢复冻结有因果贡献，范围仅本组固定开发输入和实现。
不能由此认定armed唯一根因、通知可靠或失效操作普适；静态A误通知暴露明确反作用。
下一研究需要同时处理通知可信度与near保护依据；不以无条件清零替代near检测，不加真值通知、不放宽原验收。

## 实际执行、控制与资源

monitor46例全部13输出byteeqD32；原12同时byteeqD30。feedback16个无通知来源全部13byteeqD32，其余全部13通知前前缀一致。
feedback所有mic/ref/activity.csv保持D30原字节；32field主例和两个field控制共34例全部13输出也保持D32，已有设备data的此消融未改变输出。
每模式repeat13全量byteeq；future通知1247帧前13前缀byteeq，无评分/选型。
primary/Activity/observer/selector/transition各252972调用，shadow89128次、shadow reset60次，mixed samples179840、switch562；source/input/runner起止锁保持。
mic代数最大abs误差primary/shadow=1.4901161193847656e-08、selected=2.2351741790771484e-08。
原两AEC状态66040B、guard40B、局部状态及帧缓冲71264B，128KiB研究预算；原B0 50000B不改、双AEC超限保持，不包括完整栈/RSS。
严格预编译、自测及5Python tests首次均0；计划PASS及实施fresh PASS之后才开始主矩阵，当前主DSP retry0。
argc/五非法参数拒绝符合预期，13sentinel保持、primary/shadow/Activity/observer调用0。
独立stdlib逐帧审计、输出保护负例、whole-change及最终复验以[审查记录](DEVICE_GUARD_INVALIDATION_D33_REVIEW.zh-CN.md)和绑定回执为准，主exit0不替代它们。

## 交付边界与接力

promotion_allowed=false、shipping_approved=false；没有原产品default/API变化。无commit/push/PR/merge/发布/设备写。
AISpeech固定点产品链、完整NS/RES/AGC/VAD/KWS、独立真人near、SSC305资源/性能/HIL/E001/PQ和owner批准分别未闭合。
Provider route unresolved/current为空，知识线NEEDS_REVIEW，仓内reviewing candidate，无正式归档。
消融结果和D32失败同时保留；下一轮精确冻结通知可信度与near依据的单一改动，不把本轮误保护归零当完整保护合格。
总体native优化目标active，本地D33仅闭合真实因果消融/候选拒绝与可复验工程证据。
