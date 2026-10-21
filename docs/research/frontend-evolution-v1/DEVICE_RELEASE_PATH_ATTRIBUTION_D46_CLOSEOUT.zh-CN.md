# D46 实际收口与下一机制实验边界

2026-10-13。本轮 FE_DEVICE_RELEASE_PATH_ATTRIBUTION_D46 为测量归因阶段，唯一正式测量、首次独立全量复算、根保护负例、整批审查、最终快照和本地执行收口均有实际终态。总体“全面推进优化迭代”目标保持 active，D45候选拒绝不改。

[RESULT](DEVICE_RELEASE_PATH_ATTRIBUTION_D46_RESULT.zh-CN.md)保存正式测量时点，[REVIEW](DEVICE_RELEASE_PATH_ATTRIBUTION_D46_REVIEW.zh-CN.md)追加后续独立审计及整批签署。24配对、168固定段、336分段stage及48 whole统计独立匹配，最大数值绝对误差0；没有重新执行DSP。测量数据角色为development-and-synthetic-engineering，不是新增独立真人采集。

## 已执行冻结与检查

最终签署REVIEW SHA256=`892c86006bdc8fd4403b28e37df81ed7e2767a26ffad336166f60225091bd8d6`。唯一freeze实际exit0，快照 `/tmp/audio-device-d46-review-snapshot-v1.json` SHA256=`74ad422a054e9ba245025b1b59dfecd9560bfb85893d29090f5934deb48b568b`，247项文件全部经独立当前字节回读。whole原231项锁保持；原199历史输入通过198项其余当前输入与唯一旧README完整备份保留，新README另行锁定，规则见[历史输入修订](DEVICE_RELEASE_PATH_ATTRIBUTION_D46_AMENDMENT_README.zh-CN.md)。不声称旧199路径或旧47快照全部仍为当前工作树字节。

唯一verify session25411 terminal exit0，两项子命令均exit0：documentation consistency: PASS、git diff --check无错误。两份receipt SHA分别为`31c0afeb9b978e6425a9464c11ff8cacb30257cbbc6437271c20346d018cc1a6`和`9b56b34792eb67c9e9cb291a8e071fbb34a97d8c7f6438a3330b868850c482e6`，绑定最终快照、签署REVIEW和发送前intent。独立执行前回读Spec/Quality/Reviewer Independence PASS、unresolved0后才执行收口。

## 本地真实终态

已审closeout-v1 SHA256=`01f1df2696dfbb3d3189888667e6b059dcf7fc4b6346581767d3e753adaddfdb`，唯一session25774 terminal exit0，12项操作全部exit0；每项有排他发送前intent与结果receipt，无重放。Runtime本地task-f972a6cb6470af7431f4e9e1于2026-10-13T02:01:27.068156Z completed/open0/progress5/CP5 verified/events752。required旧RESULT evidence ID仍绑定698cdc5f原摘要；新repo artifact单独使用device-d46-result-snapshot-v1，不覆盖原身份。build artifact仅指宿主测量bundle与binding，不是目标板编译或性能验收。

final gate实际status=pass、completion_allowed=true、missing evidence/artifact为空。final receipt SHA256=`dfb5ef514f93c3e6ef78ce794f611ad55604f7280680d68a412bbf6c87b6be18`；最后state receipt SHA256=`ca493331cf6baba30f668e4b9706fdf6140f3cb83aea89fb695ec70dc88b541d`。该门禁仅证明本地运行规范与本轮诊断任务收口，不批准产品或总体研究完成。本文件在冻结之后新增，属于终态记录，不反向纳入已冻结247项快照；后续文档检查和独立终态回读另按实际结果报告。

## 后续方向与产品边界

纯echo ABA回A后较长区间仍有保护差异，不能只把失败归给near结束后短尾，也没有证明唯一根因。下一机制实验须先冻结新身份、精确基线、可证伪假设、数据角色、资源预算及独立原准入，同时检验路径失配误保护与释放代价；不继续搜索同一映射的系数，不用测量合同调整替算法批准。

2026-10-13重新只读核远端main为`6fcb74f5f498dc68fab6127d8bf9bf35411f7d61`，required summary成功；open PR为714/695，#657仍OPEN、updated2026-10-12T12:11:42Z。本地研究仍使用冻结基线，不用远端CI证明D46或目标板效果。后续阶段须重新核当前远端与本地边界，不能沿用旧main状态。

measurement_only=true、algorithm_changed=false、promotion_allowed=false、shipping_approved=false。真人声学、AISpeech整链、目标板资源/热/功耗、HIL/E001/至少72小时Product Certification仍按各自真实证据验收。Provider route unresolved/NEEDS_REVIEW，本地/tmp实验保存不等于耐久归档成功。没有commit/push/PR/merge/release或设备写。
