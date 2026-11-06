# 固定中文 ASR/KWS 与双麦前端：首次真实模型结果

日期：2026-11-06（Asia/Shanghai）。实验 `FE-C2-MANDARIN-DOWNSTREAM-V1`。

**真实 ASR/KWS 已完成六个固定视图的 host 集成；双工视图留下明显负结果。**
捕获单路原始、CALL 和 ASSISTANT 的字符错误数都是 `0/12`，且各观察到一次
“广州市”触发；同一段中文叠加冻结工程回声后，原始视图为 `1/12`，CALL 与
ASSISTANT 都是 `3/12`，三个双工视图均未触发该关键词。不能把软件链执行成功
写成识别质量通过，也不能依据这个单句决定默认参数或 profile 优劣。

完整状态为 `MANDARIN_MODEL_INTEGRATION_SMOKE_ONLY`、
`quality_decision=DESCRIPTIVE_ONLY`、`promotion_allowed=false`。
这是 **1 条真实中文原始话语的 6 个相关视图**，不是六个独立说话人/样本。
真人关键词时标、独立负样本曝光、真人听评和真机均未取得；相关统计保持 `null`
或 `NOT_RUN`。[实际 scores](evidence/mandarin-downstream-v1/result/scores.json)、
[运行 report](evidence/mandarin-downstream-v1/result/report.json) 与
[证据索引](evidence/mandarin-downstream-v1/index.json) 保留全部观察。

## 先冻结再执行

| 项目 | 精确身份 |
| --- | --- |
| 原有双麦 DSP 基线 | `2d93c9ddf74355c7e5ac0bc18c9a6fe3ae53cbd3`，source 2.3.63 |
| 原始文本/事件合同 | `0751fbedee481738bb6deff903c76c2301125934` |
| 双工覆盖补充合同 | `532c9e80c07530f8be39cfc079e93e6784ae4ab0` |
| 实际来源准入与唯一 scorer | `2c07fe71ed1717768ba74b2e2e8838d0de1f3ff7` |
| 首次正式执行代码 | `fea7e0735ce2e1d6fb45e1f02e0489dea6d7e920` |
| source lock SHA-256 | `306e4a6f4f83e7e577e17037103985804d353f67d0e1d5dc3c3027f320ba64dd` |
| 实际 processor SHA-256 | `06807f512d9afa7aed9fcc19d637a51fdd8464ada6f402b15e7ab3f035622e5e` |

`856c22a` 初版执行器随后经 `ad9f485` 与 `fea7e073` 修正证据重建、超时封存、
凭据隔离及计数汇总；这些修改全部在任何实际模型执行之前完成。首次正式矩阵
只执行一次，无关键词/阈值/模型搜索、无结果选择、无 DSP/API/default 改动。
具体输入约束见[原合同](MANDARIN_DOWNSTREAM_V1_CONTRACT.zh-CN.md)和
[双工补充合同](MANDARIN_DOWNSTREAM_V1_DUPLEX_ADDENDUM.zh-CN.md)。

新鲜构建读取真实工作树 SHA，GNU 14.2.0、Release、x86_64-linux-gnu、SCALAR、
MDF、EMA、BANDLIMITED、fast-math=0；真实 build-info 仍是 source 2.3.63。
默认 CALL 的 `aec_mu/ns_floor/agc_target_dbfs` 为约 `0.22/0.12/-20`，
ASSISTANT 为约 `0.18/0.18/-18`，limiter 均为 `-2 dBFS`；没有 override。
[准备元数据](evidence/mandarin-downstream-v1/prepared-metadata/preparation.json)
保留构建哈希、实际默认值、每个 PCM、指标及命令的完整哈希。

## 输入、真值与双工覆盖

唯一真人语音来自官方 WeNet 固定 tree
`be6ad97fdb512589df113042f7ff3a29d392fb38` 的
`test/resources/aishell-BAC009S0724W0121.wav`：16 kHz、单通道、S16，
68,496 样点（4.281 秒）。外部转写来自同一 tree 的 `test/resources/dataset/text`，
在模型执行前锁定为 **“广州市房地产中介协会分析”**，共 12 字。没有用模型输出
生成或修订参考文本。WAV SHA-256 为
`2f9fc9c912bb71c85fb286cb88b599c81efb8f727c727a5ea8f6d1c89c55ac13`。

捕获视图前后各加 8,000 零样点，再明确补 144 样点对齐 10 ms 帧，总计
84,640 样点（5.29 秒）。CALL/ASSISTANT 向真实 `ap_process_pcm` 送入两份相同
麦克风通道，保留 529 帧连续输出，没有 VAD 截断。重复通道是接口集成构造，
不是真实阵列录音或空间增益测量。

双工视图将同一原始中文乘 0.5，前后各加 16,000 零样点，再补 144 样点，共
100,640 样点（6.29 秒）。远端/Render 为既有第一方 canonical generator 的
固定 seed `20261106`、64,000 样点工程信号，其后补零；不是真人远端、TTS 或
真实房间。两个通道分别用冻结 taps `[(800,0.25),(1280,0.10)]` 和
`[(801,0.25),(1281,0.10)]` 加入回声；不自动缩放、裁剪或选取更好片段。

实际 full-duplex CALL 与 ASSISTANT 都处理完整 629 帧，Render 输入有 63,998
个非零样点，真实 trace 的 `far_end_active` 各为 551 帧。这证明下游模型连接到
当前带 Render 的前端路径；它不证明真实扬声器打断、自播放误唤醒或房间泛化。
该 trace 是算法输出，不是真人活动标注。

## 实际 ASR 与 KWS 观察

ASR 使用固定 `vosk-model-small-cn-0.22`，通过哈希锁定的 Vosk 0.3.45
`libvosk.so` C API 执行，160 样点/10 ms 一次。保留所有 endpoint 与最终
`FinalResult`，按顺序连接，空识别与执行失败分开。字符规范为 NFC 后移除空白，
不改标点、大小写、繁简或数字。

| 视图 | 规范化实际文本 | S | D | I | N | CER | 实际 KWS 事件数 |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| raw | 广州市房地产中介协会分析 | 0 | 0 | 0 | 12 | 0% | 1 |
| CALL | 广州市房地产中介协会分析 | 0 | 0 | 0 | 12 | 0% | 1 |
| ASSISTANT | 广州市房地产中介协会分析 | 0 | 0 | 0 | 12 | 0% | 1 |
| raw duplex | 广州市房地产中介机会分析 | 1 | 0 | 0 | 12 | 8.3333% | 0 |
| CALL duplex | 中是房地产中介协会分析 | 2 | 1 | 0 | 12 | 25% | 0 |
| ASSISTANT duplex | 我中是房地产中介协会分析 | 3 | 0 | 0 | 12 | 25% | 0 |

`S/D/I` 按唯一 canonical scorer 的固定 S→D→I 平手规则。六视图计数记账为
`ΣS=6, ΣD=1, ΣI=0, ΣN=72`，因此 pooled-view CER 为 `7/72=9.7222%`。
这是相关视图的微平均记账，不是人口总体 CER 或六个独立样本的估计；本轮没有
词边界真值，WER 保持 `null`。

KWS 使用固定 zh-en 3M 2025-12-20、chunk8 encoder、sherpa-onnx 1.13.4，
CPU 单线程、max-active-paths=4、trailing-blanks=1、score=1.0、threshold=0.25。
唯一关键词内容是 `g uǎng zh ōu sh ì @广州市`。以 160 样点喂入，结尾明确加
5,120 样点（320 ms）零 flush 后 `input_finished`；flush 不算负样本曝光。

三个捕获视图都在已消费 33,120 样点（2.07 秒，包含前导静音）时产生一次
“广州市”事件；每个事件的原始 tokens、token timestamps 与 consumed samples
保留在[实际 predictions](evidence/mandarin-downstream-v1/result/predictions.json)。
2.07 秒是流式消费位置，不是相对关键词终点的触发延迟。三个双工视图没有事件，
不能表述为关键词检测通过。缺少逐词时间标签与真实负样本时长，因此匹配/漏检数、
FRR、FAR、延迟及 FAR 置信上界全部为 `null`，不以 0 代替未测。

原始 KWS 记录的接口边界：本轮使用的 v1.13.4 Python `KeywordResult` 仅暴露
`keyword`、`tokens`、`timestamps`，这些可见字段全部保留。C API 头的结构体/JSON
还定义 `start_time`，但该字段没有绑定到这个 Python 类；`__str__`/`__repr__`
也是继承的 object 方法，不能取到原始 C JSON。独立审查者对锁定 native 的真实
类型反射确认了这一点，无模型重新执行。这里的“原始记录”指实际 Python 可见字段，
不是完整 C API JSON；没有补造不存在的 `start_time`。

## 运行时身份与来源权利

来源锁包含两个模型档案、18 个解包模型文件、四个精确 wheels、938 个 runtime
文件、关键词、外部转写与 WAV 的哈希。解包到隔离前缀，没有全局 pip 升级、
动态依赖求解或执行上游安装脚本。模型 child 只接收执行所需的环境白名单，不继承
GitHub/Actions/cloud token 或父进程 PYTHONPATH。大模型、wheel 与音频不入 Git。

每例真实进程从 `/proc/self/maps` 读取并哈希 19 个已加载 native 库，同时记录
Python 3.12.14 可执行文件哈希、Linux/glibc 信息与实际包版本。主要实体如下：

| 实际加载实体 | SHA-256 |
| --- | --- |
| `vosk/libvosk.so` | `85c4654de3acdeb99abab86eeb2a6e603927d37089597c0fcc33d8638dc2ccaf` |
| `sherpa_onnx/lib/libonnxruntime.so` | `026c7d5c609323fb16506dbc3cce801bcdffdd7566fdba49a50727e2e1e881ca` |
| `_sherpa_onnx.cpython-312-x86_64-linux-gnu.so` | `658fc6484055892f9330566c6463e0ba258b9dcbb02bf89623d23c13b8d9f6f4` |

NumPy 实际版本 2.3.3，sherpa-onnx 为 1.13.4；Vosk 由 0.3.45 wheel、固定
C API 头与实际 `libvosk.so` 绑定。系统库单独标记 host-system，不声称整个 OS
已做可复现锁定，也不把 host 时间或内存外推到 SSC305/A32。

权利依据及原页面/回复的哈希见[source lock](mandarin-downstream-v1-source-lock.json)：

- [Vosk 官方模型页](https://alphacephei.com/vosk/models)列明 small-cn-0.22
  为 Apache-2.0；Vosk 代码 COPYING 固定到 tag v0.3.45 的真实提交。
- sherpa 精确模型的作者[回复 6052663364](https://github.com/k2-fsa/sherpa-onnx/issues/3802#issuecomment-6052663364)
  与维护者[回复 6415898531](https://github.com/k2-fsa/sherpa-onnx/issues/3802#issuecomment-6415898531)
  已明确 Apache-2.0；保留具体回复与快照，不沿用早期未解决的许可疑问。
- AISHELL-1 依据 [OpenSLR33](https://www.openslr.org/33/) 与固定 WeNet 来源；
  模型包自带 WAV 没有被提取或运行，也没有自动继承模型许可。
- sherpa、Vosk、NumPy 和随 wheel 分发的 OpenBLAS/GCC/quadmath 等原始 notices
  留在完整 runtime/source cache；本轮 host 研究集成不构成目标平台依赖选择。

首次直接读取 GitHub #3802 comments 公共端点返回 HTTP403，4.140 秒后失败；
[原失败日志](evidence/mandarin-downstream-v1/source-acquisition-initial-http403.log)
完整保留。已取得的资产保持不变，随后通过已授权 connector 读取同一个端点，
明确记录 JSON 重序列化与独立恢复回执；来源完整后才提交准入锁并执行模型。
CI 重放使用已冻结的权利结论和 immutable/hash-bound 下载，不需要给模型运行环境
传递读取公共许可的凭据。不存在被覆盖的失败模型首跑。

## 预算、负例与回读

| 阶段 | 实测 wall 秒 | 结果 |
| --- | ---: | --- |
| 精确 wheel/model 安全物化 | 6.742 | 来源操作，不执行模型 |
| 当前 source fresh configure+build | 2.089 | 实际 processor/build-info 生成 |
| canonical metric tests | 0.116 | 24 项通过 |
| 六视图前端准备 | 1.524 | 完整 source/PCM/trace，尚未推理 |
| 模型前 integrity | 6.242 | 11 项通过；4 项真实结果检查明确暂缓 |
| 首次正式六视图 ASR+KWS 矩阵 | 23.897 | 六例实际模型执行完成，退出 0 |
| canonical evidence 回读 | 0.870 | 来源、输入、结果与计数完整重算 |
| 实际结果 integrity | 11.156 | 全 15 项通过，0 skip |
| 另一执行者独立回读 | 103.775 | 6,391 checks；无模型重跑、无新增样本 |

每阶段预算都是 300 秒。来源每个固定资产下载也单独保留起止、实际退出和预算，
未把下载归入模型速度。矩阵 child 使用剩余预算减 3 秒，以给失败日志和 report
封存留时间；report 内部 elapsed 包含第一轮完整 artifact seal，明确排除最后
计时字段刷新与进程退出。本表使用外层 receipt，包含模型进程退出及所有 runner
封存。最终封存超过预算会落 FAIL，未延长预算获取成功。

唯一 scorer 覆盖空参考插入、NFC/空白及保留标点、确定性编辑平手、独立距离
交叉验证、不同参考长度的计数加权、布尔/非有限值拒绝、一事件一标签、重复与错误词、
窗外事件、正/负曝光窗不重叠、零分母 null、零误触发的非零 Poisson 上界等。
它只负责评分，不替代声学 evaluator，也不执行或选择模型。

integrity 测试在一次真实 prepared/result 的副本上篡改再重新封装哈希，确认
不能仅靠自报 hash 通过：改原始/双麦/Render PCM、参考文本、发明 KWS 标签、
移除源文件绑定、替换提交、病例 ID/PCM/status/布尔 exit_code、实际加载库 hash、
额外/缺失文件都被拒绝。超时部分输出及封存预算耗尽通过明确标记的模拟异常测试，
不冒充实际模型超时。每次临时副本都与原始证据分开。

独立回读还用单独的全矩阵编辑距离与 S→D→I 回溯重算六例 S/D/I/N，重新构造
五路 raw/capture/Render 输入并核对 source/native/样点身份；确认 pooled `7/72`
以及所有未标注量为 null。独立回执与 checker 由本轮汇总证据单独归档；这项
复核没有把原始六视图变为新的独立统计样本。

复现命令与全部实际退出日志位于[evidence/stages](evidence/mandarin-downstream-v1/stages/)。
完整 source/prepared/result 的原始外部路径见索引；Git 中 prepared-metadata 是
小型元数据副本，不声称包含完整 PCM。CI 在精确源码下重新准备和执行并上传
完整 prepared/result；不要向这两个被精确成员校验的目录加入辅助文件。

## 当前结论与仍未测的内容

本轮闭合了“实际双麦前端输出→固定中文 ASR/KWS→唯一计数评分→源/样点/库身份
回读”这条软件链，并将捕获与带 Render 两种路径都纳入可重复执行。已测负结果
是后续研究输入，不能靠降低阈值、换词、换句子或选模型抹去。当前单句证据不足以
定位回声、近端增益、AEC/RES/NS/AGC 或模型鲁棒性的独立因果，也不批准任何算法
晋升。扩大统计或改算法需要新的数据角色与冻结实验身份。

仍未测：独立多说话人中文总体 CER/WER、有人类时间标注的 KWS FRR/延迟、真实
负样本 FAR、自播放真人/TTS 误唤醒、真人听评、真实房间双麦、设备扬声器打断、
SSC305 资源与真机链路。合成远端与短单句不能替代这些观测。
