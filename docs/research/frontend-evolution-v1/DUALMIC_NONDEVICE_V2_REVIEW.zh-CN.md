# 双麦非真机 V2：审查修正与证据边界

本记录承接[冻结合同](DUALMIC_NONDEVICE_V2_PLAN.zh-CN.md)，只记录已发生的复核、
具体发现与最小修正。独立审查、作者自回读、精确提交 CI 和声学效果是不同事实。

## A：实际核验完成，首个独立审查整阶段超预算

作者的 56 例正式回放和自回读均完成于原预算内。另一实施者独立核验原 f4f222f
产物，retained verifier 退出 0、自身耗时 59.102 秒，完成 650 文件、56 个 canonical
条目和 84 WAV 检查；独立 NumPy 公式的 16 个有效双讲 SI-SDR 最大差为
2.135e-12 dB，84 WAV 共 16,128,000 个 PCM 字节一致。

**该独立审查的整个阶段仍为 REVIEW_BUDGET_EXCEEDED。** 实际核验在总计时
256.442 秒完成，整理最终 receipt 时超过原 300 秒并主动抛出异常；之后只归档
既有结果，没有重跑、继续验证或重置原计时。不能把局部核验成功写成整个阶段
按时通过。原开始记录、stdout、脚本与预算异常均见
[独立审查原件](evidence/dualmic-recorded-speech-v1/independent-review-budget-exceeded.json)。

复核确认 near-only/silent-render 的 mic0 与 clean 完全相同，原 improvement 中
约 -228 dB 的数学差来自输入数值下限，canonical 已正确排除其改善指标。
每 profile 另有八个有效混合条目；最差 pair-0 nominal 的 -12.4129/-12.0928 dB
可独立复算，不能忽略，也不能据此确定某一 DSP 模块的根因。

对齐实现是以声明的 160 samples 输出延迟为中心进行 ±3 ms 有界搜索，并非完全
不搜索。本组有效场景实际均选 output160/input0；指标使用未去均值的标量投影。
完整六秒包含远端单讲、放置区间重叠、近端单讲及静音；没有逐帧人工活动标签。
本轮没有通过调模块或改指标消除负结果。

## B：独立实际 Opus 解码回读

另一实施者审阅 corrected source dbbbe7e 并编写独立 reader，没有导入 B 的 codec
或网络 helper。完整阶段 131.224705 秒，预算 300 秒，43,011 项检查完成。
全部 296 manifest 成员加 manifest 本身、57 个 source blob 和 6,040 个 packet
record 一致；对原 payload 实际重新调用 libopus decoder/PLC，包含八次 PLC，
得到的全部 PCM 与保留产物逐字节一致。

初始化后真实配置回读、8 个 Runtime/direct 对照、播放音量/重开日程、重复与
未来前缀均完成核验。6,080 Runtime 帧、4,864 direct 帧和 event_drop_events=1/3
原样保留，没有重新执行前端 DSP。首次 e7f 错误身份表述的 report/manifest hash
仍一致，未覆盖。见[独立回读 receipt](evidence/dualmic-intercom-v1/independent-readback.json)；
同目录保留原开始记录及一次性审计脚本 `.py.txt`，其绝对路径属于原宿主执行，
不宣称该历史计时脚本是可重用 CLI。

## C：正式推理前的证据校验修正

代码审查发现初版 prepared/result verifier 主要比较自报 hash，无法充分拒绝
同时重新封印的 PCM、参考文本和身份字段。正式模型推理前补齐固定来源重新派生、
精确文件集合、已提交源码绑定、manifest 参考/样点/模型重建和 actual result
身份/成功状态/native 库检查。额外实际产物负例独立于模型质量，不以模型输出
改写标签或阈值。

canonical scorer 增加按 S/D/I/N 总数计算的 pooled-view 记账，禁止简单平均各例
error rate，并明确不声称六个视图相互独立。模型子进程使用最小环境 allowlist，
不继承调用者 token/PYTHONPATH。原 300 秒内预留三秒杀进程、保存部分日志和封存，
超时仍失败；没有延长时间或替换模型来获得成功。

模型前的 source-only 取得曾遇公开 GitHub REST HTTP403。原失败保留，仅以已连接
GitHub GET 取得同一许可评论端点；模型/录音和阈值未替换。后续 CI 消费已审查
来源锁，不重新请求可变许可页或依赖凭据。实际模型结果另见 C 结果页及精确 CI。

## CI 集成审查修正

独立审查发现，初始 SemVer-neutral 清单虽然允许 host scorer 不升级 SDK，但
单独 `analyze([downstream_metrics.py])` 仍只得到 validation-only，与冻结合同承诺
不符。修正仅把此精确路径纳入原 canonical FULL 分支，并扩展原 self-test。
实际复核为 full/run_audio/run_extended/run_tuning 全 true；29 项 self-test 完成。
未知 helper 的版本规则和其他路径分类不变。

A 现先建立独立 stage，单测、配置、构建、corpus、replay、readback 全部 tee 日志，
always artifact 同时保留原始 corpus、正式 result 和失败前产物；runner output
仍为新路径。B 安装/编译日志同样保留。中文命令显式加 `timeout 300s`。
C actual-artifact 负例需要 source/prepared/result；首次 root CLI 预检漏参退出 2
已保留在[预检记录](evidence/nondevice-v2-integration/preflight-cli-error.json)，随后将
其 CI 顺序置于真实结果产生之后并传完整参数；没有伪造模型结果。

两个 workflow 未删除旧 job/命名 step，原 if/needs/job timeout 未放宽；
`src/`、`include/`、生产 CMake 与版本/默认值不变。后继精确 PR/main 必须使用
各自的实际源码、门禁和产物；本页不是对尚未执行的 CI 提前签发 PASS。

## C 独立回读与整合源码本地执行

C 的另一实施者完成 103.775 秒 / 300 秒独立回读，6,391 项检查，未重跑模型或
DSP，也未导入生产 scorer。独立核对 14 资产、18 模型成员、938 runtime 成员、
全部 prepared/result，以及每例 19 个实际 loaded native 文件；重建五路输入
和六个视图，并用单独编辑距离重算 S/D/I/N。见
[独立 C 回执](evidence/nondevice-v2-integration/mandarin-independent-readback.json)。

修正后的整合源码 `3ce56566c4c20b30eb75a93d51e454527566aa9c` 又取得自身的 fresh
构建、A/B/C 运行与自动回读。全部 11 阶段在各自原 300 秒内完成，实际命令、日志
和各结果 digest 见[整合本地记录](evidence/nondevice-v2-integration/integrated-local.json)。

| 整合阶段 | 实际秒 | 结果 |
| --- | ---: | --- |
| fresh configure/build/bridge | 2.856 | 完成 |
| A corpus | 5.796 | 原始来源重建完成 |
| A 56 例矩阵 | 68.815 | 完整执行 |
| A 自动全量回读 | 59.086 | 650 文件/56 例/84 WAV |
| B 实际 bridge 单测 | 0.218 | 完成 |
| B 8 场景及两控制 | 9.608 | 完整执行 |
| C canonical metric tests | 0.117 | 24 项完成 |
| C 六视图 prepare | 1.277 | 完成 |
| C 六视图真实模型 | 26.000 | 完成；负结果仍在 |
| C 自动回读 | 0.869 | 完成 |
| C actual-artifact integrity | 11.613 | 15 项完成，无 skip |

193 个跨源码产物比对确认：A 全部输出 PCM/JSONL、B 全部工程场景/控制的捕获、
播放、Runtime PCM/trace 和双向 Opus payload/decoded PCM，以及 C 全部预测原始
结果与对应首轮逐字节相同。实际 source metadata 与 wall timing 单独保留，不
要求它们伪装相同。来源使用原已准入缓存并重新校验，没有冒称又下载了语料。

这里的 A 自动回读属于新整合源码的独立执行阶段；原 f4 独立人工审查的整阶段
REVIEW_BUDGET_EXCEEDED 仍保留，不把其计时重置为本次 59.086 秒。A/C 的声学和
下游负结果也没有变为质量 PASS。四项 CI 接线修正经原审查者再次只读复核为
RESOLVED，且无范围内剩余发现；见[CI 修正回执](evidence/nondevice-v2-integration/ci-integration-review.json)。
