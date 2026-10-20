# 设备采集接入与前端推进分析 D0–D2

状态：**REVIEWING / 本地开发诊断，禁止据此晋升产品候选**。日期：2026-10-09。

本文件是新输入的本地待审查报告，不改写原始 PLAN/TASKS、历史研究结论、#657 或 E001 身份。
Knowledge Provider 本轮返回 `route unresolved`；尚未正式归档，不具备 Provider 成功回执。

## 1. 结论与已推进工作

`tests/audio` 可以立即用于 frontend-evolution-v1 的 FE01 输入适配、FE04 参考时基/AEC/RES、
FE05 NS/AGC/VAD 和 FE06 机器人噪声诊断。它已经被 AISpeech 分析，本轮也已查看并用于开发诊断，
因此统一归为 disclosed development/regression；不能再作为独立 validation 或 blind。

本轮完成 16 轮严格采集校验、32 个不改算法的 AP 回放、22 个 SYNC 配置诊断、8 个 NS/AGC
隔离诊断，以及两次首例重复回放、6 个逐点控制和4类损坏输入负例。共62个固定回放，未搜索参数。
119 个原始文件哈希在实验结束及单独回读时一致。没有修改 AISpeech、app_audio_test 或产品算法。

最明确的推进方向是：

1. 将设备参考时基与 AP 默认40ms启动延迟分离，建立产品采集的显式回放配置。
2. 在实际录音中复核 SYNC 错峰/采样滑移对 AEC 稳态的影响；保留172ms跳变反例。
3. 在安静和真实电机噪声上建立 AGC 输出噪声与 VAD 保护测量，再考虑改算法。
4. 同一原始输入并列保留 AISpeech VOICE/CALL 与 AP 配置身份；下游保真、KWS/ASR独立验收。

## 2. 基线与证据位置

本轮 live main 与本地 HEAD 相同：`572b0e34a8a8e5663397ce16e378209ba9058d4d`。
开始时 open PR=0；open issue 包括 #657、#689、#691 和独立真实资格 #58。
收口时重新查询：fresh-main Verify `37946999926` 已在上述exact SHA完成 `success`，
required summary job `113887701845` 也为 `success`，未发现failure job。
已查看该run当前artifact清单，但未下载或把artifact存在解释成对应研究资格通过。

所有构建、输入派生PCM、输出、测量脚本和完整JSON位于 `/tmp/audio-fe-device-20261009/`：

| 文件 | 含义 | SHA256 |
| --- | --- | --- |
| `input-lock.json` | 119个原始文件逐文件锁 | `c63b37feff15d7eac6932c92c1ddaa99a1a6efa5d338feb0c2ec2d28443fa285` |
| `analysis.json` | D0输入诊断与32回放 | `e46b74a8f15b307c025b7e460f394637e62ff4aed87a09fd7509f7e969e63e27` |
| `sync-analysis.json` | D1固定SYNC对照 | `004587b36b158c07683edfd883db59538d3b736a92dd3a6f3c438e012eed5f82` |
| `noise-analysis.json` | D2隔离NS/AGC对照 | `df7531d5421e8202e5453138518d926a0320c2c1af99caaa78a7e926c2de3768` |

`PLAN.md`、`SYNC_PLAN.md`、`NOISE_PLAN.md` 在各自实验执行前固定。
`verify.py` 与 `verification.json` 独立回读原文件、生成文件、样本数、哈希及负例。
这些是本地临时证据，不是耐久归档；需通过已解决route的Provider/受控证据存储保留后才有长期回执。

AP使用Host GNU9.4.0、x86_64、SCALAR、MDF、EMA、fast_math=0，配置摘要
`280da05cb3f360d528077b9ee28bfe8befe3639c04597d71461e78100caa492b`。
`ap_process_pcm` SHA256：`9fc33148a4835b7c23bfff13b464695f6dd955c21e5a608a881d0c5f0681f22c`。
build-info标记 `source_revision=572b0e…-dirty`；构建前已有未跟踪 `tests/audio/`，tracked/index diff为空。
这个Host构建不是shipping SSC305制品，也不是批准计划的immutable B0重建；不能冒称B0成绩。

## 3. 实际输入与场景解释

共有68个WAV：4个旧音量采集，16轮×4条流；另有每轮session/frames/events、两张现场记录表和gitignore。
16轮匹配输出共7,715,328点，约482.21秒。文件格式均为16kHz、PCM16LE；本轮未发现WAV载荷截断。

| 输入 | 当前确认用途 | 仍缺条件 |
| --- | --- | --- |
| `80_audio_in*.wav` | 用户确认播放音量80；67.16秒、双通道 | 缺session、通道身份、制品和时轴映射 |
| `100_audio_in*.wav` | 用户确认播放音量100；69.2473秒、双通道 | 同上；不能从名字自动选择AEC参考通道 |
| `vocaltest_rpm240` | 8个场景，VOICE、音量80、运动命令±240RPM | 独立近端真值、距离/方位/房间及重复轮次 |
| `vocaltest_rpm480` | 同样8场景，VOICE、音量80、运动命令±480RPM | 同上；不是8轮全部都在运动 |

按 `app_audio_test/docs/capture.md`、`docs/TEST_REFERENCE.md` 和实际session解释：

- quiet/near/far/double-talk不发运动计划，目录RPM标签不证明这些场景运动。
- motion/near-motion/far-motion/double-talk-motion有实测轮速，反馈确实覆盖约±240/±480RPM。
- 右轮原生RPM方向与逻辑运动方向相反；不能将左右异号误报为原地转向。
- 纯motion从第3秒运动，其余运动场景从第8秒运动；forward/reverse各5秒。
  此批纯motion的coast=10秒，其余运动场景coast=2秒；具体时序从每轮session与源码推导。
- far-first播放约3–27秒；近端单讲提示约3–25秒；双讲近端提示约6–25秒。
  near_script为standard。提示、素材提交和轮速是三种独立证据；提示不能证明真人已说话。
- 所有session均保留 `near_activity=human-not-verified`、`acoustic_verdict=pending`。
  两张记录表的人工条件/试听/放行仍为空。

VOICE设备输出与AP CALL回放不是相同preset；本轮不以两者电平差直接裁决算法优劣。
AISpeech当前README陈述既有Host VOICE逐点复现及CALL候选，本轮只读取其当前文件作为协作背景，
没有重跑其库/挑战数据，不能把它写成本轮新增AISpeech通过证据。
该子仓当前有大量dirty，HEAD为 `9ce7a7f87b4835816e68df7fade6d43ebb3d47a1`；设备程序仅有MD5来源字段，
不能据此将当前源码/库绑定为已执行设备制品。app_audio_test读取时HEAD为
`c81084935638f3d3771f7c3226db0314c078d800`，同样不反推它就是录音时源码。

## 4. 完整性与显式帧适配

本轮复用当前 AISpeech `tools/codex_assets/device_replay.py:read_capture`，其源文件SHA256为
`48730b0b1a2ae4a111add74893a767c85ca7654096af2efefcfb49cea0356ecc`，未加载/执行AISpeech库。
全部16轮通过以下检查：schema-v2 complete、错误码、稳定profile、WAV几何/载荷、seq/offset/epoch/PTS、
input/output数量、正式场景output_valid、覆盖范围，以及参考逐点关系。

`stage=0`是128点mic/ref_raw；`stage=1`是256点ref_used/output。所有参考满足：
`ref_used == delay(ref_raw.channel0, 20 samples)`。20点=1.25ms是已记录参考预处理，
不是所有产品/房间的最优物理延迟。未对ref_used重复加延迟。

回放先配对256点输出流，再显式截取完整160点前缀：
9轮的raw输入末端有128点无配对数据；这不是通过填充掩盖的掉帧。
9轮的AP重组另舍弃32点尾部，其余无重组尾部；每轮数值记录在receipt。
总舍弃raw未配对72ms，AP重组另18ms，均位于末端，不补静音或改原文件。
AP使用raw参考第0路，由AP自身管理SYNC。原始双麦不重排、不重采样；物理左右麦身份仍待设备布线确认。

在/tmp副本上测试4种负例：WAV截断、实际参考改1个采样、seq跳号、complete=false，均被拒绝。
部分quiet/near在scene_start之前约39ms有输入rail样本，正式场景未检出输入rail；不能用整文件峰值误判正式场景削波。
16轮设备输出未检出rail，但无削波不证明回声消除或语音保真。

## 5. D0与D1：参考对齐是已测到的主要推进点

D0使用未改算法的 `ap_process_pcm`，每轮CALL默认与BF-isolated各一次，首例两臂再重复，PCM及metrics完全一致。
默认CALL为40ms初始延迟、自动delay/drift；AP报告的算法延迟为10ms，BF-isolated为0ms。
固定一秒相关窗口显示远端强相关峰通常为14–17点，且多为负相关。
相关峰不是完整房间脉冲响应或正式标定；生产score使用相关平方，负极性本身不是已证明根因。
18秒附近低相关窗口出现任意远峰，保留为低可信数据，不拿来调产品延迟。

D1只用公开config，预先固定三个臂：tracked40、tracked1、fixed1。
tracked1只改初始延迟1ms；fixed1保持1ms并关闭自动delay/drift，其他AEC/RES/NS/AGC参数不改。
1ms是该批已查看开发录音峰值的单个取整诊断假设，不能当作独立验证或推广默认值。

下表是同一实际输入4–6秒窗口、按AP报告10ms算法延迟配对的**输出总RMS，dBFS**：

| 场景 | 默认tracked40 | tracked1 | fixed1 | fixed1比默认低 |
| --- | ---: | ---: | ---: | ---: |
| rpm240 far | -27.31 | -34.43 | -36.56 | 9.25dB |
| rpm240 far-motion | -27.55 | -34.46 | -37.11 | 9.56dB |
| rpm480 far | -26.93 | -36.76 | -37.39 | 10.46dB |
| rpm480 far-motion | -27.12 | -33.93 | -36.83 | 9.71dB |

四个tracked40逐点复现D0，两轮零参考quiet的fixed1与D0逐点一致，避免把runner重写差异当收益。
tracked1说明启动条件贡献明显，fixed1相对tracked1的后续差异说明自动策略仍影响结果。
不能进一步将delay_tracking和drift compensation各自归因；本轮把它们作为一个策略控制。

反例：rpm480 far-motion的tracked40与tracked1都出现172ms估计，最终累计2次delay_jump/2次AEC_reset；
tracked1仍有50次sample slip。fixed1没有jump/slip/reset。
全文件输出RMS默认-30.35、tracked1 -32.36、fixed1 -36.77dBFS。
这些是配置处理的可复现差异；缺真实render时间戳与clean-echo，不能把172ms直接断言为物理错误延迟，
也不能把总能量下降称为正式ERLE提高。AEC内部erle_valid/erle_db保留在JSON，不升级为外部标定指标。

双讲两臂也已回放，但不以输出较低选择fixed1；降低近端语音同样会降低总能量。
固定1ms仍未达到设备VOICE的输出电平；增益、时基、DTD和NS/RES不同，不能全部归因于AEC。

## 6. D2：NS/AGC与机器人噪声

使用现有 `--capture-profile agc-isolated/ns-isolated`，两轮quiet及两轮motion各两臂。
下表同样为4–6秒总RMS、dBFS；motion此窗口在第一段实际运动中：

| 场景 | mic0 | AP CALL默认 | AGC-isolated | NS-isolated |
| --- | ---: | ---: | ---: | ---: |
| rpm240 quiet | -43.22 | -32.26 | -25.51 | -45.59 |
| rpm480 quiet | -45.29 | -33.19 | -27.24 | -47.90 |
| rpm240 motion | -40.10 | -30.22 | -23.80 | -42.81 |
| rpm480 motion | -35.10 | -25.29 | -22.40 | -37.05 |

独立AGC臂会明显抬高背景总电平，而独立NS臂降低背景；完整链的组合不能用二者相加推算。
这给FE05的安静增益、语音起音保持和VAD门控提供真实开发输入，不支持直接关闭AGC或套用新阈值。
默认CALL quiet全文件VAD-active比例约40–46%，motion约44–54%；该比例包括预热且缺人工逐帧标注，
只能提示需要正式标注/窗口统计，不能报告为FPR、FAR或误唤醒率。
纯motion数据可以研究实测RPM与频谱/电平关联；跨240/480不是同次配对，也缺重复/房间条件，
不能把单轮电平差直接当作速度造成的噪声因果效应。

## 7. 音量80/100旧数据

两对旧WAV当前头长度与实际载荷一致，本轮不延用历史截断判断。
音量80的mic两路全文件RMS约-29.77/-28.85dBFS；音量100约-20.05/-17.82dBFS。
100的echo两路检出74/71个rail样本，80的echo未检出rail。
这足以把100列为“参考路径饱和风险”的开发反例；尚不能定位是AO、Codec、采集转换还是其它环节。
80/100录音内容/时长不同，echo两个声道并非逐点相等；禁止直接把两录音RMS差当作音量曲线、
静默平均echo双路、假设它们是两颗额外麦克风，或混入16轮session的formal truth。

## 8. 当前方案的推进顺序与退出条件

| 优先级 | 工作包与具体动作 | 当前输入如何使用 | 退出条件与未闭环 |
| --- | --- | --- | --- |
| P0 | FE01：正式研究输入适配器 | 移入现有FE入口的hash/256→160/tail/role契约，保留本轮严格负例 | source/config/processor/input/output逐例绑定；原始数据留受控存储；精确head现有CI |
| P0 | FE04：产品参考时基与SYNC资格 | 将D1作为复现夹具；分别隔离启动延迟、sample slip与route reset；测actual ref输出 | 先复现172ms案例，再以独立录音验证；render PTS/sequence/XRUN缺失不伪造 |
| P1 | FE05：NS→AGC→VAD保护 | 以quiet/motion作开发负样本，near作语音保护诊断；保留D2 | 固定无语音标注、近端clean target、起音/尾音、输出噪声、同召回VAD比较；候选冻结后独立确认 |
| P1 | FE06：RPM与机器人噪声 | 仅8轮真实motion组含轮速反馈，按native符号、反馈age与scene PTS关联 | 速度/地面/重复/近端条件分别记录；不把RPM标签当所有录音实测速度 |
| P1 | FE04/09：AISpeech与AP公平对照 | 共用原始hash，分别记录VOICE/CALL/AP结构与增益/延迟 | 对齐源/制品/有效配置，加入固定真人听评、clean targets、KWS/ASR；不能凭音量低获胜 |
| P2 | FE03：双麦真实几何/BF | 可检通道一致性、相干性与固定BF回放；不能给未知方位DOA真值 | 补通道位置/方位/距离/标定；双麦不能填充成真实四麦 |
| P2 | FE07：神经基准 | 后续可作licensed/frozen模型的域外开发诊断 | 本轮不训练；人声授权、模型权重/数据/依赖许可及stateful latency分别就绪 |
| P2 | FE08/09：端侧整链与资格 | /tmp Host资源/功能仅作工程证据 | AP实际SSC305制品、执行身份、CPU/p99/热功耗、独立声学、真实HIL/72h仍待外部 |

后续使用同一批数据调试后的结果只能叫development confirmation。
独立确认需要新说话人/房间/素材/采集轮次；已有R01的不同帧、不同seed或AISpeech/AP两次消费不增加独立性。
真机补采优先延续app_audio_test的R01/R02/R03规范并补人工条件，而不是重复建立另一套场景计划。

现有采集不满足 `pcr02_capture_bundle` 的完整资格manifest、真实render timestamps、完整telemetry和
source/binary资格绑定；可以适配作FE开发输入，不能通过补造字段seal为资格bundle。
E001仍是v2.3.16的独立物理身份，研究B0仍是v2.3.55/37a179…；本轮均未迁移。

## 9. 本轮验证、风险与接续

- Host构建：严格warnings，`ap_process_pcm/ap_build_info_dump`目标完成；未执行全仓/板端门禁。
- 16个strict capture、62固定回放、两次重复确定性、6逐点控制、4损坏输入负例与artifact回读完成。
- 初次脚本误将build_info文本当JSON，在回放前停止；修正为保留原文后再执行，未掩盖该失败。
- Runtime Execution Policy与领域实验分别报告；不得由本地runtime conformance推导声学或产品PASS。
- Provider unresolved：正式耐久归档/跨仓canonical登记为NEEDS_REVIEW。
- fresh-main Verify与required summary已独立核查成功；本轮新增报告未提交，未获该CI覆盖。
  没有commit/push/PR/merge、版本变更或产品默认修改。

本轮可交付的是数据接入分析、可复现配置反例与下一轮测量契约。
下一次先重新核live main/checks和原始hash，解决数据/证据保留路由，再将最小适配与SYNC反例纳入现有FE入口。
选择产品配置前必须新增独立近端保护证据；本轮fixed1仅为开发diagnostic control。

复验命令（临时证据目录尚存时）：

```sh
rtk python3 /tmp/audio-fe-device-20261009/verify.py
```

原始执行脚本在 `analyze.py`、`sync_analyze.py`、`noise_analyze.py`；已生成的输出不覆盖重跑。
若重新完整执行，应先通过apply_patch把输出路径设为新目录并重新生成/读取对应计划，保留本轮JSON和负结果。
