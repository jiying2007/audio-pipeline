# B2-S2 / BA2 原 ZIP 的两条实际运输失败修复

日期：2026-11-28（北京时间）。冻结基线为 [#972](https://github.com/jiying2007/audio-pipeline/pull/972)
的实际 head `011ed322013fc7c1f009cedba5cc6ea0e594871b`。这是
[#968](https://github.com/jiying2007/audio-pipeline/issues/968) 科研平台实施中已经发生的两条运输失败。
下列身份、范围、上限和验收条件在新代码及新 CI 结果之前冻结。

## 失败原件与可证实的原因范围

两项均来自 Verify run `46052549428`、attempt `1`、上述精确 PR head。

| 项目 | B2-S2 | BA2 |
| --- | --- | --- |
| Job | [`140689095553` / frontend-reference](https://github.com/jiying2007/audio-pipeline/actions/runs/46052549428/job/140689095553) | [`140689095921` / frontend-s3-t3s2b1ba2](https://github.com/jiying2007/audio-pipeline/actions/runs/46052549428/job/140689095921) |
| 失败 step | 34，原四成员下载 | 7，原 A2 下载 |
| 原 artifact ID | `15226021798` | `15226066378` |
| 原上传名称 | `frontend-fe09-b2s2-private-apd-46052549428-attempt-1` | `frontend-fe09-t3s2b1ba2-retirement-46052549428` |
| ZIP 字节数 | 4,586 | 3,554,186 |
| ZIP SHA256 | `d42344b6047f1fe4025fdd2ad14835521a95438166c987367983fdee27f50b04` | `0c1e8a4499f5d5742a4859839f034097776c90d445a9b2268afaa759813bfcbf` |
| 四成员展开字节数 | 17,072 | 4,922,078 |

B2-S2 的原资格、四成员上传及严格 REST 列表身份见证均成功。原下载已经显式绑定
token、repository、run ID 和上传 artifact ID；在 `2026-11-27T19:04:23.726Z`，后续
REST archive endpoint 仍返回 `Not Found`。因此，**metadata/list 可见不能证明 archive
endpoint 已经可取**。见证日志中的 `attempt=2` 是两次 HTTP 请求，不是 workflow attempt 2。

BA2 的原科学执行用时 12 分 26 秒，原上传及正整数 upload-ID 检查成功；后续默认下载
报 `None of the provided artifact IDs found`。该 step 未显式传 token，不能把 action
日志显示的默认 repository/run ID 误写成“没有 run ID”。两项原独立 reader 都未运行。
现有日志足以定位运输阶段失败，不能据此断定 GitHub 底层存储服务的具体根因。

原日志、metadata 和原 ZIP 已独立保全。两份 ZIP 均为下列四个根成员，使用 deflate、
flag 8、普通文件属性；下表是原件观察值，不是后续科学 reader 的阈值修改。

| 成员 | B2-S2 字节数 | BA2 字节数 |
| --- | ---: | ---: |
| `SHA256SUMS` | 234 | 234 |
| `receipt.json` | 12,800 | 123,688 |
| `collect.log` | 3,995 | 4,798,098 |
| `verify.log` | 43 | 58 |

## 冻结的两项合同

新增 `tests/validation/frontend_evolution/fe09_same_run_artifact_download.py`，仅有
`b2s2`、`ba2` 两个 stage。没有任意 artifact、名称模糊匹配、历史结果替代或镜像入口。

| stage | 保留的原名称规则 | 压缩上限 | 展开总上限 |
| --- | --- | ---: | ---: |
| `b2s2` | 原 prefix + 当前 run ID + `-attempt-` + 当前 attempt | 64 KiB | 1 MiB |
| `ba2` | 原 prefix + 当前 run ID，仍为 run-only 名称 | 8 MiB | 16 MiB |

BA2 的上限来自已保存原件的量级，独立于 B2-S2；旧 visibility helper 的全局 1 MiB
谓词和名称 allowlist 完全不变。新工具直接校验真实 metadata，不能伪造或改写 size
再借旧谓词通过。BA2 虽保留 run-only 名称，仍必须通过实际 run-attempt endpoint、
head/repository/execution source、`created_at >= run_started_at` 及完整列表唯一性检查。
旧 attempt、同名异 ID、同 ID 异名、重复 ID、过期、来源冲突均失败。

复用旧 helper 的 `NoRedirect`、`verify_run_identity`、`utc_timestamp`、
`reject_duplicates` 等严格原语。run lookup、完整分页列表、archive API 和 blob GET
**共同最多 8 次 HTTP**。列表每页最多 100 项、总量最多 1,000，任何部分列表都不能提前
接受；允许原有缺项/变化快照在剩余预算内重新从第一页列举，已观察到的身份或 schema
冲突立即拒绝。

每次 HTTP 最多 10 秒，瞬时 HTTP `404/502/503` 可在剩余预算内等待 2 秒后重取。
`401/403/429`、其他 HTTP 状态、TLS/网络错误、摘要/大小及身份/schema 冲突不重试。
blob 瞬时缺失会先重新请求 archive endpoint 取得新短时 URL，两次请求都计入同一账本。
没有第二组八次额度，也没有无界 sleep。

整体硬时钟固定为 `8 × 10 + 7 × 2 = 94` 秒，覆盖网络响应体读取、保存、解压和成功
receipt 写出。POSIX `setitimer` 同时约束单请求和全程，避免持续小块响应绕过普通 socket
timeout。超过预算不得留下最终 PASS；停止后只允许写入小型失败记录，不再请求、读取
归档、解压或运行科学任务。原两个 job timeout 不变。

## 同一份保存的 ZIP 交给原 reader

[GitHub REST archive 文档](https://docs.github.com/en/rest/actions/artifacts?apiVersion=2022-11-28#download-an-artifact)
规定 archive endpoint 返回短时下载 URL。工具显式处理这两阶段：只向
`api.github.com` 发送 token；对 HTTPS Azure 生产存储 URL 建立新的、没有 Authorization
的请求。host 仅接受 `productionresultssa[0-9]+.blob.core.windows.net`。该收窄规则的
实际依据是本轮已成功的 S2-A 下载 host `productionresultssa3.blob.core.windows.net`。
如服务迁移到其他 host，当前合同应失败，不能自行扩宽。signed path/query 和 token
只存在请求内存中，不能写入日志、receipt 或保留产物。

metadata 精确绑定上传 ID、原名、run、attempt 和 source，并给出预期 ZIP size/digest。
工具流式保存原字节，核对精确长度及 SHA256；中断或内容错误保留有界的
`original.zip.partial`。只有外层身份/size/hash 成功，才命名为 `original.zip`。
随后直接读取这一份 ZIP，检查精确四根成员、CRC、展开总量及普通文件类型；拒绝重复、
目录、路径逃逸、symlink/特殊文件、加密和非 stored/deflate 压缩。没有 `extractall`。
四成员全部通过后才写入原 reader 的新目录，没有第二次独立下载。

原 ZIP/失败前缀与 `transport.json` 存入单独的新目录；原 reader 目录仍只有原四成员。
两目录和所有父级拒绝 symlink、父路径穿越和已存在目标，不能覆盖已有证据。新的运输
保留 step 使用原已固定 SHA 的 upload-artifact v7 和原 30 天保留期，成功与失败均留存。

**`PASS_TRANSPORT_ONLY` 只证明运输及 ZIP 边界。** 原科学执行、原四成员上传名称/ID、
原独立 reader 的 source/hash/负例、全部阈值、预算和 SDK 均保持不变。原 reader 仍需
实际执行成功，不能用运输 receipt 代替科学判定。

旧 `check_a1_archive_ready`、`check_t2f0_archive_ready`、`check_t2a_archive_ready`
仅检查 302，不跟随 URL、不保存响应体、不验证 ZIP；其请求预算独立于旧 metadata
见证。它们不能替代本次同一份已保存 ZIP，也不能消除后续独立下载的时间差。整个旧
helper（包括原 14 项函数/类和这些 probes）逐字保留，不改其他尚未观察到失败的路径。

## 入口、验证与待完成边界

实际 workflow 已使用下列固定入口；该入口要求当前运行中的确切 attempt，不能用于
把已经结束的失败 run 重判为成功。token 仅来自既有 `GH_TOKEN` 环境变量。

```sh
python3 tests/validation/frontend_evolution/fe09_same_run_artifact_download.py \
  --stage b2s2 --repository "$GITHUB_REPOSITORY" \
  --artifact-id "$ARTIFACT_ID" --run-id "$GITHUB_RUN_ID" \
  --artifact-name "frontend-fe09-b2s2-private-apd-$GITHUB_RUN_ID-attempt-$GITHUB_RUN_ATTEMPT" \
  --run-attempt "$GITHUB_RUN_ATTEMPT" --run-head-sha "$RUN_HEAD_SHA" \
  --execution-source "$GITHUB_SHA" \
  --output fe09-b2s2-readback --evidence fe09-b2s2-transport
```

BA2 使用 `--stage ba2`、原名 `frontend-fe09-t3s2b1ba2-retirement-$GITHUB_RUN_ID`，
输出固定为 `fe09-t3s2b1ba2-readback` 和 `fe09-t3s2b1ba2-transport`；其余身份参数相同。
没有 CLI 参数能放宽 cap、请求数或时钟。

本地针对性验证入口已经登记到现有 `verify-docs-gate.sh`：

```sh
python3 -m unittest discover -s tests/validation/frontend_evolution -p test_fe09_same_run_artifact_download.py -q
python3 -m unittest discover -s tests/validation/frontend_evolution -p test_fe09_same_run_artifact_visibility.py -q
```

新增 32 项离线 ZIP/HTTP tests 与既有 285 项 tests 通过。覆盖 metadata 成功后的
archive 404、两阶段共享额度、完整列表和旧 attempt 拒绝、两个独立 size cap、
token/URL 不泄露、大小/摘要/CRC、压缩展开边界、路径/类型/重复成员、失败前缀及
超时后不能留下 PASS。另以真实 POSIX 短时 alarm 中止合成阻塞读取，未访问网络。
所有内容为 tiny 合成字节，没有运行 DSP、原科学任务、真实网络或声学 replay。

独立源码比较确认：旧 helper 全文件 SHA256 为
`80faa9731e4fd2437813ceb5847bda47b8dc7f6d671a43c6583b13dc3bb0ef9f`，与冻结基线
逐字相同；除两块运输替换外整个 `quality.yml` 逐字相同；原 gate 只增加一条新测试。
Python 3.8 AST 检查与 `git diff --check` 通过。这不是实际 Python 3.8 解释器执行声明。

本地测试不替代实际 CI。新 exact-head required summary、两个原 reader 的实际回读及
protected fresh-main 仍待后续验收，统一在 #968 登记。保留两次原失败，不自动 rerun、
取消、merge 或重写历史科学结论。
