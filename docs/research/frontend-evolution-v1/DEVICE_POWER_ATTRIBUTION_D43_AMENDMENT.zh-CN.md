# D43 功率汇总与数值合同澄清

2026-10-11，experiment=FE_DEVICE_POWER_ATTRIBUTION_D43。原PLAN SHA256=`67cc799ccfc9d012694c717a1e96b66643d457be90840ecbb70b89b47b0288e1`保持。首次独立计划审查为NEEDS_CLARIFICATION，QUESTION-1/unresolved1：过去EMA与当前FFT同时捕获，但三个sum的被加数和多bin累加/独立误差规则未定义。本修订只澄清测量合同，尚未实施、编译或执行；原算法/门槛/D42拒绝不变。

## 过去功率字段与精确汇总顺序

仅在frequency_active且旧count>=10、旧E>1e-12、旧R>1e-12且floor函数valid=1的bin集合V上汇总；inactive/warmup/低功率bin不贡献这些统计。所有有效旧E/R/Cr/Ci和原旧N以及中间量必须finite，N非负；失败拒绝。noise_sum即使N超过R也不能截断。字段明确如下：

| 字段 | 每bin被加数/最终定义 |
| --- | --- |
| echo_sum | 旧binary64 EMA E |
| residual_sum | 旧binary64 EMA R |
| noise_sum | 原NS上一帧binary32 estimate[k]恢复double的N |
| innovation_sum | R*(1-q)，q=clamp((Cr*Cr+Ci*Ci)/(E*R),0,1) |
| excess_sum | R*max(raw_fraction,0)，raw_fraction=(1-q)-(N/R) |
| floor2_residual_sum | ((double)actual_floor*(double)actual_floor)*R |
| q_mean | sum(q)/len(V)，V空则0 |
| noise_dominant_bins | V中raw_fraction<=0的bin数量 |
| positive_floor_bins | V中实际binary32 floor>0的bin数量 |
| would_raise_bins | V中实际floor>original_target的bin数量，两模式均观测 |
| raised_bins | D42guard实际raised_bins，monitor为0 |
| floor_mean | D42guard实际全部257bin floor顺序累加/257，不新算或换算法 |

echo_sum/residual_sum绝不是当前FFT echo_power/power之和。当前FFT复数值及power/echo_power只在bins.csv记录，用于核原target和解释不同阶段，不混入上述过去功率汇总。旧N与R时间统计不同，数值相减不保证物理来源分离。

C测量汇总使用从k=0到256的普通binary64左折叠相加，初始+0.0；各被加数按表中括号和运算顺序计算，q的四乘加及分母、fraction两步减法不合并，保持ffp-contract=off。没有Kahan、fsum或重排累加。所有整数计数exact；全部和/V空的均值为0，拒绝非有限和或越界计数。测试要求sizeof(float)=4、FLT_MANT_DIG=24，sizeof(double)=8、DBL_MANT_DIG=53且FLT_EVAL_METHOD=0；仅限定本次实际编译宿主，不外推目标板。

## 独立复算合同

bins.csv double用17有效数字、float用9有效数字，独立按原binary64/binary32往返读取。固定选定帧的全部257bin旧状态只是实际快照，未独立重建历史EMA/FFT/噪声tracker，不改变覆盖边界。

独立实现按已保存旧E/R/Cr/Ci/N和count/active分支计算q/fraction，固定系统libm sqrt后转binary32，floor/valid必须bit exact。original_target使用已保存current power和echo_power、FULL beta=1.4f/res_floor=.10f、每一步binary32加乘除以及系统sqrtf、原clamp；applied_target按monitor/candidate分支bit exact。active实际res_gain用已保存old_gain、原target<old分支、.55f/.45f或.92f/.08f的binary32乘加、ffp-contract=off，要求bit exact。inactive保护/target/gain测量字段为0，不称原NS实际输出gain为0；当前FFT不独立重算。

独立快照汇总可使用math.fsum以不同累加实现复核，每个binary64汇总字段与C输出满足abs_error<=max(1e-24,1e-12*abs(expected))；expected为0时要求actual也严格0。所有计数与状态/集合/行数exact。floor_mean额外必须与同名D42保护trace的binary64值exact，不用该容差放宽原五输出byteexact。per-bin floor/target/gain的binary32 bit exact不能用汇总容差豁免。

该容差只覆盖不同合法binary64累加次序产生的数值差，不是声学准入预算；不修改D42 RMS1e-10 dB、1 dB/-3 dB或任何产品门槛。未选定帧的汇总只核范围、状态、模式/重复/future一致性和文件身份，不声称具有所有bin输入独立复算资格。

QUESTION-1待独立复审；reviewer通过前不登记计划PASS或实施。本地注册/checkpoint控制已独立静态审查通过但未执行，PLAN_REVIEW需原question和修订闭合事实。总体native目标active；无commit/push/PR/merge/release/设备写。
