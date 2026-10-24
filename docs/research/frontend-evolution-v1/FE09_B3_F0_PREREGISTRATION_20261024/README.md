# B3-F0：已冻结的四麦16k Render缺席／重入组合

身份：`FE09-B3-F0-C4-16K-RENDER-PAP-V1`；有限叶任务 [#837](https://github.com/jiying2007/audio-pipeline/issues/837)，父任务 #733／#657。

本目录的 `registration.json`、`test-contract.json` 和 `source-lock.json` 已由 root 在独立审查后冻结。`FREEZE.json` 记录原始审查字节、当前冻结文件及真实基线门禁。两个 `REVIEWED_DRAFT_` 文档保留审查时的原文身份，其 DRAFT 标记属于历史快照；实际冻结状态由本页与 `FREEZE.json` 确定。

冻结仅批准此有限合同下的实现与执行准备，不是实验通过或功能、声学、产品资格的证据。原始77项依赖不变；新实现和二进制必须另行绑定实际source/config/compiler/hash。

## 范围与基线

仅 C4-ULA、16k、600帧 ALL_P 与 PAP 两条固定D0轨迹。PAP在201–240帧缺少来源方Render投递，Capture保持连续；201／241帧的真实通知重置整个mono链。外置Capture SRC/FIR33保持，actual Activity控制现有AEC、frequency RES、AGC、VAD。

冻结基线 `81ee559848e1e30e3dd2eb4d03b0b479b9bd971e` 的 Verify40050719866 attempt1、required summary120750243248／App15368，以及 Release40053218180 attempt1 的 release120750280371／convergence120750333701均已实际成功。Release中的严格治理审计返回PASS。旧不可变软件发布仍为v2.3.56@c416a5f8…；没有产生新软件版本。

执行前仍须读取当前protected base和完整原件身份。基线若变化，必须新增明确迁移证据及新基线本身的实际门禁，不改写本冻结快照，也不继承旧绿灯。

## 验收和停止

完整资格为native、ASan/UBSan、AArch32/QEMU三目标；每次19800组合帧，另列5次producer publication/目标的负控setup。真实调用观察、独立直接控制回放、plain/observed透明性、固定未来前缀与16项API拒绝／8项receipt语义负控均须按合同执行。

完整资格通过要求全部固定条件成立。源码、事件、原子性、身份、目标、观察或等价失败均不能输出成功资格；固定分支未触达必须记INCONCLUSIVE。本地部分目标结果明确为部分执行，不替代完整PR或新main资格。失败先保存，禁止改输入／门控／超时／验收取得通过。

追加阶段最多300秒并服从原frontend-reference15分钟job剩余预算，预留60秒归档；observerRAM最多256KiB。182samples／11.375ms只是一项算法延迟账本。完整B3、T3-S3全进程资源、声学独立确认、公开C4SDK、物理时钟、HIL／E001和shipping分别验收。
