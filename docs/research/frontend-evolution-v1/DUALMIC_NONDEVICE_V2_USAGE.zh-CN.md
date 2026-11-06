# 双麦非真机 V2：识别交互与语音对讲使用入口

本轮把真实录音整链回放、实际 Opus/Runtime 对讲接线、固定中文 ASR/KWS 执行器
接入同一仓库的现有验证流程。依据[实施前合同](DUALMIC_NONDEVICE_V2_PLAN.zh-CN.md)
和 [CI 接入合同](DUALMIC_NONDEVICE_V2_CI_CONTRACT.zh-CN.md)，SDK/DSP 保持 2.3.63，
生产 API、Runtime 行为及 CALL/ASSISTANT 默认参数不变。

这些入口是可执行的 host 研究与集成工具。它们提供实际处理结果、完整音频和可回读
证据；算法效果、真实互联网通信、真人听评和 SSC305 物理测量各按实际证据判断。
精确 PR/main 的结果见 [PR #920](https://github.com/jiying2007/audio-pipeline/pull/920)
及[活跃研究记录 #657](https://github.com/jiying2007/audio-pipeline/issues/657)。

## 两种用途的共同输入契约

当前入口使用 16 kHz S16LE，双麦交错采样，单声道 Render，连续 10 ms 帧。
CALL 与 ASSISTANT 使用同一公共前端，并显式选择不同 preset；音质收益不能由
用途名称推导。默认参数与一般文件处理方法见 [PCM 入口](../../OFFLINE_PCM_IO.md)。

| 环节 | 应用接线要求 | 本轮实际覆盖 |
| --- | --- | --- |
| 捕获 | 保留两个同步麦克风通道和完整帧，不把 VAD 当删帧开关 | 真实单麦源的显式双麦派生；实际 C2 处理器 |
| 播放参考 | 送给 AEC 的 Render 必须等于实际播放 PCM，包含解码、PLC、音量和静音结果 | 对讲工具保存播放轨与提交 Render 实参，逐字节比较 |
| 网络丢包 | PLC 继续产生播放样点，Render 仍为 PRESENT | 单包、连续两包及超 deadline 丢弃 |
| 播放设备重开 | 独立通知真实流不连续，不能由网络丢包冒充 | 固定工程重开场景及原 Runtime 通知 |
| 下游识别 | 连续供给实际前端输出，保留模型原始结果和实际消费时刻 | Vosk C API、sherpa-onnx KWS，各六个固定视图 |
| 对讲上行 | worker 输出进入实际编码器，并由远端解码；不得用期望输出代替 | Opus 20 ms 双向编解码和有界模拟网络日程 |

本轮没有修改设备驱动或实现 SIP/ICE/RTP/UDP 传输。对讲网络到达时间是明确模拟的；
解码器、PLC、前端、worker、编码器均实际执行。

## 统一构建

先检出要测量的完整提交，保持相关源码已提交、未修改。构建身份必须与
`--source-revision` 相同；历史产物不能重标为当前 HEAD。

```sh
AP_SRC_SHA="$(git rev-parse HEAD)"
timeout 300s cmake -S . -B build-dualmic-host -DCMAKE_BUILD_TYPE=Release \
  -DAP_BUILD_BENCH=OFF -DAP_STRICT_WARNINGS=ON
timeout 300s cmake --build build-dualmic-host --parallel \
  --target ap_process_pcm ap_build_info_dump audio_pipeline_runtime
```

下述 `--output` 必须使用新路径。程序故意拒绝覆盖旧结果；应保留失败目录并以新
身份记录修正后的执行。每项新构建、测试、测量及回读使用冻结的 300 秒预算。

## A：真实录音经过完整 CALL / ASSISTANT

来源沿用现有 `speech_pinned_snapshot.py` 与 `speech_spatial.source_check` 的
准入流程；CI 在 `quality / frontend-speech` 已取得并验证的
`fe-speech/effects/data` 上继续执行，不建立第二条来源或声学评分权威。
本地 `AP_SPEECH_SOURCE` 应指向包含原 source receipt 的完整 46 文件目录。

```sh
timeout 300s python3 tests/validation/test_dualmic_recorded_replay.py
timeout 300s python3 tests/validation/build_dualmic_recorded_corpus.py \
  --source "$AP_SPEECH_SOURCE" --output /tmp/ap-recorded-corpus-v2
timeout 300s python3 tests/validation/run_dualmic_recorded_replay.py \
  --processor "$PWD/build-dualmic-host/ap_process_pcm" \
  --corpus /tmp/ap-recorded-corpus-v2/corpus.json \
  --output /tmp/ap-recorded-result-v2 --source-revision "$AP_SRC_SHA"
timeout 300s python3 tests/validation/run_dualmic_recorded_replay.py \
  --output /tmp/ap-recorded-result-v2 --verify
```

固定矩阵为四个 near/far pair、七场景、两个 profile，共 56 例。两个 profile
消费逐字节相同的输入。结果含 canonical 逐例指标、全部 PCM/JSONL、来源与二进制
身份，以及 28 个试次、84 个不改电平的匿名 WAV。原语音只有 32 秒独特英文录音；
派生视图不增加独立说话人/房间数量，数据角色保持 regression。

[首轮结果](DUALMIC_RECORDED_SPEECH_V1_RESULT.zh-CN.md)保留部分负 ERLE 和双讲近端
SI-SDR 损失。`expected={}` 导致的 `pass_rate=1.0` 只表示没有声学阈值被触发，
并不表示音质通过。无真人 VAD 时间标注，故不报告 VAD 准确率/起止延迟；
WAV 已生成也不等于真人听评已执行。

## B：实际 Opus 与 Runtime 对讲链

宿主需提供 libopus；Ubuntu 可安装 `libopus0`。工具在运行时识别实际加载实体、
版本、hash 和 lookahead，不把 host codec 加入生产 SDK 依赖。

```sh
timeout 300s cc -std=c11 -O2 -Wall -Wextra -Werror \
  -I build-dualmic-host/generated -I include \
  tests/validation/frontend_evolution/dualmic_intercom_runtime.c \
  build-dualmic-host/libaudio_pipeline_runtime.a \
  build-dualmic-host/libaudio_pipeline.a -pthread -lm \
  -o build-dualmic-host/dualmic_intercom_runtime
timeout 300s python3 tests/validation/frontend_evolution/test_dualmic_intercom_transport.py \
  --bridge "$PWD/build-dualmic-host/dualmic_intercom_runtime"
timeout 300s python3 tests/validation/frontend_evolution/dualmic_intercom_transport.py \
  --bridge "$PWD/build-dualmic-host/dualmic_intercom_runtime" \
  --source-revision "$AP_SRC_SHA" --output /tmp/ap-intercom-result-v2
```

固定覆盖正常、乱序、重复、单丢包、连续两丢包、迟到、音量/静音、重开八场景，
加同输入重复和不同未来后缀控制。每个场景都与原 public API 同步处理进行 PCM、
trace、Render 比对；错误的音量前/PLC 前参考必须拒绝。

[实际结果](DUALMIC_INTERCOM_TRANSPORT_V1_RESULT.zh-CN.md)分别记录音频和诊断事件
计数：音频输出无丢帧并不意味着事件队列无丢弃。原深度 2 的事件队列在首轮产生
1 或 3 次丢弃，具体事件身份没有被保存。有限 fixture 不追加 codec 尾部 flush，
因此不得宣称任意通话结束的尾音无损交付。60 ms 模拟缓冲、80 ms 首包播放起点、
查询到的 codec lookahead 与前端算法延迟都是组件事实，不是实测口到耳时延。

## C：固定中文 ASR / KWS

运行环境固定为 CPython 3.12、Linux x86_64；CI 使用 Ubuntu 24.04。来源工具只
下载和校验明确锁定的模型、音频、转写与四个 wheel，解压到独立目录，不进行
全局 pip 安装或浮动依赖解析。模型子进程的环境由执行器明确构造。

```sh
timeout 300s python3 tests/validation/test_downstream_metrics.py
timeout 300s python3 tests/validation/mandarin_downstream_source.py \
  --root /tmp/ap-mandarin-source-v2 \
  --lock docs/research/frontend-evolution-v1/mandarin-downstream-v1-source-lock.json
timeout 300s python3 tests/validation/mandarin_downstream.py prepare \
  --source-root /tmp/ap-mandarin-source-v2 \
  --processor "$PWD/build-dualmic-host/ap_process_pcm" \
  --source-revision "$AP_SRC_SHA" --output /tmp/ap-mandarin-prepared-v2
timeout 300s python3 tests/validation/mandarin_downstream.py run \
  --source-root /tmp/ap-mandarin-source-v2 \
  --prepared /tmp/ap-mandarin-prepared-v2 --output /tmp/ap-mandarin-result-v2
timeout 300s python3 tests/validation/mandarin_downstream.py verify \
  --source-root /tmp/ap-mandarin-source-v2 \
  --prepared /tmp/ap-mandarin-prepared-v2 --output /tmp/ap-mandarin-result-v2
```

固定使用 `vosk-model-small-cn-0.22` 和 sherpa-onnx zh-en 3M 2025-12-20 chunk8，
唯一预定关键词为“广州市”，外部参考转写为“广州市房地产中介协会分析”。
清洁 capture-only 和工程双讲各有 raw/CALL/ASSISTANT 三视图；六视图只来自同一条
4.281 秒真人中文录音，双讲 far/render 为第一方工程合成，不是真人对讲或 TTS。

唯一文本/事件权威在 `validation/tools/downstream_metrics.py`。字符归一化只做
NFC 与移除 whitespace；保留 S/D/I/N 和空分母 null。没有外部词边界时 WER 为 null；
没有人工事件时间、负样本暴露和词末真值时 FRR、FAR/h、触发延迟均为 null。
实际模型空输出、零次触发与执行失败必须分开。具体观测见
[中文模型结果](MANDARIN_DOWNSTREAM_V1_RESULT.zh-CN.md)。

## 结果定位与闭环边界

| 产物 | 主要内容 | 可支持的结论 |
| --- | --- | --- |
| `dualmic-recorded-speech-RUN-attempt-N` | 56 例完整 PCM/JSONL、来源、指标、84 WAV | 录音整链测量完成，负结果可复查 |
| `dualmic-intercom-RUN-attempt-N` | 实际 Opus 包、PLC/队列日程、播放/Render、Runtime/对照 | 有限软件对讲接线和连续性 |
| `dualmic-mandarin-RUN-attempt-N` | 六视图 PCM、模型原始输出、固定评分、来源 hash/阶段日志 | 固定中文模型实际接通 |

每份证据属于其实际 run、attempt、source SHA 和宿主。合并后 main 必须重新构建
执行，不复用 PR 的成功标记。新 main 的门禁属于软件集成；没有把单样本识别、
合成声学或 hosted CI 包装为总体音质、真实网络或物理设备通过。

这三条入口不自动产生新的算法优胜者。对已观察到的近端损伤继续提出因果假设时，
应另行冻结开发数据、单一变量和验收规则，不能回改本轮指标或用本轮曝光数据冒充
独立验证。真人听评和真实房间/互联网证据仍依实际取得情况记录，真机按本轮用户
要求保持 NOT_RUN。
