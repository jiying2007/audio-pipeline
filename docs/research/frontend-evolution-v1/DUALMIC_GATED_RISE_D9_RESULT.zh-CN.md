# D9 实际执行记录

## 首次尝试：工程编译失败，未运行科学回放

实现提交 `40712ba`，输入 ZIP hash 已通过，C 编译失败：符号隔离过宽，
将共享类型 `ap_agc_state_t` 同时改名为不存在的 `d9_agc_state_t`。
返回码1；0个case运行、无质量或性能结果。失败输出目录和日志原样保留。
修复仅恢复候选的共享状态类型名；数学变化、输入、预算、阈值不变，
生成变换必须逆转后与原C源码逐byte相等。后继执行需独立源码身份。

## 首次有效科学执行：3752d47

**NO_ADVANCE / measurement_valid=true / promotion_allowed=false**。
60例、35,916帧、5,746,560样本、362固定窗完整执行，18.915379秒（含准备/编译/回放/分析，
完成收据写入在此之后）。ZIP完整hash、全部输入/参考hash、原baseline状态/PCM和原D2评分一致，
两臂7次真实C回放逐byte重复，独立Python逐样本输出和连续gain公式审计通过。
[完整结果](dualmic-gated-rise-d9-result.json)包含所有案例、窗口、null、负结果与CPU时值，不按结果删选。

- baseline共532个allow=0状态回升帧，仅在far-only/render-gap，CALL/ASSISTANT各133帧。
- 候选共改变52,612个输出样本，全部在上述两类无clean-near参考的场景。
- 32个有参考common ΔSI-SDR全部 **0 dB**，所有可评分固定窗不降。
  nominal/weak双讲以及中文案例输出未改变，所以没有双讲≥1dB改善，原继续门槛失败。
- 远端相关及C的原common/window/native RMS、peak均不增；实际末端clamp两臂均0。
  不能将无near真值场景的更低能量等同为听感改善，也没有证明真实近端恢复无损。
- 带检测/复制开销的原生C thread CPU：全部case七次总时值中位
  baseline **0.011623159 s** / candidate **0.011655313 s**，比值 **1.002766**。
  这是共享host的AGC微基准，不是完整pipeline、SSC305、ARM或稳定性能提升证据。

本候选按冻结合同关闭，不改变生产代码、默认参数或D39–D49的衰减恢复语义。
不自动继续该参数扫描。工程负例与后续PR/main资格单独记录，不重跑科学实验来获取绿灯。

独立结果复核确认完整报告hash、所有32个common及160个可评分窗口和null筛选；
只有pair3的far-only/render-gap两profile共4例输出改变，common RMS变化约
−0.001187至−0.002205dB。不能外推长期衰减恢复风险。

工程负例首次自身断言误将2×2×5×6个合成组合写成240，实际120；原自测执行正常。
仅纠正计数断言后11项工程测试通过（含120组合/3非有限检查和输入/控制/基线破坏拒绝）。
此为测试预期错误，不改变科学结果，也没有重跑科学实验。

## 可移植执行来源

科学执行SHA是本地 `3752d47`，不是后继GitHub连接器发表提交；直接git push缺少云端Git凭证，
因此通过已授权GitHub连接器发表相同文件。[Git bundle](dualmic-gated-rise-d9-local-execution.bundle)
保留从已存在base8f282f0开始的全部本地合同/执行/结果提交，含原编译失败，不伪装成远端执行。
在具备base的仓库可先 `git bundle verify <bundle>` 再 `git fetch <bundle> research/dualmic-gated-rise-d9`。
[原构建收据](dualmic-gated-rise-d9-build.json)与[原完成收据](dualmic-gated-rise-d9-completion.json)
分别绑定编译、程序、合同与结果hash。后继CI只运行工程负例及报告归档校验，不重复科学回放。
