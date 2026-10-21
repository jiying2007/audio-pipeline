# D21 独立审查与完成声明核对

日期2026-10-11；claimant=root；verifier=device_capture_independent_review；Reviewer Independence=independent。
最终Spec PASS、Quality PASS、未解决finding=0；仅支持D21工程诊断里程碑，总体native goal仍active。

## 审查过程与实际证据

冻结合同与修正版实现均经独立核对。初版将D19根别名误当D20根，真实哈希预检exit2，尚未创建输出、编译或执行DSP。
修正显式D20根，未改变预期哈希、参数、窗口或实验集合；首次失败完整保留，retry_used=1。
初版代码审查未识别该根别名问题，后续对真实根与锁的fresh复审闭合该finding，不使用初版PASS证明路径正确。

11次真实MDF执行的独立审计未导入新工具的构造或统计函数，也未重跑DSP。
2,967项hash、44条trace/14,080,000个float、22,000帧state CSV、55组统计和15组配对差全部通过。
独立重建7,040,000个mic/reference样本并核Float32LE逐byte一致，包含future的符号位语义。
统计最大复算差7.105427357601002e-15，AEC代数最大误差3.725290298461914e-9，满足冻结的≤1e-6。
三个negative的echo零/residual等mic/权重平方和零、repeat完整逐byte一致、future前缀因果一致均通过；SYNC bridge实际调用0。
审计脚本SHA256：`312f87bc9f75ce2ca4ac83b6025a4cf763be4f7bcfe0a5f66f02ec38a441970b`。
审计回执SHA256：`3921eb59d59769aad16c6c3263b7b0dfe9878976e3a3b6afedf49d0b8cb933b4`。

另实际6个创建前拒绝负例：missing/真实root分别请求既有D18、既有D21和仓库root，全部exit2。
D18的1,205文件、D21的74文件完整manifest前后不变；仓库失败回执路径前后不存在。
负例脚本SHA256：`3372a376ed5a58a59a16653e4a8635acd1938755434ed3b45d558fa3a92ceac5`。
负例回执SHA256：`90f7462a66be7621e2803468ea038d4618135952ff3e667c90931d787a06c4f4`。

whole-change快照SHA256：`a85552aa62aea3f837268e44b5aa95c14d8d8277d9362fa4a407bede2d67a59f`。
23项绑定当前字节匹配：7仓文件、5工件、8外部脚本/证据、3检查回执。RESULT三表60数值fresh核对准确。
review_mode=whole-change；known-finding依赖根已闭合；new_finding_class_count=0；reopened_finding_count=0。
path48/64的阶段差值变号被保留，没有把offset20或高末窗工程ERLE推广为产品配置。

## Evidence Index与完成门禁

工件根`/tmp/audio-fe-device-path-d21-20261011`；verified_at=2026-10-11T01:40Z，verifier如上。
下列均为actual命令回执；表中相对路径以工件根为准。

| Command | Exit | Result | Evidence path | Layer / artifact |
| --- | ---: | --- | --- | --- |
| cc，实际D18宏与库，严格C11 | 0 | runner编译 | command-compile.json | build / runner |
| runner invalid | 2 | 非法参数拒绝 | command-invalid.json | CLI / 拒绝路径 |
| 11 registered runner invocations | 0 | 全量执行及摘要核验 | 各case命令回执、binding.json | 工程DSP / trace、CSV |
| /tmp cwd device_path.py --help | 0 | CLI可用 | postcheck-0.json | CLI |
| /tmp cwd device_path.py --dry-run | 0 | 输入及身份预检，无写入 | postcheck-1.json | 输入/身份 |
| test_device_path.py，4 tests | 0 | 已知答案、非有限/长度、目录归属负例 | postcheck-2.json | 测量测试 |
| 初次错误依赖根preflight | 2 | 尚未执行，失败保留 | /tmp/audio-device-d21-preflight-failure.json | 负结果 |
| independent audit | 0 | 完整构造/统计/状态/hash复算 | /tmp/audio-device-d21-independent-audit.json | 独立测量 |
| 6 independent rejection invocations | 2 | 全部拒绝且原目录未改 | /tmp/audio-device-d21-independent-negative.json | 文件归属负例 |
| docs_consistency.py --self-test | 0 | 自验证 | docs-check-0.json | 文档 |
| docs_consistency.py | 0 | 实际文档检查 | docs-check-1.json | 文档 |
| git diff --check | 0 | 格式检查 | docs-check-2.json | 修改格式 |

Replayable Evidence Bundle=冻结PLAN、D18库/宏/生成头、原119输入锁、70份执行工件binding、23项复审快照、实际命令回执。
本轮数据为synthetic-engineering，不包含新增真人/设备采集；未把临时证据当正式归档。
Tool / Skill Evidence Plan：primary=adk-planning-execution-loop；supporting=adk-verification-before-completion；
required artifacts=PLAN/AMENDMENT/RESULT/REVIEW、runner/tool/tests、执行binding、独立audit/negative、whole-change snapshot。
SCM提交与设备操作技能不适用，未执行这些动作；Provider未fallback，route unresolved仍NEEDS_REVIEW。
Completion Guard：build/CLI/identity/measurement/negative/test/docs/independent-review适用项均通过；
最终REVIEW追加后的文档检查与Runtime回执另存于工件根。Runtime只证明本地执行符合性。
DSP函数体/产品配置/API/ABI/异步生命周期/权限政策/模型prompt/UI/release与设备操作均未变化，对应回归not_applicable。
本轮无breaking change，声学/真实资源/HIL/owner资格仍未闭合，不作为本工程诊断通过条件的替代证据。

## Codify Decision与接续

delivery_goal=D21固定门控已知路径工程诊断；reusable_pattern=先用已知因果构造与固定门控区分坐标响应，再研究复杂路径。
affected_asset=研究runner/工具/测试/中文入口；promotion_candidate=false；owner_review=产品资格未闭合。
next_task_friction_reduced=排除简单路径无法收敛假设、避免把4点坐标变化当通用改进；reduced_by=六主臂及控制、全量独立复算。
reduction_evidence=result/独立audit/negative/snapshot；do_not_promote_reason=纯回声固定门控工程数据，无独立声学与真实产品证据。
rollback_path=仅移除本轮新增研究文件与README对应入口，保留既有dirty及冻结D18/D19/D20工件；不涉及产品DSP回滚。
verification_evidence=23项快照绑定、实际编译/命令回执、独立全量审计及whole-change复审；本文仅仓内reviewing candidate。

下一阶段冻结多反射与路径切换控制，保持参数和门控不变，检验恢复过程及两参考坐标的响应。
本阶段不批准算法/默认参数、人声保护、AISpeech接入、ASR/KWS、设备/HIL/E001或产品资格；总体任务继续active。
