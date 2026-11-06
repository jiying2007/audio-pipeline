# 双麦整合 V1：SAFE 修正前的实际回归记录

日期：2026-11-06。状态：**PRE_SAFE_FIX / DESCRIPTIVE_ONLY**。

本记录封存实际源码 `50068fa285bfa7d209e635c63e86e36bec1bd3e1` 的整合结果：CLI CALL/ASSISTANT 共用现有 pipeline，包含 capture 观察时间归一化与 fixed/tracking BF 健康观察修改。它**不包含后续 SAFE pending epoch 修正**，不能作为该修正或最终候选已通过的证明。原始 report/manifest/CTest/resource log 保留原字节，不改写已有执行身份。

## 身份、工件与可恢复性

- 实际本地提交：`50068fa285bfa7d209e635c63e86e36bec1bd3e1`，tree `adfa31b50ae6d7977829a65b039eddb529068985`。
- 共同冻结基线：`6056682486c1a2a2c84d77135de8118e07fc8cf3`。
- 构建：2.3.62、GNU 14.2.0、x86_64-linux-gnu、Release、SCALAR、MDF、EMA、BANDLIMITED、fast_math=0。
- 两个构建均为全模块 mask 1023；区别为编译选项 `AP_ENABLE_BF_DIRECTION_TRACKING=ON/OFF`。OFF 构建仍保留固定方向 BF 健康观察。
- [紧凑证据与 receipt](../../../validation/research/evidence/dualmic-integration-50068fa/) 保存两份原始报告、原始完整 artifact manifest、实际 build/default-tuning 记录、CTest、输入 manifest、逐例连续性回读及资源日志。
- [本地源码恢复包 V1](../../../validation/research/evidence/dualmic-local-source-v1/README.md) 已实际验证可恢复本提交。此 SHA 是本地实际运行身份，**不是 GitHub 连接器另建提交的 SHA，也不是远程 Verify SHA**。

| 构建 | 处理器 SHA-256 | Report SHA-256 |
|---|---|---|
| tracking ON | `e60729256ff123864c92db6ef1395f4fe915e1cc50e15882d52b235fa3347677` | `560d07762a81e5244e6e742d4b4aca89d8d64a6288b64a01e982c4d89a136ac2` |
| tracking OFF | `acb334183075ae1ffecf527f92ddebe768f5b5ca80c471958d58b064b619c730` | `3cc734797569166631c9e8c10e5d931141633748a9fe2f1b68d09a24c1e397b4` |

本次封存重新读取完整工件并校验 SHA-256/size，又检查 report 的源码文件绑定均等于实际 Git 提交。没有重跑声学实验。完整 PCM、逐帧 JSONL 与二进制未写入紧凑证据；原始完整 manifest 仍指向全量本地证据树，不能把它误当作仅检查紧凑目录的清单。`compact-manifest.json` 单独校验本次实际保留文件。

## 实际测试与回放覆盖

| 项目 | tracking ON | tracking OFF | 解释 |
|---|---:|---:|---|
| 原始 CTest | 63/63 PASS | 63/63 PASS | 真实测试日志；不包括之后新增的 SAFE 边界用例 |
| CTest wall time | 1.43 s | 1.45 s | 测试套件本次 wall time |
| 冻结合成回放 | 42/42 完成 | 42/42 完成 | 结构和覆盖完成；没有声学胜出阈值 |
| 全量工件校验 | 379 文件 / 30,634,673 B | 379 文件 / 30,634,096 B | 两份完整清单全部 SHA-256/size 相符 |
| 回放 wall time | 43.900 s | 44.124 s | 包含 Python 指标与工件处理；不是帧实时性、算法 RTF 或 A32 性能 |
| 每 case 实际输出 | 96,000 mono S16 样点 | 96,000 mono S16 样点 | 独立从 PCM 字节长度回读 |
| 每 case metrics | 600 帧，编号连续 | 600 帧，编号连续 | 实际逐帧 JSONL 校验；值均为有限值 |

两构建使用**相同的输入 corpus 和 source manifest**。矩阵保持既有 7 场景 × 3 seeds（5107、6107、7107）× 2 profiles；每例 16 kHz、双麦、35 mm、6 s，场景为 near-only/no-render、silent-render、far-only、nominal/weak double-talk、path-change、render-gap。数据角色仍是已曝光工程回归；`split=validation` 是 canonical schema 字段，不表示独立盲测。

所有 case 的 `expected` 均为空。原始报告中的 `canonical_summary.pass_rate=1` 和逐 case `passed=true` **不能称为音质 PASS**。连续输出、精确覆盖、命令 profile、进程退出状态另有实际检查；本记录不增加或调整声学门槛。两构建共 84 次 case 执行，不等于 84 个独立输入，也没有复用 CLI-only 基线逐字节等价判据来评价已经改变的 DSP。

默认 tuning 回读均保持：CALL `aec_mu=0.219999999`、`ns_floor=0.119999997`、AGC −20 dBFS、limiter −2 dBFS；ASSISTANT `aec_mu=ns_floor=0.180000007`、AGC −18 dBFS、limiter −2 dBFS。完整 preset 配置由既有真实 init/get_config/direct-API CTest 验证；这四个 tuning 字段本身不是完整配置证明。

## 描述性声学观察

以下数值来自原始 canonical/quality 汇总，保持同一输入和指标定义；不据此判定 profile 或 tracking 模式优胜。

| Tracking | Profile | median ERLE dB | P10 near projection gain dB | P10 interference attenuation dB | P90 VAD onset ms | P90 ERLE recovery ms |
|---|---|---:|---:|---:|---:|---:|
| ON | CALL | 26.988 | -5.085 | 35.084 | 10 | 190 |
| ON | ASSISTANT | 24.071 | -5.113 | 34.846 | 10 | 195 |
| OFF | CALL | 27.034 | -5.080 | 34.956 | 10 | 195 |
| OFF | ASSISTANT | 24.131 | -5.116 | 34.808 | 10 | 190 |

四组最大 clipping fraction 均为 0。near projection gain 的 P10 约 −5.1 dB，说明近端幅度保留仍需关注；不能因回声/干扰下降就声称对讲近端保真改善。ERLE 仅适用于有已知 echo 的对应场景，near/干扰指标按各自真值适用范围计算；不能跨场景合成一个未注册质量分数。VAD onset 不是 KWS 端到端响应时间。

本矩阵不包含 SAFE quality 切换，因而本次全部连续性与回放完成不能证明 SAFE 间隔后的 pending evidence 正确失效。后续 SAFE 修正及其新增定向负例须单独报告实际执行 SHA；不得把它们补写成 `50068fa` 的已执行结果。

## 实际资源读回：各自的构建 envelope

封存时直接运行原构建目录中现有 `ap_state_size` / `ap_runtime_state_size`，没有重编译；输出与已保存 resource log 一致。generated header 均绑定本次 `50068fa`，查询二进制 SHA-256、退出码、stdout、实际宏值保存在 `resources/resource-readback.json` 和 `.log`。

| 构建 | 最大 I/O / internal rate | 最大麦数 | delay / AEC tail | queue | Pipeline bytes | Runtime bytes |
|---|---|---:|---|---:|---:|---:|
| full tracking ON | 48k / 16k | 2 | 300 / 120 ms | 8 | **78,224** | **32,760** |
| full tracking OFF | 48k / 16k | 2 | 300 / 120 ms | 8 | **78,224** | **32,760** |
| composition-low | 48k / 16k | 2 | 180 / 64 ms | 4 | **47,056** | 未构建，runtime OFF |
| composition-tiny，runtime ON | 16k / 8k | 1 | 120 / 48 ms | 4 | **25,432** | **5,176** |
| composition-raw | 48k / 16k | 2 | 无 AEC/SYNC | 8 | **1,064** | 未构建，runtime OFF |

这里的 rate/mic/delay/tail 是**编译上限**，不改变回放每例实际 16 kHz 双麦输入。tiny 为 mono 且没有 BF；raw 仅编译 RESAMPLER，均不能充作完整双麦前端的资源或声学结果。low 的 pipeline 数不能与其他 envelope 的 runtime 数相加。

这是 native host 的结构状态字节数，不是进程 RSS、栈高水位、ROM 或物理 SSC305 内存/性能测量。full pipeline 与 runtime 分别为 78,224 / 32,760 B，不能把较小 profile 的资源数字代入 full 构建；本次没有通过改编译上限或资源门槛将结果标成通过。

## 复现与未测范围

先按源码恢复包说明取得实际 `50068fa`，在该 detached 源码目录中构建。以下分别执行既有 default 与 tracking-OFF 构建，输出目录须新建；没有新 workflow 或新声学阈值。

```sh
cmake -S . -B /tmp/ap-dualmic-on -G "Unix Makefiles" \
  -DCMAKE_BUILD_TYPE=Release -DAP_STRICT_WARNINGS=ON \
  -DAP_BUILD_BENCH=OFF -DAP_BUILD_TESTS=ON -DAP_BUILD_EXAMPLES=ON \
  -DAP_ENABLE_LINUX_RUNTIME=ON -DAP_SIMD_BACKEND=SCALAR -DAP_ENABLE_FAST_MATH=OFF \
  -DAP_BUILD_SOURCE_REVISION=50068fa285bfa7d209e635c63e86e36bec1bd3e1 \
  -DAP_ENABLE_BF_DIRECTION_TRACKING=ON
cmake --build /tmp/ap-dualmic-on --parallel
ctest --test-dir /tmp/ap-dualmic-on --output-on-failure
cmake -S . -B /tmp/ap-dualmic-off -G "Unix Makefiles" \
  -DCMAKE_BUILD_TYPE=Release -DAP_STRICT_WARNINGS=ON \
  -DAP_BUILD_BENCH=OFF -DAP_BUILD_TESTS=ON -DAP_BUILD_EXAMPLES=ON \
  -DAP_ENABLE_LINUX_RUNTIME=ON -DAP_SIMD_BACKEND=SCALAR -DAP_ENABLE_FAST_MATH=OFF \
  -DAP_BUILD_SOURCE_REVISION=50068fa285bfa7d209e635c63e86e36bec1bd3e1 \
  -DAP_ENABLE_BF_DIRECTION_TRACKING=OFF
cmake --build /tmp/ap-dualmic-off --parallel
ctest --test-dir /tmp/ap-dualmic-off --output-on-failure
python3 tests/validation/build_dualmic_profile_corpus.py \
  --output /tmp/ap-dualmic-corpus
python3 tests/validation/run_dualmic_profile_replay.py \
  --processor /tmp/ap-dualmic-on/ap_process_pcm \
  --corpus /tmp/ap-dualmic-corpus/corpus.json \
  --output /tmp/ap-dualmic-evidence-on --source-revision 50068fa285bfa7d209e635c63e86e36bec1bd3e1
python3 tests/validation/run_dualmic_profile_replay.py \
  --processor /tmp/ap-dualmic-off/ap_process_pcm \
  --corpus /tmp/ap-dualmic-corpus/corpus.json \
  --output /tmp/ap-dualmic-evidence-off --source-revision 50068fa285bfa7d209e635c63e86e36bec1bd3e1
```

实际 canonical runner 会记录每个输入、命令、连续性、输出、build/default-tuning 与 source binding。composition-low/tiny/raw 的精确配置与命令已保存在原始 resource logs；tiny 的 runtime ON 是本次显式覆盖，不把预设名称当成配置全貌。

仍为 **NOT_RUN**：真实中文 KWS 的固定 FAR 下 FRR/时延、ASR、真人远场双麦房间、主观对讲近端保真/残余回声/双讲/pumping、物理 SSC305 的帧时限、CPU/热/功耗，以及后续 SAFE 修正后的本矩阵重放。这里没有新训练、参数搜索或胜出判定。
