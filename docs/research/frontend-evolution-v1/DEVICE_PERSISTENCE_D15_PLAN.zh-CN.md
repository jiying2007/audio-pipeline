# D15 延后事件与持续路径支持：冻结独立诊断

日期：2026-10-11；experiment=`FE_DEVICE_PERSISTENCE_D15`；kind=`diagnostic`。
goal_statement：解释D14收紧确认容差后重新完成确认的候选簇，并测量同一时点更长上下文的支持。
本轮只改测量，不改算法、不选择候选，不以新增测量批准D11/D14；两者原REJECTED保留。
总目标“全面推进优化迭代”保持active。

## 基线、问题与数据角色

精确D11/D14 source及原replay作为被拒绝的研究对象。
D11库=`ead75733d45f5b78c086bed9122082d410847eea0ed6b21f8bafab102a1cb0ac`；
D14库=`736815d2050d49f5a1ebcf254abd140b2c39edfff2f5ae43d27b06c0282a95f3`。
D14 final-binding=`afdf4a34f18cbe049add927436c3a2c189dc613b9be3a457c4396970f2237825`。
原产品src、D11/D14隔离原副本、D12 fixture与旧结果不改。
来源是原tests/audio已经查看的development数据，不是blind、独立声学或物理delay真值。
新测量只解释算法状态和相关支持，不能宣布现场40→1 ms是真实恢复或错误物理对齐。

已核源码：每100 ms更新一次；大跳须短窗10 ms和history40 ms过原0.0324门限，
随后首候选锚±tolerance连续三次完成确认，实际写入首候选锚。
40 ms窗口之间有60 ms不覆盖；“三次确认”本身不能证明200 ms整段路径持续成立。
这是测量动机，不预判长窗分数或新策略有效。

冻结选集：case07 default及sync-default-control、case16 default、case15 tracked1，
两版本×4臂×observe/no-observe=16次完整回放。
包含两个拒绝场景、同配置对照和无目标172 ms跳变的控制，不扩大到新场景做参数选择。

## P1：计划审查、身份与测量实现

独立计划审查后从精确D11/D14分别复制新/tmp副本。
为避免D12已证实无效的unity --wrap，只将实际ap_sync_track_delay符号重命名为d15_real，
由同名observer显式转发；算法函数体不改。每个锁定source file逐hash核验，只有该精确替换允许。
generated headers与原replay byte-exact；新的测量库身份不能冒充原库。
新fixture复用D12的实际HPF/BF mono探针和逐帧counter验证，另明确两版本confirm tolerance。
保存原state不变断言；实际更新调用一次；测量计算不写原state/event/输入。

仅observer侧新增800点、4倍下采样的200 ms mic history；不新增产品state，不作为资源候选。
计算40/100/200 ms同公式归一化平方相关，分别在refined、旧delay、有效首候选锚上观测。
长窗沿原render ring、真实post-HPF/BF mono计算；100/200 ms的total/容量/配对不足输出-1并明确not_available。
40 ms shadow保留原函数不足条件返回0的语义，并与原history_score在每个eligible epoch精确一致；
所有有效score有限且在浮点容差内[0,1]。
保存actual post-HPF/BF stride4 mono Float32LE、actual render Float32LE与absolute total映射，
用于独立复算100/200 ms索引与分数；有效锚标记confirm_before>0，另列restart后新anchor。
定向自测覆盖800点回绕、完整历史边界、配对失败和reset，以独立线性数组相关对照。
冻结窗口不是参数搜索；0.0324仅作原门限诊断标记，不能给新100/200 ms策略验收授权。
严格C11编译、无效参数exit2；任一身份/测量等价失败停止并保留，不读score后改测量规则求绿。

## P2：原数据完整等价回放

16次完整执行，输入/config逐hash匹配原receipt。
observe和no-observe输出PCM/JSONL与各自原D11/D14 replay逐字节相同，不只比较终态。
全部帧集合、原delay/error/jumps/reset/slips逐帧一致；observe eligible候选对实际error匹配。
根据每次10 ms/100 ms时序实际重判confirm状态，包括超过容差重启、third清零、history/short拒绝清零。
case07 default/control两种模式的trace、PCM/metrics均一致。
no-observe仍写逐帧状态，但不进行分数计算；trace不能被称为含候选搜索证据。

## P3：固定分析，不做算法晋升

完整保留所有eligible epoch，不只取事件前三条。
分别重建D11/D14所有实际route_jump的最后确认簇，记录锚/refined序列、距离、确认计数、
short/history40门限及40/100/200 ms旧路径/新路径/锚支持。
重点核D14第727/1247帧，D11第457/617帧；完整选集其他jump也披露，control零jump保留。
事件窗口固定为jump前40帧到后10帧；无jump臂报告整段统计，不发明事件。
比较D14在原D11跳变epoch的状态重启和后续新簇；漂移导致旧delay不同必须披露，不能同态反事实。
scores支持/不支持只按冻结窗口描述，无真值不能用更高分定义正确路径。
结果固定=`ENGINEERING_PERSISTENCE_DIAGNOSTIC_NO_PROMOTION`；失败则measurement-invalid/early-stop。

## P4：独立复审与阶段收口

冻结source/库/头/input/config、原文命令exit、全部trace/输出、result/binding、脚本和文档snapshot。
独立核完整事件计数/序列，40 msshadow等价与选择事件长窗计算，中文入口/文档检查。
completion_claim=上述独立诊断完成；未完成物理、声学、产品或总体优化。
claimant=root；verifier=device_capture_independent_review；open_items=4；attestation必须hash回读。
retry_budget=测量实现最多两次修正；staleness_threshold=源/库/input/config任一漂移即stale/replan。
单命令timeout120秒，build允许300秒；每阶段heartbeat并保持实际handle，观测超时不重启。
stop_condition=pass/replan/blocked/abort；plan_completeness=四阶段明确；不commit/push/设备写。
tmp保存完整原始测量证据；仓内仅脱敏研究结论和fixture，Provider路由仍unresolved，未正式归档。

本轮live main=`feb2f8ebc17a25bf248a63139ea4a219de39545d`，summary114252893516、Verify38063778210、
Release38065749535成功；HIL38089691586失败保持可见，未宣称设备资格。
Verify研究artifact metadata实际未过期；仅查metadata，不借其批准本测量。
#657 OPEN；新PR#712与#708均为独立RealMAN工作，#695/#696为Dependabot。
AISpeech产品链路、E001、shipping default/API与历史I025–I040均不改。
