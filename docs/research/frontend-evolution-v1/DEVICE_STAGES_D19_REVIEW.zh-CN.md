# D19 独立审查记录

日期2026-10-11；claimant=root；verifier=device_capture_independent_review；Reviewer Independence=independent。
最终Spec PASS、Quality PASS、未解决finding=0；仅支持D19诊断里程碑收口，总体native goal仍active。

## 分阶段独立性与修复

冻结计划已由独立审查核验真实CALL调用链、即时缓冲观测、0/160点固定窗口和D18等价控制，Spec/Quality PASS。
实现首次审查发现MAJOR-1：创建前拒绝路径仍可能向已有输出目录写失败回执，Spec/Quality FAIL。
修复为本次mkdir成功后登记归属，只有本次归属根内允许保存失败回执。
独立审查实际执行6个拒绝负例（missing/真实capture根×既有D18/初次D19/仓根），均exit2且无工具写入。
D18的1,205项和初次D19的983项完整路径/hash前后相同，仓根受影响路径不存在，MAJOR-1闭合。
首次runner严格编译失败单独保留；修正版使用实际冻结库的内部编译宏，未改函数体或门限。

## 工件审计与最终快照

独立脚本直接读取实际Float32LE、CSV、原events/frames和绑定，以整数有理运算重新计算PTS窗口，未调用本工具统计代码。
1,561项hash、59项源码仅4定义名变更、生成头/宏/链接符号均核验通过。
160条trace、77,150,400点全有限；96,438帧CSV完整且控制与公共指标对齐。
96份PCM/JSONL/reference全部逐字节等D18，8个零参考场景全部阶段相同。
640组RMS/peak、320个两臂差、128个AGC前后差复算最大误差均0。
AEC代数误差最大`1.4901161193847656e-08`，满足冻结`≤1e-6`。

审计脚本SHA256：`2841daaeaff30ebfc6dedf9f53ef465b87830af5af2601e7d27e33c69b263300`。
审计回执SHA256：`50a4720dfd0206e80f0977c5ae81a68c87358fde13545eb9891bde5e04576fc3`。
最终`review-snapshot-v1.json` SHA256：`f3924ef544835a63a393c905d480c9d5526c31f1e37359c018d5478ae0d5d65a`。
独立whole-change复审21项绑定全部匹配：7仓内文件、5工件、6脚本/外部证据条目、3检查回执。
PLAN/AMENDMENT/RESULT/README/tool/runner/test的数值、坐标、失败记录和资格边界一致，未发现新实质finding。
非仓cwd help/dry-run、3项测量测试、docs self-test/实际检查与git diff检查均有新鲜exit0回执。

## 审查声明边界

支持[D19结果](DEVICE_STAGES_D19_RESULT.zh-CN.md)关于差异起始于AEC输出、NS联合阶段扩大整段差距、AGC收窄差距的工程诊断。
不把echo estimate称真实回声分量，不拆出RES-only，不批准音质、历史候选、AISpeech接入、设备/HIL/E001或产品资格。
Runtime收口回执单列保存于修正版工件根，属于本地执行符合性；不能代替域验证。
Provider仍NEEDS_REVIEW；本记录为仓内reviewing candidate，没有正式归档成功声明。
