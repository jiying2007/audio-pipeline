# D20 独立审查与完成声明核对

日期2026-10-11；claimant=root；verifier=device_capture_independent_review；Reviewer Independence=independent。
最终Spec PASS、Quality PASS、未解决finding=0；支持D20分析里程碑收口，总体native goal仍active。

## 审查过程与实测

冻结计划PASS，明确复用已查看development数据、不重跑DSP、eligible只为实际适配谓词一部分。
初次实现的相对依赖路径导致/tmp dry-run exit2；修复为明确ROOT+safe_file解析和自身绝对身份。
独立实际6个创建前拒绝负例均exit2且无工具写入：D19的1,332文件、初次D20的2文件清单/hash前后不变，
仓根measurement-invalid路径不存在。首次失败完整保留，修正版与初次完整分析result逐字节相同。

独立审计直接比较Float32LE的uint32位模式、独立归并连续区间，并从原WAV长度重建160点完整前缀；未导入新分析函数。
1,571项hash、96组trace配对/92,580,480浮点值、96,438帧CSV、160项控制区间和16份首次差字段快照均通过。
8个零参考/16个相同AEC输入控制通过；索引、计数、区间、关系分类核验误差均0。
实际关系0 before、1 same-frame、3 after、4 no-gate-difference、8 no-output-difference。
case7 eligible相同但far/dt联合字段322帧已变，早于AEC327帧；最终文档明确保留该区别。
审计脚本SHA256：`2d5ad653af9d118b7c4da107dd03e036d2ef2fe024f6ca183a32aa2ead530bc6`。
审计回执SHA256：`fb1616dd510d0506c5923310fc7ec008970819b2f6f0b7e72a7d1ad509bf43cf`。

whole-change快照SHA256：`454d7ef4fd9550cb90d4f72dc98f969376c356229625a1aa96043301f557a4a7`。
21项当前字节全部匹配（6仓文件、5工件、7外部脚本/证据、3检查回执），数值和披露一致，无新增实质问题。
review_mode=whole-change；known-finding相对路径已闭合；new_finding_class_count=0；retry_used=1。

## Evidence Index与适用性

工件根`/tmp/audio-fe-device-timing-d20-r1-20261011`。下列命令均有actual回执，不以代码推断运行结果。

| Command | Exit | Evidence path | Layer |
| --- | ---: | --- | --- |
| /tmp cwd device_timing.py --help | 0 | postcheck-0.json | CLI |
| /tmp cwd device_timing.py --dry-run | 0 | postcheck-1.json | 输入/身份 |
| test_device_timing.py，5 tests | 0 | postcheck-2.json | 测量已知答案/负例 |
| docs_consistency.py --self-test | 0 | docs-check-0.json | 文档 |
| docs_consistency.py | 0 | docs-check-1.json | 文档 |
| git diff --check | 0 | docs-check-2.json | 修改格式 |
| 初次/tmp cwd device_timing.py --dry-run | 2 | /tmp/audio-device-d20-portability-failure.json | 保留负结果 |
| independent audit | 0 | /tmp/audio-device-d20-independent-audit.json | 独立全量测量 |

新DSP构建/回放not_applicable，本轮没有DSP改动；继承D19实际build身份并核hash。
配置、ABI、异步生命周期、工具权限、模型/prompt/runtime政策定义、UI、发布与设备操作均未变化，对应回归not_applicable。
Completion Guard必需CLI/identity/measurement/test/docs/review通过，实际Runtime收口回执另存于工件根；
Runtime只证明本地执行符合性，不能代替声学或产品验收。

## Codify Decision与后续

delivery_goal=D20完整时序诊断；reusable_pattern=完整字段区间与谓词分开核，不以总次数解释先后。
affected_asset=研究分析工具/测试/中文入口；promotion_candidate=false；owner_review=产品资格未闭合。
next_task_friction_reduced=下一假设不再把门控差异当全部输出差的必要条件；reduced_by=16例完整时序及独立复算。
reduction_evidence=上述result/独立audit/snapshot；do_not_promote_reason=门控只是一部分条件、没有实际内部更新或声学真值。
rollback_path=仅移除本轮新增研究文件及README对应入口，保留既有dirty和D19冻结工件；不涉及产品DSP回滚。
verification_evidence=21项快照绑定及实际命令/独立审查，Provider仍NEEDS_REVIEW，本文仅仓内reviewing candidate。

后续冻结已知路径/门控控制实验；本轮不批准算法、人声保护、物理因果、AISpeech接入、ASR/KWS、HIL/E001或产品资格。
参考坐标差异先于输出差异仅是时序事实，同帧不能推出子块内更新排序，replay秒数不当PTS。
