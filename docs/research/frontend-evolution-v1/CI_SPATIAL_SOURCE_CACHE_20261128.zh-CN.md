# 既有 spatial 来源的固定缓存运输修复

本次修复对应实际 Verify `46070597129` 的 `frontend-spatial-effects`
作业 `140747911750`：原 `speech_source.py` 在 OpenSLR 下载时遇到 TLS
handshake timeout。原失败日志和失败 artifact 保留。修复只恢复此前已经准入的
**offset 8 原始来源字节**，不增加下载重试、不替换语料、不变更算法、评分或数据角色。

## 固定来源与原件证明

唯一新增 CLI profile 是 `spatial-offset8-v1`；其 frozen 对象定义在
`tests/validation/frontend_evolution/speech_source_cache_profiles.py`。
CLI 不接受任意 URL、artifact、说话人偏移或来源身份。

| 字段 | 冻结值 |
|---|---|
| 原保护 main | `21448956f65916577d13082e9dc58f275f8fbb70` |
| 原 Verify | `44281089122`，attempt 1，`push`，`head_branch=main`，全 run `success` |
| 原 spatial job | `134724309887`，success |
| 原 artifact | `14417923975`，`frontend-spatial-effects-44281089122` |
| 原 ZIP | 470,176,194 B；SHA256 `3b9a2419df9b8c1e5ba42bc24f20049e87fc28aeda6aa045d2f8f5f2b5be4cb2` |
| inner `evidence.zip` | 470,175,417 B；SHA256 `9e43c8847b4ccb9c4c073b7d03de5cd217bbef243996f34e982518febe62e525` |
| 原 source ID | `librispeech-dev-clean-spatial-v1` |
| 原准入 bound SHA256 | `f77a897bf9681af2c09f57515b99fb2d7ca072dc93371d438e872579e39f801e` |
| 原 source receipt SHA256 | `4d05852bb839b18cf9f399d27adb66cb8907cf7cfb5780bb3a73e4185e7f8150` |

该原 ZIP 已实际取回一次并验证完整 size/SHA。纯字节盘点复用了原 CAS metadata
validator 和 `speech_spatial_weights.source_check`，没有执行旧实验。
全部 46 个来源文件共 5,734,605 B；其中 32 个完整 FLAC 与已经保存、完整 SHA
再次验证的原 `dev-clean.tar.gz` 同名成员逐字节一致，合计 3,989,599 样点，
即 249.3499375 秒。

另有 8 个各 4 秒的 S16 窗口，共 32 秒；它们是原合同规定的每人四句按序拼接后
取前 4 秒的适配对象，不能把窗口与 32 个完整 FLAC 当作相同对象。
原 offset-8 source 仅保存完整 FLAC、窗口、完整解码 PCM 的历史哈希和来源说明，
**没有保存 32 个完整解码 PCM 文件**。本次检查没有调用 decoder，也没有重新
证明历史完整 PCM 解码过程。

说话人固定为 `1673, 1919, 1988, 1993, 2035, 2078, 2086, 2277`。
前四人的原角色为 `fresh-fixed-development`，后四人为
`fresh-fixed-confirmation`。这些是既有 FE03 固定诊断来源，不能更名为本轮新增
独立来源，也不能混入 F05 offset-16 的保留验证来源或改写其 637 冻结测量。
原 CC BY 4.0 attribution、`LICENSE.TXT`、`README.TXT`、`SPEAKERS.TXT`
和 decoder-version 原件全部保留。

## 复用入口与严格边界

`speech_pinned_snapshot.py` 新增 keyword-only `profile`，默认 `None`
保留旧 offset-0 CLI、常量读取、flat ZIP 读取、source checker 和 transfer receipt。
旧默认测试仍执行原文件，没有改写测试来掩盖不兼容。

新增 profile 复用原固定 GitHub API 运输、父 worker 进程组监督、失败保全、
官方来源恢复和 token 隔离。旧默认 cache 原本检查固定 head SHA、`push`
及全 run `success`，**没有显式检查 `head_branch` 字段**；新增 spatial profile
另要求 `head_branch=main`，不改变旧默认的可观察行为。实时 API 的
`expired` 必须明确为 `false`；未知、过期、错 run、错 SHA、PR 事件或失败 run
均不能作为 cache success。

`speech_source_cas.py` 只负责新的来源运输格式：

1. 验证原 ZIP 的精确 size/SHA 后，只接受外层 `evidence.zip`、`transport.json`
   两个 regular 文件。
2. 验证 inner size/SHA、canonical sidecar、manifest、原 source/run/tool 身份、
   完整对象集合、路径、mode、数量和字节上界。复用未改动的
   `.github/scripts/ci_evidence_transport.py` 严格 parser。
3. 仅解出逻辑 `effects/data/` 下的来源文件，逐对象核验 size/SHA；不调用全量
   unpack，不导出或读取原声学 result 内容。
4. 调用原 `speech_spatial_weights.source_check` 复验 f77a 合同、角色、32 FLAC
   STREAMINFO、8 窗口格式和完整来源文件哈希，然后才发布新来源目录及 transfer。

运输成功不等于当前科学结果。transfer 仍明确
`previous_scientific_score_reused=false`、
`current_acoustic_evaluation_completed=false`、`source_substitution=false`。
没有随意注册第三种 profile 的入口。

## 时间与失败语义

原 cache 的 GitHub metadata/下载调用共用 **600 秒网络 deadline**；每次调用
使用剩余时间。新增 profile 在本地 hash/extract/readback 前后检查该 deadline，
逾期拒绝成功；这不是在 Python 文件处理过程中每到 600 秒就中断的 hard alarm。

来源整体复用原 `speech_source_stage_budget.run_bounded`：父进程扣除已耗时，
以剩余 **1800 秒**监督唯一 worker 进程组，覆盖 cache、hash/extract/source check
和可能的官方恢复。不建立嵌套 process-group supervisor，不提高预算。
这一整体监督是本次接入旧 spatial job 的新增运输保护；原 spatial direct
download 行此前没有该父监督。spatial job 的 **45 分钟**总上限保持。

若 cache 不可用或被拒，先保存 profile 绑定的负回执，只允许原 OpenSLR URL、
同一完整 archive SHA/MD5、原 `speech_source.acquire(..., offset=8)` 恢复。
原下载最多三次同 URL、每次网络读取 timeout 60 秒的策略不变。
官方下载和 decoder 子进程继承的环境移除 `GH_TOKEN` / `GITHUB_TOKEN`；父级
cache 授权不因此丢失。原 ZIP partial 不会被当作原件继续下载；已发布的来源
不会在恢复路径被覆盖。错误仍导致 job 失败及原 failure artifact 保全。

## 调用与检查

CI 只替换原 spatial 来源 acquisition 行，后续 spatial weights、BF/AEC-order、
Activity、独立读回、负例、pack/upload 原命令不变。新 token 仅使用现有
`actions: read` 权限。可对已经持有的精确原 ZIP 做一次来源回读：

```bash
python3 tests/validation/frontend_evolution/speech_pinned_snapshot.py \
  --profile spatial-offset8-v1 --restore \
  --zip /absolute/path/to/original-14417923975.zip \
  --output /fresh/audit/source --transfer /fresh/audit/source-transfer.json \
  --execution-source <实际干净方法提交的40字符SHA>
```

该命令读取当前 clean checkout 的方法；不能把 dirty 新方法标成旧 90 source。
本地 source-only 回读只允许必要的只读 Git，不执行 decoder、SDK、C 编译或旧声学。
后续实际 CI 是否通过由精确新 head 的原 Actions 记录决定，不能由本说明或 tiny
tests 预先宣称成功。

新纯 tiny 测试是 `test_spatial_source_cache.py`，紧随原
`test_speech_source_recovery.py` 接入 `verify-docs-gate.sh`。覆盖闭集对象、跨
profile、原独立角色约束、branch/event/full-run、过期与缺字段、outer/inner
身份、CAS 路径/对象集合、来源 subset、原 fallback 和 token 隔离、worker
profile/预算传播及迟完成拒绝。微型 ZIP 只用于格式和控制流，不能通过真实来源准入。
