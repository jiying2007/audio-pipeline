# D19 同状态阶段诊断：冻结测量合同

日期2026-10-11；experiment=FE_DEVICE_STAGES_D19；kind=diagnostic。
goal_statement：定位D18两固定参考坐标的输出差异首次出现在哪个实际处理阶段，记录同状态能量传递。
不改算法/参数、不选择候选、不将阶段能量变化称人声/残回真值。总体目标active。

## 基线与范围

唯一DSP基线为冻结D18测量source与32份输出，result SHA369c8c484b107c549449a93d92bfa82e464f0163fefce55377d2096b1caa47be、
binding SHAab41fbe3d970b11ff4a001cfdcf4bd2c2f1d6a4032c36a1da0511526943c2da2。
原119文件锁16 development场景，fixed1/raw16与used0/raw20两臂，跟踪/漂移关闭，参数保持D18。
live main=1be9b89af778783bdbe695c72d048b3d77eee948（#712 RealMAN来源验证）；#657仍OPEN。
不把新主线或旧CI回执当本轮准确head资格；原D16仍REJECTED，不称shipping基线。

## P1：即时阶段观测

从D18 source复制新的/tmp副本，仅将AEC backend、NS、AGC controlled、独立RES四个函数定义改名d19_real。
原函数体/公共头不改，runner同名observer显式转发，不用unity --wrap。
保留D18 get_reference观测；源码除了上述定义名不许变化，generated header逐字节保持。
AEC调用前抓实际mono输入，调用后抓echo estimate与residual；NS返回抓output；AGC返回抓output。
所有观测在对应缓冲复用之前完成；不改state/input/output/event/返回值，短写/有限性/顺序异常立即失败。
NS输入与AEC residual、NS echo与AEC echo、AGC输入与NS输出必须逐float相等；
AEC mono≈echo+residual绝对误差≤1e-6（float舍入检查，不是真实源分量分离）。
每帧AEC→NS→AGC各一次、160点，reference仍按D18全float验证；observer记录实际far/double-talk、
enable_frequency_res、active flag、residual gain、AGC allow_gain_increase及state gain before/after。
完整CALL/full当前走NS内频域RES，独立时域RES预期0调用；若实际调用则测量无效/replan，不伪造阶段输出。
严格C11构建、两率不扩展，仅本轮16k/160点；D18 known answers仍通过。

## P2：完整32回放与固定测量

16场景×2臂=32完整执行，每次PCM/原JSONL/reference与D18对应工件逐字节相同，证明本范围观测中立。
5条阶段Float32LE/臂长度恰与原replay前缀相同；全有限、对应字段每帧完整，零参考控制全阶段相同。
startup欠载仍fixed1=1/used0=0，原counter规则保留。不复跑算法搜索/70臂，不改变默认/API。
窗口采用原device_replay.window的PTS与固定4–6/10–12/19–21s；AEC input/echo/residual偏移0，
NS/frequencyRES与AGC偏移160（当前NS 10ms pipeline延迟），不得逐例动态对齐。
保留whole和全部固定窗口RMS、peak，以及used0-fixed1同阶段差值、AGC前后同窗能量变化。
float RMS定义20log10(max(sqrt(mean(x²)),1e-12))，用于工程能量诊断而非新增音质评估权威；
不将float与S16量化输出的低电平舍入差当回归。不能把各stage独立重跑再相加作贡献归因。
没有独立RES-only结果；NS/frequencyRES联合阶段不能归因给某一个内部增益。

## P3：独立审查与收口

结果固定SAME_STATE_STAGE_DIAGNOSTIC_NO_PROMOTION；身份/等价/测量失败则MEASUREMENT_INVALID并保留。
source/库/runner/工具/输入/配置/旧工件起止hash绑定，独立核阶段时点、字段、能量复算及whole-change文档。
completion_claim仅32次完整同状态阶段诊断；claimant=root；verifier=device_capture_independent_review；open_items=3。
retry_budget最多2次测量修正，失败不洗绿；staleness_threshold任何锁漂移即stale/replan。
每命令timeout120、build300；heartbeat保存实际handle；三阶段明确，attestation起止回读。
stop_condition=pass/replan/blocked/abort；logical_task_open=true；milestone_close仅D19。
primary=adk-planning-execution-loop；Provider unresolved知识线NEEDS_REVIEW，仅仓内reviewing candidate。
无SCM外写/设备写/产品src改变；AISpeech/E001、历史reject和shipping资格不变。
真人标签、clean target、ASR/KWS、物理路径、目标板资源/HIL和owner仍待独立真实证据。
