# D36 前帧延迟预测诊断结果

日期2026-10-11；experiment=FE_DEVICE_HELD_LAG_D36。
结论：纯echo的历史峰值延迟能跨帧延续，静态near的本帧搜索峰值多不延续；但ABA切换首near仍含稳定可解释echo，固定前帧延迟仍不能单独区分混合near与纯echo。
decision=HELD_LAG_DIAGNOSTIC_NO_PROMOTION；promotion_allowed=false；shipping_approved=false。混合仍不可分，触发原PLAN的replan：转向可解释残差模型，不继续相近相关性诊断或阈值寻优。总体native优化目标active。

## 合同、修复与实际执行

PLAN SHA256=244bd87cde99c336e3fc791de0a49eb3ada5cb66159a522d74851586781ca501；已独立计划PASS。
实施MINOR-1为known-answer实际最优lag变化覆盖不足；原tests字节保留bb84ca1bafa1eb85e906235751d1278b21cea8e38ced96b1a1d25e87a6b06dba，按AMENDMENT拆为合法反相延续和真实延迟切换例，fresh实施Spec/Quality PASS、unresolved0后才主运行。
最终tool/tests/execute SHA256=bfffb7987e54b2520baa1833f742548819ec3aa1207ad5170b3550d7383a3461 / 781193aa1296b3f9e85a24b855c41c283eedd3fbec0b05f847fea61fd86e6758 / d80268af3bb9521364fa710b3a036f698822b9223b773739b21d82e9ef59333f。
接受根=/tmp/audio-fe-device-held-lag-d36-20261011。
result/binding SHA256=8b1123301e08caa8e695188e8005a1022e0f023500e5151046454bb90f28c8b9 / 800b73b466054e606eeb6a70210d0027e01fde3eb1d225738ea84ff4bf09820e。
四份execution实际exit0：非仓help、完整deep dry-run、7tests及主诊断；dry-run未写输出，主Host elapsed36.02549481391907s、retry0。
46例126486帧，只消费封存D30 reference/primary_residual与D35 CSV，AEC/DSP执行0、当前帧lag搜索0；Float32解码、double正向160点累加，无补零/均值扣除/未来索引或clamp。
每帧只取前帧valid_lags>0的chosen_lag；前帧无效不保持更早lag。五种reason、精确零、-1 sentinel保持；current_max直接保留D35自身有效性，不按held有效性删除对照。
3792项input_files、4项source_files起止一致，binding锁47工件；D35全部依赖及两独立审计/REVIEW锁齐。重复CSV全量exact，future只核通知前1247帧前缀exact，其measurement=null。
原240 whole/window向内完整160点帧及边界丢弃保持；旧monitor guard仅选触发帧的前帧，新量不回填当前控制。

## 时间预测增量与混合重叠

纯echo使用全2000帧，held首帧null、有效1999；near固定原[1000,1200)与[1600,1800)，各200帧。dt和unguarded是原来源角色，均消费D30未保护primary残差，不作独立重复实验。

| 场景 | 纯echo held p50 | 首near current_max p50 | 首near held p50 / p90 / max | 首near lag变化帧 | 第二near held p50 |
| --- | ---: | ---: | ---: | ---: | ---: |
| A-r16 | 0.444016 | 0.075785 | 0.003320 / 0.017796 / 0.055381 | 200/200 | 0.002230 |
| A-r20 | 0.421669 | 0.076695 | 0.003258 / 0.017218 / 0.053982 | 200/200 | 0.002148 |
| ABA-r16 | 0.449217 | 0.188908 | 0.173108 / 0.293232 / 0.424288 | 61/200 | 0.002130 |
| ABA-r20 | 0.443288 | 0.189531 | 0.170724 / 0.295693 / 0.422626 | 60/200 | 0.002120 |

静态A纯echo仅1/1999帧lag改变，ABA纯echo为53/1999和51/1999；它们max_minus_held p50/p90均0，证明此处高相关不只是本帧重新搜索的有限样本峰值。
静态near的lag全部改变，held显著低于本帧max，支持原D35近端峰值有不延续部分。ABA首near却139/200、140/200帧lag不变，gap p50=0；near与稳定echo可以共存，不能把可预测echo解释为没有near。
原纯ABAecho误guard的前帧221/218个，held min为0.185778/0.226715、p50为0.422105/0.419436；ABA首near最高0.424288/0.422626，重叠仍在。
本轮未选阈值、拟合分类器、改变guard/反馈或新声学裁判；lag来源仍是封存未保护D30状态，不假装反馈候选已经可以获得它。

## 现场null、资源与验收边界

32个field主例96438帧：reason0有效37743；reason1首帧32；reason2前帧无效58418；reason3残差零0；reason4固定过去lag当前参考零245。重复另列、future不汇总。
对照D35有效37988，新增固定过去lag无效245帧不能删除原current_max；16个整例参考Float32全零仍不可辨识。field无near真值，不作真人near/KWS或现场回声充分证明。
Python诊断不是allocation-free/实时实现；Host36.025s含来源hash/文件操作，不能推导SSC305 CPU/RSS/栈/热/功耗，不覆盖既有集成资源超限。
负例拒绝旧D35根、仓根、已有D36根均实际exit2；完整125/2469/48文件manifest前后相等，elapsed2.72007417678833s，非抽样。
negative回执SHA256=98efb0e6951ad2f5a77e3bc9a8ecba52801c3e1b826171fec626d563872a7156。
独立stdlib Python反向160点累加全量审计回执status=PASS，elapsed34.126244775019586s；46例126486帧、240原窗、3844项起止锁一致，repeat全量exact、future1247前缀exact。
全部10列/因果索引/reason/null逐帧复算，239879项零值或-1 sentinel精确断言；held/gap最大绝对误差1.4432899320127035e-15、能量最大相对误差2.7788185565234714e-15，均在冻结1e-12内，无容差放宽。
全部46例reason0/1/2/3/4计数=66443/46/59716/0/281；固定过去lag当前参考零281、实际残差零0。零残差分支仅known-answer覆盖，不冒称现场观测。
独立回执SHA256=d4729fe1f725e4e7d5913d1f8b8da7a9bcfa17fc41261cb1da83851cfbd3aed4；无项目/helper import、C编译、DSP或新lag搜索。实际terminal、whole-change与REVIEW后复验以本轮REVIEW为准，不据回执出现推断进程终态。
宿主真实压缩后同线程steady context_ratio=0、required=false恢复；旧v3控制MAJOR/QUESTION未修未用，无compact发送，见CONTEXT_RESUMED。
Provider route unresolved/current为空，知识线NEEDS_REVIEW，无正式归档。AISpeech整链、真人near/KWS、SSC305资源/热/功耗、HIL/E001/PQ、第三方权利和owner分别未闭合。
无commit/push/PR/merge/发布/设备写；下一研究必须独立冻结残差模型的拟合时间、状态、数值/资源预算与失效边界，不从本轮观测直接批准产品保护器。
