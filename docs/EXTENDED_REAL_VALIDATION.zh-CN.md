# Extended Real 真实数据验证

本文定义 Compact100 / Full160 之上的真实公共声学验证层。它扩大真实远场、移动声源、实测房间、环境噪声和多人会议覆盖，但**绝不替代真实产品板 HIL 与 Product Certification**。

## 证据边界

Extended Real 只能产生 `validation-grade`、`validation-grade-blind` 或 `research-validation` 证据。它可以证明算法在第三方真实数据上的表现，也可以暴露 3–5 m、moving source、meeting overlap、noise/music hard negative 等薄弱点；但不能证明实际发货麦克风、外壳、codec、speaker path、目标 CPU/thermal/power 或 72 h route soak。

## Profile 与许可证隔离

正式目录是 `validation/extended.datasets.lock.json`。

| Profile | 数据源 | 用途 |
| --- | --- | --- |
| `commercial-core` | RealMAN、BUT ReverbDB、MUSAN、Mini LibriSpeech | 高频真实远场/实测房间/负例验证 |
| `commercial-plus` | core + VOiCES + AMI + ICSI | 周期性更大范围真实房间/会议压力测试 |
| `research` | plus + AISHELL-4 + 过滤后的 FSD50K + WHAM | 研究用途，不能作为商业/发货证据 |

`commercial-core` / `commercial-plus` 只能包含 `commercial-validation` 数据。CC-BY-SA、混合许可证、NonCommercial 数据不能混入 commercial gate。ACE Challenge 按 NoDerivatives 处理，只登记、不生成派生音频。

仓库只保存 catalog、attribution 和测试工具，不提交大型原始音频。

## Runner 目录

使用隔离 runner：

```text
self-hosted, linux, audio-validation
```

推荐缓存：

```text
/opt/audio-validation-extended/
  RealMAN/
  BUT_ReverbDB/
  musan/
  LibriSpeechMini/
  VOiCES/        # commercial-plus
  AMI/           # commercial-plus
  ICSI/          # commercial-plus
  AISHELL4/      # research only
  FSD50K/        # research only
  WHAM/          # research only
```

至少安装 Python 3、CMake、C compiler、Git、Git LFS、`ffmpeg`。大型数据由实验室显式 materialize，`audio-pipeline` 不在 CI 中静默下载几十/几百 GB 数据。

## 推荐 materialization

- RealMAN：优先 val/test，不要求 531 GB training 数据。
- BUT ReverbDB：RIR + room noise 足够构造实测房间测试。
- MUSAN：重点保留 noise / music。
- Mini LibriSpeech SLR31：小型 clean subset 足够作为参考语音。
- VOiCES：使用 distant 16 kHz speech / distractor。
- AMI：优先 microphone-array meeting audio。
- ICSI：meeting audio 用于 spontaneous/overlap stress。
- AISHELL-4：research 模式使用 test/eval subset。
- FSD50K：必须保留 per-clip license metadata 与 split CSV；自动扫描只接受看起来属于 CC0/CC-BY 且标签非 speech/voice 的 clip，但仍保持 research-only。
- WHAM：NonCommercial，只允许 research。

上游许可可能变化，获取/分发前仍需检查当前 upstream terms；仓库 catalog 是工程门禁，不是法律意见。

## 每文件 SHA-256 绑定

扫描实际缓存：

```bash
python3 validation/tools/prepare_extended_validation.py scan \
  --catalog validation/extended.datasets.lock.json \
  --data-root /opt/audio-validation-extended \
  --profile commercial-core \
  --limit-per-dataset 48 \
  --output /tmp/extended-source-manifest.json
```

每个被选中的真实音频文件都会独立 SHA-256。构建 corpus 前再次校验：

```bash
python3 validation/tools/prepare_extended_validation.py verify \
  --catalog validation/extended.datasets.lock.json \
  --data-root /opt/audio-validation-extended \
  --manifest /tmp/extended-source-manifest.json
```

文件缺失、内容变化、catalog 变化、usage class 漂移都会 fail-closed。

## 已实现测试方法

当前 builder 可生成：

- RealMAN 真实 far-field；
- CH0/CH1 双麦（数据存在时）；
- direct-path clean reference；
- static / moving 平衡覆盖；
- distance metadata / distance bucket（上游存在时）；
- Mini LibriSpeech + BUT measured RIR + BUT/MUSAN noise；
- measured-RIR 单麦 NS；
- measured-RIR 双麦 BF；
- MUSAN music/noise VAD/NS hard negative；
- VOiCES distant speech / distractor；
- AMI array meeting；
- ICSI spontaneous meeting；
- AISHELL-4 中文多人会议 research stress；
- FSD50K permissive non-speech hard negative；
- WHAM noise/reverb research stress。

所有生成 case 都保留实际 source manifest 的逐文件 SHA-256 provenance。

## 指标与 Gate

除 SI-SDR、ERLE、render correlation、VAD、noise attenuation 外，新增：

- peak / RMS；
- output/input RMS delta；
- clipping fraction；
- DC offset；
- VAD precision / recall / F1；
- VAD FPR / FNR；
- noise-only attenuation；
- speech-active attenuation；
- P10 SI-SDR improvement；
- P10 noise attenuation；
- 每 scenario 样本数；
- 每 scenario pass rate；
- static / moving 等维度覆盖。

核心目标是避免“总体平均不错，但 moving / 4m+ / meeting / hard-negative 已崩掉”的问题被平均值掩盖。

## Blind Holdout

Commercial Extended Real 使用仓库外 `AP_VALIDATION_HOLDOUT_KEY`，并按 scenario 分层：

```bash
python3 validation/tools/split_holdout.py \
  --corpus extended-out/corpus/corpus.json \
  --validation-output extended-out/corpus/corpus-validation.json \
  --blind-output extended-out/corpus/corpus-blind.json \
  --holdout-percent 20 \
  --stratify scenario
```

当某 stratum 至少两个 case 时，visible/blind 两侧都会保留该场景。Git 中只保存 key fingerprint，不保存 secret。

## 手动验证

**Extended Real Validation** 只接受 40 位 exact commit SHA：

```text
exact SHA
 -> runner readiness
 -> license catalog
 -> source scan/per-file SHA256
 -> manifest verify
 -> exact processor build
 -> corpus build
 -> scenario-stratified holdout
 -> visible policy
 -> blind policy
 -> SHA256SUMS/evidence artifact
```

Research profile 会显式输出 `RESEARCH_ONLY_NOT_SHIPPING_AUTHORITY`。

## 自动验证

**Extended Real Automation** 只负责调度同一份正式 workflow：

- GitHub Release `published`：自动对 exact release commit 跑 `commercial-core`；
- 每周日 03:17 UTC：对 current exact `main` 跑 `commercial-plus`；
- `research` 仍只允许人工执行。

只有 runner 与真实数据缓存准备完成后才设置：

```text
EXTENDED_REAL_ENABLED=true
```

可选：

```text
EXTENDED_REAL_DATA_ROOT=/opt/audio-validation-extended
```

未启用时，hosted automation 会立即以 `EXTENDED_REAL_REQUIRED_BUT_DISABLED` fail-visible，不会占用 self-hosted runner。这表示实验室基础设施未闭环，不是算法 FAIL。

## 建议激活顺序

1. 先 materialize commercial-core。
2. `runner_preflight.py --extended-catalog ...` 必须 READY。
3. 对 exact SHA 手动跑 core。
4. 跑 scenario-stratified blind。
5. 再 materialize VOiCES / AMI / ICSI 并跑 plus。
6. 连续人工验证稳定后再设置 `EXTENDED_REAL_ENABLED=true`。
7. research 数据始终与 commercial evidence 隔离。
8. 发货继续要求真实 DUT HIL + acoustic/thermal/power + 72 h Product Certification。
