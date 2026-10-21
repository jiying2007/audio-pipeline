# D17 原采集与回放参考坐标：冻结诊断

日期2026-10-11；experiment=`FE_DEVICE_ALIGNMENT_D17`；kind=`diagnostic`。
goal_statement：核清原采集参考延迟、128→256点缓冲、160点适配及SDK初始延迟的样本坐标关系。
总体目标保持active；本轮不改算法、不选择参数，不批准D8/D11/D14/D16。

## 基线和问题

live main=`feb2f8ebc17a25bf248a63139ea4a219de39545d`；#657 OPEN。
summary114252893516成功；availability114323417025失败、soak skipped，不代表物理资格。
PR#712/#708是独立RealMAN，#696/#695为依赖工作。本地dirty保持，不SCM外写/设备写。
输入仍原D3计划和119文件锁、16场景development数据；不能用于blind或声学真值。
比较只读原D16 r1 replay receipt，SHA256=`2a1ed561e142a991b9c5679b35df0e44f12ab32ecc6e3e67c42e4582377f85f2`。
不重跑70臂DSP；原拒绝规则和结果不变。

只读外部产品源码：hdi独立仓HEAD=`d83d52838d6be20ff36ff8ba266969cd819bb7c4`；
app_audio_test独立仓HEAD=`c81084935638f3d3771f7c3226db0314c078d800`。
它们只是当前源码provenance，不证明采集运行的库/设备制品身份；dirty文件必须单独hash绑定。
HDI当前默认delay20点；input callback先采原ref，两次128点拼256点，零前缀delay在ref缓冲中。
实际SEVC与output callback消费同一ref指针；adapter使用raw.channel0而不是used。
待核问题：全部原数据是否确实满足此样本关系？1 ms与20点能否等价？默认40 ms意味着什么？
禁止把源码默认或输出estimated_delay_ms的整数值当物理路径真值。

## P1：测量实现和已知答案

新增研究工具仅进入tools.codex_assets，以现有intake/hash安全边界读取数据。
独立模拟HDI：初始ref队列有delay个零，每次追加128点，仅在mic累计256点时消费256点；
与直接索引raw[max(0,j-delay)]（j<delay零）逐点对照。保留未配对128点与160点截尾。
已知答案覆盖delay0/20/1600、跨128/256边界、pending128与非法长度/参数。
计算严格S16LE、完整native输出和完整160前缀hash；不归一化、HPF或插值，不写原文件。
附带±1点、固定1 ms=16点、固定40 ms=640点及used再加20点的字节差异计数，
这些是坐标/负例诊断，不是算法候选、ERLE、质量排序或真实性判定。
静音可能使错误移位也byte-equal，必须报告不可辨识，不要求每场景错误移位都不等。
工具输出stdout；实际工件保存/tmp，不新增归档接口。help/dry-run必须从非仓库cwd验证。

## P2：冻结16场景实测

原intake完整核119文件及采样/PTS/epoch、used-reference关系；独立队列模拟再核全部used样本。
原D16 receipt digest与每场景input identity及adapted mic/render字节核验。
两路raw来源、取channel0、无重采样、配对前缀与160点截尾显式报告。
每场景保留ref_delay_samples、精确微秒、1ms差值、native/replay长度和上述固定差异计数。
不计算新的lag/correlation，不从development分数优化初始delay；不使用validation/blind数据。
全部输入/源码/测量工具/测试/脚本sha起止回读；任何漂移立即stale/replan。

## P3：契约判断、独立复审和收口

从实际source确认SDK初始化ms→samples和metrics samples→整数ms、SYNC reference取数方向。
必须区分raw参考坐标、used参考坐标及传输延迟与物理声学延迟。
即使16场景重建全通过，结果仅=`ALIGNMENT_CONTRACT_DIAGNOSTIC_NO_PROMOTION`。
独立验证者复算样本关系/固定对照、核source角色和完整snapshot；中文入口/文档检查。
completion_claim仅上述诊断完成；claimant=root；verifier=device_capture_independent_review。
open_items=3；required_evidence=plan/result/review；retry_budget最多2次测量修正，失败保留。
staleness_threshold=任一input/source/receipt/tool漂移即stale；单命令timeout120秒。
stop_condition=pass/replan/blocked/abort；plan_completeness=三阶段明确；heartbeat保留实际handle。
logical_task_open=true；milestone_close仅D17；attestation通过绑定hash回读。
Provider route unresolved，知识线NEEDS_REVIEW，仅仓内reviewing candidate，未正式归档。
原产品src/API/shipping默认、AISpeech/E001/历史结论不改；目标板/HIL/声学/owner资格仍待。
