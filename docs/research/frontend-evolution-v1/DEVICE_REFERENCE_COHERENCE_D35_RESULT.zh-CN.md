# D35 历史参考相关性诊断结果

日期2026-10-11；experiment=FE_DEVICE_REFERENCE_COHERENCE_D35。
结论：固定历史参考搜索提供了同帧零延迟内积遗漏的残余回声信息，但切换near与纯echo仍重叠，不能直接批准检测阈值或保护候选。
decision=REFERENCE_COHERENCE_DIAGNOSTIC_NO_PROMOTION；promotion_allowed=false；shipping_approved=false；总体native优化目标active。

## 冻结合同与实际执行

PLAN SHA256=cb8bf6c715e44c2e58cb098dec41e6c997fb7a33f1d688e652e76da6dbd7ab3b。
AMEND SHA256=d6f2530524125811908ca75775cd24650e3e24cd9c66e39b365d5206e9198fca；保留实施前D31来源锁缺口与独立MINOR-1异常回执缺口，最小修复后fresh实施Spec/Quality PASS、unresolved0。
接受根=/tmp/audio-fe-device-reference-coherence-d35-20261011。
result/binding SHA256=a18f8b4e678410a043dcbb4b5e2d8ebb68df70156f52ec6f18fad02d09cf58dc / a913b140255a0a84b75e3604517536d0644c4895093d071f359fe25b5b76a6ca。
四份wrapper execution-0..3实际exit0：非仓help、完整deep dry-run、7tests、主测量；dry根未创建。
46次standalone C observer、126486帧、193907596个有效历史范围内的tested lag candidates，AEC/DSP重跑0，retry0。
固定160samples帧，lag0..1535，startup只用完整历史；不扣均值、不补零或利用未来样本；max和固定1e-12数值tie选首lag分别记录。
全部126486帧zero-lag与D31封存内积在固定1e-12内一致；重复CSV全量一致、future在notify1247之前前缀一致，future统计为null。
3675项input_files、6项source_files及实际runner起止身份一致；binding封存104工件。数据仍为已查看development及合成engineering，adaptive reuse，无独立validation/blind资格。

## 增量信息与重叠

下表为固定原near区间[1000,1200)和[1600,1800)的nearest-rank统计；纯echo列使用独立echo实例的全部2000帧。
dt与unguarded名称来自原来源角色，本轮实际消费D30未保护primary残差，两名称在所列near统计相同，不能当独立重复实验。

| 场景 | 纯echo zero-lag p50 | 纯echo历史max p50 | 首near历史max p50 / p90 / max | 第二near历史max p50 |
| --- | ---: | ---: | ---: | ---: |
| A-r16 | 0.002897 | 0.444016 | 0.075785 / 0.090912 / 0.123588 | 0.075032 |
| A-r20 | 0.003104 | 0.421669 | 0.076695 / 0.090874 / 0.123448 | 0.074928 |
| ABA-r16 | 0.002642 | 0.449607 | 0.188908 / 0.293232 / 0.424288 | 0.075832 |
| ABA-r20 | 0.002987 | 0.443324 | 0.189531 / 0.295693 / 0.422626 | 0.074994 |

零延迟量级接近时，历史搜索能解释额外残余成分，这是诊断增量；不是由本轮导出真实声学路径或物理延迟校准。
纯echo整例chosen_lag p10/p50/p90在r16均32、r20均28；ABA首near仍为32/32/64或28/28/60，说明near可同时含可解释echo，不能把高相关直接解释成没有near。
原D32 monitor纯ABAecho误触发221/218帧的上一帧，历史max p10/p50/p90分别0.342385/0.422285/0.488709与0.339604/0.419436/0.486456。
这些纯echo触发前帧的min约0.268299/0.268105，与ABA首near最高约0.424288/0.422626存在重叠。
静态near和第二near的低相关不能掩盖ABA首near；本轮未选阈值、未拟合分类器、未改变guard或反馈，也未重评分原声学窗口。
1536延迟取最大值存在有限样本搜索偏差；各lag并非独立假设，不能把峰值作显著性概率或真人辨识证明。

## 现场数据与不可辨识边界

32个field主例共96438帧：37988帧有效历史相关，58450帧null；repeat另列，future不汇总。
16个整例null的field来源原reference逐Float32均为0，不能把null当近端检测正确或证明现场没有回声。
其余field也含部分无效帧；无near真值，不从相关性或输出稳定推导真人near/KWS资格。
保留原240个whole/window范围，只向内取完整160点帧并报告边界丢弃样本；未选择有利窗口。

## 资源、负例与收口责任

standalone observer报告局部对象20400B；不是完整前端资源，也不改变D29原71196B、D30原71224B集成预算结论。
46个Host观察子命令elapsed合计45.5429608822s，包括进程/文件操作，不能换算SSC305实时CPU、RSS、栈、热或功耗资格。
C严格编译和self-test实际exit0；非法0/-1/nan/10001/空帧数及argc拒绝exit2，已有sentinel保持。
输出拒绝旧D34根、仓根、已有D35根均实际exit2；完整69/2460/105文件manifest分别前后相等，negative elapsed2.7940175533s，非抽样核验。
独立C/Python首次全量审计真实exit0，elapsed81.235357s：46例/126486帧/193907596个lag/240原窗/126486零延迟锚，3786项锁起止一致；chosen lag整数全部相同，feature最大绝对误差1.6653345369377348e-15，能量最大相对误差2.7788185565234714e-15。
独立审计回执SHA256=f33b4ce15d1030f9b035e42d92c194fdd37490fc5c7eb1c86cc21a69dc920d3c；无项目/helper import或AEC重跑。
root审阅发现首审对零能量和-1 sentinel使用容差，未独立闭合精确零值合同；原审计源码/回执保持，追加独立精确补充，不放宽门限。
补充首次实际exit0，elapsed27.250169s，回执SHA256=13192eb784710cf591aade0b3bed6c605f00b06295b70657c75f83612d52bb63；全部126486帧的60083个reference零窗口zero-lag exact -1、59750个all-invalid窗口max/chosen/zero/lag exact -1。
实际残差全零窗口数量为0，补充检查的零能量分支未被这批数据触发；C self-test提供零残差known-answer检查，不能冒称真人/现场零残差观测。两份独立回执结合闭合本轮数值审计。
whole-change与REVIEW后复验的实际终态另见本轮REVIEW，不提前声称本地里程碑已经收口。
下一单因果研究需处理时间上的可解释性与混合near/echo；独立冻结后才可实验，不从本轮最大相关性自动生成阈值或候选。
AISpeech整链、真人near/KWS、目标CPU/RSS/栈/热/功耗、HIL/E001/PQ、第三方权利与产品owner分别未闭合。
Provider route unresolved/current为空，知识线NEEDS_REVIEW，无正式归档；无commit/push/PR/merge/发布/设备写。
