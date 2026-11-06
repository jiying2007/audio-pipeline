# R7 准备证据位置修正：实施前冻结

日期：2026-11-06。本阶段仅处理研究记录的位置，不改变源码登记或执行资格。

## 精确起点与已发生失败

本地起点 `0d51e68bd6f7433b698fddde4baf7475e458d391`，tree
`10cd84c0a31e0aaa435fccdf1d608f16abbe3619`，与 PR #918 真实 head
`0761d7d24fd1c985fdf14a5e9bc3a201f8389010` 的树完全一致。protected base
是 `a920beed8e2c66ea9d90442d31af9632f5c75a23`。

Verify `42190381955` attempt 1 的 impact job `127800641572` 在实际 merge
checkout `9e42d241ee9a5f9c5f3687c11de546ad5b2a6315` 上失败：原有分类器将
`validation/research/evidence/dualmic-r7-source-preparation/` 下三份 JSON
视为 release-bearing，拒绝 base/head 同为 2.3.61。该失败及日志保持原身份。

## 唯一机械修正

使用 `git mv` 将上述目录内 README、manifest、raw-records、receipt 四文件
原字节移至 `docs/research/frontend-evolution-v1/evidence/dualmic-r7-source-preparation/`。
只更新 AUTHOR_VALIDATION 的相对链接；四文件本身连同 manifest 字节均不改。
另在独立 docs 证据目录封存完整失败日志的无损 base64 与小型来源回执。

不改变 classifier、workflow、版本、门槛、原记录、预算结果或任一 DSP 源码。
不通过改文件扩展名或新增分类例外改变门禁。准备源码仍为 protected 2.3.61；
原 R7 800.565 秒完成记录及后续文档澄清约 152/120 秒超时记录保持。

## 实际验证与预算

比较四文件迁移前后的原始字节和 manifest；记录精确 commit/tree。
从 protected a920 提取原 ci_impact 与 immutable-whitespace checker，
对 a920 至新提交实际执行；要求 SemVer 检查通过、原需 full code/quality
仍触发、严格 whitespace 零例外。失败不放宽规则，保留真实日志。

本阶段总预算 300 秒；只做上述记录与门禁检查，不运行 DSP、编译、训练、
声学回放或新 source self-tests。最终 CI 资格仍由新精确 head 的 Verify 给出。
