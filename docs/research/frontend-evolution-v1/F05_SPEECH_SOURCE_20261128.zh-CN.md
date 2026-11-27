# F05 固定保留语音来源：实际准备与独立回读

**固定 8 位说话人的 32 个原 FLAC 与完整无损 PCM 已实际准备完成，共 327.605 秒；
独立回读通过，没有运行新双麦整链或任何声学比较。** 全部材料保持保留验证角色、NOT_BLIND，
不能把这项来源准备写成 F05 新双麦质量目标已经完成。

本次严格执行[来源准备合同](F05_SPEECH_SOURCE_V1.zh-CN.md)，唯一实际执行源码为
[`a058b02582962875ac10e6bb42b928c46c405213`](https://github.com/jiying2007/audio-pipeline/tree/a058b02582962875ac10e6bb42b928c46c405213)，
tree 为 `e2b41d4a7f3678efa065dfabc09ea29ebc2c2071`，合同 SHA256 为
`cde46538288219a077927eada139fea62c2bc156fa9bd478626aae139e0db4d3`。
当前文档提交是结果登记，不能替代或改写实际执行身份。

## 实际执行与预算

唯一 acquire 于 **2026-11-27 18:59:51.243574 UTC** 开始，
**19:06:48.179684 UTC** 完成，退出码 0，stderr 为空。工作包标签 `20261128` 不是实际 UTC 日期。
原命令、时序和退出状态见[执行起点](evidence/f05-speech-source-20261128/execution-start.json)及
[执行回执](evidence/f05-speech-source-20261128/execution-receipt.json)。

| 阶段 | 实际 wall 秒 | 冻结上限秒 | 结果 |
|---|---:|---:|---|
| 原官方 tar 取回 | 401.768588 | 600 | 一次固定 URL 请求；无重试、镜像或来源替换 |
| 源准备及前后复验 | 14.918693 | 300 | 全部原件、解码与回执完整 |
| 32 文件解码累计 | 2.117771 | 180 | 原生无损解码；不重采样、不归一化 |
| 最慢单文件解码 | 0.140399 | 20 | 所有文件均在界内 |
| 整个 acquire 命令 | 416.936118 | 分阶段执行上述限制 | 正常退出；未发生外层超时 |
| 独立无 codec 回读 | 6.440306 | 300 | 0 decoder、0 acoustic；通过 |

已安装 FFmpeg 身份为 `7.1.5-0+deb13u1`，实际 executable SHA256 为
`e8a8d46f5225f3062cec7c07fb145d58ae73c603cb740dcd5bad34bfb54e455a`。
没有安装新依赖、训练、听评、候选评分、参数搜索或后继声学调用。

## 新来源实际覆盖

排除已冻结的 16 个既往可见说话人后，按数值 ID 选取最前 8 人；每人取数值 chapter/utterance
最前 4 条原文件。选择在解码前落盘，没有按能量、听感、音质或算法结果替换任何条目。

| 说话人 ID | 原 FLAC / 完整 PCM 对数 | 完整原生秒数 | 适配片段秒数 |
|---|---:|---:|---:|
| 2412 | 4 | 21.885 | 4 |
| 2428 | 4 | 25.900 | 4 |
| 2803 | 4 | 37.045 | 4 |
| 2902 | 4 | 54.545 | 4 |
| 3000 | 4 | 35.830 | 4 |
| 3081 | 4 | 27.075 | 4 |
| 3170 | 4 | 88.265 | 4 |
| 3536 | 4 | 37.060 | 4 |
| **合计** | **32** | **327.605** | **32** |

32 个 FLAC 和 32 个完整 PCM 分别都有 32 个不同 SHA256；完整 PCM 共 **5,241,680 samples**，
格式统一为 16 kHz、单声道、PCM16。每个原件的 SHA256、PCM SHA256、原生 PCM MD5、样本数
和时长均列于[32 文件与来源范围摘要](evidence/f05-speech-source-20261128/source-summary.json)。

8 个 4 秒窗口只是预定义适配材料，不能替代主资产。其中 **2 个窗口跨原 utterance 边界**；
每段原路径、源采样区间与连接后的偏移均为零基半开区间并完整保留。串接窗不代表一段连续实录，
也不是新房间、真实双麦录音或充分的统计覆盖。不能把 128 个可能的后继 profile/scene 输出
当成 128 个独立语音样本；本项没有执行这些后继输出。

## 原字节、独立回读和完整交付

来源准备原回执按原字节公开保留：
[source-receipt.json](evidence/f05-speech-source-20261128/source-receipt.json)，SHA256：

```text
35fb4797cf67d004ae1646d61b7905a85bf376f7abbd031d4b3d58531ca57e5c
```

独立核验于 **19:07:15.791653–19:07:22.231939 UTC** 使用同一公开冻结工具的 `verify` 入口，
重新检查原 tar、Git 控制文件、固定 metadata 选择、原 FLAC、完整 PCM、窗口跨度和角色闭包，
不调用 codec 或 DSP。原始[独立回执](evidence/f05-speech-source-20261128/independent-readback-receipt.json)
及 [stdout](evidence/f05-speech-source-20261128/independent-readback-stdout.log) 已保留；回执 SHA256 为：

```text
00496dc864275cc2da3671ff2a13980e1477b1797ee9f384116f62510001e493
```

完整音频证据包另行保留，公开 Git 只登记方法、原始回执、时长和哈希，不放置新增音频或完整 tar。
该包包含完整原 dev-clean.tar.gz、所有 prepared 材料、原执行日志、独立回执，以及公开执行源码的
10 文件控制闭包、原代码许可与方法说明；外层 README 面向复核读者。

| 对象 | 精确字节数 | SHA256 |
|---|---:|---|
| 原 `dev-clean.tar.gz` | 337,926,286 | `76f87d090650617fca0cac8f88b9416e0ebf80350acb97b343a85fa903728ab3` |
| 完整 `f05-source-final-20261128.tar.gz` | 352,999,000 | `268df36ff7335d87eb9472531245b15f7f751835d70a635c8fa25ac5e8560bdc` |

完整包逐 member 读回通过：134 个 tar members，其中 114 个 regular files，0 symlink；
outer manifest SHA256 为 `de809254b43fad954c4b9b3a4092c66331dd1e81bc624b5a7d81939bd96c9ddb`。
详见[封包字节核验回执](evidence/f05-speech-source-20261128/package-receipt.json)。封包没有再次解码音频。

## 权利、可见范围和未完成项

原 LibriSpeech LICENSE 明示 CC BY 4.0；原 LICENSE、README、SPEAKERS、作者、来源、许可证
链接及派生变化说明完整保留。第一方代码为 Apache-2.0；实际 FFmpeg 的版本和许可证输出已留存，
其 executable 没有再分发；没有模型或权重。代码许可没有被用来代替数据或依赖许可。

数据身份仍为 `reserved-validation-visible-scope-separated`、**NOT_BLIND**。
`training_allowed`、`optimizer_selection_allowed`、`promotion_allowed` 以及
`acoustic_execution_allowed_by_this_contract` 全为 false。
曝光扫描只覆盖冻结时可见的本地 Git 与材料；未知远端、间接 ID、未保存评估、遗漏清单等边界不变。
没有把“未查到命中”升级为普遍独立性，也没有把旧 development 录音改名成为 holdout。

本项完成的是**新的固定来源取得和无损物化**。新说话人的完整 CALL/ASSISTANT 双麦整链对照仍须
使用另立的测量合同和实际封存二进制；真实双麦、新房间、ASR/KWS、真人听评及 SSC305 物理结果
仍未由本项提供。这些缺口分别登记，不能用来源准备成功或新合同本身作结果结案。
