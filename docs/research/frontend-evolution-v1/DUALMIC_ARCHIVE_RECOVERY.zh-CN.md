# D1/D2 封存原件离线恢复

本入口落实 [#968](https://github.com/jiying2007/audio-pipeline/issues/968) 的 F03。
它恢复已经冻结的 D1/D2 原始 ZIP，复用原有解包和只读校验，不运行 DSP、模型或新声学实验。
既有 `dualmic_zero_d3_source.py` 在线入口、历史结果和冻结 reader 均保持原字节。

## 唯一允许的原件

元数据权威是仓库内既有
[`dualmic-zero-d3-input-lock.json`](dualmic-zero-d3-input-lock.json)，不是操作者提供的任意 JSON。

| 字段 | 固定值 |
| --- | --- |
| repository | `jiying2007/audio-pipeline` |
| run / attempt | `42321833898 / 1` |
| source revision | `cc853616685b9faf7880e6d8f8f1a89d187d342a` |
| artifact ID | `13553232106` |
| artifact name | `frontend-research-dualmic-stages-d1-42321833898-attempt-1` |
| ZIP bytes | `474165229` |
| ZIP SHA256 | `a3ab7823fdcd7586c3b72eb214b5536dcfb7531fdf0b1611d49e1575a29b2c3d` |
| members / uncompressed bytes | `3551 / 861385743` |

2026-11-28 只读查询 Actions 元数据时，此 ID 仍存在，`expired=false`，记录的到期时间为
`2027-02-05T01:02:47Z`。这是当时的可用性观察，不保证未来可下载；实际 ZIP 取回与恢复见下文。
原件仍可取时可由 Actions artifact `13553232106` 的 `/zip` 下载入口封存；长期保存必须保留
完整 ZIP 字节，解压后重新压缩的包不能通过原哈希。不要把 GitHub token 放进封存材料。

## 恢复命令

先在外部取得并保存上述原 ZIP；工具没有网络下载、上传、token 或任意来源回退能力。
从仓库根目录执行，输出目录必须不存在，至少预留原 ZIP 与解压数据所需空间：

```sh
timeout 300s python3 -B tests/validation/frontend_evolution/dualmic_archive_recovery.py \
  --archive /absolute/archive/frontend-research-dualmic-stages-d1-42321833898-attempt-1.zip \
  --output /absolute/recovery/dualmic-original-42321833898
```

工具首先检查冻结合同及 D1/D2 reader 依赖，再核原 ZIP 大小与 SHA256，拒绝符号链接、既有
目标和损坏输入。复制到新目录后，调用既有 `validate_extract` 检查成员数、路径、文件类型、
总字节及逐成员哈希；最后复用原 D2 `analysis_payload` 读取 D1/D2 原件，比较原 report、
manifest、source revision 与固定矩阵。该只读重算不是重跑原算法，也不修改旧 report。

成功产物包括 `original.zip`、`original/`、`frozen-input-lock.json`、`member-hashes.json`
和单独的 `recovery.json`。成功状态为 `RECOVERED_ORIGINAL_EVIDENCE_NO_NEW_EXPERIMENT`。
它没有 `admission.json` 或 `acquisition.json`，不能冒充旧在线采集流程的 PASS。
恢复回执明确标记 `live_actions_metadata_queried=false`、`artifact_expiration_checked=false`。
不把已过期元数据改成 `expired=false`，不改变旧在线入口的过期拒绝规则。

输入预检失败不会创建输出；复制/解包/只读核验失败保留独立 FAIL 回执和已取得材料。
重新尝试必须使用新的输出目录。外层 `timeout` 强制停止时可能仅留部分材料、没有完整回执；
只有退出零且完整成功回执才表示恢复完成。工具不覆盖或修复损坏的原件。

## 历史源码字节边界

D3 锁固定旧 source helper / D2 reader，D2 锁进一步固定 D1 的完整 source closure，包含
`validation/tools/run_validation_engine.py` 及部分 `tools/codex_assets/device_*.py`。
当前源码不再匹配时，入口必须失败。应在保留这些冻结字节的独立检出中使用恢复工具，
不能通过更新历史 lock、修改 reader 或放松哈希来让新源码冒充旧证据。

这是当前 D1/D2 一个固定源的恢复入口，不是任意历史工件导入器，不自动解决其他 `/tmp`
成果链、数据训练权利、真实双麦房间数据或目标端性能。既有拒绝候选保持原结论。

## 离线测试

```sh
python3 -B tests/validation/frontend_evolution/test_dualmic_archive_recovery.py
python3 -B tests/validation/frontend_evolution/test_dualmic_stages_source.py
python3 -B tests/validation/frontend_evolution/test_dualmic_zero_d3_source.py
```

新测试的 tiny ZIP 与 readback double 只验证运输和失败边界，不是原始音频、原始报告或新的
声学证据。完整 474165229-byte ZIP 的实际恢复须另附真实 `recovery.json`；不能用自测成功代替。

## 2026-11-28 实际原件恢复

已取得 artifact `13553232106` 的完整原 ZIP，独立复核大小和 SHA256 后，使用本入口实际恢复。
执行退出 `0`，耗时 `31.741` 秒，确认 `3551` 成员、`861385743` 解压字节；冻结 D2 reader
对 D1/D2 原件只读核验通过，原 report/manifest 与固定哈希精确相同。
回读矩阵仍为原 `60` 例、`35916` 帧、`5746560` 样本，无 DSP、模型或新的声学运行。

原样保留的[恢复回执](evidence/dualmic-archive-recovery-20261128/recovery.json)与
[执行源码/回执身份记录](evidence/dualmic-archive-recovery-20261128/execution.json)分开保存。
本地 tiny transport/负例 `14` 项、原 ZIP 边界 `7` 项、原在线元数据边界 `4` 项通过，
CI impact self-test 通过；这些本地结果不替代后继精确 PR/head/main 的 GitHub Verify。
