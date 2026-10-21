# D14 独立复审：执行与拒绝记录通过，候选拒绝

日期：2026-10-11；reviewer=`device_capture_independent_review`；independence=`independent`。
**Spec PASS / Quality PASS**，仅覆盖单因果实现、实验执行、证据绑定与结果披露。
Candidate=`REJECTED_DEVELOPMENT_COUNTER_REGRESSION`；`promotion_allowed=false`、`shipping_approved=false`。
没有新增blocker、major或实质minor，不保证无缺陷。
本轮里程碑可收口，总体“全面推进优化迭代”仍active；原D11拒绝和产品资格不变。

## 精确对象与核验

对象：[冻结计划](DEVICE_CONFIRM_D14_PLAN.zh-CN.md)、[结果](DEVICE_CONFIRM_D14_RESULT.zh-CN.md)、
README、研究patch、确认fixture、工程/回放/comparison/binding与三个编排脚本。
快照 `/tmp/audio-fe-device-confirm-d14-20261011/review-snapshot-v1.json`，
起止SHA256=`420ecc61f9c8c5ad23dc7d10902712355a44a3991aad37790758765925ee5017`。
独立复审实际核1259项snapshot/final-binding hash，补核142项原/候选source/config hash，未stale。
此前P1–P3复审实际核962项工程绑定；两个范围有重叠，不合计成独立项数。
本REVIEW由根代理收到独立最终结论后新增，不属于被审快照，Runtime另绑定本文件。

精确D11相对候选只有一行确认容差实参变化，独立patch重放byte-exact。
strict CTest14/14、D8 engineering/recovery、21618项oracle、确认边界性质通过，state=78840 bytes。
D13原52/52和D9原26/26 mandatory均已独立从CSV重判；输入/config和指定新进程重复保持原锁。
根代理另回读D14与D11的整个100条known summary逐字段相同，没有用该相同替代原CSV检查。

## 原开发回放与拒绝规则

独立重新运行原receipt verifier exit0：16场景、70固定臂、2重复，receipt
SHA256=`bd78f3151f3052c5ce62c1984455caf11f6235b1ccd8f4723d42c72775246807`。
全部适配输入/config跨D8/D11/D14一致；工程库与实际replay库相同。
两个重复臂相同，default/control相同，34个tracker-off控制与D8/D11完全一致。
相对D11有65/70、相对D8有42/70臂PCM/metrics逐字节相同。
所有比较行counter、变化时点、delay集合、rail samples与原文件一致；210组窗口RMS从PCM独立重算。

原D8硬门禁实际触发6条counter差异，对应3个执行臂、2个场景：
rpm240 far-motion default/control的新增jump/reset由457→727帧；
rpm480 double-talk-motion default由617→1247帧，仍各一次。
另外两臂已有jump由457→1057和547→1977，未被误计为新增失败场景。
目标tracked1与D11相同、无172 ms跳变，不豁免整版拒绝。

RESULT/README与证据一致，帧时间明确为适配回放处理时间。
未编造D14后续候选三元组，未把RMS/slips/延后解释为物理正确性、ERLE、人声保真或听感收益。
原docs自测、实际检查与diff-check回执exit0；本REVIEW补写后再定向复验，不重跑候选求绿。
独立审查只读，未写文件、spawn、访问设备或执行SCM写操作。

## 阶段完成声明与恢复

claimant=root；verifier=device_capture_independent_review；completion_claim=本版单候选实验与拒绝审查完成。
primary_skill=adk-planning-execution-loop；supporting_skill=adk-verification-before-completion。
软件实验open_items=0；总体native goal=active，外部真实声学/物理/目标板资格未完成。
breaking_change=false；无产品src/default/API、AISpeech、E001或旧历史结果改动。
无UI/主观视觉、控制面、prompt、公共API、release/设备生命周期操作，相关门禁not_applicable。

| 命令类别 | exit / 实际结果 | 证据 / 层 |
| --- | --- | --- |
| strict configure/build/CTest | 0，14/14 | build.json/ctest.json，Host |
| engineering/recovery/oracle/confirm fixture | 0，全通过 | 工程绑定中的编译/运行原文 |
| event/known矩阵与repeat | 0，57+101次运行 | 原CSV/input/output/config，工程契约 |
| event无效第三参数 | 2，按预期拒绝 | event-invalid-arguments.json，CLI负例 |
| 原device_replay与verifier | 0，70+2 | receipt/comparison，开发测量 |
| docs self-test/实际/diff-check | 0，OK/PASS | docs-check-0/1/2.json，文档/格式 |

verification_evidence=RESULT、engineering/final binding、comparison、snapshot与独立whole-change结论。
Runtime final另核实际回执，只代表D14阶段本地conformance，不推导domain release或总体完成。
reusable_pattern=确认锚点容差性质与全长回放独立验收，防止把旧三元组打断当作事件消失。
promotion_candidate=false；next_task_friction_reduced=下一诊断已有延后事件帧、完整输入/config和冻结工程保护。
reduction_evidence=70+2真实执行、210窗口独立复算和52/26工程门禁；不作为声学资格。
do_not_promote_reason=原D8稳定性硬门禁失败，且独立声学/物理/目标板资格缺失。
owner_review=未取得产品/声学owner资格，本独立复审不替代owner。
rollback_path=产品源码不启用此候选，只保留独立研究patch/fixture/docs，不清理既有dirty。
Provider route unresolved，仓内reviewing candidate，未正式归档；tmp工件恢复必须核hash。
下一阶段先冻结D14延后事件的完整候选簇和持续路径证据诊断；本实验不再缩小容差或修改验收。
