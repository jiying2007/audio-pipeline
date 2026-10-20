# D37 因果残差模型实际执行记录

2026-10-11；experiment=FE_DEVICE_CAUSAL_RESIDUAL_MODEL_D37。主测量完成，首次独立全量审计 FAIL，触发冻结停止条件 replan；不得解读为全量数值 PASS 或产品资格通过。

首次主 wrapper session 28379 真实终态 exit=0；非仓 cwd 顺序 help/deep dry-run/9 tests/main 各 exit=0。main 用时 40.80076479911804 秒，完成 46 例 / 126486 帧 / 原 240 whole/window。零 AEC 执行、零 lag 搜索；repeat 全 CSV exact，future 通知前 1247 帧前缀 exact，future measurement=null。输入、复用源码与当前源码起止身份相等。

输出根 /tmp/audio-fe-device-causal-residual-model-d37-20261011；result SHA256=2b65812dbb88db0765846c3f15adb54b8bb0df10104593df086ba4b6bfe212ec，binding SHA256=644e2197afb7b46f7b68026b2a671d3e1c8f41342603b9288332e071abfc901e。主回执 /tmp/audio-device-d37-execution-3.json SHA256=f5b28d71997ab322f4142445a12200bd01d952490f960c41ce03480b6e5a0899。

覆盖拒绝 negative session 19138 真实终态 exit=0；三个目标命令各 exit=2。旧 D36 根 68 文件、仓根 2478 文件、已有 D37 根 48 文件完整 manifest 前后相等；用时 2.7976346015930176 秒。回执 /tmp/audio-device-d37-negative.json SHA256=ea3f9aba6b29700da17455080f7e5acb1010b78865b3455b50175d19678d151e。此为 root 执行，独立审查者核回执，未声明独立重跑。

以下为导出观测；全量独立复算已失败，这些值不用于阈值或候选选择：

| 来源 | 纯 echo explained_fraction p50 | 纯 echo innovation_ratio max | 混合第一 near innovation_ratio p50 | 第一 near 中 ratio>1 帧数 / 200 |
|---|---:|---:|---:|---:|
| A r16 | 0.43796394 | 1.00695283 | 1.07837478 | 192 |
| A r20 | 0.41539107 | 0.97933475 | 1.07759480 | 193 |
| ABA r16 | 0.44335405 | 1.43119071 | 0.83560545 | 22 |
| ABA r20 | 0.43751445 | 1.44180916 | 0.83779769 | 21 |

过去单 lag 模型可解释部分纯 echo 残差，也保留路径变化导致创新增大的失败。混合 ABA 第一 near 仍包含可预测成分，创新比例不能作为 near truth；A 第一 near 的多数帧创新增加也不等于声学改善。其余 mixed 时段仅称 no-near，不提升为独立纯 echo。

数据角色保持 inspected development / synthetic engineering / adaptive reuse。固定 decision=CAUSAL_RESIDUAL_MODEL_DIAGNOSTIC_NO_PROMOTION；promotion_allowed=false，shipping_approved=false。独立 audit session 43130 真实 terminal exit=1，用时 12.93146032653749 秒；脚本 d7246244c320dbcc5a4043290370d3036c027638c180f65ce0582e16d3ba0dd7 未修改。失败回执 /tmp/audio-device-d37-independent-audit.json SHA256=038df36983b0e08fbda73022430f807d147ef328f5b7578836cd3b5e467a4e53。完整通过前 4 例 / 12012 帧 / 16 窗；第 5 例 frame1831 拒绝，其余案例未获得独立验收。

失败定位 field-case-03-fixed1-shadow frame1831、lag1516：过去 fit_xx=1.1175870895385742e-08，fit_rx=3.241998641101418e-06，beta=290.0891278584798，正反向完全相同。当前 rr 正向 0.0058948631158262455、反向 0.005894863115826248；逐点 innovation_energy 正向 127.88126265193422、反向 127.88126265193429。innovation_ratio=21693.678061599894 / 21693.678061599898；绝对误差 3.637978807091713e-12 超过冻结 1e-12，相对误差约 1.6769764890773961e-16。

当前 reference_energy 升至 0.0015110587701201439；过去小 fit_xx 产生大 beta，当前创新比例无界，其 double 间隔已超过固定绝对预算。问题来自普通累加对顺序敏感与大比例数值尺度；此帧不涉及 fit 差异放大或能量差公式抵消。原 D37 不放宽容差、不 clamping、不重跑审计、不修改既有输出；下一阶段需单独冻结数值结构与独立精确求和验证。

实施自检的两次失败、修正依据和维护请求未验证终态详见 IMPLEMENTATION。AISpeech 整链、真人 near/KWS、目标 SSC305 资源与 HIL/E001/PQ、第三方权利和 owner 验收仍分别未闭合。
