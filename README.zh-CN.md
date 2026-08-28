# audio-pipeline

[English](README.md) | 简体中文

`audio-pipeline` 是面向**低算力 Arm Linux 产品**的轻依赖、无动态分配实时语音前端与可组合 DSP SDK。同一套源码覆盖 ARMv7-A/Cortex-A7、Cortex-A32 类 AArch32，以及具有相近语音处理预算的 AArch64 产品。CPU 型号只属于构建/认证配置，不进入 DSP 算法依赖。

默认高层链路采用固定且可验证的安全顺序：

`S16采集 -> 采样率适配 -> HPF -> 双麦BF -> SYNC -> Activity/DTD -> AEC -> RES -> NS -> AGC -> VAD -> 单声道S16`

公开帧长固定为 10 ms。设备 I/O 在构建包络允许范围内支持 8/16/24/32/48 kHz；重 DSP 只运行在 8 或 16 kHz。同步数据面使用调用方持有的有界状态，不使用 heap、mutex，也没有运行时 SIMD/plugin dispatch。

## 两种集成方式

**高层组合 Pipeline。** `ap_config_t.stages` 从当前二进制已经编入的 stage 中选择合法运行子集。处理顺序固定，不设计成任意 DAG。

**Standalone Module SDK。** `audio_pipeline/audio_modules.h` 独立提供 resampler、HPF、BF、SYNC、Activity/DTD、AEC、RES、NS、AGC、VAD。Standalone wrapper 与高层 Pipeline 共用同一套私有算法实现，不维护两套 DSP。

编译期产品组合：

```text
AP_BUILD_PIPELINE=ON|OFF
AP_MODULES=RESAMPLER,HPF,BF,SYNC,ACTIVITY,AEC,RES,NS,AGC,VAD
```

未出现在 `AP_MODULES` 的模块会真实移除实现 TU 和 resident state，而不是仅运行时 bypass。

代表性 presets：

```bash
cmake --preset composition-full
cmake --preset composition-low
cmake --preset composition-tiny
cmake --preset composition-voice-frontend
cmake --preset composition-raw
cmake --preset composition-aec-only
cmake --preset composition-ns-only
cmake --preset composition-activity-only
cmake --preset composition-fast-resampler
```

当前 hosted GCC Quality gate 已证明 Pipeline RAM 会物理裁剪：

```text
full   78,072 B
LOW    46,904 B
TINY   25,384 B
RAW     1,064 B
```

Linux runtime 同样受 build envelope 控制：当前 hosted 参考为完整 48 kHz/depth-8 **31,824 B**，约束后的 16 kHz/depth-4 TINY **4,464 B**。这些数字只用于证明当前 compiler/ABI 下的物理裁剪；发货应始终读取 exact size API。

## SKU 构建包络

除模块集合外，每个产品可以在编译期限制最大几何：

```text
AP_BUILD_MAX_IO_RATE_HZ
AP_BUILD_MAX_INTERNAL_RATE_HZ
AP_BUILD_MAX_MIC_CHANNELS
AP_BUILD_MAX_DELAY_MS
AP_BUILD_MAX_AEC_TAIL_MS
AP_RUNTIME_QUEUE_DEPTH
```

这些限制会按条件缩小 AEC partitions、SYNC render history、scratch 和 runtime queue。它们是 SKU 编译约束，与运行时 `TINY/LOW/STANDARD` 策略相互独立。

生成的 `audio_pipeline_build.h` 与 `ap_build_info()` 会给出实际二进制 fingerprint：版本、模块 mask、AEC/NS/SIMD/resampler backend、fast-math 以及最大构建几何。

## DSP 与实时策略

- AEC：默认 MDF，可编译切换 NLMS fallback。
- NS estimator：默认 EMA，clean-room MCRA 为 opt-in。
- SIMD：编译期 SCALAR/NEON。
- Resampler：默认 BANDLIMITED，可显式选择 legacy-speed FAST fallback。
- fast-math：默认关闭，绝不隐藏到 CPU toolchain。
- Activity/DTD 已成为复用模块，高层 AEC/RES 不再复制独立判定。
- ERLE 仅在 AEC + far-end-only + 非双讲时有效，并显式提供 convergence 状态。
- 大的 correlation/timestamp path jump 会重置失效的 AEC convergence epoch。

默认边界 resampler 对当前固定下采样比例使用小型 FIR 以抑制 alias；FAST 保留原有轻量插值/抽取行为。API 提供 resampler filter delay，高层 algorithmic latency 会计入该延迟。

## 硬件时间戳与回声路径变化

如果产品可以获取可信的 capture/playback hardware timestamp，可调用：

```c
ap_pipeline_observe_io_timestamps(...);
```

两个 timestamp 必须描述同一 monotonic clock domain 中相互对应的位置。

如果产品明确知道 speaker route、codec reopen、gain path 等导致 echo path 发生变化，应主动调用：

```c
ap_pipeline_notify_echo_path_change(...);
```

这样会立即清理陈旧的 SYNC/Activity/AEC 状态，而不是等待相关搜索重新发现路径。

## Linux runtime 所有权

同步 Pipeline/Module API 要求调用方串行化。Pipeline 交给 `audio_pipeline_runtime` 并启动 worker 后，运行期间由 worker 独占 Pipeline。

每帧完整 `ap_metrics_t` 随 SPSC output snapshot 返回；控制面 `ap_runtime_get_metrics()` 只读取 runtime 自己的 atomics，不再并发读取 worker 正在修改的 Pipeline state。ThreadSanitizer CI 已覆盖该所有权模型。

Runtime overload 状态与产品 resource class 分离：

`FULL -> LITE -> SAFE`，健康后确定性恢复。

## 构建

Native Linux：

```bash
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build --parallel
ctest --test-dir build --output-on-failure
```

Arm presets：

```bash
cmake --preset armv7a-scalar
cmake --preset cortex-a7-scalar
cmake --preset cortex-a7-neon
cmake --preset cortex-a32-neon
cmake --preset aarch64-neon
```

CI 会持续 cross-build 全部 profile；Quality CI 还会在 QEMU 下实际执行 Cortex-A7 NEON 与 AArch64 的 module/contract/FFT/resampler 测试。Cross-build/QEMU 仅属于 correctness signal，不是实板性能结论。

## 安装后的 SDK

安装包正式导出 CMake package 与 pkg-config：

```cmake
find_package(AudioPipeline CONFIG REQUIRED)
target_link_libraries(app PRIVATE AudioPipeline::core)
# Linux runtime 可选：
target_link_libraries(app PRIVATE AudioPipeline::runtime)
```

或：

```bash
pkg-config --cflags --libs audio-pipeline
```

CI 会把 SDK 安装到干净目录，再用独立 consumer 工程执行 `find_package`、编译、链接与运行，而不是只检查文件是否存在。

## Quality / Release Gate

仓库自动化当前包含：

- GCC/Clang、strict、ASan/UBSan、libFuzzer smoke；
- ThreadSanitizer runtime race 检查；
- MDF/NLMS、EMA/MCRA、precise/fast-math、BANDLIMITED/FAST；
- RAW/LOW/TINY/voice/module-only composition；
- Pipeline/Runtime RAM 和最终 consumer ELF 裁剪；
- generic ARMv7-A、Cortex-A7、Cortex-A32、AArch64 cross-build；
- Cortex-A7 NEON / AArch64 QEMU 执行；
- hosted 源码 line coverage >=90%、clang static analyzer、nightly fuzz；
- acoustic eval harness/schema 与 SKU certification schema；
- main 上按 project version 自动生成 SDK/source/SHA256 GitHub Release。

Hosted x86 的百分比仅作为 regression signal。发货结论必须来自真实 SoC/kernel/compiler/DVFS/audio route 与声学语料。

## 产品认证

每个发货 SKU 至少应记录 CPU、p95/p99、RSS/cache/context-switch、XRUN/backpressure/overrun、thermal/power、声学 corpus 结果以及 8h soak。

参考：

- `docs/PLATFORM_SUPPORT.md`
- `docs/PERFORMANCE.md`
- `certification/record.schema.json`
- `eval/README.md`

仓库 CI 不会把 hosted/QEMU 数据包装成 Cortex-A7/A32 实板性能。

## 文档

- `docs/API_CONTRACT.md`：公开生命周期、内存、组合、线程合同
- `docs/ARCHITECTURE.md`：状态所有权与依赖方向
- `docs/DSP_DESIGN.md`：算法设计
- `docs/PERFORMANCE.md`：性能/发布/实板 gate
- `docs/PORTING.md`：BSP/ALSA/toolchain 集成
- `docs/TUNING.md`：产品声学调优
- `docs/DEVELOPMENT.md`：开发与 hard-cut 规范
- `THIRD_PARTY.md`：clean-room/reference 边界

## License

见 [LICENSE](LICENSE)。
