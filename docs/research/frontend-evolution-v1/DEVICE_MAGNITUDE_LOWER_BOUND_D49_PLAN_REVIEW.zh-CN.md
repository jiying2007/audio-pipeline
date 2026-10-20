# D49 幅度下界保护独立计划审查

2026-10-15。experiment=FE_DEVICE_MAGNITUDE_LOWER_BOUND_D49；claimant=root；verifier=device_capture_independent_review。本记录为实施前独立计划审查，不是实施、运行、数值审计或候选效果证据。

审查的冻结合同：

- PLAN：`e8ffa4a9db2165b80f036c4791fdf1af6b7ca5215a7cc2daec47d8e8d2cbb119`。
- AMENDMENT：`9e7ddaa0e82d434f3d2addc631d878562c35719a21bb03e98dcf7a810ec87a65`。

## 发现与闭合

首次计划审查发现 MINOR-1：PLAN P2 的“所有新值须 finite 且非负”若包括差值 `d=sqrt(P)-hypot(pr,pi)`，会拒绝合法的预测幅度大于当前幅度案例，与该案例应得到 L=0 的合同冲突。该问题在静态计划审查发现；当时尚未实施，没有据此发生的运行失败。

上述独立 AMENDMENT 保持原 PLAN 字节，明确 rmag/pmag/L 有限非负，d 有限但允许负数或零；仅 d>0 时平方并检查有限非负，d<=0 直接设正零。原 H/pr/pi/P/J 的全部计算与有限性检查、模型 valid 及 raw J 诊断保持。此次 fresh 读取确认修订只消除合同歧义，未改变公式、系数、门槛、容差、预算或数据角色。MINOR-1 closed。

## Spec 与 Quality

单一因果变化为保护估计量由 J 改为 `L=max(sqrt(P)-hypot(pr,pi),0)^2`，严格 2N 门控与归一化同时使用 L；不改变拟合 H、过去状态、EMA、noise、Activity、post-NS max 或下游链路。精确实数运算下 L 同时不大于 P 和 J；它相对于模型预测，不是近端真值下界。浮点跨算法单调性不作为硬门禁，避免重现 D47 的测量合同耦合。

预测幅度过大、方向反转、模型低估、近端相消、P0/J正和 J>P 均有明确解释或 known-answer 要求；原 current_innovation_sum 仍为 J，不用 L 偷换旧诊断。binary64 sqrt/hypot 顺序、严格比较、binary32 floor、有限性拒绝及 expected-zero 合同可实施和独立复算。具体源码、libm 调用、测试及运行控制仍须实施后 fresh 审查，本记录不预先证明其实现正确。

D48 baseline 的真实 decision 为 MEASUREMENT_CONTRACT_VERIFIED_NO_PROMOTION，其原开发准入两臂 accepted=false；计划未将局部 near 收益替代 no-near/pureecho 代价。D48 result/binding、actual audit/whole/final snapshot 与已完成本地状态的固定身份保持，旧失败只读保留。新 preflight 必须先 literal pins 再消费完整依赖，冲突 SHA 拒绝；未来 README 追加须先保全对应精确历史字节，不能静默排除旧锁。

保留184路/505944帧、960组评分、原160点对齐与全部窗口，两臂分别使用原24near/72no-near/4pureecho准入。development/adaptive reuse、合成近端、未知现场真值、repeat非独立和future不评分边界明确。单命令120秒、矩阵1800秒、独立审计1800秒、whole180秒及原资源/磁盘限制未放宽；新sqrt/hypot的Host成本须实际验证，不能从sizeof推断目标板实时性。

## 独立性与结论

此次仅只读审查计划、修订与既有已附核基线事实，并新增本审查记录；未运行测试、DSP、旧审计或新正式测量，未改D48冻结字节、源码、README或运行状态。后续独立审计须不导入生产measurement helper，独立复算全部新波形评分、原准入、AGC/VAD及固定snapshot算术；全帧FFT/bin、完整EMA/noise历史独立重建仍为false，不能扩张覆盖声明。

**计划阶段 Spec PASS / Quality PASS / Reviewer Independence PASS；unresolved 0。** 允许依此双文件合同进入新任务登记和实施；正式矩阵仍须等待实现、定向验证和一次执行控制的fresh审查。任何结果均不构成shipping或产品批准；原准入失败须保留并停止本映射系数搜索。D49当前尚未登记/实施/执行；总体native目标保持active，Provider unresolved/NEEDS_REVIEW不构成归档成功。
