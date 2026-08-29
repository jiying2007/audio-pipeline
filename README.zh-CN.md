# audio-pipeline

[English](README.md) | 简体中文

`audio-pipeline` 是面向**低算力 Arm Linux 产品**的轻依赖、无动态分配实时语音前端与可组合 DSP SDK，覆盖 ARMv7-A/Cortex-A7、Cortex-A32 类 AArch32 和 AArch64 产品。CPU 型号只属于构建、测试和认证配置，不进入 DSP 算法依赖。

默认高层链路：

`S16采集 -> 采样率适配 -> HPF -> 双麦BF -> SYNC -> Activity/DTD -> AEC -> RES -> NS -> AGC -> VAD -> 单声道S16`

帧长固定为 10 ms。设备 I/O 在编译包络内支持 8/16/24/32/48 kHz；重 DSP 运行在 8 或 16 kHz。DSP 与 Runtime 的持久状态均由调用方提供有界内存。

## v2 硬切 API

2.0.0 建立新的公开 C API/ABI 基线。已经移除的 1.x 代际 wrapper **不声明、不导出、也不提供兼容 alias**。

当前 Linux Runtime 只有一套入口：

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

`ap_build_info()` 同样只返回一套完整 `ap_build_info_t`，包含版本、模块组合、几何上限、后端、源码 revision、编译器/目标/build identity 和配置 SHA-256。

公开契约以 [`docs/API_CONTRACT.md`](docs/API_CONTRACT.md) 为准。

## 组合与产品包络

高层 Pipeline 使用 `ap_config_t.stages` 选择合法 stage 子集；`audio_pipeline/audio_modules.h` 提供 resampler、HPF、BF、SYNC、Activity/DTD、AEC、RES、NS、AGC、VAD 的 standalone API。

编译期组合：

```text
AP_BUILD_PIPELINE=ON|OFF
AP_MODULES=RESAMPLER,HPF,BF,SYNC,ACTIVITY,AEC,RES,NS,AGC,VAD
```

未加入 `AP_MODULES` 的模块会真实移除实现 TU 与 resident state，不是运行时 bypass。

发货 SKU 还可以限制最大几何：

```text
AP_BUILD_MAX_IO_RATE_HZ
AP_BUILD_MAX_INTERNAL_RATE_HZ
AP_BUILD_MAX_MIC_CHANNELS
AP_BUILD_MAX_DELAY_MS
AP_BUILD_MAX_AEC_TAIL_MS
AP_RUNTIME_QUEUE_DEPTH
```

Hosted 资源测量只有一个机器真相源：[`ci/resource-baseline.json`](ci/resource-baseline.json)；[`docs/generated/RESOURCE_BASELINE.md`](docs/generated/RESOURCE_BASELINE.md) 由它生成。Hosted 测量只证明 CI 声明的 build contract，不代表实板性能。

## DSP 与实时策略

- AEC：MDF 默认，NLMS 可选。
- NS：EMA 默认，MCRA 可选。
- SIMD：编译期 SCALAR / NEON。
- Resampler：BANDLIMITED 默认，FAST 为显式低成本模式。
- fast-math：默认关闭。
- Linux Runtime：有界 SPSC 数据队列、有界控制/事件队列、单 DSP worker。
- worker 启动后独占 Pipeline；output backpressure 只丢发布结果，不跳过已经接受的 DSP frame。
- frame metadata 统一携带时间戳、断流、XRUN、clock reset、codec reopen 和 lost-frame 信息。
- Runtime metrics 统一提供长期计数、failed frame、queue pressure、scheduler 状态以及 DSP p50/p95/p99。

算法细节见 [`docs/DSP_DESIGN.md`](docs/DSP_DESIGN.md)，性能策略见 [`docs/PERFORMANCE.md`](docs/PERFORMANCE.md)。

## Diagnostics / Dump / Replay

`audio_pipeline/audio_diag.h` 提供固定大小事件与可选 Flight Recorder。10 ms realtime worker 不执行文件 I/O、heap allocation、JSON 编码或格式化日志。

```bash
python3 tools/apdump.py info failure.apd
python3 tools/apdump.py extract failure.apd --out-dir extracted
python3 tools/apreplay.py failure.apd --processor ./build/ap_process_pcm --work-dir replay
```

音频 dump 可能包含用户语音，保留周期、访问控制与安全删除属于产品责任。详见 [`docs/DIAGNOSTICS.md`](docs/DIAGNOSTICS.md)。

## 验证可信等级

`validation/` 强制区分四层证据：

- `regression`：确定性生成的 CI fixture；
- `validation-grade`：固定 revision 并本地 seal 的公共数据；
- `validation-grade-blind`：仓库外 HMAC key 划分的 blind holdout；
- `product-certified`：真实发货硬件/音频 route 加 performance、thermal、power、acoustic、soak 证据。

公共数据源锁定 Microsoft AEC Challenge、Microsoft DNS Challenge 和 OpenSLR SLR28 元数据，大型 corpus 不进入 Git。

大规模公共验证只在可信 `audio-validation` runner 上执行，并先通过 readiness 和 dataset seal。详见 [`validation/README.md`](validation/README.md) 与 [`docs/TRUSTED_RUNNERS.md`](docs/TRUSTED_RUNNERS.md)。

## HIL 与发货认证

真实板 HIL 使用可信 `[self-hosted, linux, audio-target]` runner，并执行板卡本地 metadata、readiness、preflight/cleanup 与 evidence sealing。

分层 soak 为 10 分钟 / 1 小时 / 8 小时 / 24 小时 / 72 小时。Scheduled / Release 后 HIL 是 **fail-visible**：当 `HIL_ENABLED!=true` 时 availability gate 必须失败，不能静默 skip，更不能伪造 PASS。

HIL 历史不等于产品认证。当前 `product-certified` 只接受 **certification schema v4**，并绑定：

- shipping-approved SKU policy；
- exact source/build/toolchain identity；
- 独立 `audio-builder` 与 `audio-target` runner；
- build/deployed/executed binary SHA-256 完全一致；
- 真实 CPU/RSS/p95/p99 与 audio route evidence；
- 真实声学 corpus；
- 实测 thermal / power；
- policy 要求的 route soak；
- artifact attestation；
- immutable `product-lifecycle` archive receipt。

仓库内 Cortex-A32 LOW shipping policy 要求至少 **72 h**。Hosted CI、QEMU、公共数据验证以及较短 HIL 都不能替代这一步。

详见 [`certification/README.md`](certification/README.md) 与 [`docs/PRODUCT_ASSURANCE.md`](docs/PRODUCT_ASSURANCE.md)。

## 构建与安装

Native Linux：

```bash
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build --parallel
ctest --test-dir build --output-on-failure
```

Arm presets 覆盖 generic ARMv7-A、Cortex-A7 scalar/NEON、Cortex-A32 NEON 和 AArch64 NEON。部分可执行 contract 会在 QEMU 下运行，但 QEMU 时间不能作为芯片性能结论。

安装后的 SDK：

```cmake
find_package(AudioPipeline CONFIG REQUIRED)
target_link_libraries(app PRIVATE AudioPipeline::core)
# 可选 Linux Runtime：
target_link_libraries(app PRIVATE AudioPipeline::runtime)
```

CI 会从干净 install prefix 构建 CMake / pkg-config consumer。

## 仓库 Gate

PR/main Verify 包含 strict compile/test、GCC/Clang、sanitizer、TSan、static analysis、coverage、backend/composition matrix、Arm cross-build/QEMU、RAM/ROM pruning、paired performance、diagnostics replay、确定性 acoustic regression，以及 v2 API/symbol hard-cut contract。

所有 `main` push 都执行完整 Verify。Release 只有在 exact main SHA 的 required `summary` 成功后，才创建 tag、Release assets 与 attestation。

真实公共数据验证、HIL 与 Product Certification 始终与 hosted CI 分离。

## 文档

- [`docs/API_CONTRACT.md`](docs/API_CONTRACT.md) — v2 API/状态/线程契约
- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — 架构与所有权
- [`docs/DSP_DESIGN.md`](docs/DSP_DESIGN.md) — 算法设计
- [`docs/PERFORMANCE.md`](docs/PERFORMANCE.md) — 性能/资源 Gate
- [`docs/DIAGNOSTICS.md`](docs/DIAGNOSTICS.md) — 事件、Dump、Replay
- [`docs/PORTING.md`](docs/PORTING.md) — BSP/ALSA/toolchain 集成
- [`docs/TESTING.zh-CN.md`](docs/TESTING.zh-CN.md) — CI/HIL 策略
- [`docs/TRUSTED_RUNNERS.md`](docs/TRUSTED_RUNNERS.md) — self-hosted runner readiness
- [`certification/README.md`](certification/README.md) — v4 发货认证
- [`THIRD_PARTY.md`](THIRD_PARTY.md) — 第三方/reference 规则

## License

见 [LICENSE](LICENSE)。
