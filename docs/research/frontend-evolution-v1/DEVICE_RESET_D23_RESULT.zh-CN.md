# D23 完整重置收益与误通知代价

日期2026-10-11；experiment=FE_DEVICE_RESET_D23；data_role=synthetic-engineering；总体目标active。
结论：已知A→B切换处完整reset改善固定构造的恢复，但稳定A/B误reset显著损失已经收敛的消回声能力。
decision=RESET_BENEFIT_FALSE_EVENT_COST_DIAGNOSTIC_NO_PROMOTION；algorithm_changed=false；promotion_allowed=false；shipping_approved=false。
[冻结合同](DEVICE_RESET_D23_PLAN.zh-CN.md)、[独立审查](DEVICE_RESET_D23_REVIEW.zh-CN.md)、[逐byte等价的D22保持状态基线](DEVICE_MULTIPATH_D22_RESULT.zh-CN.md)。

## 实际操作和等价控制

17次真实20秒/2000帧执行全部exit0，严格C11/-ffp-contract=off编译exit0，非法参数exit2；retry_used=0。
冻结D22 C fixture由新研究wrapper直接include，构造/参数/门控/旧库均不改；只是第1000帧处理前调用一次原ap_aec_backend_reset。
该操作同时清权重、参考频域历史、prev_ref及功率并重新建立状态，不能将结果单独归为清权重收益。
六keep对D22各自四trace/完整CSV逐byte相同；各reset对keep输入全程相同，四trace前160000点/前1000帧CSV逐byte同。
原reset返回时实际weight_l2/x_power_total/steady_frames均0、x_head47；真实调用次数1/帧1000，keep调用0及事件观测null。
三个reset negative disabled/hold/zero前权重0且全程echo零/residual等mic/权重零；repeat全量同，future前半同。
单通道内部AEC、mu0.22f/taps1536/stride2、enabled1/far1/dt0、16k/160点；SYNC bridge实际调用0，不是完整双麦CALL或设备执行。
全trace有限/长度正确/完整构造匹配，AEC代数误差≤1e-6；源/库/头/宏/输入/工具身份起止相同。

实际reset前权重平方和如下（weight_l2不是实际适配次数）；switch与A拥有相同事件前历史：

| path / ref | reset_pre_weight_l2 |
| --- | ---: |
| A / 16 | 10.742406240469727 |
| A / 20 | 10.747831798811058 |
| B / 16 | 7.162447188812336 |
| B / 20 | 7.165788400795892 |
| switch / 16 | 10.742406240469727 |
| switch / 20 | 10.747831798811058 |

## 固定窗口收益与代价

仅已知无近端/噪声工程纯回声计算冻结ERLE，非canonical独立声学评分。单位dB，窗口、时长和公式未调整。
六reset主臂的whole与固定六窗如下；keep值完整逐byte复现D22，并在本轮result保留。

| path / ref reset | whole | 0–2s | 8–10s | 10–10.5s | 10.5–12s | 12–14s | 18–20s |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| A / 16 | 11.744716 | 5.394948 | 40.968947 | 2.724017 | 6.689782 | 14.271602 | 41.245671 |
| A / 20 | 11.607225 | 5.229140 | 41.182499 | 2.499632 | 6.608021 | 14.268001 | 41.531138 |
| B / 16 | 11.188113 | 4.806574 | 41.139136 | 1.999688 | 6.166652 | 13.756363 | 40.971763 |
| B / 20 | 11.121096 | 4.724713 | 41.406797 | 1.866208 | 6.123778 | 13.778344 | 41.213640 |
| switch / 16 | 11.495410 | 5.394948 | 40.968947 | 1.999688 | 6.166652 | 13.756363 | 40.971763 |
| switch / 20 | 11.381070 | 5.229140 | 41.182499 | 1.866208 | 6.123778 | 13.778344 | 41.213640 |

reset-minus-keep工程ERLE差如下；同输入下residual RMS差为反号，完整精度/峰值见result：

| path / ref | whole | 0–2s | 8–10s | 10–10.5s | 10.5–12s | 12–14s | 18–20s |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| A / 16 | -3.049188 | 0 | 0 | -44.580475 | -44.896351 | -44.939525 | -45.288141 |
| A / 20 | -3.038859 | 0 | 0 | -45.106867 | -45.260558 | -45.280358 | -45.463126 |
| B / 16 | -3.089784 | 0 | 0 | -45.395386 | -45.576140 | -45.610672 | -45.764052 |
| B / 20 | -3.093986 | 0 | 0 | -45.849855 | -46.004925 | -45.993360 | -45.983008 |
| switch / 16 | +2.561543 | 0 | 0 | +4.592672 | +4.464389 | +4.519994 | +4.647182 |
| switch / 20 | +2.540292 | 0 | 0 | +4.550133 | +4.492612 | +4.535236 | +4.580512 |

真switch首窗由keep的-2.592984/-2.683925改善到reset的1.999688/1.866208，改善不是完全消除回声或瞬时收敛。
稳定A/B误reset的切换后窗口损失44.58～46.00dB；负结果原样保留，不能只用真事件收益批准无条件reset。
误reset末窗仍在重新适配，不能把程序成功或后期ERLE为正当作无代价。fixture通知真值不提供真实事件检测可靠性。
三negative的whole/全部窗口ERLE恰0；repeat与switch/ref20/reset同；future前两窗同、whole11.432145、末窗41.316519。

## 身份、证据与下一步

工件根`/tmp/audio-fe-device-reset-d23-20261011`：result SHA256
`34999146de3ef13d1364d289165cc5381c420fb4e4f40a40cc31d0d484803f60`；binding SHA256
`e5e7ce39b20a9a077439cb2417dbd0eb26065c0248c09e9c011821d88167859a`，绑定106份实际执行工件。
库SHA256 `eb5b0c784c316e71d6ed9f58db6cb66f190b631daa00c55a94032168d5a47aa4`；D22完整源/70工件及原119输入锁继承。
非仓cwd help/dry-run及4项事件回执/差值方向/目录归属测试通过；独立actual与whole-change审查见REVIEW。
独立actual audit未导入项目测量函数、未重跑DSP，复核3,423次hash、68条trace/21,760,000个float、
10,880,000个输入样本逐byte构造、34,000帧CSV、119组统计和42组差值；11个实际reset的前权重exact等于CSV第999帧。
返回后零权重/功率/steady、head47以及随后调度重启均核实；AEC代数最大误差7.450580596923828e-9，统计/差值复算差1.4210854715202004e-14。
独立审计回执`/tmp/audio-device-d23-independent-audit.json` SHA256
`4bd7f6fe2d8b67a33f2b9951a1a3773dff10ed071995dffe98847ecbdcf7b665`。

```sh
rtk python3 tools/codex_assets/device_reset.py --help
rtk python3 tools/codex_assets/device_reset.py --root tests/audio --output /tmp/d23-new-output --dry-run
rtk python3 tests/validation/frontend_evolution/test_device_reset.py
```

下一阶段须研究有保护的状态处理，保留稳定路径误操作控制与真实切换对照；单凭事件通知执行破坏性状态清除不满足本轮收益/代价证据。
该方向尚未实施，不从合成结果批准事件检测、产品默认、AISpeech接入、真人保护、ASR/KWS/真实资源/HIL/E001/owner资格。
Provider route unresolved仍NEEDS_REVIEW；本文为仓内reviewing candidate，未正式归档。
