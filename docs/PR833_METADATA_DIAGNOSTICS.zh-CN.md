# PR #833 原始元数据诊断：保留字节，不改变准入

## 原因与边界

独立登记为 #870，基于 `3fde387d1e6008771f9d819116381c94a70d03c9`。
原 consumer `40707951147/attempt-1` 在来源验证处拒绝，原 producer
`40708024530/attempt-1` 未授予 PRE。旧收据只能看到 merge SHA 的 null 投影，
无法区分字段缺失、显式 null、零 OID 或非法类型/字符串；当次完整 GET 正文没有保存。
新请求不能恢复那次历史响应，也不能证明唯一历史根因。

GitHub 的官方 Get a pull request 文档说明 `mergeable` 可暂为 null，
并且 `merge_commit_sha` 的含义随合并状态变化。这只是 API 背景，不证明该机制
就是原 #833 失败原因，也不允许用别的 SHA 补填未知字段：
https://docs.github.com/en/rest/pulls/pulls#get-a-pull-request

本工具不调用或修改原 M1/M2/M3/V2 准入、科学脚本、原工作流、冻结源码、
#833 事件预算、#714 负责人、SDK 版本或 DSP。它不产生 CHALLENGE、PRE、
workflow output、维护跳过、声学 PASS 或产品资格。

## 离线控制与新观察

普通 Verify 仅在既有 docs gate 中运行以下离线测试，不发送实时请求：

```sh
python3 .github/program/test_pr833_metadata_observation_d1.py
python3 -O .github/program/test_pr833_metadata_observation_d1.py
python3 -OO .github/program/test_pr833_metadata_observation_d1.py
```

测试使用显式标记的 HTTP/JSON 夹具与临时本地 Git 仓库。三个 Python 模式验证的是
同一组控制，不是三批独立科学实验。它们不能替代实际 provider 响应或原协议验收。

独立批准一个新的观察上下文后，从另行标明来源的快照获得预期 base/head/merge，
在包含本工具的干净、已提交工作树执行一次；预期值只是比较上下文，不是准入凭证。
工具拒绝零值、短 SHA、非法类型以及已有输出目录，不允许补造未知的 merge 值。

```sh
python3 .github/program/pr833_metadata_observation_d1.py \
  --expected-base "$PR833_BASE_SHA" \
  --expected-head "$PR833_HEAD_SHA" \
  --expected-merge "$PR833_MERGE_SHA" \
  --output /trusted/evidence/pr833-new-observation
```

父目录必须由调用方控制并已经存在。新证据目录以 0700 创建；已有目录及目录符号链接
均在网络请求之前拒绝。工具核对自己的提交字节、commit/tree、工作树状态及原来源
helper 的固定 SHA-256 `c8a2bfdade22d33fb40155b440d80d960524adccdef10cf9131340bbb84a81f6`，
并在请求后再次检查源码。源码变化也必须非零退出。

请求固定为本仓库 PR #833 的公开端点，单次匿名 GET，不读取凭据，不使用环境代理，
不跟随重定向、不重试、不轮询。socket timeout 为 15 秒，不宣称它是整个进程的
绝对 wall-time 上限。响应接受上限 150,000 字节，额外最多读 1 字节用于超限判定。
不会因失败再请求一次。

## 四份证据文件

| 文件 | 含义 |
| --- | --- |
| `response.body` | 本次实际收到的原始正文或有界前缀；没有收到正文时为空 |
| `response.body.sha256` | 上述字节的 SHA-256；不代表来源认证或内容有效 |
| `receipt.json` | 预期/观察身份、字段类型、HTTP 状态、受限响应头、时间、源码及拒绝边界 |
| `receipt.json.sha256` | 回执字节 SHA-256 |

```sh
cd /trusted/evidence/pr833-new-observation
sha256sum -c response.body.sha256 receipt.json.sha256
```

校验和仅检查字节完整性，不证明 GitHub 传输真实性，也不能防止整个证据集合被重签。
审计仍需原始采集来源/run/日志和独立源码验证。raw 文件可能含公开 PR 正文，不能打印
到 stdout 或自动提交到 Git；按既有证据留存策略保管。只将有限固定字段写入摘要，
不写任意头、cookie、凭据、异常原文或未验证字符串。

空/无效 UTF-8、重复键/非有限 JSON、超限、HTTP 错误、网络错误、源码漂移和
写入/关闭失败都不能给出成功。超限最多保留 150,001 字节并标记不完整；IncompleteRead
只保留异常实际提供的部分字节，不编造未收到内容。其他传输异常未暴露部分字节时，
也不声称已经保存那些字节。输出异常可能留下不完整的目录，必须保留并视为失败，
不能复用目录、覆盖旧文件或将其当完整收据。

## 结果解释

`merge_field_kind` 严格区分 `MISSING`、`NULL`、`WRONG_TYPE`、`ZERO_OID`、
`INVALID_STRING` 和 `VALID_OID`。只有有效非零完整 OID 才输出其值。

| outcome | 解释 |
| --- | --- |
| `OBSERVED_MATCH`，exit 0 | 仅本次 HTTP 200 的公开 PR 身份与三个预期 SHA 一致 |
| `MERGE_IDENTITY_UNAVAILABLE`，非零 | 字段缺失或显式 null，不当作合并身份通过 |
| `MERGE_IDENTITY_INVALID` / `IDENTITY_MISMATCH` / `PR_STATE_MISMATCH` | 类型/值/开放状态不满足本次比较 |
| `METADATA_INVALID` | JSON 或仓库/作者/分支身份不合格 |
| `BODY_TOO_LARGE` / `PARTIAL_BODY` | 保存的是有界前缀或部分响应，不能当完整正文 |
| `HTTP_ERROR` / `TIMEOUT` / `TLS_ERROR` / `DNS_ERROR` / `NETWORK_ERROR` | 本次请求的实际失败类别，不推断历史根因 |
| `SOURCE_CHANGED_DURING_OBSERVATION` | 请求期间执行源码变更，拒绝成功 |

所有回执始终保持 `observation_only=true`，以及 `admission_granted=false`、
`source_range_qualified=false`、`skip_measurement=false`、
`scientific_experiment_executed=false`、`historical_failed_request_reconstructed=false`。
本诊断能力的合并不能关闭 #833、#714、F1/A3、公共 C4 SDK 或 #58 实机资格。

## English contract

This fixed-endpoint command captures one new anonymous public PR833 response,
not an earlier missing response and not a protocol retry. It preserves exact
received body/prefix bytes and hashes, distinguishes missing/null/invalid merge
identities, and never grants source, maintenance, scientific or product admission.
The original helper is pinned and unchanged. A clean committed observer checkout
and a new trusted output directory are mandatory before any request; source is
rechecked afterward. Redirects, environment proxies, credentials, polling and
retries are excluded. The byte cap is 150,000 plus one sentinel byte and the socket
timeout is 15 seconds, not a whole-process deadline. Incomplete transport or
output evidence remains a failure. Normal CI uses offline controls only.
