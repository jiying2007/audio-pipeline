# WebRTC AEC3 / APM 离线适配器：固定工程合同

本入口属于独立技术研究。它不链接 SDK、不改公共 C ABI、不替换当前算法，也不授予
音质通过或推广权限。源码准入、构建身份和数据权限由独立 source/build 回执绑定；
本文件定义适配器行为。实际执行结果以对应 Actions 原件为准，代码存在不代表已执行。

## 固定输入与通道语义

[runner](../../../tests/validation/frontend_evolution/webrtc_aec3_runner.cc) 只接受
16 kHz、S16LE、每声道 160 采样的完整 10 ms 帧：

- capture 为 interleaved 1 / 2 / 4 通道；render 是独立的 mono 文件。
- 两个文件的采样帧时长必须完全相同；拒绝空文件、奇数字节、不完整 10 ms 帧和 WAV
  容器。WAV 应在上游用 canonical 材料化入口解码。
- 必须显式给出全排列 channel map。输出通道 j 对应原始输入的 channel_map[j]；
  不做平均、隐式选麦或偷偷恢复原始顺序。
- 直接调用 int16 API，不做文件级/帧级归一化。每次调用产生同样通道数和帧数；
  不补输入、不补尾、不额外 flush。最后尚留在算法状态内的信号不被伪造成可观察尾部。
- 初始化后核对真实 processing/output 通道和 processing rate。上游若拒绝某种几何，
  返回 UNSUPPORTED，退出码 3，保留错误记录；不会降为 mono 后报告“支持”。

输出 PCM、metadata 和 frame-times 路径必须不同、不得等于输入、不得已存在。
父目录需要预先创建。输入/选项合同错误返回 2，上游处理错误返回 4，I/O 等异常
返回 5；不忽略 WebRTC 返回码，不使用其 best-effort 输出冒充成功。

## 两个固定 mode

上游固定为 freedesktop webrtc-audio-processing 2.1，commit
846fe90a289f58b7c9303a635142aa2c7caa93e5。配置使用 api/audio/audio_processing.h。

| 参数 | aec3 | apm |
|---|---:|---:|
| echo_canceller.enabled | true | true |
| mobile_mode / export_linear_aec_output | false / false | false / false |
| enforce_high_pass_filtering | false | false |
| high_pass_filter.enabled | false | true |
| high_pass_filter.apply_in_full_band | true（关闭时无效） | true |
| noise_suppression.enabled / level | false / moderate | true / moderate |
| analyze_linear_aec_output_when_available | false | false |
| gain_controller1.enabled | false | false |
| gain_controller2.enabled | false | true |
| AGC2 input_volume_controller.enabled | false | false |
| AGC2 adaptive_digital.enabled | false | true |
| AGC2 headroom_db / max_gain_db / initial_gain_db | 5 / 50 / 15（关闭时无效） | 5 / 50 / 15 |
| AGC2 max_gain_change_db_per_second | 6（关闭时无效） | 6 |
| AGC2 max_output_noise_level_dbfs | -50（关闭时无效） | -50 |
| AGC2 fixed_digital.gain_db | 0 | 0 |

两模式的 pre-amplifier、capture-level-adjustment、transient suppression、analog
mic gain emulation 均关闭；所有 pre/post gain 固定为 1。multi_channel_capture=true、
multi_channel_render=false、maximum_internal_processing_rate=48000（官方配置允许值；
实际输入/内部处理固定核验为 16000）。capture_downmix_method 显式保留 average_channels，
但必须通过实际多通道处理核验，适配器不执行 downmix。

aec3 mode 仍包含 AEC3 自身的残余回声抑制和相关输出合成。它不是纯线性自适应核。
apm mode 是额外打开固定 HPF、moderate NS 与 AGC2 的系统对照。二者不可混称为同一条
纯 AEC 比较；此参数集在执行前冻结，不根据这次声学结果调参。

每个 case 新建 APM。每帧按 ProcessReverseStream → set_stream_delay_ms(0) →
ProcessStream 顺序执行，不输入 oracle 活动标签，不调用未来帧。--reset-before-frame N
仅用于工程生命周期诊断，在指定零基帧之前重新创建完整 APM 实例；普通声学对照固定
reset_before_frame=null。配置、调用顺序、通道映射和实际几何均进入 metadata。

## 首帧可用时间与信号延迟分开记录

10 ms 是 API 帧时长，不能据此宣布整条算法的信号延迟为 10 ms。本次在执行真实语音
前，从固定上游源码预声明下面的名义缓冲延迟：

| mode | 固定信号延迟 | 静态组成 |
|---|---:|---|
| aec3 | 128 samples / 8 ms | BlockFramer 64 + AEC3 suppression OLA 64 |
| apm | 224 samples / 14 ms | AEC3 128 + NS OLA 96 |

源码锚点均位于上游 webrtc/ 下：

- modules/audio_processing/aec3/aec3_common.h 定义 FFT 128、block 64、frame 160。
- aec3/block_framer.cc 的构造函数初始化 64 个零样本；与 FrameBlocker 的
  80 ↔ 64 调度共同造成 64 样本重分块延迟。
- aec3/echo_remover.cc 的 WindowedPaddedFft 将上一块 64 与当前块 64 组合；
  aec3/suppression_filter.cc 的 ApplyGain 输出合成帧前 64，并保存后 64 到下一块，
  增加 64 样本。该 main-output 路径包含 RES；linear export 路径不是本次接口。
- api/audio/echo_canceller3_config.h 的 fixed_capture_delay_samples 默认 0。
- modules/audio_processing/ns/ns_common.h 为 FFT 256、frame 160、overlap 96；
  ns/noise_suppressor.cc 的 FormExtendedFrame / OverlapAndAdd 增加 96 样本。
- modules/audio_processing/agc2/limiter.cc 在当前 frame 原位 ScaleSamples，没有另加
  sample FIFO。HPF 的频率相关相位变化不能被改写成另一个统一的固定样本平移。

frame-times 分别记录每帧已获得/已输出的采样数、host processing begin/completion 和
duration。metadata 单独记录首输出帧要求 160 个输入采样（10 ms）与本次实际 host
完成时刻。host 数据没有实时 pacing，只作诊断，不是设备时延或 deadline 资格；
首帧可用性、PCM 信号在时间轴上的位移和端到端设备时延是不同量，也不能机械相加。

工程 fixture 固定使用 near-only 脉冲和 chirp、全零 render，独立记录实际脉冲峰位置、
固定 0…384 samples 搜索域内的 chirp 相关峰、预声明延迟处的相关值，以及首帧可用
记录。观测与 128 / 224 不符即 FAIL 查因，不调整冻结值。该合成标定的搜索结果不用于
真实语音 target 对齐；实际声学比较应同时保留原时间轴与固定延迟补偿的有效窗口，
不得对不可观察尾部补零，也不得从目标语音挑选最有利 lag。

## 使用与工程验证

构建仅消费已准入的官方库与 build receipt。上游 Meson uninstalled pkg-config 模块为
webrtc-audio-processing-2-uninstalled；C++17 runner 的 include/lib/rpath 由构建回执
给出。工程执行在 Actions 中进行，不因为开发机缺依赖而创建 mock DSP 替代结果。

示例（目标文件尚不存在）：

    /path/to/webrtc-aec3-runner \
      --mode aec3 --mic-channels 2 --channel-map 0,1 \
      --mic /path/mic.pcm --render /path/render.pcm \
      --output /new/output.pcm --metadata /new/metadata.json \
      --frame-times /new/frames.jsonl

[engineering fixtures](../../../tests/validation/frontend_evolution/test_webrtc_aec3_adapter.py)
必须调用真实 binary：

    python3 tests/validation/frontend_evolution/test_webrtc_aec3_adapter.py \
      --binary /path/to/webrtc-aec3-runner \
      --output /new/engineering-fixtures \
      --build-receipt /path/build-receipt.json \
      --code-revision <显式40位commit>

主报告为 engineering.json；code-revision 仅接收显式 commit，不猜测版本身份。
runtime_identity 复用 CI/对照入口的同一只读观测函数，记录实际 system/machine/release、
/etc/os-release 的 SHA256、ldd 解析到的全部库路径及内容 hash；首尾身份、binary hash
与总 wall budget 再次核对。runtime_identity_source_sha256 还绑定实际导入 helper 的
源码字节并在末尾复验，不能用被改写的宿主检查器生成合格回执。
换宿主重跑此工程 fixture 时保留新回执，后续声学对照须绑定
当次宿主的工程回执，不能用原 CI 宿主身份替代。
测试保存每次真实命令、退出码、stdout/stderr、输入/输出 hash、配置、逐帧时间和独立
延迟观测。覆盖两模式、1/2/4 通道、重复/重建实例、capture/render 分别改变未来的公共
前缀、显式 channel map 与物理重排等价、有效零信号、0.8 秒合成衰减尾、不补尾长度和
异常输入/既存输出拒绝。每条信号不超过 1 秒，总请求 capture 音频预算最多 10 秒，
整套 wall budget 120 秒，每次进程最多 30 秒；任何失败都保留已产生的证据。

PASS_ENGINEERING_ONLY 只说明这些工程合同成立，不证明 AEC3/APM 比当前算法好、
四麦具有空间增益、ASR/KWS 改善、SSC305 实时性或真实声学泛化。
