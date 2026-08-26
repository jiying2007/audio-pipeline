# audio-pipeline

[English](README.md) | 简体中文

面向**低算力嵌入式 Linux** 的端侧实时语音前处理引擎，目标平台为 Cortex-A32 双核级或相近低端 Arm Linux SoC，覆盖免提语音通话和语音交互。

默认主链：

`S16采集 -> 采样率边界适配 -> HPF -> 双麦TDOA/Delay-and-Sum -> 时延/漂移跟踪 -> MDF/AUMDF-lite AEC -> 分频残余回声抑制 -> STFT Wiener NS -> VAD -> AGC/Limiter -> mono S16`

同步 DSP 路径全部使用调用方提供的有界内存，不 malloc、不加阻塞 mutex；默认实现不 vendor 第三方 DSP 源码。

## 面向低算力的核心设计

- 对外固定 10 ms frame。
- I/O 支持 8/16/24/32/48 kHz，重 DSP 固定在 8/16 kHz。
- 默认 AEC 为 clean-room partitioned MDF/AUMDF-lite，每个 10 ms frame 内拆成 5 个 2 ms block。
- 16 kHz 下：32 samples / 64-point FFT；最大 120 ms tail 对应最多 60 partitions。
- `AP_ENABLE_MDF_AEC=OFF` 可切到独立测试的时域 NLMS fallback。
- FULL/LITE/SAFE 优先减少 active partitions、AEC 更新频率和阵列跟踪，基础 AEC/NS/AGC/VAD 不直接消失。
- Cortex-A32 可选 NEON complex MAC，同时保留纯 C fallback。

设计参考 aispeech-earbuds、athena-signal、SpeexDSP 的 MDF/AUMDF 思路、WebRTC Audio Processing、RNNoise、DeepFilterNet，但不复制这些项目源码。详见 [THIRD_PARTY.md](THIRD_PARTY.md)。

## 回声同步与 clock drift

AEC reference 必须尽量等于真正送到 DAC 的软件混音/音量后信号。reference ring 每约 100 ms 做低成本粗相关搜索，并在候选附近做逐 sample 精搜。

- >20 ms 变化按 route/buffer path jump 处理：直接更新时延并 reset AEC。
- 小变化按 jitter/clock mismatch 处理。
- ppm 估计器累计持续漂移，只有 fractional error 达到整 sample 时才缓慢 insert/drop 一个 reference sample。
- metrics 暴露 `estimated_drift_ppm`、`delay_error_samples`、`reference_sample_slips`、`delay_jumps`、`aec_resets`。

若硬件有可靠 capture/playback timestamp，仍应优先使用 timestamp 缩小搜索范围并明确两个时钟域。

## 分频残余回声抑制

FULL/LITE 复用 NS 的 STFT，对 AEC 预测回声谱做 frequency-dependent RES，不额外引入模型或大依赖。双讲时关闭分频 RES，避免误压近端语音；SAFE 或关闭 NS 时自动回退到更便宜的 broadband RES。

## 双核实时模型

推荐：

- **Core 0**：ALSA/Audio I/O、render-reference、codec/application；
- **Core 1**：完整串行 DSP worker。

两核通过固定容量 SPSC queue 通信。DSP worker 空闲时通过 semaphore 阻塞，不短周期轮询。CPU affinity 和 `SCHED_FIFO` 为 best-effort 优化。runtime metrics 提供 submitted/processed、input-full、output-drop、DSP overrun、last/max DSP us 和当前质量状态。

不强行把 AEC/NS 每 10 ms 拆成跨核 barrier，避免小双核上的唤醒、cache migration 和同步成本反而超过收益。

## Profile

| Profile | AEC | NS/RES | 双麦 | AGC | 场景 |
|---|---:|---:|---:|---:|---|
| `AP_PROFILE_CALL` | 默认 96 ms tail | 较强 | 开 | 保守 | 全双工通话 |
| `AP_PROFILE_ASSISTANT` | 默认 80 ms tail | 更温和 | 开 | 略高 | 唤醒/ASR/助手 |

## 构建

```bash
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build --parallel
ctest --test-dir build --output-on-failure
./build/ap_bench 30
```

安装 SDK 到 staging 目录：

```bash
cmake --install build --prefix ./stage
```

默认 Linux 构建会安装 `libaudio_pipeline.a`、`libaudio_pipeline_runtime.a` 以及 `include/audio_pipeline/` 下的公共头文件；当 `AP_ENABLE_RUNTIME=OFF` 时，仅安装 portable core 库和公共头文件。

Cortex-A32：

```bash
cmake -S . -B build-arm \
  -DCMAKE_TOOLCHAIN_FILE=cmake/toolchains/arm-cortex-a32.cmake \
  -DCMAKE_BUILD_TYPE=Release
cmake --build build-arm --parallel
```

NLMS fallback：

```bash
cmake -S . -B build-nlms -DAP_ENABLE_MDF_AEC=OFF
cmake --build build-nlms --parallel
ctest --test-dir build-nlms --output-on-failure
```

ALSA 示例是可选依赖，不污染最小构建：

```bash
cmake -S . -B build-alsa -DAP_BUILD_ALSA_EXAMPLE=ON
cmake --build build-alsa --target ap_alsa_duplex ap_alsa_runtime_duplex
```

`ap_alsa_runtime_duplex` 展示正式双核接线、XRUN recover、NULL/silence render 和 runtime telemetry。

## 真机性能门禁

`ap_bench` 输出 average/p50/p95/p99/max、10 ms deadline miss、RTF、state bytes、AEC geometry、ERLE、delay/drift/sample-slip、RES/reset 等：

```bash
./scripts/run-target-benchmark.sh ./build/ap_bench 120 0.40 9000 1
```

`ap_runtime_bench` 按真实 10 ms 节拍驱动 worker，检查 queue drop、DSP overrun 和 FULL/LITE/SAFE 驻留率。8 小时长稳入口：

```bash
./scripts/run-target-soak.sh ./build/ap_runtime_bench 28800 0 0.999 1
```

GitHub x86 结果只用于回归，不能冒充 Cortex-A32 CPU/RSS/功耗。最终必须在正式板卡、kernel/compiler/DVFS/audio route 上验收。

## CI 目标

CI 设计覆盖 GCC/Clang、strict warnings、ASan/UBSan、MDF/NLMS 双后端、8/16/24/32/48 kHz、双讲、drift/path-jump/RES、runtime backpressure/wakeup、libFuzzer、ALSA 可选示例编译、runtime benchmark smoke 和 Cortex-A32 cross-build。

## 文档

- [架构](docs/ARCHITECTURE.md)
- [DSP设计](docs/DSP_DESIGN.md)
- [性能与门禁](docs/PERFORMANCE.md)
- [移植](docs/PORTING.md)
- [调参](docs/TUNING.md)

## License

Apache-2.0。最小实现不 vendor 第三方 DSP 源码。
