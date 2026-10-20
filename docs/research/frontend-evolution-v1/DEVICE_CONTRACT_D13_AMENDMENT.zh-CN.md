# D13 执行前测量补充：验证实际候选次数

日期：2026-10-10；关联：[原冻结计划](DEVICE_CONTRACT_D13_PLAN.zh-CN.md)。
独立计划审查指出 10/20 帧 pulse 持续时间不能单独证明有效候选不足三次，原计划该描述是待验证假设。
实际必须读取候选/确认时点；若出现 jump，按原 mandatory FAIL 保留，不豁免或改输入时长。

新增同输入的独立 SYNC shadow state，直接调用同一个原库导出的 init/push_render/track_delay，
显式 S16→Float32 缩放与原等采样率 resampler 一致。只用于本组无 HPF/BF 的 SYNC|AEC 配置。
每帧独立累积 shadow jumps/slips，与公共 pipeline 的 delay/jumps/slips 比较完全一致后，
才允许用 shadow 的 candidate/confirm/error 解释实际候选时点。AEC 原输出仍由公共 pipeline 产生。
不重建或改原库，不访问或修改公共 pipeline 私有内存；shadow 使用独立状态，不能推导产品内存代价。
任一 shadow 不等价固定 measurement replan，而不是按语义失败继续。

统一零基帧：acquire phase=0，path-switch phase=120；截止为 phase+80，不从检测时点重新计时。
必须直接检查唯一跳变本帧进入truth±3 ms；switch前每帧保持40±3且无jump/reset。
补充只加强测量有效性，原56例/版、mandatory/diagnostic角色、原源码身份及失败保留规则不变。
