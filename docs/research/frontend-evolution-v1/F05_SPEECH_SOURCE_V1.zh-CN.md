# F05：有限保留语音来源准备 V1

**本文件冻结来源准备方法；提交时仍为未执行。** [机器合同](../../../.github/research/frontend-evolution-v1/f05-speech-source-v1.json)
对应 `F05-SPEECH-SOURCE-V1`，实施基线是实际 main
`4eec2329be9f2138c7ac73e8dd59026f3dc0a3ba`。合同和实现须先经审查、公开冻结 exact commit
及合同 SHA256，随后才可取回大归档或调用真实 decoder。tiny tests 不构成真实数据准备结果。

## 目的与数据角色

F05 盘点已完成原 68 WAV、既往 LibriSpeech 曝光、归档可恢复性和未知字段登记。
本项解决“已知原完整 dev-clean 归档身份，但下一组固定来源尚未物化”的具体缺口。
主保存资产是 **32 个原 FLAC 与逐个完整无损解码的 PCM**；额外的 **8 × 4 秒** 片段仅供未来
适配器接线，不能当作充分覆盖的新验证集，更不代表新房间、真实双麦录音或普遍独立性。

全部新原件、完整 PCM、适配片段共用 `reserved-validation-visible-scope-separated` 角色，
明确 **NOT_BLIND**，`training_allowed=false`、`optimizer_selection_allowed=false`、
`promotion_allowed=false`。本合同不授权声学执行。后续算法、仿真或质量比较须另立冻结合同；
不能先看分数再选择候选、替换说话人、扩大范围或改阈值。旧数据、旧结果及旧
`speech_source.py --speaker-offset 0/8` 的入口与角色均不改变。

## 曝光依据与固定选择

盘点实际执行源码为 `ad7075464953162f21cd95a35e640032a4ca2634`；其与已公开
`cbddb82cb849e9fa454227f1995efb07ad4a7bf5` 的 tree 相同。合同绑定盘点摘要、曝光清单、
Git 扫描范围和扫描文件集合的四个 SHA256。扫描覆盖当时本地可达 852 commits、4468
历史文本 blobs，以及本地审查元数据和嵌套归档；不是所有远端分支、被删 Git 对象或外部存储。
一份历史 JSON 解析失败已保留，并作文件名文本扫描；不能把解析失败当作无曝光。

排除集按先前文件名或声明中的保守命中冻结，命中不等于证实已实际运行。
`SPEAKERS.TXT` 中全局名册的成员关系本身不计曝光。

| 项目 | 固定值 |
|---|---|
| 排除的 16 人 | 84, 174, 251, 422, 652, 777, 1272, 1462, 1673, 1919, 1988, 1993, 2035, 2078, 2086, 2277 |
| 排除后按数值 ID 取最前 8 人 | 2412, 2428, 2803, 2902, 3000, 3081, 3170, 3536 |
| 每人的原件 | 按数值 chapter、utterance 排序最前 4 条，固定共 32 个 FLAC |
| 原生格式 | 16000 Hz、单声道、16-bit；不重采样、不归一化、不补零 |
| 适配片段 | 将该人的 4 条完整 PCM 按固定顺序连接，取前 64000 samples |
| 不足 4 条、格式不符或不足 64000 samples | 失败；不重新选择，不以能量、听感或分数替换 |

无命中仅支持**本次可见扫描范围的分离**。间接 ID、未保存评估、未收集清单、未知远端或私人使用
仍可能造成既往曝光；因此不能把“40 − 16”直接写成 24 个已经独立确认的说话人。
本项选 8 人后也不把其余 16 人自动登记为未曝光或可用 holdout。

适配片段如跨 utterance 边界，回执逐段记录原 archive member、源采样范围和连接后的窗口偏移，
全部为零基、半开区间。`crosses_original_utterances=true` 表示人工串接，**不是一段连续实录**。
32 个原 FLAC 与完整 PCM 始终保留，不能只保存这 32 秒片段后丢弃主来源。

## 原件与五类权利

唯一输入是 [OpenSLR 官方 dev-clean 归档](https://www.openslr.org/resources/12/dev-clean.tar.gz)：

```text
bytes   337926286
SHA256  76f87d090650617fca0cac8f88b9416e0ebf80350acb97b343a85fa903728ab3
MD5     42e2234ba48799c1f50f24a7926300a1
```

先核以上三项，再读取归档成员或启动 decoder。官方 MD5 保留为来源校验信息；完整 SHA256 与
字节数同时强制。不下载镜像、不跟随重定向、不增加自动重试，不以另一个版本替代固定原档。

| 权利类别 | 本次审阅与执行边界 |
|---|---|
| 代码 | 本仓库第一方准备代码 Apache-2.0；复用原 `speech_source.flac_info`，不修改旧 reader |
| 依赖 | Python 标准库及已安装 FFmpeg；记录真实 binary SHA256、`-version` 与 `-L` 输出；不安装或再分发该 executable |
| 权重 | 无模型、无下载权重、无训练 |
| 数据 | 精确 LibriSpeech 原档的 `LICENSE.TXT` 明示 CC BY 4.0；不推导其他 corpus、测试集或模型的权限 |
| 再分发 | 保留原 LICENSE/README/SPEAKERS、作者、来源及 CC BY 4.0 链接，披露解码/裁片/串接变换，不暗示背书；本工具不自动公开音频 |

原三个 notice 的精确 SHA256 已写入合同。来源可在
[OpenSLR 12](https://www.openslr.org/12/) 核对；许可证是
[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/)。代码许可不替代数据或依赖许可。

## 执行与失败边界

| 阶段 | 上界与接受规则 |
|---|---|
| 取回 | 1 次固定 URL；600 秒 wall；精确 337926286 bytes；失败 prefix 留存 |
| 源准备 | 300 秒 wall；原件及 Git controls 前后复验；selection.json 必须在首个 decoder 调用前落盘 |
| 无损解码 | 累计 ≤180 秒 wall；每文件 ≤20 秒；单线程；最多 32 个、每个原生 ≤60 秒 |
| 归档 | ≤10000 members、展开内容总量 ≤1 GiB、单 member ≤5 MB、notice ≤2 MB；拒绝 link、special、重复身份和不安全路径 |
| 输出 | ≤100 个文件、总字节 ≤256 MiB，不包括单独保留的原始 tar；拒绝 symlink 和额外文件 |
| 独立回读 | 300 秒 wall；不调用 codec；从原档、完整 PCM、原生 FLAC MD5 及源跨度逐字复核 |
| 声学/听评/参数搜索 | 全部 0 次 |

解码只指定原生 `pcm_s16le`，不传 `-ar`、`-ac`、filter 或 gain。逐条核对完整样本数及
STREAMINFO 中非零的原 PCM MD5；原 FLAC、完整 PCM、适配片段另存 SHA256。
MD5 的样本序列按 [RFC 9639 的 STREAMINFO 定义](https://www.rfc-editor.org/rfc/rfc9639.html#section-8.2)
采用有符号、小端、按样本交织字节；本合同单声道 PCM16 与此直接对应。
若原 FLAC 未提供可校验的 MD5，直接失败，不改用宽松规则。最多 1920 秒完整原生音频的
容许容量是输入上界，不代表将其全长计入适配窗覆盖或进行任何声学处理。

源码回执绑定 exact commit、tree 和实际导入的第一方控制文件字节；包括旧 reader 经由
`libfvad_reference` 导入的 validation 定义。该导入不会调用 VAD、评价器或 DSP。
输出必须位于 checkout 外的新目录；原档单独保存。失败移除成功回执并留下
`source-failure.json` 与已有 prefix，不覆盖旧目录、不补造 PASS。

## 可复现命令

先在审查后的公开提交上取得 exact commit 和合同 SHA256，替换下列占位值。
`acquire` 只有在这一冻结已被确认后才能执行；以下是操作说明，**本提交没有运行它**。
归档父目录须已存在，`prepared` 目录须尚不存在。

```sh
python3 -B tests/validation/frontend_evolution/f05_speech_source.py acquire \
  --archive /absolute/f05-source/dev-clean.tar.gz \
  --output /absolute/f05-source/prepared \
  --code-revision PUBLIC_FROZEN_40_HEX_COMMIT \
  --plan-sha256 PUBLIC_FROZEN_64_HEX_SHA256
```

若已有完全匹配的原 tar，使用同样参数的 `prepare`，不再下载。
准备成功状态只能是 `SOURCE_PREPARED_RESERVED_VALIDATION_NOT_BLIND`，不是声学或独立性 PASS。
只读核验可在相同源码文件仍可复原的 checkout 上执行，允许 HEAD 后续移动，但必须能读取
指定 Git 对象，且当前工具与已记录控制文件字节相同：

```sh
python3 -B tests/validation/frontend_evolution/f05_speech_source.py verify \
  --archive /absolute/f05-source/dev-clean.tar.gz \
  --output /absolute/f05-source/prepared \
  --code-revision PUBLIC_FROZEN_40_HEX_COMMIT \
  --plan-sha256 PUBLIC_FROZEN_64_HEX_SHA256

timeout 60s python3 -B tests/validation/frontend_evolution/test_f05_speech_source.py
```

tiny 测试使用显式假 STREAMINFO、合成 byte payload、mock transport；不调用真实网络或 decoder。
它覆盖错 archive、路径/链接、固定选择、native 格式、全 PCM/窗口/跨度篡改、角色/预算改变、
单次 transport、失败 prefix 和 hard wall timer。CI 只把该命令接到已有 Verify fast-code；
不增新 workflow，不触发 D1–D8，不执行本次大下载，也不自动运行后续候选。

成功后的原 tar、主资产和完整回执应另行保留，结果登记须记录实际执行时长、源码身份、
归档与文件哈希及所有失败。提交本合同和通过 tiny tests 均不能替代这份实际结果。
