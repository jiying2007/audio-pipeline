# D5 双麦 target gate 单一结构干预：执行前合同

状态 PREREGISTRATION / NOT_RUN。新实验身份 FE-DUALMIC-TARGET-GATE-D5；基线 main e0f2be9bf6273baa46149062ec7ea700cd76387e。D4科学执行身份是083edc13，主线传输修复后的整体CI身份是e0f2be9b，两者不混用。2026-11-11核查21个开放issue/PR、43条分支及D5历史检索，未发现同题占用；本分支独占实现，独立审查另行进行，#657总任务仍开放。

## 新问题和唯一干预

D2的state_only已包含allow门控对target历史的影响，有序视图不能把它与output gate分别归因。D3零输入上调抑制对固定双讲接近零效应；D4负差值固定窗的AGC输入均数字非零，但先前状态历史仍在。本轮提出可证伪的新结构诊断：在完全固定原输入/gates下，移除target gate、保留原output gate会产生怎样的完整两臂结果？

原C的唯一数学差异为删除：
    if (!allow_gain_increase && target_gain > 1.0f) target_gain = 1.0f;
仅在隔离研究候选中删除这一个精确出现的语句，另重命名导出符号避免碰撞。生产src/default/API/版本不改。允许无数学作用的观测，但其来源/变换须独立证明，不能混入第二算法改变。

保留原profile target -20/-18 dBFS、limiter -2 dBFS、RMS能量底及epsilon、target范围0.25..8、alpha值0.25/0.015、output !allow unity cap、整帧peak cap、最后逐样本clamp。D3的精确零guard不合并。不扫描任何参数。只执行一个预注册结构对照，无结果后调参/选择下一变体预算。

它识别的是移除target gate的**总干预效应**，不是纯延迟历史贡献。当前target/alpha分支/状态可同时改变，allow=0且state<1时当帧输出亦可变；之后output/peak cap的差异是中介，不是独立贡献。原gates固定，不代表新的Activity策略或实时整链反馈结果。

此新结构不重试旧paired target/limiter、I006 15dB global cap、已耗尽error-adaptive-release身份，也不改变D41–D49 NS/RES映射。上述关闭记录和失败保持。

## 输入与资源

唯一执行输入为原D2成功 run42321833898/attempt1/source cc853616685b9faf7880e6d8f8f1a89d187d342a，artifact13553232106；474165229-byte ZIP，SHA256 a3ab7823fdcd7586c3b72eb214b5536dcfb7531fdf0b1611d49e1575a29b2c3d，3551成员、861385743解包字节；D2 report SHA f259693095d73e8cca74e15cc60f0c4e1e157cfecab32706bee35926f2fca9ea，manifest SHA e43fa150e38d65ecb43020f19a403547fce9634736735b0367512040b9c58a63。

当前API未过期（2027-02-05），这是metadata检查不是本轮下载通过。执行前复用既有严格原D2准入器，验证完整ZIP、大小/hash、成员安全、全部原D2读回及当前冻结helpers。C/header/library必须来自已准入原件和其完整封存证明，不依赖已删除旧PR的Git可达性，不重新生成baseline原件。

只使用公开仓库现有Frontend Research入口与既有GitHub Actions资源。无新数据/模型下载、私有仓库、付费服务、Codex Cloud/CLI/local或ChatGPT Work任务、物理设备/真机。仅一个新的活跃研究lane；历史D1/D3/D4按scope保持且不因D5改动重跑。不得新增平行一次性workflow。

准入/build/run/analysis/readback/negative每阶段300s，包含I/O、子进程与最终写盘；每子进程30s上限，整job20min。源archive/输出有界，所有第一失败保留，不能在看到失败或分数后悄悄放宽预算、编译flags、输入或阈值。新输出必须独占，不能覆盖旧回执。

## 连续两臂与原件基线

固定原60视图 A56+C4、35916帧、5746560样点、8原reset、原profile/gates/输入顺序。每case各臂独立持续状态，不按窗口重置；reset严格在原坐标同时应用。基线完整12-byte状态和Float32输出逐帧逐字节复现原D2，不以两份新生成结果互比。

全程allow=true的near-only/silent-render控制必须两臂state/PCM完全相同。每个reset/流开始后直到第一次target cap机会前，状态与输出也须相同；不能要求所有allow=0输出相同。输入及状态须finite；signed zero/微小非零均按实际原浮点值处理，不把数字非零当人工语音标签。

保留实际两臂before/after完整state、实际应用gain、原控制/reset/zero标识、首差位置及改变样本/帧数。同时保存raw/bounded/effective target、alpha、target/output/peak/clamp事件与计数；如这些量由同输入的Float32公式审计重建，须明确标为重建并与真实状态/输出验证，不能声称未插桩的内部值是直接测量。原D2 gain.csv是基线原件权威。候选allow=0时实际gain必须≤1，所有原峰值和末端clamp保护保持并验证。

编译使用明确固定recipe（cc,-std=c11,-O2,-ffp-contract=off,-Wall,-Wextra,-Werror，原头文件和原静态库，-lm）；当前compiler路径/hash/version/argv、HEAD/tree、完整输入/源码/构建/运行命令和输出闭包保存核验，不声称当前compiler就是旧compiler。原baseline必须字节匹配，否则FAIL不评分。

## 全量固定测量和控制

所有60共同跨度和362个原固定1秒窗口（含末尾短窗）完整报告，physical[0,N-160)、signal+160保持，不搜lag、不选窗、不改输出电平或做归一化。用原canonical scorer，基线端点/分数必须等于原D2；不得另造评分权威。

报告两臂原common/windows的SI-SDR、RMS/peak/null原因，以及canonical候选减基线差值；完整保留far-only/path-change/render-gap/中文的能量风险，即使无clean-near参考仍不忽略。32有参考视图/其余28保持原null，不能把null当零。真实英语录音与合成传播、中文单句来源及已披露回归角色不升级为独立验证。60视图/362窗不是独立样本，局部符号和中位数不替代整段贡献。

工程自测须覆盖双profile、allow0/1、多个原合法state初值、zero/signedzero/tiny nonzero/有声量级及峰值输入、NaN/Inf拒绝、相同历史无targetcap机会的两臂等价、targetcap变化下候选state与原allow=true公式对应、实际output cap/peak/clamp、reset恢复。自测不是音质证据。

实际证据负例须先验证未修改原件，再仅接受每项预期专属拒绝理由；非预期I/O/timeout/异常使负例阶段FAIL。覆盖baseline/candidate样本、完整state、target/alpha/control、错窗口/漏case、篡改或重新封存报告/源/argv/tree、额外文件目录、失败阶段回执及原输入绑定。source闭包含全部实际依赖，读回不修复原件。

## 验收与结论

实施前独立方法/具体源码审查；实际构建、执行、算术/完整输出/评分读回、负例与预算全部满足，方可称 TARGET_GATE_CONTROLLED_DIAGNOSIS_NO_PROMOTION。无效测量FAIL、零效应、不利效应各自保留，不能以score正负决定证据是否有效。第一结果和各后续source身份分开登记，完整Verify/保护merge/fresh-main单独验证。

即使有SI-SDR提升也不选择/推广默认或宣称听感/ASR/KWS改善。近端电平、远端/中文能量风险与peak行为必须一起报告；中文原CER/KWS负结果保持，没有新模型运行。未做独立数据、完整2.3.64实时链、真人听评/物理声场/硬件资源证明。本轮至多得出冻结输入/控制上这一结构的总效应；后继结构、数据或算法选择必须另冻结，不用D5自证下一轮。
