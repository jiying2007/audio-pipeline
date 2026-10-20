# 有限外部对照：SOF FIR、GTCRN 与 UL-UNAS

## 状态与范围

本记录对应已授权的 frontend-evolution-v1 学术、非商业本地研究。固定基线为
`e3672ffe16e4c9d42a100e7712b9bbd3d8338545`。shipping 默认、2.x 公共 ABI、
`AP_MAX_MIC_CHANNELS`、I025–I040 冻结结果及 E001 产品证据身份均不变。

2026-10-20 会话工作区丢失后，本分支从同一基线恢复可执行代码并重新取得原始字节。
先前三个本地提交 `41b02db`、`9f42f5a`、`99df9c2` 及其输出当前不可读，
不能作为本轮验收的文件证明。代码按可见完整历史恢复，未声称与丢失提交逐字节相同。
合同保留原来样例、源提交、模型、阈值和数据角色；恢复元数据及排版并非原 JSON 字节。
此前效果已经披露，因此本轮是恢复重执行，不是新盲测或独立验证。

恢复后的 NN 六例对照已经重新执行、独立复核并通过九项证据语义负例。
22 个官方文件重新下载，逐项 SHA-256 匹配历史固定锚点；Speex 原始 ZIP 及六例
输入全部校验；25 项既有合同测试与 4 组完整 PCM 边界测试通过。
SOF 的 offset=8 原始准入语音已经恢复并重新解码验证，完整合同先于本轮 DSP 执行
固定。SOF v2 已完成六例、24 个混合 arm、全部 72 个组件输出复核，以及 13 项
重新封存的语义负例。固定三参考恢复工作已经形成可读取、可重新验证的本地结果。

## 三项限定来源

| 参考 | 固定官方提交 | 实际进入实验的部分 |
| --- | --- | --- |
| [SOF](https://github.com/thesofproject/sof/tree/460f18d9bc70729d9479f0645730e61c94a9ca97) | `460f18d9bc70729d9479f0645730e61c94a9ca97` | 原版 generic FIR C、必要原版头文件、原版线性四麦系数；first-party host 传输/混合边界 |
| [GTCRN](https://github.com/Xiaobin-Rong/gtcrn/tree/502ebfab64da7c4a9af78dcb9c6ceef1ebb01c73) | `502ebfab64da7c4a9af78dcb9c6ceef1ebb01c73` | `stream/onnx_models/gtcrn_simple.onnx` |
| [UL-UNAS](https://github.com/Xiaobin-Rong/ul-unas/tree/00f7c700da43d38347f30a6ccebd86fcbc798e07) | `00f7c700da43d38347f30a6ccebd86fcbc798e07` | `ulunas_onnx/onnx_models/ulunas_stream_simple.onnx` |

模型 SHA-256：

- GTCRN：`b4718df6228e7bdf1a8a435cf98f838636eb2fd331acabf86ba87c5192ebcb87`。
- UL-UNAS：`f2e804d54d6a88f4f82f44d86c9f1cf646db2509bfca935cfbfc5fcd8cbfac3b`。
- SOF 选择后四个 FIR 的系数二进制：`8faeac26f7232ddb74ac1148e079cee534edaa3ef64c740ea67593d73a88fdae`。

完整路径、长度、Git blob SHA-1、SHA-256 在
[源码锁](../../../.github/research/frontend-evolution-v1/external-baselines-source-lock.json)。
[准入记录](../../../.github/research/frontend-evolution-v1/external-baselines-admission.json)
将代码、依赖、权重、数据、再分发分别登记。GTCRN/UL-UNAS 的所选官方仓库 LICENSE
为 MIT，SOF 所选 FIR 代码及系数保留原 BSD 许可声明。 bundled 模型未发现所审阅文件中
另行排除的权重条款；作者报告的 DNS3 训练来源没有被本项目独立审计，也没有下载 DNS3。
本地研究准入不是更广泛产品分发的资格。

现有 FIR33/SPATIAL33 已吸收公开 FIR/阵列数学；此处的目的，是让固定原版 SOF
内核和系数形成独立效果对照。它不是完整 SOF 固件移植，也不是 XMOS 实现。
现有 `xmos-lib-voice` source 项保持原状，不新增重复条目或扩大候选清单。

## 完整神经流式边界

[固定 NN 合同](../../../.github/research/frontend-evolution-v1/external-neural-v1.json)
先于本轮模型运行登记。仅允许 16 kHz 单声道输入，无 render 通道；512 点 FFT，
256 样本原生 hop，外部每次最多 160 样本。8 kHz 和 48 kHz 明确拒绝，另行 SRC
及其延迟、资源和效果资格不由本次补齐。

`neural_pcm.py` 是声明过的 first-party 完整 PCM 适配器。原版范围只限 ONNX 图；
不是上游整文件示例或 PyTorch checkpoint 的等价证明。GTCRN 用周期 sqrt-Hann，
UL-UNAS 用周期 Hann。初始左侧补 256 个零；不读未来、不使用整文件 reflect-padding，
不做逐文件归一化。上游示例窗口/边界差异必须与模型本身分开。

输出区间 `[k*256, (k+1)*256)` 在收到 `(k+2)*256` 个真实样本后才能最终确定。
原生输入 512 样本时首次可输出；固定 160 样本调度要到累计 640 样本（40 ms）才会
交出首块 PCM，不能把 16 ms hop 当成端到端延迟。只在显式 flush 时补末尾零并加一个
零 hop，经 window-square OLA 归一化并剔除固定左补零，裁回原样本数。
每个 16 秒样例保留全部 1,600 次 push 时间、完整可用性序列和含 flush 的 1,001
网络帧，不只报告平均推理速度。

显式模型缓存为 GTCRN 72,192 B，UL-UNAS 27,264 B；PCM FIFO 上界 415 样本。
这不含 ORT arena、Python 对象和瞬态 FFT 存储。进程 RSS 仅是宿主整个进程数据，
不能作为 SSC305 SRAM 或模型独占内存。ONNX Runtime 固定 1.23.2、CPU provider、
sequential、intra/inter 各一线程；确切环境、二进制和 notices 写入每次证据。

## 输入和判定合同

神经对照固定使用 Verify 39274232480 / artifact 12199497546 的原始 Speex ZIP：
10,693,447 B，SHA-256
`aa4961bae5d7eb0d3861ce04ed4c7c8408518f002b856e1f7f9cffa538bdad12`。
它含六个 `p{0,1}-ula4-70-fir33-{none,steer,path}` 样例，每个 16 秒，
对每个 arm 使用同一 `ap.s16`，并保留固定 `target.s16` 与 `echo.s16`。
输入字节、输出数和成员清单都强校验，不改 AEC/BF 前驱。

现有 `speexdsp_aec_reference.metrics` 调用既有 canonical evaluator。
诊断候选同时要求：24 个有近端语音阶段中的最大 SI-SDR 损失不超过 0.5 dB，
六例末段 far-only 的平均额外衰减至少 3 dB。阈值不因重执行或已知结果修改。
若 AP 原样近乎精确等于量化 target，SI-SDR 可接近数值上限，必须同时给出绝对
before/after 和阶段含义，不能把极大 dB 差解释成听感损失。

所有输入均为已披露开发诊断，不属于 holdout、真实机器人阵列录音或产品 PASS。
语音原素材为 [LibriSpeech / OpenSLR 12](https://www.openslr.org/12/)，
Vassil Panayotov、Daniel Povey、Guoguo Chen、Sanjeev Khudanpur，
录音源于 LibriVox，按 [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/)
保留原 notices 与改动归属。空间混合是明确的合成研究衍生物。

## 本轮 NN 固定结果

本轮独立复核返回 `VERIFIED_LOCAL_DIAGNOSTIC`：6 例、18 个混合输出 arm。
所有输出重新完成 PCM 量化/样本数/成员散列和 canonical 指标校验。每个模型在每例
另跑 37 样本分块并 reset；与 160 样本分块逐字节一致。修改后半段实际输入，
已经完成的前缀不变，后续输出确实变化；不是只做了相同输入的重复。

| 固定 arm | 六例平均 far-only 额外衰减 | 最大近端阶段 SI-SDR 损失 | 原规则结果 |
| --- | ---: | ---: | --- |
| GTCRN | 4.386166 dB | 100.913908 dB | `REJECT_D0_POST_AEC_CONFIGURATION` |
| UL-UNAS | 8.134560 dB | 96.966000 dB | `REJECT_D0_POST_AEC_CONFIGURATION` |

最大损失都来自 `p0-ula4-70-fir33-none / near-initial`。passthrough 为
130.290227 dB，GTCRN 为 29.376318 dB，UL-UNAS 为 33.324226 dB。
这个不含回声的阶段中 AP 几乎精确等于量化 BF target，baseline 因此靠近数值上限。
表中 100 dB 量级差不是听感损失、通用降噪劣化或语音可懂度下降的量化结论。
固定保真规则仍未满足，不能在看到结果后放宽阈值。

两者在混合语音阶段也有改善。六例 `double-before` 平均 SI-SDR 为
passthrough 15.702295、GTCRN 17.243348、UL-UNAS 17.561680 dB；
`double-after` 为 15.095367、15.213490、15.913999 dB。
这些阶段数据说明不能仅凭末段远端衰减或数值上限附近的损失来概括整体效果。
最终拒绝只适用于这里的 AP 后置、固定图及适配边界；未证明模型在其他场景无用，
也没有开启新的 NS 微调、参数搜索或训练。

| 宿主完整 PCM push | GTCRN | UL-UNAS |
| --- | ---: | ---: |
| p50 / p95 / p99 | 0.913 / 1.949 / 5.051 ms | 1.085 / 2.223 / 5.662 ms |
| 最大值 | 380.542 ms | 344.462 ms |
| >10 ms 次数 / 9,600 push | 44 | 55 |
| 包含 flush 的总体 RTF | 0.107003 | 0.123777 |

这些是本轮共享开发宿主上完整 PCM push 的壁钟时间，含线程被调度出去的时间，
不是孤立 ORT kernel 耗时。未定位长尾的具体原因，不重跑挑最好成绩。
宿主进程峰值 RSS 为 143,132 KiB，包含两个模型、Python 和 evaluator。
本表不能用作 SSC305 CPU/IO、内存或 10 ms 截止资格。

新结果文件 SHA-256：
`4de5abc3076904e0908650a58e8648b4eea246c9c3ef1a1379e923072cbc7f8d`；
新 manifest SHA-256：
`91ad194062d31b6cef822765c9b66e800285ce97632851b62b4bcf7ffcdfc290`。
这两者来自本轮实际输出，不是旧会话文件的散列转录。

九项重新封存的证据篡改均被拒绝：缺例、shipping promotion、holdout 改标、错误模型、
伪造评分、翻转结论、缺失工程验证、删减 push 时间、删减完整输出可用性。
源预检也实际拒绝了模型字节篡改、额外文件和符号链接。
这些是有限已测输入/证据的工程检查，不能推广成所有可能输入的形式化证明。

## SOF 独立对照的固定合同

[SOF 合同](../../../.github/research/frontend-evolution-v1/sof-fir-reference-v1.json)
选择原版 `coef_line4_28mm_pm90deg_16khz.m4` 的第 0–3 个 FIR，即第一个
+90° 输出；64 taps，`out_shift=[1,2,2,1]`，4 个麦克风位于 Y 轴
`[+42,+14,-14,-42] mm`，孔径 84 mm。保留原 Q4.12 坐标元数据，
不把这组系数用于 70 mm 或环形四麦，也不执行设计脚本或调系数。

四个对照是现有 `fir33 / diffuse-0.1 / diffuse-1.0` 和独立 `sof64`。
输入均为 16 kHz、每次 160 样本、四麦 interleaved S16；原 FIR 内核每次计算两样本。
原 SOF FIR C/头文件不修改，host shim、传输、Q5.27 相加与输出格式转换明确属于
本项目适配层，因此不会声称“完整原版 SOF TDFB 固件”跑通。
8/48 kHz、不同几何和另一输出方向都需另外固定系数与资格。

SOF 固定对齐 34 样本由系数的解析群延时约 34 样本事先确定；其他三个 arm
沿用 21 样本，不对每例搜索延迟。两个开发说话人对各跑：
目标 +90°/干扰 -90°、目标与干扰同为 +90°、目标 +60°/干扰 -90°。
独立组件输出同时核查 SIR、target gain、相对误差能量与 SI-SDR，
并直接从实际系数计算 200–7,000 Hz 的 WNG、3D diffuse DI 和方位响应。

语音恢复使用原准入中绑定的
[run 37337539976](https://github.com/jiying2007/audio-pipeline/actions/runs/37337539976)
artifact 11357177181，5,171,219 B，ZIP SHA-256
`eb780ba093e19b21f2753048018c05ef0467ba6ebbe6c03d4372fd3ed0e0c8e1`。
本轮原 ZIP 已整包核验、原 source receipt 未改；32 个 FLAC 由当前 FFmpeg
重新解码，32 项 PCM 散列及 8 个四秒窗口全部一致，原准入 bound
`f77a897bf9681af2c09f57515b99fb2d7ca072dc93371d438e872579e39f801e` 通过。
只评分原开发说话人 1673/1919 和 1988/1993，另外四位原确认角色保持不变。
这条恢复路径没有宣称本轮重新下载了完整 LibriSpeech 原归档。

## 本轮 SOF 结果与验收

下表是目标 +90° / 干扰 -90° 两个开发说话人对的平均值。数字来自本轮 v2，
与保留的 v1 全部 72 个 target/interferer/mixture Float32 输出逐字节一致。

| arm | component SIR 增益 | target gain | target 相对误差能量 | canonical SI-SDR |
| --- | ---: | ---: | ---: | ---: |
| FIR33 | 1.526486 dB | -0.000309 dB | 0.000009719 | 1.489528 dB |
| SPATIAL33 diffuse-0.1 | 7.208022 dB | 3.346169 dB | 0.250001267 | 6.744000 dB |
| SPATIAL33 diffuse-1.0 | 3.306021 dB | 0.618426 dB | 0.007107418 | 3.247669 dB |
| 原版 SOF FIR64 + 声明适配 | 4.878552 dB | 0.034738 dB | 0.000099405 | 4.833189 dB |

独立 SOF 参考比 FIR33 多取得约 3.352 dB 分离增益，on-axis 目标增益接近 0 dB。
diffuse-0.1 的分离分数更高，同时有约 3.35 dB 目标幅度变化和 0.25 的相对误差能量，
不能只比较 SIR 或尺度不变的 SI-SDR 后就推广为整体更优。这验证了独立原版对照
的价值，并未改动已有 FIR33/SPATIAL33 算法或重新搜索其参数。

SOF 在同方向对照中的 component SIR 增益只有 0.021642 dB；在固定波束偏离目标
30° 的对照中为 4.804898 dB。两者仍只说明所测合成自由场场景的行为。
从实际系数计算出的 WNG，在 200/500/1,000 Hz 分别为
-3.205199 / -4.881219 / -3.283896 dB，FIR33 对应约 +6.0206 dB。
由此可推断该固定 SOF bank 的低频独立麦克风噪声放大和误差敏感性值得单独验证；
当前实验没有把真实自噪、麦克风失配、房间混响或机器人运动的效果测出来。

原版 C FIR 在 native 和 ASan/UBSan/LeakSanitizer 下，与独立 Python 整数直接
卷积 oracle 的 3,200 样本输出严格一致；2 与 160 样本分块严格一致。
每例全长组件还用直接整数卷积重新验证，原始 FLAC 到多麦刺激则通过独立 Python
重建核对。没有只信 runner 自报 PASS 或仅检查输出 manifest。

v1 复核中发现一个真实漏洞：删除 400 个 timing chunks 中的一项，再重算封存，
旧 verifier 仍接受。保留的 v1 原始记录实际包含全部 400 项，声学输出没有缺失。
修复提交 `2879436ccc5754bb58f0b0a039a17e90f805094c` 新增精确 native 块大小、
采样率、通道/输出数、资源计数与完整非负整数时间记录检查；新增负例前先把旧
NaN 负例完全恢复，并验证干净正例，防止前一个错误遮蔽后一个测试。
v2 以原样例、原模型/系数、原阈值再次执行，两项新时间负例均被拒绝，合计 13 项。

| SOF 六例混合输出的线程 CPU 时间 | 保留 v1 | 验收 v2 |
| --- | ---: | ---: |
| 160 样本块 p50 / p95 / p99 | 17.839 / 38.220 / 154.679 μs | 21.182 / 39.053 / 187.753 μs |
| 最大值 | 1,237.281 μs | 1,861.598 μs |
| 2,400 块总体 RTF | 0.002539 | 0.002926 |
| FIR 状态、系数、delay 持久字节 | 1,808 B | 1,808 B |

SOF 计时使用 `CLOCK_THREAD_CPUTIME_ID`，含 FIR、求和和 PCM 数值转换，
不含文件 I/O、构建、初始化、评价或调度等待。NN 表使用完整 push 壁钟，
两者的计时范围不同。1,808 B 也只统计 C FIR 持久状态、系数和延时线；
I/O 缓冲、时间数组、进程与运行时均未计入。没有 SSC305 实测资格或自动晋升。

v2 新结果 SHA-256：
`f50602899e9549f301e8ddfe7a7235d360fa97503a2e7fe40b6ff5d341018d32`；
新 manifest SHA-256：
`f3e1bab935983e55a46140541786944ee360bc8e3f9255dfebc7af40b9537a90`。
版本化 [恢复结果索引](../../../.github/research/frontend-evolution-v1/external-baselines-recovery-result.json)
保存对应源码/合同/原件身份、固定效果、工程验证和反例清单。完整证据保留实际 PCM、
时间序列、二进制、原 notices、代码快照、旧 v1 和漏洞复现回执。

## 接下来的资格边界

本轮只完成三个限定参考的本地可执行对照。SOF 留作独立 FIR 效果基线；
GTCRN 和 UL-UNAS 的这个固定后置配置按原规则停止，不扩充后端清单或继续微调 NS。
进入 SSC305 的下一步应接续现有 A1/四麦软件集成与资源资格，复用已有 prototype。
公共 C4、8/16/48 kHz 全链路、多麦全双工 AEC、线程/IO 截止、真实机器人噪声和
产品证据仍分别遵循其既有合同，不能从这里的宿主公开数据诊断推导完成。

## 本地运行

在仓库根执行，环境和输出路径由调用者指定。以下文件名只是示例；输出目录必须全新。

```sh
python3 -m venv external-venv
external-venv/bin/python -m pip install -r tests/validation/frontend_evolution/external-neural-requirements.txt
external-venv/bin/python tests/validation/frontend_evolution/external_source.py --fetch --output external-source
external-venv/bin/python tests/validation/frontend_evolution/test_contracts.py
external-venv/bin/python tests/validation/frontend_evolution/test_neural_pcm.py
external-venv/bin/python tests/validation/frontend_evolution/external_neural.py --source external-source --archive speex-aec-main-original.zip --output neural-evidence
external-venv/bin/python tests/validation/frontend_evolution/external_neural.py --output neural-evidence --verify
external-venv/bin/python tests/validation/frontend_evolution/external_neural.py --output neural-evidence --negative-evidence

# Reuse the exact admitted offset=8 cache, or rebuild it from the same original archive:
external-venv/bin/python tests/validation/frontend_evolution/speech_source.py --archive dev-clean.tar.gz --speaker-offset 8 --output spatial-source
external-venv/bin/python tests/validation/frontend_evolution/sof_fir_reference.py --source external-source --data spatial-source --output sof-evidence
external-venv/bin/python tests/validation/frontend_evolution/sof_fir_reference.py --output sof-evidence --verify
external-venv/bin/python tests/validation/frontend_evolution/sof_fir_reference.py --output sof-evidence --negative-evidence
```

脚本不会下载数据或运行训练。模型文件先经准入和散列验证再加载。
发生失败保留 output 中的失败记录、已有 PCM 和日志；不能覆写失败目录来隐藏失败。
`--verify` 重算来源、合同、全量输出尺度、完整流式轨迹和 canonical 指标；
`--negative-evidence` 对重新封存后的语义篡改做拒绝测试。
