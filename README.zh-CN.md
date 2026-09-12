# audio-pipeline

[English](README.md) | 简体中文

`audio-pipeline` 是面向**低算力 Arm Linux 产品**的轻依赖、无动态分配实时语音前端与可组合 DSP SDK，覆盖 ARMv7-A/Cortex-A7、Cortex-A32 类 AArch32 和 AArch64 产品。CPU/SOC 型号只属于构建、测试和认证配置，不进入通用 DSP 算法依赖。

> **软件商用就绪边界：**当前仓库可标记为 `software-commercial-ready`：公开 API/ABI、Runtime 所有权、安装后 SDK、Arm/QEMU、命名的 `ssc305-cortex-a32-low` 产品构建契约、资源/性能回归、数据验证权限、Release provenance/SBOM/attestation、诊断/回放和认证控制面均由仓库 fail-closed 地验证。它可用于商业产品集成和预生产软件交付，但**不等于**板级验证或 Product Qualification。SSC305 真机 CPU/热/功耗、实际机壳/route 声学、HIL 历史和至少 72 h `product-certified` 记录仍必须由真实 DUT 证据完成。

## 中文用户从这里开始

- **中文总导航**：[`docs/README.zh-CN.md`](docs/README.zh-CN.md)
- **快速构建/集成/Runtime/Dump**：[`docs/QUICKSTART.zh-CN.md`](docs/QUICKSTART.zh-CN.md)
- **架构与线程/内存边界**：[`docs/ARCHITECTURE.zh-CN.md`](docs/ARCHITECTURE.zh-CN.md)
- **关键流程图**：[`docs/FLOWS.zh-CN.md`](docs/FLOWS.zh-CN.md)
- **开发与代码规范**：[`docs/DEVELOPMENT.zh-CN.md`](docs/DEVELOPMENT.zh-CN.md)
- **贡献规范**：[`CONTRIBUTING.zh-CN.md`](CONTRIBUTING.zh-CN.md)
- **AI/Codex/助手规范**：[`AGENTS.zh-CN.md`](AGENTS.zh-CN.md)
- **产品保障/认证边界**：[`docs/PRODUCT_ASSURANCE.zh-CN.md`](docs/PRODUCT_ASSURANCE.zh-CN.md)
- **可信 Runner 操作**：[`docs/TRUSTED_RUNNERS.zh-CN.md`](docs/TRUSTED_RUNNERS.zh-CN.md)
- **测试/数据集自测**：[`docs/TESTING.zh-CN.md`](docs/TESTING.zh-CN.md)
- **Extended Real**：[`docs/EXTENDED_REAL_VALIDATION.zh-CN.md`](docs/EXTENDED_REAL_VALIDATION.zh-CN.md)

低层 API、schema 与机器配置仍保持一个 canonical truth；中文层用于商用集成、操作和维护，不复制出第二套独立协议。

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

`ap_build_info()` 暴露版本、模块组合、几何上限、backend、source revision、compiler/target、配置 SHA-256 和 build identity；商用定位问题应优先保存这份身份。

## 产品组合与 SSC305

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

保守的 `ssc305-cortex-a32-low` 是当前商用起始 preset，required CI 会直接 configure/build 它、检查 generated envelope/build identity、clean install SDK，并以 AArch32/QEMU 运行 build-info/core/runtime consumer。

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

`.apd` 可能包含用户语音；保留周期、访问控制和安全删除属于产品责任。

## 数据集自测与迭代

`validation/` 是仓库唯一 canonical 声学验证框架，权限真相源是 [`validation/authority.json`](validation/authority.json)：

- `regression`：development/search 与回归；
- `research-validation`：研究/条件性验证，不能作为商业发货证据；
- `validation-grade`：只能 validation/shadow，不能反馈 optimizer；
- `validation-grade-blind`：仓库外 blind key，只用于独立晋级，不能进入 optimizer。

`product-certified` **不是** validation corpus tier，而是独立 `certification/` schema/policy 权限。

Extended Real 可使用 RealMAN、BUT ReverbDB、MUSAN、Mini LibriSpeech 等真实公开数据扩大远场/房间/会议/环境负例覆盖，但仍不能代替真实 DUT Product Certification。

## 资源与性能

Hosted 资源机器真相源只有 [`ci/resource-baseline.json`](ci/resource-baseline.json)，生成文档为 [`docs/generated/RESOURCE_BASELINE.md`](docs/generated/RESOURCE_BASELINE.md)。Hosted/QEMU 只用于 regression、构建与可执行契约，不得解释成芯片性能。

真机性能需真实测量 CPU p95/p99、RSS/cache/context switch、XRUN/route、thermal、power 等。

## HIL / Product Certification

真实 HIL 使用 `[self-hosted, linux, audio-target]`。Scheduled/Release 后要求硬件时执行 **fail-visible** 策略：`HIL_ENABLED!=true` 时不能静默伪装为健康 PASS。

最终 `product-certified` 要求：

- annotated semantic release tag + immutable GitHub Release；
- exact release source/build/toolchain identity；
- 独立 `audio-builder` 与 `audio-target`；
- build/deployed/executed binary SHA-256 一致；
- 真实 route/acoustic/performance/thermal/power；
- shipping-approved policy；
- 至少 **72 h** soak（当前 Cortex-A32 LOW policy）；
- artifact attestation；
- immutable `product-lifecycle` archive receipt。

Hosted CI、QEMU、公开数据、较短 HIL 或 E001 readiness 均不能替代这一步。

详见 [`docs/PRODUCT_ASSURANCE.zh-CN.md`](docs/PRODUCT_ASSURANCE.zh-CN.md) 和 [`docs/TRUSTED_RUNNERS.zh-CN.md`](docs/TRUSTED_RUNNERS.zh-CN.md)。实验室部署入口仍为 [`lab/README.md`](lab/README.md)。

## 仓库 Gate

PR/main Verify 覆盖 strict compile/test、GCC/Clang、sanitizer、TSan、CodeQL/static analysis、coverage、backend/composition、Arm/QEMU、SSC305 exact product profile、RAM/ROM pruning、paired performance、SDK consumer、diagnostics replay、deterministic acoustic regression、bounded tuning、ordinary-user lab contract 和 public API/ABI contract。

只有 exact PR/main SHA 的 required `summary=success` 才是合并/Release 权威证据。release-bearing 变化遵循 SemVer/CHANGELOG；release-neutral 文档/治理变化不得人为制造新版本。

## License

见 [LICENSE](LICENSE)。
