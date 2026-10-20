# D24 双状态旁路原型独立审查

日期2026-10-11；claimant=root；verifier=device_capture_independent_review；Reviewer Independence=independent。
Spec PASS、Quality PASS；MINOR-1闭合，new_finding_class_count=0、reopened_finding_count=0、unresolved=0。
仅关闭D24本地研究里程碑，总体native goal仍active；decision=PROTECTED_SHADOW_PROTOTYPE_NO_PROMOTION。

## 合同、修复和实际执行

冻结PLAN SHA256 `264ddb76bd79096982d7fa1578b549a3fbb7039eccbcd78014d6cc0380adbc92`独立计划审查通过。
AMENDMENT修正激活前trace标签：只有shadow两trace为零，primary始终实际执行；原PLAN冻结字节保留。
首轮实施静态审查发现MINOR-1：完整非法参数可能先截断五个新增输出。首次实际DSP前修复为所有fopen前完整校验，fresh实施复审通过。
实际四项完整参数拒绝均exit2、五个预置sentinel不变、primary/shadow处理计数零；不存在被隐去的DSP失败。
严格编译、C selector已知答案及17次真实原型执行首次全部通过；execution_retry=0，不调整参数或评分规则。
研究算法改变，shipping算法未改；primary从不reset，shadow在第1000帧前reset一次并持续处理同输入。

独立actual审计未导入项目测量函数或重跑DSP：3779次hash、136条trace/43520000个float、
10880000个独立构造输入样本、primary及selector各34000行、119组统计、42组差值。
17例primary共85文件对D22逐byte一致；11例激活shadow后半共22文件对D23逐byte一致。
逐帧double顺序能量、严格0.8比较/连续三帧/双向规则、bank/streak/change及本帧selected字节全相符；能量误差0。
选中/primary最大代数误差7.450580596923828e-9、shadow为3.725290298461914e-9；统计/差值最大误差1.4210854715202004e-14。
审计脚本SHA256 `4e823fa3d808c70dcbb2551140a930b599b4533ef88c72666c7e745c8219283e`；
回执SHA256 `15a7171032edcbd1c6f9c1eef0379519c4e1d2123b80bd8acfff6b2a00ded950`。
首次自写审计因系统Python不支持dict union停止，仅修兼容写法后重跑读取审计，未改实验或重跑DSP。
失败摘要SHA256 `bb8ca389d15accbff36ca2302b19755d988608341b10086991d2e692d3d2375b`已绑定保留，不能计作DSP执行重试。
旧D22标准库helper exact hash也绑定本轮快照。

六项真实工具拒绝：missing/真实inputs × 既有D23、D24、仓根，均exit2；D23/D24完整130/220文件清单前后逐hash不变。
仓根仅核潜在measurement-invalid.json保持不存在，不声称锁住所有既有dirty。
拒绝脚本SHA256 `6534b1c3f05f77f66c138e227a831037be54d5cd6a51518b3d7f7058ecb42175`；
回执SHA256 `68b04a0e5fc172f37f418c947890fe3b25314aa0994e823b6a28cfa72f66e46c`。

whole-change快照SHA256 `94d23852eb93302f718ea8c9f8f9ff42d9a1df4a417aa46d6b0f9ccbb1fc0247`。
24项当前字节匹配：8仓文件、5工件、8外部脚本/回执、3检查回执；RESULT两表84数字及future数字逐项核实。
四static主臂无翻转且差值零；两switch主臂及repeat/future仅第1002帧翻转一次。
真实switch首窗收益约4.1dB、末窗约4.6dB；确认前两帧保留primary的取舍明确保留。
没有实际DSP反向切回，反向能力仅C已知答案与Python定向测试覆盖；真人、多次通知、切换听感未资格化。
真实ELF及summary一致记录新增状态33020字节，事件后每帧两个AEC调用；非总内存/CPU/目标板预算。

## Evidence Index与适用性

工件根`/tmp/audio-fe-device-shadow-d24-20261011`；verified_at=2026-10-11；verifier如上。

| Command | Exit | Result | Evidence path | Layer / artifact |
| --- | ---: | --- | --- | --- |
| cc，真实库/宏，C11/-ffp-contract=off | 0 | 原型严格编译 | command-compile.json | build / runner |
| 4 full-arity invalid invocations | 2 | 无截断且calls零 | 四negative目录及binding.json | CLI / 拒绝 |
| runner selector-self-test | 0 | 严格边界/确认/双向规则 | command-selector-self-test.json | selector / 已知答案 |
| 17 registered runner invocations | 0 | 实际双状态执行 | 各case回执、binding.json | 工程DSP / trace、CSV |
| /tmp cwd device_shadow.py --help | 0 | CLI可用 | postcheck-0.json | CLI |
| /tmp cwd device_shadow.py --dry-run | 0 | 身份预检 | postcheck-1.json | 输入 / 身份 |
| test_device_shadow.py，4 tests | 0 | 规则/测量/目录归属 | postcheck-2.json | 定向测试 |
| independent audit | 0 | 全量独立复算 | /tmp/audio-device-d24-independent-audit.json | 独立测量 |
| 6 independent rejection invocations | 2 | 拒绝且原数据不变 | /tmp/audio-device-d24-independent-negative.json | 归属负例 |
| docs_consistency.py --self-test | 0 | 自验证 | docs-check-0.json | 文档 |
| docs_consistency.py | 0 | 实际检查 | docs-check-1.json | 文档 |
| git diff --check | 0 | 格式检查 | docs-check-2.json | 修改格式 |

Replayable Evidence Bundle=冻结合同/AMEND、D18库/宏/头、119输入锁、D22/D23冻结源与工件、本轮216工件binding、24项快照与实际命令。
Tool / Skill Evidence Plan：primary=adk-planning-execution-loop；supporting=adk-verification-before-completion；required artifacts=PLAN/AMEND/RESULT/REVIEW、C/header/tool/tests、binding、audit/negative、snapshot。
Completion Guard适用build/CLI/identity/construction/measurement/selector/negative/tests/docs/independent-review通过。
REVIEW追加后的最终文档与Runtime回执另存工件根，不扩大原24项已审快照范围；Runtime仅本地执行符合性。
产品API/ABI/配置/生命周期、权限政策/模型prompt/UI/release/设备未变，对应回归not_applicable；研究双状态生命周期不可替代产品验收。
数据仅synthetic-engineering，无新增真人/设备采集，无敏感外发；Provider route unresolved保持NEEDS_REVIEW，仓内reviewing candidate未正式归档。
SCM外写及设备操作不适用；历史拒绝、AISpeech、独立声学、ASR/KWS、目标资源/HIL/E001/owner资格独立未闭合。

## Codify Decision和接续

delivery_goal=D24保留旧状态的双状态研究原型；reusable_pattern=保留旧状态对照并逐帧复核固定因果选择器，联合报告真事件收益与误事件代价。
affected_asset=研究C/header/tool/tests/中文入口；promotion_candidate=false；owner_review=产品资格未闭合。
next_task_friction_reduced=后续人声/反向/多次事件可直接复用双状态和选择trace，不必重建单状态对照；
reduced_by=17次真实双状态执行及独立逐帧状态/能量/字节复核；reduction_evidence=result/audit/negative/snapshot。
do_not_promote_reason=纯回声能量不能批准人声保护、无crossfade听感未验、实际反向/多次事件及目标资源未验。
rollback_path=仅移除本轮新增研究文件与README对应入口，保留既有dirty及D18至D23冻结工件；不涉及产品DSP回滚。
verification_evidence=24项快照、实际编译/执行/拒绝、独立actual及whole-change复审。
接续加入近端/双讲、真实反向退回和边界控制，再核真实开发回放及目标资源；不得据本轮工程收益提升产品默认。
