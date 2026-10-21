# D28 独立审查与复验记录

日期2026-10-11；experiment=FE_DEVICE_TRANSITION_D28；claimant=root；verifier=device_capture_independent_review。
primary=adk-planning-execution-loop；supporting=adk-verification-before-completion。
结论：Spec PASS、Quality PASS；Reviewer Independence=independent；未闭合finding=0。
覆盖冻结合同、实施、实际工件、路径拒绝与whole-change证据；仅开发工程候选。
promotion_allowed=false、shipping_approved=false；总体native goal仍active。

## 审查范围与历史

执行前PLAN b0e8712b1da8a21ca24f943c7fc99b8f61aca719f70cbe0b1855b9b8701ead29。
QUESTION-1要求明确工程边界指标通道；执行前AMEND f0fb7792abeedf93deee591df1bceb4f3979fc8fad82c0b9326ff27d6bce7940闭合。
selected residual用于合计梯度，echo只诊断；起点injection两输出分别逐事件核验；EOS未完成主事件拒绝。
随后独立计划与实现审查均PASS，320点/两通道共alpha/端点字节/overlap原子/inactive/EOS/原窗口/代数/future边界符合冻结合同。

首次Python预检查exit1，保留字keyword语法错误；仅改为字符串字典键，4项契约测试随后通过。
失败记录SHA256=26a07f59ec4dd668a6268d61ccf46e3d47ba4085609b7b25e4c714d41cee7ed9，绑定在快照中。
实际主矩阵C重跑0；独立audit/negative均首次真实terminal exit0、retry0；不混同为整轮零失败。

whole-change v1快照a3a86a423f838abf389ee65816ee3af8a2be5d2a3a3104446b067d847524b65c，27项起止一致。
MINOR-1指出RESULT“不变”文案可能误指hard/fade剩余计数及评分数值相同；真实实施/递推正确，要求仅澄清文案。
修正明确控制投影/窗口范围/null资格保持、两模式remaining/alpha独立递推、fade两输出共alpha、评分代价完整披露。
v1与writer原字节保留，不重跑C或实际审计。
最终v2快照`/tmp/audio-fe-device-transition-d28-20261011/review-snapshot-v2.json` SHA256=518d0f490e93377b181f659a89768103ef244dc550ac3e05182ea6bf52d249ec。
fresh复审29项全部一致（9仓文件、5工件、12脚本/回执、3checks）；相对v1仅RESULT仓内文案改变，实际五工件/源码/合同不变。
MINOR-1已闭合，Spec/Quality均PASS、independent、unresolved0。

## 实际验证

严格C11编译、自测、5个C拒绝及4组sentinel保持通过；90次有效C输出处理exit0。
非仓cwd help/dry-run/4项Python tests与v2 docs self-test/实际docs/git diff检查均真实exit0。
D28 result/binding=67b5a3f3a11b27a167e1d4ac7e59211cc7f92f9c865f4f891ae8ee49cd7175ae / d34ca0be4f597297de80a16f78940146b276bdde648a03fc2dbfb5187bea2102。
独立audit不导入新测量器、不执行C/AEC/selector，核5,936次hash、90case/180trace/79,015,680输出浮点、246,924 CSV行、1,234,620 control bytes。
88条hard输出full byteeq、120,438条hard控制投影、88,640混合样本时刻、528总事件/censored0。
476原窗口、1,133有效channel/295null、236delta/108near；RMS/peak/delta误差0，正常mic代数max2.2351741790771484e-08。
候选主设备243事件、合成8事件；两通道injection最大绝对值0。
设备residual梯度合计15.245871150636518→12.983306823542838，55个事件增加，最大+0.07081278739013859（case08-used0、frame1979）。
108个known-near delta范围0..+0.12601249578147744dB；128设备能量delta范围-0.03529466576168261..+0.07466469566093892dB。
全部冻结准入条件满足，TRANSITION_DEVELOPMENT_CANDIDATE_ONLY一致；不能说逐事件均改善或无点击。
audit.py/json=e22d8c9d24d349caf9620ac233a00ecd941a3e2606b9eb7280d60673c830f5ef / 32699766bd180e0a4e319c9b65436bf2cf197545c4e8e550c2bba99e4358716f。
六工具负例均exit2，旧D27495/新D28475完整manifest不变；仓根仅潜在回执路径未写，不扩张为全dirty锁。
negative.py/json=c8e1adc181a3febd8489f3fbd661acd7c4b7489f98e46af78c0aa3f6ff2ae959 / 9e5077b428fbb79ce8f37eeb46147e020c46a53d9df3daf52a5b910b8aafa8ba。

## REVIEW后门禁与下一阶段

REVIEW字节由finalcheck-0/1绑定，实际docs与git diff检查终态及独立追加复审在本轮收口时核验。
Runtime通过evidence/artifact/progress/checkpoint/heartbeat闭合本地D28里程碑，并单独核final gate；不代表总体任务完成或产品放行。
原D0-D27源/工件及用户dirty保留，无commit/push/PR/merge/设备写/发布。
Provider仍route unresolved、current为空，知识线NEEDS_REVIEW；仓内reviewing candidate，不声明正式归档。
private过渡state16字节，不含selector/双AEC/产品数组；未测DUT CPU/RAM/热/功耗。
下一阶段核完整研究回放闭环、真实近端/双讲保护、完整NS/RES/AGC/KWS及目标资源/听感/HIL；不扫本轮过渡时长。
真人独立声学、AISpeech产品调用链、产品默认/API、E001/owner/Product Qualification均独立未闭合。
