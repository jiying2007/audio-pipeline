# D10 短延迟 tracker 内部定位结果

日期：2026-10-10；experiment=`FE_DEVICE_TRACKER_D10`。
[冻结计划](DEVICE_TRACKER_D10_PLAN.zh-CN.md)；[观测 fixture](../../../tests/validation/frontend_evolution/device_tracker_d10.c)。
决定=`ENGINEERING_DIAGNOSTIC_SEARCH_COVERAGE_LIMIT`；`promotion_allowed=false`、`shipping_approved=false`。
在固定 acquire 输入中，已定位大量搜索 epoch 的 true-lag 被 coarse winner 的局部 refine 区间排除。
少量正确命中仍无法完成获取，须分别解释大跳确认及小偏差漂移路径。
D8 长窗 gate 没有阻止本轮正确大跳候选；不能据此外推 D8 的整体选型或声学效果。

## 实际执行与观测等价

两次严格 C 编译成功，分别直接 include 字节不变的 D6/D8 `ap_sync.c`。
实际 tracker 原函数执行与旁路只读计算分离；旁路使用原静态 score、严格 `>` winner 更新、
原 coarse/refine 搜索顺序，观测前后整个 state 均 byte-exact 不变。
D8 history score 在实际 tracker 追加当前 mic history 后读取，不改变状态。

固定 7 个既有输入分别回放两版本，共 14 次，每次 300 帧。
全部 4,200 帧的 delay_ms、累计 jumps/slips 与 D9 原公共 API CSV 逐点一致，原 resets 均为 0。
所以本轮内部轨迹可解释这些既有公共 API 结果；没有生成新信号或重跑完整 D9。
所有输入 SHA 匹配 D9 binding；构建相关源码、生成头、fixture、编排、命令、CSV 和 result 已绑定。

| 身份 | SHA256 |
| --- | --- |
| D10 计划 | `936345c422a16b2e4fec76ad62d0f8ff1eaf64d3215328b1901126ab55d59a50` |
| D10 fixture | `eeda522ead443ea84fe4abf7a51c20f37464640cb7a2bdd0384cbfe01a680aa1` |
| D9 原 result | `564a2d3d6b6200c728ad09469b455b0595a584286d56ea2c0fd3899e1a9624b6` |
| D10 实际 result | `9c63a6d5eee8f1f13a77f711a08054ac77e22127daf488ea4a78b063e8afe613` |
| D10 binding | `4f730f78c7a67d338cf0f64fcce803c05b1534a7a927db908e736f609000684c` |

实际工件目录为 `/tmp/audio-fe-device-tracker-d10-20261010`。
这是本机 session 工件，持久摘要不代表跨机器可复跑工件已经归档。

## 搜索覆盖的有限证据

每例发生 29 次实际搜索（生成器第 19、29、……、299 帧）。
下表的排除/命中计数在两版本一致，分母为该例的 29 次搜索；最终延迟分别列出。

| 既有 acquire 输入 | refine 排除 true-lag | 精确命中 true-lag | D6 最终 ms | D8 最终 ms |
| --- | ---: | ---: | ---: | ---: |
| 8 kHz / seed1 / 1 ms | 29 | 0 | 39 | 39 |
| 8 kHz / seed1 / 7 ms | 27 | 2 | 40 | 40 |
| 16 kHz / seed1 / 1 ms | 27 | 2 | 40 | 40 |
| 16 kHz / seed1 / 7 ms | 27 | 2 | 40 | 40 |
| 16 kHz / seed2 / 1 ms | 27 | 2 | 10 | 40 |
| 8 kHz / seed1 / 80 ms | 0 | 29 | 80 | 80 |
| 16 kHz / seed1 / 80 ms | 0 | 29 | 80 | 80 |

五个短延迟输入每版本共 145 个 epoch：137 次 refine 区间排除真实延迟，仅 8 次精确命中。
这些 epoch 的 true-lag score 最低为 0.999985039，说明原 score 函数在已知真值处能得到充分匹配，
失败并非这些输入缺少真实相关峰。coarse 仅每约 2 ms 采样一次，又只细化单一 coarse winner，
因而较远的 coarse 峰一旦获胜，就不会计算接近 1 的真实峰。这是 **137 个已观测 epoch 的搜索覆盖不足**。
它不是全体输入、全部 D9 失败或真实房间音频的通用根因证明。

## 正确候选、确认与错误跳变

8 kHz/seed1/7 ms 的正确 epoch 为 169/299；16 kHz/seed1/1 ms 为 149/159；
16 kHz/seed1/7 ms 为 89/109；16 kHz/seed2/1 ms 为 199/289。
基线前面三个输入的 6 次命中，以及 D8 的全部 8 次命中，均属于大跳候选，未完成三次连续确认。
例如 16 kHz/seed1/1 ms 的确认计数在第 149/159 帧为 1/2，随后搜索离开真值，未产生正确 route jump。

基线 seed2 有不同路径：第 79/89/99 帧 refined 为 158/163/169 samples，
三次都与首次候选 158 相距不超过 32 samples，原确认器在第 99 帧接受 158 samples（9.875 ms）。
但真实延迟为 16 samples（1 ms），在上述三个 refine 区间之外。
所以该例先形成了一次真实记录的错误跳变，再漂移到最终约 10 ms。
其第 199/289 帧虽命中真值，旧延迟已经约 160/161 samples，raw jump 小于 320 samples 大跳界限，
进入 small/uniqueness/drift 路径，不能归因为“三次大跳确认不足”。
D8 在这同一输入中没有发生该错误 route jump，但最后仍为 40 ms，不能视为正确获取。

两个 80 ms 正例每版本合计 58/58 次精确命中，第 39 帧完成三次确认并正确跳变。
它们证明原确认流程在本正例能够工作，不能抹去短延迟失败。

## D8 gate 与下一修复边界

实际 gate 拒绝只按原前提计数：refined_score ≥0.0324 且 raw jump >rate/50，
随后 history_score <0.0324。不能把每个 epoch 的只读低 history 分数都算成实际 gate 拒绝。
在五个短延迟输入中，D8 拒绝了 28 个非真值候选；正确真值候选拒绝数为 0。
因此本轮正确大跳候选的失败发生在获得稳定候选的链路，不能直接归咎于 D8 长窗 gate。

下一单独修复实验应针对 coarse 搜索覆盖，保留原最低相关门限、数据角色与失败记录，
同时检查 uniqueness 的 top4/guard 正确性：现有 top4 充分性证明依赖 coarse 间距约 2 ms，
不能只减小搜索步长却继续沿用同一个排除区间及未经证明的 top4 上界。
搜索覆盖、连续确认、CPU 代价和误跳保护必须分别验收，测量 D10 不批准后续候选。

本轮仅观测，无算法修复或参数优化；[D9 失败](DEVICE_ACQUISITION_D9_RESULT.zh-CN.md)及 D8 INCONCLUSIVE 保留。
新 live main 身份与本地冻结 D6/D8 源码分开；未执行 commit/push/设备写。
数据均为已查看合成 development 输入，不是声学评估；SSC305 资源、HIL、E001 和 PQ 独立。
Provider route unresolved，仓内记录为 reviewing candidate，未声明正式归档。
最终独立核验见 [D10 复审](DEVICE_TRACKER_D10_REVIEW.zh-CN.md)。
