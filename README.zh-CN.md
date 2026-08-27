# audio-pipeline

[English](README.md) | 简体中文

面向**低算力 Arm Linux 产品族**的轻依赖、无堆分配实时语音前端。目标不是绑定某一颗 CPU，而是在同一套 DSP 核心上长期覆盖 ARMv7-A、ARMv8-A/AArch32 以及同等语音算力档位的 AArch64 产品，例如 Cortex-A7、Cortex-A32 等。

默认链路：

`S16采集 -> 边界采样率适配 -> HPF -> 双麦波束形成 -> 延时/时钟漂移 -> AEC -> RES -> STFT Wiener NS -> VAD -> AGC/限幅 -> 单声道S16`

公共帧长固定 10 ms；设备侧支持 8/16/24/32/48 kHz，重 DSP 始终工作在 8 或 16 kHz。同步数据面全部使用调用者提供的有界内存，不 malloc、不加 mutex，也不做运行时 SIMD 分发。

## 三个独立产品维度

不再把 CPU 型号直接等同于算法档位：

- **场景**：`AP_PROFILE_CALL` / `AP_PROFILE_ASSISTANT`；
- **资源档**：`AP_RESOURCE_TINY` / `AP_RESOURCE_LOW` / `AP_RESOURCE_STANDARD`，产品配置阶段选择；
- **运行时质量状态**：`FULL` / `LITE` / `SAFE`，用于过载降级与恢复。

`TINY` 默认使用 8 kHz 内部链路、短 AEC tail、关闭波束跟踪；`LOW` 保持 16 kHz 但缩短 AEC tail；`STANDARD` 保留完整语音带宽几何。它们只是起始资源包络，不是“Cortex-A7=某档、Cortex-A32=某档”的硬编码，最终仍按实板数据认证。

## 模块边界

```text
src/core/            pipeline/config/编排
src/frontend/        边界resampler、HPF、beamformer
src/sync/            render延时与时钟漂移
src/aec/             编译期MDF或NLMS后端
src/enhance/         RES、Wiener NS、AGC、VAD
src/dsp/             FFT/数学基础
src/arch/scalar/     纯C scalar kernel
src/arch/arm_neon/   Arm NEON kernel
src/platform/linux/  Linux pthread/semaphore SPSC runtime
```

算法模块不直接包含 `arm_neon.h`，也不直接依赖 pthread/semaphore。SIMD/AEC 均为编译期选择，因此模块化不会在 10 ms 热路径中引入虚函数、插件或函数指针分发。

## 构建策略

正式构建开关为：

```text
AP_AEC_BACKEND=MDF|NLMS
AP_SIMD_BACKEND=SCALAR|NEON
AP_ENABLE_LINUX_RUNTIME=ON|OFF
AP_ENABLE_FAST_MATH=ON|OFF
```

`fast-math` 默认 **OFF**，它属于产品性能策略，不再写死到 CPU toolchain。

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
cmake --build build/cortex-a7-neon --parallel
```

通用 toolchain 只描述 compiler/ABI；`-mcpu/-mfpu` 放在 preset 或具体产品构建配置中。

## 调用者内存合同

实际大小由 `ap_pipeline_state_size()` 返回，公共硬上限为 80,000 B，内存必须满足 16-byte 对齐：

```c
_Alignas(AP_PIPELINE_STATE_ALIGNMENT)
static unsigned char pipeline_mem[AP_PIPELINE_STATE_MAX_BYTES];

ap_pipeline_t *pipeline = NULL;
ap_config_t cfg = ap_config_for_resource(AP_PROFILE_CALL, AP_RESOURCE_LOW);
ap_status_t rc = ap_pipeline_init(pipeline_mem, sizeof(pipeline_mem), &cfg, &pipeline);
```

NULL、非法参数、未对齐内存返回 `AP_EINVAL`；内存不足返回 `AP_ENOMEM`。详见 [API 合同](docs/API_CONTRACT.md)。

## AEC / 同步 / 增强

默认 AEC 为 clean-room 分区 MDF/AUMDF-lite，每 10 ms 处理 5 个 2 ms 子块。`AP_AEC_BACKEND=NLMS` 编译独立时域 NLMS 后端。两种后端都向内部 RES 提供预测回声。

render reference 必须是实际送 DAC 的 post-mix/post-gain 信号。延时跟踪采用有界 coarse/fine 搜索；大路径跳变会重置 AEC，小漂移通过慢速 sample-slip 修正。硬件 capture/playback timestamp 仍然优先。

FULL/LITE 在 NS 开启时使用频率相关 RES；SAFE 或 NS 关闭时回退到宽带 RES；真实双讲时关闭频率 RES，避免误伤近端语音。

## Linux runtime

portable core 不依赖 Linux。`AP_ENABLE_LINUX_RUNTIME=ON` 才构建 Linux-only SPSC worker，使用 pthread、C11 atomic 和 POSIX semaphore。默认不再假定“CPU1 + FIFO 20”：

```text
dsp_cpu = -1
dsp_priority = 0
```

产品可在完成 IRQ/cpuset 验证后显式设置 affinity/SCHED_FIFO。runtime 内部统计使用 lock-free-width 32-bit atomic，避免 ARMv7-A 上隐藏的 64-bit atomic 锁/`libatomic` 成本。

## CI 与平台覆盖

CI 除 GCC/Clang、strict、ASan/UBSan、fuzz、MDF/NLMS、fast-math、ALSA、runtime/perf 外，还加入架构边界检查和 5 路 Arm cross-build：

- generic ARMv7-A scalar；
- Cortex-A7 scalar；
- Cortex-A7 NEON/VFPv4；
- Cortex-A32 NEON/FP-Armv8；
- generic AArch64/NEON。

Cross-build 代表**构建支持**，不代表实板认证。CPU、RSS、温升、功耗必须在出货板卡、内核、编译器、DVFS、音频路由下重新跑 benchmark 与 8h soak。

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
