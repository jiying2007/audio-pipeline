# D28 执行前边界补充

日期2026-10-11；原PLAN b0e8712b1da8a21ca24f943c7fc99b8f61aca719f70cbe0b1855b9b8701ead29原字节保留；尚未编译或执行新C。
QUESTION-1：原计划未明确一阶差分平方和及附加跳变所用输出channel；执行前固定，不能按结果挑channel。
候选合并平方和仅使用selected residual（AEC单体音频输出），将全部主设备事件逐事件值以math.fsum合并；echo通道同样记录，仅诊断，不参与这个候选条件。
起点附加跳变<=1e-8分别检查selected echo与residual两条输出，全部主设备及D25事件逐一验；端点和过渡外byteeq也分别检查两输出。
各事件两通道hard/fade实际相邻差及区间平方和均保留，不将起点注入为0扩大为整段导数减少或听感改善。

EOS不补样本或截掉输出：C写满原N样本，回执报告remaining；若事件start+320>N，end_sample=min(start+319,N-1)，censored=true。
指标按两模式相同的可用区间计算，未完成端点不制造新bank端点；逐样本递推仍必须正确，样本数/whole/固定窗不变。
候选另要求全部主事件censored=false；任何未完成过渡直接TRANSITION_DEVELOPMENT_REJECTED，保留有效测量，不把终止边界问题掩盖为音质通过。
重复/future控制也按原样本数终止并记录remaining，future仍不计候选和原mic代数/评分。
这只补全原计划通道和尾部契约，不改20ms、D27控制、0.5dB、固定窗口或已有声学边界。
