# 固定中文 ASR/KWS 下游 V1：测量与运行合同

日期：2026-11-06（Asia/Shanghai）。实施前冻结；没有候选效果或运行结果。
父合同：`DUALMIC_NONDEVICE_V2_PLAN.zh-CN.md`，本地提交
`494ae5ebb9c5cba4a8c3d0739430259a3649513f`；DSP 基线
`2d93c9ddf74355c7e5ac0bc18c9a6fe3ae53cbd3` / 2.3.63。

## 单一目的与完成判据

实现缺失的下游文本/事件测量，并通过一条来源明确的真人中文录音完成实际模型
接线。没有 DSP、API、tuning、模型训练、阈值搜索或样本选择。权威文本/事件指标
仅在 `validation/tools/downstream_metrics.py`；不复制 canonical acoustic evaluator。
完成要求正确身份、真实执行、完整结果、负例和独立回读；小样本结果保持
`MANDARIN_MODEL_INTEGRATION_SMOKE_ONLY`，`promotion_allowed=false`。

## 固定来源及执行前两阶段

1. 第一阶段只取得/检查许可、模型、运行时和音频，写实际字节 hash，不运行模型。
   选定资源不得按后续分数替换。来源锁提交后才进入推理。每个固定资产取得预算
   300 秒，每套依赖安装 300 秒；保存实际开始、结束、退出码与失败。
2. 固定 source lock 和代码提交后，分别构建 2.3.63 processor 并运行一次矩阵，
   各 300 秒。错误结果先落盘，不靠重复执行选择结果；独立回读单独 300 秒。

固定资源：

- `wenet-e2e/wenet@be6ad97fdb512589df113042f7ff3a29d392fb38` 的
  `test/resources/aishell-BAC009S0724W0121.wav`，Git blob
  `0f1d46b3ed59c86f6a77dbeaecbb4c8ffa147b83`，137036 B；转写来自同提交的
  `test/resources/dataset/text`：`广州市房地产中介协会分析`。保留 WeNet LICENSE
  与原 AISHELL-1 OpenSLR33 的 Apache-2.0 来源说明。不是自行听写或模型自标注。
- `vosk-model-small-cn-0.22.zip`，官方 Alpha Cephei 模型页明确 Apache-2.0。
  下载后固定全部实际模型成员；Vosk 运行时固定 `vosk==0.3.45` 的 Linux x86_64
  wheel，通过其真实 `libvosk.so` C API 运行，不引入 Python 包的非必需网络依赖。
- `sherpa-onnx-kws-zipformer-zh-en-3M-2025-12-20.tar.bz2`，GitHub asset
  331699066，32885699 B，SHA256
  `68447f4fbc67e70eee3a93961f36e81e98f47aef73ce7e7ca00885c6cd3616a6`。
  使用 chunk8、int8 encoder/joiner 和 fp32 decoder；完整成员名称/hash 在来源
  预检后提交。sherpa-onnx 运行时固定 `1.13.4`，NumPy 固定 `2.3.3`。
  只读检查依赖/wheel，所有安装/加载的 native 文件必须记 hash。
  模型许可依据作者/维护者在官方 #3802 的 Apache-2.0 明确答复，保存准确评论；
  包内测试 WAV 不属于本次数据准入，不被执行或当作同许可音频。

此资源集合为 host reference；不声称 A32 可部署。第三方模型、音频和 wheel 不入 Git。

## 固定音频、前端与流式处理

- 输入原样读取完整 mono S16LE/16000 Hz WAV，不做幅度归一化、重采样或裁剪。
  先插入 500 ms 零 preroll，再放原录音，最后 500 ms 零 postroll；不足 10 ms 的
  最后块仅显式补零至下一完整 160 样点。原帧数、全部补零长度写入报告。
- 三个固定视图：raw 为上述 mono；CALL 与 ASSISTANT 使用每样点完全相同的双路
  复制 capture，经当前 `ap_process_pcm --capture-only --strict-capture-frames
  --sample-rate 16000 --mic-channels 2 --profile call|assistant`。不传 tuning
  override；两份 capture 输入逐字节相同。这是共线同源的合成双麦接线，不能称为
  实际阵列、混响、噪声或真实声学收益。每个视图的 PCM 长度完全一致。
- Vosk 每次供给 160 样点，记录每次 `AcceptWaveform` 的完整 result（若完成）、
  最终 `FinalResult`；句子按消费顺序拼接，不丢掉中间完成的语句，不设 grammar。
  独立模型实例、单次固定解码；空转写是实际输出，不等同于模型失败。
- KWS 独立 stream，每次供给 160 样点；采样率16000、feature_dim80、CPU、
  num_threads1、max_active_paths4、num_trailing_blanks1、keywords_score1.0、
  keywords_threshold0.25。唯一预定关键词 `广州市`，发音 token 为
  `g uǎng zh ōu sh ì @广州市`，不做结果驱动调整。执行前检查所有 token 在固定
  词表中，若缺失则失败而非换词。每个触发即记录其完整原始结果与实际已消费样点，
  然后依官方 API reset_stream。结束后明确追加 320 ms 零音频 flush，仅供模型
  完成既有状态；其样点单独计数，不计入真人负样本暴露。记录真实调用时长与音频
  时间，token 时间不是实际触发时间。没有词级人工时间真值，不能报告触发延迟。

## 文本和事件评分定义

- 文本归一化 `NFC-strip-whitespace-v1`：Unicode NFC 后仅移除 whitespace；保留
  标点、大小写、数字和全部其他字符。不自动简繁转换、分词或按输出修正文稿。
- CER 为字符 Levenshtein `(S+D+I)/N`，保留四个计数；相同最短路径按
  substitute、delete、insert 顺序确定。汇总为计数之和除以参考字符数之和。
- WER 只有预先提供 `reference_words` 才适用；假设按 NFC 后 whitespace 分词。
  本条原中文转写无外部词边界，WER=`null`。空参考的插入计数有定义，比例无定义。
- 评分器使用 canonical manifest digest、固定 models/settings digest、逐例 PCM
  hash 和样点数绑定预测；精确 case 集合、唯一 case/event id、整数时刻、有限数
  必须验证。失败/未运行的模型、丢例或错误身份拒绝，不能隐式补为空结果。
- 一般 KWS 评价只接受明确标注：每个目标具有 keyword、start/end、固定最大容许
  迟延；同一实例时间窗不得歧义重叠。按时序匹配最早且未匹配的同词目标，一个
  触发只对应一个目标。第二次触发、错词和超窗事件均保留为 unmatched。
- FAR/h 只统计落在明确 negative intervals 的 unmatched 事件，分母仅为这些
  不与目标窗重叠区间的总小时；零暴露/未提供暴露为 `null`。正例区域多触发另报，
  不偷并入负时长。FRR 为 missed/positive count，零正例/未标注为 `null`。
- 本条中文输入仅有外部句子转写，没有 KWS 事件时间、真实负样本暴露或词末真值；
  正例计数、FRR、FAR/h、触发延迟全部为 `null`。原始流式触发照实报告，包括零触发。
  人工语义提示“转写含广州市”不能代替事件时间标注或统计样本。

## 独立校验与负例

文本 edit counts 以小型独立全矩阵距离 oracle、已知 S/D/I、空串、Unicode/whitespace
和 WER 不适用/适用覆盖。事件覆盖漏检、重复、错词、边界、非法重叠、无暴露、
跨例/跨模型 hash 错误、缺例/重复例、NaN/非整数/越界时刻、模型失败与空输出区分。
预测及结果完整保存；评分结果从固化 manifest/predictions 重算。三视图是同一原始
录音的处理臂，不当成三个独立说话人或独立验证集。
