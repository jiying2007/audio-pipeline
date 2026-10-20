# D30 独立审查与复验记录

日期2026-10-11；experiment=FE_DEVICE_ACTIVITY_D30；claimant=root；verifier=device_capture_independent_review。
primary=adk-planning-execution-loop；supporting=adk-verification-before-completion。
结论：Spec PASS、Quality PASS；Reviewer Independence=independent；未闭合finding=0。
范围是实际Activity集成、测量与负结果披露；promotion_allowed=false、shipping_approved=false，总体native goal仍active。

## 冻结与实施审查

PLAN SHA256=372dd673052334465fabe3e435499d011197b323646bb09d479de9df238071bc。
AMEND SHA256=cc7d069eca696555dbf923f117433b9e71616ef0c26ae30c1070def97ceecafb，原PLAN字节保留。
计划独立审查确认原Activity只使用本帧mic/ref能量，先Activity再AEC，没有selected反馈；参数与Float32运算顺序冻结。
最终执行前fresh实现审查绑定tool SHA256=0c88ff191e1b43dfd2f746f7a8b2ee7439f3f4bb85d3a7dd3f6757bef0111875。
C SHA256=206a44230f84b66ff1167143ef4457fdfc0408f52e993774226f56a0a6715e58；tests SHA256=5da1c18019724f7d375dccb0207ddcf562d3fbb1b7053629ea4dc4f32b4c6dde。
原库SHA256=eb5b0c784c316e71d6ed9f58db6cb66f190b631daa00c55a94032168d5a47aa4，源/头/flags/库均起止锁定，不重编DSP库。

预编译第0次真实exit1，D29内部main宏与外层重命名冲突；原失败writer、回执和可还原原源码base64/hash快照保留。
原失败回执SHA256=b2061a33c1d477c1988c1c816dc47f70984bbc28c464c623e12f55011d9b516b；原源码快照SHA256=67cb91a32a1ca25ff403c990530cbfd3f62dade6deb987fab91d2629de93c2e9。
修复仅新D30包含方式及显式组合自测，主处理函数与首次版本字节相同；旧依赖及严格警告不改。
第1次严格编译、actual Activity自测及4项Python tests exit0；预编译retry1，主DSP重跑0，不称整轮零失败。

## 实际回放与独立验证

46次主C回放真实terminal exit0；argc和4个完整非法参数拒绝、12输出sentinel保持及AEC/Activity零调用符合合同。
非仓help/dry-run/4tests全部terminal exit0，dry-run不创建根。
result/binding SHA256=e0b74142093d4579615be9ffe047335b4618f46aa1116f0b24941bb921de470d / 2558d74e0e8377087bcb1a44fc3e13d890c4da9b641b579db9d670e207083956。
独立audit/negative均首执行terminal exit0、retry0；不导入新测量器、不执行C/AEC/Activity。
独立核46case/368trace/161,902,080个Float32，四CSV各126,486行，7,702次hash检查。
34field执行的374原文件全byteeqD29，102,486field帧门控一致；return far差0/dt差1,600（4例×400）。
Activity能量/EMA/迟滞/instant ratio/hangover全部独立Float32递推，误差0；selector和mix按实际gate/bank核验。
476原窗=本轮240+D29对照236；1,133有效channel/295null；240delta包含repeat4窗、108known-near delta，RMS/peak/delta误差0。
mic代数max2.2351741790771484e-08；actual primary/Activity/selector/transition各126486、shadow44564/reset30/mixed89920/events281/sync0。
repeat/future各13事件；repeat12输出全量同，future通知前12输出前缀同、整段Activity同；不评分future。
六工具负例均exit2，旧D29675/新D30659文件完整manifest起止同，仓仅工具潜在回执路径0文件，不锁全dirty。

audit脚本/回执SHA256=6c5b317a872ed100d27e454639a47a353e2ddd6f04fd6c420e11f0ce378fad3d / 9daf5ad297eefb83616f0e21937f6f3cfa261d789c6228abde189e4ceb9160d7。
negative脚本/回执SHA256=5d2d1a91d20d217f1bdc335e4c332b2b41460e69ecb9ee4821dce786a353e717 / 8829a32e5bec93324a197fa60600c8c856bd9a7db3964badc26ce700c1149774。

## Whole-change及派生解释核验

whole-change快照`/tmp/audio-fe-device-activity-d30-20261011/review-snapshot-v1.json` SHA256=ada1d489bc5e5f5b6377bbba5d830d38eba3fa6f4a7c52eb34d9f57ccbb423ac。
独立fresh review全部49项起止字节一致：13仓文件、5工件、28外部脚本/回执/依赖、3checks；655生成工件一致。
三个docs checks和help/dry-run/4tests回执均0；未发现可信blocker/major/minor。
return确为8例原11文件全同、4例仅mic/ref同、9文件改变；96文件等价/36改变，文档没有扩大为原bank普遍等价。
派生gate诊断脚本/JSON及输入hash核验；4例oracle区间[1000,1200)、[1600,1800)、实际dt全0/far全1及能量比/原阈值全部独立重建一致。
派生36窗口的原绝对error、delta和从near trace重建的near_present全部核验；不是新增裁判或选型。
whole改善与后期退化分别披露：最大+50.95106431158375dB在ABA-r20 dt 16–18s合成near-present窗，原error-92.70297756449978→实际-41.751913252916026dBFS。
18–20s为near-absent，不能把全部增量都称发生在人声期间；最大差值不是-240dB统计floor裁切，不推真人损害。
单路双状态、shadow通知≠公共pipeline路径通知、primary CSV非完整状态、局部资源及B0超限均准确。
REVIEW字节由finalcheck-0/1绑定；docs/git diff终态及独立追加复验在本轮收口时核验。
Runtime evidence/artifact/progress/checkpoint/heartbeat/final只闭合本地D30里程碑，不表示总体完成或产品放行。

## 复用、回退与后续资格

reusable_pattern=实际门控与oracle对照分离，以字段/控制/输出逐byte验证设备集成，再保留合成失配的原窗口与绝对误差。
promotion_candidate=false；do_not_promote_reason=真实near检测/独立声学/完整链/目标资源未合格，合成门控保护缺口已出现。
next_task_friction_reduced=无需再猜门控是否来自标签，已有实际Float32状态、输入ratio和精确near时间窗。
reduced_by=46实际执行+独立递推+派生36窗口解释；reduction_evidence=本轮result/binding/audit/gate-diagnostic及快照。
owner_review=未形成产品owner批准；rollback_path=停用D30研究入口，保留D29原代码/库/工件及用户dirty，无公共API/default变更。
verification_evidence=上述冻结合同、主回放、定向正负测试、独立审计及whole-change；听感/真人/KWS证据未提供，不以工程指标替代。
Activity28B，局部71,224B；两AEC66,040B自身超B0 50,000B，未改变B0预算或批准SSC305部署。
后续冻结可辨识near观测与完整前后处理假设，不直接扫本轮输入上的阈值；AISpeech产品链、API/default、owner/E001/PQ分别未闭合。
Provider route unresolved/current为空，知识线NEEDS_REVIEW；仓内reviewing candidate，没有正式归档。
原D0-D29及用户dirty保留，无commit/push/PR/merge/发布/设备写；总体native goal保持active。
