# D45 合成频谱增益保护独立计划审查

2026-10-11，experiment=FE_DEVICE_POST_NS_PROTECTION_D45。claimant=root，verifier=device_capture_independent_review，Reviewer Independence=independent。冻结PLAN SHA256=`15e94e9f589aa6ceb9933f8193cbbf4b10bbfc34d57bf05c794c6213fd2c24ce`，独立审查起止一致。Spec PASS / Quality PASS / unresolved=0，允许登记新实验并进入实施，不批准候选效果或正式矩阵。

## 预假设证据实际核验

独立只读复核D44的960组已有统计：567组NS/final阶段统计相同；全部216组合成candidate的NS/final配对变化字段相同。对应24个candidate-return执行的NS/final文件逐字节相同；48000帧control中gain_before/gain_after/effective_gain均为1，72项相关工件哈希与binding相同。旧源码确实先抬RES target、平滑后再乘ordinary NS gain。未执行DSP或计算新候选评分。

因此已有合成输出的代价发生在AGC之前，可以提出保护位置的新假设；不能证明ordinary NS因子是唯一根因，也不能保证新映射获益。D39既有同类观察和D44拒绝保持，不改旧裁判或失败。

## 因果、测量与边界审查

同一D44 floor从RES target移到合成gain之后，是一套完整因果修改。固定2.0/q/EMA/旧N/far/dt/noise tracker/FFT/AGC/VAD保持，不做系数搜索或新增迟滞。风险明确：扩大噪声/非线性echo、频点切换及无near能量。

旧would_raise_bins仍是floor与原RES target比较，新增post_would_raise_bins与combined_gain_before比较；power18列、bins25列及updated_noise/combined_before/after可区分原RES状态与新应用位置。observer为诊断，不反馈算法，不修改原波形评分/准入。原monitor四输出、candidate bypass、mode投影和repeat/future合同可执行；184次505944帧及960组新波形评分须重新实际执行并独立审计。

两臂各24near/72no-near/4pure-echo whole，原-3 dB/至少18改善/+1 dB准入不变；数值宽度/舍入/严格零/原容差、实际sizeof和目录预算保持。测量或身份失败独立标记、不改限或删证据；候选失败保存并停止映射参数搜索。

固定快照算术与全帧schema检查明确；完整FFT、非快照逐bin、完整EMA/noise历史未独立重建。development/合成near已查看，field近端真值未知，future不评分，repeat非独立样本。AISpeech产品链路、真人效果、目标板与HIL/PQ和shipping授权不由该计划通过推导。

## 执行准入与接力

本次计划审查不等于源码/控制/数值审查。新task/attestation、实现及定向验证、fresh实施审查、来源冻结、唯一正式矩阵、独立全量核验、whole review与本地收口必须按顺序取得真实证据。unknown先对账，不重发；范围/合同变更先AMENDMENT和独立复审。

D45尚未实现或正式执行。总体native优化目标active、无token上限；Provider知识NEEDS_REVIEW，未归档或活动持久化成功。无commit/push/PR/merge/release/设备写，既有dirty和D0–D44证据保留。
