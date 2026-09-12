# 参与贡献（中文）

[English](CONTRIBUTING.md)

`audio-pipeline` 当前处于 **software-commercial-ready 的稳定维护状态**。欢迎解决明确缺陷、回归、产品集成问题、可测资源/性能问题，或 validation/release/certification 控制面的真实缺口；不为了“显得更完整”而主动堆复杂度。

## 修改前必读

1. [`docs/DEVELOPMENT.zh-CN.md`](docs/DEVELOPMENT.zh-CN.md)：中文开发/代码规范；
2. [`docs/ARCHITECTURE.zh-CN.md`](docs/ARCHITECTURE.zh-CN.md)：架构、依赖、线程所有权；
3. `docs/API_CONTRACT.md`：public API/lifecycle 的 canonical contract；
4. `validation/authority.json`：数据搜索/验证权限真相源；
5. [`docs/PRODUCT_ASSURANCE.zh-CN.md`](docs/PRODUCT_ASSURANCE.zh-CN.md)：Release/产品认证边界；
6. [`docs/FLOWS.zh-CN.md`](docs/FLOWS.zh-CN.md)：关键流程图。

## Scope 纪律

- 一个 PR 尽量只解决一个根因或一个契约问题；
- PR 写清 scope 与 non-goals；
- 调参前冻结 measurement、数据角色、接受阈值和预算；
- 禁止为了 CI 变绿而放宽 gate、阈值、timeout 或 allow-failure；
- 禁止伪造 target/HIL/thermal/power/acoustic/toolchain/soak/PQ 证据；
- release-neutral 维护保持 release-neutral；改变 shipping behavior 的变更遵循 SemVer/CHANGELOG/Release 治理。

## Realtime / ownership

同步 stage/core/module 禁止：heap、mutex wait、文件/网络 I/O、RPC、格式化日志和无界工作。架构 intrinsic 只放 `src/arch`，通用算法不能依赖 CPU/SOC 名称。

Linux Runtime started 后，live Pipeline 由单 DSP worker 独占。ownership、queue、counter、lifecycle 变化必须覆盖 TSan。

## API/ABI

当前 2.x public C API/ABI 是兼容契约：

- 当前兼容线只有一套 public surface，不新增平行 compatibility wrapper/alias；
- 已退役 public name/symbol 由 API/ABI gate 持续 negative-test，禁止意外复活；
- public float 先拒绝 NaN/±Inf，再检查范围；
- 保持 `AP_EINVAL` / `AP_ENOMEM` / `AP_ESTATE` 语义；
- 破坏性 public change 需要下一 major version；
- required ABI baseline 无法 fetch/resolve 时必须 fail closed。

## 测试

先加能证明根因/修复的最小 targeted test，并按需要加 negative/boundary test。依据 scope，CI 会覆盖 strict GCC/Clang、ASan/UBSan、TSan、static analysis、fuzz、coverage、backend/composition、SDK consumer、RAM/ELF pruning、paired performance、Arm/QEMU、acoustic validation 与 public API/ABI contract。

只有 **exact PR head 的 required `summary=success`** 才是可合并证据。HEAD 一旦移动，旧 CI 不能复用。

## 数据/调参

- development/search 数据可选择候选；
- `validation-grade` 只能 validation/shadow；
- `validation-grade-blind` 永远不能反馈 optimizer；
- 保存 source/data/hash/seed identity 和失败候选；
- tuning 只能形成 `ACOUSTIC_CANDIDATE`，不能静默写 shipping default，更不能产生 Product Certification authority。

## 文档同步

以下变化必须同 PR 更新文档：API/lifecycle、build option/product preset、ownership/data flow、validation authority、release/certification、diagnostics/privacy、操作命令/路径。

影响商用集成的关键变化还必须检查 `docs/*.zh-CN.md` 中文入口。低层机器 schema 和明确标记为 canonical 的英文协议继续作为唯一真相源，中文层不得另造第二套标准。

## PR 与合并

- 不直接 push `main`；
- 不 force-update release tag；
- 解决 review conversation；
- exact-head required gates 通过后走 protected squash merge；
- merge 后重新验证 exact main；
- 让受治理的 branch lifecycle workflow 清理终态 head，不绕过 exact-SHA/no-open-PR/evidence 检查。

## 完成定义

一个变更只有在以下全部完成后才算 Done：需求/根因明确、targeted+negative test、exact-head required checks PASS、相关中英文文档同步、protected merge、exact-main 再验证、Release 行为符合变更类别、且没有未分类 branch/evidence 债务。
