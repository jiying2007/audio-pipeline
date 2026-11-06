# 双麦真实录音整链回放：首轮结果

2026-11-06（Asia/Shanghai）。身份 `FE-C2-RECORDED-SPEECH-DUAL-USE-V1`。
**56 例测量完整完成；声学结论为 DESCRIPTIVE_ONLY，存在明显负结果，不能宣称音质通过。**
独立集成审查、精确 PR/main CI 的后续结果应另行记录；本页不提前声明它们通过。

## 冻结与实际对象

共同合同提交 `494ae5ebb9c5cba4a8c3d0739430259a3649513f`，
[详细合同](DUALMIC_RECORDED_SPEECH_V1_PLAN.zh-CN.md) 先于新数据取得和执行提交于
`d674c0c45401b78761045c6a7c81ecf60dd49d16`。实现先提交到
`f4f222ff3f3c65689e2462bb50277b84afb6b025`，再构建和正式运行。
这是当前 2.3.63 DSP 的新测试/测量接入；DSP、公共 API、preset 和旧评估门槛未改。

真实输入来自已独立准入的 LibriSpeech 八说话人各 4 秒窗口，共 **32 秒独特录音**。
原 origin artifact 12107574410 / run 39052067322 实际恢复成功：204415056 B，
SHA256 `1dffd4fc4968a0a214658627f1faf8bf54268f119fda86600a48511f897f30d4`。
只解出 `effects/data/` 的 46 个原始来源文件，完整执行原 source_check；没有复制或
使用旧科学分数。当前没有重新下载 337926286 B 官方原始 archive，也没有再次运行
FLAC 解码器；原 source receipt 中的 decoder 身份仍属于其原始取得过程。

四对说话人、七场景、两个用途共 56 个六秒输出：336 秒处理输出、5,376,000 个
mono 样点、33,600 个连续 10 ms telemetry 帧。重复来源与派生视图不增加独立
说话人/房间数量。所有 effective_role 都是 regression；不是新的盲测。
真实英文语音与合成双麦传播/回声必须分开描述。

实际生产处理器构建身份：GNU 14.2.0、x86_64-linux-gnu、Release、SCALAR、MDF、
EMA、BANDLIMITED、fast_math=0、module_mask=1023、source 2.3.63 / f4f222f。
config_digest=`7abf0ce0985d3d15682037f715d7afc0c1844a725f56aef29164c25d103d557a`。
实际 processor 和 build-info 二进制随证据保留并绑定哈希；不是先前 GNU 13 的
ARM 测量，也不构成 SSC305 实时性能证据。

## 验证与预算

| 阶段 | 实际结果 | 观测耗时 / 预算 |
| --- | --- | ---: |
| 固定资产取得、落盘、ZIP hash、原 46 文件 source_check | 完成；没有旧分数复用 | 37.475757 / 300 s |
| native 构建 | 两个实际生产 executable 完成 | 1.986843 / 300 s |
| 方法定向/负例 | 9 tests 成功 | 37.229583 / 300 s |
| 56 例 corpus 生成和原字节重建校验 | 完成 | 5.479799 / 300 s |
| 唯一正式矩阵与材料生成，外层完整命令 | 56/56、无失败、正常退出 | 63.963196 / 300 s |
| 作者自回读，全部指标和 WAV 复核 | 完成；不重跑 DSP | 63.437065 / 300 s |

作者自回读不等于独立人员审查。正式执行于北京时间 21:14:44 完成；
自回读于 21:16:12 完成。原始命令、返回码、时间、测试日志与各阶段事实保存在
[阶段记录](evidence/dualmic-recorded-speech-v1/phases.json)。定向测试里故意运行的
错误 source worker 返回 FAIL，并被测试确认保留；这是负例成功，不是正式语料失败。
本轮没有意外失败后改阈值、换源、调参或重复选优。

方法测试拒绝缺/重复 case、错误 profile、阈值和控制事件、角色升级、伪造真人
VAD 标签、截断输入、额外文件、重新封印后改变 PCM、超范围混合、不完整输出、
非有限 telemetry、WAV 电平/身份改变，以及失败 worker 被伪装为完成。
其中人工数组只作 D0 方法测试；它们实际不能通过原真实来源 admission。

## 实际声学观察：保留坏结果

下表完整沿用 canonical 指标，没有引入质量成功阈值。ERLE 是当前完整前端输出
指标，含 NS/RES/AGC 等共同作用，不能独立归因为线性 AEC 的滤波器抑制能力。

| 指标 | CALL | ASSISTANT |
| --- | ---: | ---: |
| 完成 case | 28 | 28 |
| 有效远端场景 ERLE 中位数，dB | 3.049332 | 3.194176 |
| 所有远端场景最差 ERLE，dB | -8.198827 | -8.297337 |
| 双讲 near SI-SDR improvement 中位数，dB | -0.115602 | -0.625832 |
| 双讲 near SI-SDR improvement P10，dB | -8.851120 | -8.768297 |
| 普通双讲最差 near SI-SDR improvement，dB | -12.412929 | -12.092781 |
| near projection gain P10，dB | 1.973737 | 3.014377 |
| interference projection attenuation P10，dB | 3.916208 | 3.531406 |
| canonical 事件恢复 P90，ms | 549 | 556 |
| 最大 output clipping fraction | 0 | 0 |

**近端双讲失真与部分远端负 ERLE 都是真实保存的测量结果。** 没有新候选与独立
验收阈值，本次不决定任一 profile 优胜，不升级默认参数，也不修改这些坏结果。
数据规模仅四个说话人 pair、合成传播，不能据此给出总体用户表现或显著性结论。

near SI-SDR improvement 的汇总实际只适用每 profile 的 8 个双讲 case。
near-only / silent-render 的输入与 clean reference 完全相同；canonical 已标记
`input_near_reference_identical` 并从 improvement 汇总排除。其原逐例数学差值
仍保留，不能将相对数值地板产生的巨大负差称为实际损伤的 dB 量。
projection gain 不是 dBFS 或主观音量评分；VAD 准确率、起止延迟均未测。
canonical settling 是相对各例末段中位水平减 3 dB 的三窗规则；不能把它的
0 ms convergence 记录解读为立即完成 AEC 收敛，或把 recovery 解读为端到端时延。

原 canonical `pass_rate=1.0` 是 **全部 `expected={}` 时的阈值记账**。
本实验工程完整性是成功的，音质没有因此被判定通过。报告头始终记录
`quality_decision=DESCRIPTIVE_ONLY`、`acoustic_thresholds_applied=false` 和
`promotion_allowed=false`。

## 可回读交付物

完整本地证据根目录为 `dualmic-recorded-evidence-v1/replay-f4f222f`：
650 个文件、63,486,470 B，含原始来源、28 组输入、56 组实际 PCM/JSONL、构建
二进制、源码快照、逐例实际命令和报告、匿名听评材料及独立 key。
[完整逐例报告](evidence/dualmic-recorded-speech-v1/report.json) SHA256：
`8d33e84c908cc3641c7404f46a9b33708b30402038be4be9e42d6d4f4da5d02b`。
[原始工件清单](evidence/dualmic-recorded-speech-v1/artifact-manifest.json)
绑定全部原始文件哈希；本小型 Git 结果目录不包含大音频。

28 个听评试次，每次 raw mic0、CALL、ASSISTANT 三个匿名选项，共 84 个 WAV。
WAV 数据与对应 PCM 逐字节相同，没有输出归一化或截尾；原 mic0 未人工补齐处理器
延迟。固定 SHA256 排列和单独 key 便于复现，不代表已进行安全隔离的盲听。
署名、原许可证和衍生说明随包保留。**human_listening=NOT_RUN**，没有 MOS。

复现入口（`SHA` 必须是实际构建和检出的完整提交）：

```sh
python3 tests/validation/test_dualmic_recorded_replay.py
python3 tests/validation/build_dualmic_recorded_corpus.py \
  --source /path/to/admitted-46-file-source --output /path/to/fresh-corpus
python3 tests/validation/run_dualmic_recorded_replay.py \
  --processor /path/to/build/ap_process_pcm \
  --corpus /path/to/fresh-corpus/corpus.json --output /path/to/fresh-replay \
  --source-revision "$SHA"
python3 tests/validation/run_dualmic_recorded_replay.py \
  --output /path/to/fresh-replay --verify
```

来源 getter 继续使用已存在的 `speech_pinned_snapshot.py`；不复制新的下载流程或
平行声学评估器。后续 CI 应在同一来源核验之后执行本入口，保留对应实际 source SHA。
中文 KWS/ASR、真人听评、真实房间/互联网与物理 SSC305 结果仍按各自实际工作包
报告，不能由本实验代替。未进行进一步声学参数搜索。
