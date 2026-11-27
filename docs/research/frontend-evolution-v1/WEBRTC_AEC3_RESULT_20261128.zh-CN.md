# AEC3 固定参考：2026-11-28 真实工程与六例诊断结果

## 结论与执行范围

**固定 AEC3 参考已完成真实构建、跨宿主工程复验、一次冻结六例执行与独立回读。**
AEC3 的远端段能量抑制比提高，同时在第二组素材的双讲窗口出现明显语音保真损失。
完整 APM 在一个路径变化案例中的远端表现也明显下降。本轮结果不足以支持替换现有默认算法。

预登记的正式处置保持 `DESCRIPTIVE_ONLY_NO_PROMOTION_NO_RANKING_RULE`，
`acoustic_acceptance=false`、`promotion_allowed=false`。这是诊断结果的完成，
没有产生独立留出集、完整双麦整链、公共四麦 SDK 或 SSC305 实机通过结论。

实施父项为 [#968](https://github.com/jiying2007/audio-pipeline/issues/968)，
基础方法集成为 [#970](https://github.com/jiying2007/audio-pipeline/pull/970)，
本研究为 [#971](https://github.com/jiying2007/audio-pipeline/pull/971)。仓库集成状态以其实际
受保护 merge/main 记录为准；本文件的科学证据绑定下面的原始执行 commit，不用后续文档 commit 替代它。

## 1. 实际证据链

| 项目 | 原始身份与结果 |
|---|---|
| 实验 | `FE04-WEBRTC-AEC3-REFERENCE-V1` |
| 实际构建与测量源码 | `819849ee3ed6b269b8417ef8700eecfcf29f7958` |
| 冻结 plan SHA256 | `667847601ae3709cded97d86989f8b65066d01363a1adfa40db1f2be4a522617` |
| Actions 成功 run / job | `46043812502` / `140658030938` |
| Actions 工程状态 | `PASS_ENGINEERING_ONLY`，实际编排 127.093754927 秒 |
| 原成功 Artifact | `15220044392`，11,138,223 字节 |
| 原成功 Artifact SHA256 | `9e6dcc80317f689779d05da212143cf2d5287f0c30868b469a9ae8c9b1fd6d48` |
| 实际 binary SHA256 | `b4007d7ec35f0622298c57865a624e8e2f3d044c85cf391b51652d77cb57808d` |
| 宿主复验 | Debian 13 / x86_64，同一 binary 与研究库；13 项检查、62 次调用、6.95 秒合成音频、1.227437938 秒 wall |
| 新声学执行 | 六例 × AEC3/APM，12 次调用、19,200 帧、6.129860425 秒；0 训练、0 搜参、0 重试 |
| 独立回读 | `VERIFIED_DESCRIPTIVE_REFERENCE`，exit 0；回读不调用 DSP |
| sealed manifest | 3,099 个成员、70,157,180 字节，不含 manifest 本身 |

[真实成功日志](https://github.com/jiying2007/audio-pipeline/actions/runs/46043812502)与
[原始 Artifact](https://github.com/jiying2007/audio-pipeline/actions/runs/46043812502/artifacts/15220044392)
共同对应上述身份。机器摘要见 [WEBRTC_AEC3_RESULT_20261128.json](WEBRTC_AEC3_RESULT_20261128.json)，
独立审查原回执见 [WEBRTC_AEC3_INDEPENDENT_REVIEW_20261128.json](WEBRTC_AEC3_INDEPENDENT_REVIEW_20261128.json)。

首次 run `46043193599` 在收集库文件时把 Meson `.so.1.p` 对象目录当成共享库读取，失败如实保留。
修复仅增加非符号链接普通文件过滤及回归用例，不修改来源、算法、预算或评分。
原失败 Artifact `15220518270` 和完整成功原件都保存在最终证据包中；失败轮次不改写为 PASS。

## 2. 对照口径

六例来自两个已披露材料对，各含 none、steer、path 三种事件变体。ULA4-70 表示原四麦阵列
**70 mm 孔径**；本次比较从其已封存 post-BF 单通道边界开始，单独保留 render。
每例为 16 kHz S16LE、16 秒、256,000 样本。不能把六行当作六次独立采样，也不能把该边界
描述成新测的双麦或四麦整条 pipeline。

原 AP 与 Speex 输出保留来源 `e3672ffe16e4c9d42a100e7712b9bbd3d8338545`，不重新运行、
不改称当前 main。新 AEC3 含其内部 residual suppression；完整 APM 另固定开启 HPF、moderate NS
与 AGC2。这两臂是预先冻结的不同组成，不能从 APM 与 AEC3 的差值单独归因到某一个模块。

每例独立创建实例，reverse 在 capture 前，stream_delay_ms=0，没有中途 reset。
AEC3 / APM 的固定信号延迟为 128 / 224 样本（8 / 14 ms）；原始 canonical 分数完整保留，
另报告预登记 offset 下完整可观测窗口的对齐分数。没有对 target 搜索 lag，也不为未观测尾部补零。
首个完整输出帧需要 160 个输入样本（10 ms 帧粒度），与上述信号延迟、宿主处理时间及物理端到端延迟分别记录。

## 3. 对齐后的描述性统计

远端列是固定远端窗口的 echo/output 能量比，near 列是 canonical SI-SDR，均为 dB。
以下仅报告六例的算术均值和远端范围，不给总体排名、统计显著性或新的通过阈值。

| 对照臂 | 远端均值〔范围〕 | near-initial | double-before | double-after | near-final |
|---|---:|---:|---:|---:|---:|
| 原 AP | 12.40〔7.09–20.88〕 | 123.57 | 15.70 | 15.10 | 118.04 |
| 原 Speex | 10.87〔0.04–26.70〕 | 12.17 | 11.43 | 10.71 | 12.32 |
| WebRTC AEC3 | 33.49〔26.65–41.68〕 | 123.57 | 2.17 | 4.05 | 74.46 |
| WebRTC APM | 23.72〔7.52–41.06〕 | 7.65 | 0.64 | 2.54 | 7.94 |

### 数值高值的解释

原 AP 与 AEC3 的六个 near-initial 窗口在固定对齐后都与 target S16 **逐字节相同**，
共有 12 个“臂 × 案例”窗口。116.85–130.29 dB 来自 canonical SI-SDR 的 `1e-12` 能量正则项，
不是实测物理 SNR、器件动态范围或盲测音质。原 AP 六个 near-final 也字节相同；
AEC3 的 p0 三例 near-final 相同，p1 三例为 24.26–25.09 dB。因此不能把其 74.46 dB 的
混合均值当作有物理意义的单一音质指标。原始字节审计在独立回执与完整证据包中保留。

### 六例远端能量抑制比

| 材料对 / 事件 | 原 AP | 原 Speex | AEC3 | APM |
|---|---:|---:|---:|---:|
| p0 / none | 8.23 | 26.70 | 41.68 | 41.06 |
| p0 / steer | 8.99 | 22.39 | 41.05 | 37.61 |
| p0 / path | 7.09 | 14.87 | 36.28 | 7.52 |
| p1 / none | 19.45 | 0.62 | 27.51 | 19.11 |
| p1 / steer | 20.88 | 0.62 | 27.74 | 19.23 |
| p1 / path | 9.76 | 0.04 | 26.65 | 17.78 |

### 六例事件后双讲 SI-SDR

| 材料对 / 事件 | 原 AP | 原 Speex | AEC3 | APM |
|---|---:|---:|---:|---:|
| p0 / none | 6.72 | 14.95 | 7.77 | 5.42 |
| p0 / steer | 7.16 | 14.08 | 7.52 | 5.09 |
| p0 / path | 6.44 | 9.27 | 5.86 | 3.90 |
| p1 / none | 24.81 | 8.70 | 1.07 | 0.34 |
| p1 / steer | 25.27 | 8.50 | 0.97 | 0.32 |
| p1 / path | 20.16 | 8.74 | 1.10 | 0.20 |

AEC3 六例远端平均值为 33.49 dB，但 p1 三例 double-before 均为 −4.78 dB，
double-after 仅约 0.97–1.10 dB。远端抑制改善不能替代近端保真验证。
APM 的 p0-path 远端值为 7.52 dB，同例 AEC3 为 36.28 dB；这里只记录固定组成的观察，
没有据此追加调参、生成新候选或补跑同批样本。

## 4. 宿主运行成本

每个模式包含 9,600 帧。计时覆盖 `ProcessReverseStream`、`set_stream_delay_ms(0)`、
`ProcessStream`，不含帧文件 I/O 和首次实例构造。p95/p99 使用 nearest rank。

| 模式 | 平均 ms/帧 | 中位数 | p95 | p99 | 最大 |
|---|---:|---:|---:|---:|---:|
| aec3 | 0.07452 | 0.03882 | 0.27784 | 0.76342 | 2.42891 |
| apm | 0.09575 | 0.05958 | 0.30755 | 0.78048 | 1.94145 |

这些是本次 Debian 13、x86_64 宿主上的描述性数据，不能外推到 SSC305 deadline、RSS、
功耗、热稳态或实际音频链路延迟。原 AP/Speex 的旧宿主耗时没有与本轮混合比较。

## 5. 完整原件与复验

完整交付文件：`audio-pipeline-aec3-evidence-20261128.tar.gz`，45,053,155 字节、3,108 个成员。
SHA256：`33af853e070cf46bcc2a4aab60e4417d58ae8454f50e74eea3e62f5cfbde077e`。

它保留原失败与成功 CI ZIP、原 GitHub 元数据、原 Speex ZIP、固定 plan、完整工程 bundle、
本宿主工程回执、20 个测量实现及其 import 依赖、所有输入/输出 PCM、逐帧 trace、实际命令、
原始 result/manifest，以及独立回读与字节审计。交付的完整原件由项目所有者保管；
GitHub Actions 的保留期不被当成长久可用承诺。

原 `result.json` SHA256：`2f65de94d7d8de636fc4dc82e2d20c0990c29e005a06958a2d1dbe08a083f60d`。
原 `manifest.json` SHA256：`9a44b195432148296429eb0107f137675de945fb756819f9e27da02ca03a16f6`。

在包含原执行 Git 对象的仓库中，切换至上述实际代码版本，解开原件后执行：

```sh
python3 -B tests/validation/frontend_evolution/webrtc_aec3_reference.py verify \
  --output /absolute/evidence/comparison
```

`verify` 只回读和重算；不要把新增文件放进 sealed comparison 目录，不要用新生成数据替换失效原件。
源码、库、数据角色、输出、分数、帧数或结论被改写，以及失败包重新封 manifest，均须拒绝。

数据来源和归属：LibriSpeech / [OpenSLR 12](https://www.openslr.org/12/)，Vassil Panayotov、
Daniel Povey、Guoguo Chen、Sanjeev Khudanpur，录音来自 LibriVox；遵循
[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/)。本次使用既有已披露的合成 post-BF 派生材料。
外部代码、权重和专利声明按固定 source/admission 文件及随包原 notices 保留，不产生新的训练或其他数据许可。

## 6. 本轮处置与后续边界

保留固定 AEC3/APM 作为可重现的诊断参考，保持当前默认实现。本轮不增加参数搜索或训练，
不复开历史已关闭的候选。后续若研究双讲保护、分段控制或独立模块组合，应新建实验身份，
冻结对应假设与预算，再准入未参与选择的独立数据。当前已披露六例不能重新命名为 blind/holdout。

本新增 AEC3 参考的完整原生双麦/四麦系统比较、SSC305 交叉构建与实际 target 的 deadline/RSS/功耗/热/长稳态、
真实非线性换能链路及独立新语料确认仍分别记为未完成或 NOT_RUN；现有硬件或数据缺失不以软件回执补造。
长期平台入口与执行边界见 [运行手册](LONG_TERM_RESEARCH_PLATFORM.zh-CN.md)。
