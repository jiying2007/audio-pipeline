# D19 同状态阶段诊断结果

日期2026-10-11；experiment=FE_DEVICE_STAGES_D19。
结论：32次完整回放的即时阶段观测有效，差异首先出现在AEC估计回声/残差，完整后处理改变差距。
决策`SAME_STATE_STAGE_DIAGNOSTIC_NO_PROMOTION`；algorithm_changed=false、promotion_allowed=false、shipping_approved=false。
总体目标active；独立工件/whole-change审查见[D19审查](DEVICE_STAGES_D19_REVIEW.zh-CN.md)。

## 执行与等价

[冻结计划](DEVICE_STAGES_D19_PLAN.zh-CN.md)与[测量修正](DEVICE_STAGES_D19_AMENDMENT.zh-CN.md)保持16个development场景、
fixed1(raw延迟16点)与used0(raw延迟20点)两个固定坐标。32份PCM、32份原JSONL和32份reference全部与D18逐字节相同。
96,438帧、15,430,080点/阶段，共5条Float32LE trace；所有值有限，帧顺序与相邻阶段输入一致。
AEC input≈echo+residual最大绝对误差`1.4901161193847656e-08`，小于冻结`1e-6`舍入限。
8个零参考场景的全部阶段在两臂间逐字节相同；16个场景AEC输入全相同。
每帧AEC→NS→AGC各一次，独立时域RES零调用。full CALL的频域RES集成于NS，因此仅报告NS/频域RES联合阶段。
启动欠载fixed1=1、used0=0；原JSONL不变，不能将启动差异作为新的稳定性通过。

首次严格编译失败完整保留，未执行DSP；修正版从实际库构建取得内部编译宏后通过。
3200点参考已知答案、非法参数exit2、3项测量测试均通过；独立6个创建前拒绝负例已闭合MAJOR-1。
这是新测量库和runner的观测中立证据，不能称与D18库的二进制身份相同。

独立审计直接读取工件和原events/frames CSV，以整数有理运算重建PTS窗口，未调用本工具统计函数。
1,561项hash、160条trace共77,150,400点、96,438帧控制CSV、96份D18等价文件均通过。
640组whole/窗口RMS与peak、320个双臂差和128个AGC前后差独立复算最大误差均为0。
审计回执`/tmp/audio-device-d19-independent-audit.json` SHA256为
`50a4720dfd0206e80f0977c5ae81a68c87358fde13545eb9891bde5e04576fc3`；其独立性与最终文档审查分别记录。

## 同状态能量传递

下表为8个非零参考场景的`used0-fixed1`，单位dB；整段含启动，每个固定窗口使用原PTS。
AEC三条信号偏移0；NS/AGC偏移160点。所有窗口/peak/控制字段保存在机器结果，范围不代替逐例记录。

| 实际阶段 | 整段RMS差范围 | 三个固定窗口RMS差范围 | 两臂byte相同场景 |
| --- | ---: | ---: | ---: |
| AEC输入 | 0 | 0 | 16/16 |
| AEC估计回声 | -0.383981至+0.077150 | -0.699972至+0.481923 | 8/16 |
| AEC残差 | +0.758048至+1.459878 | +0.178285至+1.778887 | 8/16 |
| NS/频域RES联合输出 | +1.274454至+2.479091 | +0.609837至+2.723942 | 8/16 |
| AGC输出float | +0.575018至+1.311076 | +0.526682至+2.723942 | 8/16 |

8个非零参考场景的AEC残差整段和24个窗口全部为正差；NS联合阶段整段差距进一步扩大。
AGC将8个场景的整段差距收窄约0.512340至1.168015dB，但最终仍全部为正差。
这些是同一次完整处理的工程能量变化；AEC估计echo并非声学真值，残差含人声/噪声/回声。
不能根据能量增加判断人声更完整，也不能据此宣布残回改善或恶化；NS内部哪个增益起作用仍需进一步观测。
AGC float与D18 S16低电平量化差不作为回归，本轮输出PCM完全等价。

## 身份与可复核入口

修正版工件根`/tmp/audio-fe-device-stages-d19-r1-20261011`：

- result SHA256：`31998072bdb2e2836ee87722e776919e442fe836ffee48537006579910e9cd84`。
- binding SHA256：`47d4a0fe0c8e1c0a2eafb02262efd6abc449f0c6a5004557c75650356fded2a0`；绑定1,310个工件、59个冻结源码及工具/计划依赖。
- 测量库SHA256：`2e541ede7ff2fde28babc8e3058b7f1ab1f7b156ffa8fe0d7a9abda36adf9517`。
- D18库SHA256：`eb5b0c784c316e71d6ed9f58db6cb66f190b631daa00c55a94032168d5a47aa4`。
- 仅4个定义改名，函数体/公共头未改；生成头相同，执行程序/库/生成头及依赖起止hash相同，原119输入锁起止相同。

```sh
rtk python3 tools/codex_assets/device_stages.py --help
rtk python3 tools/codex_assets/device_stages.py --root tests/audio --output /tmp/d19-new-output --dry-run
rtk python3 tests/validation/frontend_evolution/test_device_stages.py
```

实际执行要求新的/tmp输出根；已有根拒绝，不覆盖冻结工件。help/dry-run已从/tmp非仓cwd验证。
初次失败根`/tmp/audio-fe-device-stages-d19-20261011`的失败编译回执与MEASUREMENT_INVALID保留。

## 接续依据与资格边界

下一步围绕已观测的AEC起始差异，冻结单一假设并核实际adaptation控制/滤波状态与能量响应；
需要区分参考坐标引起的AEC适配变化、NS联合抑制变化和AGC补偿，不能直接调整默认参数。
本轮没有训练、候选选择、shipping默认/API修改、AISpeech库替换或设备写入；D16的REJECTED结果保持。
真人活动仍未独立验证，缺clean target、ASR/KWS、物理路径及目标板资源/HIL，声学/PQ/owner验收线保持未闭合。
live main已为1be9b89af778783bdbe695c72d048b3d77eee948；来源验证job成功和4项artifact metadata不等于D19或产品资格。
Provider route unresolved，知识线NEEDS_REVIEW；本文为仓内reviewing candidate，未声明正式归档。
