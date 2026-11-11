# D5 双麦 target gate：首次实际结果

状态：原输入/原控制上的 **TARGET_GATE_CONTROLLED_DIAGNOSIS_NO_PROMOTION**。
本页登记首次执行，不把工程成功或局部正分数写成质量 PASS、默认推广或纯延迟历史归因。
[冻结合同](DUALMIC_TARGET_GATE_D5_PLAN.zh-CN.md)、[实施说明](DUALMIC_TARGET_GATE_D5_IMPLEMENTATION.zh-CN.md)、
[研究追踪 #938](https://github.com/jiying2007/audio-pipeline/issues/938)和
[PR #939](https://github.com/jiying2007/audio-pipeline/pull/939)分别保留方法、实现与后续资格记录。

## 精确身份与证据来源

- 科学合同冻结：84a557868a341adbc8e0338034809bd040d5c992，基线 main e0f2be9bf6273baa46149062ec7ea700cd76387e。
- 首次实际执行源码：**5fae6b95a31199dbf23231066d516147001af4e7**；
  tree **89eb0013d48272a476e6074a5802422c5f5231a9**。
- [Frontend Research run 42964359158 / attempt 1](https://github.com/jiying2007/audio-pipeline/actions/runs/42964359158)，
  [D5 job 130338069626](https://github.com/jiying2007/audio-pipeline/actions/runs/42964359158/job/130338069626)：
  completed/success。API 作业时间为 2026-11-11 **05:13:56–05:16:57 UTC**（181秒，含环境/上传等，不是纯算法耗时）。
  scope 成功；D1 matrix、D3 input、D4 三个历史 job 均 skipped。
- [首次 D5 artifact 13830876548](https://github.com/jiying2007/audio-pipeline/actions/runs/42964359158/artifacts/13830876548)：
  frontend-research-dualmic-target-gate-d5-42964359158-attempt-1，
  **38,146,652 bytes**，上传日志列429文件；
  ZIP SHA-256 **2da0cdc3c40d18f1b523ed7a4ea8f9fd5ac167920719733bb99187605a3bade1**。
  上传完成与API digest/size/head绑定一致；API当时 expired=false，expires_at=2027-02-09T05:13:43Z。
- 原件仍是 [D2 run 42321833898](https://github.com/jiying2007/audio-pipeline/actions/runs/42321833898) /
  [artifact 13553232106](https://github.com/jiying2007/audio-pipeline/actions/runs/42321833898/artifacts/13553232106)，
  source cc853616685b9faf7880e6d8f8f1a89d187d342a；
  474,165,229-byte ZIP，SHA-256 a3ab7823fdcd7586c3b72eb214b5536dcfb7531fdf0b1611d49e1575a29b2c3d。
  本轮准入日志确认3551成员、861,385,743解包字节和完整原D2读回，非重新生成baseline。

本页直接核查上述公开 API、完整 job 日志及精确源码；analysis/verify 两份日志 summary
结构与数值完全相同。这里没有另行下载解包全部ZIP或另跑独立DSP/评分器，
因此不冒称作者已在CI外逐文件重算原件。CI自身的全量读回与负例结论见下文；
外部独立审查、完整 Verify、保护合并和 fresh-main 资格继续在 #938/#939 记录。
本页或后继提交不是5fae6b95的执行身份，不能借用首次run作为自己的完整门禁。

实施审查曾在 a8a79c2 指出 Ubuntu cc selector 通常为符号链接，而普通证据 descriptor
拒绝 symlink。该**执行前**阻断在5fae6b95解决：记录lookup/解析关系，实际运行并校验真实普通文件；
证据文件symlink拒绝不变。这不是一次已执行的声学失败，也未改变干预、阈值或预算。

## 完整运行、算术与控制

本轮仅删除原 target unity cap；原profile、0.25..8 target范围、0.25/0.015 alpha、
output unity cap、整帧peak限制和最终clamp均保留，不混入D3零输入guard。

- **60视图（A56+C4）、35,916帧、5,746,560样点、8个原reset、362个固定1秒窗（含短尾窗）**全部完成。
- 原D2 baseline：完整12-byte gain/target/limiter状态和Float32输出逐字节对原件通过，
  canonical baseline端点/共同跨度/原固定窗口评分与原D2一致。
- 候选：逐帧连续state方程与每个输出样点的Float32审计通过；allow=0时应用gain≤1。
- 实际state/PCM由C回放保存；raw/bounded/effective target、alpha及应用gain等为
  **公式重建并核对实际state/完整PCM**，不是未插桩内部变量的直接测量。
- 全allow=true控制保持state/PCM完全相同；near-only/silent-render控制通过。
  每次流开始/reset后，首次原输入target-cap机会之前等价，机会帧before state也相同。
- 日志summary记录 **11,204个prefix控制帧**、**17,469个target-cap机会**、
  **2,766个数字零帧**；数字零/非零不充当人工语音标签。
- 两臂before/after状态记录不同的帧为 **24,651**；输出字节不同的帧为 **6,858**。
  逐case首差与改变样点计数保留在artifact，job summary没有展开，本页不补造其总值。

| 事件 | baseline | candidate |
| --- | ---: | ---: |
| target gate cap帧 | 17469 | 0 |
| output gate cap帧 | 16939 | 17484 |
| peak cap帧 | 33 | 57 |
| 最终sample clamp改变样点 | 0 | 3 |

peak/clamp保护被保留且验证，并不代表行为没有变化。
3个末端clamp样点也不等于已经测得可听削波或主观质量下降。

## 全部共同跨度聚合

下面每个 Δ 都是 **candidate − baseline**；SI-SDR列为各case共同跨度差值的
min/median/max，而非把多个case拼成一段重算，也不是362窗的统计。
共同物理跨度固定[0,N−160)，输出跨度+160，不搜lag、不归一化。
RMS列列出该组全部case，保留原case顺序；数值只在本表四舍五入至6位小数，
完整精度与case身份见原report。null保持null，不能当零。
32个有clean-near参考的case可评分，其余28个不具备该参考。

| group / profile / scenario | cases / 可评分 / null | 共同跨度 ΔSI-SDR min / median / max（dB） | 共同跨度 ΔRMS（dB，原 case 顺序） |
| --- | --- | --- | --- |
| A / assistant / doubletalk-nominal | 4 / 4 / 0 | -1.116567 / 0.085553 / 0.409170 | 2.050458, 3.318264, 2.056680, 1.834773 |
| A / assistant / doubletalk-weak | 4 / 4 / 0 | 0.402235 / 0.975226 / 1.659038 | 2.420843, 3.701443, 2.397281, 2.677414 |
| A / assistant / far-only | 4 / 0 / 4 | null / null / null | 3.968063, 4.300908, 5.595891, 2.752191 |
| A / assistant / near-only | 4 / 4 / 0 | 0.000000 / 0.000000 / 0.000000 | 0.000000, 0.000000, 0.000000, 0.000000 |
| A / assistant / path-change | 4 / 0 / 4 | null / null / null | 6.660468, 4.343794, 5.681892, 3.132032 |
| A / assistant / render-gap | 4 / 0 / 4 | null / null / null | 4.121516, 4.499229, 5.581300, 3.303844 |
| A / assistant / silent-render | 4 / 4 / 0 | 0.000000 / 0.000000 / 0.000000 | 0.000000, 0.000000, 0.000000, 0.000000 |
| A / call / doubletalk-nominal | 4 / 4 / 0 | -2.034716 / -0.437972 / 0.095215 | 2.330921, 2.922401, 2.120201, 1.745048 |
| A / call / doubletalk-weak | 4 / 4 / 0 | -0.118337 / 0.287601 / 1.216220 | 2.529143, 3.605451, 2.209055, 2.569095 |
| A / call / far-only | 4 / 0 / 4 | null / null / null | 3.846860, 4.841876, 5.177299, 2.810618 |
| A / call / near-only | 4 / 4 / 0 | 0.000000 / 0.000000 / 0.000000 | 0.000000, 0.000000, 0.000000, 0.000000 |
| A / call / path-change | 4 / 0 / 4 | null / null / null | 6.401112, 4.689804, 5.256024, 2.668161 |
| A / call / render-gap | 4 / 0 / 4 | null / null / null | 4.029115, 4.847627, 5.149459, 3.836292 |
| A / call / silent-render | 4 / 4 / 0 | 0.000000 / 0.000000 / 0.000000 | 0.000000, 0.000000, 0.000000, 0.000000 |
| C / assistant / mandarin-clean | 1 / 0 / 1 | null / null / null | 0.000000 |
| C / assistant / mandarin-duplex | 1 / 0 / 1 | null / null / null | 0.000000 |
| C / call / mandarin-clean | 1 / 0 / 1 | null / null / null | 0.000000 |
| C / call / mandarin-duplex | 1 / 0 / 1 | null / null / null | 0.000000 |


必须同时阅读不利项和电平：

- nominal CALL 的共同跨度ΔSI-SDR中位 **−0.4379724642564269 dB**，
  最差 **−2.0347161558241504 dB**；ASSISTANT中位 **+0.08555285106245303 dB**，
  仍有最差 **−1.1165668740644268 dB**。不能称nominal普遍改善。
- weak CALL中位 **+0.28760099686836904 dB**，仍有 **−0.11833736671496276 dB**；
  ASSISTANT中位 **+0.9752255585469363 dB**，本组4个case差值均正。
  小量已披露回归样本不能支持推广、听感或识别结论。
- 所有双讲组的RMS都上升，表中逐值保留。远端相关的far-only/path-change/render-gap
  虽然SI-SDR为null，RMS仍有明显上升：CALL这些case约 **+2.668161至+6.401112 dB**，
  ASSISTANT约 **+2.752191至+6.660468 dB**。
  这些输出能量风险不能被near SI-SDR正值抵销或因null而省略。
- 中文4视图共同跨度ΔRMS均0，但没有admitted clean-near参考，SI-SDR仍全null。
  RMS差0本身不单独证明全PCM相同，也不改变原中文CER/KWS负结果；本轮未运行模型。

全部362个原固定窗口的两臂SI-SDR/RMS/peak/energy/null原因和delta，
以及每case native whole-buffer energy、逐帧target/alpha/cap审计保存在artifact的
result/report.json。job日志只打印共同跨度聚合和总计，
**本页不据此虚构窗口正负个数、窗口中位数、最差窗口或逐case peak值**。
60视图/362窗共享录音和传播来源，不是独立样本；局部符号和中位数不替代整段贡献。

## 工程控制、负例与预算

日志可直接看到D5 Python控制 **9/9**、原D3 admission控制 **4/4**、
原archive reader控制 **7/7** 成功。C工程自测作为build内必经命令成功，
其完整日志与30秒命令回执封存在result；它不是音质证据。

实际负例阶段先完整验证未修改的合格baseline，然后 **32/32** 以各自预期理由拒绝：
baseline/candidate样点、完整state、应用gain、控制/数字零、target/alpha、错窗/漏case/null、
tree/report源码身份、重封存后源/候选源、build/execution argv、额外文件/空目录/symlink、
四阶段失败回执、command失败、saved admission、原输入绑定和readback回执。
日志逐项 expected_reason=reason、rejected=true，unmodified_baseline_verified=true；
没有把I/O、timeout或其它异常作为负例成功。

固定预算保持每阶段300秒（含最终写盘检查）、每子进程最多30秒、job20分钟。
以下为GitHub Jobs API的**整秒step墙钟区间**，包含步骤开销，不替代内部phase receipt精确值：

| 阶段 | UTC开始–结束（2026-11-11） | API墙钟秒 |
| --- | --- | ---: |
| 原D2准入 | 05:14:01–05:14:39 | 38 |
| build及C工程控制 | 05:14:39–05:14:40 | 1 |
| 60例连续回放 | 05:14:40–05:14:42 | 2 |
| 全量analysis | 05:14:42–05:15:02 | 20 |
| 全量verify读回 | 05:15:02–05:15:21 | 19 |
| 32项实际负例 | 05:15:21–05:16:53 | 92 |

日志另直接给出准入receipt **37.198227046秒**、negative receipt **91.17790375799999秒**，
均为首次回执写入前采样的elapsed字段；源码在写完回执后继续检查最终deadline。
各步骤success、完整自读回与负例通过，未放宽预算或失败后更换科学规则。
build/run/analysis/verify精确phase回执、compiler identity/version/argv、源/输出闭包均留在原件，
不能把上表API秒数冒称其内部数值。

## 本轮结论与边界

在冻结原AGC输入/原gates上，移除target gate产生了非零的完整双臂差异；
weak部分SI-SDR差值为正，同时存在nominal与weak CALL负值、双讲/远端相关输出电平上升，
以及peak/clamp事件变化。原output gate仍然保留，不能据此宣称直接移除AGC、
重新选择默认结构或获得整体语音质量改善。

识别的是**移除target gate的总干预效应**。同帧target、alpha分支和state可同时变化，
之后output/peak cap也是中介；不是把D2的state_only拆成独立可相加贡献，
不是纯延迟历史贡献，也不是新的Activity策略/实时反馈结果。
尤其不能将D5 final-vs-baseline差值与D2 pre→state差值相加，宣称已经解释全部原始下降。
D5未预注册质量promotion gate，结论是有效的混合效应诊断/NO_PROMOTION，
不能在见到结果后另立标准称正式算法质量PASS或REJECT。

英语是真实录音配合合成传播；中文来自同一句录音；数据保持disclosed-regression，
没有升级独立验证。无新ASR/KWS/真人听评/完整2.3.64实时链/物理声场或SSC305资源结果。
本轮没有参数扫描或下一变体执行；promotion_allowed=false。
后继结构、数据或算法选择须另冻结，不能以D5自身分数自证下一轮。
