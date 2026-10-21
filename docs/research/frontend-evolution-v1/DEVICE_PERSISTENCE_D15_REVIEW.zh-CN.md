# D15 独立复审：持续路径测量通过，无算法晋升

日期：2026-10-11；reviewer=`device_capture_independent_review`；independence=`independent`。
**Spec PASS / Quality PASS**，范围为observer实现、实际测量及诊断披露。
D11/D14原REJECTED保持，decision=`ENGINEERING_PERSISTENCE_DIAGNOSTIC_NO_PROMOTION`。
`promotion_allowed=false`、`shipping_approved=false`；总goal保持active，仅D15里程碑可收口。
没有新增blocker、major或实质minor，不保证无缺陷。

## 冻结对象与独立核验

对象：[计划](DEVICE_PERSISTENCE_D15_PLAN.zh-CN.md)、[结果](DEVICE_PERSISTENCE_D15_RESULT.zh-CN.md)、
README、observer fixture、result/binding、执行和snapshot脚本。
快照 `/tmp/audio-fe-device-persistence-d15-20261011/review-snapshot-v1.json`，
起止SHA256=`71f8a4abadf92e961dfd70125dcebc1d699b9c13e8d7608c918e6e191a86d807`。
4个仓内文件、2份工件、3份检查回执、2个脚本全部匹配，未stale。
本REVIEW由根代理收到最终结论后新增，不属于被审快照，Runtime另绑定本文件。

此前定向独立核528项binding hash；两版只有函数定义名重命名，函数体不改。
实际measurement library原符号为未定义引用、d15_real符号为定义，显式观测入口成立。
两版measurement库身份分别为
`5dbe97a4ab2b953342d7e1c3003457142686f88f332421880e591e2d7d03d551`和
`b73680e0932b6a5ae5c444bcf1bb57a82d13d3a3dcfe8d09ddb5c2b95bff8a5e`，不冒充原库。

16次48,384帧PCM/public metrics与原receipt逐字节相同；
observe/no-observe输出、metrics、actual mono/render样本相同；default/control trace也相同。
独立逐帧重判delay、jump/reset/slips和确认状态，覆盖2400个eligible epoch。
从actual Float32LE及线性absolute索引独立复算15273个分数，double累加不复用observer环形索引，
最大绝对误差2.4804382e-6，小于冻结3e-6。
40 ms原helper精确等价断言、800点回绕/完整历史边界/配对/reset自测与无效参数exit2都有实际记录。

## 新事实及语义边界

D14 case07最后确认簇707/717/727帧，refined20/23/15，提交anchor20。
最后40 ms refined/anchor=0.158609286/0.0052079712；
200 ms refined/anchor=0.404646188/0.0040005194，RESULT准确区分检验对象和提交对象。
D14 case16最后簇1227/1237/1247帧，refined16/16/16、anchor16，200 ms支持0.736714303。
旧delay635与D11原事件640已披露，不作同态反事实。

40 ms不足语义为0，100/200 ms不足为-1/not_available；没有混用。
anchor_valid只在confirm_before>0成立，旧有效anchor、残留值和restart后的anchor_after正确区分。
“长窗不能必然拒绝两个事件”限定为固定窗口实测，不给任何新策略门限或物理正确性授权。
下一提交锚一致性改动明确尚未执行，不承诺解决case16。
RESULT和README与实际CSV一致；不把相关强、输出能量或计数降低当作声学改善。
whole-change复审复用已有完整测量复算，对新文档/snapshot做新鲜核验，没有无依据重复全量测试。
独立审查只读，未修改文件、spawn或访问设备。

## 阶段完成、检查与恢复

claimant=root；verifier=device_capture_independent_review；completion_claim=D15独立诊断和证据审查完成。
primary_skill=adk-planning-execution-loop；supporting_skill=adk-verification-before-completion。
本里程碑open_items=0，总体native goal=active；未完成真实声学、物理、目标设备/HIL或产品资格。
breaking_change=false；无产品src/default/API、AISpeech、E001或历史I025–I040改动。
无UI、控制面、prompt、release、设备生命周期变更，相关门禁not_applicable。

| 实际命令类别 | exit / 结果 | 证据与层 |
| --- | --- | --- |
| 两版configure/build/strict observer compile | 0 | 对应configure/build/runner-compile/observer-link.json，Host |
| 两版observer --self-test | 0 | self-test.json，测量性质 |
| 两版无效参数 | 2 | invalid-arguments.json，CLI负例 |
| 16次完整observer run | 0，全输出/metrics等价 | 原始CSV/PCM/JSONL/Float32LE，实际测量 |
| docs自测/实际/diff-check | 0，OK/PASS | docs-check-0/1/2.json，文档/格式；REVIEW补写后定向复验 |

verification_evidence=RESULT、binding、snapshot与独立样本复算/whole-change结论。
Runtime final另核实际回执，仅本地conformance，不能推导domain或总体完成。
reusable_pattern=检验候选与提交锚分开记录，有效锚与残留状态分开定义，长窗索引须独立实际样本复算。
promotion_candidate=false；next_task_friction_reduced=提交锚一致性已有具体失败帧、支持分数与冻结回归契约。
reduction_evidence=48384全帧等价、15273独立分数和完整确认簇，不替代声学证据。
do_not_promote_reason=本轮只有诊断，D11/D14拒绝且真实物理/声学/设备资格缺失。
owner_review=未取得产品/声学owner资格，本独立复审不替代owner。
rollback_path=observer不安装SDK，原算法不改，保留研究fixture/docs及tmp测量，不清理已有dirty。
Provider route unresolved，仓内reviewing candidate，未正式归档；恢复先核hash，tmp失效则stale。
