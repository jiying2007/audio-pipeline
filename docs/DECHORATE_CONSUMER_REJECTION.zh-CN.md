# dEchorate 消费者拒绝与 attempt 漂移的区别

本次修复由 #872 独立登记，基于 `52abb9036e4660b58c110b58b0c568fa400d94c3`。
只修正生产者读取消费者证据时的错误分类，不改变原来源准入、实验预算或执行顺序。

## 已确认的问题

消费者在来源检查处失败时会留下 `phase=REJECTED`，但不会生成合格的 challenge
scope。旧 `consumer_receipt()` 先读取 scope 中的 run/attempt，因而将这种拒绝
误报为 `CONSUMER_ARTIFACT_ATTEMPT_DRIFT`；scope 为 null 或列表时还会成为通用类型错误。
原 #833 consumer `40707951147/a1` 与 producer `40708024530/a1` 的拒绝继续保留。
本次离线复现证明错误分类的代码路径，不补造失败当时缺失的 HTTP 响应。

## 新的错误分类

| reason | 含义与处理 |
| --- | --- |
| `CONSUMER_SOURCE_REJECTED` | 消费者已明确拒绝；查看其原来源回执，不按“attempt 变化”自动重试 |
| `CONSUMER_ARTIFACT_SCOPE_MISSING_OR_INVALID` | scope 缺失或不是 JSON 对象；证据不足，不能进入 PRE |
| `CONSUMER_ARTIFACT_SCHEMA_DRIFT` | receipt 本身不是对象；拒绝无效输入 |
| `CONSUMER_ARTIFACT_ATTEMPT_DRIFT` | scope 对象存在，但 run ID 或 attempt 的原精确字符串比较失败 |

这里的 SOURCE_REJECTED 是上游拒绝分类，不自动推断底层网络、GitHub 服务或具体源码根因。
对象 scope 内缺少 run/attempt 字段仍由原精确匹配门禁拒绝。原 run 元数据和原 artifact
身份/ZIP/hash/封存校验仍先执行，其失败原因不被本修复覆盖。已有 REJECTED 即使包含
看似正确的 scope 也不能提升成 challenge。所有错误仍非零退出；不授予 PRE、科学执行、
维护跳过或产品资格。任意上游 reason 字符串不会被回显到新 reason 中。

## 验证与边界

新增测试从相邻生产源码 AST 编译原 `consumer_receipt`、`preflight` 和 CLI 定义，
不复制被测逻辑。run/artifact 提供方明确使用离线单元夹具；这些测试不是 provider
真实性证明。既有完整 V2 测试和 exact-head/main 门禁继续执行，不能被局部测试替代。

```sh
python3 .github/program/test_dechorate_consumer_receipt.py
python3 -O .github/program/test_dechorate_consumer_receipt.py
python3 -OO .github/program/test_dechorate_consumer_receipt.py
```

正常第一/第二次 scoped receipt 仍返回原 receipt、proof、run 对象本身；真正的
run/attempt 不匹配仍拒绝；preflight 在消费者拒绝后停止，CLI 写出原 REJECTED
封装，所有授权标志保持 false。未添加网络调用、重试、workflow、数据或版本号变更。

#833 保持关闭且未合并，#714 的原 M2/M3 前置条件保持。本修复不重启这些任务，
不修改其 canonical PR、冻结身份、历史预算或科学结论。#845/#847、公共 C4 SDK、
SSC305 HIL 与 #58 产品认证仍使用各自验收证据。

## English contract

A rejected consumer is not evidence of an Actions attempt change. The producer
now rejects an explicit REJECTED receipt with CONSUMER_SOURCE_REJECTED and names
missing/non-object scope separately. Exact scoped run/attempt equality, provider
and original artifact validation, source locks and downstream challenge checks
remain mandatory. Valid receipts return the same objects without mutation.
No error creates a PRE, retry or permission. Offline selected-definition tests
exercise the real production code with marked fixtures; the existing full V2
and exact-source CI remain required. Original failures and physical boundaries
are unchanged.
