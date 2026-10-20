# D44 固定创新噪声门控实施记录

2026-10-11，experiment=FE_DEVICE_INNOVATION_NOISE_GATE_D44。本文件记录正式矩阵前实施阶段，不是候选准入或整体完成。PLAN、AMENDMENT、PLAN_REVIEW 和已登记 HANDOFF 保持原字节。

从 D43 NS fork 派生新 process 符号，算法差异只有 floor 映射：旧 E/R/Cr/Ci/count/N 检查与 q clamp 后，double I=R*(1-q)、bound=2*N；严格 I>bound 时 float sqrt(1-q)，否则零。原 D42 guard 状态/更新函数复用，observer/噪声读取阶段/diagnostics 不改；valid 不随新门控关闭变零。monitor 计算真实 floor，candidate 只抬原 target。原 NS tracker/平滑/OLA/AGC/VAD/gates 不改。未新增跨帧状态或第三方资产。

| 新文件 | SHA256 |
| --- | --- |
| device_innovation_noise_gate_d44.h | fbe47e192bf3702cbea4829b10683aa2e2c3d9bcfbcbabdcf4faf495711e263f |
| device_innovation_noise_gate_d44.c | f80c3ca4388eda6d174b89f24b22ccfc585ed55da68004d8e42ea597fe282261 |
| device_innovation_ns_d44.c | eec670092988145e01d473c55b71d049c9e282ba90c37f755e8c897063aa8045 |
| device_innovation_noise_gate.py | 5825c73a0740509f8ea5807ef7e8a7e8d03f12da93c7bd652245d174ac41fbb4 |
| test_device_innovation_noise_gate.py | 299d8dc612fdd74fc5dacf1431bcd3486269b530b3caf137beab06015631c139 |

工具直接复用冻结 D43 schema/trace/mode/repeat/future 校验，以及 D42 observe/development_admission。新预检查锁全部 D43 来源和工件、历史 snapshot/CLOSEOUT、新计划和新源码。monitor 四原输出 byteexact，protection 仅排真实 floor_mean；candidate bypass byteexact；两模式过去状态、与 D43 的旧操作数、重复及 future 前缀均强制验证。完整主矩阵只使用新的 /tmp 根，既有 root/symlink 拒绝。

## 实际定向验证与审查

严格编译 tool chunk7935ae exit0：C11/O2/-Wall/-Wextra/-Werror/-Wconversion/-Wshadow/-pedantic/-ffp-contract=off，D18 原 C_DEFINES、includes 和 archive；同一命令内 runner --self-test exit0。自测包含严格2N、相等不保护、nextafter边界两侧、零噪声/q0/q1/warmup/低功率/非有限/负数/非法count/溢出、原 EMA 更新、inactive reset、40帧 observed-vs-NULL状态及输出等价、旧噪声读取和固定快照。runner=/tmp/audio-device-d44-targeted-v1/runner，SHA256=91ce26730cabd06dd47e5d3ebad1ab4f09046e0af9b24d5dd3f87ce492fe719b。invalid argc实际exit2。自测不是184次正式矩阵或全帧FFT/EMA/noise历史独立重建。

新5unit实际exit0，覆盖 baseline 诊断排除项、不允许旧N/valid/功率变化、monitor日志只排floor_mean、音频及control不可豁免、candidatebypass不可改变、既有root/symlink及额外/缺失行拒绝。继承D43/D42共26unit实际exit0。非仓 cwd=/tmp help实际exit0；同cwd deepdry session28397实际terminal0，46cases/7935locks、writes=false/dsp_executed=false。git diff --check实际exit0。

工具输出转录 /tmp/audio-device-d44-targeted-observations-v1.json 明确标注为 transcribed actual tool output，含真实chunk/command/exit；它不是subprocess生成的机器回执或独立验证。独立reviewer实际从/tmp执行当前5unit exit0，独立比较NS整个diff和当前五源pin：Spec PASS / Quality PASS / Independent / unresolved0。当前审查只允许准备正式执行，不批准matrix结果、独立960组新波形计分或声学准入；正式一次writer尚待独立控制审查。

## 恢复与后续

D44 已真实登记 task-79a8493b8f963aa343cf5771、progress1/checkpoint1 verified，六份机器回执均exit0。上次native维护请求1791720902583已受理，观察120.42344195581973秒终态ACCEPTED_COMPLETION_UNVERIFIED，恢复实际无livehost。没有重发或猜测completion_verified；freshsnapshot maintenance.required=false/recommendedcontinue，按门禁继续实施。

fresh main仍70aeb4aa1458e20917ac551d1fe5f7468df721e2；78checks为77success/1skip，requiredsummarysuccess。当前openPR新增#722 head32c5e762e90b380c5639b41314c8289cb61466b0；原#717/#714/#708/#695仍open；#657 OPEN/updated2026-10-11T12:10:45Z已读取。最新工件11702037790属于#722，未过期。远端CI不验证本地D44。Provider query有一条旧reviewing命中，但route unresolved；知识NEEDS_REVIEW，未归档成功。

正式root=/tmp/audio-fe-device-innovation-noise-gate-d44-20261011尚未创建。下一步一次writer控制审查/固定源pin/fresh门禁、184执行505944帧、独立新波形全部960组及原两臂admission重算、快照2N/floor/target/gain与原操作数、根保护负例、实际RESULT/REVIEW/README/freeze/本地closeout。near每臂24、中位<=-3dB且至少18改善；no-near72最大<=+1dB；pureecho4whole最大<=+1dB，任何一臂失败保存DEVELOPMENT_REJECTED。原D42拒绝保持，measurementfail独立MEASUREMENT_INVALID_REPLAN不改判。

goal_statement=全面推进优化迭代；completion_claim=当前实施完成且定向验证/源码审查通过，正式矩阵及闭环未完成；claimant=root；verifier=device_capture_independent_review；logical_task_open=true；open_items=正式测量、独立完整审计、整批review/closeout。无commit/push/PR/merge/release/设备写；promotion_allowed=false/shipping_approved=false。AISpeech固定点产品链路、真人/QIVW、目标板/E001/HIL/PQ资格单列。

