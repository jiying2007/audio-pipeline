# D18 独立复审与固定参考诊断收口

日期2026-10-11；experiment=`FE_DEVICE_EXACT_REFERENCE_D18`。
审查者`/root/device_capture_independent_review`；Reviewer Independence=`independent`。
whole-change **Spec PASS、Quality PASS**，未发现可验证blocker/major/其他需修复finding，不保证无未覆盖缺陷。
PASS只支持诊断执行、测量与披露，result=`EXACT_REFERENCE_DIAGNOSTIC_NO_PROMOTION`。
没有算法候选、20点物理最优或声学/产品批准；总体优化目标继续active，仅D18里程碑收口。

## 原始证据与独立审计

审查覆盖[计划](DEVICE_EXACT_REFERENCE_D18_PLAN.zh-CN.md)、[执行前澄清](DEVICE_EXACT_REFERENCE_D18_AMENDMENT.zh-CN.md)、
[结果](DEVICE_EXACT_REFERENCE_D18_RESULT.zh-CN.md)、README、runner与工具。
快照`/tmp/audio-fe-device-exact-reference-d18-20261011/review-snapshot-v1.json`：
SHA256=`3d1499e6d8ba8feafc0aa58d5e5ddad06d35c5187c81302b2f0a3cfc64515af4`。
6文件/6工件/2脚本/3检查共17项当前bytehash匹配；本文后写、由Runtime单独绑定，不改冻结对象。

独立工件审计已实际输出INDEPENDENT_D18_AUDIT_PASS：1312项绑定hash及原119输入锁hash匹配。
临时source唯一差异是get_reference定义名，原函数体、其他受锁源码和generated header保持一致。
审查者用stdlib WAV/S16LE/Float32LE独立读取，不调用新测量工具自证：

| 对象 | 独立实际核验 |
| --- | --- |
| 输入/配置 | 16场景mic/raw与原D16 adapted一致，used等原WAV及raw20；两臂仅initial配置不同 |
| reference | 32条、15,430,080个Float32样本逐字节等raw16/used20；启动零及160截尾明确 |
| JSONL | 96,438帧连续、固定delay、jump/slips/reset全0，tracking/drift关闭 |
| 原fixed1 | 10场景PCM/JSONL与原D16逐字节相同 |
| 零参考控制 | 8场景PCM相同，原JSONL仅estimated_delay_ms不同 |
| 原库no-observer | 4次完整PCM/JSONL与observe相同；不外推所有配置的观测中立 |
| 能量测量 | 128组RMS（32whole+96窗口）独立复算最大误差0；全部PCM mismatch计数一致 |
| known answers | 两实际回执各3200样本PASS |

QUESTION-1闭合：原JSONL未输出SDK render_underruns，范围显式限定；
SDK fixed1首帧欠历史计数1、used0计数0逐帧实际断言并保留终态，不清零/隐藏。
observer在真实get_reference返回后立即读out，规避process后共享union覆盖；调用数/固定delay/drift0均断言。
声明配置与实际reference分别核验，原库/测量库身份分离；不称测量库是shipping制品。

whole-change复核8个非零参考场景表中32个RMS差值与工件一致，均正数，未升级为质量排序。
非仓库cwd help/dry-run exit0；plain有效参数带trace模式exit2且三个denied文件不存在；
工具existing输出拒绝exit2；文档自测/一致性/git diff --check回执exit0。

## 完成声明、复用及剩余资格

completion_claim=固定坐标36次回放及独立诊断审查完成；claimant=root；verifier=上述独立审查者。
primary_skill=adk-planning-execution-loop；完成验证=adk-verification-before-completion。
review_mode=whole-change；finding_classes=[]；new_finding_class_count=0；reopened=0；
consecutive_clean_reviews=1（最终整项）；执行前QUESTION澄清不属于测量结果后改验收。
算法、API、产品生命周期、权限、runtime资产/模型未修改；相应域门禁不适用，不借此推导领域PASS。
研究C构建通过；无目标板CPU/p99/热/功耗、HIL或主观音质结果。

reusable_pattern=在union复用前抓取实际消费reference，以真实trace和原库等价双重验证观测。
promotion_candidate=false；next_task_friction_reduced=true；
reduced_by=固定原捕获坐标并确认4点差异对同DSP的实际影响；
reduction_evidence=32reference逐float、10旧控制、8零参考及4原库复跑。
do_not_promote_reason=无独立声学/物理真值或算法候选；owner_review=产品资格仍待。
rollback_path=研究工具/runner未安装，停止调用即可；保留原失败/dirty/产品src。
verification_evidence=result/binding/command/postcheck回执、快照与独立审计。

used0内部附加delay0不等于物理0；20点不是声学最优，能量更高不能证明人声保留或残回增加。
下一轮完整同状态AEC残差/回声估计与后处理观测仍须独立冻结，不将分stage重跑结果线性相加归因。
D11/D14/D16拒绝不变。无commit/push/设备写；Provider unresolved知识线NEEDS_REVIEW、未正式归档。
tmp恢复须先核hash；真人标签、下游ASR/KWS、物理校准、目标板资源/HIL/E001、owner/shipping未闭合。
阶段Runtime只本地conformance，不关闭总体目标或授予产品资格。
