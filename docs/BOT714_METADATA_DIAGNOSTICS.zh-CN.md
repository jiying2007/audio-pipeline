# #714 元数据读取故障：独立只读诊断

## 适用范围

[PCR02 40683737372/a1](https://github.com/jiying2007/audio-pipeline/actions/runs/40683737372)
的维护回执为 `ORIGINAL_RESEARCH_GUARDS_REQUIRED`，原因为
`BOT_PR_READ_UNAVAILABLE`，`skip_measurement=false`。随后确认作业在路径边界
拒绝，科学步骤没有执行。原 M1 把多种 HTTP/网络异常合并为这一原因，历史日志
没有保留足以区分限流、超时、TLS、DNS 或其他读取问题的信息。

`.github/program/bot714_metadata_observation_d1.py` 提供一次**新的观察**，
保留当前请求的类型化诊断及预期/观察到的 base、head、merge 字段。
它不能恢复历史失败请求的响应，也不把新的 HTTP 200 当作原运行成功。

此工具不调用原 M1 准入、研究消费者或 DSP，不写 GitHub workflow output，
不修改原 M1、M3/V2 绑定、路径白名单、科学预算或 #833 的冻结事件。
#714 的 dEchorate 源范围拒绝仍由
[40683737498/a1](https://github.com/jiying2007/audio-pipeline/actions/runs/40683737498)
单独记录；HTTP 诊断不解决该来源门禁。

## 操作

先检出包含本工具的干净、已提交工作树。工具逐字节核对自己的提交源码，
并要求原 M1 保持固定 SHA-256
`156c2f14f02c12fe11de83d52f4c3e54a84e2ebbb558b5dd387a023d547299dc`。
仅新增诊断能力的维护不需要新的 SDK 版本。

先运行离线控制，不发出网络请求：

```sh
python3 .github/program/bot714_metadata_observation_d1.py --self-test
```

从新读取的 #714 快照取得三个完整 SHA，再执行一次观察。若 merge SHA 尚未形成，
保持待观察状态；不能用其他提交补填。输出文件必须尚不存在，其父目录必须存在。

```sh
python3 .github/program/bot714_metadata_observation_d1.py --observe \
  --expected-base "$BOT714_BASE_SHA" \
  --expected-head "$BOT714_HEAD_SHA" \
  --expected-merge "$BOT714_MERGE_SHA" \
  --output bot714-metadata-observation.json
```

端点固定为本仓库 PR #714；只有一次匿名 GET，socket timeout 为 15 秒，响应接受
上限为 150,000 字节，额外最多读取 1 字节用于判定超限。它不跟随重定向、不重试、
不读取 GitHub 凭据。工具记录自己的实际
提交/tree/脚本 SHA-256、原 M1 SHA-256 和观察起止时间。

离线控制覆盖 22 个响应场景、两个源码变更拒绝、两个请求上下文拒绝，
以及重定向禁止。普通 Verify 只运行离线控制，不自动增加实时请求。

## 如何读取结果

| 字段或结果 | 含义 |
| --- | --- |
| `HTTP_OK`、exit 0 | 本次 HTTP 200 返回了预期的三个 SHA |
| `HTTP_ERROR` | 保留本次实际 HTTP 状态及允许的诊断头；不猜测历史根因 |
| `TIMEOUT` / `TLS_ERROR` / `DNS_ERROR` / `NETWORK_ERROR` | 保留异常类别，不保留异常原文 |
| `METADATA_INVALID` | 空、超大、非 UTF-8、非法/重复 JSON、缺失 merge 或无效 PR 身份 |
| `IDENTITY_MISMATCH` | API 返回的有效身份与事先提供的三个 SHA 不一致 |
| `observer_source` | 这次观察实际执行的提交及源码字节身份 |

HTTP、网络、元数据和身份失败在保存回执后返回非零。源码或输出路径前置条件
失败时不发请求；已有证据文件不会覆盖。保存路径故障会非零退出，已生成的
回执也会输出到 stdout，调用方应保留命令日志。

仅保存 HTTP 状态、有限范围的数字限额/重试头、受限格式的 GitHub request ID
及三个 SHA。响应正文、任意头、cookie、凭据和异常原文不会进入回执。限额数字
是本次响应的观察值，不自动解释另一次历史失败。

三个 SHA 的比较只是元数据字段核对，不是 Git 合并父系验证或维护准入。
每份结果固定包含 `observation_only=true`，以及
`admission_granted=false`、`skip_measurement=false`、
`scientific_experiment_executed=false`、
`historical_failed_request_reconstructed=false`。后续原准入仍须自己的精确来源、
事件、独立门禁和真实回执；任何新观察都不重置 #833 的事件预算。

## English contract

This command makes one new unauthenticated public metadata observation for the
fixed PR #714 endpoint. It preserves only bounded typed diagnostics and exact
expected/observed SHA fields. It follows no redirects, retries nothing, and
retains no response body, arbitrary headers, credentials or exception text.
The source must be committed and the original M1 bytes must match their frozen
identity. Exit zero reports only this request's HTTP/metadata observation.
Every report explicitly denies admission, measurement skipping and scientific
execution. It does not reconstruct an earlier failed request, validate Git merge
lineage, amend original policy or create another #833 attempt.
