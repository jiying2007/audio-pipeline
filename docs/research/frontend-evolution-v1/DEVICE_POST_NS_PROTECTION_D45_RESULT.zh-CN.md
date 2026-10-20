# D45 合成增益后保护的正式测量结果

2026-10-12，experiment=FE_DEVICE_POST_NS_PROTECTION_D45。唯一正式矩阵已实际 terminal exit 0，测量门禁通过，候选 decision=DEVELOPMENT_REJECTED。首次独立全量审计正在 session 87961 执行，本文件记录正式测量与根保护的已完成证据；独立审计终态及整批审查另见后续 REVIEW，不提前声明通过。总体“全面推进优化迭代”保持 active。

## 因果修改与原准入

冻结 PLAN、PLAN_REVIEW、IMPLEMENTATION 及五项源码保持原字节。D45将D44同一创新功率保护floor从频域RES target移到ordinary NS与原RES合成增益之后。q、严格I>2*N、count10、EMA、噪声更新、原RES target与平滑状态、FFT/OLA、AGC/VAD和门控保持。candidate只在原frequency active时应用max(combined_gain_before,floor)，monitor不抬升；保护不反馈RES状态。

两处理臂各自要求24个near窗误差中位<=-3 dB且至少18窗改善、72个no-near窗最大能量增量<=+1 dB、4个pure-echo whole最大增量<=+1 dB。原窗口、alignment及D39比较对象保持，未调门槛或事后选窗。

| 冻结准入统计 | primary | selected | 结论 |
| --- | --- | --- | --- |
| near配对误差中位 dB | -3.269613425930995 | -3.269613425900271 | 两臂达到-3要求 |
| near改善窗数 | 20/24 | 20/24 | 两臂达到18要求 |
| no-near最大能量增量 dB | +6.5516918597166125 | +6.5516918597166125 | 两臂超过+1 |
| pure-echo whole最大增量 dB | +1.255012175073496 | +2.113633226851505 | 两臂超过+1 |

移动保护位置使near中位改善达到原要求，同时扩大无近端及纯回声能量代价；该映射整体拒绝，停止本映射参数搜索。这个结果不能证明普通NS是唯一根因，不能将development样本的局部收益升级为产品效果。promotion_allowed=false、shipping_approved=false、shipping_algorithm_changed=false。

## 实际执行与保存

正式根 `/tmp/audio-fe-device-post-ns-protection-d45-20261011`。唯一执行 session 54607已回收terminal exit 0；outer执行559.296156603843 s，矩阵470.579151914455 s。46来源例×primary/selected×monitor/candidate，共184次DSP、505944帧。无measurement-invalid.json。binding包含9829来源锁、1884工件；加binding为1885文件。

| 工件或回执 | SHA256 |
| --- | --- |
| result.json | `0d9dbf01b21510216df648d323c501166a039a5b45d44c93d2699b8eabc4e8de` |
| binding.json | `bb0fbb8b9942e2b9ca5dbecf9a53ac1f13f38d40c7bbb574d5a438506d00cff8` |
| /tmp/audio-device-d45-execute-v1.json | `56171f8c2358310bbe4b8e15da347a1bb3d73d4e78d30473c3a7a490e53c9f31` |
| /tmp/audio-device-d45-negative-v1.json | `191880e2d9beb6576c761ff07d76dda59fdf62ee914ada7e3960ff6438c0eb62` |

既有根保护session33006 terminal exit0，30.441693755798042 s；D30/仓库/D45三个请求均exit2，完整manifest前后相同，当时文件数679/2592/1885。后续新增文档不要求仓库仍为2592文件。

实际algorithm scoped22000 B、observer26728 B、measurement48728 B；加D30原71224 B为119952 B，低于131072 B上限。最大文件2817401 B、根合计1516604218 B，满足4 MiB/1536 MiB预算。原单command120 s、矩阵1800 s保持。资源证据仅为宿主scoped及输出预算，不证明目标板峰值RSS、CPU、p99、热或功耗。

## 独立验证与当前边界

独立审计脚本 `/tmp/audio-device-d45-independent-audit-v1.py` SHA256=`577f21fc0881f1c3683697ad9bfcbc5d270c48c955b5492ef6b4226ec363aac0`，标准库加系统libm，不import项目helper、不执行DSP。脚本静态审查、自测通过，正式审计已排他启动session87961；尚待实际终态。要求独立新算960组波形评分、原准入、AGC/VAD binary32、固定快照的原NS/RES合成及新max、全帧schema/count/range、baseline/mode/repeat/future及起止锁。

全FFT、非快照逐bin算术及完整EMA/noise历史独立重建仍不在覆盖内。near为实际消费的离线合成样本；field没有独立near真值，repeat不增加独立样本，future4不评分。AISpeech固定点256/QIVW产品链与本160点float研究分别验收；真人听感、ASR/KWS、目标板/HIL/PQ和shipping资格未建立。

恢复时fresh main=`c1b91e5086b0f8a3e82dc35506de4bcc1be58942`，返回检查均completed，required summary success、fast-docs skipped；#657仍OPEN，updated2026-10-12T05:29:45Z。开放PR717/714/708/695；714新head=`4f5d7dee42ed15457b2b1a0325210adbb9f66bee`。这些远端身份和CI不替代D45证据。

新的维护v2实际已受理，回执 `/tmp/audio-device-d45-native-compact-v2.json` SHA256=`1e960597ead9f62f8887d8dc206713c4a3f8d88d6173600b08c981901510b3b0`，status=ACCEPTED_COMPLETION_UNVERIFIED，120.44823437836021 s。恢复fresh Runtime maintenance.required=false，继续业务；不重发请求，不将自动压缩归因本次请求。已刷新当前线程heartbeat，后续更新进展及审查证据。

Provider route unresolved，知识NEEDS_REVIEW，未声明归档成功。无commit/push/PR/merge/release/设备写。独立终态、whole review、快照、README结果入口及本地收口仍待完成。
