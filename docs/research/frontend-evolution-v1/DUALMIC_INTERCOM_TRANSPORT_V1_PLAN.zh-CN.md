# 双麦对讲传输 V1：固定工程集成合同

状态：实现和正式 codec/Runtime 测量前冻结。日期：2026-11-06（Asia/Shanghai）。
身份：`FE-C2-INTERCOM-TRANSPORT-V1`。父合同为
[非真机闭环 V2](DUALMIC_NONDEVICE_V2_PLAN.zh-CN.md)，父合同提交
`494ae5ebb9c5cba4a8c3d0739430259a3649513f`，DSP 基线为
`2d93c9ddf74355c7e5ac0bc18c9a6fe3ae53cbd3` / 2.3.63。

## 目的与范围

原 PCM/ALSA 示例没有实际语音 codec、分包、有限 jitter queue、PLC 与播放后
Render 的完整集成。本实验固定已有 CALL 与 Linux Runtime，只新增研究目录的
host 适配器和独立检验。没有 DSP/default/API/Runtime 算法变更、质量选型、训练、
既有门槛修改或硬件执行。所有网络到达时刻均为确定性的模拟整数微秒；不是
实际 UDP/WAN、DAC/ADC 时间戳、SIP/ICE/RTP 产品栈或口到耳验收。

链路：远端工程 PCM → 实际 libopus 编码 → 模拟到达/有限队列 → 实际解码或
PLC → 音量/模拟播放重开 → 本地实际播放 PCM。该 PCM 逐字节作为原 Runtime
的 PRESENT Render，亦是合成回声的驱动。双麦捕获 → 原 CALL worker → 上行
实际编码/相同日程解码或 PLC → 远端播放 PCM。codec/文件 I/O 均在研究 host
适配器，不进入生产 DSP 的实时路径。

## 固定资产与配置

- 16 kHz，双麦 interleaved S16LE，CALL 原默认配置、35 mm 原几何；10 ms/160
  样点前端帧。不得由 VAD 删除帧。只接受小端 host，不伪装跨端序支持。
- Opus mono / VOIP / 20 ms（320 样点）/ 24000 bit/s / CBR / complexity 5，
  DTX=0、FEC=0、packet-loss expectation=0。查询并保存有效配置和
  `OPUS_GET_LOOKAHEAD`。这是一个固定集成配置，不是最佳码率/复杂度研究。
- 使用实际已安装 libopus，记录实际加载文件绝对路径、文件 SHA256、大小、
  `opus_get_version_string()`；不重分发 host library。环境盘点发现 libopus
  1.5.2，SHA256 `621e97f23655dbf2727873b7717e3b65ae8c734f84a0848f88c21edb95202357`；
  正式执行仍回读实际字节，其他 host 不冒称同一 library。
- 原生 ABI 依据官方 API：
  <https://www.opus-codec.org/docs/opus_api-1.5/group__opus__encoder.html>、
  <https://www.opus-codec.org/docs/opus_api-1.5/group__opus__decoder.html>、
  <https://www.opus-codec.org/docs/opus_api-1.5/group__opus__encoderctls.html>。
  许可来源 <https://www.opus-codec.org/license/>；已安装包的 copyright 作为
  依赖身份记录。没有模型/权重或第三方语音语料。
- 第一方 generator：原 `build_validation_corpus.py` 的 `render_signal`，
  96000 样点、seed 95931；`speech_like`，608 帧、seed 95932、amplitude 4500，
  活动窗口 [0.7,1.6)、[2.4,3.4)、[4.4,5.5) 秒。窗口只定义工程合成，非真人标签。
  捕获左声道为 near + echo(playout, [(320,0.5),(640,0.2)])，右声道为
  near + echo(playout, [(321,0.47),(641,0.19)])；复用原 mix/interleave/clamp。
  这是已知合成两路，不宣称真实空间响应。

## 固定调度和八个场景

包序号从 0 开始，不实现 RTP。包 i 的准备时刻 `(i+1)*20000 us`，正常到达为
准备+10000 us，播放起始 deadline 为准备+60000 us。第 0 包开始播放于 80000 us，
因此每方向保留 1280 样点启动静音，不在事后裁去以美化延迟。每包播放 320
样点。队列最多 6 个不同包；超容、重复序号冲突、越界包或非法样本长度直接失败。
到达等于 deadline 可接收，严格晚于 deadline 为迟到。迟到不能倒退解码状态。
同序号同 payload 重复只保留首次到达；每个播放序号恰好执行一次 decode 或 PLC。

| 场景 | 下行和上行各自的固定干预 | 预期网络计数/每方向 |
|---|---|---|
| normal | 正常到达 | loss=0, late=0, duplicate=0, PLC=0 |
| reorder | 包 40 到达改为准备+50000 us；包 41 正常先到 | loss=0, late=0, duplicate=0, PLC=0 |
| duplicate | 包 70 复制一次，到达比首次晚 1000 us | loss=0, late=0, duplicate=1, PLC=0 |
| single-loss | 不交付包 100 | loss=1, late=0, duplicate=0, PLC=1 |
| burst-loss | 不交付包 100、101 | loss=2, late=0, duplicate=0, PLC=2 |
| late | 包 100 到达改为准备+90000 us | loss=0, late=1, duplicate=0, PLC=1 |
| gain-mute | 网络正常；本地播放帧 200..239 音量0，240..319音量0.5，其余1 | loss=0, late=0, duplicate=0, PLC=0 |
| reopen | 网络正常；本地播放帧300、301为零；帧302注入播放重开通知 | loss=0, late=0, duplicate=0, PLC=0 |

网络丢包且 PLC 成功仍是连续 PRESENT Render，不通知 XRUN 或 Render gap。
gain-mute 的零 PCM 也是 PRESENT。reopen 只是明确模拟播放故障：帧302注入原
`AP_FRAME_RENDER_DISCONTINUITY | AP_FRAME_CODEC_REOPEN`，lost_render_frames=2，
其余 metadata 不含 hardware timestamp-valid 标志。没有真的 ALSA/DAC 重开。
同步公共 API 对照在同帧调用相同语义的 stream-discontinuity 通知。

下行固定 300 包，原音频600帧，播放608帧；每场景实际 Runtime 处理608帧，
上行304包，远端播放616帧。没有末尾不足包；工具对非完整 20 ms 输入明确拒绝，
不静默补零或截尾。保留启动缓冲和 codec delay，不追加隐式 codec drain；最后
codec lookahead 内的输入内容尚未播放完这一事实与输出样本数完整性分开报告。

## 实现与验收

薄 C runner 同时提供 `runtime` 和 `direct` 两种执行模式，均使用原公开头文件和
同一新构建的静态库。runtime 每帧提交后有限等待实际 completion；没有调大
Runtime 默认 overload/recovery 阈值。这个串行 host 文件驱动不测并发吞吐极限。
提交的 render 实参同时写入 consumed-render PCM，独立比较实际播放轨完整字节。
最终 pipeline 直接 telemetry 只在 stop/join 后取得。记录 build info、有效配置、
逐帧结果和 Runtime counts；拒绝任何 input-full、失败、output-drop、缺帧。

正式八场景每个只跑一个配置；对每个运行原同步 public API 对照，PCM须逐字节
相同、数值 telemetry 有限、FULL quality 保持。记录 Runtime host 调度/耗时，
但不从其推导真实设备 CPU/p99。发生 host overload 导致控制不等价时保留失败，
不换阈值或丢掉该次记录。

另外只做两个预先固定控制：

1. normal 完整重放一次，比较输入、codec payload、播放 PCM、前端 PCM 和
   非时间计数；wall-clock/调度耗时不要求逐字节相同。
2. normal 的 far 源从包180开始反相，near 从本地播放帧368开始反相。固定前缀
   downlink 前180包、local playout/捕获/前端前368帧、uplink前184包、remote
   playout前376帧逐字节相同；不得根据结果选择边界或对齐。

独立负例覆盖：错误前音量/前PLC参考、非完整20ms输入、截断/奇数PCM、非法
payload长度/解码错误、冲突重复、队列超容、非法事件时标、缺输出、非有限
数值、错误源码/二进制身份。codec函数错误不能伪造静音成功。调度逻辑测试可用
明确测试数据，正式矩阵必须为真正 libopus 和 worker，不得用 mock 替代。

成功条件是所有预注册计数、时序、字节绑定、连续性和错误拒绝满足；结论名为
`HOST_INTEGRATION_COMPLETE`，quality_decision=`NOT_EVALUATED`。
模拟网络、第一方工程信号和本地延迟组件不是实际对讲质量、真人听评、真实房间、
公网性能或 SSC305 资格。没有通过本实验调整 codec/DSP 参数或做效果晋升。

## 预算与保存

各构建、单次测试、正式矩阵（含八场景/八对照/两控制）、独立回读分别从实际
开始计时至完成封存，均限300秒。失败先保存独立报告和退出码，不覆写原目录；
原始日志、PCM/payload、逐帧/逐包记录、实际命令、所有源/库/二进制/数据哈希
保存为可归档产物，Git只保留源码、合同和小结果。正式执行前提交实现字节，
二进制 source_revision 必须对应同一已提交源码；合并后的 main另由现有门禁验证。
