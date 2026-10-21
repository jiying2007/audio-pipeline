# D38 精确求和数值结构冻结计划

2026-10-11；experiment=FE_DEVICE_CAUSAL_RESIDUAL_MODEL_D38；primary=adk-planning-execution-loop；总体目标全面推进优化迭代，active。

## 基线与唯一改变

D37 全量主测量 result=2b65812dbb88db0765846c3f15adb54b8bb0df10104593df086ba4b6bfe212ec，binding=644e2197afb7b46f7b68026b2a671d3e1c8f41342603b9288332e071abfc901e；独立审计失败回执=038df36983b0e08fbda73022430f807d147ef328f5b7578836cd3b5e467a4e53。先锁 D37 完整来源、工件、audit 源码、失败回执与 REVIEW；不修改 D37 或其前序。

真实缺陷：普通 double 顺序累加不能使大无界创新比例满足固定绝对误差合同。D37 frame1831 fit 与 beta 本身 exact，而 ratio 因末位 rr/innovation 差异改变一个 double 间隔。唯一改变为各 160 点点积/能量的求和数值结构，使用 math.fsum 正向累加各已计算 binary64 项；每项乘法、prediction、innovation 和最终 beta/ratio 除法仍按 binary64 运算。禁止改变 lag、拟合窗、模型、数据、clamp、阈值或声学裁判。

数值 SSOT：160 项 binary64 值的精确数学和，一次舍入至 binary64；fit_xx、fit_rx、rr、xx、prediction_energy、innovation_energy 均遵循。fit_rx 保留符号。prediction 和 innovation 仍逐点构造，禁止能量差公式。

## 数据与执行合同

延续 D37 PLAN+AMEND 除普通累加结构之外全部模型/15列/有效性/时间/统计/data role/NO_PROMOTION 合同。原 46 例 / 126486 帧 / 240 inward 窗；32 field 无 near truth，12 return 为 synthetic engineering，repeat 全文件与 future 通知前1247帧 exact。不进行候选选择，不复用为 validation/blind。

新独立工具与 tests，纯 stdlib Python3.8；旧工具不改。输出 /tmp/audio-fe-device-causal-residual-model-d38-20261011，fresh direct /tmp，拒绝旧 D37/仓根/已有 D38 根完整 manifest 不变。非仓 cwd 顺序 help/deep dry-run/tests/main；主及独立全量 audit timeout=None，其余120秒。异常先写 x 回执 command/exit=null/type/elapsed/部分输出再传播；retry_budget2，未知请求不重跑。

## 独立数值验收与风险

独立 audit 不 import 新旧项目 helper、不以 math.fsum 作为自身求和裁判。将每个实际 binary64 乘积项用 Decimal.from_float 精确转换，precision=2200 反向求和，转回 float 一次舍入；有限 binary64 项十进制展开与160项累加所需精度上界小于该值。audit 前必须用最大/最小有限值和混合正负的 known-answer 独立验证精度上界及求和精确性；Decimal traps Inexact/Rounded 用于发现未预料精度损失，转换回 float 的最终舍入允许。

audit 的 beta/ratio 除法仍依据其独立求得的已舍入 binary64 能量用 binary64 执行，避免悄悄采用全精度模型。全46/126486逐点核；整数/flags/null/held direct/零 exact；所有新浮点字段要求 exact binary64 相等，强于 D37 的容差，不放宽大比例误差。Decimal 仅用于独立 audit，不进入执行工具或产品。若 fsum 在实际平台双舍入导致不满足 exact，保存失败并 replan，不改容差。

known-answer 延续 D37 九项，并新增真实失败帧独立回放、160项正负大幅抵消、顺序置换/反向不变、大于21693的无界比例不 clamp。D37 的旧数值只作来源和失败对照，不要求 D38 与其非精确累加数值一致。

全量 audit 同时复算240窗/near/no-near/guard前帧/repeat/future及来源起止锁。PLAN fresh独立PASS→实施→实施fresh独立PASS→主→negative→独立audit→RESULT/README→docs/diff→whole独立→REVIEW→Runtime final独立附核。共享输出串行；不重复旧 AEC/DSP/lag 搜索。

运行总预算86400秒、Runtime本地16M token仅控制，不替代native总体无上限。新增 Decimal audit 可能更慢，记录实际耗时；不声明目标板实时/CPU/RSS/栈/热/功耗。来源漂移、非有限、exact失效、两次未知失败触发停止并replan；不得扫参数取PASS。独立reviewer沿用 device_capture_independent_review。

即使数值通过，也只证明诊断可复算，不晋升 near 保护器；路径失配/near混淆需新的结构假设和独立数据。AISpeech整链、真人near/KWS、SSC305/HIL/E001/PQ、rights/owner继续分别验收。当前 D38 尚未实现/执行/通过计划审查；总体目标未完成。
