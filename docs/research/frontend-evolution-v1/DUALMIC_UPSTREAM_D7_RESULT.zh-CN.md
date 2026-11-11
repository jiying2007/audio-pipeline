# D7 上游中性观察：首次实际有效回执与公开可读边界

实验 FE-DUALMIC-UPSTREAM-D7，候选数0。首次程序终态
UPSTREAM_OBSERVATION_VALID_NO_PROMOTION；不允许质量推广、候选准入或自动后继搜索。
追踪 [#944](https://github.com/jiying2007/audio-pipeline/issues/944)、
[PR #945](https://github.com/jiying2007/audio-pipeline/pull/945)；总研究 #657 继续开放。

## 1. 精确来源、原件与尚未完成的独立审计

- 执行源码 fee863bff0ccdd58661db90908c6460a2c69af0a，
  tree6017f54b4a7facac27c305cdfd7b0d0aacf95d71。
  冻结方法/输入锁4b7f4496d9d9fef5589456f4ac377ddfa29e24e3保持原字节；
  生产仍e348843a570503728930f06451633262b2546fa5 / 2.3.64，无DSP修改。
- [Frontend Research run43055603884 / attempt1](https://github.com/jiying2007/audio-pipeline/actions/runs/43055603884)，
  [dualmic-upstream-d7 job130644189276](https://github.com/jiying2007/audio-pipeline/actions/runs/43055603884/job/130644189276)
  的执行及上传步骤均为success；其它历史研究jobs均skipped。
- [artifact13871038614](https://github.com/jiying2007/audio-pipeline/actions/runs/43055603884/artifacts/13871038614)，
  frontend-research-dualmic-upstream-d7-43055603884-attempt-1，
  3535个上传文件，663075627 bytes；
  上传日志/API SHA256 7f29a1a0129f53beb7e103343bcffe9b1420a98ab43d05cac1136338e09fc451，
  API expires_at=2027-02-09T16:10:09Z。
- 原D2 ZIP仍为artifact13553232106、474165229 bytes、
  SHA256 a3ab7823fdcd7586c3b72eb214b5536dcfb7531fdf0b1611d49e1575a29b2c3d。
  stdout准入回执报告3551成员、861385743解包字节、
  original_D2_readback_exact=true，elapsed50.91596095799999秒；
  没有另下A/C或运行模型。
- 本文依据已直接读取的完整job文本、Actions API和准确执行源码；
  [逐字保存的首次summary stdout JSON](dualmic-upstream-d7-first-stdout.json)
  含全部18组、完整精度和null，原数据只移除日志时间戳。
  当前仅有ZIP下载file-reference，没有本任务允许的connector内ZIP成员文本读取入口，
  因此尚未独立解包读取report/state/taps/phase/negative/completion原件。
  不把程序自己的readback与独立作者的二进制原件审计合并。
  driver的completion本来就明确独立审计仍需单独完成。

此终态是首次实际运行的程序有效回执，不等于最终PR/main保护资格或已完成独立原件审计。
后继新head及fresh-main必须各自通过准确源码门禁，不沿用本head的成功。

## 2. 已打印的完整计数与检验路径

stdout报告measurement_valid=true、promotion_allowed=false、models_executed=false：
60视图、35916帧、5746560样点/新lane、362个固定窗、32个可评分参考、8个原reset。
其余28例参考保持null。actual_mode_census={"1":35916}：
所有本轮BF调用实际track_direction=1；这不是lag/route分布。

按准确源码，要打印这一终态必须先完成全部原件身份、当前plain/currentobserver/原A/C
PCM及metrics JSONL三方byte桥、旧D1七lane/control复现、完整state/输出方程、
原固定评分与readback，然后完成51类实际证据篡改。
complete_report逐项断言51个类别/顺序、untouched guard、status和expected=observed reason，
再校验最终completion在内的512MiB新结果闭包。
成功job表明这一程序路径返回；本文尚未从artifact独立读回各条51负例回执和原二进制。
不能据此伪造逐条耗时、具体状态值或独立审计PASS。

原300秒/phase、min(30,remaining)/child、20分钟job及16MiB源/512MiB新结果预算不改。
执行步骤日志从16:10:25.5959746Z到summary的16:14:59.5609899Z，间隔约273.965秒；
这是日志墙钟跨度，不冒称全部phase精确耗时。
准入器50.915961秒来自其实际打印字段。其它phase数值回执尚未独立读取。
663075627-byte上传ZIP包含原474165229-byte输入ZIP与新结果，不是单独新结果闭包的字节数；
不能用合包压缩大小替换512MiB新结果边界，也不猜测未打印的实际新结果总字节。

## 3. 全部已打印固定共同跨度增量

以下每格为min / median / max，单位dB，来自原固定raw-clean参考的共同跨度SI-SDR增量。
A每个profile/scenario有4个相关视图，不能当4名独立说话者；
两个profile的上游聚合相同，不能重复计为独立证据。
n=0的null保留，不转成0。表显示6位小数，链接JSON保留完整原精度。

| 组 | profile | scenario | cases | rawL→HPFL | rawR→HPFR | HPFL→BF | HPFR→BF |
|---|---|---|---:|---|---|---|---|
| A | assistant | doubletalk-nominal | 4 | -7.583000 / -2.393775 / -0.970109 | -7.698062 / -2.424012 / -0.966344 | -0.067502 / 0.149816 / 0.284574 | -0.093273 / -0.004980 / 0.255282 |
| A | assistant | doubletalk-weak | 4 | -3.967566 / -1.218951 / -0.683275 | -4.044676 / -1.229204 / -0.661440 | -0.020873 / 0.142653 / 0.234502 | -0.049159 / -0.040251 / 0.168432 |
| A | assistant | far-only | 4 | null (n=0) | null (n=0) | null (n=0) | null (n=0) |
| A | assistant | near-only | 4 | -131.492552 / -129.411243 / -126.946026 | -131.492552 / -129.411243 / -126.946026 | 0.000000 / 0.000000 / 0.000000 | 0.000000 / 0.000000 / 0.000000 |
| A | assistant | path-change | 4 | null (n=0) | null (n=0) | null (n=0) | null (n=0) |
| A | assistant | render-gap | 4 | null (n=0) | null (n=0) | null (n=0) | null (n=0) |
| A | assistant | silent-render | 4 | -131.492552 / -129.411243 / -126.946026 | -131.492552 / -129.411243 / -126.946026 | 0.000000 / 0.000000 / 0.000000 | 0.000000 / 0.000000 / 0.000000 |
| A | call | doubletalk-nominal | 4 | -7.583000 / -2.393775 / -0.970109 | -7.698062 / -2.424012 / -0.966344 | -0.067502 / 0.149816 / 0.284574 | -0.093273 / -0.004980 / 0.255282 |
| A | call | doubletalk-weak | 4 | -3.967566 / -1.218951 / -0.683275 | -4.044676 / -1.229204 / -0.661440 | -0.020873 / 0.142653 / 0.234502 | -0.049159 / -0.040251 / 0.168432 |
| A | call | far-only | 4 | null (n=0) | null (n=0) | null (n=0) | null (n=0) |
| A | call | near-only | 4 | -131.492552 / -129.411243 / -126.946026 | -131.492552 / -129.411243 / -126.946026 | 0.000000 / 0.000000 / 0.000000 | 0.000000 / 0.000000 / 0.000000 |
| A | call | path-change | 4 | null (n=0) | null (n=0) | null (n=0) | null (n=0) |
| A | call | render-gap | 4 | null (n=0) | null (n=0) | null (n=0) | null (n=0) |
| A | call | silent-render | 4 | -131.492552 / -129.411243 / -126.946026 | -131.492552 / -129.411243 / -126.946026 | 0.000000 / 0.000000 / 0.000000 | 0.000000 / 0.000000 / 0.000000 |
| C | assistant | mandarin-clean | 1 | null (n=0) | null (n=0) | null (n=0) | null (n=0) |
| C | assistant | mandarin-duplex | 1 | null (n=0) | null (n=0) | null (n=0) | null (n=0) |
| C | call | mandarin-clean | 1 | null (n=0) | null (n=0) | null (n=0) | null (n=0) |
| C | call | mandarin-duplex | 1 | null (n=0) | null (n=0) | null (n=0) | null (n=0) |

可以直接读出的有限结果：
- nominal双讲的HPFL→BF中位+0.149816dB，范围−0.067502至+0.284574；
  HPFR→BF中位−0.004980dB，范围−0.093273至+0.255282。
- weak双讲对应中位+0.142653与−0.040251dB，正负视图均存在。
- near-only及silent-render两路HPF→BF共同跨度增量均0；
  这句话只描述该已打印分数，不推出未读出的lag或fallback状态。
- near-only/silent-render的raw→HPF中位约−129.411243dB必须保留，
  但S003 HPF-aware oracle已证明此raw-clean比较高度依赖参考域。
  本轮不换参考、不把大幅下降命名为HPF损伤、听感问题或算法根因。
- A无near参考的far-only/path-change/render-gap，以及全部C视图都保持null。
  C mixed duplex绝不是clean truth。

这些是已有完整报告中四个stage比较的描述性聚合，不是新的评分/筛选；
不将中位数盖过负视图，也不推导KWS/ASR/MOS、真人阵列或SSC305物理结果。

## 4. 尚不能从首次stdout回答的实际状态关联

首次stdout只含聚合和mode census，没有输出各例的tracked/effective lag、
fallback/hard/strong-channel、recovery/arm/fixed-health、score-update cadence、
固定窗口状态或来源放置关联。它们按源码保存在完整report/state artifact，
但本次还没有直接读取这些值。不能仅由BF分数或track_direction=1声称
“跟随远端回声”“near从150帧出现时导致转向”或选择一个听感根因。

为读取已计算结果，后继仅将自己已验证report中全部60个whole、60个common及362个固定window
association对象与同一原stage结果序列化到16MiB上限的stdout字节流，并附既有身份、phase/51负例回执。
每块6144原始bytes、base64编号，BEGIN/END绑定run/source/字节数/分块数和整体SHA256；
必须等完整校验与job success后消费。仅内存/stdout导出，不改completion后的结果文件闭包。
这不会重新定义窗口、指标、阈值或新增科学运算；准确实现仍须独立审查后才更新活动PR分支。
后继日志若可读，应按其自己的source/run身份追加，不冒充首次run的原件内容。
原数据、原失败、原null和不推广边界全部保留。

## 5. 两次先前失败不覆盖

1. head62bf806998aa2c6d551dbaa44544db72d751b8cc，
   [run43040461777](https://github.com/jiying2007/audio-pipeline/actions/runs/43040461777)：
   plain-build / D7_BUILD_FLAGS，根101.457399s。
   [artifact13863789529](https://github.com/jiying2007/audio-pipeline/actions/runs/43040461777/artifacts/13863789529)，
   474615764 bytes，SHA256 78f210dc83f93778442d94425ec03af4cda471c5afa3e3911e6ac627a67fadc7。
2. heada3dea0ad4560f8c198247c288e3525dcc6824a8e，
   [run43052616782](https://github.com/jiying2007/audio-pipeline/actions/runs/43052616782)：
   plain-build / D7_GENERATED_UNITY，根59.402543s。
   [artifact13871015523](https://github.com/jiying2007/audio-pipeline/actions/runs/43052616782/artifacts/13871015523)，
   474702632 bytes，SHA256 23775f6be36e594b2bb3ba069906951d48bc7feddd0ae37b3a4990b1275ca42c。

源码诊断、严格修复范围与不可冒称artifact实测的边界见
[实施说明](DUALMIC_UPSTREAM_D7_IMPLEMENTATION.zh-CN.md)。
第三次成功只说明精确fee863bf执行通过，不抹去前两次实际失败。

## 6. 新head完整日志证据：与首次fee原件严格分开

以下新增结果只属于源码224fd79ed22db416fccf7d8374f3be041cdabefe，
tree d2893a54e83b55e90e49f8b2c631ddfd6b8bef3c。
[run43060600294 / attempt1](https://github.com/jiying2007/audio-pipeline/actions/runs/43060600294)、
[job130661894462](https://github.com/jiying2007/audio-pipeline/actions/runs/43060600294/job/130661894462)
的主执行和上传均success，旧研究jobs仍skipped。
[artifact13872539067](https://github.com/jiying2007/audio-pipeline/actions/runs/43060600294/artifacts/13872539067)
为663133601 bytes，SHA256
3a88a6c774a9ea1baa9bf109fe39edbaaa2b4e07802df5fce05b830f9da734ba；
到期2027-02-09T16:40:15Z。

直接读取完整job文本后，以纯JS按编号重组844块，核对唯一BEGIN/END、顺序、分块长度、
原始5180773 bytes及SHA256
251d5d2cbef5b0593f52cbd1f4eb42ed0f9c3792c642aac4bd542c26c041ba4d，
之后才解析JSON；同时通过Actions API确认成功job、源码及上传artifact身份。
独立审查也重新读取并验证同一流。这是新运行导出报告的独立文本/描述符审查，
**不是解包首次fee ZIP，也不是独立重算二进制波形/state的审计**。

[完整案例/固定窗紧凑摘要](dualmic-upstream-d7-43060600294-summary.json)
保存原顺序60例、60 whole、60 common及全部362窗的lag/route/cadence计数、
5路原stage分数/RMS/peak与4种原增量、全部null原因、51负例完整回执、7phase回执、
201命令身份/状态/耗时及来源描述符。数组列名在projection字段中明确列出；
无按结果删窗、选声道或另算SI-SDR。文件679191 bytes，
SHA256 45f4c3c989b0cf3cac94d56bac1c16ea79ab72343f7edeabb6c5ef52143012de。
它是较小的精确数值投影，不冒充完整原报告；完整EMA统计、counter全值直方图、
cadence帧列表、命令argv和源/结果清单仍在已校验的原日志流中。
未导出的逐帧关联、历史数组和原tap字节仍只在artifact中。
不能从边际窗口直方图还原精确帧内先后关系。

新运行的totals与18组聚合逐项等于第3节首次fee输出，仍为60例、35916帧、
71832次HPF调用、35916次BF调用、每lane5746560样点、32可评分/28null、8 reset。
新report.json描述符：37007122 bytes，
SHA256 470ca3f2195fc913a652f9c75d0a74c6e2f465fc5fb7273646a114c4b9e3b8b1。
不把新运行的源码身份替换到首次fee结果上。

## 7. 实际whole状态与tracked/applied差别

所有35916帧的实际track_direction均1。effective_output_lag总计
0=16244、−1=19640、+1=16、+2=16。
下表每行是**每个profile**的完整组计数，call与assistant逐例stage/state科学对象相同；
这里只合并重复展示，不将它们当独立重复实验。A每行4个相关pair视图；
C每行1例。tracked取BF更新后state.lag，applied为实际fallback分支作用后的lag。

| 组 / scenario | 例数 | 帧数 | tracked lag:帧 | applied lag:帧 | applied转移数 | soft fallback帧 | reset数 |
|---|---:|---:|---|---|---:|---:|---:|
| A / near-only | 4 | 2400 | 0:2400 | 0:2400 | 0 | 0 | 0 |
| A / silent-render | 4 | 2400 | 0:2400 | 0:2400 | 0 | 0 | 0 |
| A / far-only | 4 | 2400 | -1:2384 / 0:16 | -1:2384 / 0:16 | 4 | 32 | 0 |
| A / doubletalk-nominal | 4 | 2400 | -1:1176 / 0:1208 / +1:8 / +2:8 | -1:1180 / 0:1204 / +1:8 / +2:8 | 28 | 32 | 0 |
| A / doubletalk-weak | 4 | 2400 | -1:1244 / 0:1156 | -1:1248 / 0:1152 | 20 | 32 | 0 |
| A / path-change | 4 | 2400 | -1:2384 / 0:16 | -1:2384 / 0:16 | 4 | 32 | 0 |
| A / render-gap | 4 | 2400 | -1:2364 / 0:36 | -1:2364 / 0:36 | 8 | 32 | 4 |
| C / mandarin-clean | 1 | 529 | 0:529 | 0:529 | 0 | 0 | 0 |
| C / mandarin-duplex | 1 | 629 | -1:260 / 0:369 | -1:260 / 0:369 | 10 | 0 | 0 |

- nominal/weak的tracked与applied计数确有差别，不能只读state.lag代表输出。
  搜索半径仍±3、单次更新slew仍±1；+2不是违反±1更新规则。
- 全部hard_fault=0、hard_arm_count=0、fixed_health_counter=3；
  strong_channel字段全0，不能据此声称所有帧都输出左声道，只有对应fallback分支才适用。
- soft fallback共320帧，只在pair-3的五种含far场景、两个profile共10例出现，
  每例32帧。每例固定窗[16000,32000)内4帧，[32000,48000)内28帧；
  每例recovery_after=1…7各4帧，其余为0。此分布是soft recovery，不是hard fault。
- score_updates增加共8982次；actual cadence记录四帧更新节奏，
  fixed-health值不变并不意味着做过一套额外健康检测。
- render-gap每例在frame300/sample48000收到flags2/lost_frames4的原discontinuity，
  两个profile共8次reset。path-change保持0 reset，不能混为同一种事件。
- C duplex虽也有−1/0状态变化，near来源仍unknown，所有近端SI-SDR仍null；
  C clean名称不构成本实验已准入的clean truth。

这补上了D1合并tap无法分辨的实际上游状态，但还不能判定“BF统一锁在回声上”。
near-only/silent-render全部lag0；含far组与双讲组的分布不同，并且双讲内部会变化。
这是混合输入下的stage/state关联，不是已经找到可推广的算法改动。

## 8. 全固定窗口矩阵及双通道stage解释

窗口索引0…5为A原固定物理样点
[0,16000)、[16000,32000)、[32000,48000)、[48000,64000)、
[64000,80000)、[80000,95840)。
每profile前5窗各4×100帧，末窗4×99帧。
它们分割common的599帧/例，不是whole600帧；不得用末窗补齐或错当新增窗。
C clean末窗[80000,84480)为28帧，C duplex另有第6窗[96000,100480)为28帧。
下表遍历全部scenario及所有固定窗，格内仍为每profile applied lag:帧数。

| 组 / scenario | 窗0 | 窗1 | 窗2 | 窗3 | 窗4 | 窗5 | 窗6 |
|---|---|---|---|---|---|---|---|
| A / near-only | 0:400 | 0:400 | 0:400 | 0:400 | 0:400 | 0:396 | 不适用 |
| A / silent-render | 0:400 | 0:400 | 0:400 | 0:400 | 0:400 | 0:396 | 不适用 |
| A / far-only | -1:384 / 0:16 | -1:400 | -1:400 | -1:400 | -1:400 | -1:396 | 不适用 |
| A / doubletalk-nominal | -1:384 / 0:16 | -1:392 / 0:8 | -1:180 / 0:220 | -1:168 / 0:216 / +1:8 / +2:8 | -1:56 / 0:344 | 0:396 | 不适用 |
| A / doubletalk-weak | -1:384 / 0:16 | -1:400 | -1:216 / 0:184 | -1:196 / 0:204 | -1:52 / 0:348 | 0:396 | 不适用 |
| A / path-change | -1:384 / 0:16 | -1:400 | -1:400 | -1:400 | -1:400 | -1:396 | 不适用 |
| A / render-gap | -1:384 / 0:16 | -1:400 | -1:400 | -1:380 / 0:20 | -1:400 | -1:396 | 不适用 |
| C / mandarin-clean | 0:100 | 0:100 | 0:100 | 0:100 | 0:100 | 0:28 | 不适用 |
| C / mandarin-duplex | -1:92 / 0:8 | -1:76 / 0:24 | -1:48 / 0:52 | -1:44 / 0:56 | 0:100 | 0:100 | 0:28 |

A near来源放置是样点[24000,88000)，即frame150…549的scheduled presence，
不是人工VAD或实际逐帧有声标签。nominal/weak全部48个完全落在该放置区间的固定窗
（每例窗2、3、4）中，36窗包含非零lag；合计lag0=3032、−1=1736、+1=16、+2=16。
因此“安排near存在”与“始终lag0”并不等价，但也不能据此推断near开始的那一帧引起转向。
+1/+2仅在pair-1 nominal窗3出现，每profile各8帧；完整矩阵同时保留全部0/−1窗口，
不拿这个局部值作为因果证明或候选准入条件。

下面遍历nominal及weak全部6个固定窗，汇总每profile4个pair的原near-SI-SDR增量：
min / median / max，单位dB。null窗保留4个null；其余各n=4。
这些是已有固定窗数值的展示统计，不另算波形指标、lag搜索或窗口选择。

| scenario | 窗 | rawL→HPFL | rawR→HPFR | HPFL→BF | HPFR→BF |
|---|---:|---|---|---|---|
| doubletalk-nominal | 0 | null | null | null | null |
| doubletalk-nominal | 1 | -34.595501 / -6.864663 / 9.768692 | -32.027797 / -6.360925 / 8.791836 | 0.492269 / 1.179943 / 2.215166 | -0.713618 / -0.384975 / -0.058982 |
| doubletalk-nominal | 2 | -6.951776 / -4.206615 / -0.480745 | -7.039656 / -4.228108 / -0.471490 | -0.190745 / -0.006837 / 1.171305 | -0.220587 / -0.069518 / 1.142725 |
| doubletalk-nominal | 3 | -12.169280 / -5.727374 / -1.959956 | -12.144782 / -5.886285 / -2.056960 | 0.052545 / 0.073329 / 1.184866 | -0.034784 / 0.048512 / 0.290433 |
| doubletalk-nominal | 4 | -61.343001 / -32.475267 / -16.787941 | -61.356539 / -34.203077 / -16.839029 | -0.000000 / 0.051303 / 0.380054 | -0.000038 / 0.050836 / 0.387295 |
| doubletalk-nominal | 5 | -123.078408 / -122.180849 / -120.794894 | -123.078408 / -122.180849 / -120.794894 | 0.000000 / 0.000000 / 0.000000 | 0.000000 / 0.000000 / 0.000000 |
| doubletalk-weak | 0 | null | null | null | null |
| doubletalk-weak | 1 | -31.276076 / -3.343106 / 17.060020 | -37.416940 / -5.061621 / 30.692200 | -4.025671 / -0.919760 / 0.663113 | -0.501668 / -0.209253 / 1.678820 |
| doubletalk-weak | 2 | -3.440766 / -2.140096 / -0.210313 | -3.494043 / -2.150432 / -0.194102 | -0.018855 / 0.044434 / 0.776722 | -0.044925 / -0.033109 / 0.716704 |
| doubletalk-weak | 3 | -12.129752 / -3.175390 / -1.009575 | -12.086938 / -3.239940 / -1.024175 | 0.062538 / 0.119705 / 0.903421 | -0.230407 / 0.010553 / 0.091197 |
| doubletalk-weak | 4 | -56.150461 / -27.292348 / -11.854156 | -56.164005 / -29.019222 / -11.911162 | -0.000000 / 0.052889 / 0.362241 | 0.000001 / 0.051460 / 0.373218 |
| doubletalk-weak | 5 | -117.885873 / -116.988191 / -115.602269 | -117.885873 / -116.988191 / -115.602269 | 0.000000 / 0.000000 / 0.000000 | 0.000000 / 0.000000 / 0.000000 |

末位−0.000000只是六位小数显示，原JSON保留小负数，不当零处理。
全部near-only/silent-render窗0因零参考保持null，窗1…5的HPFL→BF与HPFR→BF均精确0；
raw→HPF在这些窗仍有较大负值。far-only/path-change/render-gap所有窗、
C每profile全部13个窗位置均无准入clean near参考，四种SI-SDR增量全部null。
全部stage的原SI-SDR/null原因、RMS/peak和精确物理坐标均保存在紧凑摘要，未只保留改善窗。

同一lag类别不能单独解释质量方向。双讲表中左/右基准、nominal/weak和不同固定窗的
符号会不同；nominal窗1左侧四例全正而右侧四例全负，weak窗1两侧均有正有负。
不能把common略正的中位数概括成所有窗/声道改善，也不能把一条负值概括为BF损伤。
raw-clean的HPF比较继续受S003已识别的参考域混淆约束；本轮没有重开HPF候选、
改变参考或把大负值解释为听感退化。完整窗口并列只支持限定的描述性关联。

## 9. 原件桥、51负例与真实预算回执

本次独立文本审查逐项核对：
- 冻结锁中65个生产文件及26个helper的91个内容描述符与导出source身份一致。
- 原A/C out.pcm及metrics JSONL对当前plain/observer、旧D1七tap/control
  共720个描述符比较一致；60例all_original_bytes_equal均true。
- 7phase、201命令及report/seal/readback/negative共212个描述符与completion清单一致，
  201命令的402个stdout/stderr描述符也一致。
  这些是原报告/完成清单之间的精确绑定核对，不冒称对未读取的二进制重新计算了SHA。
- 51负例类别唯一且顺序与冻结锁一致，全部status=PASS、untouched_guard_passed=true、
  expected_reason=observed_reason；完整pristine/mutant字节数和哈希保留在摘要中。
  negative qualification的full_unchanged_readback=true，canonical_analysis_runs=1，
  DSP_executed=false、models_executed=false；没有把每个负例变成一次全量DSP重跑。
  单个定向负例最大记录0.9857577240000523秒。
- 14个日志传输负对照全部通过，与原51实际证据负例分别记录。

| phase | elapsed_seconds（六位展示） | phase列出的命令数 | 回执 |
|---|---:|---:|---|
| admission | 50.073404 | 0 | PASS / first_failure=null |
| plain-build | 4.765452 | 26 | PASS / first_failure=null |
| observer-build | 2.949923 | 4 | PASS / first_failure=null |
| run | 4.506998 | 120 | PASS / first_failure=null |
| analysis | 64.308754 | 17 | PASS / first_failure=null |
| verify | 64.612175 | 17 | PASS / first_failure=null |
| negative | 74.439135 | 17 | PASS / first_failure=null |

以上elapsed字段**只截至terminal receipt准备**。
同一个300秒硬闹钟继续覆盖receipt写入和finalizer，包括导出序列化/stdout写入；
不能把negative的74.439135秒称为包括844块交付的完整phase实测时长。
日志BEGIN为16:46:03.6135228Z，END为16:47:43.1233816Z；
这是日志时间戳跨度，不替代进程内phase总耗时。
完整END及最终job success两者同时存在才接受本次导出。

phase列出的201个命令全部PASS、returncode0、timed_out=false；
它们的timeout_seconds均30，最大实际记录2.6707415519999955秒。
原准入器内部执行仍由其自身保留回执约束，不误称D7这201条囊括全部嵌套命令。
exact-source.tar=1628160 bytes，小于原16MiB上限。
completion清单3528个既有文件加completion自身765430 bytes，
最终3529个新结果文件共405870996 bytes，小于512MiB。
这个数来自新结果清单，不是把663133601-byte合包ZIP与512MiB直接比较。
seal.json=460207 bytes / SHA256 ef404f0ebb908b695643f8ee2d5600c711fb944fcf9f645f818791342b5525e4；
completion.json SHA256 99ee24581289d6f29a18250b27c80a35140677f07e4c303ee224875136d151a4。

## 10. 收口边界

D7得到实际、可公开核对的stage/state/window诊断信息，终态继续
UPSTREAM_OBSERVATION_VALID_NO_PROMOTION、候选0。
独立日志/身份/描述符审查已完成；独立二进制tap/state/历史逐样点重算仍未完成，
不将二者合并成“完整原件独立审计PASS”。
本提交只追加结果文档和数值投影，不改DSP、driver、builder、测试、冻结合同或CI。
主分支保护、准确文档head重资格及fresh-main结果各自核验；
无自动后继变体，也不重开D3/D5/D6、AGC、NS/RES等已关闭线路。
前两次MEASUREMENT_INVALID及首次fee有效回执保持第1…5节原样。
