# Frontend Evolution v1 / 双麦与四麦开放研究

## 2026-10-20 本地研究与采集保全

[设备采集数据说明](DEVICE_CAPTURE_DATASET.zh-CN.md)记录原119文件的身份、数据角色和本地提交边界。
本次保留设备采集D0–D49离线研究源码与科学记录；多数历史实验仍依赖封存的/tmp成果链，
不能由源码提交推导fresh clone复现、真人效果或产品放行。D49原矩阵完整执行但开发准入拒绝，独立全量审计尚待。
同步前原工作树及历史README字节另有校验备份；本索引保留远端新进展与本地科学负结果。

## Authority and immutable proposal

The user approved this new stage on 2026-10-05 and authorized implementation. This is an explicit new integration/research requirement under the root agent contract, not permission to rewrite the completed software/public-data program. Research may change algorithm structures, run bounded preregistered searches, train/finetune models, prototype 1/2/4-mic processing, and evaluate streaming/quantization/SIMD. It does not automatically change shipping defaults, API/ABI, third-party rights, holdout roles or Product Certification authority.

- [Complete approved Chinese plan](PLAN.zh-CN.md): original bytes, not a rolling progress report.
- [Original task dependencies](TASKS.json): preserves `PLAN_ONLY_NOT_EXECUTED` as the proposal's historical state.
- [Original checksums](SHA256SUMS): enforced by executable tests. Amendments require a new reviewed document, not rewriting the proposal.
- Live work and evidence: GitHub issue #657; initial foundation PR #656. Neither an unchecked task nor a passing contract is an acoustic result.
- B0 software baseline: `37a1792861a89c815bec462f819f3deac7d29b09` / v2.3.55.
- E001 physical qualification remains `v2.3.16 / 57e4c64adc1cf06819e46e24e275ecd746d5f17f`; no implicit migration.

## First implementation tranche

FE00/FE01 are **in progress**, not fully qualified. The following foundations are implemented under `tests/validation/frontend_evolution/` and use only Python's standard library:

1. Exact-byte archive and dependency validation, including duplicate/non-finite JSON rejection.
2. A source inventory separating code, dependencies, weights, data and redistribution dispositions. Pinned or review-only references cannot silently become executable. Admission requires explicit review and materialized-source digests; a later runner must verify the actual receipt/bytes before execution. Metadata validation itself is not that runner or a legal determination.
3. Explicit S16LE/normalized Float32LE, interleaved 1/2/4-mic **research input contracts** with render channels counted separately. The current shipping SDK remains single/dual microphone. Planar conversion, channel remapping and resampling must be explicit adapter operations, not hidden inside this primitive.
4. Bounded 10 ms to native-hop reblocking. Native 128/384-sample hops remain their real durations. Output is emitted as soon as a native hop is available; no LCM-period wait, normalization or silent tail padding. Partial final hops fail until the adapter declares an explicit tail policy.
5. Per-case output receipts: exact expected case set, explicit success plus integer zero exit status, source/config/processor/evaluator/input/output hashes, exact mono sample count, safe paths, finite normalized floats, and a predeclared nonzero requirement where appropriate. An `OUTPUT_CONTRACT_PASS` is not a quality score.
6. Finite common-prefix/different-future causality checks with preregistered latency/lookahead. This catches hidden future dependence in tested cases, not every possible input. Never tune latency per case to improve a score.

These are offline Python research tools, not allocation-free DSP or a runtime sandbox. They neither execute nor download upstream code. Actual external adapters, model/data admission, baseline comparisons, array DSP and independent effect studies remain to be implemented. Acoustic metrics continue to use `validation/tools` and `validation/authority.json`; do not build a second evaluator here.

## Reference inventory

Machine inventory: `.github/research/frontend-evolution-v1/sources.json`. The initial list includes 26 reference/data/variant entries. Athena and libfvad commits were resolved live; the approved aispeech-earbuds commit is retained as review-only. Other entries remain explicitly unpinned/PLANNED, not falsely frozen. H-GTCRN noisy/IVA remain distinct entries. No external entry has been admitted for execution in this tranche.

Review code, dependency, model and dataset rights independently. Unknown rights on one resource do not block first-party prototypes or other reviewed references. No upstream source, coefficients, weights or binaries were copied by this change.

## 设备数据开发回放

[设备采集研究入口](DEVICE_CAPTURE_REPLAY.zh-CN.md) 提供独立schema-v2校验、显式256→160点适配、
70个固定公共API对照及逐例证据回读。只消费已查看的development数据；不依赖AISpeech工作树、
不改变产品DSP/default/API或E001，也不把总能量下降视为独立声学收益。

[D4拒绝结果](DEVICE_SYNC_D4_RESULT.zh-CN.md) 保留路径恢复回归；
[D5验证与观测](DEVICE_CONTINUATION_D5_RESULT.zh-CN.md) 记录完整本地门禁通过和短窗歧义证据。
这些开发诊断未形成可晋升的SYNC候选。[D6独立复审](DEVICE_REVIEW_D6_RESULT.zh-CN.md)
已闭合本地软件审查；设备声学与产品资格仍待。
[D7多帧测量](DEVICE_MULTIFRAME_D7_RESULT.zh-CN.md) 保留首次内存上限拒绝及Host旁路观测结果，
只用于下一假设设计，不改变产品SYNC或批准算法候选。
[D8固定长窗候选](DEVICE_ROUTE_D8_RESULT.zh-CN.md) 消除指定开发误跳并保持工程恢复，
同时保留默认延迟迁移被阻止和输出RMS上升的取舍；仅开发候选，选型仍不确定，shipping不变。
[D9已知延迟矩阵](DEVICE_ACQUISITION_D9_RESULT.zh-CN.md) 完成两版本各100例及独立重复，
保留26个必测项中16个共同短延迟获取失败和未通知缺帧差异；不能据零新增必测回归晋升D8。
[D10内部定位](DEVICE_TRACKER_D10_RESULT.zh-CN.md) 在14次既有输入回放中逐帧复现D9，
定位固定短延迟例中大量搜索区间未覆盖真值，并分别披露大跳确认与错误跳变后的小偏差漂移；仅工程诊断。
[D11搜索几何候选](DEVICE_SEARCH_D11_RESULT.zh-CN.md) 已知获取由10/26提高到26/26，
但真实开发回放两个场景新增jump/reset，按冻结条件拒绝；工程改善不能替代稳定性或声学资格。
[D12事件诊断](DEVICE_EVENT_D12_RESULT.zh-CN.md) 保留unity截获失败并建立独立测量身份，
逐帧等价回放解释新增事件的三次确认与AEC重置；未发现门禁绕过，不判断物理对齐正确性或批准新候选。
[D13事件契约](DEVICE_CONTRACT_D13_RESULT.zh-CN.md) 完成原库114次有真值工程回放，
分别保留正常获取、稳定保持、持续切换与短时分量结果；D11必验52/52、D8保留16项获取/切换失败，均无晋升。
[D14确认容差候选](DEVICE_CONFIRM_D14_RESULT.zh-CN.md) 将首候选容差收紧至0.5 ms，
保留52/52事件与26/26获取工程通过，但原设备两个场景仍新增jump/reset，实际只是延后事件，候选拒绝。
总体优化目标继续active，下一阶段核完整候选簇与持续路径证据，不从Host或计数下降推导声学/产品资格。
[D15持续路径诊断](DEVICE_PERSISTENCE_D15_RESULT.zh-CN.md) 完成16次全帧等价测量及15,273个分数独立复算：
rpm240事件存在被检验refined与实际提交anchor的支持差异；rpm480同一新路径在200 ms仍强相关。
两种情况分别推进提交对象一致性契约与真实时间轴/声学证据，不用加长窗口或更高相关分数豁免旧拒绝。
[D16提交锚候选](DEVICE_ANCHOR_D16_RESULT.zh-CN.md) 保留初次fixture断言失败与独立测量修正，
新增提交锚检查通过52/26工程门禁，但原两个现场场景仍新增jump/reset，候选拒绝。
下一阶段核设备适配配置与采集同步/初始延迟契约，独立冻结集成验收，不改写既有稳定性负结果。
[D17参考坐标诊断](DEVICE_ALIGNMENT_D17_RESULT.zh-CN.md) 独立重建全部16场景的7,715,328个native样本，
确认捕获used为raw.channel0延后20点；原1ms回放初值16点并不精确复制该偏置。
固定移位负例保留8个零参考场景不可辨识；该坐标结论不是物理声学路径真值或算法晋升。
[D18精确参考对照](DEVICE_EXACT_REFERENCE_D18_RESULT.zh-CN.md) 完成32条实际reference全帧观测与4次原库等价复跑，
明确原fixed1(raw16)与used0(raw20)有效坐标差4点；8个播放参考场景输出改变且窗口RMS上升。
启动欠载单独保留，不能从能量变化批准配置；后续在固定坐标上分离AEC残差与完整后处理贡献。

[D19同状态阶段诊断](DEVICE_STAGES_D19_RESULT.zh-CN.md)完成32次即时阶段观测，PCM/指标/reference全与D18逐字节相同。
AEC输入完全相同，差异首次出现在AEC估计回声/残差；NS/频域RES联合阶段扩大整段能量差距，AGC收窄差距。
阶段能量不能判定声学收益；首次测量编译失败与修正均保留，后续以实际AEC适配观测冻结新假设，不批准候选。

[D20首次分歧时序](DEVICE_TIMING_D20_RESULT.zh-CN.md)复用D19全量记录：4个非零参考场景eligible全程相同仍有AEC差异，
3个门控差晚于AEC差、1个同帧；门控差异不能解释全部输出差异。完整字段/区间保留，不将eligible当实际adapt次数。
后续冻结已知路径/固定门控的参考坐标控制实验；本轮不重跑DSP，不晋升默认或声学结论。

[D21已知路径控制](DEVICE_PATH_D21_RESULT.zh-CN.md)完成11次真实MDF独立工程执行，固定CALL AEC参数与门控，
三条纯延迟路径均收敛，offset16/20差随路径/阶段变号。三个负例、重复和未来前缀通过；不把工程ERLE当设备效果。
接续多反射/路径切换控制，不据简单合成结果选择产品参考坐标或改默认。

[D22多反射与切换控制](DEVICE_MULTIPATH_D22_RESULT.zh-CN.md)完成11次冻结MDF工程执行，静态两路径均收敛，
保留旧状态切换时出现短时负工程ERLE并逐步恢复。坐标差仍随阶段变号，不据此选默认；接续状态保持/reset与误通知控制。

[D23完整重置对照](DEVICE_RESET_D23_RESULT.zh-CN.md)完成17次真实工程执行，六keep逐byte复现D22；
真切换reset窗口改善约4.5～4.6dB，稳定A/B误reset损失约45dB。收益代价同时保留，不批准无条件重置，接续有保护状态处理。

[D24双状态原型](DEVICE_SHADOW_D24_RESULT.zh-CN.md)完成17次真实工程执行，primary全量等D22、shadow后半等D23。
四个稳定误通知场景未切输出，真切换在1002帧切旁路并改善约4.1～4.6dB；新增状态33020字节和事件后双AEC调用。
这是研究算法原型，不批准产品默认；人声、无crossfade边界、真实退回及目标资源仍待。

[D25路径退回与近端门控](DEVICE_RETURN_D25_RESULT.zh-CN.md)完成26次真实工程执行，冻结D24选择器不调参。
短B路径后实测1002帧切旁路、1202帧退回，回A首窗误差增加约0.157～0.178dB，后续保持原输出。
已知双讲标签减少合成近端污染却阻止B路径恢复，收益代价均保留；独立噪声/oracle标签不能批准真人保护、检测或产品默认。

[D26设备开发数据双状态回放](DEVICE_FIELD_D26_RESULT.zh-CN.md)完成66次真实执行，primary估计回声和残差逐字节复现D19。
16个激活主臂累计538次往返切换，每臂5～55次；固定窗口残差能量有增有减，不能据此认定音质改善。
冻结D24选择器未调参，本轮仅工程诊断；频繁切换、真人保护、输出边界与目标资源继续推进，产品默认未批准。

[D27固定最短保持实验](DEVICE_DWELL_D27_RESULT.zh-CN.md)完成90次真实选择器执行，不重跑AEC。
固定500ms保持将设备主矩阵切换由538降为243次，首次接管不延迟，D25已知退回/合成近端对照输出不变。
同时保留最高约+0.845dB窗口残差能量代价；仅开发工程候选，无独立音质或产品晋升，后续核输出边界与真人保护。

[D28固定输出过渡实验](DEVICE_TRANSITION_D28_RESULT.zh-CN.md)完成90次真实C输出处理，冻结D27控制，不重跑AEC/选择器。
固定20ms过渡将243个设备事件的残差差分平方和合计降低约14.84%，两路起点附加跳变为0。
同时保留55个事件梯度增加、设备窗口最高约+0.075dB能量与合成近端最高约+0.126dB误差代价。
仅开发工程候选，不证明无点击或真人保护；后续核真实检测闭环、完整前端链与目标资源。

[D29实际AEC、选择与过渡集成](DEVICE_ONLINE_D29_RESULT.zh-CN.md)完成46次真实逐帧C回放，复现D26/D25四bank、D27选择与D28过渡结果。
这是同一单路输入上的两套AEC状态，外部far/dt冻结，未新执行Activity检测或完整前后处理链；不新增声学收益。
局部状态和帧缓冲71,196B，两套AEC状态自身超过B0 50,000B预算；仅研究集成通过，不批准设备部署或产品默认。

[D30实际Activity集成](DEVICE_ACTIVITY_D30_RESULT.zh-CN.md)完成46次实际回放；原Activity驱动双AEC/保持选择/过渡，设备原11输出全部复现。
4个合成dt来源各400帧oracle门控未被实际检测触发，known-near原窗口出现显著误差代价，whole改善不能掩盖后续near窗口退化。
固定参数未调，局部资源71,224B；仅集成/依赖诊断，不批准真人双讲保护或产品默认，接续可辨识near观测与完整前后处理。

[D31近端与路径失配观测](DEVICE_OBSERVABILITY_D31_RESULT.zh-CN.md)消费原46例/126486帧，不重跑DSP。
冻结的同帧内积和残差功率比揭示近端与路径失配的混淆，原240窗和零能量null全部保留，不新增检测阈值或声学裁判。
原执行顺序偏差与跨case数组生存期问题保留，修复后独立复审并用新根重测，47输出逐byte同；不是检测器或产品晋升。

[D32因果近端保护反馈候选](DEVICE_CAUSAL_GUARD_D32_RESULT.zh-CN.md)完成92次C回放/252972帧，按原五项准入被拒绝。
静态A近端覆盖199/200帧，但ABA纯echo误保护892–895帧、恢复窗口error最高增加约33.14dB，首次near覆盖仅68/200帧。
monitor原12输出复现D30，feedback未改变原Activity；保留负结果，接续路径/适配可信度与near保护边界，不批准产品默认或目标资格。

[D33通知时保护历史失效消融](DEVICE_GUARD_INVALIDATION_D33_RESULT.zh-CN.md)完成92次C回放/252972帧，仍按原准入拒绝。
纯echo误保护由ABA的892–895帧降为0、D32额外恢复退化消除，但所有8near首段保护归零，静态误通知也失去保护。
monitor全部13输出复现D32，near与通知可信度须联合继续验证；误保护减少不批准完整检测或产品默认。

[D34反馈隔离诊断](DEVICE_GUARD_FEEDBACK_D34_RESULT.zh-CN.md)复用三臂138个case-arm/379458状态帧，不重跑DSP。
未反馈monitor仍有ABA纯echo误保护218–221帧，但feedback延长至892–895帧；切换near首段潜在覆盖仅87/200帧。
因此隔离观测单独不足原准入，下一研究须处理初始失配/near辨识；潜在触发不是实际保护或候选批准。

[D35历史参考相关性诊断](DEVICE_REFERENCE_COHERENCE_D35_RESULT.zh-CN.md)对原46例/126486帧执行standalone observer，不重跑AEC。
固定历史搜索增加零延迟内积遗漏的回声信息，但ABA首near与纯echo分布仍重叠；16个field来源参考全零，保留null。
本轮未选阈值或改变保护反馈，仅诊断NO_PROMOTION；下一研究须处理混合near/echo的时间可解释性。

[D36前帧延迟预测诊断](DEVICE_HELD_LAG_D36_RESULT.zh-CN.md)固定前帧lag计算原46例/126486帧，不重跑DSP或当前lag搜索。
纯echo具有延迟延续性，静态near峰值多不延续；ABA首near仍含稳定echo，与纯echo重叠，不能单独批准保护。
按冻结停止条件replan转向可解释残差模型，不继续相近诊断/阈值寻优；field零参考/null和NO_PROMOTION保持。

[D37因果残差模型](DEVICE_CAUSAL_RESIDUAL_MODEL_D37_RESULT.zh-CN.md)以过去帧有符号系数预测当前残差，完成46例主测量；
独立审计在第五例frame1831因大创新比例的普通求和末位差异失败，保持NUMERICAL_CONTRACT_FAILED_REPLAN。
[D38精确求和接续](DEVICE_CAUSAL_RESIDUAL_MODEL_D38_RESULT.zh-CN.md)仅修改六类求和结构，13项测试及46例主测量通过；
独立Decimal全46例/126486帧/240窗exact审计通过，旧D37失败保留；数值验证和声学/真人near/目标板资格分别验收。

[D39下游接续](DEVICE_DOWNSTREAM_D39_RESULT.zh-CN.md)消费冻结D30匹配echo/residual，实际接续原NS联合频域RES、受控AGC与VAD。
两臂92次执行/252972帧主测量及首次独立全量审计通过，最终收口进行中；[计数勘误](DEVICE_DOWNSTREAM_D39_COUNT_ERRATA.zh-CN.md)披露每臂45个whole+195个固定窗口。
合成无near残余能量降低，但含near工程误差中位增加约9.34dB，保持NO_PROMOTION；完整SDK、AISpeech产品链路、真人效果和目标板资源分别待证。

## Foundation verification

```sh
(cd docs/research/frontend-evolution-v1 && sha256sum -c SHA256SUMS)
python3 tests/validation/frontend_evolution/test_contracts.py
```

The existing `.github/scripts/verify-docs-gate.sh` executes these tests for docs and full Verify paths, so the required aggregate summary includes this foundation without introducing another one-shot or scheduled workflow. Full-main verification and the existing release identity gates remain unchanged. Passing tests do not mean FE00-FE09 are complete.

## 接续顺序与中文边界

完整方案已归档；新研究允许结构改进、有限参数实验和训练，不继承旧阶段的 candidate-zero 限制。旧研究结论、失败与归档保持不变。后续进度只更新 #657 和新的实验记录，不把原方案改成虚假的执行证据。

当前已经实现授权/来源登记、帧契约、有界重组、逐例输出检查和有限因果负例。尚未完成上游最小适配器、实际效果对照、原生四麦 DSP、NN 流式/量化和端侧候选资格。四麦输入契约测试不等于 C SDK 已支持线性或环形四麦；25 项基础测试不等于 25 项音质实验。

下一步先完成首批来源/依赖审查及 B0、WebRTC、SpeexDSP、libfvad、Athena 的最小可复现对照，再推进 FE02/03 的几何、分数延时和固定滤波。经典增强与神经研究各自复用同一评估入口。最多三个研究通道，不新增大量一次性工作流，不用独立验证或 blind 数据调参。改 shipping 默认或公共 ABI 时另行执行版本与资格门禁。

## First executed external reference

See [libfvad reference qualification](LIBFVAD_REFERENCE.md) for the first actual
source-byte admission, C adapter, frozen D0 paired VAD replay and evidence checks.
Only the minimal libfvad core is admitted in the catalog; other entries retain
their prior pending/review-only status. FE00/FE01 and the full #657 program remain
in progress. The initial-tranche description above is historical, not a claim
that no later reference can be admitted. No shipping VAD default is changed.

## Native array research prototype

[Native 1/2/4-mic geometry and fractional-delay BF](ARRAY_NATIVE.md) is the next
FE02/03 executable tranche. It processes actual multichannel PCM in C and checks
analytic answers on native/sanitized and AArch32/QEMU builds. It is not installed
in the 2.x SDK. DOA, smooth live steering, BF/AEC integration, independent speech
quality and the final C4 delivery remain open in #657; no new product claim is
inferred from the engineering checks.

## Controlled live steering continuation

[FE03 controlled steering](ARRAY_STEERING.md) extends the same native research
core with a shared-history two-bank crossfade and a small timestamp/confidence
controller. The existing array qualification retains static tests and adds
transition known answers. This is not recorded-speech or AEC quality validation,
automatic DOA, a C4 SDK, or completion of the full research program.

## 设备采集频域 RES 因果对照

[D40频域RES消融](DEVICE_FREQUENCY_ABLATION_D40_RESULT.zh-CN.md)已完成92次执行及独立全量数据审计。
仅全帧关闭频域RES：合成含near固定窗口的配对工程误差中位下降约6.19 dB，但无near窗口的残余能量中位增加约16.72 dB；不建议全局关闭产品RES。
该轮不晋升候选，不代表真人识别/目标板资格；最终本地收口记录单列。既有D39快照中的README是其历史绑定，后续新增入口不覆写该旧快照。

[D41因果频带创新保护](DEVICE_SPECTRAL_PROTECTION_D41_RESULT.zh-CN.md)完成184次主执行及首次独立全量审计。
candidate含near配对误差中位下降约5.15 dB，但无near固定窗能量中位增加约14.11 dB，最大约16.59 dB；纯echo整例最大增加约2.17/2.11 dB，按冻结1 dB门槛拒绝。
monitor四原输出复现D39；归一化创新量尚不能批准语音保护或产品默认。后续核查绝对创新量及残余来源的可辨识性，保持已有失败和独立数据/真人/目标板资格边界。旧D40 README快照只代表其历史绑定。

[D42过去噪声功率约束](DEVICE_NOISE_CONDITIONED_PROTECTION_D42_RESULT.zh-CN.md)已完成184次主执行及首次独立全量审计。
候选把纯echo整例最大能量增加降至约0.39/0.54 dB，但无near固定窗最大仍+3.71 dB，near配对误差中位改善约2.18 dB，按原1 dB和-3 dB门槛拒绝。
原NS噪声估计不能据此视为残余来源真值；保留拒绝及测量覆盖边界。旧D41 README快照保持历史绑定，不覆写。

## Recorded-speech spatial diagnostics

[FE03 recorded-speech probe](SPEECH_SPATIAL.md) admits fixed LibriSpeech bytes and
runs the unchanged native BF against actual speech in explicitly synthetic
free-field scenes. Reference/mean/linear/cubic arms, speaker roles and source
selection are fixed before scores. Component transfer and canonical SI-SDR are
reported together, with co-located negative controls and no automatic promotion.
This is not a room recording, DOA/AEC test, installed C4 SDK or full FE closure.

## 设备采集过去功率归因诊断

[D43过去功率诊断](DEVICE_POWER_ATTRIBUTION_D43_RESULT.zh-CN.md)完成184次测量、505944帧及两项独立审计，原五输出与D42逐字节相同。
近端结束后的既有最坏窗中，旧噪声扣除使约62.9%的有效频点floor为零，但约33.5%仍抬升target；全960组固定窗描述均经独立复算。
这解释已有保护行为的分布，不批准新算法；D42拒绝保持，全部FFT/EMA/噪声历史重建和真人/目标板资格仍待。
[D43审查记录](DEVICE_POWER_ATTRIBUTION_D43_REVIEW.zh-CN.md)单列覆盖、负例、实际回执和后续边界，旧D42 README快照保持其历史身份。

## 设备采集绝对创新功率门控

[D44绝对创新功率门控](DEVICE_INNOVATION_NOISE_GATE_D44_RESULT.zh-CN.md)完成184次主处理、505944帧及首次独立全量审计；全部960组新波形统计和原准入独立复算。
固定严格I>2N门控使无near最大增量降至约1.09/1.56 dB，但仍超过1 dB；near配对误差中位改善约1.84 dB，未达3 dB，候选DEVELOPMENT_REJECTED。
停止本规则系数搜索，保留原门槛及失败；[D44审查记录](DEVICE_INNOVATION_NOISE_GATE_D44_REVIEW.zh-CN.md)单列独立覆盖、已通过整批审查和待执行本地收口。旧D43 README冻结快照保持历史身份，真人/目标板/shipping资格未据此成立。

[D45合成增益后保护](DEVICE_POST_NS_PROTECTION_D45_RESULT.zh-CN.md)完成184次处理/505944帧及首次独立全量审计；960组新波形统计和原准入独立复算。near中位约-3.270 dB、20/24窗改善，但no-near最大+6.552 dB，pure-echo whole最大+1.255/+2.114 dB超过原上限，候选DEVELOPMENT_REJECTED。
停止本映射参数搜索；[D45独立审计记录](DEVICE_POST_NS_PROTECTION_D45_REVIEW.zh-CN.md)明确测量PASS与候选拒绝，[结束后保护释放定位](DEVICE_POST_NS_PROTECTION_D45_DIAGNOSIS.zh-CN.md)保存单例尾部差异集中前10帧的线索，不冒称根因或新增评分。整批审查、冻结和本地收口按实际后续回执记录，旧快照保持；真人/目标板与shipping资格另行验收。

## 设备采集路径失配与保护释放归因

[D46固定分段归因](DEVICE_RELEASE_PATH_ATTRIBUTION_D46_RESULT.zh-CN.md)复用D45已生成波形和power数据，不重新执行DSP。24配对、168固定段及48项whole统计全部经首次独立审计精确复算，最大数值绝对误差0。
纯echo ABA回A后的1210–1600帧仍有明显保护差异：r20 primary/selected抬升帧数375/377，NS差异能量约0.254/0.477；该失败不能仅归给near结束后的短尾。路径失配误保护及释放机制需在新实验身份下分别验证，D45拒绝及原准入保持。
[D46审查记录](DEVICE_RELEASE_PATH_ATTRIBUTION_D46_REVIEW.zh-CN.md)区分实际审计、整批审查及本地收口。[历史README修订](DEVICE_RELEASE_PATH_ATTRIBUTION_D46_AMENDMENT_README.zh-CN.md)保存测量消费的旧625af26c版本及显式备份映射；旧199输入和D45快照保持历史身份，当前追加版另行冻结。D46仅测量诊断，不批准算法、真人效果或目标板产品资格。

## 当前创新映射与测量契约解耦

[D47当前创新实验](DEVICE_CURRENT_INNOVATION_D47_RESULT.zh-CN.md)保留一次正式测量失败：17条C命令成功，但第17例的旧floor上界检查失败，仅16例测量完成，无最终result/binding。旧上界属于旧算法专有性质，不能将该测量耦合失败当成当时已完成的算法准入判断。

[D48测量契约解耦](DEVICE_CURRENT_MEASUREMENT_D48_RESULT.zh-CN.md)固定D47算法，只修复测量适配器，完成184路/505944帧；独立复算960组测量，RMS最大误差0，13636项身份起止一致。测量结论为MEASUREMENT_CONTRACT_VERIFIED_NO_PROMOTION；原开发准入两臂accepted=false：near误差中位约-5.5495 dB、20/24改善，但no-near最大+16.8727 dB，pureecho whole最大primary+2.3947/selected+2.7978 dB，均超过原+1 dB限制。停止本映射系数搜索，后续结构假设另立获审查身份。

[D48独立复审](DEVICE_CURRENT_MEASUREMENT_D48_REVIEW.zh-CN.md)记录测量合同和算法负结果，完整FFT/全帧bin/EMA/noise历史重建仍未覆盖，真人、AISpeech产品链与目标板资格分别验收。[README历史身份保全](DEVICE_CURRENT_MEASUREMENT_D48_AMENDMENT_README.zh-CN.md)明确ac998版本完整字节的新保存映射，旧625af备份和D46快照保持。机械whole、最终snapshot与本地阶段收口按后续真实回执报告，不据本索引声明已完成。

## Fixed external baselines

[SOF FIR, GTCRN and UL-UNAS limited comparisons](EXTERNAL_BASELINES.md) records
three exact-source local research adapters, full PCM boundaries, source/model
admission and fixed disclosed-input evidence. Recovery and new execution status
are explicit. These references do not change shipping defaults or complete C4,
real-robot qualification or the frozen NS research program.
