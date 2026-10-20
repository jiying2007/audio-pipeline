# D22 多反射与路径切换工程结果

日期2026-10-11；experiment=FE_DEVICE_MULTIPATH_D22；data_role=synthetic-engineering。
结论：两条静态多反射路径都能收敛；保留A状态切到B时出现短时工程残差放大，随后恢复。
decision=MULTIPATH_TRANSITION_DIAGNOSTIC_NO_PROMOTION；algorithm_changed=false；promotion_allowed=false；shipping_approved=false；总体目标active。
[冻结合同](DEVICE_MULTIPATH_D22_PLAN.zh-CN.md)、[独立审查](DEVICE_MULTIPATH_D22_REVIEW.zh-CN.md)。

## 实际执行与控制

11次真实20秒/2000帧MDF执行全部exit0，严格C11及-ffp-contract=off编译exit0，非法参数exit2。
继承D18真实库与CALL AEC mu0.22f/taps1536/stride2，enabled1/far1/dt0固定；仅单通道AEC内部API，不是完整双麦CALL。
路径A=(48,0.5)/(176,-0.25)/(400,0.125)，B=(80,0.375)/(240,-0.125)/(560,0.25)，按冻结顺序float32乘加。
switch在样本160000（10秒）由A切B，沿绝对时间轴取过去raw；AEC只在开始初始化，切换时没有reset。
六主臂分别static-A/static-B/switch × reference offset16/20，信号无近端、噪声、量化、非线性或真实房间。
三个negative disabled/hold/zero均echo零、residual等mic、weight_l2零。
repeat四trace/CSV全量逐byte相同；future只改变raw后半，前160000点四trace及1000帧CSV逐byte同。
switch对static-A同坐标前半四trace/CSV完全同；switch对static-B后半mic/reference完全同，状态和输出保留不同适配历史。
SYNC bridge调用0，真实CSV读取返回state；weight_l2是复权重平方和，不是实际适配次数。
全trace有限、长度正确、已知构造逐byte核，mic≈echo+residual≤1e-6；继承输入/源码/库/宏与新工具身份起止相同。

## 固定窗口工程ERLE

仅已知无近端/噪声纯回声构造使用冻结ERLE公式，不属于canonical独立声学评分，也不表示设备听感。
窗口不移位、不延长，负值保留；单位dB。

| path / ref | whole | 0–2s | 8–10s | 10–10.5s | 10.5–12s | 12–14s | 18–20s |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| A / 16 | 14.793904 | 5.394948 | 40.968947 | 47.304491 | 51.586132 | 59.211126 | 86.533813 |
| A / 20 | 14.646084 | 5.229140 | 41.182499 | 47.606499 | 51.868579 | 59.548359 | 86.994263 |
| B / 16 | 14.277898 | 4.806574 | 41.139136 | 47.395073 | 51.742792 | 59.367035 | 86.735816 |
| B / 20 | 14.215081 | 4.724713 | 41.406797 | 47.716063 | 52.128704 | 59.771704 | 87.196647 |
| switch / 16 | 8.933867 | 5.394948 | 40.968947 | -2.592984 | 1.702263 | 9.236369 | 36.324582 |
| switch / 20 | 8.840778 | 5.229140 | 41.182499 | -2.683925 | 1.631166 | 9.243108 | 36.633128 |

三negative的whole及全部窗口ERLE恰0。repeat与switch/ref20完全一致；future前两窗同，whole8.848054、末窗36.612183。
switch切换后首窗ERLE为负，表示该窗口残差能量高于已知mic回声能量；不将进程exit0或全量finite当作效果改善。
静态B末窗已适配近20秒，switch在B上仅适配近10秒且继承A权重；约50dB差不能当纯路径收益或同等适配时间性能差。

offset20-offset16工程ERLE差如下；对应residual RMS差为反号（完整精度见result），配对mic逐byte同：

| path | whole | 0–2s | 8–10s | 10–10.5s | 10.5–12s | 12–14s | 18–20s |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| A | -0.147820 | -0.165808 | +0.213551 | +0.302007 | +0.282447 | +0.337232 | +0.460451 |
| B | -0.062816 | -0.081861 | +0.267661 | +0.320990 | +0.385911 | +0.404670 | +0.460831 |
| switch | -0.093089 | -0.165808 | +0.213551 | -0.090941 | -0.071097 | +0.006739 | +0.308546 |

切换后switch-minus-static-B工程ERLE差如下；两者后半输入一致，适配历史不同，对应residual RMS差为反号：

| ref offset | 10–10.5s | 10.5–12s | 12–14s | 18–20s |
| --- | ---: | ---: | ---: | ---: |
| 16 | -49.988057 | -50.040530 | -50.130666 | -50.411234 |
| 20 | -50.399988 | -50.497538 | -50.528596 | -50.563519 |

坐标差随阶段变号，不能选offset20作为通用改进。相同输入但不同旧路径历史提供下一阶段受控状态策略实验的依据。
当前尚未执行reset策略、路径检测或误通知控制，不能宣称已修复恢复问题。

## 身份、验证与接续

工件根`/tmp/audio-fe-device-multipath-d22-20261011`：result SHA256
`96c7e749eac0e435b28e9f0ffdfe4d7985adc2e7bc7e4c45b8b25ac5ac77dd78`；binding SHA256
`fdcd9b3e4ead2e3d7767a30a1eacaefdcad8c6fe9f64e7ca88a505e48b727a19`，绑定70份实际执行工件。
库SHA256 `eb5b0c784c316e71d6ed9f58db6cb66f190b631daa00c55a94032168d5a47aa4`；D21源/70工件完整核锁，原119输入锁继承。
非仓cwd help/dry-run及4项已知答案/float32顺序/目录归属测试通过；独立工件与whole-change审查单列于REVIEW。
独立全量审计未导入本工具分析函数、未重跑DSP：3,258次hash检查，44条trace/14,080,000个float、
独立构造7,040,000个mic/reference样本逐byte同，22,000帧CSV、77组统计、21组坐标配对差及8组切换后历史对照均通过。
AEC代数最大误差7.450580596923828e-9，统计及差值最大复算差1.4210854715202004e-14，均满足冻结范围。
独立审计回执`/tmp/audio-device-d22-independent-audit.json` SHA256
`3c1d20e7c670c1ff7c0e59774895277afe38925ceb8724cdee9300f280987f85`。

```sh
rtk python3 tools/codex_assets/device_multipath.py --help
rtk python3 tools/codex_assets/device_multipath.py --root tests/audio --output /tmp/d22-new-output --dry-run
rtk python3 tests/validation/frontend_evolution/test_device_multipath.py
```

下一阶段对相同已知切换冻结状态保持/reset对照，并加入稳定路径误reset控制、切换前逐byte等价及同输入同时间比较。
该接续可检验状态处理的瞬态代价，但不把已知切换通知当设备路径检测能力，不据合成工程收益改变产品默认。
历史候选拒绝、AISpeech链路、真人/独立声学/ASR/KWS/真实资源/HIL/E001/owner资格仍分别待验。
Provider route unresolved，知识线NEEDS_REVIEW；本文仅仓内reviewing candidate，未正式归档。
