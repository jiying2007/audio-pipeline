# D4 双麦固定窗口与原增益轨迹关联：首次实际结果

状态：**FIXED_WINDOW_GAIN_LOCALIZATION_VALID_NO_PROMOTION**。这是真实执行完成的只读诊断，不是 NOT_RUN、算法候选或音质推广。

## 冻结身份与实际运行

- 合同/input-lock 冻结：29a04701d8d555e46c82ecde86e83175fb16d526，任务 [#935](https://github.com/jiying2007/audio-pipeline/issues/935)。
- 实施前独立静态终审通过的执行 source：70a55ae9b5028b4daf0d71426cf395a2721a89c8。
- 首次 [Frontend Research42934479553 / attempt1](https://github.com/jiying2007/audio-pipeline/actions/runs/42934479553)，[D4 job130241093491](https://github.com/jiying2007/audio-pipeline/actions/runs/42934479553/job/130241093491)，全部适用步骤success；旧D1/D3实验按scope跳过，未重跑DSP。
- 完整D4 artifact13818415226：frontend-research-dualmic-window-d4-42934479553-attempt-1；ZIP1578015 bytes；SHA256 e3fc4c583e4c1e1107e9da444ff4c493079c274bb885382a2ad43080f72a0447。
- 原D2 artifact13553232106/run42321833898 a1/source cc853616685b9faf7880e6d8f8f1a89d187d342a。474165229-byte ZIP、3551成员、861385743解包字节和完整原D2读回实际准入，用时57.478546053s/300s。不是仅核metadata。
- 13项统计/证据保护单测、原准入4项、原archive reader7项均通过。16项实际保存证据负例在未修改原件先经同一verifier成功后，全部以逐项预注册的确切理由拒绝；30.281552900s/300s。非预期异常不能冒充负例成功。
- 独立审查核对了精确head/attempt、完整job日志、上传记录与API工件metadata，结果一致；这不是第二份下载ZIP后逐成员重算审计。
- 分析和读回打印的完整聚合JSON逐字一致。每阶段300秒（包含最终写盘）、子进程30秒、整job20分钟预算未放宽。

工件保存完整逐case/逐window报告、原D1/D2报告副本、源依赖、准入/阶段/负例回执与日志。原大ZIP没有重复上传到D4工件，仍是明确的原件依赖，API有效期为2027-02-05。此工件不声称永久独立封装了所有原波形。

## 覆盖与坐标

原60视图、362个固定窗口全部保留。35916原生帧、8次原reset；共同跨度覆盖35856帧，另外60个frame0各自保留为历史上下文，没有丢弃或重新初始化算法。每个原1秒窗口（含末尾短窗）使用既有physical范围与AGC +160样点映射；原frame ID/control_frame_shift=0不变，D1其它stage保留各自offset。

32视图有准入clean-near参考，28视图没有。这里的“数字非零帧”仅表示原ns_output帧不是全部精确零，含任意小的非零值，不是人工语音标签。参考能量不足的窗口仍保留原null，不能把null算成0或改善。

## 双讲的固定窗口观察

下表均为原D2的pre_agc→state_only窗口SI-SDR差值，不是新算法与基线对照。每行4个相关视图，共24原窗口，其中20可评分、4null；符号计数不等同实质音质变化。

| Profile/场景 | 负/零/正窗口 | 最小dB | 中位dB | 最大dB | 负窗口内数字非零/零帧 |
|---|---:|---:|---:|---:|---:|
| CALL nominal双讲 | 19/0/1 | -6.367086007 | -1.090003815 | +9.257096366 | 1896/0 |
| ASSISTANT nominal双讲 | 19/0/1 | -5.156145175 | -1.120870984 | +10.161381512 | 1896/0 |
| CALL weak双讲 | 17/0/3 | -4.428051499 | -0.533167126 | +11.751471206 | 1696/0 |
| ASSISTANT weak双讲 | 17/0/3 | -4.692455489 | -0.243507802 | +12.910763797 | 1696/0 |

这些固定负差值窗内没有精确零AGC输入帧，残余定位落在数字非零输入的原动态轨迹上；但它们依然继承此前全部状态历史。这不证明某个更新系数、门控切换或噪声帧是因果根源，也不能把非零帧改称“真实语音帧”。

D2 weak双讲整个common-span的中位状态增量为正，与本表多数局部窗口为负并不矛盾：SI-SDR是非线性整段测量、全局尺度拟合及能量权重不同。不得用局部中位数替代原common分数、平均局部分数重建整段分数，或挑局部负窗否定原正结果。

## 其它控制与未评分组

- near-only每profile同样24窗/20可评分/4null，18负、2正。CALL窗口中位-1.761909840 dB，ASSISTANT -1.551646195 dB；负窗各含1654数字非零帧和142零帧。silent-render结果相同，属于相关视图，不是独立复现。
- nominal双讲state→output gate每profile20可评分窗中3负、5零、12正；weak为2负、5零、13正。部分增量在1e-6量级，不能把符号当可感知影响。
- gate→peak仅ASSISTANT nominal一个可评分窗为正（+0.122099235 dB），其余上述双讲窗口为零；peak→final全部双讲可评分窗为零，保持原D2最后clamp不改变样本的证据。
- far-only/path-change/render-gap每profile各24窗全部null；中文clean每profile6窗、duplex每profile7窗全部null。原能量/控制/时序仍保留，不据此补造近端真值、DT误判率或CER/KWS改善。
- 全部60视图和窗口都是已披露开发/回归数据；没有独立样本量、置信区间或统计显著性主张。各有序差值不当作独立因果贡献，跨组/跨列中位数不相加。

## 结论与下一步限制

本轮的新增结果是完整固定窗口与原增益/控制轨迹的可复读关联。结合D3对双讲几乎不变的实际干预结果，后继研究可重点提出非零输入期间动态行为的可证伪结构假设；D4本身没有执行该干预，也不批准重新扫描既有AGC target、limiter、global cap、adaptive release或D41–D49参数。

不修改波形、生产DSP/default/API或评分权威；不新增lag搜索、masked score、投影拆分、VAD标签、模型运行、真人听评或物理设备证据。原中文负结果不改，无质量推广。独立结果复核、精确PR完整Verify、保护合并和fresh-main资格另按各自真实身份登记，不能借首次研究success声称整体CI通过。
