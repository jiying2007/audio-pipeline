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

Hosted GCC 资源测量只有一个机器真相源：`ci/resource-baseline.json`；`docs/generated/RESOURCE_BASELINE.md` 由它生成，CI 会重新测量并 diff 两者。Hosted 数字只证明声明的 hosted build contract 下存在物理裁剪；产品 exact size API 与 shipping certification 才是发货构建的最终依据。

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
- Activity/DTD 增加 attack/release 能量平滑、far-end hysteresis 和双讲双阈值/hangover，但仍保持低成本接口。
- AEC 在重收敛阶段保持快速 adaptation；连续稳定 far-end-only 后自动降低 adaptation cadence，双讲或参考消失时立即恢复配置的快速 cadence。
- SYNC 保留整数 delay correction，同时使用 `drift_credit` 的小数残差进行两点线性 reference interpolation，减少纯整数 sample slip 带来的跳变。
- delay search 改用平方归一化相关性比较，移除每个候选 delay 上的 `sqrtf`。
- ERLE 仅在 AEC + far-end-only + 非双讲时有效，并显式提供 convergence 状态。
- 大的 correlation/timestamp path jump 会重置失效的 AEC convergence epoch。

默认边界 resampler 对固定下采样比例使用小型 FIR 抑制 alias；FAST 保留轻量插值/抽取行为。API 提供 filter delay，高层 algorithmic latency 会计入该延迟。

## 验证级自验证

`validation/` 是 unit/regression test 与真实产品板认证之间的正式声学证据层，并强制区分可信等级：

- `regression`：PR/main 和 Nightly 使用的确定性自生成 fixture，**不得**包装成验证级证据。
- `validation-grade`：锁定 revision 的公共真实数据 + 已本地封存的公共数据派生仿真。当前锁定 Microsoft AEC Challenge、Microsoft DNS Challenge、OpenSLR SLR28；第三方大数据不进入 Git。
- `validation-grade-blind`：使用仓库外 HMAC key 对同一封存 corpus 做 blind holdout，发布报告可隐藏逐 case blind 指标。
- `product-certified`：仍必须使用真实发货硬件/音频 route，加 CPU、时延、thermal、power、soak 等 `certification/` 证据。

验证 runner 在存在 reference 时计算 SI-SDR、SI-SDR improvement、AEC render-correlation reduction、ERLE、VAD F1；每份报告都会用 SHA-256 绑定 dataset lock、corpus manifest、policy 和 source revision，并生成 evidence manifest。

```bash
python3 validation/tools/build_validation_corpus.py --output /tmp/ap-validation --seed 1307
cmake -S . -B build-validation -DCMAKE_BUILD_TYPE=Release -DAP_BUILD_BENCH=OFF
cmake --build build-validation --target ap_process_pcm --parallel
python3 validation/tools/run_validation.py \
  --corpus /tmp/ap-validation/corpus.json \
  --policy validation/policies/validation-smoke.json \
  --dataset-lock validation/datasets.lock.json \
  --processor build-validation/ap_process_pcm \
  --output /tmp/ap-validation/report.json --enforce
```

大规模公共 corpus 始终保存在仓库外；`Validation Grade` 只在带 `audio-validation` 标签的 self-hosted runner 上运行，并先验证 revision/checksum/local seal。详见 `validation/README.md`。

## 时间戳、断流与回声路径变化

产品可用 `ap_pipeline_observe_io_timestamps()` 提供同一 monotonic clock domain 中对应的 capture/playback hardware timestamp；明确的 speaker route、codec/gain path 变化使用 `ap_pipeline_notify_echo_path_change()`。

Linux runtime 侧，`ap_runtime_submit_ex()` 可携带 versioned frame metadata：stream sequence、capture/render timestamp、XRUN、capture/render discontinuity、clock reset、codec reopen 以及丢帧数量。

`ap_runtime_command()` 提供有界控制队列，支持 echo-path change、stream discontinuity、reset、quality、tuning。所有 command 只由 DSP worker 在 frame boundary 执行，保持 live pipeline 单 owner。

## Linux runtime 所有权与过载行为

同步 Pipeline/Module API 要求调用方串行化。Pipeline 交给 `audio_pipeline_runtime` 并启动 worker 后，由 worker 独占 Pipeline。

output consumer 变慢不会再跳过 DSP frame：output queue 满时只丢弃该次发布结果并计数，AEC/SYNC/NS/AGC/VAD 状态仍继续按 10 ms 时间线前进，避免 backpressure 破坏自适应状态。

Runtime overload 状态与产品 resource class 分离：

`FULL -> LITE -> SAFE`，健康后确定性恢复。

`ap_runtime_get_metrics_v2()` 增加长期 64 位计数、queue high-water、capture/render gap、discontinuity、timestamp、RT scheduler/mlock 失败、实际 CPU/scheduler/priority 和基于固定 histogram 的 DSP p50/p95/p99。

## 日志、事件、Dump 与 Replay

`audio_pipeline/audio_diag.h` 定义正式 diagnostics plane。10 ms realtime worker **不执行** `printf/fwrite`、文件 I/O、heap allocation、JSON 编码。

- 固定大小 event 覆盖生命周期、RT 配置失败、queue pressure、deadline miss、render/sync/AEC 异常和 quality transition。
- event queue 有界且允许丢失，`event_drop_events` 可观测；event ring 满不会阻止 Flight Recorder 触发。
- 可选 Flight Recorder 使用调用方提供的有界内存，保存可配置 pre-roll/post-roll 的 mic/render/output/metrics，并在指定 severity/event 后冻结。
- `.apd` dump 带 exact build fingerprint。
- PC 侧可检查、抽取、回放：

```bash
python3 tools/apdump.py info failure.apd
python3 tools/apdump.py extract failure.apd --out-dir extracted
python3 tools/apreplay.py failure.apd --processor ./build/ap_process_pcm --work-dir replay
```

音频 dump 可能包含用户语音；保留周期、访问控制、上传授权和安全删除由产品侧定义，SDK 本身不会上传数据。详见 `docs/DIAGNOSTICS.md`。

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

CI 会持续 cross-build 全部 profile；Quality CI 还会在 QEMU 下实际执行 Cortex-A7 NEON 与 AArch64 contracts。Cross-build/QEMU 只属于 correctness signal，不是实板性能结论。

## 安装后的 SDK

安装包正式导出 CMake package 与 pkg-config。Linux runtime 安装时会同时安装 `audio_runtime.h` 及其 diagnostics 依赖 `audio_diag.h`。

```cmake
find_package(AudioPipeline CONFIG REQUIRED)
target_link_libraries(app PRIVATE AudioPipeline::core)
# Linux runtime 可选：
target_link_libraries(app PRIVATE AudioPipeline::runtime)
```

CI 会安装到干净目录后，用独立 consumer 工程编译、链接和运行，而不是只检查源码树。

## 声学评测

`eval/run_eval.py` 支持 1/2 麦、capture-only/full-duplex、可选 clean near-end，并可对 SI-SDR、RMS、input/output 与 render 的相关性配置 case-level threshold。`--enforce-thresholds` 会让未达标 case 直接失败。真实产品语料继续保留在仓库外。

## 测试智能化与 HIL 自动化

PR 先通过强制 Fast Gate，再展开高成本矩阵。`scripts/ci_impact.py` 按显式依赖保守选择 composition/Arm/backend/performance 域；未知路径、公开头文件、构建/测试基础设施改动直接回退 FULL，所有 `main` push 无条件完整 Verify。ARM/QEMU/ALSA/static-analysis 等重任务统一使用按 immutable digest 固定的 GHCR toolchain image，只复用 `ccache` 编译对象，不缓存测试结论或认证 evidence。

Nightly 增加显式 flaky 检测和 revision-bound 历史趋势分析；声学 validation 失败会保留可一键重放的 reproducer artifact；metamorphic/property contracts 覆盖 reset deterministic replay、silence 稳定性和拓扑不变量。

真实板 HIL 与 hosted/QEMU 证据严格分离。可信 `[self-hosted, linux, audio-target]` runner 使用板卡本地 metadata/preflight/cleanup，并支持 10 分钟 / 1 小时 / 8 小时 / 24 小时 / 72 小时分层 soak。Scheduled/Release 后 HIL 是 fail-visible：策略要求执行但 `HIL_ENABLED!=true` 时 availability gate 失败，而不是静默 skip 或伪造 PASS。Release 后 8 小时 HIL 只在真正新建且确认 immutable 的 Release 后触发，并绑定该 Release exact SHA；Scheduled HIL 固定调度事件 SHA。Public 仓库外部 PR 不会自动在产品板执行。详见 `docs/TESTING.zh-CN.md`、`docs/PRODUCT_ASSURANCE.md` 和 `hil/README.md`。

## Quality / Release Gate

仓库自动化包含：

- GCC/Clang、strict、ASan/UBSan、libFuzzer smoke；
- ThreadSanitizer runtime ownership 检查；
- MDF/NLMS、EMA/MCRA、precise/fast-math、BANDLIMITED/FAST；
- RAW/LOW/TINY/voice/module-only composition；
- Pipeline/Runtime RAM 与最终 consumer ELF 裁剪；
- generic ARMv7-A、Cortex-A7、Cortex-A32、AArch64 cross-build；
- Cortex-A7 NEON / AArch64 QEMU 执行；
- hosted 源码 line coverage >=90%、clang static analyzer、nightly fuzz；
- `.apd` 生成 -> parse/extract -> 同构建 deterministic replay；
- acoustic eval threshold/self-test 与严格 SKU certification validator；
- main 按 project version 生成 SDK/source/checksum Release。

Hosted x86 百分比只作为 regression signal。发货结论必须来自真实 SoC/kernel/compiler/DVFS/audio route 与声学 corpus。

## 产品认证

`product-certified` schema-v4 记录必须绑定 shipping-approved SKU policy、exact shipping toolchain、build/deployed/executed 二进制 SHA-256 一致性、真实 target performance/acoustic/thermal/power/route evidence、nominal XRUN/overrun/drop、attested artifacts，以及 immutable `product-lifecycle` archive receipt。正式 Cortex-A32 LOW shipping policy 要求最少 72 小时 soak；1 小时 / 8 小时 / 24 小时 HIL 仅属于运营健康与发布历史，不能替代 72 小时 shipping certification。

参考：

- `docs/PLATFORM_SUPPORT.md`
- `docs/PERFORMANCE.md`
- `docs/DIAGNOSTICS.md`
- `certification/record.schema.json`
- `certification/validate_record.py`
- `eval/README.md`

仓库 CI 不会把 hosted/QEMU 数据包装成 Cortex-A7/A32 实板性能。

## 文档

- `docs/API_CONTRACT.md`：公开生命周期、内存、组合、线程合同
- `docs/ARCHITECTURE.md`：状态所有权与依赖方向
- `docs/DSP_DESIGN.md`：算法设计
- `docs/PERFORMANCE.md`：性能/发布/实板 gate
- `docs/DIAGNOSTICS.md`：event、Flight Recorder、dump/replay 契约
- `docs/PORTING.md`：BSP/ALSA/toolchain 集成
- `docs/TUNING.md`：产品声学调优
- `docs/TESTING.zh-CN.md`：Fast/Full CI、impact、cache、失败分类、flaky/trend 与 HIL 策略
- `docs/DEVELOPMENT.md`：开发与 hard-cut 规范
- `THIRD_PARTY.md`：clean-room/reference 边界

## License

见 [LICENSE](LICENSE)。
