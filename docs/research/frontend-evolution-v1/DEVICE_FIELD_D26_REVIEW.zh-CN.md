# D26 设备开发回放独立审查

日期2026-10-11；claimant=root；verifier=device_capture_independent_review；Reviewer Independence=independent。
v2 whole-change Spec PASS、Quality PASS，unresolved=0；总体native goal保持active。
decision=FIELD_SHADOW_DIAGNOSTIC_NO_PROMOTION；仅关闭D26本地工程诊断，不批准产品默认或声学资格。

## 审查历史与实际范围

PLAN冻结SHA256为9bd6b907156b7a10bd9ca5365cc671a69f6fa98d2dff6eb5559712e7182d52ac。
实施首轮MAJOR-1误将D19九列control用于校验D22八列state，首编译/DSP前修复并fresh独立复审闭合。
AMENDMENT为136c1baad52f75b13839d407aa32d8e50d0ce9b530a5bb176131c2c2e3ed2244；5项正负例实际exit0。
research_algorithm_changed=false、shipping_algorithm_changed=false，冻结D24选择器/比例/确认帧及无crossfade行为不改。
66次真实工程执行均exit0；64主矩阵+repeat的primary估计回声/残差全量逐字节等D19，future仅通知前前缀逐字节等D19。
该结论不声称完整MDF内部状态字节一致；RESULT的future因果段限定前缀范围，不将其扰动后半当原开发输入。
16个主激活shadow臂538次切换，每臂5～55次；repeat/future分别27/25次，全部590次，负结果保留。

独立actual审计不导入新项目测量器、不重DSP，复用冻结D19标准库helper，运行前核其exact hash。
4035次hash核验、396trace/190967040个float、state与selector各198924行、264窗口组、548有效bank/244null、128差值、132个D19基线对照文件全部核实（130全量、future两文件仅通知前前缀）。
原D16全部counter事件/首通知、同输入实际far/dt、逐帧能量/严格0.8比较/三帧确认/方向/streak/selected字节、切换边界、inactive零值、PTS与null评分资格均独立核对。
RMS/peak/差值最大误差0，AEC代数最大误差1.4901161193847656e-08，低于冻结1e-6。
repeat八文件全量同，future通知前八文件前缀同；future后半未重新检测gate，不是现场选择数据。
实际额外sizeof33020字节、shadow总调用32564次，非目标板总RAM/CPU/功耗/热资格。

独立审计首版逐例核了代数误差，却没有更新回执最大值字段。首版脚本/回执原字节保留，修正版仅修该汇总及新输出路径后全量纯工件重审通过。
纯工件审计retry=1、DSP retry=0，不隐藏失败历史，不重试工程DSP。
最终审计脚本SHA256为bcd23ee2159e8c18cfda92ae6d8dea2b3d9b185c4a794ec9c127ac6d0312ed63；
回执为f87e6f5cdb74d1cc83ee96e3541c05ae5dc9a5c2303e9a3884142d91851656b0。

六项工具negative实际exit2，missing/真实输入×旧D25/新D26/仓根均正确拒绝。
D25完整431文件、D26完整713文件manifest前后逐hash一致；仓根仅工具潜在measurement-invalid影响路径未写，非全dirty仓锁定。
负例脚本SHA256为0c96aa18269e638b424980415604e30fd81a861cb453dcbe4773392cc15e46ce；
回执为1016c037a52f7f3e7b62b5f423ff334023e9a9958218d29b5318d03c95b83a52。

whole-change首轮v1快照8a7ef1216bd99b112de36ca36d5b833c247036229bbb920c493e1d1775658a1e保留。
MINOR-1：README将输出byteeq扩大为完整状态byteeq，已收窄为primary估计回声/残差，RESULT同时披露历史。
v2快照db38ea5149007d719b8728e19d442af28a5ff5d4c305d3470ab2161df9391c28的29项当前字节匹配：8仓文件、5工件、13脚本/回执、3新检查。
v1原snapshot脚本保存字节与v1绑定hash相同；相对v1仅RESULT/README两份仓内文档变化，五项实际工件hash不变。
RESULT的64表值、16切换计数、时间覆盖、资源边界与失败历史独立核实；fresh v2 Spec/Quality PASS，无新finding或reopen。
REVIEW首版MINOR-2将66执行基线范围写得含混，已精确列为130全量与future两前缀；仅改REVIEW，v2快照原字节不变。
历史MAJOR-1、MINOR-1/2均闭合；审计回执汇总缺陷已修正；当前unresolved=0，不抹除历史finding。

## Evidence Index与适用性

工件根`/tmp/audio-fe-device-field-d26-20261011`；verified_at=2026-10-11；verifier如上。

| Command | Exit | Actual result | Evidence path | Layer |
| --- | ---: | --- | --- | --- |
| cc C11，冻结真实库/宏，ffp-contract=off | 0 | 严格编译 | command-compile.json | fixture build |
| 5 full-arity invalid runner invocations | 2 | 输出打开前拒绝，8文件sentinel不变 | command-invalid-preserve-*.json | CLI negative |
| 66 registered runner invocations | 0 | 实际双状态执行 | command-case-*.json、repeat/future、binding.json | 工程DSP |
| /tmp/audio-device-d26-run.py | 0 | 父执行terminal | /tmp/audio-device-d26-execution.json | 执行身份 |
| /tmp cwd device_field --help / --dry-run | 0 | CLI/身份预检，无dry-run输出目录 | postcheck-0/1.json | CLI / source |
| test_device_field.py，5 tests | 0 | state列契约及负例 | postcheck-2.json | 定向测试 |
| independent audit，首版及r1 | 0 | 全量独立工件核验，汇总字段修正保留 | /tmp/audio-device-d26-independent-audit-attempt0.json、-r1.json | 测量 |
| 6 independent tool rejection invocations | 2 | 拒绝且原根不变 | /tmp/audio-device-d26-independent-negative.json | 归属负例 |
| docs_consistency.py --self-test / actual | 0 | v2自验证/实际文档检查 | docs-check-v2-0/1.json | 文档 |
| git diff --check | 0 | v2格式检查 | docs-check-v2-2.json | 格式 |

Replayable Evidence Bundle=PLAN/AMEND、119输入锁、D18库/宏/头、D16事件、D19真实输入/参考/gate、继承D24/D25、709生成工件binding、29项v2快照及v1历史。
Tool / Skill Evidence Plan：primary=adk-planning-execution-loop；supporting=adk-verification-before-completion；required artifacts=PLAN/AMEND/RESULT/REVIEW、C/tool/tests、binding、audit/negative、snapshot。
Completion Guard适用build/CLI/source/trace/gate/selector/measurement/negative/tests/docs/independent-review均通过。
REVIEW追加后的最终文档检查与Runtime回执另存工件根，不扩大原29项已审快照；Runtime仅本地执行符合性。
产品API/ABI/配置/生命周期、权限政策/模型prompt/UI/release/设备未变，对应回归not_applicable。
无新真人采集或敏感外发；Provider route unresolved保持NEEDS_REVIEW，仓内reviewing candidate未正式归档。
SCM外写/设备操作未执行；AISpeech、独立声学/真人、ASR/KWS、目标资源/HIL/E001及owner资格独立未闭合。

## Codify Decision与接续

delivery_goal=真实设备development门控下冻结双状态选择器诊断；reusable_pattern=原primary输出逐byte基线等价与逐帧bank选择审计独立于声学结论。
affected_asset=研究C/tool/tests/中文入口；promotion_candidate=false；owner_review=产品资格未闭合。
next_task_friction_reduced=已有完整实际切换事件及窗口基线，下一轮能对频繁往返切换做单因果实验；
reduced_by=66次真实执行与独立396trace/逐帧/窗口/事件核验；reduction_evidence=result/audit/negative/v2snapshot。
do_not_promote_reason=538次主臂往返切换、窗口能量增减非质量、无clean target、无crossfade/真人保护/目标资源资格。
rollback_path=仅移除本轮新D26研究文件及README对应入口，保留既有dirty与冻结旧工件，不涉及产品DSP回滚。
verification_evidence=29项快照、编译/66执行/拒绝/定向测试、独立actual与fresh v2 whole-change复审。
后续先冻结切换稳定性单因果合同，再分开核真人保护、输出边界、完整后处理与目标资源；总体逻辑任务保持open。
