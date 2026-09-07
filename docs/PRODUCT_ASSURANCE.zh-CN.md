# 产品保障与认证边界（中文）

本页说明仓库软件就绪、Release、HIL 与最终 Product Certification 的权限边界。英文 canonical 文档为 [`PRODUCT_ASSURANCE.md`](PRODUCT_ASSURANCE.md)。

## 1. 软件 Release Gate

一个软件 Release 至少要求：

- exact `main` SHA 的 required `Verify/summary` 成功；
- release SHA 可追溯到 merged PR；
- live repository governance 通过；
- main ruleset 要求 PR、squash-only、review conversation resolved、strict `summary`，并禁止 delete/non-fast-forward、无 bypass；
- `v*` tag ruleset 禁止 delete/non-fast-forward、无 bypass；
- GitHub Immutable Releases 已启用。

普通 workflow `GITHUB_TOKEN` 不能充当 repository administration state 的证明。

## 2. software-commercial-ready

这是**仓库/集成状态**，不是 Product Qualification 状态。

只有在以下能力持续成立时才可使用该表述：

- public v2 API/ABI、lifecycle、ownership、realtime 规则由机器 Gate 约束；
- GCC/Clang、sanitizer、TSan、static analysis、fuzz、coverage、SDK consumer 等通过；
- 支持的 Arm 类别由 cross-build/QEMU 覆盖；
- 每个命名商用 product preset 都是 required CI contract；
- `ssc305-cortex-a32-low` 会被直接 configure/build、检查 envelope/build identity、clean install，并执行 AArch32 SDK consumer；
- Hosted performance/resource 只作为 regression evidence；
- validation 数据角色保持 development/search、validation/shadow、blind promotion 与 product-certified 隔离；
- tuning 有界、可复现，不能自动修改 shipping default；
- Release assets/checksum/SBOM/provenance/immutable identity fail-closed；
- diagnostics/replay、trusted-runner、HIL 和 Product Certification 控制面存在，但不会伪造物理权限；
- 软件/public-data program 没有 READY task，也没有把软件 blocker 隐藏到 deferred hardware task 后面。

它允许：商业产品集成、受控软件交付、预生产软件验证。

它**不允许**声称：具体板卡已验证、真机性能已证明、Product Qualification PASS、`product-certified`。

## 3. Product Certification 权威链

```text
annotated semantic release tag
  -> non-draft/non-prerelease immutable GitHub Release
     tag peel == exact release source SHA
     release tag == v<project version>
  -> audio-builder
     exact shipping compiler + sysroot + CFLAGS + SKU CMake args
  -> sealed shipping binary
  -> audio-target DUT
     deployed digest == built digest
     executed digest == deployed digest
     real route + corpus + thermal/power + policy soak
  -> release-identity-bound + attested certification bundle
  -> certification-archive
     immutable product-lifecycle archive receipt
```

仅有 reviewed commit SHA 不足以获得 Product Certification authority。

## 4. 四类真实角色

- `audio-validation`：真实/授权数据缓存与 Extended Real；
- `audio-builder`：量产编译器/sysroot/toolchain 与 sealed binary；
- `audio-target`：真实 DUT、route、声学、性能、热、功耗；
- `certification-archive`：不可变 lifecycle archive receipt。

这些角色必须由真实 self-hosted runner 提供。Hosted CI 只能验证控制面实现。

## 5. HIL 与 Product Certification 的关系

HIL 是工程/运行历史证据，不等于产品认证。

典型真实 HIL：

- Nightly 1 h；
- post-release 8 h；
- Weekly 24 h；
- 其它 policy 规定的 route soak。

`HIL_ENABLED!=true` 时，要求硬件的 scheduled/release HIL 必须 fail-visible，而不是静默 skip/PASS。

最终 Cortex-A32 LOW shipping policy 要求至少 **72 h** Product Certification。

## 6. E001 Activation Preflight

E001 preflight 用于证明基础设施已就绪：

- exact immutable release/source；
- `HIL_ENABLED=true`；
- `EXTENDED_REAL_ENABLED=true`；
- 四类 trusted role 全部 READY；
- toolchain/data/DUT/archive 输入可用。

输出 `E001_TRUSTED_INFRASTRUCTURE_READY` 仍然只是 infrastructure readiness，**不是** HIL、Extended Real、Product Certification 或 PQ PASS。

## 7. 不可伪造的证据

以下内容不得由 mock、hosted runner、QEMU、复制文件或手工 JSON 代替：

- 真机 CPU/p95/p99；
- thermal/power；
- route/XRUN/clock 行为；
- 真实产品声学；
- shipping compiler/sysroot/toolchain identity；
- build→deploy→execute binary identity；
- 72 h soak duration；
- immutable archive durability/receipt。

缺失任一项时，状态必须是 blocked/incomplete/deferred，而不是 synthetic PASS。

## 8. 软件与产品终态的区别

```text
software-commercial-ready
    = 仓库/SDK/CI/Release/控制面可商用

board-validated
    = 真实板卡性能/route/热/功耗得到证据

product-certified
    = shipping-approved policy + >=72 h + 全部物理/声学/identity/archive gate PASS
```

在 Issue #58 正式关闭前，中文和英文材料都必须保留这三个状态的区别。
