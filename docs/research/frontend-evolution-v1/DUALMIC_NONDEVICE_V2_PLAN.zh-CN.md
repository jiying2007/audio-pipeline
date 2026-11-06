# 双麦非真机闭环 V2：实施前合同

日期：2026-11-06（Asia/Shanghai）。状态：本轮实施与新测量之前冻结。

用户新增授权：`按建议全部推进，除真机外，继续迭代闭环落地完成`。
本轮承接已完成的双麦 2.3.63，不重新批准旧的失败算法或商业发布。
精确基线 `2d93c9ddf74355c7e5ac0bc18c9a6fe3ae53cbd3`，tree
`745f27fa08dac7a3b64eda676413cceea804bcb4`；fresh GitHub main 与本地一致，
Verify `42207897152/attempt2` 成功，required summary `127891735614`。
原 attempt1 失败和既有研究负结果全部保留。

## 共同边界与预算

三个工作包是已确认缺口的测量/集成，不修改 DSP、公开 API、Runtime 行为、默认
CALL/ASSISTANT tuning、既有声学阈值或物理资源上限。没有参数搜索、训练、效果晋升、
新 release/tag 或新硬件执行。复用 canonical acoustic evaluator；新下游文本/事件
指标只有一份权威实现，与模型执行适配器分离。

各工作包先提交更具体的输入/配置/判据合同，再执行正式测量；不得根据结果改判据。
每项本地构建、单次测试/正式矩阵、独立回读预算各 300 秒；来源取得每个固定资产
300 秒，来源检查不执行模型或挑选片段。依赖安装每套 300 秒，完整 CI 使用原门禁
与原超时。计时从实际阶段开始，不因下载/本地文件已存在而偷换口径；失败独立记录。
大音频、模型、压缩包保存在工作目录/Actions 产物，Git 保存来源锁、代码和小型结果。
host 时间与逻辑音频时间分列；不能外推 SSC305 帧 p99、CPU、功耗或真机端到端时延。

## A：FE-C2-RECORDED-SPEECH-DUAL-USE-V1

缺口：42 例旧 profile 回放使用 speech_like；现有真实 LibriSpeech 空间诊断不经过
当前完整 C2 CALL/ASSISTANT 链。复用已准入的原始八说话人源及 source_check，
原 source receipt 不改，新实验统一 effective_role=regression（曾曝光，不是盲测）。

固定四对 near/far、七场景、两 profile，共 56 例；沿用工程回放场景含义，但为
4 秒真实片段明确固定放置/补零方式和各成分时标。生成/执行前冻结具体矩阵。
同场景两 profile 使用逐字节相同的输入，不做 tuning override。报告完整 PCM/JSONL、
逐例 canonical 近端/回声/失真指标及坏结果。真实录音没有逐帧活动标注，不把
放置窗口当真人 VAD 真值。完成判据是源、样本、帧、配置、指标和输出的完整正确性；
声学判断保持 DESCRIPTIVE_ONLY，不宣称任何 profile 胜出。

允许生成有准确署名、固定播放电平和匿名选项的 WAV 听评材料；未收到真人评分时
human_listening=NOT_RUN，不生成 MOS 或自动听感结论。

## B：FE-C2-INTERCOM-TRANSPORT-V1

缺口：现有 PCM/ALSA 示例没有语音 codec、分包、jitter queue、PLC 与实际播放参考
串接。使用真实 host libopus（记录版本和加载实体 hash）及现有原生 Runtime 薄适配，
建立双向离线对讲链：远端编码→固定网络日程→有界播放队列→解码/PLC→音量→
实际播放与同字节 Render；合成双麦回声驱动捕获→原 CALL worker→上行编码/解码。

固定 16 kHz、双麦、CALL 默认；Opus VOIP/mono/20 ms/24 kbit/s/CBR/complexity5，
DTX 与 FEC 关闭；60 ms 目标播放缓冲，容量和时标在子合同固定。查询真实
OPUS_GET_LOOKAHEAD。八类工程场景：正常、乱序、重复、单包丢失、两包连续丢失、
超过 deadline 的迟到、音量/mute、明确播放重开。无界队列、隐式尾部丢弃和 VAD
截断都不允许。网络 PLC 保持 PRESENT Render，不冒充 XRUN；真实重开单独通知。

验收：实际 codec 调用；预期计数/有界队列/有序且仅一次解码；完整 capture/output；
Render 与实际播放逐字节相同；Runtime 没有输入满、处理失败或输出发布丢失；错误
前音量/前 PLC 参考必须被独立负例拒绝；同输入重复和有界未来前缀检查。网络时序
明确为模拟，不能称为 WAN、SIP/ICE、拥塞控制或真实口到耳验收。

## C：FE-C2-MANDARIN-DOWNSTREAM-V1

缺口：没有固定中文模型执行器及 CER/WER、KWS 事件评分合同。先独立完成评分
实现/负例，再固定来源及运行配置后执行实际模型；不能用模型输出自造参考文本。

拟采用一个固定中文 KWS 参考（sherpa-onnx zh-en 3M 2025-12-20，chunk8）和一个
固定 ASR 参考（vosk-model-small-cn-0.22）。这只是 host reference，不是 A32 后端。
模型、运行时、词表、阈值、归一化、音频和外部转写必须在执行前按实际字节冻结。
包内测试音频不因模型许可自动获准；首个明确可用的真实中文输入是固定 WeNet
commit 的 AISHELL 测试 WAV及官方转写，适用原 AISHELL-1/WeNet 来源条款。

固定 raw、CALL、ASSISTANT 视图；双麦由已说明的派生方式构造，不是实际阵列录音。
中文 CER 以固定规范字符微平均；WER 必须说明分词；保留 S/D/I、零分母 null。
KWS 保留实际流式触发消耗音频时间；token 时间不当实际触发延迟。每次事件只能
匹配一个标注，缺失/重复/错误词/超窗/非有限数/错误 hash/预测缺例均不可吞掉。
没有真实负样本时长或时间标注则 FAR/延迟为 null，绝不以短 smoke 推广统计性能。
模型失败与空识别结果分开保存；未运行不是通过。

## 软件收口

各包具体合同、源码、来源锁、实际命令/时间/退出码、逐例结果、失败与能力边界
形成可回读记录；合并前独立审查准确 PR head/base、全部适用检查和 required summary，
受保护 squash 后核验新 main 的完整门禁与本轮实际产物。中文使用入口同步更新。
真人听评、真实房间/未获得的独立语料、真实互联网和真机仍按实际状态记录，不能
因为用户排除真机就把其余外部事实凭空补成 PASS。
