# D27 固定最短保持独立审查

日期2026-10-11；claimant=root；verifier=device_capture_independent_review；Reviewer Independence=independent。
计划、实施、actual及whole-change fresh Spec PASS、Quality PASS；unresolved=0，无新软件finding或reopen。
仅关闭D27本地有界研究里程碑，总体native goal保持active。
decision=DWELL_DEVELOPMENT_CANDIDATE_ONLY；promotion_allowed=false、shipping_approved=false。

## 审查范围及真实执行

PLAN冻结SHA256为bed08018d79b0f0cb54d1fc743bf8d8c7c1f1ed480ab18f3589ecd437c9e882e；无事后阈值、时间或窗口调整。
新增选择器仅固定50帧保持；释放后重新三帧确认，最短52帧。保持期间清streak，far/dt不暂停帧时钟，有限校验不跳过；首次不延迟。
legacy复用冻结D24规则。新C只链接数学库、无AEC库调用，不改变四条冻结状态输出。
独立实施审查从/tmp真实复跑6Python tests exit0，C/header/tool/tests字节在执行及whole-change期间一致。
严格编译/C self-test、90次真实C选择器执行首次exit0；4完整非法参数在任何文件打开前exit2，三输出sentinel不变且calls0。
32个D26和12个D25主shadow源×legacy/dwell=88，加repeat/future2次；不是90次完整AEC或产品DSP执行。
88个legacy selected文件全量等原输出、120438行CSV原字段投影同；不声称内部MDF状态转储等价。

## 独立actual审计及失败保留

独立actual不导入D27或原D26/D25测量器、不执行C/AEC，使用冻结D19标准库helper并先核exact hash。
4400次hash核验；90case、180trace共79015680个float、246924行selector、740772个gate byte全部核实。
476窗口组、1133有效bank/295null、236差值窗口、108 known-near差及813次事件独立复算。
逐帧順序double能量、严格比例/确认、保持边界/时钟/失活、当前输出字节、事件两种边界、PTS与原固定窗、null资格、重复与future前缀全部对应。
RMS/peak/差值最大误差0。
工程候选条件独立重判：538→243，减少54.83271375464684%；首次不延迟；相邻至少52帧。
D25所有12个dwell源的24输出全量逐byte等原D25，四ABA echo/unguarded仍1002/1202切换，静态与dt无切换，108项原窗口known-near差全0。
设备残差能量范围-0.07603389444414788～+0.8451197379992834dB保留，不能解释成音质改善。
candidate-only是固定开发规则的判断，非独立声学、真人、检测闭环或产品晋升。

审计首版实际session84399 terminal exit1：独立比较器误要求D25统计有samples字段，进入return true_echo时KeyError。
真实原脚本及完整stderr/terminal失败回执保留；仅修独立schema适配后session40442 terminal exit0。
纯工件审计retry=1、C/AEC重试0；不把审计失败说成执行软件失败，也不隐藏负记录。
首版脚本/失败回执SHA256：37d1a5b1e5317e848653e52109fe646b928ddb33070a6fa0d7e179ed5204762b / b42ff8129eb108aa3bcbecf0d89960e4e8ac84db569faf73121d3ab9fcccfc48。
最终审计脚本/成功回执：aef1b786c85ad47f9de736b04a5b63483114636216f1ef0b55542566a2bd134f / 37162df128c710bb76de2cf58330e59f7236eb2efb6c6e3d86ef552decf9118e。
helper SHA256：2841daaeaff30ebfc6dedf9f53ef465b87830af5af2601e7d27e33c69b263300。

六次工具negative实际exit2，父negative session54593 terminal exit0；missing/真实input×旧D26/新D27/仓根均正确拒绝。
D26完整739文件、D27完整475文件manifest前后逐hash相同；仓根仅潜在measurement-invalid影响路径未写，非全dirty仓锁定。
负例脚本/回执SHA256：a5e46ed83f60b3d310169bcbf0ece4b9a2549c971d2057583f1e93583ce3125e / d738a9fd9f24e5a81ffa111c32f9436085d6f41bdbdcd997860165a4a1da5d18。

whole-change快照SHA256为3381e9c3cf7b3f7fcb853d502100f4262db4f189562beb823668c241edac1cc9。
27项当前字节匹配：8仓文件、5工件、11外部脚本/回执、3文档检查；RESULT64数字/32切换数及108零差值fresh核实。
选择器sizeof20字节不包含原双AEC成本，文档明确集成资源独立未验；无额外lookahead/帧缓冲，不是无点击证明。

## Evidence Index及适用性

工件根`/tmp/audio-fe-device-dwell-d27-20261011`；verified_at=2026-10-11；verifier如上。

| Command | Exit | Actual result | Evidence path | Layer |
| --- | ---: | --- | --- | --- |
| cc C11/O2/strict warnings/ffp-contract=off | 0 | selector fixture编译，无AEC库 | command-compile.json | build |
| runner --self-test | 0 | legacy/保持/finite/inactive/时钟/gate | command-self-test.json | C契约 |
| 4 full-arity invalid runner invocations | 2 | sentinel不变、calls0 | command-invalid-preserve-*.json | 拒绝 |
| 90 registered selector invocations | 0 | 实际输出选择 | command-field/return/repeat/future及binding.json | 工程研究 |
| /tmp/audio-device-d27-run.py | 0 | 完整父执行terminal | /tmp/audio-device-d27-execution.json | 身份 |
| /tmp cwd tool --help / --dry-run | 0 | CLI/44源预检，dry根未创建 | postcheck-0/1.json | CLI / source |
| test_device_dwell.py，6 tests | 0 | 边界/严格比较/门控/失活 | postcheck-2.json | 定向测试 |
| first independent audit | 1 | schema KeyError，真实失败保留 | /tmp/audio-device-d27-independent-audit-attempt0.json | 审计失败 |
| corrected independent audit | 0 | 全量独立工件复算 | /tmp/audio-device-d27-independent-audit.json | 测量 |
| 6 independent tool rejection invocations | 2 | 拒绝且原根不变 | /tmp/audio-device-d27-independent-negative.json | 归属负例 |
| docs_consistency.py --self-test / actual | 0 | 自验证及实际文档检查 | docs-check-0/1.json | 文档 |
| git diff --check | 0 | 修改格式检查 | docs-check-2.json | 格式 |

Replayable Evidence Bundle=PLAN、119原输入锁、D24-D26依赖、四bank trace/原gate/known-near目标、471生成工件binding、27项快照、真实命令及审计失败历史。
Tool / Skill Evidence Plan：primary=adk-planning-execution-loop；supporting=adk-verification-before-completion；required artifacts=PLAN/RESULT/REVIEW、C/header/tool/tests、binding、audit/negative、snapshot。
Completion Guard适用build/C契约/CLI/source/trace/gate/selector/measurement/negative/tests/docs/independent-review均通过。
REVIEW追加后的最终文档检查及Runtime回执另存，不扩大已审27项快照；Runtime仅本地执行符合性。
产品API/ABI/配置/生命周期、权限/模型prompt/UI/release/设备未变，对应回归not_applicable；固定状态轨迹不代替实际闭环。
无新真人采集、敏感外发或SCM/设备写；Provider route unresolved保持NEEDS_REVIEW，仓内reviewing candidate未正式归档。
真人声学/听感、AISpeech及KWS/ASR、目标资源/HIL/E001/owner资格独立未闭合。

## Codify Decision与接续

delivery_goal=以固定500ms保持减少真实开发轨迹频繁往返切换，同时保留已知退回及近端代价验证；
reusable_pattern=当bank演进独立于选择时，从冻结bank输出做单因果选择器研究，legacy逐byte基线和验收条件独立复算。
affected_asset=研究C/header/tool/tests/中文入口；promotion_candidate=false；owner_review=产品资格未闭合。
next_task_friction_reduced=已有更稳定的固定候选及完整事件/能量代价，后续可独立核输出边界与真人保护；
reduced_by=90次实际选择器执行、独立180trace/逐帧/目标/窗口/事件复算；reduction_evidence=result/audit/negative/snapshot。
do_not_promote_reason=开发自适应复用、无独立真人/clean目标、+0.845dB能量代价、无crossfade/检测闭环/整链/目标资源资格。
rollback_path=只移除新D27研究文件和README对应入口，保留既有dirty、D24-D26及原工件，不涉及产品DSP回滚。
verification_evidence=27项快照、真实90执行/拒绝/self-test、独立actual及fresh whole-change复审。
不继续扫保持时间获取有利分数；下一阶段分开验证切换边界、真实近端、完整后处理与目标成本，总体逻辑任务open。
