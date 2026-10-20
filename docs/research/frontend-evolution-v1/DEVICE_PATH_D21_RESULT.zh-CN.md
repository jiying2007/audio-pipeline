# D21 固定门控与已知路径工程结果

日期2026-10-11；experiment=FE_DEVICE_PATH_D21。
结论：本轮三个已知纯延迟路径都收敛，4点参考坐标变化的影响随路径和收敛阶段改变，未形成通用坐标选择。
decision=KNOWN_PATH_COORDINATE_DIAGNOSTIC_NO_PROMOTION；data_role=synthetic-engineering；algorithm_changed=false。
promotion_allowed=false、shipping_approved=false；总体目标active。
[冻结合同](DEVICE_PATH_D21_PLAN.zh-CN.md)、[执行前修正](DEVICE_PATH_D21_AMENDMENT.zh-CN.md)、[独立审查](DEVICE_PATH_D21_REVIEW.zh-CN.md)。

## 实际执行与约束

11次实际20秒/2000帧独立MDF执行全部exit0，严格C11编译通过，非法输入exit2。
继承冻结D18真实库，CALL AEC mu0.22f/taps1536/stride2；直接单通道AEC内部API，未运行完整双麦CALL。
六主臂均固定enabled1/far1/dt0；mic=0.5×raw延迟32/48/64点，reference延迟16或20点。
原始信号为冻结xorshift宽带确定性序列，所有构造由Python完整逐byte核，不是设备播放、真人或房间录音。
三negative disabled/hold/zero全部echo零、residual等mic、权重平方和零。
repeat四trace/完整CSV逐byte相同；future只改后半raw，前160000点trace及1000帧CSV逐byte相同。
unity链接桥实际SYNC调用数0；库/生成头/实际宏/runner/工具/输入起止身份相同，AEC函数体未改。
首次依赖根误引用被哈希预检拒绝，尚未编译或执行；失败回执保留，retry_used=1。

## 纯回声工程衰减

仅在已知无近端/无噪声构造中计算固定公式ERLE；数值不是canonical独立声学评分，更不是设备残回或听感结果。
整段含收敛初期；固定窗口不移位、不挑选最佳值。单位dB。

| path / ref offset | whole | 0–2s | 4–6s | 10–12s | 18–20s |
| --- | ---: | ---: | ---: | ---: | ---: |
| 32 / 16 | 15.132445 | 5.649074 | 24.404812 | 52.463335 | 89.147939 |
| 32 / 20 | 15.350056 | 5.854213 | 24.749608 | 52.915863 | 89.576109 |
| 48 / 16 | 15.065027 | 5.650146 | 23.548427 | 50.506779 | 86.869747 |
| 48 / 20 | 14.884625 | 5.446858 | 23.602018 | 50.782828 | 87.331694 |
| 64 / 16 | 14.392253 | 4.920904 | 23.456305 | 51.340863 | 88.099337 |
| 64 / 20 | 14.449507 | 4.982360 | 23.474987 | 51.318043 | 88.067413 |

三个negative whole和全部窗口ERLE恰0，证明这些控制中没有估计回声或权重增长。
各path的offset20-offset16 ERLE差如下，配对mic逐byte相同：

| path | whole | 0–2s | 4–6s | 10–12s | 18–20s |
| --- | ---: | ---: | ---: | ---: | ---: |
| 32 | +0.217611 | +0.205139 | +0.344797 | +0.452527 | +0.428170 |
| 48 | -0.180402 | -0.203288 | +0.053591 | +0.276049 | +0.461947 |
| 64 | +0.057254 | +0.061456 | +0.018682 | -0.022821 | -0.031924 |

对应residual RMS差如下（单位dB），完整精度以及各窗mic/residual峰值保存在result：

| path | whole | 0–2s | 4–6s | 10–12s | 18–20s |
| --- | ---: | ---: | ---: | ---: | ---: |
| 32 | -0.217611 | -0.205139 | -0.344797 | -0.452527 | -0.428170 |
| 48 | +0.180402 | +0.203288 | -0.053591 | -0.276049 | -0.461947 |
| 64 | -0.057254 | -0.061456 | -0.018682 | +0.022821 | +0.031924 |

路径48的初期与后期差值变号，路径64后两个窗口变号。不能从D19设备整段能量差推断20点普遍改善。
本轮没有复现已知简单路径中的发散或无法收敛，但它不覆盖多反射、噪声、近端、非线性及运动路径。
CSV来自真实返回state，权重平方和不当实际更新次数；不据高ERLE批准产品资格。

## 身份、验证与接续

工件根`/tmp/audio-fe-device-path-d21-20261011`：result SHA256
`7441e49b516a810fdda0f7acc91095771ddb29a4c9fd2fab5b376205bd4c55c0`；binding SHA256
`a368f3f69ffbfe1a567343e4be96c8c06fbfdc5de97f80e49a59b025ff4539d9`，绑定70份工件。
库SHA256 `eb5b0c784c316e71d6ed9f58db6cb66f190b631daa00c55a94032168d5a47aa4`，独立runner与库身份分别绑定。
非仓cwd help/dry-run和4项测量已知答案/负例通过，实际工程回放与独立工件审计分别验收。
独立审计未导入本工具分析函数，核2,967项hash、44条trace/14,080,000点、22,000帧state CSV、55组统计及15组配对差。
最大统计复算差为7.1054e-15（浮点舍入量级），AEC代数最大误差3.7253e-9，三个negative/repeat/future均通过。
审计回执`/tmp/audio-device-d21-independent-audit.json` SHA256为
`3921eb59d59769aad16c6c3263b7b0dfe9878976e3a3b6afedf49d0b8cb933b4`。

```sh
rtk python3 tools/codex_assets/device_path.py --help
rtk python3 tools/codex_assets/device_path.py --root tests/audio --output /tmp/d21-new-output --dry-run
rtk python3 tests/validation/frontend_evolution/test_device_path.py
```

下一阶段应增加冻结的多反射/路径切换控制，并分别保持门控和信号角色，核收敛/恢复与参考坐标响应；
只有确认可复现缺陷或固定候选假设后才修改算法，不对这三条简单路径调参。
本实验不能解释设备全部差异；历史候选REJECTED、AISpeech产品链路、ASR/KWS、真实物理/HIL/E001/owner资格保持独立。
Provider route unresolved，知识线NEEDS_REVIEW；本文为仓内reviewing candidate，未正式归档。
