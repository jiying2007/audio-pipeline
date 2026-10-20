# D13 已知真值事件回归：冻结契约计划

日期：2026-10-10；experiment=`FE_DEVICE_CONTRACT_D13`；kind=`measurement`。
goal_statement：建立公共 SYNC/AEC 调用的初始获取、稳定跟踪、持续路径切换和短时干扰事件回归入口，
验证下一算法实验必须同时保护哪些行为。用户已授权继续推进；本轮算法实现权限为 none。
来源：[D12 事件诊断](DEVICE_EVENT_D12_RESULT.zh-CN.md)，D11 REJECTED 不变。

## 基线、假设和数据角色

固定 D8 库 `a04ca88a75c0fd8538f7eb6d3726dfe906b2dfc284cc77c577f2328eb04b23b1`，
D11 库 `ead75733d45f5b78c086bed9122082d410847eea0ed6b21f8bafab102a1cb0ac`。
使用各原 replay 的生成头及已锁源码；不重建、替换或重命名库，不使用 D12 measurement 库。
保留 D9/D11 已知延迟获取的历史结果，不把本轮新增生成输入称为独立 validation/blind 或现场真值。
仅 first-party disclosed synthetic engineering 数据；不得以数据生成标签推导设备实际对齐。

假设：同一 route_jump/reset 在有真值的初始获取或持续路径切换中是恢复行为，
在稳态或不足三次连续确认的短干扰中应受抑制；不能单凭 reset 总数批准算法。
该假设先接受公共 API 测量，不预先假定 D11 在新矩阵全通过。
原传入流严格同步且连续：每帧先 push_render 再 process_capture，10 ms，无 timestamp 或 gap 通知。

## 固定生成器与配置

直接复用字节不变的 `device_acquisition_d9.c` 的 white/broad/render_value/s16 工程生成器，
render 仍为 signal=0 宽带、rate/500 点平滑、幅度 0.30；主回声为原 S16 render 延迟后乘 0.4。
两个 sample rate 8/16 kHz，各 seeds 1/2，每例 300 帧，单麦。
公共配置 CALL、SYNC|AEC、max_delay=100 ms、tracking/drift=1；其余 default 不改。
测量记录实际逐帧 delay/error、jumps/resets/slips、真值阶段和输出；登记配置、输入、库、runner 与输出 hash。
独立计数检查 jumps==resets，只适用于本组启用 AEC 的冻结配置。

## 预注册场景：每个 rate/seed 共 14 例

| 家族 | 例数 | 生成与初始化 | 冻结规则 |
| --- | ---: | --- | --- |
| acquire | 3 | initial=40，真实延迟从开始为 1/7/80 ms | 初始获取为正常恢复候选，需目标内完成一次 jump/reset |
| steady | 3 | initial 与真实延迟相同，1/7/80 ms | 不得新增 jump/reset；末窗保持目标 |
| path-switch | 3 | initial=真实40 ms，第120帧起真实延迟持续变为1/7/80 ms | 变更前无 jump/reset；之后一次 jump/reset进入目标 |
| pulse | 2 | initial=真实40 ms不变；第120帧加幅度0.9的80 ms参考相关分量，持续10/20帧 | 短时分量不足三次搜索确认，不得jump/reset；恢复后保持40 ms |
| pulse3 | 1 | 同pulse，持续30帧 | 诊断组，完整披露是否触发及恢复，不用于必验PASS或选型 |
| silence | 1 | initial40，render/mic全0 | 无可识别物理延迟；保持40、不jump/reset |
| unrelated | 1 | initial40，render原seed；mic为独立seed+100宽带乘0.4 | 无单一已知echo lag；不jump/reset，不能把保持40判为正确对齐 |

合计每版本 **56例**，其中 mandatory=52、diagnostic=4；两版共112例。
指定 r16k/seed1/path-switch/7 ms 各新进程复跑一次，共114次。
pulse 分量是人为参考相关叠加，不是真电机/真人双讲，更不代表所有干扰。
pulse3 与 persistent-path 在前三次相似候选上可能有因果歧义；不强迫算法预知后续消失。
同一生成器、seed 或场景衍生不算独立语音/房间来源。

## 验收、失败保留和停止规则

测量硬门禁：56唯一case/版；每例300 capture完整，S16尺寸正确，逐CSV重算summary，
两版 input字节相同、config相同；指定新进程input/output/CSV逐字节相同；库/源/头hash全匹配。
必验语义：已知真值例末20帧全部在truth±3 ms（与D9相同）；
acquire/path-switch 首次进入目标不晚于 phase+80帧，exactly1 jump/reset且该跳变进入truth±3 ms；
path-switch 第120帧前保持40±3且无jump/reset。
steady/pulse/silence/unrelated jumps/resets为0；pulse末20恢复40±3，steady末20保持各目标；
silence必须逐帧delay40且slips0。unrelated不把任何末delay当作真值。
这些是新增事件契约，旧D9门限/时长/失败不改。

P1：冻结计划、生成器与库，独立计划审查；只读核符号和实际配置。
P2：strict warnings编译实际public runner，两版56+1全量执行及逐CSV回读；测量无效立即replan。
P3：按原冻结规则逐例保留PASS/FAIL，D8与D11分别报告，不以两版共同失败豁免mandatory；
若必验失败，定位具体家族并停止算法实现；若通过也仅为event-contract工程基线，不批准D11或新候选。
P4：冻结快照、独立whole-change、中文文档和Runtime收口；恢复入口含下一独立算法实验前置条件。

retry_budget：最多两次测量实现缺陷修正，无算法/参数搜索。
staleness_threshold：source/library/config/input任一漂移即stale；运行超120秒先核状态，不裁剪帧数。
heartbeat：阶段完成登记；stop_condition=`pass/replan/blocked/abort`；plan_completeness=四阶段明确。
claimant=`root`；verifier=`device_capture_independent_review`；初始open_items=4。
required_evidence=计划、两版库/源码/头、114次回执、完整input/output/CSV、逐例决定、独立复审；attestation需hash回读。

当前live main=`cc887b0ced20a828ed7148b9ac949f639a1e2868`、#657 OPEN；PR #695/#696独立，不借用主线CI。
Provider route unresolved，无项目权威命中，本轮仓内 reviewing candidate，未正式归档。
不改产品源码/default/API、AISpeech、E001，不commit/push/设备写，不以总能量或reset数量推导声学收益。
