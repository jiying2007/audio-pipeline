# D28 固定输出过渡实验结果

日期2026-10-11；experiment=FE_DEVICE_TRANSITION_D28；本地研究里程碑，总体目标仍active。
合同见[PLAN](DEVICE_TRANSITION_D28_PLAN.zh-CN.md)及[执行前补充](DEVICE_TRANSITION_D28_AMENDMENT.zh-CN.md)。
本轮新增320点、16k下20ms线性输出过渡，冻结D27控制，不重跑AEC或选择器。
主测量有效，decision=TRANSITION_DEVELOPMENT_CANDIDATE_ONLY；promotion_allowed=false、shipping_approved=false。
这批准保存开发工程候选，不能批准无点击、真人保护、产品默认或完整前端链。

## 精确身份与执行

local HEAD572b0e34a8a8e5663397ce16e378209ba9058d4d及既有dirty保留。
冻结时live main373008e89f2ebaabc298d2c9613420b1d4811c78，summary completed/success；线上证据不批准本地D28。
D27 result/binding=c8b7cf96ee67facb504e502a2b5ec5a13f5c6f06eb84c6436ff5aad0d5513985 / c1d340bfea936ba6c01661245097eaa3621994479100803d0d201243348d1b4f。
工件根`/tmp/audio-fe-device-transition-d28-20261011`；原D0-D27源码及工件未修改。
D28 result SHA256=67b5a3f3a11b27a167e1d4ac7e59211cc7f92f9c865f4f891ae8ee49cd7175ae。
D28 binding SHA256=d34ca0be4f597297de80a16f78940146b276bdde648a03fc2dbfb5187bea2102。
主execution回执`/tmp/audio-device-d28-execution.json` SHA256=3717e11f8bb60b7be4efc41bc9f4bd61537a0cc1fc842958aa3807663e30d4eb，真实exit0。

44个主来源（32设备开发数据、12合成工程对照）各hard/fade，加新进程repeat/future，共90次真实C输出处理。
共246,924帧、39,507,840样本时刻、180条输出、79,015,680个输出Float32；绑定471项生成工件。
总528个控制事件包含两模式和额外控制，候选只使用44主来源fade的设备243、合成8个事件。
fade实际混合88,640样本时刻；全部终态remaining=0，无主事件censored。
独立计划与实现审查通过；严格C11编译及生命周期/端点/overlap/inactive/EOS自测通过。
主流程5个C拒绝执行（argc及4个完整非法参数），完整非法参数4项输出sentinel保持，按command回执分别记录，不能把拒绝计入90个有效处理。
非仓cwd的help/dry-run/4项Python数值契约测试均真实exit0，dry-run未建输出根。
预执行首次Python测试真实exit1，原因是保留字return被用作keyword；改为字符串字典键后通过。
失败记录`/tmp/audio-device-d28-precheck-failure.json`保留；阈值/时长/窗口不改，主矩阵C及AEC重跑为0。

## 冻结条件与收益代价

| 检查或指标 | hard | fade | 结论范围 |
|---|---:|---:|---|
| 设备主切换次数 | 243 | 243 | 控制决定及事件帧/方向完全保持D27 |
| 设备事件residual差分平方和合计 | 15.245871150636518 | 12.983306823542838 | 合计下降14.84050537183779%，仅冻结工程指标 |
| 主事件起点附加跳变 | 保留逐事件原值 | echo/residual均0 | 首样本原old字节，不等于无可闻点击 |
| D25原108窗known-near误差差值 | 基准 | +0至+0.12601249578147744dB | 满足<=0.5dB，合成/oracle对照 |
| D26原128窗selected residual RMS差值 | 基准 | -0.03529466576168261至+0.07466469566093892dB | 能量有增有减，不推导设备ERLE或音质 |

243个设备主事件中，55个事件的residual差分平方和增加；最大增加0.07081278739013859，case08-used0、frame1979。
这未触发冻结的合计条件拒绝，但必须保留；不能扩大为全部事件改善，不改逐事件筛选以获取更好结论。
24个无事件主来源的两条输出全量不变。hard的88条输出全量逐字节复现D27原dwell。
全部正常输出复核原mic代数，最大绝对误差2.2351741790771484e-08，小于1e-6。
全部输出核精确Float32混合，fade的两输出共用同一alpha，端点和过渡外原字节直通。
控制投影与原whole/固定窗口范围、null资格保持；remaining/alpha按各模式独立递推，评分数值变化完整披露。
repeat三文件全量同；future在冻结通知前两音频及CSV前缀同，通知后仅核混合/控制/有限。
future不核原mic代数、不评分/不参加候选，不能称真实AEC、选择器或Activity闭环证据。

private transition state的真实sizeof=16字节，不含runner输入/输出数组、原20字节selector、双AEC状态及产品总RAM。
AEC/selector调用均0，无lookahead或额外音频缓存；20ms是新bank混合完成时长，不代表瞬时全量接管。
far/dt不暂停已开始过渡；inactive/overlap生命周期仅自测覆盖，实际矩阵未覆盖中途inactive或重叠。

## 独立验证与交接

独立实际审计和六次工具拒绝均真实terminal exit0，首次成功、retry0，不导入新测量器，不执行C/AEC/selector。
独立audit核5,936次hash、90case/180trace/79,015,680个输出Float32、246,924条CSV与1,234,620控制byte。
88条hard输出全量byteeq，120,438条hard控制投影；88,640混合样本时刻、528个总事件、censored0。
独立复算476个原窗口、1,133个有效channel及295个null、236个delta及108个near delta；RMS/peak/delta与主报告误差均0。
原mic代数最大误差、合并梯度及55个事件代价均独立复核一致，候选条件全部为true。
audit脚本`/tmp/audio-device-d28-independent-audit.py` SHA256=e22d8c9d24d349caf9620ac233a00ecd941a3e2606b9eb7280d60673c830f5ef。
audit回执`/tmp/audio-device-d28-independent-audit.json` SHA256=32699766bd180e0a4e319c9b65436bf2cf197545c4e8e550c2bba99e4358716f。
negative脚本`/tmp/audio-device-d28-independent-negative.py` SHA256=c8e1adc181a3febd8489f3fbd661acd7c4b7489f98e46af78c0aa3f6ff2ae959。
negative回执`/tmp/audio-device-d28-independent-negative.json` SHA256=9e5077b428fbb79ce8f37eeb46147e020c46a53d9df3daf52a5b910b8aafa8ba。
missing/真实input分别指向旧D27/新D28/仓根六次工具拒绝均exit2；旧D27的495项和新D28的475项完整manifest起止同。
仓根只锁该工具潜在影响的measurement-invalid回执路径，未写；不扩大为锁全部既有dirty。
whole-change v1独立审查发现MINOR-1：上述原文“不变”可能误指hard/fade剩余计数和评分数值相同；实际递推与指标正确。
按审查明确两模式递推、两通道共用alpha及窗口范围/null资格，保留v1快照，无需重跑C或实际审计。
最终源码/文档/工件/失败记录及检查回执由review-snapshot-v2.json绑定，whole-change独立复审及REVIEW后复验另见[REVIEW](DEVICE_TRANSITION_D28_REVIEW.zh-CN.md)。
Provider context仍route unresolved、current为空，知识线NEEDS_REVIEW；仓内仅reviewing candidate，没有正式归档成功声明。
无commit/push/PR/merge、设备写或发布；shipping/API默认与AISpeech产品链路不变。
后续优先真实近端/双讲检测闭环、完整NS/RES/AGC/KWS链、目标资源与听感/HIL，不在本轮结果后扫过渡时长。
E001/真人独立声学/owner/Product Qualification各自未闭合；Runtime里程碑门禁不能替代这些资格。
