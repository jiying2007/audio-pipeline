# D25 路径退回与近端门控独立审查

日期2026-10-11；claimant=root；verifier=device_capture_independent_review；Reviewer Independence=independent。
Spec PASS、Quality PASS；QUESTION-1/2闭合，new_finding_class_count=0、reopened_finding_count=0、unresolved=0。
仅关闭D25本地工程诊断里程碑，总体native goal保持active；decision=RETURN_NEAR_GATE_DIAGNOSTIC_NO_PROMOTION。

## 审查、执行与独立实测

原PLAN SHA256 `312e95fa166fd0ec6e0671093ef666abb6f512d18559579523fb2d27b7f4594d`冻结保留。
初次计划复审提出两个QUESTION：shadow跨inactive范围评分未定义，新增字段与旧D24等价投影不够精确。
执行前AMENDMENT SHA256 `710e2bb9f06d428761b3fd4dafcb080c236ee5e546fe1f4dadebac46c58329e0`冻结明确null评分与字段投影，fresh计划复审闭合。
fresh实施复审通过；没有算法/比例/确认帧、路径/幅度/窗口调整。
严格编译、五项完整参数sentinel拒绝和26次真实执行全部首次符合预期；DSP及审计retry均0，无隐藏执行失败。
新C仅借用冻结D22常量/真实结构/SYNC桥，不调用旧main，直接include冻结D24 selector；两状态均调用真实MDF。
research_algorithm_changed=false、shipping_algorithm_changed=false；oracle dt/近端伪随机输入不是检测器或真人。

独立actual审计不导入项目测量器、不重DSP，复用旧D22标准库helper且运行前核其exact hash并绑定快照。
4412次hash、260trace/83200000个float、4输入共33280000样本独立逐byte构造，state和selector各52000行。
234窗口组、552有效channel组、150null shadow组、108项shadow差及72项gate差全部独立复算。
D24共72文件与12000帧selector投影，primary84配对文件、gate32输入文件、repeat/future各12文件通过。
逐帧double顺序能量、严格0.8比较/连续3帧/方向/streak/selected字节和事件两边界全部相符，能量/边界误差0。
最大AEC代数误差7.450580596923828e-9，统计/差值最大误差7.105427357601002e-15。
审计脚本SHA256 `751c60f6982bc4c4cd108939fb35e93afb5a3a7a4202a9b854dbb38929dc827b`；
回执SHA256 `6cd5deca4b0ba12532766f765510bd95acdbd5528d23b5cbb7acc763b99bf7d3`。

六项工具真实拒绝：missing/真实inputs × 既有D24、D25、仓根，均exit2；D24/D25完整242/411文件清单前后逐hash不变。
仓根只核潜在measurement-invalid.json保持不存在，不声称锁住所有既有dirty。
拒绝脚本SHA256 `37631267f86b9353cc39e98223404e3e8213e4f81ae16067ecfe2167c403e0ba`；
回执SHA256 `fd73ddeab130b87d760c02f063b2afe0af8ad9dfa48cf1ff2f8347574c36b7a3`。

whole-change快照SHA256 `a95faab625bf3645902d7e1236ba91431400d936be0b0475b0de290dc561a197`。
25项当前字节匹配：8仓文件、5工件、9外部脚本/回执、3检查回执；RESULT三表116数字及合并列零差值逐项核实。
ABA echo/unguarded四主shadow及repeat/future实测1002帧0→1、1202帧1→0；dt无翻转，所有A无翻转。
退A首窗误差+0.156889～+0.178141dB与后续primary等价同时保留；dt在B段shadow误差+5.182901～+9.101977dB的代价未隐藏。
dt各例400帧weight_l2等前帧，只支持平方和观察，不是完整权重身份或实际adapt计数。
实际state_bytes33020及调用次数核实，不是CPU/峰值内存/目标板资源。

## Evidence Index与适用性

工件根`/tmp/audio-fe-device-return-d25-20261011`；verified_at=2026-10-11；verifier如上。

| Command | Exit | Result | Evidence path | Layer / artifact |
| --- | ---: | --- | --- | --- |
| cc，真实库/宏，C11/-ffp-contract=off | 0 | 诊断fixture严格编译 | command-compile.json | build / runner |
| 5 full-arity invalid invocations | 2 | 12 sentinel不变且calls零 | command-invalid-preserve-*.json及对应目录 | CLI / 拒绝 |
| 26 registered runner invocations | 0 | 真实双状态执行 | 各case回执、binding.json | 工程DSP / trace、CSV |
| /tmp/audio-device-d25-run.py | 0 | 完整编排终态 | /tmp/audio-device-d25-execution.json | 执行身份 |
| /tmp cwd device_return.py --help | 0 | CLI可用 | postcheck-0.json | CLI |
| /tmp cwd device_return.py --dry-run | 0 | 身份预检，无输出目录 | postcheck-1.json | 输入 / 身份 |
| test_device_return.py，4 tests | 0 | null/混合目标/边界/归属 | postcheck-2.json | 定向测试 |
| independent audit | 0 | 全量独立复算 | /tmp/audio-device-d25-independent-audit.json | 独立测量 |
| 6 independent rejection invocations | 2 | 拒绝且原数据不变 | /tmp/audio-device-d25-independent-negative.json | 归属负例 |
| docs_consistency.py --self-test | 0 | 自验证 | docs-check-0.json | 文档 |
| docs_consistency.py | 0 | 实际检查 | docs-check-1.json | 文档 |
| git diff --check | 0 | 格式检查 | docs-check-2.json | 修改格式 |

Replayable Evidence Bundle=PLAN/AMEND、D18库/宏/头、119输入锁、D24及旧依赖冻结源/工件、本轮407工件binding、25项快照及实际命令。
Tool / Skill Evidence Plan：primary=adk-planning-execution-loop；supporting=adk-verification-before-completion；required artifacts=PLAN/AMEND/RESULT/REVIEW、C/tool/tests、binding、audit/negative、snapshot。
Completion Guard适用build/CLI/identity/construction/gate/selector/measurement/negative/tests/docs/independent-review均通过。
REVIEW追加后的最终文档和Runtime回执另存工件根，不扩大原25项已审快照；Runtime仅本地执行符合性。
产品API/ABI/配置/生命周期、权限政策/模型prompt/UI/release/设备未变，对应回归not_applicable；研究生命周期/门控不替代产品验收。
数据仅synthetic-engineering，无新增真人/设备采集，无敏感外发；Provider route unresolved保持NEEDS_REVIEW，仓内reviewing candidate未正式归档。
SCM外写及设备操作不适用；AISpeech、独立声学/真人、ASR/KWS、目标资源/HIL/E001及owner资格独立未闭合。

## Codify Decision与接续

delivery_goal=D25实际反向退回和近端门控取舍诊断；reusable_pattern=固定同输入双讲标签对照，并把门控收益与路径恢复代价一起审计。
affected_asset=研究C/tool/tests/中文入口；promotion_candidate=false；owner_review=产品资格未闭合。
next_task_friction_reduced=已有真实双向切换和混合目标误差参照，可接回设备开发输入核实际门控/切换，不靠纯回声总能量推断保护效果；
reduced_by=26次实际执行及独立逐帧/目标/事件/窗口复算；reduction_evidence=result/audit/negative/snapshot。
do_not_promote_reason=合成噪声非真人、oracle非实际检测、退回短窗退化及双讲期间路径变化代价、无crossfade和目标资源未资格化。
rollback_path=仅移除本轮新增研究文件及README对应入口，保留既有dirty与D18至D24冻结工件；不涉及产品DSP回滚。
verification_evidence=25项快照、实际编译/26执行/拒绝、独立actual与whole-change复审。
后续核设备development真实门控及切换行为，真人独立评分/听感/目标资源另验；不以本轮工程PASS提升产品默认。
