# D18 精确参考对照：消费坐标验证通过，不能据输出能量晋升

日期2026-10-11；experiment=`FE_DEVICE_EXACT_REFERENCE_D18`；[冻结计划](DEVICE_EXACT_REFERENCE_D18_PLAN.zh-CN.md)。
最终结果 **EXACT_REFERENCE_DIAGNOSTIC_NO_PROMOTION**，`promotion_allowed=false`、`shipping_approved=false`。
总体目标active；20点只是复现捕获参考消费坐标，未证明声学最优，不改变D16及其他历史拒绝。

## 单因果和真实观测

固定同一D16研究DSP，tracking/drift关闭。fixed1输入原raw.channel0、initial1ms（16点）；
used0输入原ref_used、initial0。两臂其余完整CALL参数相同，有效参考相差4点/0.25ms。
原库仍被拒绝，作为本实验常量不意味着批准或shipping资格。

reference/work共享union，不能在process返回后读取reference。
本轮仅在新的/tmp测量source把get_reference定义重命名；runner的原名observer先调用real，
立即读取返回的out，再继续原DSP；原函数体/公共头不改。每调用断言delay固定、drift_credit=0、
160点及调用数对应capture帧，写失败退出非零，不修改算法state/event/输入/返回值。
测量source相对原59文件仅这一个定义名变化，generated build header逐字节匹配。
两库/二进制身份分别保存，不称同一个库；数据逐float匹配与输出对照共同验证观测。

## 完整执行与控制

| 验证 | 实际结果 |
| --- | --- |
| 严格C11构建 | 测量库、observer runner和原库plain runner成功，warnings为error |
| 已知答案 | 两runner分别验证3200个reference样本；0/16/20/640点、启动历史及跨帧通过 |
| 冻结场景 | 16场景×2臂，32次完整observe成功 |
| 实际reference | 32条trace共15,430,080个float、96,438帧，逐Float32LE匹配raw16或used20 |
| 原fixed1等价 | 原D16已有10场景的PCM/JSONL逐字节相同 |
| 零参考控制 | 8场景PCM逐字节相同，原JSONL除estimated_delay_ms外相同 |
| 原库no-observer | case07/case16各两臂4次全帧PCM/JSONL与observe完全相同 |
| 固定臂计数 | 全32臂jump/reset/slips逐帧均0；跟踪本已关闭，不能据此推导声学稳定资格 |
| 数据身份 | 原119文件锁、mic/render前缀、config、source/依赖起止一致 |

本轮总36次回放，未重跑原70臂矩阵。两臂每场景长度一致，完整160前缀合7,715,040点，
capture配对和截尾沿原D17，无重采样/尾部补零。

独立计划审查指出启动欠载的已知例外，执行前[澄清记录](DEVICE_EXACT_REFERENCE_D18_AMENDMENT.zh-CN.md)保留：
fixed1首帧start=-16，SDK render_underruns=1；used0首帧start=0，计数0。
每帧实际断言累计值并在终态summary输出。原JSONL未含该字段，不能称所有SDK公共metrics相同。
used0指标estimated_delay_ms=0是used坐标的内部附加延迟，实际raw坐标仍为20点，不是物理零延迟。

## 完整能量差异，保留非质量结论

复用原device_replay.measure/metric_rows/window、原PTS和10ms算法延迟，
固定4–6s、10–12s、19–21s窗口，未逐场景挑窗口或作相关搜索。
8个无播放参考场景PCM完全相同；8个有播放参考场景PCM均改变。
以下为used0减fixed1的输出RMS dB差值，正数表示输出能量更高，不表示质量更好或更差。

| 条件 / 场景 | whole | 4–6s | 10–12s | 19–21s |
| --- | ---: | ---: | ---: | ---: |
| rpm240 far | +1.311065 | +2.048207 | +2.724063 | +2.343201 |
| rpm240 double-talk | +0.784358 | +2.170102 | +1.455741 | +0.526682 |
| rpm240 far-motion | +0.980611 | +2.160911 | +1.529245 | +1.655290 |
| rpm240 double-talk-motion | +0.860297 | +2.380302 | +1.597677 | +0.764162 |
| rpm480 far | +1.263825 | +1.804756 | +2.481178 | +1.845432 |
| rpm480 double-talk | +0.654192 | +2.411033 | +1.843738 | +1.246010 |
| rpm480 far-motion | +1.068581 | +1.781332 | +1.081456 | +1.953251 |
| rpm480 double-talk-motion | +0.575012 | +2.173223 | +0.916366 | +1.095873 |

全部16场景的PCM差异计数、whole/window RMS、peak/rail、VAD诊断和原counter完整保存。
该4点适配差异确实改变当前开发输入的全链输出，但没有clean target/独立真人标签，
不能分清增加的是人声保留、残回还是处理增益；不能称ERLE、降噪、唤醒/ASR或听感收益。
原1ms臂也不因能量较低自动获批。精确复制捕获reference不等于与AISpeech完整DSP等价。

## 身份、工具和恢复

工件根`/tmp/audio-fe-device-exact-reference-d18-20261011`：

| 工件 | SHA256 |
| --- | --- |
| 原D16 library | `4a748de3501241ff66787c8fdb4ccf445126ae49b1be3c4420b7e15e1ffb1170` |
| 新measurement library | `eb5b0c784c316e71d6ed9f58db6cb66f190b631daa00c55a94032168d5a47aa4` |
| result.json | `369c8c484b107c549449a93d92bfa82e464f0163fefce55377d2096b1caa47be` |
| binding.json | `ab41fbe3d970b11ff4a001cfdcf4bd2c2f1d6a4032c36a1da0511526943c2da2` |

binding锁12个当前tool/runner/计划/依赖文件、原/测量59项source身份和1182个实际工件。
完整stdout/stderr/exit保留command回执；独立审计与新文档snapshot另绑定。
[新工具](../../../tools/codex_assets/device_exact_reference.py)只能向新的/tmp目录输出，existing目标拒绝，
dry-run只读；原库runner不允许trace模式。无效args返回2；help/dry-run从非仓库cwd实际验证。
后置负例与文档检查另保存在postcheck/docs-check回执，不改原binding。
tmp不是永久证据仓，恢复先核hash；Provider unresolved知识线NEEDS_REVIEW，未正式归档。
不SCM外写/设备写，不改产品src/API/shipping、AISpeech/E001或历史结论；DUT/HIL仍待实际证据。

## 下一阶段

现在可以在固定参考坐标上继续分离AEC残差、回声估计与RES/NS/AGC贡献，
先沿同一完整处理状态观测即时中间量，避免把独立重跑各stage的结果相加作归因。
任何算法改动另冻结因果、数据角色与验收；不能让测量与候选互相批准。
真人/已知目标分量保护、下游唤醒ASR、物理路径/目标板resource与owner资格保持未完成；总目标active。
