# D6 双麦帧内线性增益过渡：首次实际结果

状态：**measurement_valid=true / NO_ADVANCE / promotion_allowed=false**。
本候选没有通过执行前冻结的发展屏障，按原规则关闭，不进入独立确认或默认推广。
工程运行成功不等于质量通过；本页只结论于这一固定160样点输出域候选及冻结输入，
不宣称所有增益平滑或所有ramp方案无效。

[冻结合同](DUALMIC_GAIN_RAMP_D6_PLAN.zh-CN.md)、
[完整输入锁](dualmic-gain-ramp-d6-input-lock.json)、
[实施说明](DUALMIC_GAIN_RAMP_D6_IMPLEMENTATION.zh-CN.md)、
[研究追踪#942](https://github.com/jiying2007/audio-pipeline/issues/942)与
[PR#943](https://github.com/jiying2007/audio-pipeline/pull/943)分别保存方法、实现和后继资格。

## 精确身份和证据口径

- 冻结提交 caaed2efa09243b99064c8ee793d3c27591ab6df；
  基线main 6c7752800838f2c7fd707593c658f250a071e98c。
- 首次实际执行源码 **087bd38318f37261f75482596d5bdd593352d331**，
  tree **de25c2ce66a40683cb20217e974fd19f638987e2**。
- [Frontend Research run43008230556 / attempt1](https://github.com/jiying2007/audio-pipeline/actions/runs/43008230556)
  和[D6 job130481063774](https://github.com/jiying2007/audio-pipeline/actions/runs/43008230556/job/130481063774)
  为completed/success。Jobs API时间 **2026-11-11 10:59:58–11:04:10 UTC**，
  共252秒，包括环境、上传等开销，不是算法净耗时。
  scope成功；历史D1 matrix、D3 input、D4、D5四个job均skipped。
- [首次artifact13848394534](https://github.com/jiying2007/audio-pipeline/actions/runs/43008230556/artifacts/13848394534)，
  名称 frontend-research-dualmic-gain-ramp-d6-43008230556-attempt-1；
  **49,319,382 bytes**，上传日志列491文件；
  ZIP SHA256 **fb6113dcccfbd9958d3caea820ce8d77afc3e09c160917f88de904fa7d5dac9c**。
  API digest/size/head与上传日志一致；核查时expired=false，
  expires_at=2027-02-09T10:59:49Z。
- 原件仍为[D2 run42321833898](https://github.com/jiying2007/audio-pipeline/actions/runs/42321833898) /
  [artifact13553232106](https://github.com/jiying2007/audio-pipeline/actions/runs/42321833898/artifacts/13553232106)，
  source cc853616685b9faf7880e6d8f8f1a89d187d342a；
  474165229-byte ZIP，SHA256 a3ab7823fdcd7586c3b72eb214b5536dcfb7531fdf0b1611d49e1575a29b2c3d。
  本轮准入确认3551成员、861385743解包字节和完整原D2读回，不重新生成原baseline。

本页直接读取公开API、完整job日志和精确源码。
analysis/verify两份完整summary的结构与数值相同。
CI确实执行了全量实际字节/算术/canonical读回和40项实际证据负例；
本页没有在CI外另行下载解包完整ZIP或重新运行DSP/评分器，
不把日志/API复核冒称为CI外独立逐文件重算。
后继文档提交不是087bd383的执行身份，仍须取得自己的exact-head工程门禁；
受保护合并和fresh-main资格继续在#942/#943记录。

实施前01e95的独立审查要求补全原准入receipt的experiment、成员数、解包字节、
promotion_allowed和elapsed_scope核验及篡改/缺失测试，087bd383已完成。
这是首次执行前的源码加固，不是已发生的声学或CI失败，也未改变干预/预算/屏障。
原D5的remaining helper本来已硬限30秒，本轮没有重写它或修复一个虚构的历史超时缺陷。

## 完整运行和实际控制

唯一候选在输出域进行160样点weight-first Float32线性过渡，
原target/alpha/state/gate参数和两级cap/sample clamp保持，D3/D5不合并。
不增加未来帧或额外帧延迟；原整帧energy/peak依赖仍在，不声称逐样点零前视。

- **60视图（A56+C4）、35916帧、5746560样点、8个原reset、362原固定窗口**全部完成。
- baseline完整12-byte before/after状态及PCM逐字节复现原D2；
  candidate的同一12-byte状态每帧与baseline相同，**changed_state_frames=0**。
- 全部5746560个实际乘法系数直接由C保存，独立Python Float32重建及全部实际PCM对照通过。
  S/G、P、初始化、端点G、首帧/reset及常数G中性均通过。
  target/alpha/cap派生值明确为公式重建，不能冒称全部均是直接内部插桩。
- **13172帧输出PCM改变**；首差帧/样点和改变样点数保存在逐case report，
  job summary没有给出改变样点总数，本页不补造。
- **17036个中性帧**、**16975个上升ramp帧**、**1905个下降ramp帧**；
  三者合计35916。**68个warm-start帧=60个流开始+8个原reset**。
  **2766个数字零帧**保持原数字定义，不当作人工静音/语音标签。
- 原baseline target unity cap **17469帧**、output unity cap **16939帧**、
  原整帧peak cap **33帧**。
  candidate在插值后逐系数重复unity/peak cap的额外改变次数均为**0**；
  这两个计数不包含S/G形成时已有的cap，不代表取消保护，
  也不能与baseline的“帧数”直接作同口径比较。
- 最终sample clamp改变样点数 **baseline0 / candidate0**；
  每个case不增条件通过。没有把未发生的clamp称为硬削波或可听伪影。

## 执行前屏障的实际判定

所有比较采用冻结canonical全精度值，没有epsilon、四舍五入阈值或事后筛选。

| 冻结谓词 | 实际 |
| --- | --- |
| 全32个有参考共同跨度ΔSI-SDR>=0 | false；**全部32例都为负** |
| 每个原可评分固定窗ΔSI-SDR>=0 | false；至少存在负窗，日志未展开其个数 |
| 16个nominal/weak双讲中至少一个共同跨度ΔSI-SDR>0 | false；**0/16** |
| 全24个far-only/path-change/render-gap视图，common/全部原窗/native的原RMS指标与linear peak均不增 | false |
| 全60例最终sample clamp计数分别不增 | true |

因此是**有效测量的NO_ADVANCE**，不是MEASUREMENT_INVALID，也不是默认或质量PASS。
24个远端相关视图的屏障为多span、多指标合取；日志未逐项展开所有违例，
不能推断每个case都恶化、只由某一种指标失败，或虚构peak最差值。
共同跨度的far-only/render-gap原RMS指标已有部分正增量，见完整表。
原RMS指标是20log10(max(raw_RMS,1e-12))；本页不将floor下被隐藏的变化解释成零raw energy变化。

## 全部18组共同跨度聚合

以下Δ均为candidate−baseline。
SI-SDR列是各组case共同跨度差值的min/median/max，不是把case拼接后重算，
也不是窗口聚合。RMS逐值保留原case顺序。
数值保持job JSON中的全精度表示，不使用表格舍入结果进行判定。
32个可评分case/28个null均保留；null不是零。

| group / profile / scenario | cases / scored / null | 共同跨度 ΔSI-SDR min / median / max（dB） | ΔRMS（dB，原case顺序） |
| --- | --- | --- | --- |
| A / assistant / doubletalk-nominal | 4 / 4 / 0 | -0.19407929453544082 / -0.11416118424324057 / -0.044565864995018245 | 0.20952640691186986, 0.1092239602920202, 0.09971265247155614, 0.07275328201012954 |
| A / assistant / doubletalk-weak | 4 / 4 / 0 | -0.19973741022501645 / -0.045988706630539555 / -0.037853753581306604 | 0.13276663301016356, 0.031533303710382654, 0.03290901582374062, 0.01561170400694678 |
| A / assistant / far-only | 4 / 0 / 4 | null / null / null | -0.034946377970186404, -0.007931366402914364, -0.029120559377531663, 0.12874854708015704 |
| A / assistant / near-only | 4 / 4 / 0 | -0.2167465450352406 / -0.12709881938358336 / -0.11552647726901011 | 0.23604551833195941, 0.19049962483611083, 0.17940807373609857, 0.1819816963968357 |
| A / assistant / path-change | 4 / 0 / 4 | null / null / null | -0.04955625999823354, -0.007953132362509052, -0.030011059518244565, -0.01495264028764609 |
| A / assistant / render-gap | 4 / 0 / 4 | null / null / null | -0.03802366224996234, -0.009409339077350864, -0.029081083216063064, 0.25056389564445425 |
| A / assistant / silent-render | 4 / 4 / 0 | -0.2167465450352406 / -0.12709881938358336 / -0.11552647726901011 | 0.23604551833195941, 0.19049962483611083, 0.17940807373609857, 0.1819816963968357 |
| A / call / doubletalk-nominal | 4 / 4 / 0 | -0.23742681223768702 / -0.1206778754287689 / -0.04408239477374298 | 0.27178839691710976, 0.1397035348793736, 0.12387270805548667, 0.09687513882466092 |
| A / call / doubletalk-weak | 4 / 4 / 0 | -0.25307115867927266 / -0.0485577613915229 / -0.03913207143621089 | 0.18717308730311188, 0.05896151791398907, 0.05712806301559681, 0.03139601944215187 |
| A / call / far-only | 4 / 0 / 4 | null / null / null | -0.028016204144506673, -0.0070365165701673504, -0.020631615514872692, 0.25239072590661493 |
| A / call / near-only | 4 / 4 / 0 | -0.28709241763007753 / -0.16655852039136354 / -0.14144507706853915 | 0.303122239301274, 0.241654570919124, 0.2401050400614686, 0.21595958805795945 |
| A / call / path-change | 4 / 0 / 4 | null / null / null | -0.04276177766686118, -0.006559029209839196, -0.021245822989655494, -0.011665291184094428 |
| A / call / render-gap | 4 / 0 / 4 | null / null / null | -0.030493347102911628, -0.007628073094572585, -0.020440591963975407, 0.348349536664891 |
| A / call / silent-render | 4 / 4 / 0 | -0.28709241763007753 / -0.16655852039136354 / -0.14144507706853915 | 0.303122239301274, 0.241654570919124, 0.2401050400614686, 0.21595958805795945 |
| C / assistant / mandarin-clean | 1 / 0 / 1 | null / null / null | 0.22445195904687765 |
| C / assistant / mandarin-duplex | 1 / 0 / 1 | null / null / null | 0 |
| C / call / mandarin-clean | 1 / 0 / 1 | null / null / null | 0.27844033227131604 |
| C / call / mandarin-duplex | 1 / 0 / 1 | null / null / null | 0 |

所有nominal/weak双讲共同跨度SI-SDR均下降，而RMS均上升。
near-only/silent-render也均下降，且此候选本来就适用于allow=true，
不能套用D5的这些场景全PCM中性控制。
中文clean的RMS增量为ASSISTANT 0.22445195904687765dB、
CALL 0.27844033227131604dB；
中文duplex的共同跨度ΔRMS均0，但没有clean-near参考，
仍全部null，单凭RMS差0不证明整PCM逐字节相同，也不改写原中文CER/KWS负结果。

全部362原固定窗的两臂SI-SDR、RMS/peak/null原因和delta、
逐case native_whole_buffer_energy、逐帧轨迹/实际系数及完整screen详细谓词，
均保存在首次artifact的result/report.json及case文件。
job日志未打印全部窗口记录，本页不虚构窗口正负个数、窗口中位数、
最差窗口、逐case峰值或其它未展开细节。
60视图/362窗共享录音及合成传播来源，不是独立统计样本。

## 工程控制、40项负例与预算

日志显示D6 Python控制 **13/13**、原D3 admission控制 **4/4**、
原archive reader控制 **7/7**成功。
C工程自测是build中的必经成功命令，其完整stdout与命令回执封存在result；
不把它当作声学质量证据。

实际负例先完整验证未修改的合格原件，再完成 **40/40**，
每项rejected=true且reason=expected_reason，unmodified_baseline_verified=true。
包括baseline/candidate PCM、完整state、真实系数/端点、P/initialized/S/G、
controls/zero、target/alpha、错窗/漏case/null、screen结论/谓词、
source/tree/argv、重封存source/header、额外文件/空目录/symlink、
四阶段失败、command失败、saved admission、输入绑定和readback。
没有将非预期I/O/timeout/异常作为负例成功。

预算保持每阶段300秒（含最终写盘）、每子进程最多30秒、job20分钟。
以下是Jobs API的**整秒step墙钟**，包含步骤开销，不冒充内部phase精确时长：

| 阶段 | UTC开始–结束（2026-11-11） | API整秒墙钟 |
| --- | --- | --- |
| 原D2准入 | 11:00:03–11:00:41 | 38s |
| build与C控制 | 11:00:41–11:00:43 | 2s |
| 60例连续两臂run | 11:00:43–11:00:44 | 1s |
| analysis | 11:00:44–11:01:06 | 22s |
| 完整verify读回 | 11:01:06–11:01:27 | 21s |
| 40项实际负例 | 11:01:27–11:04:05 | 158s |

日志直接给出的准入receipt elapsed_seconds为 **37.380317789**，
negative receipt为 **157.56969379000003**。
这两个elapsed字段均在首次回执写入前采样，源码在最终写盘后再检查deadline。
其余phase精确回执、compiler identity/hash/version/argv和完整源/输出闭包保存在原件。
全部阶段成功，首次负例阶段未触及300秒，未通过放宽预算消除失败。

## 本候选结论与后继边界

**FE-DUALMIC-GAIN-RAMP-D6按预注册规则NO_ADVANCE，候选关闭。**
原state完全不变仍出现这些波形及分数差异，限定说明这个输出域过渡
没有满足本轮冻结双讲质量和全量退化屏障。
它不证明原block gain就是主要可听损伤原因，不推出所有平滑结构都失败，
也不能把D6差值与D2有序视图差值相加作为独立因果贡献。

不执行第二变体、不改变ramp长度/形状/参数、不事后重新定义质量门槛。
保留现有更简单生产实现；本研究源码和负结果作为可复现记录，
不是新默认。任何不同结构或独立数据工作都需要自己的新假设及执行前合同，
不能借D6工程绿灯自证晋升。

无新ASR/KWS、真人听评、真实WAN、完整Activity反馈整链、真实双麦声场、
SSC305物理资源或设备结果。公开回归数据角色、原中文负结果、
D3/D5历史记录和关闭的参数研究均保持。最终PR/主线源码资格单独核对。
