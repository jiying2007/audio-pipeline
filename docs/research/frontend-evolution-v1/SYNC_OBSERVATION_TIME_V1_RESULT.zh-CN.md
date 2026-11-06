# FE-C2-SYNC-OBSERVATION-TIME-V1：首次本地验证

日期：2026-11-06。状态：定向正确性验证已执行，等待独立复审、主任务集成及精确源码门禁；不是物理 SSC305 或语音效果结论。

## 身份与唯一因果变化

- 基线：`438fe09d79ff768306c00573849517bcd91cbc6e`。
- 实施前冻结合同：`6056682486c1a2a2c84d77135de8118e07fc8cf3` 中的 [双麦双用途合同 A](DUALMIC_INTERACTION_INTERCOM_V1_PLAN.zh-CN.md)。
- 候选新增 capture 样点总数、成功声学观察的 capture 坐标和该计数的采样率；真实间隔采用 `1e6 * delta_delay / elapsed_capture_samples`。
- 正常 100 ms 保留原浮点运算顺序。EMA、ppm clamp、相关门槛、三次 route 确认、credit、整数 slip、误差反馈和插值公式不变。
- 关闭跟踪/补偿、capture rate 变化或计数重新建立会使旧 basis 失效；下次声学观察先建立新 basis。合法 timestamp 仍立即校准对齐、清零漂移，同时结束旧声学 basis。启用补偿时确认的 route jump 在当前 capture 坐标建立新锚点。
- 只通过新增公开 API 回归测试观察真实搜索/更新；内部 counter 边界单列为 white-box 数值测试，没有伪造长时间物理采集。

候选关键源码 SHA-256：

| 文件 | SHA-256 |
|---|---|
| `src/sync/ap_sync.c` | `67aae726e5019befc9b7f5d9c5ca264963394bee4ff58b78d1bcedcec00c5fa2` |
| `src/sync/ap_sync.h` | `e855c8a517d7030be90ca4190cad75e84f8764fc35cebef9032cc001b7b47630` |
| `tests/test_sync_observation_time.c` | `c7541530f6b10e3072d2e58d569f3282d400048d68d433c6488c17117142820f` |

## Before / after

同一最终测试文件的公开用例先链接精确基线库，再链接候选。基线 `elapsed` 入口实际 exit 1：

```text
1 s interval rate=16000 actual_ppm=31.25 expected_ppm=3.125
```

候选公开用例与内部边界入口实际 exit 0：

| rate | +1 样点 / 100 ms，一次 EMA | +1 样点 / 1 s，一次 EMA | +4 样点 / 1 s，一次 EMA |
|---|---:|---:|---:|
| 16000 | 31.25 ppm | 3.125 ppm | 12.5 ppm |
| 8000 | 62.5 ppm | 6.25 ppm | 25 ppm |

正负变化、零相关拒绝、非零周期信号的非唯一峰拒绝均已覆盖。+4 样点 / 1 s 用例验证归一化在 clamp 之前，不能把未归一化的过大 ppm 先裁剪再缩放。

正常 100 ms 的 20 条 `ppm=%a`、delay、slip 记录与基线逐字节相同；该记录 SHA-256 为 `7a5728de262a416ff79608523d2c060b2358d25e648c722ab905daf00718fba2`。这是这些确定性轨迹的遥测一致性，不是全语料 PCM 等价声明。

边界已实际覆盖：reset；timestamp 在搜索周期中途更新；非法公开参数与 timestamp 的完整状态原子拒绝；分别关闭 tracking 或 drift 后恢复；drift 开/关时 route 确认后的新 basis；8k→16k 与 16k→8k 的 basis 失效；`UINT64_MAX` 前后的计数重基准；零 elapsed 的安全重新建锚。rate 切换用例只验证不混合旧速率单位，不批准无 reset 的声学采样率切换。

## 构建与既有回归

Host GCC 14.2.0，Release，严格 warnings，fast-math 关闭。新 CMake target 为 `ap_sync_observation_time_tests`，通过已有 CTest 入口注册；没有新增 workflow。

| 配置 | 实际结果 |
|---|---|
| 默认全模块 native | 6/6：module、新 SYNC、contract、pipeline control、drift/RES、runtime 通过 |
| 8k-only SYNC native | 2/2：module、新 SYNC 通过 |
| 低资源参数 native | module、新 SYNC 通过；额外运行的旧 drift/RES 初始化失败，保留为 2/3，通过与失败分别报告 |

低资源构建使用 I/O/internal 16k、双麦、max delay 60 ms、AEC tail 64 ms、queue 4、direction tracking OFF；CPU/SIMD 为本机 SCALAR，不冒充 Cortex-A32/NEON 或 DUT。

旧 `test_drift_res.c` 首例硬编码 `c.max_delay_ms = 100`，超出该低资源构建的 60 ms envelope，因此在第 56 行初始化断言失败。将精确基线的 CMake/include/src 和该测试导出到独立目录、按相同低资源参数重新构建后，也得到同一断言失败、exit 134。没有修改这个旧测试、编译上限或门槛。默认 envelope 下该旧测试通过。

## 内部状态预算

| native 查询 | 基线 bytes | 候选 bytes | 增量 |
|---|---:|---:|---:|
| 默认 standalone SYNC | 32816 | 32840 | +24 |
| 默认最大能力 pipeline | 78192 | 78216 | +24 |
| 低资源参数 pipeline | 38832 | 38856 | +24 |

新增内部状态 24 B，低于共同合同的总增量 64 B；低资源 host arena 为 38,856 B，保持低于 50,000 B。默认最大能力构建与低资源 envelope 不同，不能把两者混成同一个目标配置。物理目标 CPU、cache、时延、热和功耗均未据此成立。

## 保留的夹具与环境失败

首次 8k 连续单调位移夹具在第六次更新触发现有 coarse lag 误选的断言；当时尚未修改算法。该失败不是时间分母证据。最终 8k 连续轨迹限制在 coarse anchor 附近的 0/1 样点变化，16k 保持十次单调位移；该固定夹具在基线上重新确认正常轨迹通过、1 s 时间用例失败，然后才实施候选。没有通过修改搜索阈值解决该夹具失败。

第一次配置使用了不存在的 Ninja 路径，配置失败，后续构建/执行没有产生候选结果。纠正为实际工具路径后重新配置和执行；上述成功结果来自重新生成的真实程序。失败日志与最终日志分开保存。

## 可重建命令

工具实际路径为 `/workspace/scratch/b74ab3415ba4/build-tools/cmake/data/bin/cmake`，Ninja 为 `/workspace/scratch/b74ab3415ba4/build-tools/bin/ninja`。在其他环境可使用对应的 `cmake`/`ninja` 可执行文件。

```sh
cmake -S . -B /tmp/audio-sync-observation -G Ninja \
  -DCMAKE_BUILD_TYPE=Release -DAP_STRICT_WARNINGS=ON \
  -DAP_BUILD_BENCH=OFF -DAP_BUILD_EXAMPLES=OFF
cmake --build /tmp/audio-sync-observation --parallel 4 \
  --target ap_sync_observation_time_tests ap_module_tests ap_contract_tests \
  ap_drift_res_tests ap_pipeline_control_tests ap_runtime_tests ap_state_size
ctest --test-dir /tmp/audio-sync-observation --output-on-failure --timeout 300 \
  -R '^(ap_module_tests|ap_sync_observation_time_tests|ap_contract_tests|ap_drift_res_tests|ap_pipeline_control_tests|ap_runtime_tests)$'
```

8k-only 配置另加 `-DAP_BUILD_PIPELINE=OFF -DAP_MODULES=SYNC -DAP_ENABLE_LINUX_RUNTIME=OFF -DAP_BUILD_MAX_IO_RATE_HZ=8000 -DAP_BUILD_MAX_INTERNAL_RATE_HZ=8000`，构建并运行两个 module/SYNC target。

低资源配置另加 `-DAP_BUILD_MAX_IO_RATE_HZ=16000 -DAP_BUILD_MAX_INTERNAL_RATE_HZ=16000 -DAP_BUILD_MAX_MIC_CHANNELS=2 -DAP_BUILD_MAX_DELAY_MS=60 -DAP_BUILD_MAX_AEC_TAIL_MS=64 -DAP_RUNTIME_QUEUE_DEPTH=4 -DAP_ENABLE_BF_DIRECTION_TRACKING=OFF`。若运行旧 drift/RES target，必须如实保留上述已复现的初始化失败。

基线公开回归可将此测试文件链接到精确基线的 `libaudio_pipeline.a`，不定义 `AP_SYNC_TEST_INTERNAL_COUNTERS`（该选项只用于候选新字段的内部边界）；分别运行 `elapsed` 和 `continuous` 参数。前者应保留原失败，后者用于正常路径逐字节对照。

本次完整本地日志、命令输出和 comparison JSON 位于工作会话的 `sync-observation-evidence` 目录；核心失败文本、数值和源码身份已在本文件保留。集成后的 2.3.62 身份、独立源码准入、适用 CI/ABI/跨架构验证由主任务执行，本结果不提前将其标为通过。
