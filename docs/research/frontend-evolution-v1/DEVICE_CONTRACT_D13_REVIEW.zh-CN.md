# D13 独立复审：事件基线通过审查，算法资格不变

日期：2026-10-10；reviewer=`device_capture_independent_review`；independence=`independent`。
**Spec PASS / Quality PASS**，范围为测量实现、冻结契约执行及结果披露。
未发现新增 blocker、major 或实质 minor；计划审查的 pulse QUESTION 已闭合，不保证无缺陷。
决定=`ENGINEERING_EVENT_CONTRACT_BASELINE_ONLY`，D8 的16项 mandatory FAIL 与D11原现场 REJECTED均保留。
`promotion_allowed=false`、`shipping_approved=false`，未批准算法或产品采用。

## 冻结对象与独立核验

对象：[冻结计划](DEVICE_CONTRACT_D13_PLAN.zh-CN.md)、[测量补充](DEVICE_CONTRACT_D13_AMENDMENT.zh-CN.md)、
[结果](DEVICE_CONTRACT_D13_RESULT.zh-CN.md)、README、fixture及三份工件、两个编排脚本。
快照 `/tmp/audio-fe-device-contract-d13-20261010/review-snapshot-v1.json`，
SHA256=`50b5b7f69cfcdd7f52355a566d873ea03685feb7e508c2e5d66464dcc2bf9f0f`。
独立起止核验5个仓内文件、3份工件、2个编排全部匹配；连同binding实际核验605项hash，未stale。
本REVIEW由根代理收到独立最终结论后补写，不属于上述被审快照文件。

实际链接D8/D11原库，各59个锁定源码文件与原receipt完全一致，生成头匹配，未使用D12测量库。
独立SYNC shadow同库、独立状态、S16缩放与本组等采样率公共路径一致；
fixture逐帧断言delay/jumps/slips/resets一致，仅在observed时比较公开误差，输出由原public pipeline产生。

56种input/config跨版本逐字节一致；两版指定新进程repeat的input/output/CSV/config与首跑一致。
48次acquire/path-switch输入实际匹配原D9文件。
独立从原输入重算 **2,016,000个mic样本**的延迟、pulse叠加、静音与unrelated量化，全部一致。
独立回读CSV重算累计计数、首次到达、末20帧、唯一jump本帧目标、切换前逐帧保护：
**D8 36/52 PASS、16 FAIL；D11 52/52 PASS**。
D8失败全为1/7 ms获取/切换的16个case，四项失败原因未重复计算为64个独立事件。

## 干扰分量边界与结果披露

10帧pulse最大confirm_after=1；20帧为1或2，随后更新清零，无jump/reset。
没有把中间帧持有确认计数算为多次更新，原计划关于时长的疑问由实际候选记录闭合。
pulse3实际D8有事件3/4、D11有事件2/4，均在149/179帧跳79/80 ms后回40。
第三次确认后清零的解释正确，四例/版诊断未纳入mandatory分母，也未推导真实抗干扰优势。
RESULT和README与实际证据一致；0.39 s和变更后0.29 s限定为生成器帧时间，非产品实测。
D11合成52/52不改写原设备回放REJECTED，也不证明现场40→1–2 ms迁移属于正常获取。
独立审查只读，未修改文件、spawn、重跑旧全套门禁或访问设备。

## 定向检查和恢复入口

根代理Python3.10 `scripts/docs_consistency.py --self-test` exit0/OK；
实际 `scripts/docs_consistency.py` exit0/PASS；`git diff --check` exit0。
Runtime证据绑定与final门禁另行执行，不从本复审推导其结果。
无产品源码/default/API、AISpeech、E001改动，无commit/push/设备写。
Provider route unresolved，仓内reviewing candidate，未正式归档。

恢复先核RESULT及原库、源、生成头、binding/audit/快照；临时工件失效不得伪称历史可复现。
下一算法实验需同时保护正常获取、持续路径恢复、稳态与短分量拒绝，另核原D9、uniqueness、资源和设备回放门禁。
真实对齐、人声标签、render时间轴和独立数据仍需真实采集；不得用已查看development结果替代。
本地主机、main CI、Runtime conformance不等于目标板、HIL、shipping、owner或Product Qualification资格。

## 完成声明核对与复用决定

claimant=root；verifier=device_capture_independent_review；completion_claim=冻结事件回归及证据审查完成，
不是算法或产品完成。软件测量open_items=0；真实对齐/声学/目标板资格仍为独立外部事项，不计作已完成。
primary_skill=adk-planning-execution-loop；supporting_skill=adk-verification-before-completion。
无UI/主观效果、控制面、prompt、公共API、release或生命周期操作修改，相关门禁not_applicable。
breaking_change=false；测试shadow和fixture不安装到SDK，原库及默认构建不改。

| 实际命令类别 | exit | 结果 / 证据 | 层 |
| --- | ---: | --- | --- |
| cc strict C11编译两版fixture | 0 | d8-build.json / d11-build.json，原库身份已锁 | Host build |
| 两版runner完整矩阵与repeat | 0 | d8-run.json / d11-run.json / 两份repeat；114次完整回读 | 工程事件契约 |
| runner无效第三参数 | 2 | 两份invalid-arguments.json，按预期拒绝 | CLI负例 |
| docs_consistency自测/实际 | 0 | 本轮CLI返回OK/PASS，复审补写后复验实际入口 | 文档 |
| git diff --check | 0 | 本轮实际执行无错误，复审补写后复验 | 格式 |

command级编译/运行原文、输入/输出/config、环境头/库及完整摘要由binding绑定，
snapshot绑定审查文件与audit；临时工件的保留边界如RESULT所述。
reusable_pattern=正常获取/路径恢复与干扰抑制分开定义真值和事件，而非只比较reset总数。
promotion_candidate=false；next_task_friction_reduced=下一候选已有固定52项门禁、诊断项与逐帧确认入口。
reduced_by=可复用C fixture和原库/输入/CSV锁；reduction_evidence=114次执行、跨版输入一致及独立复算。
do_not_promote_reason=合成工程数据、D11现场拒绝且真实对齐/声学/板端资格缺失。
owner_review=产品/声学owner未取得，本独立review不替代owner。
rollback_path=本轮仅新增研究fixture/docs；不启用到产品，原库不改，不清理已有dirty。
verification_evidence=RESULT、binding、audit、snapshot与独立whole-change结论。
completion_guard=Host build/CLI负例/逐CSV测量等价/文档/独立review适用且通过；
Runtime final另核实际回执；domain release、设备/HIL、声学和真实resource不在本轮完成声明内。
