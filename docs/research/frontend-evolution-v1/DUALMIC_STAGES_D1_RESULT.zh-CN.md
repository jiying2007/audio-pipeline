# 双麦 D1：完整同状态诊断实际结果

日期：2026-11-07（Asia/Shanghai）。任务 [#922](https://github.com/jiying2007/audio-pipeline/issues/922)，
[PR #923](https://github.com/jiying2007/audio-pipeline/pull/923)。本页记录首次实际执行，
不是合并后 main 身份或通用音质资格；最终 head/main 的独立门禁与原件见任务实时索引。

## 结论

**60 例中性阶段测量有效，独立原件复核通过。预先提出的“NS/频域 RES 联合阶段为
本批英文双讲主要损伤来源”假设受到削弱；不满足据此直接进入 frequency-off 的条件。**

16 个 A nominal/weak 双讲例的固定公共跨度 NS/频域 RES SI-SDR 增量全部为正。
原来表现最差的 pair 0 在 AGC 阶段出现明显 SI-SDR 下降；其他 pair/场景的 AGC
变化不统一。中文 duplex 的 gate 与能量现象另行保留，不能用英文结论替它归因。

这次没有候选算法、扫参、默认变更或新的声学通过结论。D1 只观察原有流水线，
所有真实输出仍等于原 main 结果；不是通过修改评估器取得音质改善。

## 精确执行与原件

| 项目 | 实际身份 |
|---|---|
| 执行 source | `31b949c14d473fe8221a4125adf896a75e785644` |
| source tree | `e568ba3bda62127a1676d894cdf768765f9ea74f` |
| 生产字节基线 | `4daa7e239eebda11f6c7066df2e851269021112f`，2.3.63 |
| 冻结合同 commit | `22e9ff695ee8b2cb552673cfe4d4d9ad8ba211e3` |
| Frontend Research | [42318230362 / attempt 1](https://github.com/jiying2007/audio-pipeline/actions/runs/42318230362)，success |
| Artifact | [13552165963](https://github.com/jiying2007/audio-pipeline/actions/runs/42318230362/artifacts/13552165963) |
| ZIP | 404,327,625 bytes；2,836 members；解包 754,943,374 bytes |
| ZIP SHA-256 | `2d72315f28a5801aa6a753bdaefa7c7460c409863430843dbb074cae0efb167e` |
| report.json SHA-256 | `6ebc4242874563d76d3c59ccc53e4b3746b9e09cf4a6304bfeec367a4536309e` |
| artifact-manifest.json SHA-256 | `190faf324499c64b4a9a268b0df8cd810082586d63ed6caef08480960369789f` |

原 A/C ZIP 全量锁、old PCM/trace、实际执行命令、Float32 taps、控制 CSV、完整
源码 archive、五处可逆变换、库/程序/headers/flags/日志都在实际工件中。没有
重新生成原样本或重新跑中文模型。新 source 与旧 source 分别记录。

实际阶段时间：原件取得 3.293272 秒；60 例 plain+observer 执行与证据准备总阶段
6.476364 秒；阶段分析与封存 25.543753 秒；独立进程工具读回 25.625196 秒。
各自通过冻结的 300 秒预算及末端写盘检查；不能将这些 Host 时间称为物理设备预算。

## 中性与独立复核

60 例 × 三份（原 main、fresh plain、observer）的最终 PCM 和原 metrics JSONL
全部逐字节相同。累计 35,916 帧、5,746,560 mono 样点；Activity/NS/AGC 各
35,916 次，AEC 30,058 次，capture-only 5,858 帧，独立时域 RES 0 次。
capture-only 的 AEC taps 确实 absent；没有补造 AEC 输出或启用原来关闭的模块。

独立审查者直接下载完整原件，首次运行即 PASS：7,401,395 项检查，11,386 次
数值一致性比较，27.477176 秒/300 秒；无失败重试、DSP 或模型执行。核对范围
包含 actual Git blobs/source archive、五处逆变换、实际构建证明、全部 PCM/trace、
七 lane 时序、固定完整窗口，以及 AGC Float32 到实际 S16 输出。最大数值差
`2.291500322826323e-12` 仅是独立算术审计误差，不是声学验收容差。

- 独立 checker SHA-256：`f9c2b57d62041e61e85f2ef5566b067d7a2a381f32a461e75c73f8e896dca67b`。
- 独立回执 SHA-256：`4d6b936df3ae288ab759cf94ffba482e7cd540fc9aeb592cf8ab54cc69e7f1f7`。
- outer ZIP 绑定回执 SHA-256：`e94be89d75a2fba6b14f3f42d8164027f46289c0d442c0f541e08c48af8ac442`。

## 英文固定双讲的阶段结果

以下全部使用 D1 的公共跨度 `[0,N-160)`，post-NS lane 偏移 160 样点；不做
逐级 lag 搜索。与旧全六秒 ±3 ms alignment 的 canonical 得分不是同一测量定义，
不能跨定义直接做差。每行四个固定 pair，无事后剔除。

| Profile / 场景 | AEC 增量中位 dB | NS+频域 RES 增量中位 dB | AGC 增量中位 dB | AGC 最小增量 dB |
|---|---:|---:|---:|---:|
| CALL nominal | -0.143348 | +0.895635 | -0.329893 | -4.910133 |
| ASSISTANT nominal | -0.163305 | +0.914998 | -0.312134 | -4.646694 |
| CALL weak | -0.771073 | +1.160541 | +1.581435 | -3.795951 |
| ASSISTANT weak | -1.246165 | +1.123903 | +2.002015 | -3.843966 |

NS/频域 RES 的 16 个单例增量均正，不能称其在该公共跨度整体造成主要退化。
固定一秒窗口和完整逐例数据仍在工件中；共同跨度改善不保证每个局部语音片段
都改善，也不替代听感、识别或独立效果验证。

最差 nominal pair 0 的阶段 SI-SDR：

| Profile | post-HPF/BF / AEC input | AEC residual | NS+频域 RES | AGC output |
|---|---:|---:|---:|---:|
| CALL | 10.957051 | 10.607644 | 10.752680 | 5.842547 |
| ASSISTANT | 10.957051 | 10.668315 | 10.809402 | 6.162708 |

near-only 控制也有 AGC 阶段变化：CALL 四例中位 -2.943934、最小 -5.822848 dB；
ASSISTANT 中位 -2.268843、最小 -4.860304 dB；相应 NS 阶段中位仅 -0.369708 /
-0.339858 dB。near-only 全程没有 AGC allow 翻转，因此不能把全部现象归于 far/DT
门控切换。SI-SDR 只对单一全局缩放不敏感，预期的时变电平控制也会改变该指标；
不能直接把这些下降称为硬削波、听感变差或识别错误。

实际 `gain_after` 是平滑状态增益，后面还有 far/DT 的 unity cap 和整帧 peak cap；
它不等于实际应用增益。后续必须先分清 state gain、gate cap、peak cap 与量化，
不能看到 state gain 高就修改 limiter 或泛化扫参。

## 中文 duplex 保留的独立问题

两例均 629 帧，far=551、DT=0、frequency_active=551，AGC allow=78。新观测保持
原 PCM，所以旧的单句中文 CER/KWS 负结果仍然成立，未重标或重算。

| Profile | AEC residual / AEC input RMS 差 dB | NS output / residual RMS 差 dB | AGC / NS RMS 差 dB |
|---|---:|---:|---:|
| CALL | -7.961342 | -6.125754 | 0.000000 |
| ASSISTANT | -7.947048 | -6.168098 | 0.000000 |

这里是混合信号能量变化，没有已准入的 clean-near stage 真值，不能把回声消除
和语音损伤混为一谈，不能计算 DT 漏检率。AGC 与 NS 的 RMS 在报告精度下相同，
**不是逐字节相同**：CALL 首差 sample 89013、ASSISTANT 首差 sample 88960，均在 frame 556，
对应 allow 恢复后的尾部。不能据此声称整条中文退化已经由 AGC 或 RES 单独解释。

## 本轮决策与未测边界

遵守冻结分支：不执行以“英文双讲主要损伤在 NS”为前提的 frequency-off 后继；
优先问题改为实际 AGC 增益传递及 HPF/BF 联合上游的分离观察。中文识别路径需要
自己的固定输入因果对照，不能从英文聚合统计推导答案。

不重开已关闭的 AGC/limiter lower-paired 扫参、15 dB global gain cap 或 error-adaptive
release；也不重开 D41–D49 的保护 floor/innovation 系数搜索。新的结构研究须有
独立冻结身份和准入证据；这次没有产生可晋升算法。

没有新增 blind/independent-validation、真实双麦声场、中文多话者识别率、真人
MOS、WAN 端到端时延、SSC305 声学/功耗/热/长期运行结果。本轮科学测量有效与
完整 CI 是否通过分别记账；首次 Verify 的真实失败见下一份接线记录。
