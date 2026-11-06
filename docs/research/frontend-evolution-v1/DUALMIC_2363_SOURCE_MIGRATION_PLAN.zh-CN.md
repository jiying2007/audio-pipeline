# 双麦 2.3.63：SYNC credit 修正的源码身份迁移 R7

日期：2026-11-06。状态：实施前冻结；不构成 DSP 执行或效果结论。

## 精确基线与原因

准备分支从受保护 main `a920beed8e2c66ea9d90442d31af9632f5c75a23`
出发，保留其 2.3.61 生产源码。原 R6 精确 proposal
`516ace7230f4846ab76941bcdeacc5465f79e2ce`、候选
`b1f40864fb0fc941561950a656041ade6e8b9b89` 和 Verify
`42186062706` 的 composition-tiny 漂移失败保留原身份。

已确认 accepted-observation cadence 与 reference-credit 消耗存在不同时间基准。
生产修复由独立因果合同限定；本准备阶段只为最终精确修复字节建立新登记。
研究源版本使用 2.3.63，使 2.3.62/R6 与 2.3.63/R7 一一对应。canonical
API 契约应如实说明 credit 语义，不为缩小登记范围保留错误文字。
最终 proposal SHA/blob 尚待提交；本合同不伪造它们，也不预报 PASS。

## 唯一允许的登记与派生

1. 新增 R7 source admission、PREREGISTRATION 和可逆 delta，登记完整
   77/66/88 原集合中的准确候选字节。预计仍为 13 个 compiled exceptions；
   若实际差异超出 R6 原 13 路径，停止并报告，不能自动扩大作用域。
2. B3/F0 仅从已保护 R6 执行器派生新的 R7 身份命名空间；原输入、角色、
   科学函数、错误处理、矩阵、进程管理、时限及产物上限保持。
3. Runtime 的 forward-maintenance 仅追加准确 2.3.63 六路径映射及独立
   正逆补丁；2.3.57–2.3.62 原映射、补丁、历史重建与负例保持。
4. F1 新增 R4 source/build 身份入口；A3 新增 R4 static-build 入口以适配
   生成头的 2.3.63。F1/A3 的 build_only 只允许一个初始失败状态字符串
   改名，不能把整个函数列入 metadata 白名单。其余科学/构建/预算函数
   以 AST 和完整源码比较保护，沿用 R6 窄例外与控制流突变负例。
5. 现有 docs gate 与 quality workflow 增加准确 2.3.63→R7 路由及独立
   artifact 名。2.3.62→R6、所有旧路由及未知版本拒绝保持。没有新增 workflow。

原 R1–R6 locks、source gates、source deltas、派生合同、collectors、F1/A3
前任入口与结果均不改字节；新的计划显式 pin 完整前任集合。源码准备 PR
不得包含 `src/`、`include/` 或 `CMakeLists.txt` 的生产变更。

## 验收、执行顺序与预算

先固定真实最终 proposal，再生成准确 pins。独立审查 source-only 准备 PR，
通过原 protected-main 门禁并合并后，候选才使用 R7 进行完整 B3/F0 执行。
旧失败和历史结果不继承为候选 PASS，实际执行 SHA 与 proposal SHA 分离。

本阶段仅运行 source/derivation/method/runtime self-tests、版本路由和原
负例；不编译、不运行 DSP、QEMU、声学回放、训练或付费任务。核验正逆
补丁、旧集合、旧字节、原门槛，以及每个科学函数/过程类的原字节。

冻结科学预算保持：B3 19,800 frames；F0 21,600 distinct frames、36
processes、144 groups；native/sanitized/ARM 120/180/300 秒；outer 300 秒、
archive reserve 60 秒、job 900 秒、retained evidence 32 MiB。不得放宽。

本 source-preparation 的设计、实现、定向自检与可审查工件总预算 **900 秒**，
从本次独立任务开始计时；各原 subprocess 上限不变。缺少最终 proposal、
预算耗尽、源码/科学函数漂移或门禁失败均如实报告，不制造最终资格。
