# D32 因果近端保护反馈候选结果

日期2026-10-11；experiment=FE_DEVICE_CAUSAL_GUARD_D32；数据角色=已披露development设备采集与合成工程对照。
主测量真实exit0；固定结论CAUSAL_GUARD_DEVELOPMENT_REJECTED，promotion_allowed=false、shipping_approved=false。
本轮完成首次完整92次C回放/252972帧，候选三个准入条件失败。不是目标板或真人声学资格。

## 身份与冻结合同

接受根=/tmp/audio-fe-device-causal-guard-d32-20261011。
result SHA256=a9e8d6f1120c420361d10daae103f207679638439da4ff65d01fa621af8b477a。
binding SHA256=d6a49352c331734bd4015b2c2e56ba3fa0a1f4c36a957b968566ae0d03ce80fe。
[原计划](DEVICE_CAUSAL_GUARD_D32_PLAN.zh-CN.md)不改，SHA256=0e808bd69b2dcbfe443fa8f887d7644ed05eef5a6ec41549160ed2b786f1ea18。
[偏差记录](DEVICE_CAUSAL_GUARD_D32_AMENDMENT.zh-CN.md)SHA256=70e0ccfe4e1b1338a21ae375eb47919d6c4df241df7b6ebaae0301ad85a70cd1。
只链接原D18预编译库，未重编DSP；monitor与feedback同源44主例及各repeat/future，对照原D30。
唯一研究算法改动是上一帧primary mic/echo/residual三特征状态生成guard，并与原Activity dt取OR；没有标签/前视输入。
原Activity、AEC、选择器和过渡参数不改；当前观察供下一帧，armed只是历史收敛迹象，不是路径真值。

## 五项冻结准入

| 条件 | 结果 | 实际证据 |
| --- | --- | --- |
| 8个near来源每个200帧区间used_dt至少180帧 | FAIL | ABA四来源首次区间仅68帧 |
| 静态A near首次触发延迟不超过2帧 | PASS | 四来源两区间均1帧 |
| 四个纯echo来源[800,2000)guard为0 | FAIL | ABA-r16/r20分别895/892帧 |
| 12个return原whole/windows selected error增量不超过0.5dB | FAIL | ABA纯echo最高+33.136973dB，有near最高+19.129093dB |
| 32个field各switch_count不超过D30 | PASS | 未增加；这些来源guard帧数均0 |

失败不改变阈值、窗口、验收、超时或输入角色。字段和失败逐例保存在result；一次退出0不能批准候选。

## 近端保护与纯回声混淆

near真值在测量后从near.f32le逐帧非零值重建；dt和unguarded都含相同近端，不能把旧dt标签当完整真值。
下表每项列出[1000,1200)、[1600,1800)覆盖/首次触发延迟；帧长10ms，延迟0也可能来自既存保护状态，不能解释为新语音被零延迟识别。

| 来源 | 首区间覆盖/延迟 | 次区间覆盖/延迟 | 原whole/windows最大error增量dB |
| --- | --- | --- | --- |
| A-r16-dt / unguarded | 199/1 | 199/1 | 0.000000 |
| A-r20-dt / unguarded | 199/1 | 199/1 | 0.000000 |
| ABA-r16-dt / unguarded | 68/87 | 199/0 | +19.129093 |
| ABA-r20-dt / unguarded | 68/108 | 200/0 | +19.080385 |

静态A近端原10–10.5s窗口error下降约12.30–12.31dB，10.5–12s下降约15.64–15.69dB；收益只属于本组合成开发对照。
ABA第一次near延迟870/1080ms，后续较高覆盖与纯echo大面积误保护并存，不能用第二段覆盖证明识别质量。

| 纯echo来源 | [800,2000)误保护帧 | whole error增量dB | 18–20s error增量dB |
| --- | --- | --- | --- |
| A-r16 | 0 | 0.000000 | 0.000000 |
| A-r20 | 0 | 0.000000 | 0.000000 |
| ABA-r16 | 895 | +7.700908 | +33.016651 |
| ABA-r20 | 892 | +7.568456 | +33.136973 |

实测显示反馈在路径变化后持续误保护并伴随恢复退化。合同中的armed跨路径通知保留、上帧特征与适配反馈形成潜在耦合；这是待下一独立实验验证的机制假设，不能把相关结果写成已单独证明的根因。
只读事后时序披露：ABA两纯echo首次guard均在帧1087（10.87s），最长连续误保护分别803/814帧；帧1000路径通知时armed_before仍为1，帧1200路径返回时保护仍持续，本例未发第二次通知。
时序来源guard.csv哈希及完整连续区间保存在/tmp/audio-device-d32-disclosure.json；不新增评分窗口、检测阈值或候选选择。
disclosure中的notification_states是999/1000/1199/1200四个抽样状态行的历史字段名，不代表四次通知；实际每例notify_frame=1000且shadow reset为1次。
下一研究必须冻结路径/适配可信度与near保护的因果边界，同时保留本轮恢复失败；不靠调宽接受门槛晋升。

## 实际执行与资源

46个monitor原12输出逐byte复现D30；feedback mic/reference/activity.csv保持D30原字节，原Activity检测未被重写。
每模式repeat全部13输出byteeq；future通知1247帧前全部13前缀byteeq，future无评分/选型。
总primary/Activity/observer/selector/transition各252972次，shadow89128次、shadow reset60次、mixed samples177920、switch556。
mic代数最大abs误差primary=1.4901161193847656e-08、selected=2.2351741790771484e-08；源/输入/runner起止身份一致。
严格C11预编译、自测、argc及五类非法参数负例均符合预期；非法参数13sentinel保持，primary/shadow/Activity/observer调用0。
局部状态/帧缓冲71264B，新增guard40B；研究局部预算128KiB。原两AEC状态66040B，仍超过B0 50000B，不修改B0或用局部统计替代总资源。

## 失败保留与资格边界

预编译第0次exit1、实施漏导入f32的独立NameError、首次wrapper dry-run exit2均保留，可还原原源码；具体身份见AMEND。
修复分别为声明分行、显式导入/完整observe解析测试、正确传tests/audio采集根；没有修改候选公式或验收。
修复后实施fresh PASS及调用fresh PASS之后才开始首次主92回放；实际DSP重跑0，不称整轮零失败。
独立stdlib全量复算、工具输出保护负例及whole-change/final复验以最终[审查记录](DEVICE_CAUSAL_GUARD_D32_REVIEW.zh-CN.md)及绑定回执为准，本文主退出0不替代它们。
无产品API/default改变；AISpeech完整链、NS/RES/AGC/VAD/KWS、独立真人near、SSC305资源/性能/HIL/E001/PQ和owner批准各自未闭合。
Provider route unresolved/current为空，知识线NEEDS_REVIEW；仓内reviewing candidate，无正式归档。
无commit/push/PR/merge/发布/设备写；总体优化目标active，本轮只闭合候选负结果与可复验工程证据。
