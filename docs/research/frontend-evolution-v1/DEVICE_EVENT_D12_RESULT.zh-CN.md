# D12 事件诊断：搜索几何改变连续确认，原门禁按代码执行

日期：2026-10-10；experiment=`FE_DEVICE_EVENT_D12`；kind=`measurement`。
决定 **ENGINEERING_EVENT_DIAGNOSTIC_NO_PROMOTION**；`promotion_allowed=false`、`shipping_approved=false`。
本轮解释 D11 新增跳变的有限控制流因果链；[D11 REJECTED](DEVICE_SEARCH_D11_RESULT.zh-CN.md) 保留。
没有算法修复、参数搜索或物理对齐真值，不判断新增跳变的物理正确性。

## 计划、负结果与测量身份

[原冻结计划](DEVICE_EVENT_D12_PLAN.zh-CN.md)、[截获验收补充](DEVICE_EVENT_D12_AMENDMENT.zh-CN.md)、
[入口重计划](DEVICE_EVENT_D12_REPLAN.zh-CN.md) 均保留原字节。
独立计划审查指出 unity 对象内调用可能不受 GNU --wrap 作用；实际先验验证确认：
原 D11 库 observed/no-observe 各完整执行 3,024 capture，wrapper 调用数均为 **0**。
PCM/公开 metrics 虽与旧 receipt byte-exact，也不能证明观测有效，原 P1 判定 `MEASUREMENT_REPLAN`，未继续其 P2。

新测量副本仅把原函数定义名改为 `d12_real_ap_sync_track_delay`，其函数体和其他原源码均不变。
公共 pipeline 的原函数名由 [测量 fixture](../../../tests/validation/frontend_evolution/device_event_d12.c) 提供，
明确调用新名字的原函数。未使用 --wrap。fixture 的 library 注释应按此重计划理解为原算法体不变，
重新构建的 measurement library **具有新身份**，不等同于原 D8/D11 库。
原源码、副本、库、输入、配置和 receipt 均未覆盖。

| 身份 | SHA256 |
| --- | --- |
| D8 原库 | `a04ca88a75c0fd8538f7eb6d3726dfe906b2dfc284cc77c577f2328eb04b23b1` |
| D8 测量库 | `5db3e0e5ca4dff20c9ccebd0afbeda22ac4554b38a521d79dbdb6c3e2bddfc67` |
| D11 原库 | `ead75733d45f5b78c086bed9122082d410847eea0ed6b21f8bafab102a1cb0ac` |
| D11 测量库 | `6fa19897a4f6254525d6511e96a953b46d9ae76f492b0f1db67ae9f8f2358ce0` |

真实 pipeline 在 HPF/BF 后把 `pipeline->mono` 传给 wrapper，未以原始单麦或平均双麦代替该信号。
观测在完整复制的 sync state 中，按原 tracker 时点加入当前 mono 的 stride4 history，随后调用原 helper。
旁路返回前真实 state `memcmp` 不变；状态变化仍由新名原函数执行。
生成头逐字节匹配各旧 replay，实际编译 flags/defines 亦一致，路径和库身份独立记录。

## 测量有效性

四个原固定臂×D8/D11×observed/no-observe，共 **16 次有效完整运行**；每次 3,024 capture，合计 **48,384 帧**。
八次 observed 共 **2,400 个搜索 epoch**，不把同配置重复控制算作独立场景。
每次 wrapper 调用数等于原 capture 帧数，CSV frame 完整；
PCM 与公开 metrics 均逐字节匹配原 receipt，且 observed/no-observe 彼此相同。
逐帧新 delay、累计 jumps/slips 与公开 metrics 精确一致；本次调用全程 history mic/render totals 配对。
本组 CALL 执行臂启用 AEC，公开 resets 与 jumps 一致，原 pipeline 的 route_jump 分支立即 reset AEC 并计数。
default/sync-default-control 的诊断 CSV 也逐字节相同。

这些等价证据只覆盖冻结四臂；不是所有配置、设备或算法形式的全局等价证明。
最初两次无截获的失败加上述 16 次有效运行，共保留 **18 次执行回执**。

## rpm240/far-motion：第 457 帧触发

`run-2908630469-2466` default 与同配置 control 结果相同。
帧号为适配后公共 pipeline 的零基 capture index；10 ms/hop，第 457 帧起点为处理时间 4.57 s，
不能直接当作采集事件绝对时间或真实 render↔mic 延迟。

| 版本 / 帧 | refined samples | short score | 40 ms history score | 确认计数前→后 | 实际新 delay |
| --- | ---: | ---: | ---: | --- | ---: |
| D8 / 437 | 224 | 0.441406 | 0.117782 | 0→1 | 640 |
| D8 / 447 | 65 | 0.835224 | 0.774726 | 1→1，候选重启 | 640 |
| D8 / 457 | 24 | 0.271109 | 0.073728 | 1→1，候选重启 | 640 |
| D11 / 437 | 15 | 0.790728 | 0.709818 | 0→1 | 640 |
| D11 / 447 | 16 | 0.845554 | 0.776459 | 1→2 | 640 |
| D11 / 457 | 24 | 0.271109 | 0.073728 | 2→0，route jump | 15 |

D11 后两次候选距首次 candidate=15 samples 均在 tolerance=16 内，连续三次完成确认。
最终采用**首次保存候选 15 samples（0.9375 ms）**，不是第三次 refined=24。
原 delay=640 samples（40 ms），产生一次大跳、一次 AEC reset。
更早第 417 帧候选 0 的一次确认已在第 427 帧 history gate 失败后清零，不是跨失败窗口累计三次。
D8 tolerance=32，224→65→24 相对保存候选的差异仍超容差，故确认反复重启。

## rpm480/double-talk-motion：第 617 帧触发

`run-4874838670-2672` default，第 617 帧起点为处理时间 6.17 s。

| 版本 / 帧 | refined samples | short score | 40 ms history score | 确认计数前→后 | 实际新 delay |
| --- | ---: | ---: | ---: | --- | ---: |
| D8 / 597 | 15 | 0.331989 | 0.201440 | 1→1，候选重启 | 642 |
| D8 / 607 | 87 | 0.487034 | 0.348980 | 1→1，候选重启 | 642 |
| D8 / 617 | 16 | 0.629891 | 0.652263 | 1→1，候选重启 | 642 |
| D11 / 597 | 31 | 0.320961 | 0.198457 | 1→1，候选重启 | 640 |
| D11 / 607 | 16 | 0.768552 | 0.703656 | 1→2 | 640 |
| D11 / 617 | 16 | 0.629891 | 0.652263 | 2→0，route jump | 31 |

D11 第 587 帧 candidate=59；第 597 帧 refined=31 相距 28，大于 tolerance=16，重新从一次确认开始。
接着 31→16→16 相对首次保存的 31 均在容差内，第三次采用 **31 samples（1.9375 ms）**。
D8 第 597/607/617 帧为 15→87→16，未形成连续确认。
D8 与 D11 此前漂移状态已不同，不能把对应行都当作仅网格变化的瞬时同态反事实。
实际结果仍解释了各自保存候选/计数以及是否产生跳变。

## 因果结论与下一步边界

两个事件的三次确认都通过原 short/history 门限 **0.0324**，且实际统计的 unique 均为 1。
确认器没有绕过三次要求；40 ms gate 也未被绕过。确认间隔为原搜索节奏的 10 个 capture，即 100 ms。
原 large-jump 分支不调用 small-jump uniqueness 门禁；本轮这六个确认 epoch 的独立唯一峰诊断仍通过，
因此不能用“给大跳加同一 uniqueness 检查”解释或声称能阻止这两次事件。
数据支持的有限链路是：搜索几何改变候选轨迹→连续确认完成→采用首次候选→route_jump→原 AEC reset。
这不证明候选是真回声延迟，也不证明默认 40 ms 正确。

指定 rpm480/far-motion `run-4823498871-2661` tracked1 两版本均无 jump/reset，仍与原结果逐字节一致。
D11 REJECTED 保持；本诊断不批准新的算法参数。下一实验需要先区分初始延迟获取与稳定跟踪/实际路径切换，
为正常获取、错误候选、真路径变化定义独立可观测事件契约，再冻结单一修改。
真实对齐真值、人声标签、render 时间轴、SSC305 资源与实际声学仍为外部证据，不能用本组已有 development 数据填充。

## 证据与恢复入口

工件目录 `/tmp/audio-fe-device-event-d12-20261010`，临时工件不等同于长期归档。

| 工件 | SHA256 |
| --- | --- |
| 原 P1 无截获负结果 smoke-result.json | `816c6123d69d4e57560858af2697e9b1a1e73ad9220cd189e6ceaed98666d4f5` |
| 测量 fixture | `93b36fd62454f1fdff785423db5fbbf90bbf809d57d3d13105020b67ae625e78` |
| 16 次结果 result.json | `0eaab10a146a256fc09f03fc398797d1d4359655d8d5ed0b25d5fa1a0ee90c50` |
| 实际执行 binding.json | `e14b756f794c8b6df1cb0c68286b709009585f72f29520af95ef2973e65df2ab` |
| 补充 audit-v2.json | `5d518e89bb9fc96e2b12aa74a8031309e710e27bbb69786bafb94e70ea2a982b` |

原 binding 不覆盖后续补充；最终审查快照另绑定以上工件及当前文档。
audit-v1 保留一次文件匹配过宽的零 epoch no-observe 行；v2 精确排除这些行，仅统计八个 observed 文件，
没有改原 CSV、result 或执行回执，也没有改变总 epoch=2,400 的结论。
Provider route unresolved，仓内记录为 reviewing candidate，未正式归档。
无产品源码/default/API、AISpeech、E001 改动，无 commit/push/设备写。
独立审查与定向检查见 [D12 复审](DEVICE_EVENT_D12_REVIEW.zh-CN.md)。
