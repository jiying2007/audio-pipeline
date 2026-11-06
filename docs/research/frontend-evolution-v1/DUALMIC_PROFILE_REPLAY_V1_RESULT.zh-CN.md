# 双用途 profile 接入：首轮实际回放结果

日期：2026-11-06。身份：`FE-C2-DUAL-USE-PROFILE-REPLAY-V1`。

**软件接入与冻结合成矩阵完成；声学结果只作描述，不作 profile 优胜判定。**
此结果只覆盖 CLI/preset 工作包，不包含并行 SYNC、BF 修复后的集成成绩。

## 源码与实际执行

- 原 DSP/CLI 基线：`438fe09d79ff768306c00573849517bcd91cbc6e`。
- 共同合同：`6056682486c1a2a2c84d77135de8118e07fc8cf3`。
- 独立矩阵冻结：`96f892baebe189ae976b12751f960caeffb22467`；
  [实施前记录](DUALMIC_PROFILE_REPLAY_V1_IMPLEMENTATION_FREEZE.zh-CN.md)。
- 本轮实际构建/执行源码：`edff155ce9541dc42feb1660e6b7a30d8e9fa63a`。
- Host：GNU 14.2.0、x86_64-linux-gnu、Release、MDF、EMA、SCALAR、
  BANDLIMITED、fast_math=0。中间工作包 build version 为 2.3.61；
  共同集成另行统一 2.3.62，不能把该后续版本冒充本轮执行身份。
- 处理器 SHA-256：`1e197df0f5d30780c6a5a11a947d0ff9ca641ccc3c189bfad4442c683ea61461`。
- report SHA-256：`b1b0336797900ebcb3477606498f603074e96cad6f628d52da1364a4ba6d6f04`。

结果与 compact 原始日志保存在
[`validation/research/evidence/dualmic-profile-v1-cli-edff155/`](../../../validation/research/evidence/dualmic-profile-v1-cli-edff155/)。
其中 report、artifact manifest 和测试/构建日志均为实际输出原字节复制；
完整 PCM/逐帧 JSONL 位于 receipt 记录的本地 evidence root，未将约 44 MB
重复音频写入 Git。对应 runner 会重新生成并保留整份输入/输出证据。

## 实际结果

| 检查 | 实际结果 | 证据含义 |
|---|---|---|
| 既有 I/O CTest + 新 profile CTest | 22/22 PASS | 原 21 项文件边界保持，新配置入口通过 |
| 新 profile 的真实 CLI / direct API 对照 | 56 次正常处理调用通过 | 两 profile、8/16k、双麦、capture/duplex/短/空 render、override 顺序与 legacy |
| 配置与 tuning | 实际 init 后 get_config/get_tuning 验证 | tail、mu、floor、AGC、limiter 与其余配置逐字段核对 |
| 非法 profile、缺参、严格尾帧 | 通过 | 非法参数在打开输出前拒绝；两 profile 不完整帧非零退出 |
| Python 正/负例 | 9/9 PASS | 无隐式 tuning、所有 capture stage、duplex、事件透传、长度/帧号/非有限拒绝、工件保全 |
| 双麦冻结回放 | 42/42 完成 | 7 场景 × 3 seeds × 2 profile，每 case 600 帧/96,000 mono 样点 |
| 旧 CALL / 新缺省 / 新显式 CALL | 21/21 组 PCM 与 JSONL byte-identical | CLI-only 向后兼容，不包含后续 DSP 变化 |
| 工件回读 | 464 文件，44,364,069 B，全部 SHA-256/size 相符 | 输入、输出、命令、逐帧指标、配置/源码身份完整性 |
| 42 case 与 baseline 对照总时间 | 43.998 秒 | 本次 Host 回放 wall time；不是音频算法 RTF 或 Cortex-A32 性能 |

`--print-default-tuning` 的实际值为 CALL mu `0.219999999`、floor `0.119999997`、
AGC `-20`、limiter `-2`；ASSISTANT mu/floor `0.180000007`、AGC `-18`、limiter `-2`。
这些小数来自原 Float32 默认值的 JSON 序列化。完整 tail/config 差异另外由真实 API
读回测试确认，不以四个 tuning 字段代替完整配置验证。

## 声学描述与解释边界

以下数值由未修改的 canonical/quality 函数计算；该新组合矩阵没有声学胜出阈值，
旧 corpus/policy 的声学门槛均保持原字节。
report 中 `canonical_summary.pass_rate` 来自这些新 case 的空 `expected`，
只表示无额外声学阈值违例，不能称为声学 PASS。输出长度/帧号、固定覆盖和
CLI 等价另有实际工程检查；后续集成可在相同输入上重复 tracking 开/关构建，
仍须分别报告真实执行身份与描述值。

| 描述项 | CALL | ASSISTANT |
|---|---:|---:|
| far-only/path/gap 已知 echo case 的 median ERLE | 26.988 dB | 24.071 dB |
| 带近端真值 case 的 P10 near projection gain | −5.085 dB | −5.113 dB |
| 双讲已知 interference 的 P10 projection attenuation | 35.052 dB | 34.815 dB |
| 全部 case 最大 clipping fraction | 0 | 0 |
| 已标注 near case 的 P90 VAD onset delay | 10 ms | 10 ms |
| 已知事件 case 的 P90 ERLE recovery | 190 ms | 195 ms |

近端 projection gain 为负，说明还必须关注语音电平/保真，不能仅看回声下降。
这些是第一方有真值工程信号的描述；不宣称真人音色、pumping 或双讲听感改善，
不以 VAD onset 代替端到端 KWS 响应时间。中文 KWS FAR/FRR、ASR、
主观对讲、真实双麦房间及物理 SSC305 均为 `NOT_RUN`。

## 实施中发现与处理

源码审查发现第一版 builder 将 case `split` 写为 `regression`，而既有 canonical
schema 只允许 `dev/validation/blind`。正式矩阵执行前已保留原 `add_case()` 的
`split=validation`，并由 corpus `tier=regression` 与 `dimensions.data_role=regression`
明确本轮实际角色；新增 schema enum 正例防止复发。没有把已曝光 seed 升格为
独立验证，没有修改 schema、冻结数据角色或声学门槛。本轮正式执行没有失败 case；
单元负例的预期失败由测试明确验证，不计作真实音频结果。

## 复现命令与持续回归

从上述实际源码提交构建；这里的 `cmake`/`ctest` 可替换为环境中的绝对工具路径。
输出目录必须为新目录，工具拒绝覆写已有回放。

```sh
cmake -S . -B build-dualmic-profile \
  -DCMAKE_BUILD_TYPE=Release -DAP_BUILD_BENCH=OFF -DAP_STRICT_WARNINGS=ON \
  -DAP_BUILD_SOURCE_REVISION=edff155ce9541dc42feb1660e6b7a30d8e9fa63a
cmake --build build-dualmic-profile --target \
  ap_process_pcm ap_build_info_dump ap_process_pcm_profile_tests ap_process_pcm_io_tests \
  --parallel
ctest --test-dir build-dualmic-profile --output-on-failure -R ap_process_pcm_
python3 tests/validation/test_dualmic_profile_replay.py
python3 tests/validation/build_dualmic_profile_corpus.py --output /tmp/ap-dualmic-profile-corpus
python3 tests/validation/run_dualmic_profile_replay.py \
  --processor build-dualmic-profile/ap_process_pcm \
  --corpus /tmp/ap-dualmic-profile-corpus/corpus.json \
  --output /tmp/ap-dualmic-profile-evidence \
  --source-revision edff155ce9541dc42feb1660e6b7a30d8e9fa63a
```

CLI-only 基线对照额外加入 `--baseline-processor <438fe09构建目录>/ap_process_pcm`；
基线目录同样须包含实际 `ap_build_info_dump`。本轮该选项已实际执行。
后续包含 DSP 修复的日常 CI 不使用这个旧版本 byte-equivalence 选项，
而继续跑两 profile 实际配置/PCM oracle 与 42-case 完整回放。
根工作包负责接入既有 audio-quality workflow，无新增 workflow 或阈值放宽。

新 runner 输出 `REGRESSION_REPLAY_COMPLETE`/`FAIL` 和独立的
`quality_decision=DESCRIPTIVE_ONLY`，保存每例 PCM、metrics、continuity、command、
execution、完整 input、source/build/default-tuning 绑定及 artifact manifest。
源码与构建 revision 不符、输入/hash 漂移、缺帧或超预算均不得输出成功。
本地工作包不推送、不创建 PR、不训练；独立审查、集成版 exact-head CI/主线确认
由共同工作包继续完成。
