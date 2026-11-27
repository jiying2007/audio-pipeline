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


## 后继：BA0 实际 404 后的 17 条同类原件消费者闭集迁移

本节是新方法修订；上文两条失败、原方案和当时的 32/285 项测试记录保持为历史。
新冻结基线为公开 head `90a50276643960a6a8047ca6bfb095040b710369`，
tree `f4e979948e8bdedf9399336ebec4e6290f5c0d46`，Verify run `46070597129`、attempt `1`。
本节没有重跑原 head，没有把事后取回的 ZIP 改称当时 CI reader 已通过。

### 已发生的 BA0 运输失败

[`frontend-s3-t3s2b1ba0` job `140747911957`](https://github.com/jiying2007/audio-pipeline/actions/runs/46070597129/job/140747911957)
中，原 18 项 tiny、四目标收集/验证、四成员上传、严格列表身份见证均成功；
在 `2026-11-27T21:36:49.3025450Z`，已显式绑定 token/repository/run/upload-ID 的
原下载仍在 archive GET 返回 404。原独立 reader 未运行。该事实再次说明列表可见
不保证后续 archive GET 同时可取，不能归因于漏传 token，也不能断言存储后端的内部原因。

原 artifact 为 `15232189967`，名称
`frontend-fe09-t3s2b1ba0-finite-46070597129-attempt-1`。只读取回的原 ZIP 为 7,283 B，
SHA256 `5faa91a96967aa516a685d786c5961e3d39935f3436f2b9b61d05e487941bc12`；
四原成员共 79,112 B，其 SHA256SUMS 与实际字节相符。原 source receipt 绑定当次
Actions merge `a0f618255af2179a1a90c34bb67e8e4771ba8f45`，其 tree 与公开 head 相同。
原失败日志为 39,920 B，SHA256
`a8900645cbb3c5e8d3534152437d2ca0fa45d8f030e602b39a54d02721d0f1e3`。
此次保全只检查归档和身份，没有执行原 reader、SDK 或真实语音。

### 一次覆盖相同失效模式的有限名单

静态盘点在 `quality.yml` 找到同一四根成员类的 19 条消费者：现有 B2-S2、BA2 两条
保持原字节，其余 **17 条、16 个 job** 改为同一个已验证的 saved-ZIP helper。
28 条其他 schema 的 v4 下游包不在本次范围。所有上传名称、当前 run/attempt 语义、
原 source 输出、reader 目录与 reader 后续断言保持；B2S3/F0 原来没有 upload step ID，
仅补固定 ID 来使用上传结果。其余原 ID 不变。

| stage | 原 job | 原 reader 目录 | 名称含 attempt | ZIP 上限（B） | 原四成员展开总上限（B） |
| --- | --- | --- | :---: | ---: | ---: |
| `b2s1` | `frontend-reference` | `fe09-b2s1-readback` | 是 | 1,048,576 | 1,115,392 |
| `b2s3` | `frontend-reference` | `fe09-b2s3-readback` | 否 | 2,097,152 | 1,115,392 |
| `t1` | `frontend-s3-t1` | `fe09-b2s3-t1-readback` | 是 | 1,048,576 | 1,115,392 |
| `t2f0` | `frontend-s3-t2-f0` | `fe09-t2-f0-readback` | 是 | 1,048,576 | 1,115,392 |
| `t2a` | `frontend-s3-t2a` | `fe09-t2a-readback` | 是 | 1,048,576 | 1,115,392 |
| `t2b0` | `frontend-s3-t2b-b0` | `fe09-t2b-b0-readback` | 是 | 1,048,576 | 2,360,576 |
| `b1s0` | `frontend-s3-t2b-b1s0` | `fe09-b1s0-readback` | 否 | 1,048,576 | 2,360,576 |
| `b1s1` | `frontend-s3-t2b-b1s1` | `fe09-b1s1-readback` | 否 | 1,048,576 | 2,360,576 |
| `t2c0` | `frontend-s3-t2c0` | `fe09-t2c0-readback` | 是 | 1,048,576 | 2,360,576 |
| `t3s0` | `frontend-s3-t3s0` | `fe09-t3s0-readback` | 是 | 1,048,576 | 4,457,216 |
| `t3s1` | `frontend-s3-t3s1` | `fe09-t3s1-readback` | 是 | 1,048,576 | 4,457,216 |
| `t3s2a` | `frontend-s3-t3s2a` | `fe09-t3s2a-readback` | 是 | 1,048,576 | 4,495,072 |
| `t3s2b0` | `frontend-s3-t3s2b0` | `fe09-t3s2b0-readback` | 是 | 1,048,576 | 4,495,072 |
| `t3s2b1a` | `frontend-s3-t3s2b1a` | `fe09-t3s2b1a-readback` | 是 | 1,048,576 | 4,495,072 |
| `f0` | `frontend-s3-t3s2b1bf0` | `fe09-t3s2b1bf0-readback` | 否 | 8,388,608 | 4,495,072 |
| `ba0` | `frontend-s3-t3s2b1ba0` | `fe09-t3s2b1ba0-readback` | 是 | 1,048,576 | 5,543,648 |
| `ba1` | `frontend-s3-t3s2b1ba1` | `fe09-t3s2b1ba1-readback` | 否 | 1,048,576 | 5,543,648 |

15 条原有 metadata guard 的压缩上限 **1 MiB 原样保留**。B2S3/F0 原来没有压缩
metadata 上限，本次明确新冻结 2 MiB / 8 MiB；不得将这两项说成原有门限。它们分别
大于原合法展开总和 1,115,392 / 4,495,072 B，容纳四成员的普通 ZIP 封装；每个
科学 reader 原来的单成员 cap 和所有语义检查仍独立执行，不因运输总上限而放松。
旧 B2-S2 的 64 KiB / 1 MiB 与 BA2 的 8 MiB / 16 MiB 合同不变。

此次仅增加 17 项固定 stage 参数和替换相应 workflow 运输块。`class TransientHTTP`
起直到 helper 末尾的下载实现与 `90a50276` **逐字相同**；旧 visibility 模块也保持
全文件逐字相同。原 run/list/archive/blob **共用 8 次请求、10 秒单请求、94 秒总时钟
和 2 秒间隔**，没有为原 302 probe、metadata witness 或 action 再叠加一组预算。
原 302-only probe 函数仍保留历史回归测试，但新接线只请求一条 saved-ZIP 运输链。
所有 job 原来的 15–30 分钟等各自预算均未增加。

新运输成功或失败都保全同一次 `original.zip` / `original.zip.partial` 与
`transport.json`，然后只有从此 ZIP 验证得到的四成员能进入原目录。各阶段 reader
仍按原成功条件执行；任何下载失败、证据保全失败或 reader 失败都不能被后续成功覆盖。
运输 receipt 仍仅为 `PASS_TRANSPORT_ONLY`，没有科学、设备或声学晋级含义。

### 后继验收边界

现有 download tiny 扩展为 38 项，合成四成员正例遍历完整 19 个固定 stage；对
17 项新增展开边界、所有压缩 cap、错误 stage/name/attempt/upload 身份、原 reader
删除或改写、额外跳过/忽略失败、错误证据目录等做负例。原 285 项 visibility tests
只更新实际 workflow 的运输断言，原 metadata、302、分页、冲突、预算及拒绝矩阵保持。
测试直接检查当前工作树接线，再将精确 17 个新运输块及两个新增 step ID 还原，要求
16 个受影响 job 和旧 BA2 job 全部等于冻结原文，因此包含完整原 reader/所有后续断言。
本次单因果提交另有整个 workflow 块外逐字比较；独立的后续来源准备修复不属于本合同。

这些 tiny 在旧 R11 source reader 之前执行，其只读 Git 获取冻结原文时自行传
`-c safe.directory=<当前物理仓库路径>` 和 `-c core.fsmonitor=false`，先清空继承的
safe.directory 列表，不写 global 配置，不给后续步骤 export Git 环境。
`GIT_TEST_ASSUME_DIFFERENT_OWNER=1` 下检查同一实际接线，旧 R11 的外来 Git 环境
拒绝规则不变。Python 3.8 AST 只验证语法兼容，不宣称实际运行 3.8 解释器。

以上均是离线 synthetic/metadata 验收，未编译 C、运行 SDK、真实语音或原科学任务。
新公开 source 的完整 exact-head CI、17 条原 reader 的实际回读与 protected fresh-main
仍须随后真实完成；原 `90a50276` 的失败及未运行 reader 状态保留。
