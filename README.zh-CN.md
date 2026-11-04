# audio-pipeline

[English](README.md) | 简体中文

`audio-pipeline` 是面向**低算力 Arm Linux 嵌入式研究平台**的轻依赖、无动态分配实时语音前端与可组合 DSP SDK，覆盖 ARMv7-A/Cortex-A7、Cortex-A32 类 AArch32 和 AArch64。CPU/SoC 型号属于构建和实验配置，不进入通用 DSP 算法依赖。

> **纯技术研究定位**：以可复现的 DSP/音频前端算法、多麦克风、独立声学验证、ARM/SSC305 类资源和嵌入式运行时为目标。数据、训练、实验和评测不要求商业导入批准、Shipping SKU、GitHub Release 发布或 72 小时产品认证。原有自动 Release、产品认证 Actions 已退役；剩余历史命名按[清理跟踪 #882](https://github.com/jiying2007/audio-pipeline/issues/882)迁移，不得阻塞科研。参见[研究执行边界](docs/RESEARCH_ONLY_EXECUTION.md)。保留真实来源/许可、独立测试、数据权益、可复现证据和物理板实测要求。

## 中文用户从这里开始

- **中文总导航**：[`docs/README.zh-CN.md`](docs/README.zh-CN.md)
- **快速构建/集成/Runtime/Dump**：[`docs/QUICKSTART.zh-CN.md`](docs/QUICKSTART.zh-CN.md)
- **架构与线程/内存边界**：[`docs/ARCHITECTURE.zh-CN.md`](docs/ARCHITECTURE.zh-CN.md)
- **关键流程图**：[`docs/FLOWS.zh-CN.md`](docs/FLOWS.zh-CN.md)
- **开发与代码规范**：[`docs/DEVELOPMENT.zh-CN.md`](docs/DEVELOPMENT.zh-CN.md)
- **贡献规范**：[`CONTRIBUTING.zh-CN.md`](CONTRIBUTING.zh-CN.md)
- **AI/Codex/助手规范**：[`AGENTS.zh-CN.md`](AGENTS.zh-CN.md)
- **历史产品保障/认证资料（非研究准入）**：[`docs/PRODUCT_ASSURANCE.zh-CN.md`](docs/PRODUCT_ASSURANCE.zh-CN.md)
- **可信 Runner 操作**：[`docs/TRUSTED_RUNNERS.zh-CN.md`](docs/TRUSTED_RUNNERS.zh-CN.md)
- **测试/数据集自测**：[`docs/TESTING.zh-CN.md`](docs/TESTING.zh-CN.md)
- **Extended Real**：[`docs/EXTENDED_REAL_VALIDATION.zh-CN.md`](docs/EXTENDED_REAL_VALIDATION.zh-CN.md)

低层 API、schema 与机器配置仍保持一个 canonical truth；中文层用于技术研究复现、操作和维护，不复制出第二套独立协议。

## 默认音频链路

```text
S16 采集
-> 采样率适配
-> HPF
-> 双麦 BF
-> SYNC
-> Activity / DTD
-> AEC
-> RES
-> NS
-> AGC
-> VAD
-> 单声道 S16
```

帧长固定 10 ms。设备 I/O 在编译 envelope 内支持 8/16/24/32/48 kHz；重 DSP 运行于 8/16 kHz。Pipeline/standalone module/Runtime 的持久状态均由调用方提供有界内存。

## Public API / Runtime

当前 2.x 是唯一 public C API/ABI 兼容线；不兼容的 public symbol/structure 变化必须进入下一 major version，当前兼容线不提供平行 compatibility alias。

Linux Runtime 典型生命周期：

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

worker started 后独占 live Pipeline。公开契约以 [`docs/API_CONTRACT.md`](docs/API_CONTRACT.md) 为准。

`ap_build_info()` 暴露版本、模块组合、几何上限、backend、source revision、compiler/target、配置 SHA-256 和 build identity；研究复现和性能归因应保存这份身份。

## 算法模块组合与 SSC305 研究

主要 build envelope：

```text
AP_MODULES
AP_BUILD_MAX_IO_RATE_HZ
AP_BUILD_MAX_INTERNAL_RATE_HZ
AP_BUILD_MAX_MIC_CHANNELS
AP_BUILD_MAX_DELAY_MS
AP_BUILD_MAX_AEC_TAIL_MS
AP_RUNTIME_QUEUE_DEPTH
```

Backend：

```text
AP_AEC_BACKEND=MDF|NLMS
AP_NS_ESTIMATOR=EMA|MCRA
AP_SIMD_BACKEND=SCALAR|NEON
AP_RESAMPLER_MODE=BANDLIMITED|FAST
```

保守的 `ssc305-cortex-a32-low` 是可复现的嵌入式构建/资源研究 preset。必需 CI 会 configure/build、校验生成的 envelope/build identity、clean install SDK，并以 AArch32/QEMU 运行 build-info/core/runtime consumer。

该 Gate 证明**软件构建与集成**，不代表 SSC305 真机性能。

## Native 构建与安装

```bash
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release -DAP_STRICT_WARNINGS=ON
cmake --build build --parallel
ctest --test-dir build --output-on-failure
cmake --install build --prefix "$PWD/install"
```

安装后：

```cmake
find_package(AudioPipeline CONFIG REQUIRED)
target_link_libraries(app PRIVATE AudioPipeline::core)
# Linux Runtime 可选
target_link_libraries(app PRIVATE AudioPipeline::runtime)
```

详细步骤见 [`docs/QUICKSTART.zh-CN.md`](docs/QUICKSTART.zh-CN.md)。

## Realtime / Diagnostics

Realtime stage/core/module 禁止 heap、mutex、文件/网络 I/O、RPC、格式化日志和无界工作。Linux 控制面与 realtime data plane 分离。

Dump/Replay：

```bash
python3 tools/apdump.py info failure.apd
python3 tools/apdump.py extract failure.apd --output-dir extracted
python3 tools/apreplay.py failure.apd \
  --processor ./build/ap_process_pcm \
  --output-pcm replay.pcm
```

`.apd` 可能包含真实语音；数据处理方须按实际许可和隐私要求管理保留周期、访问控制与安全删除。

## 数据集自测与迭代

`validation/` 是仓库唯一 canonical 声学验证框架，权限真相源是 [`validation/research-authority.json`](validation/research-authority.json)：

- `regression`：development/search 与回归；
- `research-validation`：研究/条件性验证，不自动代表真实家庭或目标板效果；
- `validation-grade`：只能 validation/shadow，不能反馈 optimizer；
- `validation-grade-blind`：仓库外 blind key，仅供独立后选验证，不能进入 optimizer。

历史 `product-certified` **不是科研数据集分层**。其原始 schema/policy 保留在 `certification/` 供溯源，活动产品认证入口已退役；科学评估按独立数据、来源/标签与实际目标板测量判断。

Extended Real 可使用 RealMAN、BUT ReverbDB、MUSAN、Mini LibriSpeech 等真实公开数据扩大远场/房间/会议/环境负例覆盖，但它们不能替代真实 DUT 的 CPU、音频路径、功耗和连续运行实测。

## 资源与性能

Hosted 资源机器真相源只有 [`ci/resource-baseline.json`](ci/resource-baseline.json)，生成文档为 [`docs/generated/RESOURCE_BASELINE.md`](docs/generated/RESOURCE_BASELINE.md)。Hosted/QEMU 只用于 regression、构建与可执行契约，不得解释成芯片性能。

真机性能需真实测量 CPU p95/p99、RSS/cache/context switch、XRUN/route、thermal、power 等。

## HIL / 物理目标板研究测量

真实 HIL 依赖可信 `[self-hosted, linux, audio-target]` Runner，必须显式绑定源码、构建和实际测量。可开展 10 分钟、1 小时、8 小时、24 小时或 72 小时等有界实验；**72 小时不是研究代码或算法评估的商业准入门槛**。

请求硬件测试但尚未配置时，`HIL_ENABLED!=true` 采取 **fail-visible** 策略，不能将不可用、跳过或等待真机的状态伪装为 PASS。没有真实采集时标记 NOT_RUN/BLOCKED。Host/QEMU 只能证明源码构建与软件回放，不应冒充 SSC305 真机测量。

科研报告按需记录真实 build/deployed/executed SHA-256、板端 CPU/RSS/p95/p99、音频路径连续性、独立声学效果、温度/功耗及连续运行时长。每种结论必须由其真实数据支持，历史 Shipping 证书和产品长稳策略仅供溯源，不参与科研放行。实验室路径见 [lab/README.md](lab/README.md) 与 [可信 Runner](docs/TRUSTED_RUNNERS.zh-CN.md)。

## 仓库 Gate

PR/main Verify 覆盖 strict compile/test、GCC/Clang、sanitizer、TSan、CodeQL/static analysis、coverage、backend/composition、Arm/QEMU、SSC305 exact research profile、RAM/ROM pruning、paired performance、SDK consumer、diagnostics replay、deterministic acoustic regression、bounded tuning、ordinary-user lab contract 和 public API/ABI contract。

受保护研究主线以 exact PR/main SHA 的 required `summary=success` 为合并质量依据。公开 API/ABI 版本变更遵循 SemVer/CHANGELOG；研究文档、数据与治理变更不人为制造版本，Verify 成功也**不自动触发 GitHub 产品 Release 或产品认证**。

## License

见 [LICENSE](LICENSE)。
