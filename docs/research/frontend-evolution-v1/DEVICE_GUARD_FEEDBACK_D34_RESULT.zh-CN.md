# D34 保护反馈隔离诊断结果

日期2026-10-11；experiment=FE_DEVICE_GUARD_FEEDBACK_D34；decision=GUARD_FEEDBACK_DIAGNOSTIC_NO_PROMOTION。
固定原阈值，未反馈monitor仍误触发；反馈后误保护明显延长。因此隔离观测能针对反馈耦合，但单独采用该结构仍不足以解决初始误判和切换时near遗漏。
这是封存开发状态的诊断，不是新AEC候选执行或声学效果证明。

## 精确身份与测量边界

[冻结计划](DEVICE_GUARD_FEEDBACK_D34_PLAN.zh-CN.md)SHA256=d51c6e21402f5dae92e485449e7a4540317aaeccf4dc3c217bdb0f1d5c87106c；[兼容性偏差](DEVICE_GUARD_FEEDBACK_D34_AMENDMENT.zh-CN.md)保留首次实施MAJOR与旧源码。
接受根=/tmp/audio-fe-device-guard-feedback-d34-20261011。
result/binding SHA256=902de3247ac3179082481f28c07b471b8dd2eabd0834562da7416b3a657b9acd / edf842ff61d6d9fd0ac4ccdb05bc408c8f2500f692db00b5edf64eabb2df0d09。
固定D32 monitor/D32 feedback/D33 feedback三臂，每臂46例126486帧，共138个case-arm/379458状态帧，DSP执行0。
实际deep dry-run、6项测试及主诊断首次均exit0；源/输入3570项起止锁保持，输出46个43列CSV和精确result/binding。
逐帧重建原gate/100stable/3hold/D33通知失效，不重算声学评分；日志特征为本帧observer之后值，gate用上一帧特征。
monitor实际used_dt仅原Activity；potential_dt为未施加的detected_dt OR guard，不能冒充实际保护或隔离观测候选的输出。
future仅核通知1247前前缀，不生成未来段统计；repeat全量等normal。45个非future来源原240窗口逐三臂计数，窗口向内取完整160点帧，边界丢弃样本保留。

## 初始误判与反馈延长分列

纯echo误保护只在已知无near的四个合成对照成立；field没有near真值。

| 纯echo来源 | monitor潜在guard帧[800,2000) | feedback实际guard帧 | D33实际guard帧 | monitor最长连续段 | feedback最长连续段 |
| --- | --- | --- | --- | --- | --- |
| A-r16 | 0 | 0 | 0 | 0 | 0 |
| A-r20 | 0 | 0 | 0 | 0 | 0 |
| ABA-r16 | 221 | 895 | 0 | 200 | 803 |
| ABA-r20 | 218 | 892 | 0 | 200 | 814 |

ABA两来源monitor与feedback首次guard都在1087帧；monitor实际used_dt仍为0。
primary相关特征cme/cre/ratio首次分歧均为1087帧，guard首次分歧分别1091/1094帧。
monitor最后guard区间均为[1334,1337)，feedback最长区间分别[1197,2000)/[1186,2000)，延续至记录末尾；不能把观察末尾当实际终止。
这支持反馈改变观测后延长误保护的耦合解释，但初始误触发在未反馈臂已存在，不能把全部失败归为反馈唯一根因。
D33清零消除误保护的历史结果保持；其首段near归零代价仍不能豁免。

## Near潜在辨识并未满足原条件

每行dt/unguarded两个来源同值；首段[1000,1200)，次段[1600,1800)。计数/首次延迟单位均为帧，null表示整段没有触发。

| near来源 | monitor首段潜在计数/延迟 | D32首段实际计数/延迟 | D33首段实际计数/延迟 | monitor次段潜在计数/延迟 |
| --- | --- | --- | --- | --- |
| A-r16 | 199/1 | 199/1 | 0/null | 199/1 |
| A-r20 | 199/1 | 199/1 | 0/null | 199/1 |
| ABA-r16 | 87/87 | 68/87 | 0/null | 199/1 |
| ABA-r20 | 87/108 | 68/108 | 0/null | 199/1 |

所有monitor near区间的实际used_dt均0。静态near潜在计数保持199，但切换期首段只有87帧，未达到原>=180帧条件。
这些是未反馈观测的潜在触发能力，不是第三AEC隔离观测已执行的保护率，也不批准新结构。
三臂32个field主源及repeat的guard字段均无分歧；不得从现场输出未变推导真人检测或唤醒合格。

## 验证、解释与接力

root四类输出保护负例均exit2，D32完整1387文件、D33完整1387文件与新D34完整48文件manifest前后保持。
negative回执SHA256=b747e046d0dc22522fb5d69dac3aacc59593f923fecff1bd7874619b42c3d3f8。
独立逐帧统计、完整连续区间/原窗/near波形复核、whole-change及REVIEW后复验以[审查记录](DEVICE_GUARD_FEEDBACK_D34_REVIEW.zh-CN.md)与实际绑定回执为准。
无新增候选接受规则，不改变D32/D33拒绝或原五项准入。下一实验不能只增加隔离AEC就预期通过；需先冻结独立的路径失配与near辨识机制，避免重复已知不足。
data_role=已查看设备development和合成工程对照，adaptive reuse披露；无新的validation/blind或真人资格。
promotion_allowed=false、shipping_approved=false；产品default/API、完整AISpeech/NS/RES/AGC/VAD/KWS与目标资源/HIL/E001/PQ分别未闭合。
Provider route unresolved/current为空，知识线NEEDS_REVIEW，无正式归档；无commit/push/PR/merge/发布/设备写。
总体native优化目标active，本地里程碑只收口反馈隔离诊断与可复验工程证据。
