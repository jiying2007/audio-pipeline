# FE09 历史 Runtime 身份与当前维护源码边界

## 为什么需要单独的入口

Runtime 2.3.56 修复修改了 shipping `ap_runtime.c`。旧 R2B0/S0 预检及后续
研究来源链同时冻结这个文件的完整旧 blob，尽管六个相关研究目标的实际 C
编译依赖都不包含该 Runtime。直接修改旧 qualifier 的 hash 常量会沿着后继
实验的完整文件冻结传播，混淆原有证明与这次维护。

`fe09_runtime_maintenance_rebind.py` 保留原预检与合同字节，以固定的三个 after
blob、完整逆补丁 SHA256、before blob 和原结构锚点检查维护来源；在临时历史
副本上运行原预检及负例。`fe09_runtime_source_boundary.py` 仅为其六个后继研究
入口增加 **source_admission v1**，原 C/H、APX3/FBS1 格式、科学结果 schema、
阈值、目标集合、重复次数、编译器参数和失败日志规则均不修改。

| 新入口 | 原文件保持原字节 | 包含旧 Runtime 的历史身份字段 |
| --- | --- | --- |
| `s1` | `fe09_b2s1_private_queue_qualification.py` | `b2_s0_source_sha256` |
| `s2` | `fe09_b2s2_private_apd_qualification.py` | `s1_b2s0_git_source_sha256`, `protected_unchanged_sha256` |
| `s3` | `fe09_b2s3_threaded_qualification.py` | `frozen_s1_s2_source_sha256` |
| `t1` | `fe09_b2s3_t1_source_wrap_qualification.py` | `t0_s1_s2_source_sha256` |
| `t2f0` | `fe09_b2s3_t2_f0_feasibility_qualification.py` | `t1_upstream_s1_s2_sha256` |
| `t2a` | `fe09_b2s3_t2a_controlled_restart_qualification.py` | `t1_upstream_s1_s2_sha256` |

每个表中字段的 Runtime 条目继续保存历史 SHA256，并被新回执明确列为历史身份。
新入口逐文件检查六个原 qualifier 与实际 C/include 依赖闭包相对
`e3672ffe16e4c9d42a100e7712b9bbd3d8338545` 的完整原字节，且强制排除三个维护
变更文件作为编译输入。后续 T2b-B0 起不递归调用这些旧 Runtime 身份函数，
维持原入口即可。本改动不赋予未知的后续 shipping 变更任何豁免。

## 三个只读历史函数的作用域

只有 `S0.check_sources()`、`S2.frozen_source_identity()`、`S3.old_sources()`
执行期间，其各自的 `ROOT` 指向严格重建、逐文件核验的只读历史副本。原函数
仍检查原合同、完整 blob、Git `show BASE:path` 和原负例；函数退出立即恢复
原 ROOT，异常也恢复。副本的独立 Git metadata 使用原仓库只读对象 alternates，
其 HEAD 是真实历史 `e3672ff…`，必须与当前执行 HEAD 不同。

实际 collector、编译源 `CFILES/SOURCES`、本地头文件、`HERE`、编译输出目录、
`tools.source_head()`、`GITHUB_SHA` 和顶层 `source_commit` 始终属于真实当前
工作树。没有替换全局文件读取、hash、subprocess 或 source-head 结果，也没有
将历史源码副本标成当前 GITHUB_SHA。每次进入/退出历史函数都复验当前维护
绑定和所有受影响的原输入，历史副本也再次核验；未知变化一律拒绝。

## 新执行与独立验证回执

原四成员 `SHA256SUMS/receipt.json/collect.log/verify.log` 保持成员集合与
科学内容。receipt 增加独立版本的 `source_admission`，包含：当前提交、当前
Runtime 的 Git blob/SHA256、历史 Runtime 的 Git blob/SHA256、历史字段清单、
adapter/maintenance checker/policy/逆补丁 SHA256、真实编译依赖闭包 SHA256、
以及 `shipping_src_changed=true`。S1 顶层同名字段也必须为 true；其旧 false
仍可在未修改的原 qualifier 和历史执行回执中复验。

收集、初次验证、上传后独立读回都必须使用相同新入口。原 verifier 的 identity
比较因此包含完整 `source_admission`；缺少元数据、交换新旧 Runtime、替换
adapter、冒充历史/current 提交或隐藏 shipping 变化均拒绝。旧入口仍可用于
精确的历史源码重放；它不会接受当前维护树并声称旧 Runtime 完全未变。

```sh
# 同时执行六个原科学 self-test 和 67 个边界/独立回执强负例
python3 tests/validation/frontend_evolution/fe09_runtime_source_boundary.py --self-test

# 实际目标矩阵和独立读回；SHA 必须是当前真实工作树 HEAD
python3 tests/validation/frontend_evolution/fe09_runtime_source_boundary.py s3 \
  --collect --output fe09-b2s3 --execution-source "$GITHUB_SHA"
python3 tests/validation/frontend_evolution/fe09_runtime_source_boundary.py s3 \
  --verify --output fe09-b2s3-readback --execution-source "$GITHUB_SHA"
```

边界验证证明的是原研究输入没有被此次 Runtime 修复改变。当前 Runtime 的行为、
并发回归、公开 ABI、Release 与精确 HEAD CI 仍由维护变更自己的门禁验证。
历史预检结果不充当当前 Runtime 的执行证据；hosted/QEMU 结果不增加 HIL 或
物理产品资格。
