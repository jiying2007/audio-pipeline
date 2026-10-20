# D39 原实现语义澄清

2026-10-11，正式矩阵、实现及结果均尚未执行。原PLAN保持，以下是实现前原源码核验引出的契约澄清，不改变测量阈值或因结果调参。

canonical ap_agc_process_controlled 的 allow=0 将 target_gain 限制到<=1，并将实际输出使用的gain限制到<=1；state.gain在低于1时仍可向1增加。因此“AGC禁止增益增长严格检查”指输出effective gain不能超过1，不是gain_after必须<=gain_before。control.csv另记录effective_gain（含limiter约束），与原state float递推和实际逐样本clamp输出分别核验；gain_before/after保持真实，绝不把正常向1恢复报告为失败。allow标志仍为!(far&&!dt)，目标-20dBFS/limiter-2dBFS保持。

D39只消费D30已锁保存输出；完整锁D30的16 source、156 input和655 artifact，不重新递归调用需要raw capture目录的D30 preflight。探索性错误调用把仓库ROOT当capture root，实际exit1 extra/missing input files，未写入任何输出，保留为调用错误而不是源数据漂移。随后完整D30 binding逐项actual核验全部匹配。

PLAN及本澄清共同接受独立审查，PASS后实施；数值失败依原合同replan，不放宽预算、误差、数据角色或声学/产品门槛。
