# D40 计划独立审查及实施入口

2026-10-11，FE_DEVICE_FREQUENCY_ABLATION_D40。Reviewer=device_capture_independent_review；Spec PASS / Quality PASS，Reviewer Independence=independent，unresolved=0。计划SHA256=1e7046fb8fe6e326c523e4b400000d5c0d7d27f82ca3bc0847f6ab99a9fb6bdd，可进入实现阶段；本文件不代表实现、DSP执行、数值结果或Runtime登记完成。

独立只读核原ap_ns.c：noise tracker使用抑制前残差FFT power，频域RES gain随后作用于spectrum。因此普通NS speech_probability与noise_rms_dbfs逐帧恢复float32 exact对照有源码依据，仍须真实执行验证；不能将依据替代已知答案结果。

唯一变化所有帧enable_frequency_res1→0；原Activity gates、配对echo/residual、普通NS floor、FULL模式、AGC/VAD与状态生命周期保持。4输出byte exact控制限于整例从未激活频域RES；不能拿已有抑制历史后的单帧inactive当控制。90whole+390fixed=480总组、原范围/160点坐标/tail/null、repeat/future、原数值容差与失败停止均保持。

无改善或纯echo代价必须真实保留，无效果晋升阈值，near标签不反馈算法。独立audit、NSFFT边界、局部资源与目标板资格分开。D39原42项快照保留为历史身份；后续追加README时须披露其条目变化，不声称历史快照仍全部current。baseline专属source/input/artifact须重新真实核身份。

下一安全动作：fresh Execution Policy/外部状态与D39基线专属锁，登记新的D40本地逻辑目标，然后只新增D40 C/tool/tests，按单因果配置实施；实际定向检查及独立实现审查PASS后才唯一主矩阵。不得重跑D39，已有输出或intent必须对账，未知不得重发。总体nativegoal active，未commit/push/PR/merge/release/设备写。
