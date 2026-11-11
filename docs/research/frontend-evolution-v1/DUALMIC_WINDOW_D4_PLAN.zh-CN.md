# D4 双麦固定窗口增益定位：执行前合同

状态 PREREGISTRATION / NOT_RUN。本合同在 D4 新表格或结果产生前冻结。基线 main dec7bf7c94f0e2a99d415eb497357e2ea44a5dcc，已完成 #933 自身 push Verify42927067248 和 Research42927067077。执行负责人为本研究分支；#925 ALSA、旧 FE09/FE03 来源任务不占用此问题。2026-11-11 检查开放 issue/PR 与分支，未发现同题 D4；总任务 #657 保持开放。

## 具体问题与边界

D2 已将部分英文固定双讲 SI-SDR 下降定位到原时变状态增益视图，但其它例可为正；D3 抑制精确零输入时上调对双讲仅约1e-8到1e-6 dB变化，不能解释原显著下降。本轮只把既有完整固定窗口测量与同源原始增益/控制轨迹关联，回答负差值具体出现在哪些预先固定窗口、这些窗口的数字非零输入和状态变化如何分布。不是新因果干预、算法候选或声学通过门槛。数字非零不等于人类语音，数字零不等于声学静音。

不新增 DSP/模型执行、波形修改、global/window normalization、masked score、VAD标签、lag搜索或窗口选择。不新增独立评分器。投影残差拆分明确不进入本轮。AGC target/limiter/global cap/adaptive release 及 D41–D49 已关闭扫描保持关闭。生产源码/default/API/版本不改变。

## 原件和资源准入

唯一输入是原 D2 成功 run42321833898/attempt1/source cc853616685b9faf7880e6d8f8f1a89d187d342a 的 artifact13553232106。ZIP474165229 bytes，SHA256 a3ab7823fdcd7586c3b72eb214b5536dcfb7531fdf0b1611d49e1575a29b2c3d，3551成员/861385743解包字节。D2 report SHA f259693095d73e8cca74e15cc60f0c4e1e157cfecab32706bee35926f2fca9ea；manifest SHA e43fa150e38d65ecb43020f19a403547fce9634736735b0367512040b9c58a63。2026-11-11 API仍未过期，expires2027-02-05；最近 D3 main 已真实完整取得并读回，不把metadata当下载成功。

复用字节不变的 D3 原D2准入器（其D3标签只是已存在输入入口），保留REST run/attempt/source、完整ZIP和安全解包、原D2全读回。D4另绑定本合同、input-lock、当前执行HEAD/tree/工具文件及全部输出目录集合。无新外部数据、权重、收费服务、私有仓库、Codex/ChatGPT Work任务或物理设备操作。仅既有公开仓库 Actions / Frontend Research 入口，不创建平行一次性workflow。

每个准入/分析/读回/负例阶段300秒，包含最终写盘；整job20分钟，子进程最多30秒。原ZIP大小、解包量和成员上限不扩大；不因失败后放宽预算。输出不重复上传完整474MB原ZIP，保留原件锁、准入回执、来源字节、原报告副本及新的完整结果/负例/日志。原件依赖及到期明确记录，不称永久独立归档。

## 全量固定测量

使用原60视图 A56+C4，35916原生帧、5746560样点、8次原reset；32视图有准入clean-near参考，其余28保持原null语义。它们不是60名独立说话者或独立试验。

所有60公共跨度与362个原1秒窗口完整保留，含末尾不足1秒窗口，不挑最差或事后剔除。公共物理跨度[0,N-160)，窗口从0起每16000样点划分；AGC输入为 ns_output.f32le，输出/增益对应样点偏移+160。物理[a,b)关联原 gain.csv 行[(a+160)/160,(b+160)/160)，原frame ID不变，control_frame_shift=0。这是坐标关联，不是把控制移一帧；原reset原生坐标与其影响的aligned-output窗口分别保留。frame0单列为连续历史上下文，不重置原算法。

D1各stage仍保留其原offset，只有AGC输入/增益关联使用+160，不统一平移其它stage。

逐case保留原D1全部stage测量及原D2全部五视图/有序差值；D2 pre/final必须精确等于D1 NS/AGC端点。逐window保留原分数/null reason/RMS/peak等原字段，新增只读gain摘要：
- 原frame范围、物理/信号样点范围，zero/nonzero帧数；
- 分zero/nonzero的同一行Float32 state before→after上升/下降/相等计数，不用跨行差把reset当下降；
- 原allow=0/1、target cap/output gate/peak cap、reset数与原frame IDs；
- before/after/applied gain的首/尾/min/max和每帧绝对更新量总和；
- 输入峰值/RMS范围，全部finite检查；zero须全部样点finite且exact==0（含signed zero），并与原gain.csv input_peak==0一致；不使用带能量底的input_rms或阈值判零。

保留全原生帧摘要及frame0，窗口覆盖行1..frames-1，不伪称公共窗包含frame0。全量case顺序及每窗顺序固定。group/profile/scenario描述性聚合同时报告全部窗/可评分窗/null窗分母，以及原有分数适用窗数/负零正变化数及min/median/max、negative窗口的zero/nonzero组成；负号仅描述符号，不等同实质恶化/改善；不以窗均分替代common-span分数；null不当0；不做置信区间、显著性、独立样本计数或跨列中位数贡献相加。分数不按nonzero掩码重算。

## 有效性/失败规则

只有完整原件准入、冻结输入与当前源身份、60case/362window精确覆盖、原分数复制/端点一致、增益坐标/原始行/输入字节逐项复核、保存结果全量重算读回和实际证据篡改负例全部成立，才称 FIXED_WINDOW_GAIN_LOCALIZATION_VALID_NO_PROMOTION。任何缺失、非finite、错位、改源/报告/原件、增减case/window/成员或预算超限均FAIL，并保留首次失败；NOT_RUN不是结果。

负例必须在合格原件的临时副本执行，覆盖window边界错一帧、删除/重复/交换窗口、gain计数变化（含跨reset误计）、原评分/null改变、源revision/tree、增加成员、原输入receipt/report篡改；不得修复/覆盖原证据。实施须独立静态审查后再启用实际Actions；首真实结果须独立日志/产物身份复核，完整Verify与保护合并、新main资格分开记录。

## 解释与停止

有效结果只允许定位既有数据/算法轨迹上的描述性关联，不确定数字非零部分就是语音、不证明增益变化造成听感/ASR退化，也不把D3的near-only单指标上升推广。若未找到局部负窗/关系不统一，应如实保留；不得转成新参数搜索。后继结构干预必须另冻结，中文仍无clean-near阶段真值、旧CER/KWS负结果不改，无独立验证/物理声场/MOS结论。
