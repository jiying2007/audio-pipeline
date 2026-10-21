# D20 首次分歧时序结果

日期2026-10-11；experiment=FE_DEVICE_TIMING_D20。
结论：far/double-talk门控差异不能解释全部D19 AEC输出差异；完整时序把下一假设收敛到参考坐标/滤波历史响应。
decision=TIMING_DIAGNOSTIC_NO_PROMOTION；data_role=development；promotion_allowed=false；shipping_approved=false。
总体目标active；[冻结计划](DEVICE_TIMING_D20_PLAN.zh-CN.md)、[路径修正](DEVICE_TIMING_D20_AMENDMENT.zh-CN.md)、[独立审查](DEVICE_TIMING_D20_REVIEW.zh-CN.md)。

## 全量分析结果

复用D19全部16场景×2臂reference与5条阶段trace、完整CSV与公共指标；本轮新DSP执行/编译均0。
原119输入锁和D19全部绑定起止验证，AEC输入16例全相同，8个零参考场景全部trace保持相同。
逐4字节比较报告bitwise首次差，没有显著性阈值、动态对齐或删启动数据。
gate_eligible只指far&&!dt；它是MDF实际adapt条件的一部分，不能替代adapt_due/x_power_total或实际更新次数。

下表帧号采用AP回放前缀160点/帧，不能当场景PTS或物理播放时刻；far/double-talk名称是采集scene标签，真人活动尚未独立核实。

| 采集目录/scene | 首次参考差帧 | 首次AEC残差差帧/帧内点 | 首次eligible差帧 | 时序关系 |
| --- | ---: | ---: | ---: | --- |
| rpm240 / far | 321 | 326 / 64 | 326 | 同帧 |
| rpm240 / double-talk | 321 | 326 / 64 | 1430 | 门控差较晚 |
| rpm240 / far-motion | 321 | 327 / 32 | 无 | eligible全程相同 |
| rpm240 / double-talk-motion | 319 | 326 / 64 | 1758 | 门控差较晚 |
| rpm480 / far | 321 | 326 / 64 | 无 | eligible全程相同 |
| rpm480 / double-talk | 322 | 329 / 32 | 886 | 门控差较晚 |
| rpm480 / far-motion | 321 | 327 / 32 | 无 | eligible全程相同 |
| rpm480 / double-talk-motion | 322 | 328 / 64 | 无 | eligible全程相同 |

8个零参考场景没有输出差异；非零参考场景关系分布为0例before、1例same-frame、3例after、4例no-gate-difference。
所有非零参考场景的echo与residual首次差样本相同；首次残差差前缀时间为3.264至3.292秒，不代表物理播放起点。
rpm240/far-motion的far/dt联合字段在322帧已不同，但两个布尔值变化后eligible仍相同。
因此既要保留实际字段，也要比较实际谓词；仅比较标志总次数或首次far/dt差会产生错误归因。

机器结果保留全部逐字段不相同帧数、首末帧、连续半开区间，以及reference/所有阶段首次差与差样本数。
NS/AGC的固定对应输入坐标为输出首差样本减160，负启动坐标不截去；没有动态移动某个场景获得有利解释。
同帧不能证明子块内因果顺序，bitwise差本身不代表具有声学意义的幅度差。
本结果不推出门控无影响，也不证明相位敏感性是算法缺陷；它仅否定门控差异是全部已观测差异的必要条件。

## 验证、身份和复跑

修正版从/tmp执行完整分析，结果与仓cwd初次完整分析逐字节相同；非仓cwd help/dry-run、5项定向测量测试通过。
独立审计未导入新工具分析函数，直接按uint32位模式比较trace并独立归并控制区间。
1,571项hash、96组trace配对共92,580,480个两臂浮点值、96,438帧控制CSV和160项控制区间均通过，
16份首次差帧字段快照完整匹配；索引、计数、区间和分类核验误差均0。
审计回执`/tmp/audio-device-d20-independent-audit.json` SHA256为
`fb1616dd510d0506c5923310fc7ec008970819b2f6f0b7e72a7d1ad509bf43cf`。
独立6个创建前拒绝负例全部exit2且D19/初次D20工件完整manifest不变；初次非仓cwd预检失败保留，不覆盖基线。
修正版工件根`/tmp/audio-fe-device-timing-d20-r1-20261011`：

- result SHA256：`66126f7b6ea71347a2cdd9a18ec72f1ac5b33a96a0a5b9d6e402da1823f65180`。
- binding SHA256：`eca1f9ac9d4276a6184a389e5eca46d8dbb99892c0a007044c8d667b62aa6c21`。
- 继承已验证的D19测量库SHA256：`2e541ede7ff2fde28babc8e3058b7f1ab1f7b156ffa8fe0d7a9abda36adf9517`；new_compilation=false。

```sh
rtk python3 tools/codex_assets/device_timing.py --help
rtk python3 tools/codex_assets/device_timing.py --root tests/audio --output /tmp/d20-new-output --dry-run
rtk python3 tests/validation/frontend_evolution/test_device_timing.py
```

仅实际执行分析时创建新的/tmp输出根；dry-run不写，已有目标拒绝。
下一阶段应冻结已知路径控制实验，保持门控/参数，单独检验参考坐标与MDF滤波历史响应，先证明测量和预期行为再决定改算法。
不再用整段门控累计数解释本批全部输出差；不以本批已查看数据制造blind或参数晋升资格。
历史候选REJECTED、AISpeech产品链路、默认/API、E001和真人/clean-target/ASR/KWS/目标板HIL/owner资格保持独立。
Provider route unresolved，知识线NEEDS_REVIEW；本文为仓内reviewing candidate，未正式归档。
