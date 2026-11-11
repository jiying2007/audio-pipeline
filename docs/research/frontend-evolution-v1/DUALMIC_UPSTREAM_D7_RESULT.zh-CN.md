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
