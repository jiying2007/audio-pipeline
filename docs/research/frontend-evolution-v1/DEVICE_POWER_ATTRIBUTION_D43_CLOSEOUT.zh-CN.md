# D43 功率诊断本地收口

2026-10-11，experiment=FE_DEVICE_POWER_ATTRIBUTION_D43。本诊断实际闭环：正式测量、根保护负例、独立数值及全窗口描述审计、整批源码/文档审查、冻结和本地最终门禁完成。decision=POWER_ATTRIBUTION_DIAGNOSTIC_NO_PROMOTION，promotion_allowed=false、shipping_approved=false。总体 native 目标“全面推进优化迭代”仍 active，无 token 上限；这里只完成 D43 诊断里程碑。

## 实际终态与冻结身份

正式 184 次 / 505944 帧，原五输出与 D42 byteexact；独立审计 1944976 bin 行及全 960 组描述通过，细节和覆盖边界见 [RESULT](DEVICE_POWER_ATTRIBUTION_D43_RESULT.zh-CN.md) 与 [REVIEW](DEVICE_POWER_ATTRIBUTION_D43_REVIEW.zh-CN.md)。D42 拒绝保持。

38 项源码、计划、文档、控制及实测回执冻结在 `/tmp/audio-device-d43-review-snapshot-v1.json`，SHA256=`b00d2bbb92e733dda91c0440b96269ab1d14c4096d50cdcb45ca069a91f878b3`。最终 REVIEW SHA256=`c438b001741afbf8d7d3a817dd3676498a42a1ab2c1bc4c3adee9b8c165cd14e`；独立最终读回确认全部 38 项起止一致，Spec PASS / Quality PASS / Reviewer Independence PASS，unresolved=0，放行唯一一次本地收口。

绑定快照与 REVIEW 的双 verify session 28902 terminal exit 0，两操作实际为 docs consistency PASS / git diff --check 0；回执 SHA256 分别 `42da051f0747c16e1f9c6f27625f15e6402bcb480c0db9c720e6ca7569485b59` / `2182c2a40d97865afc54aea4cdd4dd9b4a692393d3c010d62fa7f7ad257068b6`，intent/writer/snapshot/review 绑定完整。

唯一 closeout session 15861 terminal exit 0，13 个实际记账操作全部 exit 0，所有 intent/receipt 绑定读回一致。固定本地任务 `task-849c8fe1606259906ad1bde3` completed / open_items=0 / progress5 / checkpoint5 verified；final gate 实际 2026-10-11T11:59:11.367448Z status=pass，missing_evidence=[]，maintenance.required=false。

最终 gate 回执 `/tmp/audio-device-d43-closeout-v1-11.json` SHA256=`bcd39113f01c967ecea11b989a7e0e06abfee65d29cb706017ac4532c7a0817f`；最终本地状态回执 `...-12.json` SHA256=`8b909195eb5b1e94534d0167a62403dc886d4ac48dacc311991756d3b9b18b2b`。这只证明 Codex Runtime 本地 conformance；声学和产品资格由各自验收证据决定。

本文件在上述快照及收口之后追加，故不在该 38 项历史快照内；不会改写冻结 REVIEW/IMPLEMENTATION、旧 snapshot 或正式 result/binding。

## 下一轮优化的输入与约束

本轮最坏近端后窗口已有约 62.9% 有效 bin 被旧噪声约束为 floor=0，却仍有约 33.5% 抬升 target。全 near 后固定窗中旧总 N/R 中位接近 1，逐 bin excess 仍非零；不能以总量比值作消除逐频点保护的依据。下一轮应先区分旧统计时间尺度、逐频点截断和保护恢复过程的贡献，再冻结一个单一因果修改的新实验身份。

下一轮必须同时保留原 near -3 dB 与 no-near +1 dB 准入，不放宽门槛，不以 D43 描述自批准新算法，不以离线 near 标签驱动 DSP；沿用独立开发/合成数据角色、重复/future 控制、来源锁和独立审计。该后续假设尚未冻结或执行，不能声称新候选通过。

AISpeech 固定点/QIVW 产品链路、真人效果、目标板资源与 HIL/E001/PQ 仍分开验收；未新增产品准入。Provider route unresolved，知识 NEEDS_REVIEW，未声明归档成功。原维护 accepted/completion-unverified 保留，不推断本次自动压缩与请求的因果归属。无 commit/push/PR/merge/release/设备写。
