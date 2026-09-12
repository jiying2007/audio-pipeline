# API 契约摘要（中文）

本页是中文集成摘要。**函数签名、结构字段、ABI 和精确前置条件以 [`API_CONTRACT.md`](API_CONTRACT.md) 为唯一 canonical contract**；本页不得独立改变 public API。

## 当前兼容线

- 2.x 是当前公开 C API/ABI 兼容线；
- 当前兼容线不提供平行 compatibility alias；
- 已退役的 public symbol/name 由仓库 API/ABI contract 防止意外重新引入；
- 破坏性的 public symbol/structure 变化需要下一 major version；
- 可扩展结构使用 `struct_size`、`api_version` 和 reserved 字段维持有界兼容。

## 调用方内存

Pipeline、standalone module 与 Linux Runtime 的持久内存由调用方提供。

典型模式：

```text
读取 default config
-> 查询 state_size / required memory
-> 分配满足大小/对齐的 caller storage
-> init/open
-> process/start
-> reset/stop
-> deinit
```

`AP_ENOMEM` 表示调用方存储不足，不代表实现内部 heap 分配失败。

## 10 ms 同步 Pipeline

每次 process 固定一个 10 ms frame。调用方负责：

- 提供符合 build envelope 的 mic PCM；
- 需要 AEC 时提供匹配 route 的 far-end render；
- 提供明确的 timestamp/gap/XRUN/reset/reopen 等 metadata；
- 保持输入/输出 buffer 生命周期满足 API contract；
- 不并发访问同一个非线程安全 Pipeline state。

同步数据面内部不执行 heap、文件 I/O、网络、RPC 或格式化日志。

## Linux Runtime lifecycle

推荐顺序：

```c
ap_runtime_config_t cfg = ap_runtime_config_default();
ap_runtime_options_t opts = ap_runtime_options_default();

ap_runtime_open(memory, memory_size, pipeline, &cfg, &opts, &runtime);
ap_runtime_start(runtime);
ap_runtime_submit_frame(runtime, mic, render_or_null, metadata_or_null);
ap_runtime_receive(runtime, output, metrics_or_null);
ap_runtime_read_metrics(runtime, &runtime_metrics);
ap_runtime_stop(runtime);
ap_runtime_deinit(runtime);
```

所有权：

- `open/start` 前 live Pipeline 由调用方拥有；
- `start` 后单 DSP worker 独占 live Pipeline；
- 应用线程不能绕过 Runtime 直接读写 Pipeline；
- frame/control/output 通过有界通道交互；
- `read_metrics` 读取 Runtime-owned telemetry；
- stop/deinit 后按英文 canonical contract 恢复/结束所有权。

## 状态码

常见语义：

- `AP_OK`：成功；
- `AP_EINVAL`：参数、范围、结构版本或非有限 float 等输入非法；
- `AP_ENOMEM`：caller-provided storage 不足；
- `AP_ESTATE`：build capability/lifecycle 当前状态不允许该操作。

不要把“未编译 feature”伪装成普通成功 bypass。

## 浮点输入

Public float 先检查 `finite`，再检查范围。NaN、+Inf、-Inf 必须作为非法输入处理；fast-math 配置也必须保持该 public contract。

## Standalone module

Stateful standalone module 统一遵循：

```text
state_size
-> aligned caller storage
-> init
-> reset（需要时）
-> process/status
```

Standalone API 复用 stage 实现，不复制算法分叉。

## Metadata 与 route 事实

时间戳/断流/XRUN/clock reset/codec reopen/lost frame 是系统事实，不应让 DSP 通过音频波形猜测。Route/path reset 会建立新的收敛 epoch；AEC/同步 telemetry 的解释必须尊重该 epoch。

## Metrics

Runtime/DSP metrics 用于运行监控和回归，包括 queue pressure、failed frame、scheduler 状态、长期计数以及 DSP latency percentile 等。

Hosted/QEMU metrics 不能直接解释成 SSC305 真机性能。

## Build identity

`ap_build_info()` 返回当前 build 的关键身份：

- project version；
- modules/composition；
- geometry envelope；
- backend/SIMD/resampler 等选择；
- source revision；
- compiler/target；
- config/build SHA-256 identity。

线上问题、dump、benchmark、HIL 和 certification evidence 都应尽可能携带同一 build identity。

## ABI/SDK 消费

安装后支持 CMake package 与 pkg-config。CI 从 clean prefix 实际 compile/link/run consumer；仅检查头文件/库文件存在不算 SDK contract。

## 修改 public API 前

至少回答：

1. 是否兼容当前 2.x ABI？
2. 是否需要 `struct_size`/reserved 扩展？
3. invalid/lifecycle/error semantics 是否明确？
4. caller memory/state size 是否变化？
5. thread ownership 是否变化？
6. SDK consumer/ABI/negative test 是否覆盖？
7. 是否属于 release-bearing/SemVer 变化？

无法证明当前兼容线内 ABI 兼容时，不应直接修改公开契约；应进入下一 major version 设计。
