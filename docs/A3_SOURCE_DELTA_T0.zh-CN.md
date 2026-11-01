# FE09 A3-R2-T0：归档来源核对与当前主线差异（非执行）

本阶段独立从 #847 的最新源码归档 `c4e9cb92af2fe42f09f09bcac0d0a814a511aab8` 读取原始 Git 对象，
而不是退回旧 `ddd65039` 草稿。归档 tree 为
`66a5e619587dcaf44c0fbd3c7292435e95190179`。

**完成的能力是 A3 的历史源码对账，不是 A3 科学结果或源码准入。**

## 固定输入和检查

- 锁定原始 A3 R1 `source-lock.json` 的 Git blob `02a08648d829e3d27b7acb0bf1a1eb71790999df`，保留 DRAFT、六项实施工作未获首次执行授权的原文。
- 从原始基线 `7138b17acd6246cc779efa7597d25771ddfc8c7a` 读取 88 份文件，同时核对其在比较提交 `5187c5e59526d4047b3965b44c770ab21edbde9f` 中的 Git blob、mode、大小与 SHA-256。两者不一致直接拒绝。
- 将这些**原始对象**与执行 checkout 的当前 Git tree 比较，严格区分 SAME / DIFFERENT / MISSING。当前维护差异只记录，不将旧文件覆盖到当前源码，不重新解释历史测量或降级 SDK。
- 检查归档中的 A3 live-roll C、header、原验证器、来源 guard 和三份登记文档的精确 Git blob 与原始字节。**不会 import Python guard，也不会编译、链接或运行任何 A3 C 程序**；不会发送 HTTP 或读取 provider/Device/HIL。
- 校验 audit 本身已提交且本地 tracked bytes 与 HEAD 对应，Git 子进程只允许只读对象命令，拒绝替换 Git 对象、lazy fetch、协议访问和环境 token；每次命令限定超时与结果长度。
- 新增 16 个离线单元方法，覆盖重复／非法路径、旧基线漂移、字节哈希／长度错误、模式差异、缺失当前文件、源锁内容、重复 JSON、NaN／指数溢出、未经授权的 Git 命令以及零资格状态。三个 Python 模式检查同一组 16 项，**不是 48 个独立科研控制**。

## 运行

```sh
python3 tests/validation/frontend_evolution/test_fe09_a3_r2_source_audit.py
python3 -O tests/validation/frontend_evolution/test_fe09_a3_r2_source_audit.py
python3 -OO tests/validation/frontend_evolution/test_fe09_a3_r2_source_audit.py
python3 tests/validation/frontend_evolution/fe09_a3_r2_source_audit.py --check
```

`--check` 要求完整、已提交且可读取原始 Git 对象的 checkout。所有路径和原始 SHA 在源码中明确固定。执行结果保留实际 HEAD / tree、原归档及 88 文件的 byte identity、当前变更／缺失清单，以及所有资格拒绝标志。缺任何原始对象或凭据无需重试；不能静默给出成功。

`A3_R2_T0_ARCHIVE_DELTA_RECORDED_NO_EXECUTION` **只代表源码来源已核对**，不能代替原登记的 117 项控制、PRE/POST、外部源冻结、A3 实际 worker/driver/collector、49 步连续滚动、CPU/RSS 或 SSC305 资格。

后续需另立 T1，复核已归档 A3 C 代码的完整源依赖，按当前主线接入非安装的静态构建，然后独立处理缺少的驱动与采集器；不得把旧 workflow 片段直接覆盖当前 Quality/Verify。#847、#657 保持开放。此次不修改 SDK API/ABI、V2.3.61、F1 原始锁与其他科学门禁。

## 同一性结论的精确范围

回执 `registered_88_equal_current` 仅表示登记的 88 份源码和当前树逐项相同。
`current_tree_is_original_tree` 则**独立比较完整 Git tree 所有路径与 mode/blob**，
不能用 88/88 自动推导整个仓库 SHA/树等同于历史版本。若另增未登记文件，即使
88 项全部一致，完整树也须为 `false`；本次测试包含此负例。
完整树与历史版本不同是预期的维护演化，不是需要回滚的错误。

## English contract

A3-R2-T0 reads pinned original Git objects, verifies all 88 source bytes against
the original baseline and comparison, and reports current-tree differences.
It checks exact archived draft-source and preregistration blobs without importing,
building or running A3. No provider authorization, experiment execution, external
freeze, HIL, public SDK or shipping status is granted. Current drift is not
silently repaired or used to rewrite immutable historical references.
