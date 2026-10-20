# D45 本地收口控制修订

2026-10-12。修订仅涉及未执行的本地Runtime收口控制与退出码文案，不改D45算法、测量、数据角色、准入、超时或已冻结历史证据。

独立整批审查MAJOR-1：closeout-v1先要求device-d45-result已登记为RESULT SHA698d52d7098b9e37ad50783795a40f956f03e96d3cc37f715c4f2e3b9af89154，又试图以同一证据ID登记snapshot摘要。Runtime证据ID不可改digest，故该操作不成立。v1两个脚本原字节保留且未执行，没有运行时失败副作用；禁止执行旧closeout-v1。

v2保留device-d45-result及required evidence指向原RESULT；为快照新增device-d45-result-snapshot-v1，repo artifact引用这个新ID。核新ID与build ID不存在后才发送排他12项收口操作；verify/finalcheck/closeout回执换用v2命名，snapshot仍为尚未创建的review-snapshot-v1.json。固定当前thread/task、CP4、计划/RESULT/review pins、audit PASS、negative保留及fresh maintenance.required=false要求保持。只完成本D45 local Runtime milestone，不调用总体native goal完成、不外部发布。

closeout-v2 `/tmp/audio-device-d45-closeout-v2.py` SHA256=`ec956fc26e47a4dc84f64e527ec9eaf0bdc4775632c90b3dd9977a09f9d167c4`。freeze-v2将v1/v2控制及本修订一并纳入新快照；其最终SHA由独立复审与真实回执证明。尚未执行，必须独立复审PASS后依次freeze、verify、closeout；任何未知先对账，不重放。

MINOR-2：REVIEW原称14项定向operation均exit0，实际父控制exit0，14子记录符合各自expected，其中7项拒绝负例exit2/4。已澄清REVIEW；targeted回执及原IMPLEMENTATION保持字节，不重跑。这是文案真实性修正，不改变已通过的负例判据。
