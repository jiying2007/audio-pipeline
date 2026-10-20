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

当前提交只声明恢复和执行前资格：22 个官方文件重新下载，逐项 SHA-256 匹配历史
固定锚点；Speex 原始 ZIP 及六例输入全部校验；25 项既有合同测试与 4 组完整 PCM
边界测试通过。新的效果、耗时和最终结论须由随后重新执行的结果补齐。
SOF 的 offset=8 语音源正由统一的原始归档恢复，完整 SOF 合同必须在 DSP 执行前固定。

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
```

脚本不会下载数据或运行训练。模型文件先经准入和散列验证再加载。
发生失败保留 output 中的失败记录、已有 PCM 和日志；不能覆写失败目录来隐藏失败。
`--verify` 重算来源、合同、全量输出尺度、完整流式轨迹和 canonical 指标；
`--negative-evidence` 对重新封存后的语义篡改做拒绝测试。
