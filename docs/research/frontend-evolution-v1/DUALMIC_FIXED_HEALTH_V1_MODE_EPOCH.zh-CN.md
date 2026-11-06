# FE-C2-FIXED-DIRECTION-HEALTH-V1：模式计数生命周期

日期：2026-11-06。独立复审提出并复现未完成证据跨模式继承风险；本补充属于原合同的模式生命周期正确性，不增加候选阈值、状态字节或故障类别。

## 修正前实际失败

固定序列：一次健康 tracking 更新使旧 counter=4；一次 fixed hard 观察使 hard_arm_count=1；进入 tracking 健康输入一帧（无 tracking 观察）或四帧（包含一次健康观察）；再回 fixed。同目标和左右目标交换分别执行，覆盖 8k/16k。

原候选的未确认计数会越过 tracking 区间；旧 tracking fallback 在 inactive/non-severe 时直接返回，也不会清掉这个 fixed 待确认计数。确定性测试共3916个检查、24个失败，日志 `evidence/dualmic-fixed-health-v1/candidate-pending-mode-fail.log` 保留。不能把另一模式区间当作固定方向连续有效证据。

## 冻结的最小修正

复用唯一新增的 `uint32_t fixed_health_counter` 编码模式和相位：

- 3：当前不在 fixed 观察 epoch；init/reset 使用此值。
- 4..7：fixed epoch，有效低两位为四帧观察相位；4 为执行观察的帧。
- fixed 内仅在4..7循环，最大加数为7，不存在长时间运行的 uint32 wrap。
- 非3且不在4..7的值不作为历史证据；下一调用重建相应 epoch。该防御只涉及此私有节拍字段，不承诺任意内存损坏恢复。

模式 epoch 切换时清未完成确认和恢复计数，保留已确认 hard 的 active 状态、目标通道、gain和冻结lag。进入 fixed 的首帧观察；返回 tracking 后继续原 counter/search/score 节拍，不将 fixed 相位用于 tracking。始终 track=true 时该字段保持3，旧176B状态和PCM仍须逐字节等于精确base。

新增测试只检查预先固定的一帧/四帧 tracking 间隔、同目标/交换目标、已确认路由保留与异常私有节拍重建。不得改变hard/recovery阈值、增加crossfade或将此修正称为新声学收益。
