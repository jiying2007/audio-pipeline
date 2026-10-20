# D26 设备开发数据双状态回放结果

日期2026-10-11；experiment=FE_DEVICE_FIELD_D26；decision=FIELD_SHADOW_DIAGNOSTIC_NO_PROMOTION。
总体目标active；research_algorithm_changed=false、shipping_algorithm_changed=false、promotion_allowed=false、shipping_approved=false。

66次真实执行均terminal exit0，原状态估计回声和残差逐字节复现D19。16个激活的主shadow臂累计发生538次输出bank切换，每臂5～55次。固定窗口的残差能量变化有正有负；频繁往返切换是下一步应处理的工程问题，不能把能量下降解释为声学改善。

## 冻结输入与实际执行

遵循[冻结计划](DEVICE_FIELD_D26_PLAN.zh-CN.md)及[实施审查修正](DEVICE_FIELD_D26_AMENDMENT.zh-CN.md)。
16个设备development场景×fixed1/used0×keep/shadow共64次；case07/used0/shadow另做repeat和future，共66次。
实际处理198924帧、31827840个单通道输入样本，六输出trace共190967040个float样本。
直接使用冻结D19的AEC输入、对应参考及同臂真实Activity far/dt；原119文件锁与源/库/依赖起止hash核一致。
原MDF库SHA256为eb5b0c784c316e71d6ed9f58db6cb66f190b631daa00c55a94032168d5a47aa4。
这不是完整双麦CALL/NS/RES/AGC/QIVW回放，也不是AISpeech产品集成或真人近端保护验证。

通知取自冻结D16 rejected候选的实际reset/jump counter，全部事件保留，每场景仅取首个作为外部控制时间。
8场景有通知，另8场景无通知；每个有通知场景原记录恰一个事件。通知不是物理路径真值，不批准D16候选。
primary始终不reset；shadow通知帧处理前复制primary并full reset第二状态。冻结D24选择器参数和无crossfade行为均未改变。

| case | 原首通知帧 | fixed1切换次数 | used0切换次数 |
| --- | ---: | ---: | ---: |
| 03 | 457 | 53 | 41 |
| 04 | 1057 | 38 | 38 |
| 07 | 1247 | 29 | 27 |
| 08 | 1977 | 18 | 21 |
| 11 | 457 | 54 | 55 |
| 12 | 627 | 41 | 45 |
| 15 | 2557 | 7 | 5 |
| 16 | 1247 | 38 | 28 |

无通知的8场景，两坐标keep/shadow均保持原输出；shadow不激活，shadow trace为零且其统计为null。
18个实际执行激活第二状态，包括16主臂与repeat/future；其余48次不激活。

## 固定窗口测量

以下为shadow-minus-keep的selected残差RMS差，单位dB；正值代表残差能量增加。
窗口沿用原PTS固定4～6、10～12、19～21秒及whole，不增加事件居中窗口。
没有clean target，这些数值不是ERLE、残回改善、人声误差或音质结论。

| case/坐标 | whole | 4～6s | 10～12s | 19～21s |
| --- | ---: | ---: | ---: | ---: |
| 03/fixed1 | -0.495097 | -1.705195 | -0.229743 | +0.027353 |
| 03/used0 | -0.360000 | -1.792524 | -0.535362 | -0.195437 |
| 04/fixed1 | -0.361989 | 0 | +0.290219 | -0.196926 |
| 04/used0 | -0.230188 | 0 | +0.278634 | -0.013686 |
| 07/fixed1 | -0.106520 | 0 | 0 | +0.147828 |
| 07/used0 | -0.079502 | 0 | 0 | +0.002007 |
| 08/fixed1 | -0.353044 | 0 | 0 | -1.495926 |
| 08/used0 | -0.287886 | 0 | 0 | -1.019413 |
| 11/fixed1 | -0.491331 | -1.605819 | -0.598472 | +0.015542 |
| 11/used0 | -0.310582 | -1.201236 | -0.021253 | +0.008997 |
| 12/fixed1 | -0.003193 | 0 | -0.214879 | +0.131664 |
| 12/used0 | +0.169087 | 0 | +0.063475 | +0.163757 |
| 15/fixed1 | +0.009256 | 0 | 0 | 0 |
| 15/used0 | +0.005854 | 0 | 0 | 0 |
| 16/fixed1 | -0.019331 | 0 | 0 | -0.235501 |
| 16/used0 | -0.015306 | 0 | 0 | -0.117242 |

其他无通知主场景各窗口差值全为0。case15通知在25.57秒，晚于最后固定窗口，窗口0不能解释为全程没有变化。
原始精度数值、每次切换帧和方向、门控计数、相邻样本边界差以及两bank首样本差均保存于result.json。
未制定听感阈值，不能据边界记录宣称无点击。只有完整active的窗口才报告shadow统计；跨inactive的whole和keep均为null。

## 因果、资源及验证

case07/used0重复进程的六trace和两CSV全量逐字节相同，重复仍27次切换。
future从通知帧起将原mic/ref反号，gate/通知保持冻结，通知前八文件前缀相同；后半实际25次切换。
future只是有限因果控制，后半gate未重新检测，不能参与设备选型。
额外AEC状态实测sizeof为33020字节；66次shadow总调用32564次，SYNC调用0。
这些是状态与调用计数，不是目标DUT总RAM、CPU、功耗、热或实时预算。

严格编译exit0；5个完整非法参数sentinel在任何输出打开前拒绝exit2且预置文件不变；66次测量exit0。
非仓cwd help、dry-run、5项定向测试均terminal exit0。执行retry为0。
实施前独立静态审查发现一次MAJOR-1：误用D19九列control表校验D22八列state表。
已在首编译/测量前修复并独立复审通过，正负例均覆盖，未制造失败DSP执行记录。

工件根：`/tmp/audio-fe-device-field-d26-20261011`；709个生成工件绑定。
result SHA256：51c2007f9dfa74a8f6ea032dd8caba79137b34a0379da55c79e69dac016ef42c。
binding SHA256：4dc0a3459d686abc5a86b6c7ad423bfa4294102ee5dfbbc0b63451ae2a097309。
独立actual审计及修正版均已terminal exit0，不导入本轮测量器、不重DSP。
66例/396trace的190967040个float、state和selector各198924行、264窗口组、548有效bank组、244null组、128差值及132个D19基线文件全部核验。
590次全部执行切换包含主臂538次及repeat/future的27/25次；窗口RMS/peak和差值最大误差0，独立AEC代数最大误差1.4901161193847656e-08。
审计首版正确核各例代数但未更新回执最大值汇总字段；首版脚本和回执原字节保留，修正后全量纯工件复审1次，DSP重试0。
首版脚本/回执SHA256：544dff4616e67db9e17de637a17197d388eb9204e6b326c8c9f5aea5fe047e04 / 0d467cdbadb3b8694a81d43019729792794985a31092f67249be532cd94ad7c1。
最终独立审计脚本/回执SHA256：bcd23ee2159e8c18cfda92ae6d8dea2b3d9b185c4a794ec9c127ac6d0312ed63 / f87e6f5cdb74d1cc83ee96e3541c05ae5dc9a5c2303e9a3884142d91851656b0。
六项missing/真实输入×旧D25/新D26/仓根工具负例均真实拒绝exit2；D25完整431文件、D26完整713文件manifest前后逐hash不变。
仓根只核潜在measurement-invalid影响路径未写，不声称锁住所有既有dirty。
负例脚本/回执SHA256：0c96aa18269e638b424980415604e30fd81a861cb453dcbe4773392cc15e46ce / 1016c037a52f7f3e7b62b5f423ff334023e9a9958218d29b5318d03c95b83a52。

## 后续边界

whole-change首轮发现一项MINOR披露问题：README将两条primary输出逐字节一致写成了原AEC状态一致。
已收窄为primary估计回声和残差，不声称完整MDF状态转储等价；v1快照保留，修正文档后重新冻结v2。
下一轮须针对频繁往返切换冻结单因果假设、输出边界与测量合同，再做有界研究实验；不得直接增加参数直到绿灯。
真实开发数据可用于研究选择，不能替代独立验证或blind；最低残差能量不能自证声学收益。
真人双讲、真实路径检测、完整后处理、目标资源与HIL/E001/产品资格仍各自未闭合。
未commit/push/merge、未部署设备、未改产品默认。Provider route unresolved，知识线NEEDS_REVIEW；本记录仅仓内reviewing candidate。
