# C4 单一核心：尚未取得的软件资格与证据清单

## 2026-10-23 有限 A2-F0 收口状态更正

下方 2026-10-21 接续与 2026-10-20 盘点保留为历史快照。A2-F0 已通过[实现 PR #829](https://github.com/jiying2007/audio-pipeline/pull/829)完成有限范围资格；此前“实现候选仍待资格”的时态已被后续收口取代。

其 protected main 为 `b6c439e58675ed703aad56b348a1c276a560cdf9`，该提交自己的 [Verify 39739604417](https://github.com/jiying2007/audio-pipeline/actions/runs/39739604417) 与同 SHA [Release 39744241299](https://github.com/jiying2007/audio-pipeline/actions/runs/39744241299) 均成功，release 与 convergence 两项成功。2026-10-23 已重新读取这些运行状态及原始 [Artifact 12409795879](https://github.com/jiying2007/audio-pipeline/actions/runs/39739604417/artifacts/12409795879) 元数据：3,552,757 字节，ZIP SHA256 `9af265facea49a4e56931d7823636b38b93cdaa212308df32def283604732e2a`，未过期，绑定该 main。原 ZIP/成员独立读回引用 #829 的既有收口记录，本次文字更正不宣称重新运行实验或重新下载该原件。

已完成范围严格限定为停源、调用者独占时固定 **1..32 → 17..32** 前缀退休，以及由存活父协调器持有外部 expected anchor 的 hosted fresh-process 恢复。它不具备连续滚动、整机冷启动后锚点重建或 NAND/UBIFS 物理掉电资格；不替代完整进程 RSS、逐帧时延、真实 SSC305、HIL/E001 或公共 C4 SDK 的验收。

接续软件范围保持为 #796/#791 的连续滚动与恢复剩余范围、#767 明确作用域的完整资源归账、#733 的有限全双工组合；已完成的有限 A2-F0 不重复实施。上述 b6c439e 是已完成阶段的证据身份，不冒充 live main，也不替代本次文档 PR/main 自己的检查。

## 2026-10-21 接续状态更正

下方 2026-10-20 盘点保留为原始历史快照；其中“A1 候选 / 资格读回待完成”的时态已被后续收口证据取代。已重新读取 [A1 #809](https://github.com/jiying2007/audio-pipeline/issues/809)、[Runtime #810](https://github.com/jiying2007/audio-pipeline/issues/810)、[证据运输 #754](https://github.com/jiying2007/audio-pipeline/issues/754) 的 completed 状态，以及实际 [合并 PR #818](https://github.com/jiying2007/audio-pipeline/pull/818) 和以下运行元数据。

| 已完成范围 | 精确收口与保留边界 |
|---|---|
| A1：私有 FRM2 非零左锚点根 | 已在 `c416a5f8e44b36a6af5be4dc53c71456dd6ba5ef` 完成独立主线资格。逻辑窗口 17..32、物理原文件 1..32 均保留；没有 A2 删除、循环复用或物理掉电资格。 |
| Runtime R1–R4 与 CI C1–C2 | #810 已随 v2.3.56 收口；不再作为待修复任务重开。历史源码绑定由 [2.3.56 维护说明](RUNTIME_MAINTENANCE_REBIND_2_3_56.md) 保留。 |
| 无损空间证据运输 | #754 已完成原归档与下游读回资格；没有改变科学执行、来源、阈值或真实设备权限。 |

共同收口证据为该精确 c416 主线的 [Verify 39435091890](https://github.com/jiying2007/audio-pipeline/actions/runs/39435091890)（79 成功、1 预期跳过、required summary 成功），以及同 SHA 的 [Release 39440540096](https://github.com/jiying2007/audio-pipeline/actions/runs/39440540096)（release、convergence 均成功）。这是已完成阶段的来源身份，不代替后续提交自己的 PR/main 检查。

A1 原始 [Artifact 12272245576](https://github.com/jiying2007/audio-pipeline/actions/runs/39435091890/artifacts/12272245576) 为 37,894 字节，ZIP SHA256 `cc2e851af1b7a0edf88c778e4e67e7d93a2f29b6f12daf2b9fb06ab9ab3ec3ef`；本次实时元数据与 #809 登记的原始 ZIP、四成员及三个内部哈希独立读回记录一致。本次状态更正没有重新下载或重做该实验。

因此接续软件范围为 **另行预注册的 A2 源锚定删除/滚动与故障恢复、T3-S3 完整作用域资源归账、B3 有限全双工组合**；这些阶段仍未由 A1 收口完成或自动准入。根计划 #730/#733、滚动留存 #796/#791、资源 #767 保持开放。真实 SSC305、ADC/DAC 时钟、NAND/UBIFS 掉电、HIL/E001 和公共 C4 SDK 仍保留各自资格门禁。

A2 的首个有限实验已通过 [登记 #825](https://github.com/jiying2007/audio-pipeline/issues/825) 和 [预注册 PR #826](https://github.com/jiying2007/audio-pipeline/pull/826) 纳入 protected main `de78006f82dcb5c34218ecdacf4d9c0ffe397df1`，保留四份冻结原件及 ACTIVE 分支登记。A2-F0 只研究独占停源后的 **1..32 → 17..32 固定前缀退休和外部锚定的 hosted 进程恢复**；实现候选仍需自身四目标、原始 Artifact 读回和受保护主线资格，连续滚动及设备权限继续独立。

## 2026-10-20 原始盘点（历史快照）

审查日期：2026-10-20 UTC。源码基线为 protected `main=e3672ffe16e4c9d42a100e7712b9bbd3d8338545`；本轮重新读取 main、相关 issue 状态及以下代码/文档。本文是只读盘点，**不新增实验准入、不改变 2.3.56 修复范围、不宣称 public C4**。根计划 [#730](https://github.com/jiying2007/audio-pipeline/issues/730)、[#733](https://github.com/jiying2007/audio-pipeline/issues/733) 仍 OPEN。旧 issue 正文和冻结预注册文档中的 `BLOCKED` 是登记时状态；不能用它覆盖后续已关闭的 children。

## 已有实现：后续必须复用

| 现有软件事实 | 精确仓库依据与已核状态 |
|---|---|
| 私有 C1/C2/C4 ingress；N 个物理麦 SRC 与 0/1 个独立 Render SRC；16/32/48 kHz 的 10 ms 输入进入单一 16 kHz/160 样本 FIR33。这里已经有真实 SRC 和单一 BF。 | `tests/validation/frontend_evolution/fe09_b1a_ingress.[ch]`、`tests/validation/frontend_evolution/fe09_b1b0_src.[ch]`、`tests/validation/frontend_evolution/fe09_b1b1_single_bf.[ch]`；[B1-S1 header/处理与 gap 合同][b1-code]；[B1-S1 文档][b1-doc]。[#735](https://github.com/jiying2007/audio-pipeline/issues/735)、[#737](https://github.com/jiying2007/audio-pipeline/issues/737)、[#743](https://github.com/jiying2007/audio-pipeline/issues/743) 当前均 CLOSED。 |
| 私有 SPSC queue、独立 APX3 writer/CRC/parser/replay、threaded bridge、source-owned Render PRESENT/ABSENT、K1/K2 compact handoff 均已有代码。APX3 是私有格式，未发布为新的公共 dump ABI。 | `tests/validation/frontend_evolution/fe09_b2s1_private_queue.[ch]`、`tests/validation/frontend_evolution/fe09_b2s2_private_apd.[ch]`、`tests/validation/frontend_evolution/fe09_b2s3_private_bridge.[ch]`、`tests/validation/frontend_evolution/fe09_b2s3_t2b_b1s0_owner_spsc.[ch]`、`tests/validation/frontend_evolution/fe09_b2s3_t3s1_compact_handoff.[ch]`；[S2 文档][s2-doc]、[S1 compact §Compiler memory model][compact-doc]。[#755](https://github.com/jiying2007/audio-pipeline/issues/755)、[#760](https://github.com/jiying2007/audio-pipeline/issues/760)、[#789](https://github.com/jiying2007/audio-pipeline/issues/789) 当前均 CLOSED。 |
| A0 已经将原始 APX3/FBS1 连续 seq1..32 放入有界、不可覆写的独立 outboard；它不是滚动保留或 GC。 | `tests/validation/frontend_evolution/fe09_b2s3_t3s2b1ba0_finite_outboard.[ch]`；[A0 文档 §What is added / Correct authority and limits][a0-doc]；[#803](https://github.com/jiying2007/audio-pipeline/issues/803) 当前 CLOSED。 |
| 已接过真实 AEC/mono SDK。R0 是 16 kHz 研究 BF→真实旧 mono SDK 功能桥；FE04 已比较 BF→单 AEC 与逐麦 AEC→BF。 | `tests/validation/frontend_evolution/array_sdk_bridge_r0.c`、`tests/validation/frontend_evolution/bf_aec_order_runner.c`；[R0 §Why this is a research bridge / Frozen inputs][r0-doc]、[FE04 §What actually executes / Data and frozen matrix][order-doc]。FE04 用同步参考和预设双讲门控隔离顺序；不包含实际 SYNC/DTD/RES/NS/AGC 全链资格。 |

## 明确尚未取得的资格

| 边界 | 仍缺什么；可由软件阶段完成的有限前置 | 精确证据 |
|---|---|---|
| **A1 → A2，滚动保留** | A1 当前为独立 FRM2 非零左锚点候选，逻辑 17..32、物理 1..32 仍保留；四目标、同运行原件读回和 protected-main 门禁尚不能由本地代码代替。只有 A1 独立关闭后，A2 才能另行冻结“可读新根→持久化屏障→删除→目录同步”与重启/半事务矩阵。A1 的根目录临时链接清理不是 A0 原文件 GC。 | [#809 §Separate future A2 = actual unlink/rolling candidate, not A1](https://github.com/jiying2007/audio-pipeline/issues/809)；[A0 文档末段 A1/A2 分界][a0-doc]。本基线没有 A2 生产实现。 |
| **T3-S3，全进程资源与尾延迟** | 已有 compiler-true 下界和 compact slots，不等于完整预算。下一阶段应固定实际运行链与配置，把物理 source queues、SRC/BF state、rollback work、preflight scratch、thread stacks、heap/ELF/RSS、outboard 同进程或其他进程的费用分别列清，记录逐帧 CPU 与 wall p50/p95/p99/max/超时。若该阶段仍未接 AEC 等下游，它只能描述这条私有链，不能提前叫完整应用预算。 | `tests/validation/frontend_evolution/FE09_T3S0_COMPILED_MEMORY_CENSUS.md` [内存下界与 excluded fields][census-doc]；[compact §Compiler memory model][compact-doc] 明列独立 T3-S3/T3-S4；[#767 §Precisely scoped T3 research question](https://github.com/jiying2007/audio-pipeline/issues/767)。 |
| **B3，真实估计器与完整全双工组合** | 复用 B1 的 N+Render SRC/单一 BF 以及 R0 的真 mono SDK 接口，有限验证实际 SYNC/DTD/AEC/RES/NS/AGC/VAD 的时序、reset、Render 缺席/重入、capture/clock gap 和双讲。先冻结来源、速率、延迟映射、状态所有者和拒绝时原子性，再做固定效果对照；已有 FE04 oracle 门控结果不能替代这些交互。8/24 kHz 和异步 ADC/DAC 目前没有 B1 资格，不能顺带宣称支持。 | [B1-S1 header 中 `fe_b1b1_process` 的 NOT AEC 与 controls 合同][b1-code]；[R0 §Exit and future work][r0-doc]；[FE04 §What actually executes / Resources and reproducibility][order-doc]；[#733 §R2-B3](https://github.com/jiying2007/audio-pipeline/issues/733)。 |
| **下一 major 公共 cutover** | 私有原型通过后仍需独立版本化 `struct_size/api_version`、配置专属 size/alignment/arena、32/64-bit 溢出与 consumer ABI 测试、Linux capture/render 生命周期及公共 writer/parser/replay 的显式格式迁移与回退。APX3 私有可回放不等于这些公共消费者已迁移。**不得抬高 2.x `AP_MAX_MIC_CHANNELS`、扩展旧按值结构或把第二 DSP 核永久挂在 2.x 旁路。** | `docs/research/frontend-evolution-v1/FE09_R2B0_MAJOR_MIGRATION_PREFLIGHT.md` [§Current-source cutover matrix / ABI and memory ownership / Independent gates][major-doc]；`tests/validation/frontend_evolution/FE09_R2B2_S0_RUNTIME_RECORDER_CUTOVER.md` [§Two mutually exclusive architecture choices / Grounded 2.x boundary][cutover-doc]；[#733 §Nonnegotiable boundaries / R2-B2](https://github.com/jiying2007/audio-pipeline/issues/733)。 |
| **B4 / R2-C / T3-S4，设备与声学资格** | hosted/QEMU 可完成有界功能和资源归因；SSC305 vendor BSP、真实 ADC/DAC 时钟和阵列校准、全机 RAM、10 ms deadline、热/功耗、HIL/E001 仍需实际设备证据。它们不是继续写软件便会自动补齐的门禁。 | [#733 §R2-B4 / R2-C handoff](https://github.com/jiying2007/audio-pipeline/issues/733)；[compact §Compiler memory model][compact-doc]；[#58](https://github.com/jiying2007/audio-pipeline/issues/58)。 |

## 审查判断与执行分界

最小后续软件范围是 **A1 的真实资格读回 → 独立 A2 合同/故障验证、T3-S3 明确作用域的完整资源归账、B3 复用已有核心的有限整链组合**。这些是各自保留前置和失败的研究阶段；它们不属于当前 2.3.56 有限修复 tranche，也不因本文自动开放下一 major 发布。

不要从零重造 N SRC、FIR33、私有 APX3 或另做一次同样的 oracle BF/AEC 顺序实验；不要用 compact K2 的 10,648 B 或 R0 的 81,896 B 部分和取得全机 192 KiB PASS。T3-S0 已记录的超预算下界必须保留；后续优化只能在新的、范围完整且可复算的账本中给出新的结果。[T3-S0][census-doc]、[compact][compact-doc] 和 [R0][r0-doc] 明确支持这些范围限制。

[b1-code]: https://github.com/jiying2007/audio-pipeline/blob/e3672ffe16e4c9d42a100e7712b9bbd3d8338545/tests/validation/frontend_evolution/fe09_b1b1_single_bf.h
[b1-doc]: https://github.com/jiying2007/audio-pipeline/blob/e3672ffe16e4c9d42a100e7712b9bbd3d8338545/tests/validation/frontend_evolution/FE09_R2B1B_S1_SINGLE_ARRAY_BF.md
[s2-doc]: https://github.com/jiying2007/audio-pipeline/blob/e3672ffe16e4c9d42a100e7712b9bbd3d8338545/tests/validation/frontend_evolution/FE09_R2B2_S2_PRIVATE_APD_V2.md
[compact-doc]: https://github.com/jiying2007/audio-pipeline/blob/e3672ffe16e4c9d42a100e7712b9bbd3d8338545/tests/validation/frontend_evolution/FE09_T3S1_COMPACT_HANDOFF.md
[a0-doc]: https://github.com/jiying2007/audio-pipeline/blob/e3672ffe16e4c9d42a100e7712b9bbd3d8338545/tests/validation/frontend_evolution/FE09_T3S2B1B_A0_FINITE_OUTBOARD.md
[r0-doc]: https://github.com/jiying2007/audio-pipeline/blob/e3672ffe16e4c9d42a100e7712b9bbd3d8338545/docs/research/frontend-evolution-v1/ARRAY_SDK_BRIDGE_R0.md
[order-doc]: https://github.com/jiying2007/audio-pipeline/blob/e3672ffe16e4c9d42a100e7712b9bbd3d8338545/docs/research/frontend-evolution-v1/BF_AEC_ORDER.md
[census-doc]: https://github.com/jiying2007/audio-pipeline/blob/e3672ffe16e4c9d42a100e7712b9bbd3d8338545/tests/validation/frontend_evolution/FE09_T3S0_COMPILED_MEMORY_CENSUS.md
[major-doc]: https://github.com/jiying2007/audio-pipeline/blob/e3672ffe16e4c9d42a100e7712b9bbd3d8338545/docs/research/frontend-evolution-v1/FE09_R2B0_MAJOR_MIGRATION_PREFLIGHT.md
[cutover-doc]: https://github.com/jiying2007/audio-pipeline/blob/e3672ffe16e4c9d42a100e7712b9bbd3d8338545/tests/validation/frontend_evolution/FE09_R2B2_S0_RUNTIME_RECORDER_CUTOVER.md
