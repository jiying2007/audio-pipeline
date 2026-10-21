# D29 执行前范围澄清

日期2026-10-11；原PLAN SHA256=6daa1dada8d06b07a81bed9332f02aea99698ce8dcff016e630f24d843f4e97b，原字节保留。
尚未开始主DSP矩阵；本补充不改46个执行、参数、数据角色、字节等价、评分、预算或超时。
双AEC指同一单路16k Float32 AEC-input及同一reference上的primary/shadow两套滤波状态，不能称双麦逐路AEC或原生C2/C4整链。
上游已经生成的AEC-input/ref和外部far/dt被冻结，D29不新执行上游BF/SYNC/Activity，也不执行下游NS/RES/AGC/KWS。
state.csv是原primary状态诊断字段的相同序列，不是完整MDF内部状态转储；四bank全输出字节等价与该观测须分别核验。

预编译第0次严格拒绝：旧D26全局primary/shadow可见时，D27头参数同名触发-Wshadow；回执precheck-0.json与原writer保留。
只调整新D29 C的私有头包含顺序，使其在D26状态定义之前；不改原头/C/library，不关闭或削弱警告。
第1次严格编译及集成时序自测实际exit0；预编译retry1，主DSP重跑0；该修复不改变算法或混合表达式。
scope_write补充本AMENDMENT，执行前及后hash绑定；后续结果与审查保留上述失败历史，不能写整轮零失败。
资源71,196B只是两状态/selector/transition/8帧缓冲的局部口径；没有目标板、进程总资源或部署批准。
