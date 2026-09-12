# 快速使用指南（中文）

本页面向第一次集成 `audio-pipeline` 的应用/系统开发人员。低层 API 的最终契约以 [`API_CONTRACT.md`](API_CONTRACT.md) 为准。

## 1. 选择构建方式

### Native Linux 开发验证

```bash
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release -DAP_STRICT_WARNINGS=ON
cmake --build build --parallel
ctest --test-dir build --output-on-failure
```

### SSC305 软件商用起始配置

仓库提供命名 preset：

```bash
cmake --preset ssc305-cortex-a32-low
cmake --build --preset ssc305-cortex-a32-low --parallel
```

该 preset 是当前 required CI 的直接 executable contract：仓库会实际 configure/build、验证 generated build identity、clean install SDK，并用 AArch32/QEMU 执行 build-info/core/runtime consumer。

> 该结果证明**构建与集成契约**，不证明 SSC305 真机 CPU、热、功耗或声学性能。

## 2. 安装 SDK

可使用独立安装前缀：

```bash
cmake --install build --prefix "$PWD/install"
```

CMake consumer：

```cmake
find_package(AudioPipeline CONFIG REQUIRED)

target_link_libraries(app PRIVATE AudioPipeline::core)

# Linux Runtime 可选：
target_link_libraries(app PRIVATE AudioPipeline::runtime)
```

pkg-config consumer 也由 CI 从 clean install prefix 实际编译、链接和运行。

## 3. Pipeline 同步处理

典型调用顺序：

```c
ap_config_t cfg = ap_config_default(AP_PROFILE_CALL);
size_t bytes = ap_pipeline_state_size();

/* 由调用方提供满足 AP_PIPELINE_STATE_ALIGNMENT / bytes 的持久内存。 */
ap_pipeline_t *pipeline = NULL;
ap_pipeline_init(memory, bytes, &cfg, &pipeline);

/* AEC 场景先提交实际送往 DAC 的 mono render reference。 */
ap_pipeline_push_render(pipeline, render_frame, render_samples);

/* 每次固定处理 10 ms capture；frames 为每声道帧数。 */
ap_pipeline_process_capture(pipeline, mic_interleaved, frames, output_frame);
```

如果需要显式传入时间线/route 事实，使用当前公开控制面：

- `ap_pipeline_observe_io_timestamps()`：同一 monotonic clock domain 的 capture/render hardware timestamp；
- `ap_pipeline_notify_stream_discontinuity()`：gap/XRUN/clock reset/codec reopen；
- `ap_pipeline_notify_echo_path_change()`：产品已知的 route/path 变化；
- `ap_pipeline_apply_tuning()`：调用方串行化后的 frame-boundary tuning。

核心原则：

- data plane 不动态分配内存；
- 只处理构建 envelope 允许的采样率、麦克风数、delay/tail；
- far-end render 仅在需要 AEC 的场景提供；
- timestamp/gap/XRUN/reset 等 route 事实通过公开控制面明确传入；
- 不要在 stage/core 处理线程中执行日志格式化、文件 I/O、网络或 RPC。

## 4. Linux Runtime

推荐生命周期：

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

重要所有权规则：

1. `start` 前 Pipeline 由调用方拥有；
2. worker 启动后，只有 DSP worker 可以访问/修改 live Pipeline；
3. 应用线程通过有界队列提交 frame，通过 Runtime API 读结果和 telemetry；
4. output backpressure 允许丢弃“发布结果”，但不会跳过已经接受的 DSP frame；
5. 任何 ownership、queue、counter 或 lifecycle 变更都应通过 TSan。

## 5. Build identity

运行时可通过：

```c
const ap_build_info_t *info = ap_build_info();
```

读取版本、模块、几何 envelope、backend、source revision、compiler/target、配置和 build identity。商用问题定位时，**先记录 build identity，再比较音频结果**，不要仅依赖文件名或手工版本字符串。

## 6. Diagnostics / Dump / Replay

查看 dump：

```bash
python3 tools/apdump.py info failure.apd
```

提取证据：

```bash
python3 tools/apdump.py extract failure.apd --output-dir extracted
```

确定性回放：

```bash
python3 tools/apreplay.py failure.apd \
  --processor ./build/ap_process_pcm \
  --output-pcm replay.pcm \
  --require-bit-exact
```

`.apd` 可能包含用户语音。产品必须定义访问控制、保留时长、上传策略和安全删除；Realtime worker 不负责文件 I/O。

## 7. 数据集自测

仓库内唯一 canonical 声学评估框架是 `validation/`。

常规原则：

- regression/development 可以用于搜索；
- validation-grade 只能用于 validation/shadow；
- validation-grade-blind 不允许进入 optimizer；
- 公共/真实数据必须锁 revision/hash/license/用途；
- 候选搜索只能形成 `ACOUSTIC_CANDIDATE`，不能自动改变 shipping default；
- 真实产品资格只能来自 `certification/`。

详细见 [`TESTING.zh-CN.md`](TESTING.zh-CN.md) 和 [`EXTENDED_REAL_VALIDATION.zh-CN.md`](EXTENDED_REAL_VALIDATION.zh-CN.md)。

## 8. 集成 SSC305 时必须额外完成的事情

仓库 CI 已证明 `ssc305-cortex-a32-low` 软件构建契约，但真正量产前还需要真实设备完成：

- 实际交叉工具链/sysroot 与量产 CFLAGS/CMake args 固定；
- ALSA/codec capture/playback/far-end route；
- timestamp、XRUN、reopen、clock reset 行为；
- 真机 CPU p95/p99、RSS/cache、热与功耗；
- 实际机壳/麦克风/扬声器声学；
- HIL 1 h/8 h/24 h 历史；
- shipping-approved policy 下至少 72 h Product Certification。

在这些证据完成前，可以称为 `software-commercial-ready`，不能称为 `product-certified`。

## 9. 常见错误

- **把 QEMU 时间当真机性能**：禁止；QEMU 只证明可执行/ABI/链接契约。
- **把 Hosted Real 当产品认证**：禁止；它只是 validation 证据。
- **调 threshold 直到测试变绿**：禁止；接受规则必须在搜索前冻结。
- **直接修改 started Runtime 的 Pipeline**：违反 ownership。
- **把缺失 HIL 写成 skip/PASS**：Scheduled/Release HIL 必须 fail-visible。
- **只复制库文件、不记录 build identity**：会破坏可追溯性。

## 10. 出问题从哪里开始

1. 记录 `ap_build_info()`；
2. 记录 Runtime metrics 和 route metadata；
3. 如有 `.apd`，先 `apdump info/extract`；
4. 使用 `apreplay` 做可重复复现；
5. 判断问题属于 API/ownership、route/sync、具体 DSP stage、资源/性能或真实硬件；
6. 用最小 targeted test 固定根因，再跑 full Verify。
