# AEC3 / APM 六例描述性对照

本入口执行冻结实验 `FE04-WEBRTC-AEC3-REFERENCE-V1`：对已公开的六个
post-BF 开发样例，各运行一次固定 `aec3` 和 `apm` 模式，并与原始归档的
AP MDF、Speex 输出并列报告。完整参数、数据角色、样例字节和预算由
[冻结合同](../../../.github/research/frontend-evolution-v1/webrtc-aec3-reference-v1.json)
定义；合同 SHA256 为
`667847601ae3709cded97d86989f8b65066d01363a1adfa40db1f2be4a522617`。

这是测量方法与可执行入口说明，不是六例已经执行的声学结果。成功的工程
bundle 只证明其记录的真实 binary 工程测试通过。实际对照必须另有
`result.json`、完整输出和独立 `verify` 结果，才能声称完成这次描述性运行。

## 科学问题与范围

六例为 `p0`、`p1` 两对材料各自的 `none`、`steer`、`path` 事件，使用已有
ULA4、70 mm 孔径、FIR33 仿真生成的 **单声道 post-BF 输入**。每例 16 秒、
16 kHz；原始 `input.s16` 按 S16LE 样本交错存放 microphone、render。
入口只拆分两字节样本，不重采样、不重定量化、不做归一化。

| 对照臂 | 输出来源 | 预声明信号延迟 | 解释边界 |
| --- | --- | ---: | --- |
| archived AP | 原始 ZIP 的 `ap.s16` | 0 样本 | 原 ACTIVITY + MDF 输出 |
| archived Speex | 原始 ZIP 的 `speex.s16` | 0 样本 | 原最小 SpeexDSP echo API 输出 |
| WebRTC AEC3 | 固定 2.1 binary 的 `aec3` 模式 | 128 样本 / 8 ms | AEC3 包含内部残余回声抑制 |
| WebRTC APM | 同 binary 的 `apm` 模式 | 224 样本 / 14 ms | AEC3 加 HPF、moderate NS、AGC2 |

AP、Speex 原始执行源码仍为
`e3672ffe16e4c9d42a100e7712b9bbd3d8338545`，不表示当前 main 整条前端的
重新测试。AEC3 与 APM 的处理组成也不同，不能把本表解释为只改变线性
回声滤波器的消融实验。

所有样例角色固定为 `DISCLOSED_DEVELOPMENT_DIAGNOSTIC_NOT_HOLDOUT`。
它们使用已披露材料、已提供的 BF 方向、精确参考同步和线性合成回声路径。
无独立真实房间、未知方向或盲测确认；原 LibriSpeech / OpenSLR 12 的
CC BY 4.0 署名和原 ZIP 中的说明继续保留。第三方代码五权与源码准入复用
[源码说明](WEBRTC_AEC3_SOURCE.zh-CN.md)，不授予其他数据、训练或产品权利。

## 指标不选择延迟或参数

每臂首先直接调用既有 `speexdsp_aec_reference.metrics`，保存其原始指标。
原始 SI-SDR 不补偿 WebRTC 固定延迟，因此还并列报告预声明对齐后的指标：

- 近端窗口固定为 0.1–1.9、6.1–7.9、8.1–9.9、14.1–15.9 秒。
  直接调用 canonical `speech_spatial.si_sdr_span`，目标起点不动，
  output 起点只增加该臂固定的 0 / 128 / 224 样本。
- 远端窗口固定为 12.0–13.9 秒，echo 起点不动，output 加相同固定延迟。
  使用原 canonical 100 ms mean-square 能量窗口的聚合、能量有效性判断和
  `1e-30` 残差分母下限。这样零残差情形也保留原数值语义，不因改为未归一化
  总能量而人为增加约 32.04 dB。
- 输出窗口必须完全落在实际记录的样本内。未知尾部被排除，不补零、不追加
  flush、不让 target 搜索最佳 lag。工程 impulse / chirp 的独立延迟观察也
  不成为真实样例调 lag 的来源。

不计算晋级规则、赢家排序或声学通过阈值。最终处置始终为
`DESCRIPTIVE_ONLY_NO_PROMOTION_NO_RANKING_RULE`。host 时间记录不能证明
SSC305 的内存、功耗或 deadline。

## 输入与来源链

原始归档必须为 `speex-aec-main-original.zip`：10,693,447 字节，SHA256
`aa4961bae5d7eb0d3861ce04ed4c7c8408518f002b856e1f7f9cffa538bdad12`。
入口验证整 ZIP、252 个成员、原 manifest 和所选 30 个数据成员的固定哈希，
拒绝路径穿越、链接、特殊文件、加密成员、重复成员及超预算解压。
不运行原归档内的代码。

另一个输入是成功 CI 产生的工程 bundle。入口核对完整文件清单、真实 runner、
research shared libraries、源码 materialization、原 build receipt、adapter
编译身份、工程 fixture 和共享 runtime observer 的 Git 源码身份。源码准入
仍调用既有 `webrtc_aec3_source.admitted`，不建立第二套准入策略。
工程报告必须有完整的 13 项检查与 62 次小型工程调用，保留所有输入/输出哈希，
并重新核算其不超过 10 秒的 capture 输入预算。

bundle 只携带 WebRTC / Abseil 研究库；系统 libc、libm、libstdc++、libgcc
和 loader 依然来自真实执行主机。它不是跨发行版通用二进制承诺。入口使用
共享 `webrtc_aec3_ci.runtime_identity` 观察当前 host 与动态链接解析，按
SONAME、实际库哈希和 host 身份对照工程报告；目录搬移本身不改变库身份。

如果本机和 CI 主机不同，先在该主机对同一 binary 运行原有、总输入不超过
10 秒、wall 不超过 120 秒的工程 fixture，保留其整目录。此时通过
`--engineering-receipt` 提供新的 `engineering.json`；原 CI 工程证据仍完整
保留和核验。缺失依赖、工程失败或来源不一致会阻止六例开始，不产生代替输出。

## 执行命令

使用包含这些脚本、固定 source / fixture / observer 和冻结合同的已提交源码。
Git 中必须可读取 bundle 所声明的准确 commit；入口不自动联网获取历史。
先根据成功 CI 的工件清单恢复 bundle；本次六例在核验成功的源码/工程 CI 之后执行。
所有路径使用实际绝对路径；下面路径是需要替换的示例。

不同宿主需要的工程复验：

```bash
LD_LIBRARY_PATH=/abs/bundle/bin/lib python3 -B \
  tests/validation/frontend_evolution/test_webrtc_aec3_adapter.py \
  --binary /abs/bundle/bin/webrtc-aec3-runner \
  --build-receipt /abs/bundle/build/build-receipt.json \
  --code-revision BUNDLE_COMMIT_40_HEX \
  --output /abs/new-host-engineering
```

只在源码工程 CI 与本次主机工程检查成功后执行六例：

```bash
python3 -B tests/validation/frontend_evolution/webrtc_aec3_reference.py run \
  --bundle /abs/bundle \
  --archive /abs/speex-aec-main-original.zip \
  --engineering-receipt /abs/new-host-engineering/engineering.json \
  --output /abs/new-aec3-reference

python3 -B tests/validation/frontend_evolution/webrtc_aec3_reference.py verify \
  --output /abs/new-aec3-reference
```

若实际 host/runtime 与 bundle 中 CI 工程报告完全一致，可省略
`--engineering-receipt`。输出目录必须全新，且与 bundle、原 ZIP 分离。
每例新建进程/实例，两个模式各一次，共 **12 次**；wall 总预算 **300 秒**，
不重试、不搜索、不训练。超时终止该 process group，失败前已有的命令、日志
和输出保留；新的尝试需要显式处理原失败与实验预算，不能由入口自动补跑。

`run` 返回 `EXECUTED_DESCRIPTIVE_REFERENCE`，同时明确要求单独执行 `verify`。
300 秒预算包含运行前验证、复制、12 次真实调用、指标和封存；独立只读核验
另外执行，不调用 AEC binary。核验成功返回 `VERIFIED_DESCRIPTIVE_REFERENCE`，
两者的 `acoustic_acceptance` 和 `promotion_allowed` 均为 false。

## 结果保全与独立核验

输出保留原 ZIP、完整工程 bundle、本次主机工程目录（若使用）、冻结合同、
测量源码及其实际 repository import 闭包。每例保留输入原件、拆分后的
mic/render、两个模式的完整 output、metadata、逐帧 JSONL、命令、日志和
单调时钟起止。`manifest.json` 覆盖全部文件字节，不自引用自身。

独立 `verify` 从输出重新读取原始数据与四臂实际输出，重算全部 raw/aligned
指标，核对六例十二次、每例 256,000 样本 / 1,600 帧、真实命令参数、固定
配置/延迟、逐帧顺序、来源哈希和结论结构。报告改成 blind、删例、换输入角色、
改 lag、缺帧、伪造分数、允许 promotion 或换源码，均不能靠重新生成外围
manifest 获得通过。存在 `failure.json` 的失败/部分结果明确拒绝，重封 manifest
也不能把封存后超时变成成功结果。verify 读取 Git 与源码作身份核验，不执行保存的源码，
也不要求执行核验的机器拥有原 host 的系统库。

可将整个结果目录搬移后核验；命令原始绝对路径作为历史身份保留。为复核数值，
使用相同的测量实现和兼容 Python 环境；这些脚本保持 Python 3.8 语法兼容。
Actions artifact 是传输副本，长期保全仍需保存完整结果、原 ZIP、工程 bundle、
相应 Git 源码和各项 SHA256，不能只保存一份最终分数表。

纯小型回归命令：

```bash
python3 -B tests/validation/frontend_evolution/test_webrtc_aec3_reference.py
```

它只使用构造的字节、JSON、短向量和临时本地 Git 仓库验证 transport、数学和
语义拒绝路径；不调用 AEC binary、不生成声学 PASS，也不替代真实工程与六例运行。
