# F1 历史源码与 2.3.61 维护源码桥接

## 为什么需要独立桥接

本项是 #845 的 **F1-R2-T0 源码集成前置**，不是新的 RSS 实验结果。
登记记录：#845 评论 6527212069；起点主线为
`52abb9036e4660b58c110b58b0c568fa400d94c3`。

最新 F1 实现保存在 `9ac5a209b16210c7e514d57711f22c9b27354cb8`，
不是早期 `28871c90…` 快照。旧 R1 source-lock 的 96 个 original 成员绑定
`92a7546a75cfe0d8aca132c7ee5996dcf0005c74`。之后已发布的维护使当前部分文件
合法变化；直接把旧 guard 移到当前主线，会要求当前文件等于旧文件，因而拒绝。
不能为此修改旧哈希、回退修复，或把旧实验结果转成当前源码结果。

新脚本 `tests/validation/frontend_evolution/fe09_f1_r2_source_bridge.py`
独立处理两组身份：历史成员在原 Git 提交上证明；当前成员通过现有受保护的
R5 2.3.61 源码准入及其精确补丁证明，再逐项核对。它不替换原 F1 guard。

## 固定范围

| 对象 | 检查 |
| --- | --- |
| 最新 F1 归档 | 固定 commit/tree；qualifier blob `26ffa7922f8425ede57780a516772eb2c4ff5682` |
| 旧 source-lock | blob `460c6fbabf766c249602067863ed2b195e06cd5f` 和固定 SHA-256；完整读取，不改写 |
| 96 个历史成员 | 原提交上的 regular `100644`、Git blob、字节数和 SHA-256 |
| 9 个维护成员 | 现有 R5 2.3.61 精确源码证明；不能以任意九个变化替代 |
| 87 个其他成员 | 当前提交与历史原件逐字节相同 |
| 当前执行来源 | 干净已提交工作树、commit/tree、脚本与 R5 helper 身份；结束时再次检查 |

9 个维护成员是根 CMake、两份 pkg-config 模板、两个公共模块/runtime 头文件、
BF/SRC 模块、Linux Runtime 与 SYNC。精确 blob 必须与已保护 R5 登记一致；
未登记的变化、缺失、重命名、模式变化或工作树软链接均拒绝。

当前 R5 helper 在验证 blob 之后才被导入；归档的 F1 Python/C 文件只作为 Git 数据
读取，绝不导入、编译或执行。旧 R1 锁、原 F1 实现、原科学步骤和结果均不修改。

## 使用与验证

需要包含归档对象的完整本地 Git 历史，以及包含本脚本的干净已提交工作树。
正常 CI 的完整 checkout 提供所需对象；对象缺失时直接拒绝，不自动 fetch、
不访问 HTTP，也不制造替代对象。

```sh
python3 tests/validation/frontend_evolution/test_fe09_f1_r2_source_bridge.py
python3 -O tests/validation/frontend_evolution/test_fe09_f1_r2_source_bridge.py
python3 -OO tests/validation/frontend_evolution/test_fe09_f1_r2_source_bridge.py
python3 tests/validation/frontend_evolution/fe09_f1_r2_source_bridge.py --check
```

需要保留逐项结果时，在已存在且由调用方控制的目录写入一个新文件：

```sh
python3 tests/validation/frontend_evolution/fe09_f1_r2_source_bridge.py \
  --check --output /trusted/evidence/f1-r2-t0-source.json
```

已有文件不覆盖；输出/关闭失败均非零返回。摘要包含完整回执的 SHA-256。
回执中的 96 个 before/current 身份可独立复核；哈希是字节完整性，不是测量资格。

本脚本新增的本地 Git 读取每条命令最多 10 秒，包含 0.5 秒清理预留；stdout
按调用者声明的有界长度读取，stderr 上限 4096 字节。单源码文件上限 262144
字节、回执上限 100000 字节。归档及目标 OID 固定，Git 协议、lazy fetch 和继承的
外部 Git 上下文被禁用或拒绝。这些是源码读取边界，不改原 F1 实验时间/进程预算。
既有 R5 验证器仍执行原来的源码/补丁检查，未修改其实现或预算。

测试使用明确的合成字节与临时 Git 仓库；普通、`-O`、`-OO` 是同一组测试的三种
解释器模式，不能算成三批独立科学实验。实际仓库 96 成员检查以该精确提交的 CI
输出为准，不由合成测试代替。

## 不授予的资格和后续接入

唯一正向状态为 `F1_R2_T0_SOURCE_BRIDGE_VERIFIED_NO_EXECUTION`。
所有回执保持 F1 执行、provider 授权、测量资格、完整 F1 源码闭包、workflow 接入、
历史结果继承、shipping 和 SSC305 HIL 资格为 false。

本项只覆盖原 96 依赖的历史/当前关系，不覆盖未来 F1 的六个实现文件、三份 hook、
生成代码或完整构建依赖闭包。后续须从最新归档实现新身份的 F1 executor，保留现有
R5/PATH-R1 和 #871 控制，完成完整源码/接线审查、原控制清单、独立保护主线闭环及
真实外部 freeze 后，才能执行正式 F1 矩阵。不能直接把本回执输入旧 R1 或将其当作
执行批准。#845、#847、#714、公共 C4 SDK 和 #58 不因本项成功而自动关闭。

## English contract

F1-R2-T0 reconciles the preserved 96 original dependencies with the exact
separately reviewed 2.3.61 maintenance source. It verifies historical bytes at
the original commit and current bytes through the unchanged protected R5 proof,
with a nine-change/87-identical partition. Archived code is read as data only.
This does not alter R1, inherit any result, replace the original F1 guard,
authorize a process cohort or qualify the complete future F1 build/workflow.
Missing objects, unexpected source changes, stale proofs and incomplete receipt
writes fail. No provider request, DSP execution or product promotion occurs.
