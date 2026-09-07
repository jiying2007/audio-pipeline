# 架构说明（中文）

本页给出面向集成和维护的中文架构视图。模块/API 的低层细节分别以 [`ARCHITECTURE.md`](ARCHITECTURE.md)、[`API_CONTRACT.md`](API_CONTRACT.md) 与源码为准。

## 设计目标

`audio-pipeline` 面向低算力 Arm Linux 产品，核心目标是：

- 实时数据面有界、可预测；
- 产品 SKU 可通过编译期组合和几何 envelope 裁剪；
- CPU/平台差异隔离在 arch/platform 层，不污染算法；
- Runtime、DSP、验证、HIL、Product Certification 各自拥有清晰 authority；
- 每个发货构建都可通过 build identity 追溯源码、配置、编译器和模块组合。

## 分层

```text
应用/产品
  |
  +-- public C API / installed SDK
  |
  +-- Linux Runtime (platform/linux)
  |      |
  |      +-- bounded queues / worker / scheduling / telemetry
  |
  +-- Pipeline core
         |
         +-- frontend / sync / activity / aec / enhance
         |
         +-- dsp / arch
```

允许的生产依赖方向：

```text
core -> frontend / sync / activity / aec / enhance
modules -> frontend / sync / activity / aec / enhance
frontend/sync/activity/aec/enhance -> dsp/arch（按需）
platform/linux -> public pipeline API
```

Stage 不得反向依赖 `src/modules`、core 或 Linux Runtime。Sibling stage 间的影响通过 event/result 交给 core 解释，不建立隐藏耦合。

## 10 ms 数据契约

Pipeline 以固定 10 ms frame 工作。设备 I/O 可在构建 envelope 内选择 8/16/24/32/48 kHz；重 DSP 在 8/16 kHz 工作。

输入事实包括：

- mic PCM；
- 可选 far-end render；
- timestamp；
- gap/lost-frame；
- XRUN；
- clock reset；
- codec reopen/route reset。

这些事实必须显式进入 metadata/控制面，不能靠算法猜测系统事件。

## 内存模型

同步 Pipeline、standalone module 和 Runtime 的持久状态均由调用方提供有界内存。核心原则：

- data plane 无 heap allocation；
- SKU 几何上限决定实际 state 大小；
- 未编译模块真实移除实现 TU/state，不是 runtime bypass；
- state/ELF pruning 由 CI 直接验证；
- 安装后的 consumer 也必须能链接并运行，而不是只检查文件存在。

## 模块组合与 SKU envelope

主要编译维度：

```text
AP_MODULES
AP_BUILD_MAX_IO_RATE_HZ
AP_BUILD_MAX_INTERNAL_RATE_HZ
AP_BUILD_MAX_MIC_CHANNELS
AP_BUILD_MAX_DELAY_MS
AP_BUILD_MAX_AEC_TAIL_MS
AP_RUNTIME_QUEUE_DEPTH
```

主要 backend：

```text
AP_AEC_BACKEND=MDF|NLMS
AP_NS_ESTIMATOR=EMA|MCRA
AP_SIMD_BACKEND=SCALAR|NEON
AP_RESAMPLER_MODE=BANDLIMITED|FAST
```

当前 SSC305 软件商用起始配置 `ssc305-cortex-a32-low` 已成为 required CI 的独立 executable contract。它不代表真机性能认证。

## Runtime ownership

Pipeline 在 `ap_runtime_open()` 前由调用方拥有；worker started 后由单 DSP worker 独占 live Pipeline。

调用方只能通过 Runtime API：

- submit frame；
- receive output；
- read metrics；
- stop/deinit；
- 使用受控 control/event 通道。

应用线程不能在 worker started 后直接读取或修改 Pipeline state。任何 ownership/counter/queue/lifecycle 改动必须通过 TSan。

## Realtime 与 Control Plane 分离

### Realtime data plane 禁止

- heap allocation；
- mutex；
- 文件/网络 I/O；
- RPC；
- 格式化日志；
- runtime plugin/backend discovery；
- 依赖 CPU 型号名称的算法分支。

### Control plane 可负责

- Linux scheduling/thread lifecycle；
- 文件/配置加载；
- dump/replay 管理；
- self-hosted runner/toolchain/DUT 编排；
- validation/HIL/certification evidence sealing。

## Diagnostics

Realtime 只写固定大小 diagnostics/Flight Recorder 状态；文件 I/O、JSON 和 replay 在实时线程之外完成。

典型链路：

```text
Runtime/DSP event -> bounded diagnostics -> .apd -> apdump -> apreplay -> reproducer
```

## 验证权限架构

`validation/` 是仓库内唯一 canonical 声学验证框架。`validation/authority.json` 决定哪些数据可用于 development/search、validation/shadow 或 blind promotion。

`product-certified` 不属于 validation corpus tier。最终产品权限来自独立 `certification/` schema/policy + 真实 DUT/HIL/72 h evidence。

因此以下层次不可互相替代：

```text
unit/property/hosted CI
  < public-data validation
  < Extended Real
  < real DUT/HIL
  < Product Certification / product-certified
```

## Build identity

`ap_build_info()` 暴露版本、模块、几何上限、backend、source revision、compiler/target 和配置 SHA-256。定位商用问题时，build identity 是第一层 provenance，不应只依赖包名、tag 名或人工记录。

## 架构变更准入

新增架构复杂度必须说明：

1. 解决的真实或可重复失败是什么；
2. 为什么不能在当前边界内解决；
3. 新状态/线程/队列/延迟/内存成本；
4. 如何 fail-closed；
5. targeted/negative/TSan/ABI/resource/Arm/QEMU 测试；
6. 是否影响 shipping behavior、SemVer 或 Product Certification。

没有明确收益证据时，保留更简单的实现。
