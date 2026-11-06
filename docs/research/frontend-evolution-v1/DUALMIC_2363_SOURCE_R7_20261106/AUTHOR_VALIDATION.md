# R7 source-only 作者验证

精确准备实现 `70c0f6491e9959bab614b2c4719150d8f98c4d3f` 绑定真实远端 proposal
`79636e3c53050639cf16573aa5cd6db37b153c93`。候选的 2.3.63 CMake、SYNC 修复
和 canonical API 文本仅作为预登记字节；准备树保持 protected main 的 2.3.61
生产源码，不运行候选 DSP。

实际 source31、derivation24、literal-method12、Runtime新14及全部原负例通过；
B3/F0 元数据自检通过。source/derivation/runtime/routes 同时在普通、`-O`、
`-OO` 下通过。77/66/88 集合、41 个历史 pin、102 个科学函数、8 个过程类、
全部科学门槛与时间/产物预算保持。两个 build_only 函数仅允许各自的一个
初始失败状态 literal；不是 metadata 白名单。

原2.3.62→2.3.63 version-only Runtime负例仍拒绝、输入和14项计数不变。
独立实测中，protected a920 原 checker 对该相同输入实际返回
`UNREGISTERED_FORWARD_MAINTENANCE_VERSION`；新增准确 2.3.63 登记后，新
checker 实际返回 `CURRENT_MAINTENANCE_SOURCE_DRIFT_docs/API_CONTRACT.md`。
本轮首次自检沿用的默认期望标签误写为 CMake mismatch，随后仅纠正为 API
mismatch；“CMake→API”指该新登记后的期望标签纠正，不是原 R6 的实际拒绝
原因。原映射和 patch 不改，verifier 不放宽。

[原始失败、实际命令、最终日志、源码审计和预算记录](../evidence/dualmic-r7-source-preparation/README.md)。
首次未提交作者尝试的文件名/诊断标签/route测试期望失败原样保存。没有声称
独立审查、完整Verify、F1/A3编译、B3/F0执行、QEMU或DUT已经通过。
