# F05 数据准备：原件盘点、说话人曝光排除与两个 WAV 头衍生件

本目录保存这次固定来源准备的公开元数据。完整私有准备包包含衍生音频、原始盘点、脚本与失败记录；当前可移植包为 **9,784,723 B / 37 members**，SHA256 `1bf45d6ed74ec4d7572dec61bbecc093468fc0c4a8dcaddd8fac43c5ea2bbcbc`。

[机器摘要](summary.json) · [新检出的回读方法](PORTABLE_READBACK.zh-CN.md) · [实际可移植性回执](portability-receipt.json) · [整体当前进展 #968](https://github.com/jiying2007/audio-pipeline/issues/968)。下文相对文件路径和脚本命令以完整准备包为根目录；数据角色与未执行项按该次盘点的真实时点保留。后继 dEchorate 取回和新语音来源准备另有身份，不追溯改写本快照。


**已完成本轮可直接实施的来源准备；新说话人、新房间的独立双麦质量对照仍为 `NOT_RUN`。**
本次没有播放、转写、声学评分、候选执行、重采样或大语料下载。现有 intake 会解析 WAV/PCM 并核验采样和参考序列合同；这不是音质实验。

目录名称沿用任务约定的 `20261128` 标签。机器回执记录的实际执行时间为 UTC **2026-11-27**，不以目录名替代执行时间。

## 1. 实际源码与回执

元数据盘点实际绑定本地提交 `ad7075464953162f21cd95a35e640032a4ca2634`，不能改写成远端提交。
它与公开提交 `cbddb82cb849e9fa454227f1995efb07ad4a7bf5` 的 tree 均为
`49e1c72263e55c8d018d6dd6ccc21f771e2f1ca5`；独立回读验证了此映射。
随后两个 WAV 的来源准备实际在公开 `cbddb82` 的独占 detached worktree 上执行。

复用的原 `tools/codex_assets/device_capture.py` SHA256 为
`4e7948a50e94602aae446a247a49767627f2bf8a9fd289be0fa7e459a84f72bf`。
原 helper、D3 合同、119 文件输入锁和 inventory 均未修改。

| 证据 | 状态 / 身份 |
| --- | --- |
| 最终机器摘要 | `summary.json` |
| 完整盘点回执 | `result-v2/receipt.json`，SHA256 `e4fec6a6d8367162e680c78213731d0508ce7d2ad03c68de13fe3efdce098453` |
| WAV 头来源准备合同 | `wav-header-preparation-v1.json`，SHA256 `1f7b266da4de8a955a83f0b5f72fc0eed7630a6892f26a14fa95bebeab607a8a` |
| WAV 头来源准备结果 | `header-derived/receipt.json`，SHA256 `dc04d22d5fd1a8aff3b77a14536f8406224ebf589fe048c1d10630dd2459cb5d` |
| 独立字节回读 | `independent-readback.json`，`PREPARATION_READBACK_PASS_NO_ACOUSTIC_EVIDENCE` |

## 2. 已有设备录音能做什么

本次真实重算 **119/119 文件 SHA256**，共 **114,131,862 B**，全部匹配原 inventory。
原 `device_capture.intake` 对 **16 个 session** 的文件集合、WAV/CSV/session、PTS/帧计数、参考对应关系和原 70 臂登记检查通过；没有执行这 70 臂。

68 个 WAV 的声明格式均为 16 kHz / PCM16：36 个声明双通道，32 个声明单通道。
其中只有 **56 个不同的整文件 SHA256**，重复主要来自参考信号。不同文件 hash 也不能当成独立说话人、房间或录音个体数。

数字通道格式和物理标签分别记录：已知 `mic.wav` 数字通道索引 `[0,1]`、`ref_raw.wav` 索引 `[0,1]`、既有选定参考为 `ref_raw.channel0`。
16 个 session 没有提供结构化的说话人 ID、房间 ID、物理麦克风映射/坐标、采样钟身份、人工近端活动真值和人工转写；回执将这些字段保留为 null。
这是对这批 session 字段的盘点，不断言用户在其他地方没有现场信息。

所有 session 仍为 `near_activity=human-not-verified`、`acoustic_verdict=pending`。
原角色为 `development`，`training_allowed=false`、`promotion_allowed=false`。
这些限制不妨碍已有范围内的字节核验、来源准备和有明确合同的开发诊断；它们不授权将已查看录音改名为新独立 holdout。

### 两个实际发现并处理的原头问题

额外用原严格 WAV reader 检查全部 68 WAV，结果 **66 PASS、2 REJECTED**。
两份原文件 `tests/audio/100_audio_in.wav` 与 `tests/audio/100_audio_in_echo.wav` 的
`fmt.block_align=1024`；它们声明 PCM16/双通道，正确值应为 4。
两份原文件的字节身份与旧锁一致，问题来自原文件头，不是本轮损坏。

在生成衍生件之前，另行冻结了两文件来源准备合同：记录完整 chunk 清单、fmt 字段、文件/PCM hash 和精确唯一改动。
执行 **4.879 秒**，每文件保持 **4,431,872 B / 1,107,957 帧**，仅将零基偏移 **32、33** 的 little-endian block_align 字段由 1024 改为 4。
其他字节和全部 PCM 载荷逐字节不变，原 119 文件执行前后 SHA 校验均通过。

原 reader 对两份原件仍按原规则拒绝，对两份新衍生件均通过。
另一个回读脚本不调用变换脚本的解析器，重新检查了变动位置、PCM 字节、SHA、冻结先于执行和两源码 tree 的对应。

| 文件 | 新衍生 WAV SHA256 | 原 / 新完全相同的 PCM 载荷 SHA256 |
| --- | --- | --- |
| `100_audio_in.wav` | `214ce849d1f903db112494deb44370ed7479f8b33c71ae65fd1957517eab78c6` | `e545e20373596647065da84eb4f42693b1d6849168253afdfbda6a2f895694d7` |
| `100_audio_in_echo.wav` | `f9fa17c94caf94ff7cb07869ef893ccb3d4af55142c4e3051a3b57f468fbc570` | `77a1d1d9d65e04a5cfcbc64452fd78d04b4a7e359810a3c874869c2021d187db` |

衍生件只放在私有审查准备包 `header-derived/`；不覆盖原录音，不写入旧数据合同，不公开新增音频副本。
来源准备没有增加独立录音数，也没有升级数据角色。

## 3. 说话人曝光扫描与真实可取回材料

扫描冻结了本地所有可达 refs 的身份，共 **852 个 commit、4,468 个历史文本 blob**。
再加入当前留存本地元数据与有界嵌套归档，共读取 **12,638 个文本出现、316,678,298 B、5,802 种不同文本内容**。
完整文件集合、路径、Git blob / 容器 hash、SHA256、来源和重复情况保存在 `result-v2/scanned-files.json`。
文本范围为 JSON/JSONL/Markdown/TXT/CSV/YAML/Python；Git 使用每个 blob 的代表路径，不遗漏同内容的字节，但不会列出其每一历史别名。

唯一 JSON 解析失败保留在 `parse-failures.json`：历史 blob `927fc929bd0ed3765a01738fb6abe584d5e02efe`，
`validation/research/evidence/i033-36719045384/summary.json` 尾部有额外内容。
其原文本仍经过文件名 token 扫描；没有把解析失败自动当成“无曝光”。

官方 `SPEAKERS.TXT` 从已恢复原 source receipt 中核验，SHA256
`3350f093382f8baa1d589c9f5a5cee8ec3705e656f521d6eafbaa31a5fcd8f76`，列出 dev-clean 40 人。
既有两份 admission 明确覆盖以下 16 人，继续排除为已披露来源：

`84, 174, 251, 422, 652, 777, 1272, 1462, 1673, 1919, 1988, 1993, 2035, 2078, 2086, 2277`。

另 24 人在本次可见材料中没有匹配到该类命名曝光，但状态仍为 **`PENDING_EXPOSURE_PROOF_NOT_ADMITTED`**：

`2412, 2428, 2803, 2902, 3000, 3081, 3170, 3536, 3576, 3752, 3853, 5338, 5536, 5694, 5895, 6241, 6295, 6313, 6319, 6345, 7850, 7976, 8297, 8842`。

没有将“40−16”或扫描无命中写成独立性证明。文件名/计划/夹具中的身份命中都保守记录为排除线索，不因此声称真正执行过。
远端未留存 artifact、未保存评测、不可达/删除的 Git 对象、外部存储、仅间接或匿名身份不在证明范围。
JSON 的结构化 speaker 字段与文本中的标准 LibriSpeech 文件名被扫描；未尝试根据非标准数字、波形或说话声纹补推身份。

本地物料扫描共登记 **30 个归档出现**（18 个物理路径，含重复归档；14 个不同归档 SHA256）并检查嵌套成员。
松散 FLAC 为 32 个不同 hash；计入封存原件后为 **64 个不同 FLAC hash，仍只覆盖上述已披露 16 人**。
第二批八人来源确实可从已留存 `external-recovery-evidence-20261020.tar.gz` 内的 `spatial-preflight-original.zip` 取回。

本范围内没有找到完整原 `dev-clean.tar.gz`（337,926,286 B，SHA256
`76f87d090650617fca0cac8f88b9416e0ebf80350acb97b343a85fa903728ab3`），也没有找到那 24 名候选人的原 FLAC。
这属于**当前材料未物化**，不是官方语料没有权限或无法取得的结论。
既有 `train-clean-5` 的精确锁和 CC BY 4.0 声明仍在，但整个来源已登记为 research-development，旧 builder 按 seed/utterance 选择，不能为新 validation 重命名角色。

## 4. 本轮准备之后的最小工作划分

| 类别 | 下一项具体工作 | 真正缺少的输入 / 判断 |
| --- | --- | --- |
| 已有授权、现成材料可继续做 | 使用本包源清单与原 intake 做开发数据索引；后续研究引用两个新头衍生件时使用独立来源身份 | 不需要放宽原 reader；物理/人工字段继续 null |
| 全面实施授权内、需另立有限冻结合同 | 新语音 source-only 准备：明确新的 speaker 选择、所有已用 cohort 排除、旧 dev-clean/dev-clean-2/其他来源重叠核对、原完整 archive hash、选定 FLAC/解码 hash、归档/预算和未来数据角色，取得原件后只出来源回执 | 当前没有该批新 FLAC；尚未完成跨来源曝光闭包。旧 `speech_source.py` 只允许 offset 0/8，不能修改旧锁为新 cohort 开门 |
| 全面实施授权内、需另立有限冻结合同 | dEchorate 现有 12 对象 / 19,403,164 B 微集的有界取回和精确 hash 核对，再研究现有仿真与实测 IR 的偏差 | 本地/封存包未找到 SOFA/HDF5 原件；旧锁和官方地址已存在，不是待商业批准。新的坐标/时间解释与校准方法需要冻结 |
| 需要真实外部标注或采集 | 给现有 session 建立可追溯说话人/房间/物理 mic map、人工 near/转写标签；获得独立采样钟、真实方向、扬声器/机器人物理校准 | 不能由目录名、prompt 事件、相互相关峰或 WAV 通道数替代这些真值 |

dEchorate 旧微集的 11 个 wall configuration 来自**同一物理 cuboid 房间**，并已被 S003 使用；不是 11 个独立新房间。
新有限校准可以复用同一合法来源，但应从原 `Data.IR` 得到观测。
同时开展的一手来源复核指出，发布的 `EchoTimings`/`EchoAmplitudes` 来自 image-source 距离计算，坐标也有声学校准历史；不能把它们当作完全独立实测峰来验证同一公式。
新任务应明确使用哪一几何来源、坐标 convention、`Data.Delay`/sample-zero 含义与由原 IR 独立提取的观测，保留不能识别的量。

既有仿真已覆盖自由场分数延时、短回声 taps、S001 故障、S002 非线性、motion-v2 准静态像源等；本次不重开 S003 或已否决候选。
现有 `build_dechorate_artifact_exclusion_corpus.py:102–109` 的 48→16 kHz 处理是在每第三样点插值取样；
`build_extended_real_corpus.py:213–237` 的相邻 RIR 配对也没有在该处建立同房间/同声源的物理阵列对应。
因此不能仅凭这些入口存在，就宣称完成反混叠、物理双麦配对和模型独立校准。这些是后续有限方法工作，不是必须等待新硬件的事项。

## 5. 复现与保留失败

完整命令在各 receipt 的 `command` 字段及脚本中。Python 3.10+；不安装包。
盘点可重跑到新目录，**输出目录必须不存在**。扫描包含的 refs 和本地物料若变化，新扫描应另记身份，不声称逐字复现旧清单。

```sh
python3 f05_readiness.py \
  --repo /absolute/audio-pipeline \
  --revision ad7075464953162f21cd95a35e640032a4ca2634 \
  --workspace /absolute/workspace \
  --roster /absolute/recovered/source/SPEAKERS.TXT \
  --source-receipt /absolute/recovered/source/source-receipt.json \
  --output /absolute/fresh/readiness-result

python3 wav_header_prepare.py run \
  --repo /absolute/detached-cbddb82 \
  --contract wav-header-preparation-v1.json \
  --contract-sha256 1f7b266da4de8a955a83f0b5f72fc0eed7630a6892f26a14fa95bebeab607a8a \
  --output /absolute/fresh/header-derived

python3 verify_preparation.py \
  --package /absolute/f05-readiness-20261128 \
  --repo /absolute/detached-cbddb82 \
  --output /absolute/fresh/independent-readback.json
```

`attempt-1-*` 保留首次盘点脚本在两个原 WAV 严格 reader 处停止的真实失败。
`result/` 与 `attempt-2-*` 保留第一版扫描汇总的修正历史：defaultdict 在生成 40 人表时插入空 key，导致“被提及 ID”汇总过宽；16 人排除、24 人待核与逐人证据没有改变。
正式结果使用 `result-v2/`，修正后的脚本已重新实际执行。没有改写任何旧研究结果。

## 来源定位

- 原设备数据与角色：`docs/research/frontend-evolution-v1/DEVICE_CAPTURE_DATASET.zh-CN.md:3–12,20–33`；`.github/research/frontend-evolution-v1/device-capture-dataset-inventory-v1.json`；`device-capture-d3.json`。
- 原严格 intake：`tools/codex_assets/device_capture.py:84–112,145–203,220–259`。
- 两组已用 LibriSpeech：`.github/research/frontend-evolution-v1/speech-admission-v1.json`、`spatial-speech-admission-v1.json`；旧 getter 的 0/8 约束在 `speech_source.py:38–62`。
- 开发来源：`.github/research/continuous-optimization/development-data-v3/development.lock.json:5–24`；`dataset-registry.json`。
- dEchorate 原对象与角色边界：`development-v3/dechorate-source-qualification-v1.json:17–58`；`dechorate-ground-truth-diagnostic-v1.json:29–36,48–68`；`docs/program/iterations/S003-cross-source-artifact-exclusion-v1-result.json:20–30,100–113`。
- [官方 dEchorate v1 数据许可与一房多配置说明](https://zenodo.org/records/5562386)、[官方 v2 HDF5 记录](https://zenodo.org/records/6576203)、[已锁 SOFA 镜像目录](https://www.sofaconventions.org/data/database/dechorate/)。本次仅查阅网页，未下载 RIR。
- RealMAN 原 Gym source/lag 研究已完成有限诊断，见 [#723 最终记录](https://github.com/jiying2007/audio-pipeline/issues/723#issuecomment-6110786040)。旧 D0 的 metadata-only 状态不能抹去 S3R/S6 的实际来源工作；这些已披露材料仍不是独立 clock/DOA/BF 质量证据。
