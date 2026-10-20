# D15 持续路径诊断：写入锚与门禁候选分离，长窗不能解释全部事件

日期：2026-10-11；experiment=`FE_DEVICE_PERSISTENCE_D15`；[冻结计划](DEVICE_PERSISTENCE_D15_PLAN.zh-CN.md)。
decision=`ENGINEERING_PERSISTENCE_DIAGNOSTIC_NO_PROMOTION`；
`promotion_allowed=false`、`shipping_approved=false`；总目标“全面推进优化迭代”保持active。
D11/D14的原REJECTED不变；本轮只建立测量证据，没有新算法候选或物理/声学资格。

主要新发现：D14 rpm240事件对当前refined=15 samples检验通过，却实际提交首候选anchor=20；
该anchor在提交时的40 ms支持低于原门限。rpm480事件的候选与锚均为16 samples，
100/200 ms也强相关，不能假定加长窗口就会拒绝全部新增事件。
这分别是“检验对象与提交对象分离”和“长期相关支持仍不等于真物理路径”的证据。

## 实际实现、身份与等价

两版精确原source/库/头作为研究对象，原函数体与产品src不改。
隔离副本只有实际函数定义名改为d15_real_ap_sync_track_delay，由同名observer显式转发一次。
测量库身份不同于原库；沿用D12有效入口，不重试已失败的unity --wrap。
[observer fixture](../../../tests/validation/frontend_evolution/device_persistence_d15.c)仅计算和记录，
在调用前断言原state逐字节未变，并保存actual post-HPF/BF stride4 mono及actual render Float32LE。
每帧记录absolute mic/render total，原输入/config与旧receipt hash匹配。

| 验证 | 实际结果 | 边界 |
| --- | --- | --- |
| 两版严格C11编译、实际测量库构建 | exit0 | Host测量 |
| 两版新长窗自测 | exit0 | 800点回绕、8000样本完整历史边界、配对失败、reset、独立线性数组对照 |
| 两版无效参数 | exit2 | 按预期拒绝 |
| 两版×4臂×observe/no-observe | 16次、48,384帧实际处理 | 全长回放，不裁剪触发前缀 |
| 原PCM和全部JSONL | 每次与原D11/D14逐字节一致 | 不只比较终态 |
| 原delay/error/jump/reset/slips | 全帧一致 | 实际HPF/BF后的跟踪器输入 |
| 40 ms shadow | 每个eligible epoch与原helper精确一致 | 保留不足返回0语义 |
| 独立线性样本相关重算 | 15,273个有效/不足分数通过 | 双精度独立求和，绝对误差≤3e-6；未复用observer环形索引 |
| 100/200 ms不足窗口 | -1/not_available | 不伪造填满历史 |
| case07 default/control | trace、PCM/JSONL、mono/render各模式逐字节相同 | 同配置对照，不计为独立场景 |

新observer侧历史800个float仅用于Host测量，不是新增产品state或DUT资源结果。
每种窗口在当时已到达样本上计算，不用未来样本；100/200 ms没有参与算法原门禁或候选选择。
confirm_before>0才标记调用前anchor有效；计数为0的残留值不用作有效anchor分数。
本次restart的新anchor由anchor_after单独记录，不能混为先前有效anchor。

## 原D11事件与D14旧时点重启

每臂每版实际有300个eligible epoch，完整CSV全部保留。
D11 case07（rpm240 far-motion）的最后确认簇为437/447/457帧，refined=15/16/24、anchor=15。
D14在相同旧时点前两次仍为15/16，457帧refined=24距锚9 samples，超过新容差8，
因此confirm从2重启到1、anchor_after=24，原旧事件确实未发生。

D11 case16（rpm480 double-talk-motion）的最后确认簇为597/607/617帧，refined=31/16/16、anchor=31。
D14在607帧距原锚15 samples，重启anchor=16；617帧只累积到2，没有旧事件。
这些事实与D14确认性质fixture一致，但不能推出后续事件消失。

## D14 rpm240：当前候选通过，写入锚支持不足

实际最后确认簇为707/717/727帧，旧delay均为640 samples（40 ms）。
新容差8 samples；refined=20/23/15距首次anchor20均在容差内，计数1→2→third清零，
727帧实际提交anchor20（1.25 ms），公开整数指标显示1 ms。

| 帧 | refined samples | 40 ms refined支持 | 100 ms refined支持 | 200 ms refined支持 | 调用前有效锚 | 40 ms锚支持 |
| --- | ---: | ---: | ---: | ---: | --- | ---: |
| 707 | 20 | 0.357740 | 0.192482 | 0.090262 | 无；此帧设20 | -1 |
| 717 | 23 | 0.331415 | 0.286122 | 0.238572 | 20 | 0.001811 |
| 727 | 15 | 0.158609 | 0.457170 | 0.404646 | 20 | 0.005208 |

727帧short_score=0.348408、40 ms refined支持0.158609，都超过原0.0324门限；
最终写入anchor20的40/100/200 ms支持却为 **0.005208 / 0.001925 / 0.004001**，均低于原门限数值。
算法当前gate实际只检验refined，再由confirm提交保存anchor，不重新核提交对象。
这是可观察的检验/提交对象差异；本轮没有改gate，也不把长窗门限诊断标记升级成新策略验收规则。
同期旧40 ms路径的40 ms支持为0.048778，100/200 ms为0.006790/0.002177。
不同窗口对旧路径的支持也不同，不能用单一高分宣布它正确或错误。

## D14 rpm480：同一新路径在长上下文仍受支持

实际最后确认簇为1227/1237/1247帧，refined全部16 samples，anchor16。
1227帧将先前anchor128重启为16；后两次完成三次确认，1247帧实际写入16（1 ms）。

| 帧 | 调用前旧delay samples | refined | 40 ms新路径支持 | 100 ms新路径支持 | 200 ms新路径支持 |
| --- | ---: | ---: | ---: | ---: | ---: |
| 1227 | 635 | 16 | 0.468420 | 0.238122 | 0.180133 |
| 1237 | 635 | 16 | 0.823983 | 0.797630 | 0.777787 |
| 1247 | 635 | 16 | 0.421809 | 0.501223 | 0.736714 |

1247帧anchor与refined相同，三窗口分数也相同；旧635-sample路径支持为
0.001374 / 0.002553 / 0.000110。单纯以原门限数值检验更长窗口，无法在这些时点拒绝该簇。
但相关强仍不能作为真值或声学获益，更不能豁免D14原冻结的新增jump/reset拒绝。

D11在617帧的旧delay为640，D14在1247帧已因先前drift变为635。
它们不是相同时间/相同状态下的反事实，不能把最后分数差直接归因于确认容差。
同期其他epoch、窗口不足和原D11全部簇均保留，不选择性只报告高分。
case15 tracked1两版全段无route_jump，继续保留为无事件控制，不为它编造确认簇。

## 证据、恢复与下一行动

工件根 `/tmp/audio-fe-device-persistence-d15-20261011`。
16次完整PCM/JSONL/CSV、mono/render Float32LE、配置依赖、原文命令及exit、原/测量source/库/生成头均保留。

| 工件 | SHA256 |
| --- | --- |
| result.json | `4f23dbb3769aeb577fac0b3f255598705e3bb0dcfda9034abfb853ede76e37c7` |
| binding.json | `d3e3901dee23ef8ec30943f3b9aae82380a4b6add92bd941d9f709284869bd98` |

binding锁精确原source与唯一符号替换、独立测量库身份、输入/config依赖、fixture/计划/脚本和全部工件。
临时目录不是永久证据仓；恢复先逐hash核验，丢失/漂移则stale，不凭本文升级可复现声明。
Provider route unresolved，仓内reviewing candidate，未正式归档；无commit/push/设备写。
主线summary/Release成功不批准这次测量；HIL失败保持可见，AISpeech、E001与历史结果不改。

下一独立实现可以围绕“实际提交锚也必须满足所声明的history支持”冻结单因果契约，
保护D13正常获取/持续切换及D9获取，不与本轮测量互相批准。
该一致性改动本身也不能承诺解决rpm480的强相关事件：还需要独立校准的参考时间轴/真实延迟、
人声标签及声学验收，判断配置初始40 ms到1 ms的迁移实际含义。
本轮不继续扫描窗口/容差，不把零新增jump当作声学改善的唯一目标。
总goal保持active；本次测量完成不等于整体方案落地或产品资格完成。
