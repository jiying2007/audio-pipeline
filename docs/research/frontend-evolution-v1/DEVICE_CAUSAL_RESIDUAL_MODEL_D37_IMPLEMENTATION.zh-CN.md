# D37 实施与维护核验记录

2026-10-11。原 PLAN 与 AMEND 身份保持；本文件记录实际实施，不替代待执行的全量结果或独立审计。

宿主已实际触发上下文压缩。唯一 v5 请求留有 intent、accepted、compact 三份回执；compact 状态为 ACCEPTED_COMPLETION_UNVERIFIED，观测耗时 120.43818570114672 秒。没有重发。2026-10-11T06:59:56.461088Z 的 canonical steady 回执 required=false、recommended_action=continue、context_ratio=0；其 compaction_completion_verified=false 保持，不将宿主事件归因于该请求。

工具实现前帧自身 lag 拟合有符号 beta，当前逐点预测和创新；仅输出研究 CSV/统计。原 D36/D35 工具保持，来源锁延伸至 D36 完整绑定、独立审计与审查，以及 D37 冻结 PLAN/AMEND。

实施前自检失败保留：首次从 /tmp 运行 unittest 未设置 PYTHONPATH，实际 exit=1，ModuleNotFoundError: tools；改用明确仓库 PYTHONPATH。第二次实际 exit=1，极端参考测试只有 f0，未执行拟合，所以预期异常的断言失败；测试改为两帧触发真实 fit 能量溢出。未改变模型、数据、容差或验收要求。修正后 9 项 known-answer 实际 PASS（9 tests / 0.005 秒），包含 signed beta=-1 的合法值、非零 lag 跨帧、ratio>1、near 创新、当前 rr=0 的真实预测与无效归一化、当前参考零、不保持失效状态、输入/schema/非有限拒绝和未来前缀。

当前尚未执行全量主测量；须 fresh 独立实施 PASS 后，由 /tmp/audio-device-d37-execute.py 串行从非仓 cwd 执行 help、deep dry-run、tests、main，独立写各命令回执。主 wrapper 无 timeout，其余 120 秒；异常先写回执再传播。总体目标仍 active。

随后 fresh 独立实施审查 Spec PASS / Quality PASS / Reviewer Independence=independent / unresolved=0；审查者从 /tmp 独立运行 9 tests，实际 exit=0。工具 SHA256=9d02e3ea8369f12e3249d9dd86823d8879b83afce86ee3bf6778d5cb7bb7ef02，测试 SHA256=dfec9cc6f848d0fe76a8922355f81e5b7864fc839b70b9aaa8c67016723a5e89。据此进入首次主测量：session 28379 已实际返回 help/deep dry-run/tests 三命令 exit=0；主命令仍执行中，待真实终态。独立 audit 当前冻结 SHA256=d7246244c320dbcc5a4043290370d3036c027638c180f65ce0582e16d3ba0dd7；尚未执行实际审计。
