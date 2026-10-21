# D18 精确捕获参考：冻结固定坐标对照

日期2026-10-11；experiment=`FE_DEVICE_EXACT_REFERENCE_D18`；kind=`diagnostic`。
goal_statement：在同一研究DSP库中核实际消费的reference样本，测量20点捕获坐标与原16点固定臂的差异。
总体目标active；不是新算法候选或真实声学delay选型；D8/D11/D14/D16拒绝结果不改。

## 数据、精确基线和两个臂

只读原119文件锁16个已查看development场景，不使用validation/blind；原D17结果与binding起止核hash。
固定DSP为原D16 r1隔离source与库，lib SHA256=4a748de3501241ff66787c8fdb4ccf445126ae49b1be3c4420b7e15e1ffb1170。
D16被拒绝且仍不晋升；本轮只是将其作为两臂相同DSP基线，跟踪/漂移都关闭，候选差异路径不参与选型。
不得把该库称shipping库或新的领域资格。

两臂均完整CALL、16k/双麦、stages255，其他配置字节相同，tracking=0、drift=0：

| 臂 | render输入 | initial_delay_ms | 预期实际reference |
| --- | --- | ---: | --- |
| fixed1 | raw.channel0完整160前缀 | 1 | raw延后16点，起始零 |
| used0 | 原ref_used完整160前缀 | 0 | used即raw延后20点，起始零 |

唯一因果差异为有效参考坐标4点；render和initial以显式适配构成该差异，不改DSP参数或API。
20点仅复制捕获消费坐标，不称物理最优。默认40ms不参与本新固定比较，也不改旧门禁。
全部16场景各两臂=32次完整回放。原D16已有fixed1的10场景须PCM/metrics逐字节一致。
所有原输入mic/原used/raw/config/旧receipt起止身份核验，未配对及160截尾保持原D17。

## P1：真实reference观测与已知答案

内部reference与work共享union，不能在process返回后读该字段冒充送AEC前reference。
为规避已证实的unity --wrap失效，只在新的/tmp source副本将ap_sync_get_reference定义重命名为d18_real；
runner提供原名observer，先调用real，仅在函数返回时读取out，不修改state/输入/out/return值。
只有该定义名替换允许，函数体/公共头保持原字节；新测量库身份不冒充原D16库。
每次写Float32LE reference160点，calls必须每capture帧一次，失败/短写立即非零终止。
原library链接无observer的同一runner，measurement library链接observer版，两个二进制显式区分。
known answer通过实际SYNC ring检查delay0/16/20/640、起始缺历史/跨帧、负号和边界；
全回放trace独立与对应S16/32768逐样本Float32LE对照，不只检查终态或metrics整数值。
严格C11 warnings；invalid args/不允许的trace模式非零；新fixture/runner与tools均研究用途，不安装SDK。

## P2：冻结回放、控制和测量

32次observe全部保存PCM/JSONL/reference；mic和render前缀来自原锁且无补尾/重采样。
fixed1原10场景与D16 byte-exact；used0的8零参考场景PCM与fixed1 byte-exact，
metrics只允许estimated_delay_ms不同，其他公共字段相同；这不是声学收益证据。
reference每帧恰160点、finite、逐float字节匹配预期，used0正好原used坐标，不重复延迟。
每臂jump/reset/slips都必须0；本来关闭跟踪，零计数不用于声学批准。
case07 run-2908630469-2466和case16 run-4874838670-2672各两臂另用原库no-observe完整重复，
4次结果与observe PCM/JSONL byte-exact，证明测试范围内观测中立，总36次回放。
32臂复用原device_replay.measure/metric_rows/window做相同PTS与latency窗口RMS/rail/counters，
不造第二音质裁判，不将reported ERLE当可用真值，不生成clean target或真人标签。
完整记录used0-fixed1三窗口及whole PCM差异/输出RMS；不按分数挑最佳初值或扩大搜索。

## P3：独立复审与收口

结果固定EXACT_REFERENCE_DIAGNOSTIC_NO_PROMOTION；若身份/观测/重复不一致则MEASUREMENT_INVALID并保留。
不因输出能量更低批准used0；完整音质、ASR/KWS、物理路径与DUT资源另验。
完成source/库/header/runner/input/config/trace/output/hash绑定及独立whole-change复审、中文入口/文档检查。
completion_claim=固定坐标实测和诊断完成；claimant=root；verifier=device_capture_independent_review；open_items=3。
retry_budget最多2次测量修正，不改冻结验收求绿；staleness_threshold任何source/input/旧receipt漂移即stale/replan。
单命令timeout120，build300；heartbeat和实际handle跟踪；三阶段明确；attestation起止hash回读。
stop_condition=pass/replan/blocked/abort；logical_task_open=true；milestone_close仅D18，不关闭总体目标。
live main=feb2f8ebc17a25bf248a63139ea4a219de39545d，#657 OPEN；summary成功、availability失败/soak skipped。
Provider unresolved知识线NEEDS_REVIEW；只仓内reviewing candidate，tmp保存证据且恢复时先核hash。
无SCM外写/设备写/产品src修改，AISpeech/E001、历史实验与shipping default/API不改。
