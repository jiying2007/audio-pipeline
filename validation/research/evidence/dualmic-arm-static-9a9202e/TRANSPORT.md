# ARM 静态证据：无损传输入口

原始快照及其 [README](README.md) 是保留的历史证据。测量仍对应 base
`438fe09d79ff768306c00573849517bcd91cbc6e`、candidate
`9a9202eca32cfa03d92644f5735bfc2c2429efbc`；原 ROM/arena 数字与总任务
326 秒超过 300 秒预算的失败事实不变。本次没有重跑任何测量。

原 `original/base-size.log` 和 `original/candidate-size.log` 各有真实末尾空行。
它们曾在 [Verify 42185156796](https://github.com/jiying2007/audio-pipeline/actions/runs/42185156796)
触发 strict whitespace 拒绝。为完整保留原字节，当前存储为同名 `.b64` 文件；
不是删除原日志空行，也不是修改 gate 或追加例外。其余 22 个原成员逐字节保留。

`transport/original-artifact-manifest.json` 是旧 manifest 的原字节，定义解码后的
24 个逻辑成员。当前 `artifact-manifest.json` 定义实际存储文件；传输容器变化
不改变原测量事实或原 manifest 身份。`transport-receipt.json` 记录编码映射、
原 manifest 身份、失败 PR/base/head/merge SHA 和原 impact job 日志身份。

从本目录执行：

```sh
PYTHONDONTWRITEBYTECODE=1 python3 decode_original.py
PYTHONDONTWRITEBYTECODE=1 python3 decode_original.py --output /new/external/original-snapshot
```

校验覆盖当前物理成员和哈希、旧 manifest 身份、全部 24 个解码后成员及完整
失败 CI 日志文本；输出目录必须尚不存在。解码目录恢复原路径、原 manifest 和
真实末尾空行，适合原始快照的独立复核，不应再次直接导入工作树绕过 whitespace 门禁。

失败日志以单行 base64 保存 GitHub job-log 工具返回的完整 decoded text 的 UTF-8
字节，包括原 BOM/ANSI/换行；没有声称它是 HTTP 压缩包的原始字节。
源 URI 为 `https://api.github.com/repos/jiying2007/audio-pipeline/actions/jobs/127783643002/logs`。
失败 candidate 为 `ce5d3f460c3fdb371c8ce9182b4443b2c262fb79`，base 为
`a920beed8e2c66ea9d90442d31af9632f5c75a23`，实际 checkout merge 为
`abb9dd778830e0817548183e5b036a484bedc3a6`。该失败不会被本地运输校验改写为通过。
