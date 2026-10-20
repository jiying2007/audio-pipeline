# D12 P1 测量截获验收补充

日期：2026-10-10；阶段：P1 执行前独立计划审查。
关联：[原冻结计划](DEVICE_EVENT_D12_PLAN.zh-CN.md)，保留其原始字节。

独立审查指出 GNU --wrap 只作用于未解析引用；原库使用 unity 构建，
pipeline 与 sync 定义可能在同一对象，链接成功和 PCM 等价不能证明实际截获。
因此增加 P1 硬条件：先运行一个完整原 capture，wrapper 调用数及 CSV frame 必须覆盖原 metrics 的全部 capture 帧，
且 observed/no-observe 均逐帧完整。若实际未截获，原测量实现判定失败，停止 P2，按 `measurement replan` 记录。
不得改旧库、构建配置或对象后冒充原库的截获证据。
该补充提高测量有效性要求，不修改算法或放宽原验收。
