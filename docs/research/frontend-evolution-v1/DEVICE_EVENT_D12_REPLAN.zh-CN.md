# D12 测量入口重计划：保留 unity 截获失败

日期：2026-10-10；关联：[原计划](DEVICE_EVENT_D12_PLAN.zh-CN.md)、[P1 补充](DEVICE_EVENT_D12_AMENDMENT.zh-CN.md)。
P1 实际决定=`MEASUREMENT_REPLAN`，原 --wrap 方案无效，不进入其 P2。
原 D11 库两个完整运行均 capture=3,024、wrapper=0；observed/no-observe 的 PCM 和 metrics 虽 byte-exact，
也不能作为有效观测。完整负结果保留 `/tmp/audio-fe-device-event-d12-20261010/smoke-result.json`。

## 新测量身份与唯一变更

在精确 D8/D11 源码的独立 /tmp 副本中，仅把 ap_sync_track_delay 的函数定义名改为 d12_real_ap_sync_track_delay。
原函数体字节不变、头声明及其他源码不变；公共 pipeline 的原函数名由同一测量 wrapper 提供，
wrapper 明确调用新名字的原函数。移除 --wrap，避免依赖 unity 未解析引用。
副本重新构建，源码/库/工具链/编译命令/生成头必须登记 **新的 measurement identity**，
不得把新库 hash 写成原 D8/D11 库 hash，也不得宣称测量库就是原 shipping 库。
原库、原副本与原 receipt 不修改。

只有新 wrapper 调用数等于全部原 capture 帧数，trace 帧集合完整且每帧新延迟、jump、slips
与原 metrics 精确一致，且 observed/no-observe PCM/metrics 与旧 receipt 全部 byte-exact，
才允许有限时序解释。copy-state、history 时点及 helper 仍执行原计划的严格断言。
若不等价或未截获，停止并记录测量失败，不修改算法体、参数、门限或输入。

四臂×两版本×两模式的 16 次新测量均完整执行，保留原 P1 两次失败，共 18 次回执。
不重新进行 D11 优化，不复跑整套 70 臂算法选型，不据本测量批准候选。
根代理冻结重计划后，由原独立 reviewer 审查入口修改与全量实际等价证据。
retry：本次为第一轮测量实现重计划，仍最多两次修正；新增 finding class=unity interpose ineffective。
contract_change_decision=`measurement identity change`，数据角色、硬拒绝规则和产品权限不变。
