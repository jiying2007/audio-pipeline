# audio-pipeline

[English](README.md) | 简体中文

面向**低算力 Arm Linux 产品族**的轻依赖、无堆分配实时语音前端与可组合 DSP SDK。目标不是绑定某一颗 CPU，而是在同一代码资产上长期覆盖 ARMv7-A、ARMv8-A/AArch32 以及同等语音算力档位的 AArch64 产品，例如 Cortex-A7、Cortex-A32 等。

高层 pipeline 采用拓扑安全的固定顺序：

`S16采集 -> 边界采样率适配 -> HPF -> 双麦BF -> 延时/时钟漂移 -> AEC -> RES -> STFT Wiener NS -> AGC -> VAD -> 单声道S16`

公共帧长固定 10 ms；设备侧支持 8/16/24/32/48 kHz，重 DSP 始终工作在 8 或 16 kHz。同步数据面全部使用调用者提供的有界内存，不 malloc、不加 mutex，也不做运行时 SIMD/插件分发。

## 两种正式使用方式

**高层组合 pipeline。** `ap_config_t.stages` 选择当前 binary 已编入模块的合法运行时子集。顺序固定并在 init 时校验，不提供任意 DAG。可形成完整 CALL、capture-only voice frontend、RAW rate-adapter 等链路。

**独立 Module SDK。** `audio_pipeline/audio_modules.h` 提供 Resampler、HPF、BF、Sync、AEC、RES、NS、AGC、VAD 的 caller-owned standalone API。它们直接复用高层 pipeline 的同一内部算法实现，不维护第二套 DSP。

编译期产品组合：

```text
AP_BUILD_PIPELINE=ON|OFF
AP_MODULES=RESAMPLER,HPF,BF,SYNC,AEC,RES,NS,AGC,VAD
```

模块从 `AP_MODULES` 移除后，不只是运行时 bypass，而是对应 translation unit 和 pipeline 常驻 state 都从构建中物理移除。安装后的 generated `audio_pipeline_build.h` 通过 `AP_HAVE_PIPELINE` / `AP_HAVE_MODULE_*` 给出当前 SDK 的能力事实源。

代表性 preset：

```bash
cmake --preset composition-full
cmake --preset composition-voice-frontend
cmake --preset composition-raw
cmake --preset composition-aec-only
cmake --preset composition-ns-only
```

当前 GCC CI 的 state-size gate 实测：完整图 **78,456 B**、voice frontend **9,936 B**、RAW/resampler-only **3,392 B**。这些数字用于证明物理裁剪成立，不是跨 ABI/compiler 永久常量；产品必须使用对应 build 的精确 `*_state_size()`。

## 组合约束

init 阶段统一校验：

- BF 必须是双麦；
- AEC 必须有 SYNC/reference alignment；
- RES 必须有 AEC；
- delay/drift 子策略必须有 SYNC；
- runtime `stages` 必须是当前 binary 已编译 stage 的子集。

RAW pipeline 可以没有任何 `AP_STAGE_*` DSP bit；RESAMPLER 属于边界模块而不是 DSP stage。capture-only 组合不要求 render reference，Linux runtime 也只在存在 SYNC 时提交 render。

## 三个独立产品维度

- **场景**：`AP_PROFILE_CALL` / `AP_PROFILE_ASSISTANT`；
- **资源档**：`AP_RESOURCE_TINY` / `AP_RESOURCE_LOW` / `AP_RESOURCE_STANDARD`；
- **运行时质量状态**：`FULL` / `LITE` / `SAFE`。

`TINY` 默认使用 8 kHz 内部链路、短 AEC tail、关闭 BF 跟踪；`LOW` 保持 16 kHz 但缩短 AEC tail；`STANDARD` 保留完整语音带宽几何。它们不是 Cortex-A7/A32 的硬编码映射，最终仍按实板认证。

## 模块边界

```text
src/core/            pipeline/config/编排
src/frontend/        resampler、HPF、BF
src/sync/            render延时与时钟漂移
src/aec/             MDF/NLMS编译期后端
src/enhance/         RES、NS、AGC、VAD
src/modules/         public standalone adapter
src/dsp/             FFT/数学基础
src/arch/scalar/     纯C scalar kernel
src/arch/arm_neon/   Arm NEON kernel
src/platform/linux/  Linux pthread/semaphore SPSC runtime
```

算法 stage 不依赖 public module wrapper；wrapper 只向下调用 stage，core 也不会反过来经过 wrapper。完整 pipeline 保留 CMake unity compilation 以维持跨模块 inline，但源码所有权/state 边界仍独立。

## 构建策略

正式构建开关：

```text
AP_BUILD_PIPELINE=ON|OFF
AP_MODULES=...
AP_AEC_BACKEND=MDF|NLMS
AP_NS_ESTIMATOR=EMA|MCRA
AP_SIMD_BACKEND=SCALAR|NEON
AP_ENABLE_LINUX_RUNTIME=ON|OFF
AP_ENABLE_FAST_MATH=ON|OFF
```

`fast-math` 默认 OFF，属于产品性能策略，不写死到 CPU toolchain。

本机 Linux：

```bash
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build --parallel
ctest --test-dir build --output-on-failure
```

跨平台 preset：

```bash
cmake --preset armv7a-scalar
cmake --preset cortex-a7-scalar
cmake --preset cortex-a7-neon
cmake --preset cortex-a32-neon
cmake --preset aarch64-neon
```

## 调用者内存合同

高层 pipeline 公共静态上限为 80,000 B；standalone 模块使用独立 `AP_MODULE_STATE_MAX_BYTES` 与 `AP_MODULE_STATE_ALIGNMENT`。产品分配应优先使用当前 build 对应的精确 `*_state_size()`。

```c
_Alignas(AP_PIPELINE_STATE_ALIGNMENT)
static unsigned char pipeline_mem[AP_PIPELINE_STATE_MAX_BYTES];

ap_pipeline_t *pipeline = NULL;
ap_config_t cfg = ap_config_for_resource(AP_PROFILE_CALL, AP_RESOURCE_LOW);
cfg.stages = AP_STAGE_HPF | AP_STAGE_NS | AP_STAGE_AGC | AP_STAGE_VAD;
ap_status_t rc = ap_pipeline_init(pipeline_mem, sizeof(pipeline_mem), &cfg, &pipeline);
```

NULL、非法参数、未对齐内存返回 `AP_EINVAL`；内存不足返回 `AP_ENOMEM`；请求当前 SDK 未编译的 stage 返回 `AP_ESTATE`。

## AEC / 同步 / 增强

默认 AEC 为 clean-room MDF/AUMDF-lite；`AP_AEC_BACKEND=NLMS` 编译独立 NLMS。默认 NS noise estimator 为 EMA；clean-room MCRA-lite 仍是 opt-in backend。

render reference 必须是实际送 DAC 的 post-mix/post-gain 信号。大路径跳变会重置 AEC，小漂移通过 sample-slip 修正。FULL/LITE 在 RES+NS 同时选择时使用频率相关 RES；SAFE 使用宽带 RES；共享 double-talk gate 会冻结 AEC adaptation 并关闭 subband RES。

## Linux runtime

portable core 不依赖 Linux。`AP_ENABLE_LINUX_RUNTIME=ON` 才构建 Linux SPSC worker。默认 `dsp_cpu=-1`、`dsp_priority=0`。runtime 已支持 capture-only composed pipeline，只有选择 SYNC 时才要求/提交 render。

## CI 与平台覆盖

CI 覆盖 GCC/Clang、strict、ASan/UBSan、fuzz、MDF/NLMS、EMA/MCRA、fast-math、ALSA、架构边界、full/RAW/voice/AEC-only/NS-only composition、物理 RAM pruning、same-runner regression，以及 generic ARMv7-A、Cortex-A7 scalar/NEON、Cortex-A32 NEON、AArch64 NEON cross-build。

Hosted x86 timing 只作为回归信号。Cross-build 代表**构建支持**，不代表实板认证。CPU、RSS、温升、功耗仍必须在出货板卡、内核、编译器、DVFS、音频路由下重新跑 benchmark 与 8h soak。

## 文档

- [平台支持与认证](docs/PLATFORM_SUPPORT.md)
- [架构](docs/ARCHITECTURE.md)
- [API 合同](docs/API_CONTRACT.md)
- [DSP 设计](docs/DSP_DESIGN.md)
- [移植](docs/PORTING.md)
- [性能与发布门禁](docs/PERFORMANCE.md)
- [调参](docs/TUNING.md)
- [开发/模块规范](docs/DEVELOPMENT.md)

## License

Apache-2.0。最小实现不 vendoring 第三方 DSP 源码，详见 [THIRD_PARTY.md](THIRD_PARTY.md)。
